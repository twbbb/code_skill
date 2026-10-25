<!--
翻译临时文件。只给对照看。AI 不要读，不要写。
-->

---
name: svc-implement-spec
description: "Implement the result of /to-spec and /to-tickets in code."
disable-model-invocation: true
---

你已获得一份规格说明。该规格应附有相关工单，说明如何实现该规格。

问题跟踪器应该已经提供给你。如果没有，请告诉用户运行 `/setup-matt-pocock-skills`。

目标是在单一 **集成分支** 上实现整份规格，按问题跟踪器关闭工作的方式解决每张工单，在本地对服务做端到端测试，并完成代码审查。

工单不是步骤清单。它们是带有阻塞关系的 **任务图**。这意味着始终存在一批可供领取的工单 **前沿**。

与子代理之间的通信应尽量精简。主要通过 **上下文指针** 沟通：指向规格、工单、研究笔记和既往提交。不要重复指针已能获取的信息。

**实现子代理** 应尽可能在后台运行，以实现最大并发。

本地测试仅在集成分支上、由主代理执行：`svc-local-test-flow` 会停下来让用户确认用例，且本地端口、数据库和 Redis 由整台机器共享，因此一次只能跑一轮。

## 步骤

1. 阅读规格和工单，理解任务图。

2. （可选）使用 **探索子代理** 完成工单所需的任何探索——相关代码库文件或外部文档。确保探索子代理能够保存文件——它应将 markdown 笔记保存在仓库外的目录中，供后续所有子代理访问。这样 **实现子代理** 就能专注于实现，而不是探索。

3. 创建集成分支并记下其基线提交：它是下文每次审查的固定起点。如果问题跟踪器通过 PR 关闭工作，或用户要求开一个 PR，则在步骤 5 首次合并之后打开草稿 PR（没有任何超前于 main 的提交的分支无法打开 PR），并标记为关闭该规格和工单。

4. 使用 **实现子代理** 实现每张工单，每个子代理在各自的 worktree 和各自的分支上工作。每个实现子代理：
   - 开始前确认其 worktree 基于集成分支，若不是则重置到该分支；
   - 构建该工单，定期运行类型检查（`go build ./... && go vet ./...`），并在最后运行一次现有测试套件；
   - 在报告完成之前，将集成分支的最新提交合并到自己的分支。

5. 一旦 **实现子代理** 完成，用 **合并子代理** 将其工作合并到集成分支。

6. 如果这改变了可用工单的 **前沿**，再启动更多 **实现子代理** 处理新工单。这样可以实现最大并发。

7. **测试。** 所有工单合并完成后，检出集成分支，并对规格涉及的每个服务用 `svc-local-test-flow` 调用 Skill 工具。用单个 **实现子代理** 修复它报告的失败，合并，然后再次调用 `svc-local-test-flow`（它会对变更代码走 同步 路径）。
   当每个用例都通过，或其余用例阻塞于用户时，即告完成。

8. **审查。** 在集成分支上用 `svc-code-review` 调用 Skill 工具，固定起点为步骤 3 的基线提交。用单个 **实现子代理** 修复它提出的问题并合并。
   当每个问题都已修复，或已向用户说明保持原样时，即告完成。

9. **循环。** 如果步骤 8 改动了任何代码，回到步骤 7。否则继续：上一轮测试已通过，上一轮审查未改动任何内容。

10. 如果已有草稿 PR，将其标记为待审查。否则，按问题跟踪器关闭工作的方式解决每张工单，并报告集成分支。

11. 清理所有 **实现子代理** 的 worktree，并停止本地服务（在每个已测服务的 `testcase/` 中执行 `localstart/startserver.sh stop --siblings`）。

<!-- md-zh
source: 2bf0029c3ae5e9a5f77fc52ec2f90da6652cb46ff7db9ee91ffb68de2359ed7b
d54b8c3226f059e178e31aeaa86c1e274f2734aa88b02a0b3b65fbaba9b72808
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b
233105c28546e90e543feb975c9acc60a150ad3fed197eb94d960f1e7c596a47
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b
80e7baf9ef27365fc91d6f0b508e049f1af0cd3ce9062d926d09d729e504628b
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b
8d113851ada2b3489273119d45604c8db6529526e6ee6ab2b1ed263730dc7237
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b
8d6822f0643c2974ceb2e6afdfda499ca0854801838c06eef234453f4e4db054
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b
56acbffec788d0e58700f58ba285a6de03c79b372fbd761e99cb84be63aece4b
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b
049134853b85eedfca1208e359d2d4be96cd005c87827bc65c326efc273e0dfb
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b
208d3d2e85bf21c5449a3041ad2d83b22eb6c52fcdddc3977851afe5d5f6687b
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b
e935da64fdb59fc9bf8a846fb7f22c14156e8abd7842124149869c5135e7554f
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b
d83535dc70fa08da65d50f550db15910196668440b24457563888733473153b5
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b
9efeb1976ce0c1c4526c9b4f259818475560b4c15bac05b6e0617df4610e5297
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b
64fc5af34497794137f024daf57c84aac275e0aa2d5d8a2ed43c268d4f4e9859
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b
ce9991948d13f629fecd9c58985ef92b55f600e3a4781161805ffee2a7dfed3b
597d4f51c83119d994db20a11eac0201ef00c28549b97253ac5184f54df34514
c82454f5ff2c22fa9d407a4aed25ec5d7bfa73b7a7d6d0558229c90b61146720
fa3187bc102182b6c574387e738d074a22e6033f60ef640fba421adbb5b362a8
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b
ad3f08a3170e8514a78f754b433b16df2b14b067d8bfd509d04f3763439a2fb7
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b
a77f12e6fafaa459728c0cd47d38dfd649b7cdf430df61445cc3602b327d5d81
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b
779cf4f072ec696fdb8963c79050252e1a9770b78b4e477325ed776dc8be5eb3
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b
1055f76557e6b1cc11d3d824a9ef177ad17192f75b7448ce4950fdd59704c24b
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b
8cfab13514b5003d1c4994ed63f17bf7e4d4824ef8f5b8ffd6a5fa788f7a58a6
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b
3406d59b2ef85061d88c03903790a826d0e135ceadd774b146bdbdb2d617b1cb
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b
db632ed50d83e74e0fe291423c4e08bb494feff3d4a3ba83d3dbc2632c84e4f7
-->
