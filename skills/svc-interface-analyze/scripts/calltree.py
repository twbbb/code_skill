#!/usr/bin/env python3
"""gocalls.sh 产出的调用树骨架 testcase/analysis/<接口名>/<时间戳>.calltree.json：解析和写回。

读或改这棵树时抄下面的函数，或直接跑：

  python3 calltree.py list testcase/analysis/GetAccessToken/20261016120000.calltree.json
  python3 calltree.py list --open testcase/analysis/GetAccessToken/20261016120000.calltree.json

补断点落到一个树上还没有的方法时，不要只写 file/line。expand 会用
gocalls.sh 拉这个方法的整棵调用链，挂到断点节点的 calls 下：

  python3 calltree.py expand testcase/analysis/GetAccessToken/20261016120000.calltree.json \
    --dir /path/to/module --entry 'pkg.(Type).Method' --onto 'iface.Foo' \
    --entry 'pkg.(Type2).Bar' --onto 'iface.Bar'

--entry/--onto 成对，可以一次挂多对；任一对挂不上就整体不写入。

判断参考版本还能不能直接用：列出它的 meta.commit 之后（含未提交改动）调用链涉及的源文件里哪些改了：

  python3 calltree.py changed testcase/analysis/GetAccessToken/20261016120000.json --dir /path/to/repo

改节点就地改 dict，然后 dump 整文件覆盖。expand 同样要在沙箱外执行，因为它会调 gocalls.sh。
"""
import copy
import json
import os
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

# --- 抄这段 ---


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dump(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def roots(data):
    return data if isinstance(data, list) else [data]


def walk(node, path=None):
    if not isinstance(node, dict):
        return
    path = (path or []) + [node.get("name", "")]
    yield node, path
    for c in node.get("calls") or []:
        yield from walk(c, path)


def iter_nodes(data):
    for r in roots(data):
        yield from walk(r)


def breaks(data, open_only=False):
    """带 break 的节点。(node, path)。open_only 只留没 skipped/todo 的。"""
    out = []
    for node, path in iter_nodes(data):
        if "break" not in node:
            continue
        if open_only and (node.get("skipped") or node.get("todo")):
            continue
        out.append((node, path))
    return out


def find(data, **eq):
    """所有 eq 字段都匹配才命中，如 name=..., pkg=..."""
    for node, path in iter_nodes(data):
        if all(node.get(k) == v for k, v in eq.items()):
            yield node, path


# --- 抄到这里 ---
#
# 标桩（仓库外 / 接口 invoke 跟不下去）：
#   for node, _ in breaks(data, open_only=True):
#       if not node.get("inModule"):
#           node["skipped"] = "桩/仓库外"
#   dump(path, data)
#
# 补本仓库实现：走 expand，把新方法整棵调用链挂上。只写 file/line 会漏掉下游。
# 手改只用于 expand 挂不上的个别字段；挂调用链不要手写一个叶子。
#
# 多实现分不清：
#   for node, _ in find(data, name="iface.Bar"):
#       if node.get("break") and not node.get("skipped"):
#           node["todo"] = "候选: a/impl.go:10, b/impl.go:30"
#   dump(path, data)


def report(data, open_only=False):
    items = breaks(data, open_only=open_only)
    all_items = breaks(data)
    open_n = len(breaks(data, open_only=True))
    print(f"total breaks: {len(all_items)}  open: {open_n}")
    print("\n=== unique names ===")
    c = Counter((n.get("name", ""), n.get("pkg", "")) for n, _ in items)
    first = {}
    for n, _ in items:
        first.setdefault((n.get("name", ""), n.get("pkg", "")), n)
    for (name, pkg), n in c.most_common():
        node = first[(name, pkg)]
        skipped = node.get("skipped")
        todo = node.get("todo")
        print(
            f"{n:3d}  inModule={str(node.get('inModule')):5}  "
            f"skipped={skipped}  todo={todo}  {name}  pkg={pkg!r}"
        )
    if not open_only:
        print("\n=== open (no skipped/todo) ===")
        for node, path in breaks(data, open_only=True):
            loc = f"{node.get('file')}:{node.get('line')}" if node.get("file") else "-"
            print(f"{' > '.join(path[-4:])}  {loc}  {node.get('break')}")
            for c in node.get("candidates") or []:
                print(f"    候选 {c}")


def _same_method(a, b):
    return (
        a.get("name") == b.get("name")
        and a.get("file") == b.get("file")
        and a.get("line") == b.get("line")
    )


def graft(data, onto, root):
    """把 root 整棵调用链挂到未处理断点（name == onto）的 calls 下，并去掉 break。

    同名同位置的叶子换成这棵树；已经带 calls 的不覆盖。返回改了几个断点。
    """
    targets = []
    for node, _ in iter_nodes(data):
        if node.get("name") != onto or "break" not in node:
            continue
        if node.get("skipped") or node.get("todo"):
            continue
        targets.append(node)
    n = 0
    for node in targets:
        calls = node.setdefault("calls", [])
        replaced = False
        for i, child in enumerate(calls):
            if not isinstance(child, dict) or not _same_method(child, root):
                continue
            if not child.get("calls") and root.get("calls"):
                calls[i] = copy.deepcopy(root)
            replaced = True
            break
        if not replaced:
            calls.append(copy.deepcopy(root))
        if not node.get("file") and root.get("file"):
            node["file"] = root["file"]
            node["line"] = root["line"]
        node["inModule"] = True
        del node["break"]
        n += 1
    return n


def run_gocalls(module_dir, entry):
    """跑 gocalls.sh，返回唯一入口的那棵树。0 个或多个入口都直接退出。"""
    script = Path(__file__).resolve().parent / "gocalls.sh"
    with tempfile.TemporaryDirectory() as tmp:
        env = os.environ.copy()
        env["OUT_DIR"] = tmp
        env.pop("OUT", None)
        proc = subprocess.run(
            [str(script), module_dir, entry],
            env=env,
        )
        if proc.returncode != 0:
            sys.exit(proc.returncode)
        produced = list(Path(tmp).glob("*.json"))
        if len(produced) != 1:
            sys.exit(f"gocalls 产出 {len(produced)} 个 json，期望 1 个")
        forest = load(produced[0])
    if isinstance(forest, dict):
        forest = [forest]
    if len(forest) != 1:
        names = ", ".join(n.get("name", "") for n in forest) or "(无)"
        sys.exit(
            f"gocalls 命中 {len(forest)} 个入口（{names}）。"
            "收窄 --entry；仍多个就给断点标 todo，不要挂。"
        )
    return forest[0]


def source_files(page_path, repo):
    """页面 JSON 里每个 src 的文件，加上同时间戳骨架里每个节点的 file，都转成相对仓库根的路径。"""
    files = set()

    def page_walk(n):
        src = (n.get("src") or "").rsplit(":", 1)[0].strip()
        if src.endswith(".go"):
            files.add(src)
        for k in n.get("kids") or []:
            page_walk(k)

    page_walk(load(page_path)["tree"])
    skeleton = page_path[: -len(".json")] + ".calltree.json"
    if os.path.exists(skeleton):
        for node, _ in iter_nodes(load(skeleton)):
            if (node.get("file") or "").endswith(".go"):
                files.add(node["file"])
    top = subprocess.run(["git", "-C", repo, "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True, check=True).stdout.strip()
    rel = set()
    for f in files:
        absf = f if os.path.isabs(f) else os.path.join(repo, f)
        rel.add(os.path.relpath(os.path.realpath(absf), os.path.realpath(top)))
    return top, sorted(rel)


def changed(page_path, repo):
    """meta.commit 之后（含未提交改动）调用链涉及的源文件有哪些改了。"""
    commit = load(page_path).get("meta", {}).get("commit")
    if not commit:
        sys.exit(f"{page_path} 没有 meta.commit")
    top, files = source_files(page_path, repo)
    if not files:
        sys.exit(f"{page_path} 里没有 .go 的 src，无法判断")
    out = subprocess.run(["git", "-C", top, "diff", "--name-only", commit, "--"] + files,
                         capture_output=True, text=True, check=True).stdout.split()
    print(f"meta.commit={commit} 涉及文件 {len(files)} 个")
    print("\n".join(f"changed {f}" for f in out) if out else "无改动")


USAGE = """usage:
  calltree.py list [--open] <json>
  calltree.py expand <json> --dir <module> --entry <method> --onto <break name> [--entry ... --onto ...]
  calltree.py changed <页面 json> --dir <仓库>"""


def _expand_args(args):
    """--entry/--onto 成对出现，可以多对，一次挂完。"""
    module_dir = None
    entries, ontos = [], []
    positional = []
    it = iter(args)
    for a in it:
        if a in ("--dir", "--entry", "--onto"):
            try:
                v = next(it)
            except StopIteration:
                sys.exit(USAGE)
            if a == "--dir":
                module_dir = v
            elif a == "--entry":
                entries.append(v)
            else:
                ontos.append(v)
        elif a.startswith("-"):
            sys.exit(USAGE)
        else:
            positional.append(a)
    if len(positional) != 1 or not module_dir or not entries or len(entries) != len(ontos):
        sys.exit(USAGE)
    return positional[0], module_dir, list(zip(entries, ontos))


def main(argv):
    if not argv:
        sys.exit(USAGE)
    cmd, args = argv[0], argv[1:]
    if cmd == "list":
        open_only = "--open" in args
        args = [a for a in args if a != "--open"]
        if len(args) != 1:
            sys.exit(USAGE)
        report(load(args[0]), open_only=open_only)
        return
    if cmd == "changed":
        if len(args) != 3 or args[1] != "--dir":
            sys.exit(USAGE)
        changed(args[0], args[2])
        return
    if cmd == "expand":
        path, module_dir, pairs = _expand_args(args)
        data = load(path)
        for entry, onto in pairs:
            root = run_gocalls(module_dir, entry)
            n = graft(data, onto, root)
            if n == 0:
                open_names = sorted({node.get("name", "") for node, _ in breaks(data, open_only=True)})
                shown = ", ".join(open_names[:20]) or "(无)"
                sys.exit(f"没有可挂的未处理断点 name={onto!r}，本次一对都没写入。当前未处理：{shown}")
            downstream = sum(1 for _ in walk(root)) - 1
            print(
                f"grafted {n} break(s) onto={onto!r} "
                f"method={root.get('name')} downstream={downstream}"
            )
        dump(path, data)
        return
    sys.exit(USAGE)


if __name__ == "__main__":
    main(sys.argv[1:])
