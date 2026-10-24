# 单服务本地测试的约定

四个 svc 技能（svc-interface-analyze、svc-gen-test-case、svc-local-env、svc-local-test）共用。术语见 [CONTEXT.md](../../CONTEXT.md)，决定见 `docs/adr/`。

## 适用范围

被测服务配置是本地文件、依赖本机 MySQL 和 Redis、能独立在本机起起来，如 common_server 的 gateway、auth、wxtoken。

## 路径占位

- `<服务>`：被测服务的 go 模块目录，有 `go.mod` 的那一层（如 `common_server/wxtoken`），用户给出。
- `<工作区>`：`<服务>/testcase/`，测试工作区。所有命令都在这里执行。
- `<用例文档>`：`<工作区>/<服务目录名>.md`，格式见 [CASE-DOC.md](../svc-gen-test-case/CASE-DOC.md)。
- **样板**：`common_server/wxtoken/testcase/`，一份做完的测试工作区。拿不准文件该长什么样时照它抄。

## 原则

- **真实优先**：兄弟服务（同一仓库、被被测服务调用的其他服务，如网关调 auth）在本机真实起起来；只有本机调不通的**外部下游**（微信、谷歌、邮件）用**替身**，并在用例文档写一行 `降级：<真实> → 替身，<原因>`。
- **替身**是 rpcproxy 缓存目录里的一份文件，trpc 和 HTTP 下游都一样（用法见 `toolbox/filter/rpcproxy/README.md`）。替身没有状态，同一份请求永远拿到同一份返回：要下游前后返回不同，就让两次请求不同（带旧 token 和新 token），做不到时把用例拆成 `NNa`、`NNb` 换替身。见 `docs/adr/0001-stateless-stubs-only.md`。
- **合成数据**：每个被测服务一个测试标识前缀（如 `wx_lt_`），每条用例只用带自己序号的标识（`wx_lt_01`、`wx_lt_06_near`），数据脚本开头先清自己的行和 key。
- **日志即证据**：流程链路用被测服务现有的日志核对；没有日志的节点改用库表、Redis 或替身命中核对，业务代码保持原样。

## 测试工作区布局

| 路径 | 内容 | 谁写 |
|---|---|---|
| `<服务目录名>.md` | 用例文档，含用例结果和执行汇总 | svc-gen-test-case 写用例，svc-local-test 写结果 |
| `analysis/<接口名>/<ts>.json` | 调用树 | svc-interface-analyze |
| `env.yaml`、`localstart/config/` | 本地环境，格式见 [ENV.md](../svc-local-env/ENV.md) | svc-local-env |
| `run`、`kit_test.go`、`scripts/`、`localstart/startserver.sh` | **标准脚本**副本，源头在 `svc-local-test/kit/`（见 `docs/adr/0002-copy-scripts-into-workspace.md`） | svc-local-env 复制 |
| `cases.yaml` | 执行清单，格式见 [CASES.md](../svc-local-test/CASES.md) | svc-local-test |
| `data/NN.sql`、`data/NN.redis` | 数据脚本 | svc-local-test |
| `common_test.go`、`<分组>_test.go` | 服务自己的辅助、每条用例一个 `Test_NN_<Method>` | svc-local-test |
| `result/<轮>/` | 证据文件、全量日志、本轮汇总，格式见 [EVIDENCE.md](../svc-local-test/EVIDENCE.md) | 脚本和 svc-local-test |

都提交；`localstart/bin/`、`localstart/log/`、`localstart/rpcproxy_cache/`、骨架 `analysis/**/*.calltree.json` 放进 `.gitignore`。

用例序号 `NN`（两位，拆段加 `a`、`b`）是数据脚本、test 函数、证据文件的共同主键。
