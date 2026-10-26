---
name: svc-sql2gorm
description: 根据sql生成gorm的go代码
---

## 步骤
1. **跑 sql2gorm**。`-r` 是 model 文件的绝对路径，一次一张表。SQL 来源只给一种。

   从语句：

   ```bash
   sql2gorm -sql='CREATE TABLE t_user (id bigint NOT NULL, name varchar(30) NOT NULL);' -r /abs/path/model/t_user.go
   ```

   从文件：

   ```bash
   sql2gorm -f schema.sql -r /abs/path/model/t_user.go
   ```

   从库。库名写在 DSN 里，`-db-table` 只写表名：

   ```bash
   sql2gorm -db-dsn='user:pass@/dbname?charset=utf8mb4' -db-table=t_user -r /abs/path/model/t_user.go
   ```


2. 有问题就 `sql2gorm -h`。