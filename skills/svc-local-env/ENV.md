# env.yaml

测试工作区的本地环境配置，在 `<服务>/testcase/env.yaml`，由 svc-local-env 写。标准脚本（`scripts/localstart.py`、`run_case.py`、`evidence.py`）和 `kit_test.go` 都从这里读，一个服务和别的服务不同的地方都写在这里，标准脚本里不写死。提交。

```yaml
# 本地测试环境，svc-local-env 生成。startserver.sh、scripts/、kit_test.go 都从这里读。
service: wxtoken                    # 被测服务目录名，requestId 前缀和汇总里用

build:                              # localstart/bin/ 下编译出的二进制，cwd 是 <服务>；第一个是被测服务本身
  - {bin: wxtoken, pkg: .}
  - {bin: encsecret, pkg: ./cmd/encsecret}

cmd: "__BIN__/wxtoken -conf __DIR__/trpc_go.yaml"   # 启动命令，cwd 是 localstart/log/<进程>/
envs:                               # 启动时的环境变量
  CONFIG_FILE: "__DIR__/app.yaml"
templates:                          # 每个进程渲染一份：输出文件名 → 模板（相对 testcase/）
  app.yaml: localstart/config/app.local.yaml
  trpc_go.yaml: localstart/config/trpc_go.local.yaml

vars:                               # 所有进程共用的模板变量
  REFRESH: 3600
procs:                              # 本服务的进程，端口按 PORTS.md 分
  wx1:
    port: 18301
    service: trpc.common.wxtoken.WxToken
    note: RPC 用例
  wxt1:
    port: 18302
    service: trpc.common.wxtoken.WxToken
    note: 定时任务用例，用例期间起
    vars: {REFRESH: 2}              # 覆盖顶层 vars
default: [wx1]                      # startserver.sh start 不带参数时起哪些

siblings:                           # 兄弟服务：用它自己 testcase 的 startserver.sh 起
  auth: {dir: ../../auth/testcase, procs: [au1]}

mysql:
  db: db_wxtoken                    # 数据脚本、SQL 核对用的库；模板变量 MYSQL_DSN 也连它
  check: db_wxtoken.t_wx_app        # 这张表查不到就执行 init
  init: ../../sql/20261024_01_init.sql
redis:
  db: 14                            # 按 PORTS.md 分

secretFiles:                        # 里面键名像密钥（secret、password、key、token）的值不能出现在证据里
  - localstart/config/app.local.yaml
```

## 模板变量

模板里写 `__名字__`，起进程时替换。内置的有：

| 变量 | 值 |
|---|---|
| `PORT` | 进程的端口 |
| `LOG` | `localstart/log/<进程>/trpc.log` 的绝对路径，trpc 日志写这里 |
| `DIR` | `localstart/log/<进程>/` 的绝对路径，进程的工作目录 |
| `BIN` | `localstart/bin/` 的绝对路径，只在 `cmd` 里能用 |
| `WS`、`MODULE` | 测试工作区、被测服务目录的绝对路径 |
| `STUB_DIR` | `localstart/rpcproxy_cache/` 的绝对路径，填 `rpcProxyArg.localFilePath` |
| `MYSQL_DSN`、`MYSQL_DB` | 按环境变量 `MYSQL_*` 和 `mysql.db` 拼的 DSN |
| `REDIS_ADDR`、`REDIS_PASSWORD`、`REDIS_DB` | 按环境变量 `REDIS_*` 和 `redis.db` |

再加上顶层 `vars` 和进程自己的 `vars`。模板里出现没有定义的变量，起进程时报错。

## 进程引用

`cases.yaml` 的 `proc`、test 代码的 `ClientOpts`、`Port`、`LogPath` 里，本服务的进程直接写名字（`wx1`），兄弟服务的写 `兄弟名:进程名`（`auth:au1`），端口和日志从兄弟服务自己的 `env.yaml` 找。
