---
name: svc-code-review
description: "Review the changes since a fixed point (commit, branch, tag, or merge-base) along two axes: Standards (does the code follow this repo's documented coding standards?) and Spec (does the code match what the originating issue/spec asked for?). Runs both reviews in parallel sub-agents and reports them side by side. Use when the user wants to review a branch, a PR, work-in-progress changes, or asks to \"review since X\"."
---

对 `HEAD` 与用户指定的固定点之间的 diff 做双轴审查：

- **Standards**：代码是否符合本仓库已文档化的编码规范？
- **Spec**：代码是否忠实实现了源 issue / 规格？

两条轴分别作为**并行子代理**运行，以免污染彼此的上下文，然后由本 skill 汇总它们的发现。

应当已经向你提供了 issue 跟踪器。如果没有，请让用户运行 `/setup-matt-pocock-skills`。

## 流程

### 1. 钉死固定点

用户所说的就是固定点（commit SHA、分支名、标签、`main`、`HEAD~5` 等）。如果他们没有指定，就向他们询问。

一次性记下 diff 命令：`git diff <fixed-point>...HEAD`（三点比较，因此对照的是 merge-base）。同时通过 `git log <fixed-point>..HEAD --oneline` 记下 commit 列表。

在继续之前，确认固定点可以解析（`git rev-parse <fixed-point>`），且 diff 非空。错误的引用或空 diff 应在此处失败，而不是在两个并行子代理内部。

### 2. 确定规格来源

按以下顺序查找源规格：

1. commit 信息中的 issue 引用（`#123`、`Closes #45`、GitLab `!67` 等），按跟踪器文档中的工作流获取。
2. 用户作为参数传入的路径。
3. 位于 `docs/`、`specs/` 或 `.scratch/` 下、与分支名或功能匹配的规格文件。
4. 如果什么都没找到，询问用户规格在哪里。如果他们说没有规格，**Spec** 子代理将跳过并报告 "no spec available"。

### 3. 确定规范来源

在仓库中搜索所有记录应如何写代码的文件。当 `CODING_STANDARDS.md` 或 `CONTRIBUTING.md` 存在时，必须列入清单。

在仓库已有文档之上，Standards 轴始终携带下面的**坏味道基线**：一组固定的 Fowler 代码坏味道（《重构》第 3 章），即使仓库没有任何文档也适用。两条规则约束它：

- **仓库优先。** 已文档化的仓库规范始终胜出；当它认可基线会标记的做法时，压制该坏味道。
- **始终是主观判断。** 每种坏味道都是带标签的启发式（"possible Feature Envy"），绝不是硬性违规。与此处任何规范一样，跳过工具已经强制执行的内容。

每种坏味道读作*是什么* → *如何修*；对照 diff 匹配：

- **Mysterious Name**：函数、变量或类型的名称未能揭示它做什么或持有什么。→ 重命名；如果想不出诚实的名字，说明设计本身含糊。
- **Duplicated Code**：同一逻辑形态出现在本次改动的多个 hunk 或文件中。→ 抽出共享形态，两边都调用它。
- **Feature Envy**：一个方法更多地伸进另一个对象的数据，而不是自己的。→ 把该方法移到它所依恋的数据上。
- **Data Clumps**：相同的几个字段或参数总是结伴而行（一个类型正待诞生）。→ 把它们捆成一个类型，传递那个类型。
- **Primitive Obsession**：用基本类型或字符串顶替一个理应拥有自己类型的领域概念。→ 给该概念一个自己的小类型。
- **Repeated Switches**：对同一类型的同一 `switch`/`if` 级联在本次改动中反复出现。→ 换成多态，或两边共用一张映射表。
- **Shotgun Surgery**：一次逻辑改动迫使 diff 中许多文件出现零散编辑。→ 把一起变化的东西收进一个模块。
- **Divergent Change**：一个文件或模块因若干不相关的原因被编辑。→ 拆分，使每个模块只因一个原因而变。
- **Speculative Generality**：为规格中并不存在的需求而添加的抽象、参数或钩子。→ 删掉；内联回去，直到真正的需求出现。
- **Message Chains**：调用方本不该依赖的长 `a.b().c().d()` 导航。→ 把这段遍历藏到第一个对象的一个方法后面。
- **Middle Man**：一个类或函数基本上只是继续转交。→ 砍掉它，直接调用真正的目标。
- **Refused Bequest**：子类或实现者忽略或覆盖了所继承的大部分内容。→ 丢掉继承，改用组合。

### 4. 并行拉起两个子代理

同时发出两个子代理调用，在前台运行，并汇总它们返回的报告。

**Standards 子代理提示**应包含：

- 完整的 diff 命令和 commit 列表。
- 你在第 3 步找到的规范来源文件清单，**外加第 3 步的坏味道基线**全文粘贴进去（子代理没有其他途径获取它）。
- 简报："按相关的文件/hunk 报告：(a) diff 违反已文档化规范的每一处：引用该规范（文件 + 规则）；以及 (b) 你发现的任何基线坏味道：点名并引用 hunk。区分硬性违规与主观判断：违反已文档化规范可以是硬性的，但基线坏味道始终是主观判断，且已文档化的仓库规范覆盖基线。跳过工具已强制执行的内容。不超过 400 词。"

**Spec 子代理提示**应包含：

- diff 命令和 commit 列表。
- 规格的路径或已获取的内容。
- 简报："报告：(a) 规格要求但缺失或不完整的需求；(b) diff 中未被要求的行为（范围蔓延）；(c) 看起来已实现但实现看起来不对的需求。每条发现都引用规格原文。不超过 400 词。"

如果规格缺失，跳过 Spec 子代理，并在最终报告中注明。

### 5. 汇总

将两份报告放在 `## Standards` 和 `## Spec` 标题下呈现，原文照录或略作清理。**不要**合并或重排发现，因为两轴是有意分开的（见_为何要两条轴_）。

以一行摘要收尾：每轴发现总数，以及_各轴之内_最严重的问题（如有）。不要跨轴选出一个总赢家：那正是这种分离要防止的重排。

## 为何要两条轴

一次改动可以通过一条轴而在另一条轴上失败：

- 代码遵循所有规范但实现了错误的东西 → **Standards 通过，Spec 失败。**
- 代码精确做了 issue 要求的事但破坏了项目约定 → **Spec 通过，Standards 失败。**

分开报告可防止一条轴掩盖另一条。

<!-- md-zh
source: 0227480e0258972ecc20ae592ef14035fb1a617a603bb6a613cd9f851a79e456
d88ec403c1cd912420b3b4f6adfc214efc7d22c3cffd652351a6edf4ae12de54
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b
687ea18c01612cecdf9395915e978cc63c8ee5312aa11ada4b76ab6313b25b63
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b
892193307df743ace7e86b3c4c6d937740cd97020750647a7756f49a0d0effce
b0969ce74bda9987969662dbf47c8f9f704dca00c8738610d00e8256f883a04e
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b
07329d1d01437e670051b0ec1cc09be8b66f68278a6ae04d751130cbf1eee3b6
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b
b7baeca7cce06d83564edf5e18eadfd36cfd76f6d17569c65219718006e711c1
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b
bc9c478fd63463cd3b44cf6931e4fe6eb121af166c4fdc5296a63d7b22c2b726
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b
9729136e112f9371c57e6224838651fd0a828b7c76b25e1e2f5d9dcac0500859
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b
178fd32632707e7f159217d4255c4ab1adee46690b438787bee5f74b6b692174
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b
35ae8e3b141a9c59a40c360664824ee164adefb154ff7c5c1a12a5a78712cd4c
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b
2a18e8f5bcdaa56c82ae4b41abd503fcd1140fc69549242b6574cb4ceb191d65
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b
05def91a5769546e79c6c988f4e78563264b61a6be366213ac57910eae296a40
ee742c26fead90c1e1989c192fcdb07daa3eb0e11345fb74255f29560ae04e8e
fc15afb34c18674eef448ac1bd8a0d03e76a2132398dfbad6c7da7a1a9e7a866
3d7872d587154848836ed5ec940a7ec789461eca6f2c38f560e4eb04ed5be6e9
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b
5fb294f71145fbb75cc2b853dff13568c4b695728e8e9ccd00d105bdfbc41960
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b
2ef82137617ec11d1e57973f7b8d452f4226d913bbfae0560bda3754bd21e8dd
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b
94e183846d234c69d0c915faaf0b80e5c312768646e79bcde50cf9dd6a5c777b
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b
0ccd1dc67fae36391d939a5595b5bff1197a87cdc896856c4bbb70b2520a0d01
54d11f06528a3fea058713ace66ae7ceb2aec2cabffee41a4df6de17b4ac3346
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b
3efc43b684b65fb1e188a23b067941592a20b5a00762d32fa647e726972a3320
60dfe907859e87282f6a5970687f32ebdb85e1fde33882e312e880b89004927a
e3ca5ef4e42f5bcb665d554242e0b013b6cb6827696a9d0f178716dfef05358d
f8ef065e4ef61876041e60efac079e7bc207f631d7a1fccc6cdffec45061a93f
d4051d703e10b84e6b082e2b46fb1a990478367f7ce5eebd9b166aed5b94b88e
6e9e5e5db37619846b7dbf3c1c8e147df4e4663a2dff2ef8c68ff3881bda50ba
3547fa974adbb2bcaa7cc254d4b927c86a62abb270fa1c55fa5533fb3223cb1f
1e8869a7eecf80df354dfb3d9e3aee80fd7297b248c4f748f36eedbd956a49f2
d7052df8f199da0b0a896228a1fc2a0125ce0a32f59d46f13130a423d521f9df
9e1323d96ff07b7b9838b70aff37f15c9d2e2772fbdaf69e53cb8df30c3a490f
19edbc4c5288887c81745345dfd03e6e397b3bcb72cbbfcf07e29b41a561dadd
e17073e11b3d32955cd3014af80a0226eec4f378860a6920430d4a650bcae18e
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b
84d0c9786c869d1d82377f23e0258adcd8e98e29e22aa85bab01af3958fa7967
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b
fde3ea9c8ee5234562b680b6bcf582cdac63fb4bdac6e3ad715a75a505bfadba
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b
e5e1e8ef4567d446c712a9349556d2ae9c543fcf14989d0f18398545d4974c09
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b
8ac7dd2092f0d75e1ea6f613c70298b772a3b261f28dc4585b0494ed4f429f64
c6868e87dce4708cfbcd8ee6bf24741fbfc756cf9384d9e6a7e1c41663100a96
5e70990d53b7380d21776645ada48ac76adc707a3a7e4d4acf31e927cc99611b
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b
ba68ffd635d9d84dda9917d6749f9758304fe8d0ba010dfbbb8b1efdc385c18f
a3fbf1b8e1ea74d4315ed76ee89541ce0bd4b7c16f4c1b1cb5c501bf00ee31d7
3d53f7ac116d1c6334091509c5efc6aa187fe2063c0bda2459dd2be24fd85416
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b
6543b9b78c2fe48ef62f49330a1a98cc98ec16a2d737a3d5d7a9d6cc01d64fe5
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b
136ce557cd64d6f139ab9c9ee5361ed4a0ddc1367059f6c67aad9180d9c88d5a
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b
2bed3e33766dfa51fbdee38859be61525c98875c0f77583d2bc59f08186f3653
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b
1d54149324b0e19e46169f0e6f6dfa555fa03b6cd0ece6535b3f932958d95836
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b
3991fa24ba72afc15019437fd4ab7150f4ddb22778192bc360878f5d94649a0d
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b
0f4c291d8b64844671a52364280ea9466815846f988c78d24351337f9c6f4feb
16c953f099ec8c3bb8db5b13788f00605e3640284bf178b46d94d2354fe489f0
-->
