#!/usr/bin/env python3
"""按 cases.yaml 执行用例并取证。标准脚本，由 svc-local-test 维护，不在工作区里改。

每条用例：init → 清替身目录 → 数据 → before → 前置核对 → go test → 原始输出 → 流程链路（含替身命中）
→ rpcproxy 日志 → 全量日志 → after → 清替身目录。判定不在这里做，看证据文件后用 evidence.py judge 填。

占位符（cases.yaml、data/ 里都能用）：
  ${A}            accounts 里的标识
  ${now:+300}     当前 unix 秒 +300；${ms:-60} 当前 unix 毫秒 -60 秒
  ${名字:参数}    cases.yaml render 里定义的命令，{arg} 换成参数、{acc} 换成参数对应的标识，取标准输出

用法：
  run_case.py [--round <轮>] [--force] NN [NN ...] | all
  run_case.py --list
  run_case.py --env      环境自检：本服务和兄弟服务的进程在监听，MySQL、Redis 连得上
"""
import argparse
import datetime
import os
import re
import shutil
import subprocess
import sys
import time

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import evidence as ev  # noqa: E402
import kitlib as kl  # noqa: E402

PLACEHOLDER = re.compile(r"\$\{(\w+)(?::([^}]*))?\}")


class Render:
    def __init__(self, cfg):
        self.accounts = {k: str(v) for k, v in (cfg.get("accounts") or {}).items()}
        self.commands = cfg.get("render") or {}
        self.cache = {}

    def run(self, name, arg):
        key = (name, arg)
        if key not in self.cache:
            cmd = self.commands[name].replace("{arg}", arg).replace("{acc}", self.accounts.get(arg, arg))
            p = subprocess.run(["bash", "-c", cmd], cwd=kl.WS, capture_output=True, text=True)
            if p.returncode != 0:
                sys.exit(f"占位符 ${{{name}:{arg}}} 的命令失败：{p.stderr.strip()}")
            self.cache[key] = p.stdout.strip()
        return self.cache[key]

    def _one(self, m):
        key, arg = m.group(1), m.group(2)
        if key == "now":
            return str(int(time.time()) + int(arg or 0))
        if key == "ms":
            return str((int(time.time()) + int(arg or 0)) * 1000)
        if key in self.commands:
            return self.run(key, arg or "")
        if arg is None and key in self.accounts:
            return self.accounts[key]
        sys.exit(f"未知占位符 {m.group(0)}")

    def __call__(self, value):
        if isinstance(value, str):
            return PLACEHOLDER.sub(self._one, value)
        if isinstance(value, list):
            return [self(v) for v in value]
        if isinstance(value, dict):
            return {k: self(v) for k, v in value.items()}
        return value


def now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:23]


def shell(cmds, render, what):
    """before/after：在工作区用 bash 依次执行，失败即停。before 在数据之后执行。"""
    for c in cmds or []:
        c = render(c)
        print(f"$ {c}")
        if subprocess.run(["bash", "-c", c], cwd=kl.WS).returncode != 0:
            sys.exit(f"{what} 失败：{c}")


def clean_stubs():
    """替身目录只放本条用例写的替身，开始和结束都清空。"""
    shutil.rmtree(kl.STUB_DIR, ignore_errors=True)
    os.makedirs(kl.STUB_DIR)


def run_data(nn, render):
    """data/NN.sql 进 env.yaml 的库，data/NN.redis 进 env.yaml 的 Redis db。"""
    found = False
    for ext in ("sql", "redis"):
        path = os.path.join(kl.WS, "data", f"{nn}.{ext}")
        if not os.path.exists(path):
            continue
        found = True
        text = render(open(path, encoding="utf-8").read())
        print(f"数据 {os.path.basename(path)}")
        if ext == "sql":
            code, out = kl.run_sql(text)
        else:
            code, out = kl.run_redis("\n".join(l for l in text.splitlines()
                                               if l.strip() and not l.lstrip().startswith("#")))
        if out:
            print(out)
        if code != 0:
            sys.exit(f"数据脚本 {path} 失败")
    if not found:
        sys.exit(f"用例 {nn} 没有 data/{nn}.*，不需要数据的用例在 cases.yaml 写 data: false")


def checks(path, items, section, named, render):
    for it in items or []:
        note = render(it.get("note", ""))
        if "redis" in it:
            ev.check_redis(path, section, note, render(it["redis"]))
        else:
            q = it["sql"]
            ev.check_sql(path, section, note, render(named.get(q, q)))


def expand(items, flows):
    nodes = []
    for item in items or []:
        if item in flows:
            nodes += flows[item]
        elif "=" in item:
            nodes.append(item)
        else:
            sys.exit(f"flow 里的 {item!r} 既不是公共流程名，也不是「名=关键字」")
    return nodes


def run_one(a, cfg, nn, render):
    case = cfg["cases"].get(nn)
    if case is None:
        sys.exit(f"cases.yaml 里没有用例 {nn}")
    procs = case["proc"] if isinstance(case["proc"], list) else [case["proc"]]
    named = cfg.get("sql") or {}
    flows = cfg.get("flows") or {}
    print(f"\n===== 用例 {nn}：{case['title']} =====")

    path = ev.init(a.round, nn, case["method"], case["title"], a.force)
    start = now()
    ok = False
    clean_stubs()
    try:
        if case.get("data", True):
            run_data(nn, render)
        shell(case.get("before"), render, f"用例 {nn} before")
        checks(path, case.get("pre"), "前置核对", named, render)
        test = subprocess.run(["go", "test", ".", "-run", f"^Test_{nn}_", "-v", "-count=1"], cwd=kl.WS,
                              env=dict(os.environ, ROUND=a.round), capture_output=True, text=True)
        out = test.stdout + test.stderr
        print(out)
        end = now()
        ev.append(path, "原始输出", f"**go test**（退出码 {test.returncode}）\n\n{ev.block('text', out)}")
        checks(path, case.get("post"), "原始输出", named, render)

        stubs = sorted(os.listdir(kl.STUB_DIR))
        also = case.get("also")
        lines = ev.case_lines(procs, ev.request_ids(path), also, start, end)
        source = "、".join(os.path.relpath(kl.proc_log(p), kl.WS) for p in procs)
        if also:
            source += f"（含时段内匹配 `{also}` 的行）"
        nodes = render(expand(case.get("flow"), flows)) + [f"替身命中 {s}=rpcproxy cache|hit| && {s}" for s in stubs]
        if nodes:
            ev.flow(path, "日志", source, lines, nodes)
        ev.rpcproxy_lines(path, lines)
        ev.fulllog(path, source, lines)
        ok = test.returncode == 0
    finally:
        shell(case.get("after"), render, f"用例 {nn} after")
        clean_stubs()
    print(f"--- 用例 {nn}：{'go test 通过' if ok else 'go test 失败'}；证据 {path}")
    return ok


def check_env():
    """default 里的进程和兄弟服务要在监听；其他进程（如定时任务实例）由用例自己起停，只列出来。"""
    bad = []
    procs = kl.env().get("procs") or {}
    must = set(kl.env().get("default") or procs)
    refs = list(procs)
    for sib, s in (kl.env().get("siblings") or {}).items():
        sib_refs = [f"{sib}:{p}" for p in s.get("procs") or []]
        refs += sib_refs
        must |= set(sib_refs)
    for ref in refs:
        _, _, port = kl.proc(ref)
        up = kl.listening(port)
        print(f"{'✅' if up else ('❌' if ref in must else '—')} {ref} 端口 {port}"
              + ("" if up else "（没在监听）" if ref in must else "（用例自己起停）"))
        if not up and ref in must:
            bad.append(ref)
    code, out = kl.run_sql("SELECT 1")
    print(f"{'✅' if code == 0 else '❌'} MySQL 库 {kl.mysql_db()}" + ("" if code == 0 else f"：{out}"))
    rcode, rout = kl.run_redis("PING")
    print(f"{'✅' if rcode == 0 else '❌'} Redis db {kl.redis_conn()['db']}" + ("" if rcode == 0 else f"：{rout}"))
    if bad or code or rcode:
        sys.exit("环境没准备好" + (f"：{'、'.join(bad)} 没在监听，先 localstart/startserver.sh start" if bad else ""))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--round", default="", help="轮次，默认当前时间")
    p.add_argument("--force", action="store_true", help="同一轮重跑已有证据文件的用例")
    p.add_argument("--list", action="store_true")
    p.add_argument("--env", action="store_true")
    p.add_argument("nn", nargs="*")
    a = p.parse_args()

    with open(os.path.join(kl.WS, "cases.yaml"), encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if a.list:
        for nn, c in cfg["cases"].items():
            print(f"{nn}\t{c['proc']}\t{c['method']}\t{c['title']}")
        return
    if a.env:
        check_env()
        return
    if not a.nn:
        sys.exit("给出要执行的用例序号（all 表示全部），或用 --list 查看")
    if a.nn == ["all"]:
        a.nn = [nn for nn, c in cfg["cases"].items() if not c.get("abandoned")]
    if not a.round:
        a.round = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    print(f"轮次 {a.round}（续跑同一轮：--round {a.round}）")
    render = Render(cfg)
    bad = [nn for nn in a.nn if not run_one(a, cfg, nn, render)]
    print(f"\n轮次 {a.round}：执行 {len(a.nn)} 条" + (f"，go test 没通过：{' '.join(bad)}" if bad else ""))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
