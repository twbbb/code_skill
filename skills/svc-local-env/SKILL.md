---
name: svc-local-env
description: 给被测服务准备本地测试环境：接入 rpcproxy、生成 env.yaml 和启动脚本、建本地库、备好兄弟服务。通常由 svc-local-test-flow 带着走。
disable-model-invocation: true
---

# 准备本地测试环境

先读 [约定](../svc-local-test-flow/CONVENTIONS.md)。`env.yaml` 格式见 [ENV.md](ENV.md)，端口和 Redis db 按 [PORTS.md](PORTS.md) 分。`<同步>` 指 `python3 ../svc-local-test/scripts/sync.py`。

输入：`<服务>`，以及经用户确认过的 `<用例文档>`。

## 步骤

1. **读需要什么**：从用例文档「测试前置」读出进程（用途、配置差异）、兄弟服务、外部下游、建表/配置要求。读 `<服务>` 的 `main.go`、配置结构（`entity/config/`）、`app.example.yaml`、`trpc_go.yaml`。
   完成：知道配置文件从哪读（如 `CONFIG_FILE` 环境变量）；每个进程要改哪几个配置项；每个外部下游是 trpc client 还是 `http.Client`、在哪个文件构造。

2. **接入 rpcproxy**（已接入就跳过）：替身靠 `github.com/twbbb/toolbox/filter/rpcproxy`。这一步改业务代码：
   - `go.mod` 加 `github.com/twbbb/toolbox/filter/rpcproxy`；服务已用 `replace` 指向本地 toolbox 时照样加一行 `replace`（如 `=> ../../toolbox/filter/rpcproxy`），再 `go mod tidy`。
   - 配置结构加 `RpcProxyArg rpcproxy.Config \`yaml:"rpcProxyArg"\``，配置加载成功后（含热更新）调 `rpcproxy.SetConfig(...)`。这一项只写进第 4 步的本地模板，`app.example.yaml` 保持原样，线上没配就是关闭。
   - 调外部下游的 `http.Client` 加 `Transport: rpcproxy.Transport(nil)`（原来有自定义 Transport 的传进去）。trpc 下游的 `rpcProxy` filter 只加在第 4 步的本地模板。
   - server filter 里要有 `logContext`（`toolbox/filter/logcontext`），日志才带调用方的 requestId；没有就一起加上。

   `go build ./... && go vet ./...` 通过后，把 `git -C <服务> diff` 发给用户，说明每处改动的作用和线上为什么不受影响（`enable` 默认关；`DOCKER_ENV` 非空时完全不注册）。
   完成：用户确认后单独提交一次，提交信息「<服务> 接入 rpcproxy，本地测试用」；或用户明确不接入，在用例文档「外部下游与替身」写明外部下游只能真实调用。

3. **复制标准脚本**：`<同步> --workspace <工作区> --apply`。工作区里已有同名文件且内容不同时先看差异：工作区里改过的，提回 `svc-local-test/kit/` 或告诉用户，再同步。
   完成：`<同步> --workspace <工作区>` 输出「标准脚本一致」。

4. **写本地配置模板**：
   - `localstart/config/app.local.yaml`：从 `app.example.yaml` 拷。连接信息换成 `__MYSQL_DSN__`、`__REDIS_ADDR__`、`__REDIS_PASSWORD__`、`__REDIS_DB__`；按进程变的项换成自定义变量（如 `__REFRESH__`）；本地专用密钥写死，注释「只用于本地测试」；外部下游地址保持真实地址，替身文件名按真实 host 算；加上
     ```yaml
     rpcProxyArg:
       enable: true
       readOnly: true            # 只读替身，没命中的真实调用，不写缓存
       localFilePath: "__STUB_DIR__"
     ```
   - `localstart/config/trpc_go.local.yaml`：从 `trpc_go.yaml` 拷。`global.env_name` 换成 `__ENV_NAME__`（默认 `lt`，同时会跑定时任务的 RPC 进程另给一个，任务锁才分得开）；service 端口 `__PORT__`、监听 `127.0.0.1`；日志写 `__LOG__`，`write_mode: 1` 同步写、`level: debug`；`server.filter` 有 `logContext`；`client.filter` 最后一个是 `rpcProxy`；兄弟服务的 client 按它 `env.yaml` 的端口写 `ip://127.0.0.1:<端口>`。
   完成：两份模板里连接信息、端口、日志路径都是变量；注释里也只出现定义过的 `__变量__`。

5. **写 `env.yaml` 和 `.gitignore`**：按 [ENV.md](ENV.md)。PORTS.md 里还没有这个服务就先加一行。进程名用服务名缩写加序号（`wx1`、`wxt1`），回写进用例文档「进程」。`secretFiles` 写 `localstart/config/app.local.yaml`。`.gitignore` 按[约定](../svc-local-test-flow/CONVENTIONS.md)「测试工作区布局」。
   完成：每个进程都有端口；`default` 里的进程都在 `procs` 里。

6. **兄弟服务**：`siblings` 里的每个兄弟服务，它自己的测试工作区要有 `env.yaml` 和 `localstart/`；缺的，对它从第 2 步做起，只配被测服务要用的进程。
   完成：每个兄弟服务的 `localstart/startserver.sh status` 列出 `siblings` 里写的进程。

7. **起来验证**：`localstart/startserver.sh start`（缺表时执行 `mysql.init`，也起兄弟服务），再 `./run env`。没起来的看 `localstart/log/<进程>/stdout.log`；连不上 MySQL、Redis 的，告诉用户要设的环境变量（见 `scripts/kitlib.py` 开头）。用例期间才起的进程（如定时任务实例）也起一遍、看过日志再停。
   完成：`./run env` 全部 ✅；汇报分到的端口和 Redis db、改了的业务代码和 commit、兄弟服务情况、要设的环境变量。
