#!/usr/bin/env python3
"""证据文件 result/<轮>/NN_<Method>.md 的读写。标准脚本，由 svc-local-test 维护，不在工作区里改。

run_case.py 调这里的函数写前置核对、原始输出、流程链路和全量日志；判定和汇总由 agent 跑：
  evidence.py brief   --round <轮> --nn NN
  evidence.py judge   --round <轮> --nn NN --verdict 通过|失败|阻塞 --nodes ✅,❌,无日志 \
                      --row '检查项 ;; 预期 ;; 实际 ;; 结论 ;; 原始输出' --note '说明'
  evidence.py summary --round <轮>
"""
import argparse
import datetime
import glob
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kitlib as kl  # noqa: E402

MAX_LINE = 2000
SECRET_KEY = re.compile(r"(secret|password|passwd|pwd|key|token)", re.I)
TEMPLATE = """# 用例{nn} `{method}`：{title}

- 轮次：{round}
- requestId：{request_id}
- 执行时间：{time}
- 判定：待填

## 前置核对

## 请求

## 响应

## 替身

## 流程链路

## 核对表

| 检查项 | 预期 | 实际 | 结论 | 原始输出 |
|---|---|---|---|---|

## 原始输出

## 说明

"""


def round_dir(rnd):
    return os.path.join(kl.WS, "result", rnd)


def evidence_file(rnd, nn):
    files = glob.glob(os.path.join(round_dir(rnd), f"{nn}_*.md"))
    if len(files) != 1:
        sys.exit(f"{round_dir(rnd)} 下 {nn}_*.md 有 {len(files)} 个，先用 run_case.py 执行")
    return files[0]


def request_ids(path):
    """头部的 requestId，加 test 代码记下的「关联 requestId」（如网关自己生成的）。"""
    text = open(path, encoding="utf-8").read()
    ids = re.findall(r"^- (?:关联 )?requestId：(\S+)$", text, re.M)
    if not ids:
        sys.exit(f"{path} 头部没有 requestId")
    return ids


def append(path, section, text):
    """把 text 追加到 section 分段末尾（下一个 ## 之前）。kit_test.go 的 append 与这里一致。"""
    content = open(path, encoding="utf-8").read()
    head = f"\n## {section}\n"
    start = content.find(head)
    if start < 0:
        sys.exit(f"{path} 没有「{section}」分段")
    nxt = content.find("\n## ", start + len(head))
    end = len(content) if nxt < 0 else nxt + 1
    body = content[start + len(head):end].rstrip("\n")
    body = (body + "\n\n" if body.strip() else "\n") + text.rstrip("\n") + "\n\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(content[:start + len(head)] + body + content[end:])


def block(lang, text):
    return f"```{lang}\n{text.rstrip()}\n```"


def truncate(line):
    return line if len(line) <= MAX_LINE else f"{line[:MAX_LINE]}…(截断，原长 {len(line)})"


def init(rnd, nn, method, title, force):
    os.makedirs(round_dir(rnd), exist_ok=True)
    existing = glob.glob(os.path.join(round_dir(rnd), f"{nn}_*"))
    if existing and not force:
        sys.exit(f"本轮已有 {nn} 的证据文件，同一轮重跑加 --force")
    for f in existing:
        os.remove(f)
    now = datetime.datetime.now()
    rid = f"{kl.service()}-lt-{nn}-{now:%H%M%S}"
    path = os.path.join(round_dir(rnd), f"{nn}_{method}.md")
    with open(path, "w", encoding="utf-8") as f:
        # 精确到毫秒：test 代码按它数日志，按秒会把上一条用例同一秒的行也算进来
        f.write(TEMPLATE.format(nn=nn, method=method, title=title, round=rnd, request_id=rid,
                                time=now.strftime("%Y-%m-%d %H:%M:%S.%f")[:23]))
    print(f"{path}\nrequestId={rid}")
    return path


# ---------------------------------------------------------------- 核对

def check_sql(path, section, note, query):
    _, out = kl.run_sql(query, table=True)
    title = f"**SQL**（库 {kl.mysql_db()}）" + (f"：{note}" if note else "")
    append(path, section, f"{title}\n\n{block('sql', query)}\n\n{block('text', out or '（空结果）')}")
    print(out or "（空结果）")


def check_redis(path, section, note, command):
    _, out = kl.run_redis(command)
    title = "**Redis**" + (f"：{note}" if note else "")
    append(path, section, f"{title}\n\n{block('text', '> ' + command)}\n\n{block('text', out or '（空）')}")
    print(out or "（空）")


# ---------------------------------------------------------------- 日志

def read_lines(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", errors="replace") as f:
        return [l.rstrip("\n") for l in f]


def in_window(line, start, end):
    return start <= line[:23] <= end


def case_lines(procs, rids, also, start, end):
    """各进程日志里带本条 requestId 的行；also 是正则，时间窗口内匹配它的行也算（定时任务的 requestId 每轮都变）。"""
    out = []
    for p in procs:
        for l in read_lines(kl.proc_log(p)):
            if not in_window(l, start, end):
                continue
            if any(r in l for r in rids) or (also and re.search(also, l)):
                out.append(f"[{p}] {l}" if len(procs) > 1 else l)
    return out


def flow(path, title, source, lines, nodes):
    parts = [f"{title}：`{source}`，本条 {len(lines)} 行"]
    for node in nodes:
        name, _, kw = node.partition("=")
        absent = kw.startswith("!")
        kw = kw[1:] if absent else kw
        parts_kw = kw.split(" && ")  # 用 && 连起来的几段都要出现在同一行
        hits = [l for l in lines if all(p in l for p in parts_kw)]
        parts.append(f"### {name}｜{'预期不出现' if absent else '预期出现'}｜结论：待填\n\n关键字：`{kw}`，命中 {len(hits)} 行")
        if hits:
            more = f"\n\n另有 {len(hits) - 5} 行，见 `.log`" if len(hits) > 5 else ""
            parts.append(block("text", "\n".join(truncate(l) for l in hits[:5])) + more)
    append(path, "流程链路", "\n\n".join(parts))


def rpcproxy_lines(path, lines):
    """本条日志里 rpcproxy 的每一行：替身命中、没命中走了真实调用。"""
    got = [truncate(l) for l in lines if "rpcproxy cache|" in l]
    append(path, "原始输出", "**rpcproxy 日志**（本条）\n\n" + block("text", "\n".join(got) or "（没有）"))


def fulllog(path, title, lines):
    with open(path[:-3] + ".log", "a", encoding="utf-8") as f:
        f.write(f"# {title}（{len(lines)} 行）\n")
        f.writelines(truncate(l) + "\n" for l in lines)


# ---------------------------------------------------------------- 判定、汇总

def cmd_brief(a):
    path = evidence_file(a.round, a.nn)
    s = open(path, encoding="utf-8").read()
    for m in re.finditer(r"^### (.+?)｜(预期出现|预期不出现)｜结论：(.+)\n\n关键字：`(.*)`，命中 (\d+) 行", s, re.M):
        name, want, verdict, kw, n = m.groups()
        ok = (int(n) > 0) == (want == "预期出现")
        print(f"{'✅' if ok else '❌'} {name}｜{want}｜命中 {n}｜{kw}｜当前结论 {verdict}")
    m = re.search(r"\*\*go test\*\*（退出码 (\d+)）", s)
    print(f"go test 退出码：{m.group(1) if m else '没有'}")
    print(f"证据文件：{path}")


def cmd_judge(a):
    path = evidence_file(a.round, a.nn)
    s = open(path, encoding="utf-8").read()
    s = s.replace("- 判定：待填", f"- 判定：{a.verdict}", 1)
    nodes = [x.strip() for x in a.nodes.split(",") if x.strip()]
    if s.count("结论：待填") != len(nodes):
        sys.exit(f"流程链路有 {s.count('结论：待填')} 个待填节点，--nodes 给了 {len(nodes)} 个")
    for n in nodes:
        s = s.replace("结论：待填", f"结论：{n}", 1)
    header = "| 检查项 | 预期 | 实际 | 结论 | 原始输出 |\n|---|---|---|---|---|\n"
    rows = []
    for r in a.row:
        cells = [c.strip().replace("|", "\\|") for c in r.split(";;")]
        if len(cells) != 5:
            sys.exit(f"核对表行要 5 列（;; 分隔）：{r}")
        rows.append("| " + " | ".join(cells) + " |\n")
    s = s.replace(header, header + "".join(rows), 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(s)
    for n in a.note:
        append(path, "说明", f"- {n}")
    left = open(path, encoding="utf-8").read().count("待填")
    print(f"已填 {path}" + (f"，仍有 {left} 处待填" if left else ""))


def git(*args):
    p = subprocess.run(["git", "-C", kl.MODULE] + list(args), capture_output=True, text=True)
    return p.stdout.strip() if p.returncode == 0 else ""


def secrets():
    """不能出现在证据里的值：env.yaml secretFiles 里键名像密钥的值，加上连接用的密码。"""
    out = {kl.mysql_conn()["pwd"], kl.redis_password()}

    def walk(v, key=""):
        if isinstance(v, dict):
            for k, x in v.items():
                walk(x, f"{key}.{k}")  # 带上上层键名：secretKeys: {1: "..."} 的值也算
        elif isinstance(v, list):
            for x in v:
                walk(x, key)
        elif isinstance(v, (str, int)) and SECRET_KEY.search(key):
            out.add(str(v))

    import yaml
    for f in kl.env().get("secretFiles") or []:
        p = os.path.join(kl.WS, f)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                walk(yaml.safe_load(fh) or {})
    return {s for s in out if len(s) >= 8 and not s.startswith("__")}


def cmd_summary(a):
    d = round_dir(a.round)
    rows, counts, leaks = [], {}, []
    values = secrets()
    for path in sorted(glob.glob(os.path.join(d, "*.md")) + glob.glob(os.path.join(d, "*.log"))):
        name = os.path.basename(path)
        content = open(path, encoding="utf-8", errors="replace").read()
        leaks += [name for v in values if v in content]
        if not name.endswith(".md") or name == "summary.md":
            continue
        title = content.splitlines()[0].lstrip("# ")
        m = re.search(r"^- 判定：(.+)$", content, re.M)
        verdict = m.group(1).strip() if m else "待填"
        counts[verdict] = counts.get(verdict, 0) + 1
        rows.append(f"| {title} | {verdict} | [{name}]({name}) |")
    stat = "，".join(f"{k} {v}" for k, v in counts.items())
    head = git("rev-parse", "--short", "HEAD") or "未提交"
    dirty = "（有未提交改动）" if git("status", "--porcelain", "--", ".", ":(exclude)testcase") else ""
    with open(os.path.join(d, "summary.md"), "w", encoding="utf-8") as f:
        f.write(f"# 本轮汇总 {a.round}\n\n- 生成时间：{datetime.datetime.now():%Y-%m-%d %H:%M:%S}\n"
                f"- 被测代码：`{kl.service()}` @ `{head}`{dirty}\n- 用例数：{len(rows)}（{stat}）\n\n"
                "## 用例\n\n| 用例 | 判定 | 证据 |\n|---|---|---|\n" + "\n".join(rows) + "\n")
    if leaks:
        sys.exit(f"证据里出现了密钥或密码原文：{'、'.join(sorted(set(leaks)))}，改掉再汇总")
    if "待填" in counts:
        sys.exit(f"有 {counts['待填']} 份证据文件判定还是「待填」")
    print(f"{d}/summary.md：{stat}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("brief")
    s.add_argument("--round", required=True)
    s.add_argument("--nn", required=True)
    s = sub.add_parser("judge")
    s.add_argument("--round", required=True)
    s.add_argument("--nn", required=True)
    s.add_argument("--verdict", required=True, choices=["通过", "失败", "阻塞"])
    s.add_argument("--nodes", default="", help="流程节点结论，按顺序逗号分隔：✅,❌,无日志")
    s.add_argument("--row", action="append", default=[], help="核对表一行：检查项 ;; 预期 ;; 实际 ;; 结论 ;; 原始输出")
    s.add_argument("--note", action="append", default=[], help="说明里的一条")
    s = sub.add_parser("summary")
    s.add_argument("--round", required=True)
    a = p.parse_args()
    globals()["cmd_" + a.cmd](a)


if __name__ == "__main__":
    main()
