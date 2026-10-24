#!/usr/bin/env python3
"""按 env.yaml 编译、起停本服务的本地进程。标准脚本，由 svc-local-test 维护，不在工作区里改。
localstart/startserver.sh 只是转调这里。

  startserver.sh build                编译 env.yaml build 里的每个二进制到 localstart/bin/
  startserver.sh start [进程 ...]     默认起 env.yaml default；缺表时先执行 mysql.init；也按 siblings 起兄弟服务
  startserver.sh stop [进程 ...]      默认全停（不停兄弟服务；加 --siblings 一起停）
  startserver.sh restart [进程 ...]   停、重新编译、再起
  startserver.sh status

每个进程的工作目录是 localstart/log/<进程>/：env.yaml templates 里的每个模板替换 __变量__ 后写到这里（权限 600），
日志是这里的 trpc.log。变量有 PORT、LOG、DIR、WS、MODULE、STUB_DIR、MYSQL_DSN、MYSQL_DB、REDIS_ADDR、REDIS_PASSWORD、
REDIS_DB，加上进程自己的 vars（覆盖 env.yaml 顶层 vars）。
"""
import os
import re
import signal
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kitlib as kl  # noqa: E402

BIN = os.path.join(kl.LOCALSTART, "bin")
LOGS = os.path.join(kl.LOCALSTART, "log")


def procs():
    return kl.env().get("procs") or {}


def build():
    os.makedirs(BIN, exist_ok=True)
    for b in kl.env().get("build") or [{"bin": kl.service(), "pkg": "."}]:
        out = os.path.join(BIN, b["bin"])
        print(f"go build -o {os.path.relpath(out, kl.WS)} {b['pkg']}")
        if subprocess.run(["go", "build", "-o", out, b["pkg"]], cwd=kl.MODULE).returncode != 0:
            sys.exit(f"编译 {b['pkg']} 失败")


def variables(name):
    e = kl.env()
    m, r = kl.mysql_conn(), kl.redis_conn()
    d = os.path.join(LOGS, name)
    v = {"PORT": str(procs()[name]["port"]), "LOG": os.path.join(d, "trpc.log"), "DIR": d, "WS": kl.WS,
         "MODULE": kl.MODULE, "STUB_DIR": kl.STUB_DIR, "MYSQL_DB": kl.mysql_db(),
         "MYSQL_DSN": f"{m['user']}:{m['pwd']}@tcp({m['host']}:{m['port']})/{kl.mysql_db()}"
                      "?charset=utf8mb4&parseTime=True&loc=Local",
         "REDIS_ADDR": f"{r['host']}:{r['port']}", "REDIS_PASSWORD": r["pwd"], "REDIS_DB": r["db"]}
    v.update({k: str(x) for k, x in (e.get("vars") or {}).items()})
    v.update({k: str(x) for k, x in (procs()[name].get("vars") or {}).items()})
    return v


def fill(text, v):
    def one(m):
        if m.group(1) not in v:
            sys.exit(f"模板里的 __{m.group(1)}__ 没有对应变量")
        return v[m.group(1)]
    return re.sub(r"__([A-Z][A-Z0-9_]*)__", one, text)


def ensure_db():
    my = kl.env().get("mysql") or {}
    if not my.get("check"):
        return
    code, _ = kl.run_sql(f"SELECT 1 FROM {my['check']} LIMIT 1", db="")
    if code == 0:
        return
    init = os.path.normpath(os.path.join(kl.WS, my["init"]))
    print(f"建库建表：{init}")
    c = kl.mysql_conn()
    with open(init, encoding="utf-8") as f:
        p = subprocess.run(["mysql", f"-h{c['host']}", f"-P{c['port']}", f"-u{c['user']}"], stdin=f,
                           env=dict(os.environ, MYSQL_PWD=c["pwd"]))
    if p.returncode != 0:
        sys.exit(f"执行 {init} 失败")


def pid_of(name):
    try:
        pid = int(open(os.path.join(LOGS, name, "pid")).read().strip())
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError):
        return None


def start_one(name):
    if name not in procs():
        sys.exit(f"env.yaml procs 里没有 {name}")
    port = int(procs()[name]["port"])
    d = os.path.join(LOGS, name)
    os.makedirs(d, exist_ok=True)
    if kl.listening(port):
        print(f"{name} 已在 {port} 监听")
        return
    v = variables(name)
    old = os.umask(0o077)
    try:
        for out, tpl in (kl.env().get("templates") or {}).items():
            with open(os.path.join(kl.WS, tpl), encoding="utf-8") as f:
                text = fill(f.read(), v)
            with open(os.path.join(d, out), "w", encoding="utf-8") as f:
                f.write(text)
    finally:
        os.umask(old)
    v["BIN"] = BIN
    cmd = fill(kl.env()["cmd"], v)
    envs = {k: fill(str(x), v) for k, x in (kl.env().get("envs") or {}).items()}
    with open(os.path.join(d, "stdout.log"), "ab") as out:
        p = subprocess.Popen(["bash", "-c", "exec " + cmd], cwd=d, env=dict(os.environ, **envs),
                             stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    with open(os.path.join(d, "pid"), "w") as f:
        f.write(f"{p.pid}\n")
    for _ in range(100):
        if kl.listening(port):
            print(f"{name} 已启动，端口 {port}，pid {p.pid}")
            return
        if p.poll() is not None:
            break
        time.sleep(0.2)
    tail = open(os.path.join(d, "stdout.log"), encoding="utf-8", errors="replace").read().splitlines()[-20:]
    sys.exit(f"{name} 没起来，{os.path.relpath(d, kl.WS)}/stdout.log 末尾：\n" + "\n".join(tail))


def stop_one(name):
    pid = pid_of(name)
    if pid:
        os.kill(pid, signal.SIGTERM)
        for _ in range(100):
            if not pid_of(name):
                break
            time.sleep(0.1)
        else:
            os.kill(pid, signal.SIGKILL)
        print(f"{name} 已停")
    try:
        os.remove(os.path.join(LOGS, name, "pid"))
    except OSError:
        pass


def siblings(cmd):
    for sib, s in (kl.env().get("siblings") or {}).items():
        script = os.path.normpath(os.path.join(kl.WS, s["dir"], "localstart", "startserver.sh"))
        if not os.path.exists(script):
            sys.exit(f"兄弟服务 {sib} 没有 {script}，先对它执行 svc-local-env")
        print(f"--- 兄弟服务 {sib}：{cmd} {' '.join(s.get('procs') or [])}")
        if subprocess.run([script, cmd] + list(s.get("procs") or [])).returncode != 0:
            sys.exit(f"兄弟服务 {sib} {cmd} 失败")


def status():
    for name, p in procs().items():
        port = int(p["port"])
        state = f"运行中，pid {pid_of(name) or '?'}" if kl.listening(port) else "stopped"
        print(f"{name}\t端口 {port}\t{state}\t{p.get('note', '')}")


def main(argv):
    cmd = argv[0] if argv else "status"
    with_sib = "--siblings" in argv
    names = [a for a in argv[1:] if a != "--siblings"]
    if cmd == "build":
        build()
    elif cmd == "start":
        if not os.path.exists(os.path.join(BIN, (kl.env().get("build") or [{"bin": kl.service()}])[0]["bin"])):
            build()
        ensure_db()
        os.makedirs(kl.STUB_DIR, exist_ok=True)
        siblings("start")
        for n in names or kl.env().get("default") or list(procs()):
            start_one(n)
    elif cmd == "stop":
        for n in names or list(procs()):
            stop_one(n)
        if with_sib:
            siblings("stop")
    elif cmd == "restart":
        targets = names or [n for n in procs() if pid_of(n)] or kl.env().get("default") or list(procs())
        for n in targets:
            stop_one(n)
        build()
        main(["start"] + targets)
    elif cmd == "status":
        status()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
