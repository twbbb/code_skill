---
name: svc-local-test
description: 按已确认的用例文档在本机执行被测服务的用例：为每条用例生成数据脚本、替身和 test 代码，执行、取证、判定，回写用例结果。用户要求执行或重跑某个服务的用例时使用。
---

# 执行本地用例

术语见 [CONTEXT.md](../../CONTEXT.md)。

- `<服务>`：被测服务的 go 模块目录。`<工作区>`：`<服务>/testcase/`，所有命令都在这里执行。
- 输入是 `<工作区>/<服务目录名>.md`（由 `../svc-gen-test-case/SKILL.md` 生成、用户确认过），以及 svc-local-env 准备好的 `env.yaml`、本地配置模板和标准脚本。参考 `common_server/wxtoken/testcase/`，看一份做完的测试工作区。
- `<同步>`：`python3 <本skill目录>/scripts/sync.py`。`kit/` 是标准脚本，复制在工作区里，工作区里不改（见 `docs/adr/0002-copy-scripts-into-workspace.md`）。
- 调用一次本 skill 就是一**轮**，`<轮>` 是开始时间 `YYYYMMDD-HHMMSS`。执行结果写在 `result/<轮>/`，每条用例一份**证据文件**，格式见 [EVIDENCE.md](EVIDENCE.md)。

## 工作区产物

| 路径 | 内容 | 谁写 |
|---|---|---|
| `<服务目录名>.md` | 用例文档，含用例结果和执行汇总 | svc-gen-test-case 写用例；本 skill 写结果 |
| `env.yaml`、`localstart/config/` | 本地环境 | svc-local-env |
| `run`、`kit_test.go`、`scripts/`、`localstart/startserver.sh` | 标准脚本副本 | svc-local-env 复制 |
| `cases.yaml` | 执行清单，格式见 [CASES.md](CASES.md) | 本 skill |
| `data/NN.sql`、`data/NN.redis` | 数据脚本 | 本 skill |
| `common_test.go` | 服务自己的辅助：建 client proxy、查状态、常量 | 本 skill |
| `<分组>_test.go` | 每条用例一个 `Test_NN_<Method>`，按入口分组拆文件，如 `token_test.go`、`proxy_test.go` | 本 skill |
| `result/<轮>/` | 证据文件、全量日志、本轮汇总 | 脚本和本 skill |

都提交。`localstart/bin/`、`localstart/log/`、`localstart/rpcproxy_cache/` 不提交。

### 生成标记

生成的每个 test 函数、数据脚本，第一行都带 `@gen 用例NN`；`cases.yaml` 里每条用例用 `mark` 字段。手工改过的产物，把 `@gen` 改成 `@manual`。只改写带 `@gen` 的产物；`@manual` 的保持原样，需要改时在用例下标「待复核」交给用户。

## 步骤

1. **检查前提**：
   - 用例文档「测试前置」有「用户确认」记录。标了 `- 待确认` 的用例不执行，除非用户这次点名要执行。
   - `<同步> --workspace <工作区>`：不一致时把差异给用户看，用户同意后加 `--apply`；工作区里改过的标准脚本先提回 `kit/`。
   - `localstart/startserver.sh status` 和 `./run env`：用例要用的进程都在监听。没有 `env.yaml`、缺进程（用例文档「进程」里有、`env.yaml` 里没有）、兄弟服务没准备的，按 `../svc-local-env/SKILL.md` 补。业务代码有更新就 `localstart/startserver.sh restart`，它会重新编译。
   完成：`./run env` 全部 ✅。

2. **选用例、定轮次**：默认执行全部用例，跳过「已废弃」和「待确认」。用户指定序号时只执行指定的。标了「待复核」的用例：产物带 `@gen` 就按新的用例描述重新生成，带 `@manual` 就保持原样，在结果里写明。用当前时间定下 `<轮>`，本轮所有命令都用它。
   完成：本次要执行的序号清单和 `<轮>` 已确定。

3. **写数据脚本**：每条用例一份 `data/NN.sql` 和（或）`data/NN.redis`，写法见 [CASES.md](CASES.md)「数据脚本」。测试标识用用例文档「测试数据」里的，写进 `cases.yaml` 的 `accounts`。全表扫描的用例先清掉所有带前缀的行。本地专用密钥加密这类要调工具的值，在 `cases.yaml` 的 `render` 里定义占位符。
   完成：每条要执行的用例都有数据脚本，或在 `cases.yaml` 写了 `data: false`。

4. **写 test 代码和 cases.yaml**：每条用例一个函数 `Test_NN_<Method>`，只用 `kit_test.go` 和 `common_test.go` 里的辅助。

   ```go
   // @gen 用例10：Proxy 遇到 40001，换 token 重试一次
   func Test_10_Proxy(t *testing.T) {
   	c := NewCase(t, "10")
   	a := Acc(t, "P10")
   	// 替身：旧 token 回 40001，新 token 成功；新 token 由 stable_token 的替身发
   	c.StubHTTP("POST", wxHost+"/cgi-bin/stable_token", stableBody(a), &rpcproxy.HTTPRsp{
   		Body: json.RawMessage(`{"access_token":"tok-lt10-new","expires_in":7200}`)})
   	c.StubHTTP("POST", wxHost+"/wxa/msg_sec_check?access_token=tok-lt10-stale", `{"content":"hello"}`,
   		&rpcproxy.HTTPRsp{Body: json.RawMessage(`{"errcode":40001,"errmsg":"invalid credential"}`)})
   	c.StubHTTP("POST", wxHost+"/wxa/msg_sec_check?access_token=tok-lt10-new", `{"content":"hello"}`,
   		&rpcproxy.HTTPRsp{Body: json.RawMessage(`{"errcode":0,"errmsg":"ok"}`)})
   	req := &wxtokenpb.ProxyReq{ /* 用例文档的参数 */ }
   	rsp, err := wxtokenpb.NewWxTokenClientProxy(c.ClientOpts("wx1")...).Proxy(context.Background(), req)
   	c.Record("WxToken/Proxy", req, rsp, err)
   	if err != nil {
   		t.Fatalf("Proxy 失败: %v", err)
   	}
   	// 只断言用例文档「预期结果-响应」里的字段，状态和流程由 run_case.py 取证
   }
   ```
   - RPC 入口用 `c.ClientOpts(<进程>)` 建 proxy，它带上本条 requestId；`c.Record` 传发请求用的同一个 `req`。HTTP 入口用 `c.HTTP(<进程>, method, path, body, header)`；被测进程自己生成 requestId 的（如网关），从响应里取出来调 `c.AddRequestID`。
   - 外部下游每一次调用写一份替身：trpc 用 `c.StubRPC(被调服务名, 方法名, 被测服务会发出的请求, 返回, 身份 metadata)`，HTTP 用 `c.StubHTTP(method, 带 query 的 URL, 请求体原文, 返回)`。请求按代码里拼请求的地方写，和被测服务实际发出的逐字段一致才会命中；命中本身就是请求内容的证据。兄弟服务不写替身。
   - 定时任务入口：test 里先写替身，再 `c.Exec("localstart/startserver.sh", "start", <实例>)` 起定时任务实例，用 `WaitLog` 等到任务结束的日志行；`cases.yaml` 的 `after` 写停实例，`also` 写匹配定时任务 requestId 的正则。多实例抢锁的用例起两个实例，`proc` 写两个。
   - 一条用例要多次调用、中间改数据或换替身时，拆成 `Test_NNa_`、`Test_NNb_`，后一段的数据改动写成 `data/NNb.*`。
   - 同时为每条用例在 `cases.yaml` 写一条（格式见 [CASES.md](CASES.md)）：`pre` 覆盖「前置条件」，`post` 覆盖「预期结果-状态」，`flow` 取公共流程链路加本用例的分支节点（标「无日志」的不写）。
   完成：`go vet .` 通过；`./run --list` 列出本次要执行的全部用例。

5. **执行并取证**：`./run --round <轮> NN [NN ...]`（或 `./run --round <轮> all`）。它对每条用例依次：建证据文件 → 清替身目录 → 数据脚本 → before → 前置核对 → go test → 原始输出 → 流程链路（含替身命中）→ rpcproxy 日志 → 全量日志 → after → 清替身目录。同一轮重跑加 `--force`。
   1. `python3 scripts/evidence.py brief --round <轮> --nn NN` 看每个流程节点和替身是否命中、go test 退出码。
   2. 替身没命中按 [EVIDENCE.md](EVIDENCE.md)「流程链路」排查，改 test 代码后 `--force` 重跑这条。
   3. 按 [EVIDENCE.md](EVIDENCE.md) 填流程链路结论和核对表：`python3 scripts/evidence.py judge --round <轮> --nn NN --verdict 通过|失败|阻塞 --nodes "✅,✅,无日志" --row "<检查项> ;; <预期> ;; <实际> ;; <结论> ;; <原始输出>" … --note "<说明>"`。
   完成：每条选中的用例都有符合 [EVIDENCE.md](EVIDENCE.md)「完成」的证据文件。

6. **判定**：
   - **通过**：核对表全部 ✅，流程链路每个节点是 ✅ 或「无日志」（「无日志」的在核对表里已用状态核对为 ✅），每个替身都命中。
   - **失败**：业务行为不符合预期。定位到代码行写进「说明」，业务代码保持原样，交给用户。
   - **阻塞**：环境或数据问题得不出结论。能自己修的（进程没起、数据脚本写错、替身请求写错、端口不对）修好后 `--force` 重跑，「说明」里写修了什么。修不了的（缺配置值、要改业务代码才能测、证据不够定位）停下来，把原因和需要用户决定的事报告给用户；证据不够时写清缺哪条日志、哪个变量。
   - 实际行为符合需求、是用例预期写漏或写错：改用例文档的预期，在该用例下加 `- 待复核：<原因>`，按改后的预期判定。
   - 执行中发现用例预期之外的问题（日志、性能、幂等），能补成用例的追加一条新序号的用例，标 `- 待确认`，告诉用户；补不成用例的记进执行汇总「其他发现」，附代码行。
   完成：本轮每份证据文件的判定都是通过、失败或阻塞之一。

7. **回写结果**：
   - `python3 scripts/evidence.py summary --round <轮>`，生成 `result/<轮>/summary.md`。它同时检查证据里有没有密钥、密码原文，有就先改掉（换成 `***`）再跑。
   - 在用例文档每条执行过的用例末尾写本轮结果，覆盖上一次的：
     ```markdown
     - 结果：通过｜2026-10-24 21:26｜[证据](result/20261024-212559/10_Proxy.md)
     ```
     拆段的用例每段各写一行 `- 结果（10a）：…`。
   - 文档末尾维护「## 执行汇总」，按每条用例的最新结果统计全部用例：总数、通过、失败、阻塞，失败和阻塞的清单，降级（来自「外部下游与替身」），「其他发现」，以及结果来自哪几轮（链接各轮 `summary.md`）。
   完成：`summary` 退出码为 0；每条执行过的用例都有链接到本轮证据文件的结果；执行汇总与逐条结果一致。

8. **汇报并停服务**：把执行汇总、每条失败用例的定位、每条阻塞用例的原因和要用户决定的事、其他发现报告给用户。然后 `localstart/startserver.sh stop --siblings`。中途因阻塞等用户决定时先不停。
   完成：汇报已发出；`localstart/startserver.sh status` 每个进程都是 `stopped`。
