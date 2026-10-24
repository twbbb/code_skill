---
name: svc-local-env
description: 给能独立在本机起起来的服务准备本地测试环境：接入 rpcproxy（改业务代码，先给用户看 diff），生成 testcase/ 下的 env.yaml、本地配置模板和启动脚本，分配端口和 Redis db，建本地库，让兄弟服务也能起起来。用例文档确认后、执行用例前使用；svc-local-test 发现缺进程时也会回来调用。
---

# 准备本地测试环境

术语见 [CONTEXT.md](../../CONTEXT.md)。

- `<服务>`：被测服务的 go 模块目录。`<工作区>`：`<服务>/testcase/`。用例文档 `<工作区>/<服务目录名>.md` 由 `../svc-gen-test-case/SKILL.md` 生成并经用户确认过。
- `<kit>`：`../svc-local-test/kit/`，标准脚本。`<同步>`：`python3 ../svc-local-test/scripts/sync.py`。
- `env.yaml` 的格式见 [ENV.md](ENV.md)，端口和 Redis db 按 [PORTS.md](PORTS.md) 分。
- 参考 `common_server/wxtoken/testcase/`，看一份做完的测试工作区。

## 步骤

1. **读需要什么**：从用例文档「测试前置」读出「进程」（每个进程的用途和配置差异）、「兄弟服务」「外部下游与替身」「建表/配置要求」。读 `<服务>` 的 `main.go`、配置结构（`entity/config/`）、`app.example.yaml`、`trpc_go.yaml`，弄清配置文件从哪读（如 `CONFIG_FILE` 环境变量）、哪些配置项要按进程变、调外部下游的 client 在哪构造。
   完成：每个进程都知道要改哪几个配置项；每个外部下游都知道是 trpc client 还是 `http.Client`、在哪个文件构造。

2. **接入 rpcproxy**（已接入就跳过）：外部下游的替身靠 `github.com/twbbb/toolbox/filter/rpcproxy`，用法见它的 `README.md`。这一步改业务代码：
   - `go.mod` 加上 `github.com/twbbb/toolbox/filter/rpcproxy`。服务已经用 `replace` 指向本地 toolbox 时，照样加一行 `replace`（如 `=> ../../toolbox/filter/rpcproxy`），然后 `go mod tidy`。
   - 配置结构加 `RpcProxyArg rpcproxy.Config \`yaml:"rpcProxyArg"\``，配置加载成功后调 `rpcproxy.SetConfig(...)`；有热更新的，热更新后也调。`app.example.yaml` 不加这一项：没配就是关闭，线上不受影响。
   - 构造调外部下游的 `http.Client` 时加 `Transport: rpcproxy.Transport(nil)`（原来有自定义 Transport 的传进去）。
   - trpc 下游的 filter 不改 `trpc_go.yaml`，只在第 4 步的本地模板里加。
   - 服务的 server filter 里要有 `logContext`（`toolbox/filter/logcontext`），日志里才有调用方带来的 requestId；没有就一起加上。

   改完 `go build ./... && go vet ./...`，再把 `git -C <服务> diff` 发给用户看，说明每处改动的作用以及线上为什么不受影响（`enable` 默认关；`DOCKER_ENV` 非空时完全不注册）。用户确认后单独提交一次，提交信息写「<服务> 接入 rpcproxy，本地测试用」。用户不同意就停下，把原因报告给用户。
   完成：提交了，或用户明确不接入（这时外部下游只能真实调用，在用例文档「外部下游与替身」里写明）。

3. **复制标准脚本**：`<同步> --workspace <工作区> --apply`，把 `run`、`kit_test.go`、`scripts/`、`localstart/startserver.sh` 复制进工作区。工作区里已有同名文件且内容不同时，先看差异：是工作区里改过的，提回标准脚本或告诉用户，不直接覆盖。
   完成：`<同步> --workspace <工作区>` 输出「标准脚本一致」。

4. **写本地配置模板**：
   - `localstart/config/app.local.yaml`：从 `app.example.yaml` 拷，连接信息换成 `__MYSQL_DSN__`、`__REDIS_ADDR__`、`__REDIS_PASSWORD__`、`__REDIS_DB__`；按进程变的项换成自定义变量（如 `__REFRESH__`）；本地专用的密钥写死在这里，注释「只用于本地测试」；加上
     ```yaml
     rpcProxyArg:
       enable: true
       readOnly: true            # 只读替身，没命中的真实调用，不写缓存
       localFilePath: "__STUB_DIR__"
     ```
     外部下游的地址保持真实地址（如 `https://api.weixin.qq.com`），替身文件名按真实 host 算。
   - `localstart/config/trpc_go.local.yaml`：从 `trpc_go.yaml` 拷。`global.env_name` 改成 `lt`，锁 key、缓存 key 带环境名的不会和本机开发进程抢；service 端口换成 `__PORT__`，监听 `127.0.0.1`；日志写 `__LOG__`，`write_mode: 1` 同步写（用例跑完马上取证，异步会漏最后几行），`level: debug`；`server.filter` 有 `logContext`；`client.filter` 最后一个加 `rpcProxy`。兄弟服务的 client 配置按兄弟服务 `env.yaml` 的端口写成 `ip://127.0.0.1:<端口>`。
   完成：两份模板里的连接信息、端口、日志路径都是变量，没有真实密码。

5. **写 `env.yaml`**：按 [ENV.md](ENV.md)。端口和 Redis db 按 [PORTS.md](PORTS.md) 分；表里还没有这个服务就先加一行。进程名用服务名缩写加序号（`wx1`、`wxt1`），和用例文档「进程」一致；用例文档里还没写进程名的，回写进去。`secretFiles` 写 `localstart/config/app.local.yaml`。
   再写 `<工作区>/.gitignore`：
   ```
   localstart/bin/
   localstart/log/
   localstart/rpcproxy_cache/
   scripts/__pycache__/
   analysis/**/*.calltree.json
   ```
   完成：`env.yaml` 的每个进程都有端口，`default` 里的进程都在 `procs` 里。

6. **兄弟服务**：`env.yaml` 的 `siblings` 里每个兄弟服务，它的测试工作区里要有 `env.yaml` 和 `localstart/`。没有的，对它从第 3 步做起（它自己的外部下游也按第 2 步接入），只配被测服务要用的那个进程。
   完成：每个兄弟服务的 `localstart/startserver.sh status` 能列出 `siblings` 里写的进程。

7. **起来验证**：在 `<工作区>` 执行 `localstart/startserver.sh start`（缺表时会执行 `mysql.init`，也会起兄弟服务），再 `./run env`。没起来的看 `localstart/log/<进程>/stdout.log`；连不上 MySQL、Redis 的，告诉用户要设哪些环境变量（见 `scripts/kitlib.py` 开头）。
   - 对每个进程 `grep "rpcproxy" localstart/log/<进程>/trpc.log`：有外部下游调用时，日志里能看到 `rpcproxy cache|` 开头的行。
   - 用例文档里要用的进程都起一遍，定时任务那种只在用例期间起的，起来看过后再停掉。
   完成：`./run env` 全部 ✅。

## 完成

工作区有标准脚本、`env.yaml`、两份配置模板、`.gitignore`；被测服务接入了 rpcproxy（或用户明确不接）；`./run env` 全部 ✅。汇报：分到的端口和 Redis db、改了哪些业务代码以及提交的 commit、兄弟服务的准备情况、用户需要设的环境变量。进程留着给 `../svc-local-test/SKILL.md` 用，不接着执行时 `localstart/startserver.sh stop --siblings` 停掉。
