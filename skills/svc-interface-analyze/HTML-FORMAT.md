# 产出页面格式

`svc-interface-analyze` 的调用树格式规范：目录、数据结构、渲染器行为。生成或修改 `testcase/analysis/` 下的调用树时读这份。

`example.json` 是一份填满真实内容的接口数据，包含 DB、RPC、缓存、循环、分支各类节点和待确认标记。拿不准某个字段怎么填就照它抄。`example.html` 只是壳，和模板一样，由常驻服务挂在 `/example.html`。

## 目录与资产

```
<服务>/testcase/analysis/
  <接口名>/
    <ts>.json                       # 调用树：改内容只动这个，提交
    <ts>.calltree.json              # 骨架，不提交
```

HTML、css、js 在 skill 里，一份调用链页给所有入口用。数据从参考版本或 `assets/interface-page.template.json` 拷成 `<ts>.json` 再填。

打开：`<本skill目录>/assets/serve.sh <这份 JSON 的绝对路径>`。没在跑就启动，已经在跑就复用。地址是 `http://127.0.0.1:8766/view?json=<绝对路径>`；打开 `http://127.0.0.1:8766/` 也可以直接把 `.json` 文件拖到页面上，自动跳转到 `/view?json=<绝对路径>`。清单是同一服务的 `/list?dir=<analysis 目录>`。`serve.py` 变了，再跑一次会重启；`serve.sh stop` 停掉。

渲染器读 `?json=`。没有这个参数时，才退回与 HTML 同名的 `.json`，或 `#mm-app` 的 `data-src`。旧页若还内联了 `#mm-data` 也能打开。新页把数据放在 JSON 文件里。

页头是从 `analysis` 到当前文件的路径，点上一级目录打开 `/list?dir=`。该目录有 `interfaces.json`（或带 `interfaces` 数组的 `index.json`）就是接口清单，都没有就列出同目录带 `tree` 的解读 JSON。`src` 仍是 `path:line` 文本。

## 接口页

HTML 是壳。页头、图例、画布、右侧详情、术语表全由 `mindmap.js` 读 JSON 生成。改内容只动 JSON。

```json
{
  "meta": { "service": "", "interface": "", "entryType": "rpc", "proto": "", "impl": "", "branch": "", "commit": "", "dirty": true, "openDepth": 2 },
  "tree": { },
  "terms": [ { "term": "", "meaning": "" } ]
}
```

`meta.branch`、`meta.commit` 记分析时的分支和 40 位完整 hash，`meta.interface` 是入口名，`meta.entryType` 是 `rpc`、`http`、`cron` 之一。分析时被测服务有未提交改动就写 `meta.dirty: true`，没有就不写这个字段。`calltree.py changed` 靠 `meta.commit` 判断参考版本还能不能直接用。返回清单由打开时的 JSON 路径决定，不必再写 `meta.index`。旧 JSON 里留着该字段也不影响跳转。

### 节点字段

`t` 是唯一必填项。

| 字段 | 用途 |
| --- | --- |
| `t` | 标题，写成 `动作 \| 落点 \| 依赖`，用 `\|` 分隔 |
| `type` | 节点类型，见下表，缺省 `step` |
| `src` | 代码位置 `path:line`，路径相对仓库根 |
| `log` | 这一步打的日志：格式串原文和 `文件:行`；没有日志写 `无`。分支、`db`、`rpc`、`cache` 节点必填 |
| `note` | 我的解读：这一步在干什么、为什么。白话、该换行换行，见下方。普通 `step` 节点一句话或留空 |
| `code` | 关键代码，三到五行 |
| `sql` | SQL 全文 |
| `req` | 请求参数结构 |
| `rsp` | 响应关键字段 |
| `sample` | 真实样例：日志摘录、RPC 响应、DB 结果，人工在页面上补 |
| `warn` | 代码注释与代码行为不一致，写下代码的真实行为 |
| `todo` | 待确认；知识库和代码冲突时写清两边分别说了什么 |
| `kids` | 子节点数组 |
| `fold` | `true` 时默认折叠，用在内容密集的长分支上 |
| `open` | `true` 时默认展开，用在必看的主干上 |

标题三段的渲染效果：第一段加粗，第二段红色等宽，第三段换行显示成灰色小字。三段缺后两段可以，顺序别换。

标题前缀标节点的性质，写在第一段开头：「附注 · 」是死配置、开关注释、背景说明；「见 <接口名> 页 · 」指向另一份页面里展开过的方法。页面保存时只保留上表里的字段，节点性质要写进标题，不另加字段。

`kids` 排列按代码真实执行流，不按声明顺序或功能分组。复杂方法的顺序规则见 [SKILL.md](SKILL.md)「读代码的规则」。

### 解读怎么写

`note` 给人扫的，像跟刚接手的同事口述。渲染器会保留换行。

- 一段一个意思。JSON 里用 `\n` 换行，段落之间空一行（`\n\n`）。
- 白话。字段名、函数名可以留，周围用「走哪条路」「业务挂了」这种说法。
- 签名、版本 hash、结构体原文放 `req`/`code`/`src`，别堆进 `note`。

反例（一坨）：

```
rpc GetAccessToken(GetAccessTokenReq) returns(GetAccessTokenRsp)。先查进程内缓存再查 Redis wx:token:{wx_appid}，都没有或过期就拿 wx:token:lock:{wx_appid} 锁调 /cgi-bin/stable_token。t_wx_app 里 f_status 不是启用返回 4003003，secret 解不开返回 5003001。
```

正例：

```
给业务后台发某个小程序的 access_token。

先看进程内缓存，再看 Redis 的 wx:token:{wx_appid}，都没有或过期了才去微信换。

换之前要拿 wx:token:lock:{wx_appid} 这把锁，多个实例同时来只换一次。

小程序停用了回 4003003，secret 解不开回 5003001。
```

### 节点类型

`root` 中心本身（接口分析时就是接口），`proto` 协议，`entry` 入口方法，`section` 章节，`quote` 原文，`branch` 条件分支，`db` 数据库访问，`rpc` 调下游服务，`cache` 读写缓存，`loop` 循环，`build` 数据组装，`step` 普通步骤。

类型只影响左侧色条和图例，选不准就用 `step`。

### 渲染器行为

`openDepth` 控制初始展开层数，默认 2，也就是打开先看到协议和入口方法下面第一级。

`log` 是 `无` 的节点右上角显示灰色「∅」点，有 `code`/`sql`/`req`/`rsp`/`sample` 的显示绿色「证」点，有 `warn` 的显示橙色「!」点，有 `todo` 的显示红色「?」点，同时有就按这个顺序并排。折叠状态的节点右侧圆点显示 `+`，鼠标悬停提示底下藏了多少个末端节点。画布按住可拖动平移。左下角 − / 百分比 / + 可缩放，点百分比回到 100%；Command 加滚轮同样缩放，锚在指针位置，范围 25%～250%。方向键切换节点：上一个/下一个兄弟，左到父节点，右到第一个子节点；折叠着就先展开再进去。输入框里方向键仍是改文字。左右中间那根竖线可拖动，改详情栏宽度。

点节点看详情。有内容的字段点文字就能改，改完点外面收回去。空着的字段不占地方，用「＋ 字段」补。「＋ 子节点」加下一跳，右上角 ⋯ 里上移下移删除。改完自动 PUT 写回 `?json=` 那份文件，必须用 `serve.sh`（或 `analyze_server`）打开。页头会闪「已保存」。

## 一个坑

JSON 文件本身 pretty-print（结构换行、缩进）没问题。字符串值里的换行必须写成 `\n`，不能在引号里直接断行。SQL 和 proto 结构容易踩这条，写完自己扫一遍能不能 `JSON.parse`。
