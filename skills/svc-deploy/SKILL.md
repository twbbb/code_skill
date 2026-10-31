---
name: svc-deploy
description: 把 Go 服务或小程序/小游戏接入发布台（fabutai）。新服务要上线、小程序要第一次上传微信、旧发布脚本迁过来时使用。已登记服务的查看、改配置、发布、重启、回滚走 fabutai skill。
---

# 接入发布台

发布台目录是 code_knowledge 的 `02_project/dev_tool/deploy`（本机在 `~/Documents/workspaceai_my/code_knowledge/02_project/dev_tool/deploy`）。规则以那里的文档为准，本 skill 只给接入的顺序和文档里没写的坑。用到 MCP 的地方（连上、`allocate_ports`、`list_services`、发布）都按 fabutai skill 做；它不在时读 code_knowledge 的 `01_skill/base_skill/skills/fabutai/SKILL.md`。

- `docs/发布声明.md`：服务目录结构、`deploy.yaml` 字段、变量、探活、加载时的校验、发布台之外还要手动做的事。
- `GLOSSARY.md`：术语。下文的发布声明、线上配置、本机配置、密钥表、探活、前置检查都按它的意思用。

Go 服务（`kind: go`）走「接入一个服务」。小程序和小游戏（`kind: mini`）走「接入一个小程序」。静态站还在清单的 `projects` / `others` 旧写法里。

## 接入一个服务

先读 `docs/发布声明.md`，再按顺序做，每步对着「完成」核一遍。

1. **代码按节点的方式起得来。** 节点上 systemd 在节点目录里直接执行二进制、不带参数，给两个环境变量：`CONFIG_FILE=<节点目录>/app.yaml`、`NODE_NAME=<节点名>`；`trpc_go.yaml` 从工作目录读。所以业务配置的路径从 `CONFIG_FILE` 取。本机跑法写进 `main.go` 的注释：`CONFIG_FILE=config/local/app.yaml go run . -conf config/local/trpc_go.yaml`。
   完成：本机用这条命令能起来。
2. **探活有得打。** 默认 `probe: ping`，按线上 `trpc_go.yaml` 里 `server.service` 第一项的协议：trpc 服务要实现 `Ping`，http 服务任何响应都算通。两样都不合适时，在 `deploy.yaml` 写一条 `probe` 命令。
   完成：说得出这个服务的探活走哪条。
3. **定节点。** 机器从清单 `machines` 里选，地域要对上。端口用 MCP 的 `allocate_ports`（给 `machine` 和节点数）取：`ports` 是各节点的 `port`，`metrics_ports` 写进节点的 `vars.metrics_port`。返回里有 `listen_error` 时说明没连上机器、只按清单分，要告诉用户。
   完成：端口来自 `allocate_ports`，节点名全局唯一。
4. **建 `config/`。** 原来的配置用 `git mv` 移进 `config/local/`，保留历史。`config/server/<地域>/` 从本机配置复制后改：端口换 `${node_port}`，监控端口换 `${node_metrics_port}`，本机地址换线上内网地址，密码、token、DSN 换成变量。变量名是 `<地域>_<服务>_<用途>`，几个服务共用的（同一个 Redis）省掉服务名，如 `gz_redis_password`；先在密钥表里找有没有现成的键。服务的 `.gitignore` 只忽略根目录的文件（写 `/app.yaml`），`config/` 下的才进得了 git。
   完成：线上配置里没有明文密钥；`git check-ignore -v config/server/<地域>/app.yaml` 没有输出。
5. **写密钥表。** 新变量加进发布台的 `secrets.yaml`（权限 600，不提交），值从线上节点现有配置或云控制台取；模板里带引号的地方值不带引号。操作密钥表时只按键名读写，输出里只出现键名。
   完成：线上配置里每个变量在密钥表里都有键。
6. **写 `deploy.yaml`。** 照 `docs/发布声明.md`。迁移已经在线上跑的服务时，`unit`、`dir`、`bin` 写成线上现有的值（默认是节点名、`/home/ubuntu/apps/<节点名>`、服务名），否则会起出第二份进程抢端口。发布前会跑 `go test`（`testcase` 下的集成用例不跑），过不了先修；确实修不了才写 `env: { SKIP_TEST: "1" }`，上面加一行注释说为什么。
   完成：在服务目录里 `go test` 能过，或者已写 `SKIP_TEST` 并注释了原因。
7. **登记到清单。** 发布台 `manifest.yaml` 的 `services` 加上服务目录（相对清单）；地域有整套发布顺序的，按依赖插进 `regions[].order`，被调方在前。迁移来的服务把 `projects` 里的旧条目删掉。
8. **验证加载。** 清单只在发布台启动时读，改完要重启发布台（`./script/install-macos.sh`）。用 `list_services`（或页面）看这个服务，再用 `get_status` 看各节点；新节点还没发过时，状态里没有进程是正常的。
   完成：`list_services` 里这个服务没有 `error`，`can_deploy` 为 true。
9. **发布台之外的事。** 见 `docs/发布声明.md` 的「还要手动做的」：挂在网关后面的服务，要在 `db_gateway.t_gw_service` / `t_gw_method` 里加行，写成项目 `sql/` 下的脚本；http 入口要改 nginx upstream；跨机器调用要在轻量服务器防火墙放行内网入站；用新机器要先配好 ssh 别名和免密 sudo。这些做完再发，记进第一次发布的前置检查。
10. **第一次发布。** 按 fabutai skill 的「改线上」做，第 9 步做完的事写进 `checklist`。
11. **收尾。** 删掉旧的发布脚本和旧配置，在整个工作区搜一遍引用它们的地方，一起改掉。

## 接入一个小程序

先读 `docs/发布声明.md` 的「小程序」。云函数不接。

1. **项目根能被微信开发者工具打开。** 有 `project.config.json`，`compileType` 是 `miniprogram` 或 `game`，`appid` 已填。
   完成：说得出 appid。
2. **版本文件是上次上传成功的号。** 默认 `script/version`，内容是 x.y.z。还没上传过就写 `0.0.0`，第一次发布变成 `0.0.1`。微信上已经传过的，先写成上次成功的号。
   完成：文件内容是 x.y.z。
3. **写 `config/deploy/deploy.yaml`。** `kind: mini`，`region: wx`。上传前要测试或构建的，命令写进 `build`，构建后必须在的文件写进 `expect`。不写节点，不建 `config/local` 和 `config/server`。
   完成：`build` 里的命令在服务目录里能跑过；没有 `build` 就是源码直接上传。
4. **登记到清单 `services`。** 不放进 `regions.order`。
5. **验证加载。** 同 Go 服务的第 8 步。
   完成：`list_services` 里这个服务没有 `error`，`can_deploy` 为 true，`can_config` 为 false。

第一次上传按 fabutai skill 的「改线上」做；上传用本机微信开发者工具，要已登录。旧的 `deploy_mini.sh` 留到第一次用发布台上传成功后再删。
