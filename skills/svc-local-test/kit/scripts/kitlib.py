"""测试工作区的公共部分：读 env.yaml、连本机 MySQL 和 Redis、找进程端口和日志。标准脚本，由 svc-local-test 维护，不在工作区里改。

连接信息从环境变量取，仓库里不存：
  MYSQL_HOST(127.0.0.1) MYSQL_PORT(3306) MYSQL_USER(root) MYSQL_PWD(空)
  REDIS_ADDR(127.0.0.1:6379) REDIS_PASSWORD（不给就读 /usr/local/etc/redis.conf 的 requirepass）
库名、Redis db 写在 env.yaml。
"""
import functools
import os
import socket
import subprocess
import sys

import yaml

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # <服务>/testcase
MODULE = os.path.dirname(WS)  # 被测服务的 go 模块目录
LOCALSTART = os.path.join(WS, "localstart")
STUB_DIR = os.path.join(LOCALSTART, "rpcproxy_cache")


@functools.lru_cache(maxsize=None)
def env(ws=WS):
    path = os.path.join(ws, "env.yaml")
    if not os.path.exists(path):
        sys.exit(f"没有 {path}，先按 svc-local-env 准备环境")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def service():
    return env().get("service") or os.path.basename(MODULE)


def proc(ref):
    """进程引用 → (工作区, 进程名, 端口)。本服务的进程直接写名字，兄弟服务的写「兄弟名:进程名」。"""
    ws, name = WS, ref
    if ":" in ref:
        sib, name = ref.split(":", 1)
        s = (env().get("siblings") or {}).get(sib)
        if not s:
            sys.exit(f"env.yaml siblings 里没有 {sib}")
        ws = os.path.normpath(os.path.join(WS, s["dir"]))
    p = (env(ws).get("procs") or {}).get(name)
    if not p:
        sys.exit(f"{ws}/env.yaml procs 里没有 {name}")
    return ws, name, int(p["port"])


def proc_log(ref):
    ws, name, _ = proc(ref)
    return os.path.join(ws, "localstart", "log", name, "trpc.log")


def listening(port):
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


# ---------------------------------------------------------------- MySQL、Redis

def mysql_db():
    return (env().get("mysql") or {}).get("db", "")


def mysql_conn():
    return {"host": os.environ.get("MYSQL_HOST", "127.0.0.1"), "port": os.environ.get("MYSQL_PORT", "3306"),
            "user": os.environ.get("MYSQL_USER", "root"), "pwd": os.environ.get("MYSQL_PWD", "")}


def redis_password():
    if os.environ.get("REDIS_PASSWORD"):
        return os.environ["REDIS_PASSWORD"]
    try:
        with open("/usr/local/etc/redis.conf", encoding="utf-8") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2 and parts[0] == "requirepass":
                    return parts[1].strip('"')
    except OSError:
        pass
    return ""


def redis_conn():
    host, port = os.environ.get("REDIS_ADDR", "127.0.0.1:6379").rsplit(":", 1)
    return {"host": host, "port": port, "db": str((env().get("redis") or {}).get("db", 0)), "pwd": redis_password()}


def run_sql(query, table=False, db=None):
    c = mysql_conn()
    cmd = ["mysql", f"-h{c['host']}", f"-P{c['port']}", f"-u{c['user']}"] + (["-t"] if table else [])
    name = mysql_db() if db is None else db
    cmd += ([name] if name else []) + ["-e", query]
    p = subprocess.run(cmd, env=dict(os.environ, MYSQL_PWD=c["pwd"]), capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


def run_redis(commands):
    c = redis_conn()
    p = subprocess.run(["redis-cli", "-h", c["host"], "-p", c["port"], "-n", c["db"]],
                       input=commands.rstrip("\n") + "\n", env=dict(os.environ, REDISCLI_AUTH=c["pwd"]),
                       capture_output=True, text=True)
    out = (p.stdout + p.stderr).strip()
    bad = p.returncode != 0 or any(l.startswith(("ERR", "NOAUTH", "WRONGTYPE")) for l in out.splitlines())
    return (1 if bad else 0), out
