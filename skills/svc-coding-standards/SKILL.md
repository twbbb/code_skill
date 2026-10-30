---
name: svc-coding-standards
description: Go 服务编码规范，分架构、编码、数据库三块。写代码、改代码、审查代码之前先读。
---

# Go 服务编码规范

- 改代码前，从代码所在目录往上逐级读到仓库根目录，每层有 `AGENTS.md` 就读。
- 项目里的 `AGENTS.md`、`CODEBUDDY.md` 和本规范冲突时，按项目的来。
- 写完对照下面每一节过一遍，每条要么满足，要么能说出为什么不适用。

## 架构

- 对接外部的代码都放在 `repo/` 下，包括数据库、微信等第三方接口、其他服务的 RPC。
- `repo/` 下每个包用 `api.go` 定义接口，用 `api_impl.go` 写实现。
- 服务的 `trpc_go.yaml` 在 `server.filter` 里挂上 `logContext` 和 `debuglog`，实现放在服务的 `filters/` 目录，样板见 `mathgame_server` 的 `server/filters/`。
- `logContext` 把网关透传的 requestId、userid 写进日志上下文。
- `debuglog` 打每个请求和响应，探活 Ping 跳过。

## 编码

- 变量、参数、接收者都用完整单词表意，比如 `writer`、`request`、`userID`，单字母名只留给循环下标。
- 逻辑写成具名函数或方法，函数体里的匿名函数只用在起协程的时候。
- 起协程用 `trpc.Go`，它会复制 ctx、加超时、兜住 panic。
- 枚举类型都用 `int`，0 留给「未知」，业务值从 1 开始。
- 处理枚举的 `switch` 都写 `default` 分支兜底。
- 返回的错误都取自 `entity/errcode/errcode.go`。
- 新错误先在该文件里加一个变量再用，调用方的错用 `clientErr`，服务自己的错用 `serverErr`。
- 接口出错时返回 `nil, err`，由框架统一转成错误响应。
- 接口成功时响应体的 `Code`、`Msg` 保持零值。
- 日志都用带 ctx 的方法，比如 `log.InfoContextf(ctx, ...)`、`log.ErrorContextf(ctx, ...)`。
- 日志正文只写业务信息，userId、requestId、代码行由 `logContext` 和日志框架自动带上。

## 数据库

- 表的 GORM model 用 skill `svc-sql2gorm` 从建表语句生成，放在 `entity/model/` 下。
- 一张表一个 model 文件，文件名就是表名，比如 `t_user.go`。
- 枚举字段（如状态）默认值给 1，注释写全每个值的含义，例如 `f_status tinyint NOT NULL DEFAULT 1 COMMENT '状态:1=等待接受,2=已接受,3=已拒绝,4=已过期,5=已取消'`。
- varchar 字段都写 `NOT NULL DEFAULT ''`，例如 `f_inviter_dataid varchar(64) NOT NULL DEFAULT '' COMMENT '邀请方dataId'`。
