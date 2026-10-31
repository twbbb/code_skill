---
name: svc-deploy
description: 接入发布台：把新 Go 服务、小程序/小游戏，或旧发布脚本发的服务登记进发布台（fabutai）。已登记服务的查看和发布用 fabutai skill。
---

# 接入发布台

发布台目录是 code_knowledge 的 `02_project/dev_tool/deploy`（本机在 `~/Documents/workspaceai_my/code_knowledge/02_project/dev_tool/deploy`）。规则以那里的文档为准，本 skill 只给接入的顺序和文档里没写的坑。调发布台 MCP 时按 fabutai skill 做；它没加载时读 code_knowledge 的 `01_skill/base_skill/skills/fabutai/SKILL.md`。

- `docs/发布声明.md`：服务目录结构、`deploy.yaml` 字段、变量、探活、加载时的校验、发布台之外还要手动做的事。
- `GLOSSARY.md`：术语。下文的发布声明、线上配置、本机配置、密钥表、探活、前置检查都按它的意思用。

Go 服务（`kind: go`）走「接入一个服务」。小程序和小游戏（`kind: mini`）走「接入一个小程序」。静态站还在库的旧格式项目表里。

登记、密钥表在本机 MySQL `db_fabutai`。写库用 `mysql -uroot --default-character-set=utf8mb4 db_fabutai`。服务目录相对发布台根目录（`deploy/`），例如 `../../common_server/auth`。

## 接入一个服务

先读 `docs/发布声明.md`，再按顺序做，每步对着「完成」核一遍。

1. **代码按节点的方式起得来。** 节点上 systemd 在节点目录里直接执行二进制、不带参数，给两个环境变量：`CONFIG_FILE=<节点目录>/app.yaml`、`NODE_NAME=<节点名>`；`trpc_go.yaml` 从工作目录读。所以业务配置的路径从 `CONFIG_FILE` 取。本机跑法写进 `main.go` 的注释：`CONFIG_FILE=config/local/app.yaml go run . -conf config/local/trpc_go.yaml`。
   完成：本机用这条命令能起来。接入发布台后，首页和详情会出现「本机启动」，MCP 用 `start_local`。
2. **探活有得打。** 默认 `probe: ping`，按线上 `trpc_go.yaml` 里 `server.service` 第一项的协议：trpc 服务要实现 `Ping`，http 服务任何响应都算通。两样都不合适时，在 `deploy.yaml` 写一条 `probe` 命令。
   完成：线上 `trpc_go.yaml` 第一项是 http，或是 trpc 且服务实现了 `Ping`，或 `deploy.yaml` 里写了 `probe` 命令。
3. **定节点。** 机器从库的 `t_machine` 里选，地域要对上。端口用 MCP 的 `allocate_ports`（给 `machine` 和节点数）取：`ports` 是各节点的 `port`，`metrics_ports` 写进节点的 `vars.metrics_port`。返回里有 `listen_error` 时说明没连上机器、只按登记分，要告诉用户。
   完成：每个节点的 `port` 和 `metrics_port` 都来自这次 `allocate_ports` 的返回，节点名和已有服务的都不重（`search_service` 拿节点名对一下）。
4. **建 `config/`。** 原来的配置用 `git mv` 移进 `config/local/`，保留历史。`config/server/<地域>/` 从本机配置复制后改：端口换 `${node_port}`，监控端口换 `${node_metrics_port}`，本机地址换线上内网地址，密码、token、DSN 换成变量。变量名是 `<地域>_<服务>_<用途>`，几个服务共用的（同一个 Redis）省掉服务名，如 `gz_redis_password`；先在密钥表里找有没有现成的键。服务的 `.gitignore` 只忽略根目录的文件（写 `/app.yaml`），`config/` 下的才进得了 git。
   完成：线上配置里没有明文密钥；`git check-ignore -v config/server/<地域>/app.yaml` 没有输出。
5. **写密钥表。** 新变量加进 `t_secret`（`f_name`、`f_value`），值从线上节点现有配置或云控制台取；模板里带引号的地方值不带引号。操作密钥表时只按键名读写，输出里只出现键名。
   服务要一个新的 MySQL 库时，用 `scripts/create_cdb_db.py` 在腾讯云实例上建库、建账号，DSN 直接写进密钥表：`python3 scripts/create_cdb_db.py --instance <实例ID> --db db_<服务> --secret <地域>_<服务>_mysql_dsn`。库名以 `db_` 开头，账号默认是库名去掉 `db_`，只给这个库的权限。账号已经存在时脚本不改密码、不写密钥表。建表用服务自己 `sql/` 下的脚本另外执行。
   完成：线上配置里每个变量在密钥表里都有键。
6. **写 `deploy.yaml`。** 照 `docs/发布声明.md`。迁移已经在线上跑的服务时，`unit`、`dir`、`bin` 写成线上现有的值（默认是节点名、`/home/ubuntu/apps/<节点名>`、服务名），否则会起出第二份进程抢端口。发布前会跑 `go test`（`testcase` 下的集成用例不跑），过不了先修；确实修不了才写 `env: { SKIP_TEST: "1" }`，上面加一行注释说为什么。
   完成：在服务目录里 `go test` 能过，或者已写 `SKIP_TEST` 并注释了原因。
7. **登记到清单。** `t_service_dir` 加上服务目录；地域有整套发布顺序的，按依赖插进 `t_region_order`（`f_region`、`f_seq`、`f_service_key`），被调方在前。页面要归到某一块的，加 `t_group_service`。迁移来的服务把 `t_legacy_project` / `t_legacy_service` / `t_legacy_node` 里的旧条目删掉。
   完成：`t_service_dir` 里有这个服务目录；它在每个整套发布顺序里都排在它调用的服务之后；旧格式表里没有它。
8. **验证加载。** 在发布台目录跑 `./script/install-macos.sh` 重启发布台，登记才会重读；Cursor 里拿到的工具不对时，在 MCP 设置里重连 fabutai。用 `search_service` 找到这个服务，再用 `get_service`、`get_status` 看各节点；新节点还没发过时，状态里没有进程是正常的。
   完成：`search_service` 能 UNIQUE 到这个服务，没有 `error`，`get_service` 里 `can_deploy` 为 true。
9. **发布台之外的事。** 见 `docs/发布声明.md` 的「还要手动做的」：挂在网关后面的服务，要在 `db_gateway.t_gw_service` / `t_gw_method` 里加行，写成项目 `sql/` 下的脚本；http 入口要改 nginx upstream；跨机器调用要在轻量服务器防火墙放行内网入站；用新机器要先配好 ssh 别名和免密 sudo。
   完成：上面每一项都标了「已做」或「不涉及」。
10. **第一次发布。** 按 fabutai skill 的「改线上」做，第 9 步标「已做」的写进 `checklist`。
11. **收尾。** 删掉旧的发布脚本和旧配置，在整个工作区搜一遍引用它们的地方，一起改掉。
   完成：工作区里搜不到旧脚本名和旧配置路径。

## 接入一个小程序

先读 `docs/发布声明.md` 的「小程序」。云函数不接。

1. **项目根能被微信开发者工具打开。** 有 `project.config.json`，`compileType` 是 `miniprogram` 或 `game`，`appid` 已填。
   完成：说得出 appid。
2. **版本文件是上次上传成功的号。** 默认 `script/version`，内容是 x.y.z。还没上传过就写 `0.0.0`，第一次发布变成 `0.0.1`。微信上已经传过的，先写成上次成功的号。
   完成：文件内容是 x.y.z。
3. **写 `config/deploy/deploy.yaml`。** `kind: mini`，`region: wx`。上传前要测试或构建的，命令写进 `build`，构建后必须在的文件写进 `expect`。不写节点，不建 `config/local` 和 `config/server`。
   完成：`build` 里的命令在服务目录里能跑过；没有 `build` 就是源码直接上传。
4. **登记到 `t_service_dir`。** 不放进 `t_region_order`。
5. **验证加载。** 同 Go 服务的第 8 步。
   完成：`search_service` 能 UNIQUE 到这个服务，没有 `error`，`get_service` 里 `can_deploy` 为 true，`can_config` 为 false。

第一次上传按 fabutai skill 的「改线上」做。旧的 `deploy_mini.sh` 留到第一次用发布台上传成功后再删。
