# code_skill

自建服务用的技能插件 `code-skill`，以后的技能都往这里加。术语见 [CONTEXT.md](CONTEXT.md)，决定见 [docs/adr/](docs/adr)。

## 安装

```bash
claude plugin marketplace add twbbb/code_skill      # 或本地目录：claude plugin marketplace add <code_skill 目录>
claude plugin install code-skill@code-skill
```

改了技能以后执行 `claude plugin marketplace update code-skill`，再重开会话。

## 技能

新加技能时，在 `skills/` 下建目录，并登记到 `.claude-plugin/plugin.json` 的 `skills`。

### 单服务本地测试

给能独立在本机起起来的服务生成用例、本地执行、留证据。依赖远程配置中心、注册中心才能起来的服务不在此列。

入口是 [svc-local-test-flow](skills/svc-local-test-flow/SKILL.md)：按工作区现状选「新建」「同步」「重跑」路线，依次带着下面几个技能走。共用的约定在 [CONVENTIONS.md](skills/svc-local-test-flow/CONVENTIONS.md)。

| 技能 | 做什么 | 触发 |
|---|---|---|
| [svc-local-test-flow](skills/svc-local-test-flow/SKILL.md) | 一条龙：生成用例 → 用户确认 → 准备环境 → 执行取证 | 自动 |
| [svc-interface-analyze](skills/svc-interface-analyze/SKILL.md) | 读代码，把一个入口写成调用树 | 自动 |
| [svc-gen-test-case](skills/svc-gen-test-case/SKILL.md) | 生成或增量更新用例文档，等用户确认 | 手动或 flow |
| [svc-local-env](skills/svc-local-env/SKILL.md) | 接入 rpcproxy，生成本地启动脚本，建本地库 | 手动或 flow |
| [svc-local-test](skills/svc-local-test/SKILL.md) | 按用例文档执行，取证、判定、回写结果 | 手动或 flow |

「手动」的技能设了 `disable-model-invocation`，不占上下文，敲名字就能单独用。
