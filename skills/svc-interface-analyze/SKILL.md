---
name: svc-interface-analyze
description: 读代码把被测服务的一个入口（RPC 方法、HTTP handler、定时任务）按执行顺序写成调用树，带每一步的解读和日志，存进测试工作区；同一入口已有调用树时在它上面增量补。生成用例前要拿到与当前代码一致的调用树，或想摸清某个入口怎么走时使用。
---

# 分析入口的调用树

在参考版本上，用 `gocalls.sh` 拉静态调用树当骨架，逐方法读代码，补成一份调用树（页面 JSON，格式见 [HTML-FORMAT.md](HTML-FORMAT.md)）。读者是写用例的人：要从调用树里看出走哪条路由什么条件决定、读写了哪些表和缓存 key、调下游发了什么、每一步打什么日志。术语见 [CONTEXT.md](../../CONTEXT.md)。

- `<本skill目录>`：本文件所在目录。
- `<服务>`：被测服务的 go 模块目录（有 `go.mod` 的那一层，如 `common_server/wxtoken`）。
- `<工作区>`：`<服务>/testcase/`，没有就建。
- `<接口名>`：RPC 用方法名（`GetAccessToken`），HTTP 用 handler 函数名（`handleAPI`），定时任务用任务名（`RefreshAccessToken`）；入口类型分别是 `rpc`、`http`、`cron`。
- 服务都不大，主 agent 自己从头读到尾，不派子 agent。

## 产物

| 路径 | 内容 | git |
|---|---|---|
| `<工作区>/analysis/<接口名>/<ts>.json` | 调用树，`<ts>` 是分析开始时间 `YYYYMMDDHHmmSS` | 提交 |
| `<工作区>/analysis/<接口名>/<ts>.calltree.json` | 骨架 | 不提交 |

`<工作区>/.gitignore` 里要有 `analysis/**/*.calltree.json`，没有就加上。

## 步骤

1. **定入口**：调用方指定了入口就用指定的。只给 `<服务>` 时取全部入口：
   - `rpc`：`main.go` 里注册的 trpc service 的实现类型上，proto 里声明的每个方法。
   - `http`：`thttp.RegisterNoProtocolServiceMux`、`http.HandleFunc` 等注册的每个 handler。
   - `cron`：`InitTaskTicker*` 等注册的每个任务，入口方法是传进去的那个函数。

   每个入口定下 `<接口名>`、入口类型、gocalls 用的入口全名（如 `'wxtokensvc.(*WxTokenImpl).GetAccessToken'`，只写方法名会命中 pb 里的同名 getter）、`<ts>`。
   完成：每个入口都有这四项。

2. **定做法**：参考版本是 `<工作区>/analysis/<接口名>/` 下 `<ts>` 最大的那份 JSON。

   | 参考版本 | 本次做 |
   |---|---|
   | 没有 | **新建**：从 `<本skill目录>/assets/interface-page.template.json` 拷成 `<ts>.json`，从第 3 步开始 |
   | 有 | 执行 `python3 <本skill目录>/scripts/calltree.py changed <参考版本> --dir <服务>`，列出参考版本的 `meta.commit` 之后（含未提交改动）调用链涉及的源文件哪些改了 |

   `changed` 输出「无改动」：参考版本的 `meta.commit` 就是 HEAD 时直接**复用**它，不新建文件，跳到第 6 步；不是 HEAD 时拷成 `<ts>.json`，改 `meta`（见第 6 步）后也算**复用**。有改动就是**增量**：拷成 `<ts>.json`，第 3 步重拉骨架，第 4 步只重读改动文件涉及的节点，其余节点保留。
   完成：每个入口都定下了「新建」「复用」或「增量」。

3. **生成骨架、补断点**：
   ```bash
   OUT=<工作区>/analysis/<接口名>/<ts>.calltree.json <本skill目录>/scripts/gocalls.sh <服务> '<入口全名>'
   ```
   第一次跑会在 `<本skill目录>/scripts/bin/` 现编 gocalls，要本机 go 1.24 以上。读、改骨架用 [scripts/calltree.py](scripts/calltree.py) 的 `load`/`walk`/`dump`。

   本仓库只有一个实现的接口调用已直接下钻；本仓库没有实现的（trpc client proxy、go-redis、`cipher.AEAD` 这类标准库接口、第三方 SDK）已标 `skipped: 桩/仓库外`。`calltree.py list --open <骨架>` 列出剩下的断点，只有两类：
   - `断点: 接口 invoke，N 个实现`：`candidates` 列了每个实现的 `文件:行`。
   - `断点: 遍历 []接口 后 invoke`：责任链。**执行顺序看返回 `[]接口` 的那个函数**，节点的出边不代表顺序。

   补断点：
   1. 打开调用点，看接口值从哪来（构造函数、`SetHandler`、全局变量），从 `candidates` 里定实现。
   2. 定下的用 `expand` 挂整棵调用链，多对一次挂完：
      ```bash
      python3 <本skill目录>/scripts/calltree.py expand <骨架> --dir <服务> \
        --entry '<实现A全名>' --onto '<断点A name>' --entry '<实现B全名>' --onto '<断点B name>'
      ```
   3. 同一个接口在不同调用点走不同实现：标 `todo: 按调用点分别铺，见页面 JSON`，第 4 步在各调用点下按实际实现铺。
   4. 定不了的：`todo` 里写候选的 `文件:行`。

   完成：`list --open` 为空。

4. **读代码**：按骨架从入口方法开始，照下面「读代码的规则」逐方法读，结论直接写进 `<ts>.json`。新建时根是 `<接口名>`，第一层是 `协议`、`入口方法`；根节点 `note` 写一句话职责和主要的下游、表。HTTP 入口的「协议」写路径格式、请求体和响应体约定；定时任务的「协议」写任务名、触发周期的配置项和分布式锁 key。
   完成：入口到每个本仓库叶子或外部边界都连得上。

5. **通读核对**：从根节点起，打开每个父方法源码逐层核对 `kids`：调用点行号递增，分支、循环、goroutine、`defer` 按执行流铺开，排错了当场调。
   完成：整棵树按执行顺序通读过一遍；分支、`db`、`rpc`、`cache` 节点都有 `log`。

6. **写 meta、交回**：
   - `meta.service` 写 `<服务>` 目录名，`meta.interface` 写 `<接口名>`，`meta.entryType` 写入口类型。
   - `meta.branch`、`meta.commit` 写当前分支和 HEAD 的 40 位完整 hash。
   - `git -C <服务> status --porcelain -- .` 有输出时（有未提交改动）写 `meta.dirty: true`，否则删掉这个字段。dirty 的调用树照样能用，下游判断代码改动时会更保守。
   - 有新词时写进 `terms`；`python3 -c 'import json,sys; json.load(open(sys.argv[1]))' <ts>.json` 自检能 parse。
   - 想看图时用 `<本skill目录>/assets/serve.sh <ts>.json 的绝对路径` 打开，地址是 `http://127.0.0.1:8766/view?json=<绝对路径>`，`serve.sh stop` 停掉。

   向调用方回报每个入口的：`<ts>.json` 路径；新建、复用还是增量；节点数；`log: 无` 的节点；剩下的 `todo`；是否 dirty。
   完成：每个入口都有 `meta.commit` 与 HEAD 一致的调用树。

## 读代码的规则

- **整棵树细铺**：骨架里本仓库的每个方法都读，下一次分析才能在它上面增量补。纯判断、取值的小方法（`expired`、`tokenKey` 这类）并进父节点的 `note` 一句带过。
- **仓库边界**：下钻到本模块最底层（含 dao、helper、内部 package）。同一仓库里的其他模块（`pkg/`）、`replace` 进来的 toolbox、第三方包、框架、下游服务，在调用处记一行就停。纯工具函数不展开，它拼出的 SQL、key、请求体记在父节点上。
- **每个方法深度优先这样读**：
  1. 写清输入、输出、副作用、分支条件（写到具体字段和取值）。
  2. 从上到下按执行顺序列出下一跳（本模块方法、DB、RPC、HTTP、缓存、外部包），记下调用点行号。本模块的被调方法先下钻到底，再回到兄弟节点。
  3. 每个节点填 `log`：格式串原文和 `文件:行`，没有日志写 `无`。日志缺判断要用的字段（只打了状态没打日期、打出来是指针）时，在 `note` 里写缺什么。
  4. 边界节点写全拼出的 SQL、缓存 key、RPC 请求结构、HTTP 的 method 和 URL，`type` 标 `db`/`rpc`/`cache`（HTTP 下游也标 `rpc`），关键代码放 `code`。
- **`kids` 按执行顺序排**，简单方法也一样：从上往下扫一层 `kids`，等于顺着代码读一遍。按功能归类、按重要程度排、把 DB 调用集中到一起，读者都对不上代码。
- **复杂方法按真实执行流铺**：有 goroutine、闭包、defer、channel、条件触发时，先从上到下列出每一步的行号，再照这个顺序建 `kids`。
  - 闭包被调用时才算一步。
  - `wg.Wait()`、`close(ch)`、拿锁放锁这类同步点单独成节点，把前后的步骤分开。
  - 死配置、开关注释、背景说明放最后，标题前缀「附注 · 」。
- 依赖源码在 `$(go env GOMODCACHE)/<模块路径>@<版本>/`，版本看 `<服务>/go.mod`；`replace` 到本地的看 `replace` 指向的目录。
- 按骨架的 `file:line` 用 `sed -n '<起>,<止>p'` 读方法体（`endLine` 是方法最后一行）。
- 页面 JSON 用 Python 按节点拼，一块块写进文件，每次写完 `json.load` 一下。
