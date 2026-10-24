#!/usr/bin/env python3
"""对比用例文档的代码基线和被测服务当前代码（含未提交改动），列出受代码改动影响的用例。

基线写在用例文档「## 测试前置」下的「### 代码基线」，一行，由 stamp 写入：
  - `<服务>`：`<分支>` @ `<40 位 commit>`（有未提交改动）
「（有未提交改动）」表示 stamp 时工作区不干净：那时没提交的改动这次还会算成改动，宁多不漏。

用法：
  code_impact.py impact --doc <服务>/testcase/<服务>.md
  code_impact.py stamp  --doc <服务>/testcase/<服务>.md

impact 比「基线 commit → 当前工作区」，没跟踪的新 .go 文件整个算新增。改动按 Go 顶层声明（func、type、var、const）归并，
每条没废弃的用例判定为：
  直接命中      用例正文里的 `文件:行` 落在改动声明里
  调用链有改动  用例入口的调用链（流程链路引用的调用树里每个节点的 src，加同名骨架的 file:line）经过改动声明
  无改动        以上都没有
  未关联调用链  找不到对应的流程链路，且没有直接命中
_test.go、testcase/ 和 import 不算改动。另外列出：每个入口调用链经过的改动声明、落在改动声明上的流程链路节点、
日志关键字在当前代码里搜不到的节点、非 Go 文件改动、不在任何入口调用链上的改动声明。
"""
import argparse
import json
import os
import re
import subprocess
import sys

CASE = re.compile(r"^### (\d+[a-z]?)\.\s*(.*)$")
CASE_ENTRY = re.compile(r"^`([^`]+)`")
BASE_LINE = re.compile(r"^- `([^`]+)`[：:]\s*`([^`]+)`\s*@\s*`([0-9a-f]{7,40})`(（有未提交改动）)?")
CHAIN = re.compile(r"^- `([^`]+)`[（(]`?(analysis/[^`）)]+\.json)`?[）)]")
CHAIN_NODE = re.compile(r"^\s+(\d+)\.\s*(.*)$")
REF = re.compile(r"([\w./-]+\.go):(\d+(?:\s*[、,，]\s*\d+)*)")
REF_SHORT = re.compile(r"[（(]:(\d+)[）)]")
KEYWORD = re.compile(r"`([^`]+)`[（(]([^）)]*)[）)]")
DECL = re.compile(r"^(func|type|var|const|import)\b")
FUNC = re.compile(r"^func\s*(?:\(\s*(?:\w+\s+)?\*?\s*(\w+)(?:\[[^\]]*\])?\s*\)\s*)?(\w+)")
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
WORKTREE = "工作区"
EXCLUDE = [":(exclude)*_test.go", ":(exclude)testcase"]


def git(d, *args, check=True):
    r = subprocess.run(["git", "-C", d, *args], capture_output=True, text=True)
    if check and r.returncode:
        sys.exit(f"git {' '.join(args)} 失败（{d}）：{r.stderr.strip()}")
    return r.stdout if r.returncode == 0 else None


class Module:
    """被测服务的 go 模块目录。路径都相对它；某个 commit 或当前工作区的文件顶层声明都缓存。"""

    def __init__(self, d):
        self.dir = d
        self.prefix = git(d, "rev-parse", "--show-prefix").strip()
        self.cache = {}

    def has_commit(self, commit):
        return git(self.dir, "cat-file", "-e", commit + "^{commit}", check=False) is not None

    def text(self, rev, path):
        if rev == WORKTREE:
            try:
                with open(os.path.join(self.dir, path), encoding="utf-8") as f:
                    return f.read()
            except OSError:
                return None
        return git(self.dir, "show", f"{rev}:{self.prefix}{path}", check=False)

    def decls(self, rev, path):
        key = (rev, path)
        if key not in self.cache:
            t = self.text(rev, path)
            self.cache[key] = None if t is None else parse_decls(t)
        return self.cache[key]

    def locate(self, rev, path, line):
        """path:line 在 rev 下落在哪个声明：[(path, 声明名)]。"""
        if os.path.isabs(path):
            path = os.path.relpath(os.path.realpath(path), os.path.realpath(self.dir))
        for start, end, decl in self.decls(rev, path) or []:
            if start <= line <= end:
                return [(path, decl)]
        return []


def parse_decls(text):
    """gofmt 过的 Go 源码里的顶层声明：[(起始行, 结束行, 名字)]，行号从 1 开始。"""
    lines = text.split("\n")
    out, blocks, i = [], {}, 0
    while i < len(lines):
        line = lines[i].rstrip()
        m = DECL.match(line)
        if not m:
            i += 1
            continue
        kind = m.group(1)
        if kind == "import":
            closer, name = (")" if line.endswith("(") else None), "import"
        elif kind == "func":
            closer = None if line.endswith("}") and "{" in line else "}"
            fm = FUNC.match(line)
            name = (f"({fm.group(1)}).{fm.group(2)}" if fm.group(1) else fm.group(2)) if fm else f"func@{i + 1}"
        else:
            closer = {"{": "}", "(": ")"}.get(line[-1:])
            parts = line.split()
            if len(parts) > 1 and parts[1] != "(":
                name = f"{kind} {parts[1]}"
            else:
                blocks[kind] = blocks.get(kind, 0) + 1
                name = f"{kind} 块{blocks[kind]}"
        end = i
        if closer:
            while end + 1 < len(lines) and lines[end + 1].rstrip() != closer:
                end += 1
            end += 1
        out.append((i + 1, min(end, len(lines) - 1) + 1, name))
        i = end + 1
    return out


def touched(decls, start, count):
    """diff 一侧的 hunk 碰到的声明名。count 为 0 是在 start 行之后插入。"""
    if count:
        lo, hi = start, start + count - 1
        return {n for s, e, n in decls if s <= hi and lo <= e}
    return {n for s, e, n in decls if s <= start and start + 1 <= e}


def diff_decls(mod, base):
    """基线到当前工作区改动的 Go 顶层声明：{(路径, 声明名): 改动|新增|删除}。"""
    out = {}
    text = git(mod.dir, "diff", "--relative", "-U0", "-M", "--no-color", base, "--", "*.go", *EXCLUDE)
    old = new = None
    for line in text.splitlines():
        if line.startswith("--- "):
            old = None if line == "--- /dev/null" else line[6:]
        elif line.startswith("+++ "):
            new = None if line == "+++ /dev/null" else line[6:]
        elif (m := HUNK.match(line)):
            a, b, c, d = int(m[1]), int(m[2] or 1), int(m[3]), int(m[4] or 1)
            old_hit = touched(mod.decls(base, old) or [], a, b) if old else set()
            new_hit = touched(mod.decls(WORKTREE, new) or [], c, d) if new else set()
            base_names = {n for _, _, n in mod.decls(base, old) or []} if old else set()
            head_names = {n for _, _, n in mod.decls(WORKTREE, new) or []} if new else set()
            for n in old_hit | new_hit:
                if n == "import":
                    continue
                path = old if n in base_names else new
                state = "改动" if n in base_names and n in head_names else ("删除" if n in base_names else "新增")
                out[(path, n)] = state
    for path in git(mod.dir, "ls-files", "--others", "--exclude-standard", "--", "*.go", *EXCLUDE).split():
        for _, _, n in mod.decls(WORKTREE, path) or []:
            if n != "import":
                out[(path, n)] = "新增"
    return out


def section(lines, title, level):
    """标题行号和该节结束行号（不含）。没找到返回 (None, None)。"""
    mark = "#" * level + " "
    for i, l in enumerate(lines):
        if l.rstrip() == mark + title:
            j = i + 1
            while j < len(lines) and not any(lines[j].startswith("#" * k + " ") for k in range(1, level + 1)):
                j += 1
            return i, j
    return None, None


def refs_in(text, last_file=None):
    """一段文字里的 `文件:行`，`（:113）` 这种简写沿用前面最近的文件。返回 ([(path, line)], last_file)。"""
    out = []
    tokens = sorted([(m.start(), "full", m) for m in REF.finditer(text)]
                    + [(m.start(), "short", m) for m in REF_SHORT.finditer(text)], key=lambda t: t[0])
    for _, kind, m in tokens:
        if kind == "full":
            last_file = m.group(1)
            for n in re.split(r"\s*[、,，]\s*", m.group(2)):
                out.append((last_file, int(n)))
        elif last_file:
            out.append((last_file, int(m.group(1))))
    return out, last_file


def parse_doc(lines):
    """用例：[{nn, title, entry, body, abandoned}]；流程链路：[{name, page, nodes: [(序号, 文字)]}]。"""
    cases, cur = [], None
    for l in lines:
        if l.startswith("## "):
            cur = None
            continue
        m = CASE.match(l)
        if m:
            em = CASE_ENTRY.match(m.group(2))
            cur = {"nn": m.group(1), "title": m.group(2), "entry": em.group(1) if em else None,
                   "body": [], "abandoned": "已废弃" in m.group(2)}
            cases.append(cur)
            continue
        if l.startswith("### "):
            cur = None
        elif cur is not None:
            cur["body"].append(l)
            if l.startswith("- 已废弃"):
                cur["abandoned"] = True

    chains = []
    s, e = section(lines, "流程链路", 3)
    for l in lines[s + 1:e] if s is not None else []:
        if (m := CHAIN.match(l)):
            chains.append({"name": m.group(1), "page": m.group(2), "nodes": []})
        elif chains and (m := CHAIN_NODE.match(l)):
            chains[-1]["nodes"].append((m.group(1), m.group(2)))
    return cases, chains


def entry_key(entry):
    """`WxToken.GetAccessToken` → GetAccessToken；`HTTP handleAPI`、`定时任务 RefreshAccessToken` → 最后一段。"""
    return re.split(r"[ .]", entry.strip())[-1]


def page_refs(page_path):
    """调用树每个节点的 src，加同名骨架每个节点的 file:line。"""
    out = []

    def walk(n):
        m = re.match(r"^\s*(\S+\.go):(\d+)", n.get("src") or "")
        if m:
            out.append((m.group(1), int(m.group(2))))
        for k in n.get("kids") or []:
            walk(k)

    with open(page_path, encoding="utf-8") as f:
        page = json.load(f)
    walk(page.get("tree") or {})
    skeleton = page_path[: -len(".json")] + ".calltree.json"
    if os.path.exists(skeleton):
        with open(skeleton, encoding="utf-8") as f:
            data = json.load(f)
        stack = data if isinstance(data, list) else [data]
        while stack:
            n = stack.pop()
            if isinstance(n, dict):
                if (n.get("file") or "").endswith(".go") and n.get("line"):
                    out.append((n["file"], int(n["line"])))
                stack.extend(n.get("calls") or [])
    return page.get("meta", {}), out


def read_baseline(lines):
    s, e = section(lines, "代码基线", 3)
    if s is None:
        return None
    for l in lines[s + 1:e]:
        if (m := BASE_LINE.match(l)):
            return m.group(2), m.group(3), bool(m.group(4))
    return None


def impact(a):
    doc = os.path.abspath(a.doc)
    ws = os.path.dirname(doc)
    mod = Module(os.path.dirname(ws))
    with open(doc, encoding="utf-8") as f:
        lines = f.read().split("\n")
    cases, chains = parse_doc(lines)

    baseline = read_baseline(lines)
    if baseline is None:
        sys.exit("用例文档没有「### 代码基线」，先 stamp")
    bb, base, base_dirty = baseline
    if not mod.has_commit(base):
        sys.exit(f"基线 `{bb}` @ `{base[:7]}` 本地不存在（分支可能被 rebase 或 force push），所有用例按「调用链有改动」处理")
    branch = git(mod.dir, "rev-parse", "--abbrev-ref", "HEAD").strip()
    head = git(mod.dir, "rev-parse", "HEAD").strip()
    dirty = git(mod.dir, "status", "--porcelain", "--", ".", ":(exclude)testcase").strip()
    note = "；基线不是 HEAD 的祖先（分支被 rebase 过），按两边代码直接对比" \
        if git(mod.dir, "merge-base", "--is-ancestor", base, "HEAD", check=False) is None else ""
    count = git(mod.dir, "rev-list", "--count", f"{base}..HEAD", check=False) or "?"
    print("## 基线 → 当前代码")
    print(f"- `{bb}` @ `{base[:7]}`{'（stamp 时有未提交改动）' if base_dirty else ''} → `{branch}` @ `{head[:7]}`"
          f"{'（有未提交改动）' if dirty else ''}（{count.strip()} 个提交{note}）")

    changed = diff_decls(mod, base)
    out = git(mod.dir, "diff", "--relative", "--name-status", "-M", base, "--", ".", ":(exclude)*.go", ":(exclude)testcase")
    other = out.splitlines()
    other += [f"??\t{p}" for p in git(mod.dir, "ls-files", "--others", "--exclude-standard", "--", ".",
                                         ":(exclude)*.go", ":(exclude)testcase").split()]
    if not changed and not other:
        print("\n基线和当前代码之间没有改动：所有用例无改动")
        return

    print(f"\n## 改动声明（{len(changed)}）")
    for (path, decl), state in sorted(changed.items()):
        print(f"- {path} `{decl}` {state}")
    print(f"\n## 非 Go 文件改动（{len(other)}）")
    for l in other:
        print(f"- {l}")

    def hits(refs, rev):
        return [(p, l, k) for p, l in refs for k in mod.locate(rev, p, l) if k in changed]

    chain_changed, chain_notes = {}, []
    for c in chains:
        page = os.path.join(ws, c["page"])
        if not os.path.exists(page):
            chain_notes.append(f"- {c['name']}：调用树 {c['page']} 不存在，调用链无法判断")
            continue
        meta, refs = page_refs(page)
        pc = meta.get("commit")
        if not pc or not mod.has_commit(pc):
            pc = base
        chain_changed[c["name"]] = {k for _, _, k in hits(refs, pc)}
        last = None
        for seq, text in c["nodes"]:
            node_refs, last = refs_in(text, last)
            for path, line, key in hits(node_refs, base):
                chain_notes.append(f"- {c['name']} 节点 {seq}：{path}:{line} 落在改动声明 `{key[1]}`")
            for kw, _ in KEYWORD.findall(text):
                if git(mod.dir, "grep", "-q", "--untracked", "-F", "-e", kw, "--", "*.go", check=False) is None:
                    chain_notes.append(f"- {c['name']} 节点 {seq}：日志关键字 `{kw}` 在当前代码里搜不到")

    print("\n## 入口调用链")
    for c in chains:
        if c["name"] in chain_changed:
            got = chain_changed[c["name"]]
            print(f"- {c['name']}：" + ("、".join(f"`{k[1]}`" for k in sorted(got)) if got else "无改动"))
    print(f"\n## 流程链路节点（{len(chain_notes)}）")
    for l in chain_notes:
        print(l)

    print("\n## 用例")
    print("序号\t入口\t判定\t依据")
    for c in cases:
        if c["abandoned"]:
            continue
        body_refs, _ = refs_in("\n".join(c["body"]))
        direct = hits(body_refs, base)
        if c["entry"]:
            names = [n for n in [entry_key(c["entry"])] if n in chain_changed]
        else:
            text = c["title"] + "\n" + "\n".join(c["body"])
            names = [n for n in chain_changed if re.search(rf"(?<![A-Za-z0-9]){re.escape(n)}(?![A-Za-z0-9])", text)]
        via = [n for n in names if chain_changed[n]]
        if direct:
            verdict, why = "直接命中", "、".join(f"{p}:{l} `{k[1]}`" for p, l, k in direct)
        elif via:
            verdict, why = "调用链有改动", "见入口 " + "、".join(via)
        elif names:
            verdict, why = "无改动", ""
        else:
            verdict, why = "未关联调用链", ""
        print(f"{c['nn']}\t{c['entry'] or '/'.join(names) or '-'}\t{verdict}\t{why}")

    covered = set().union(*chain_changed.values()) if chain_changed else set()
    rest = sorted(k for k in changed if k not in covered)
    print(f"\n## 不在任何入口调用链上的改动声明（{len(rest)}）")
    for path, decl in rest:
        print(f"- {path} `{decl}` {changed[(path, decl)]}")


def stamp(a):
    doc = os.path.abspath(a.doc)
    module = os.path.dirname(os.path.dirname(doc))
    name = os.path.basename(module)
    branch = git(module, "rev-parse", "--abbrev-ref", "HEAD").strip()
    head = git(module, "rev-parse", "HEAD").strip()
    dirty = git(module, "status", "--porcelain", "--", ".", ":(exclude)testcase").strip()
    row = f"- `{name}`：`{branch}` @ `{head}`" + ("（有未提交改动）" if dirty else "")
    print(row)

    with open(doc, encoding="utf-8") as f:
        lines = f.read().split("\n")
    block = ["### 代码基线", "",
             "用例按下面的代码写成。代码更新后用 svc-gen-test-case 的 `code_impact.py impact` 对比，同步完用例再 `stamp`。",
             "", row, ""]
    s, e = section(lines, "代码基线", 3)
    if s is None:
        s, _ = section(lines, "测试前置", 2)
        if s is None:
            sys.exit(f"{doc} 没有「## 测试前置」")
        s = e = s + 1
        while e < len(lines) and not lines[e].strip():
            e += 1
        block = [""] + block
    lines[s:e] = block
    with open(doc, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("cmd", choices=["impact", "stamp"])
    p.add_argument("--doc", required=True, help="用例文档 <服务>/testcase/<服务>.md")
    a = p.parse_args()
    impact(a) if a.cmd == "impact" else stamp(a)


if __name__ == "__main__":
    main()
