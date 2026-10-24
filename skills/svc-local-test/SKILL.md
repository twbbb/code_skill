---
name: svc-local-test
description: 按已确认的用例文档在本机执行被测服务的用例：写数据脚本、替身和 test 代码，执行、取证、判定、回写结果。通常由 svc-local-test-flow 带着走。
disable-model-invocation: true
---

# 执行本地用例

先读 [约定](../svc-local-test-flow/CONVENTIONS.md)。`<同步>` 指 `python3 <本skill目录>/scripts/sync.py`。

调用一次就是一**轮**，`<轮>` 是开始时间 `YYYYMMDD-HHMMSS`；结果写在 `<工作区>/result/<轮>/`，每条用例一份**证据文件**（格式见 [EVIDENCE.md](EVIDENCE.md)）。

## 步骤

1. **检查前提**：
   - 用例文档「用户确认」有记录。
   - `<同步> --workspace <工作区>`：不一致时把差异给用户看，同意后加 `--apply`；工作区里改过的标准脚本先提回 `kit/`。
   - `./run env`。缺 `env.yaml`、缺用例文档「进程」里的进程、兄弟服务没准备的，按 `../svc-local-env/SKILL.md` 补；业务代码更新过就 `localstart/startserver.sh restart`（会重新编译）。
   完成：`./run env` 全部 ✅。

2. **选用例、定轮次**：默认全部，跳过「已废弃」和 `- 待确认`（用户点名的除外）；用户指定序号就只跑那些。标了「待复核」的，`@gen` 产物按新描述重新生成，`@manual` 的原样保留并在结果里写明。用当前时间定 `<轮>`。
   完成：本轮的序号清单和 `<轮>` 定下了。

3. **写数据脚本**、4. **写 test 代码和 cases.yaml**：按 [TESTCODE.md](TESTCODE.md)。已有且不受「待复核」影响的产物沿用。
   完成：每条要跑的用例都有 `data/NN.*` 或 `data: false`；`go vet .` 通过；`./run --list` 列出全部要跑的用例。

5. **执行并取证**：`./run --round <轮> NN [NN ...]`（或 `all`），同一轮重跑加 `--force`。然后逐条：
   1. `python3 scripts/evidence.py brief --round <轮> --nn NN`：看每个流程节点、每份替身是否命中，go test 退出码。
   2. 替身没命中：看「原始输出」里 rpcproxy 日志的 `cache|miss|<另一个文件>`，对照代码找出请求差在哪个字段，是替身写错就改 test 代码 `--force` 重跑这条，是代码行为不符就判失败。
   3. 按 [EVIDENCE.md](EVIDENCE.md) 填：`python3 scripts/evidence.py judge --round <轮> --nn NN --verdict 通过|失败|阻塞 --nodes "✅,✅,无日志" --row "<检查项> ;; <预期> ;; <实际> ;; <结论> ;; <原始输出>" … --note "<说明>"`。
   完成：每份证据文件都满足 [EVIDENCE.md](EVIDENCE.md)「完成」。

6. **判定**：
   - **通过**：核对表全 ✅；流程节点都是 ✅ 或「无日志」（已用状态核对为 ✅）；每份替身都命中。
   - **失败**：业务行为不符合预期。定位到代码行写进「说明」，交给用户；业务代码保持原样。
   - **阻塞**：环境或数据问题得不出结论。自己能修的（进程没起、数据脚本、替身请求写错、端口）修好后 `--force` 重跑，「说明」写修了什么；修不了的（缺配置值、要改业务代码才能测、证据不够定位）停下来，把原因、缺的日志或变量、要用户决定的事报告给用户。
   - 实际行为符合需求、是用例预期写漏或写错：改用例文档的预期，加 `- 待复核：<原因>`，按新预期判定。
   - 发现用例预期之外的问题（日志、性能、幂等）：能补成用例的追加新序号、标 `- 待确认` 并告诉用户；补不成的记进执行汇总「其他发现」，附代码行。
   完成：本轮每份证据文件的判定都是通过、失败或阻塞。

7. **回写结果**：`python3 scripts/evidence.py summary --round <轮>`（同时查证据里有没有密钥原文，有就换成 `***` 再跑）。按 [CASE-DOC.md](../svc-gen-test-case/CASE-DOC.md) 给每条跑过的用例写结果行、更新「执行汇总」。
   完成：`summary` 退出码 0；每条跑过的用例都有链接到本轮证据的结果行；执行汇总与逐条结果一致。

8. **汇报并停服务**：报告执行汇总、每条失败的定位、每条阻塞的原因和待决定事项、其他发现。然后 `localstart/startserver.sh stop --siblings`；等用户决定阻塞项时先留着进程。
   完成：汇报已发出；`localstart/startserver.sh status` 每个进程都是 `stopped`。
