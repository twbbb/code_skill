# 本地端口和 Redis db

本机的 MySQL、Redis 是几个服务共用的，各服务的测试进程端口和 Redis db 按这张表分，互不冲突，几个服务可以同时测。新服务接入时在这里加一行，再写进它的 `env.yaml`。

| 服务 | 目录 | 端口段 | Redis db | MySQL 库 |
|---|---|---|---|---|
| gateway | `common_server/gateway` | 18101～18199 | 12 | `db_gateway` |
| auth | `common_server/auth` | 18201～18299 | 13 | `db_auth` |
| wxtoken | `common_server/wxtoken` | 18301～18399 | 14 | `db_wxtoken` |

- 端口段里从小到大分给 `env.yaml` 的 `procs`，默认进程用第一个。一个进程要多个端口（如一个 trpc 端口加一个 HTTP 端口）时，第二个端口写进进程的 `vars`，也从本段里取。
- 生产端口（8080、8081、8082）留给本机开发直接起的进程，测试进程不用。
- 新服务从 18401 起，每个服务占一段 100 个，Redis db 接着往后分。
