# cases.yaml

测试工作区的执行清单，`scripts/run_case.py` 读。每条用例一项，键是用例序号（拆段用例是 `02a`、`02b`），和用例文档、`data/NN.*`、`Test_NN_*`、证据文件 `result/<轮>/NN_<method>.md` 共用。提交。

```yaml
# <服务> 本地用例的执行配置，run_case.py 读。用例说明见 <服务>.md。
# 每条用例只用自己的测试标识（wx_lt_ 开头），数据脚本开头先清自己的行和 key。

render:                         # 可选：自定义占位符 ${名字:参数}，{arg} 换成参数，{acc} 换成参数对应的测试标识，取标准输出
  secret: "printf 'sec-%s\n' '{acc}' | localstart/bin/encsecret -conf localstart/log/wx1/app.yaml -ver 1"

accounts:                       # 测试标识，角色名对应用例文档「测试数据」
  A01: wx_lt_01
  H06a: wx_lt_06_near           # Redis 里还剩 5 分钟

sql:                            # 多条用例共用的查询，pre/post 里按名字引用
  app: "SELECT f_wx_appid,f_status FROM t_wx_app WHERE f_wx_appid LIKE 'wx_lt_%' ORDER BY f_wx_appid"

flows:                          # 多条用例共用的流程节点
  renew: ["换新=access_token 已换新"]
  norenew: ["不换新=!access_token 已换新"]
  task: ["定时任务开始=runDistributProcess start", "定时任务结束=定时刷新完成"]

cases:
  "01":
    mark: "@gen 用例01"         # 生成标记，手工改过改成 @manual
    method: GetAccessToken      # 证据文件名用
    title: Redis 里没有，当场换新
    proc: wx1                   # 取日志的进程，可以是列表；兄弟服务写 auth:au1
    pre:                        # 前置核对：数据脚本之后、go test 之前
      - {note: 行, sql: "SELECT f_wx_appid,f_status FROM t_wx_app WHERE f_wx_appid='${A01}'"}
      - {note: Redis, redis: "EXISTS wx:token:${A01}"}
    post:                       # 原始输出：go test 之后
      - {note: Redis 里的 token, redis: "GET wx:token:${A01}"}
      - {note: 全部测试行, sql: app}
    flow: [renew, "调微信=stable_token 成功"]
  "06":
    mark: "@gen 用例06"
    method: RefreshAccessToken
    title: 换快过期的、不动还新的
    proc: wxt1
    also: 'RefreshAccessToken_\d+'   # 正则：时段内匹配它的日志行也算本条（定时任务的 requestId 不是本条的）
    after: ["localstart/startserver.sh stop wxt1"]
    flow: [task]
  "13":
    mark: "@gen 用例13"
    method: GetAccessToken
    title: 不需要数据的用例
    proc: wx1
    data: false                 # 没有 data/13.*
    abandoned: true             # 已废弃，./run all 跳过
```

## 字段

| 字段 | 说明 |
|---|---|
| `mark` | `@gen 用例NN` 或 `@manual`，见 SKILL.md「生成标记」 |
| `method`、`title` | 证据文件名和标题 |
| `proc` | 取日志的进程；多个进程（多实例、兄弟服务）写列表，日志行前会标 `[进程]` |
| `data` | 默认 `true`，要有 `data/NN.sql` 或 `data/NN.redis` |
| `before`、`after` | bash 命令列表，cwd 是测试工作区。`before` 在数据脚本之后，`after` 不管成败都执行 |
| `pre`、`post` | 每项 `{note, sql}` 或 `{note, redis}`；`sql` 可以写 `sql` 里的名字 |
| `flow` | `flows` 里的名字，或 `"节点名=日志关键字"`，关键字前加 `!` 表示预期不出现；`"a && b"` 表示同一行里 a、b 都要有。替身命中不用写，按本条写过的替身自动加 |
| `also` | 正则，时段内匹配它的行也算本条日志 |
| `abandoned` | 已废弃 |

## 占位符

cases.yaml 和 `data/` 里都能用：`${A01}` 测试标识；`${now:+300}` 当前 unix 秒 +300；`${ms:-60}` 当前 unix 毫秒 -60 秒；`${名字:参数}` 是 `render` 里定义的命令。

## 数据脚本

`data/NN.sql` 在 `env.yaml` 的 `mysql.db` 里执行，`data/NN.redis` 每行一条 redis-cli 命令，在 `redis.db` 里执行，`#` 开头是注释。第一行写 `-- @gen 用例NN` 或 `# @gen 用例NN`。开头先清：按本条的测试标识删每张会读写的表、`DEL` 相关 key 和锁 key；再写入前置状态，时间一律用占位符或 `UNIX_TIMESTAMP()` 这类相对表达式。单独执行、重复执行都得到同样的前置状态。
