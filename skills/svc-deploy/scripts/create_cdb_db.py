#!/usr/bin/env python3
"""在腾讯云 MySQL（CDB）实例上给一个服务建库和账号，DSN 写进发布台密钥表。

做四件事，已经有的跳过：
1. 建库（utf8mb4）。库名必须以 db_ 开头。
2. 建账号，密码随机生成，不打印。
3. 给账号这个库的全部权限，不给全局权限。
4. 把内网 DSN 写进 db_fabutai.t_secret 的 --secret 键。DSN 的地址取实例的内网地址。

账号已经存在时不改密码，也不写密钥表：密码取不回来，要轮换就去控制台重置后自己写。
腾讯云密钥读环境变量 TXY_SECRETID / TXY_SECRETKEY。

用法：
  create_cdb_db.py --instance cdb-8mqqif7n --db db_babygrowth --secret gz_baby_mysql_dsn
建表另用服务自己的 sql/ 脚本，经实例外网地址或在同 VPC 的机器上执行。
"""
import argparse
import os
import re
import secrets
import string
import subprocess
import sys
import time

from tencentcloud.cdb.v20170320 import cdb_client, models
from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile

DB_PATTERN = re.compile(r"^db_[a-z0-9_]{1,61}$")
USER_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,31}$")

# 库内权限全给，GRANT 出来是 ALL PRIVILEGES ON `库`.*，没有 CREATE USER、SHOW DATABASES 这些全局权限。
DB_PRIVILEGES = [
    "SELECT", "INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "REFERENCES", "INDEX", "ALTER",
    "CREATE TEMPORARY TABLES", "LOCK TABLES", "EXECUTE", "CREATE VIEW", "SHOW VIEW",
    "CREATE ROUTINE", "ALTER ROUTINE", "EVENT", "TRIGGER",
]


def die(msg):
    print("error: " + msg, file=sys.stderr)
    sys.exit(1)


def new_client(region):
    sid, skey = os.environ.get("TXY_SECRETID"), os.environ.get("TXY_SECRETKEY")
    if not sid or not skey:
        die("环境变量 TXY_SECRETID / TXY_SECRETKEY 没设")
    http = HttpProfile()
    http.endpoint = "cdb.tencentcloudapi.com"
    profile = ClientProfile()
    profile.httpProfile = http
    return cdb_client.CdbClient(credential.Credential(sid, skey), region, profile)


def wait_async(client, async_id, label):
    if not async_id:
        return
    for _ in range(60):
        req = models.DescribeAsyncRequestInfoRequest()
        req.AsyncRequestId = async_id
        rsp = client.DescribeAsyncRequestInfo(req)
        if rsp.Status == "SUCCESS":
            print(f"  {label}：完成")
            return
        if rsp.Status in ("FAILED", "KILLED", "REMOVED"):
            die(f"{label}失败：{rsp.Status} {rsp.Info or ''}")
        time.sleep(3)
    die(f"{label}超时，异步任务 {async_id}")


def internal_addr(client, instance):
    req = models.DescribeDBInstancesRequest()
    req.InstanceIds = [instance]
    items = client.DescribeDBInstances(req).Items or []
    if not items:
        die(f"找不到实例 {instance}，检查 --region")
    return f"{items[0].Vip}:{items[0].Vport}"


def list_dbs(client, instance):
    req = models.DescribeDatabasesRequest()
    req.InstanceId = instance
    req.Limit = 5000
    return list(client.DescribeDatabases(req).Items or [])


def has_account(client, instance, user, host):
    req = models.DescribeAccountsRequest()
    req.InstanceId = instance
    req.Limit = 100
    req.AccountRegexp = f"^{user}$"
    return any(a.User == user and a.Host == host for a in (client.DescribeAccounts(req).Items or []))


def new_password():
    alphabet = string.ascii_letters + string.digits
    while True:
        pwd = "".join(secrets.choice(alphabet) for _ in range(24))
        if any(c.islower() for c in pwd) and any(c.isupper() for c in pwd) and any(c.isdigit() for c in pwd):
            return pwd


def write_secret(name, value):
    # 值走标准输入里的 SQL，不进命令行参数，ps 看不到。
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    sql = (f"INSERT INTO t_secret (f_name, f_value) VALUES ('{name}', '{escaped}') "
           f"ON DUPLICATE KEY UPDATE f_value = VALUES(f_value);")
    subprocess.run(["mysql", "-uroot", "--default-character-set=utf8mb4", "db_fabutai"],
                   input=sql, text=True, check=True)


def main():
    ap = argparse.ArgumentParser(description="腾讯云 CDB 建库建账号，DSN 写进发布台密钥表")
    ap.add_argument("--instance", required=True, help="实例 ID，例如 cdb-8mqqif7n")
    ap.add_argument("--region", default="ap-guangzhou", help="实例地域，默认 ap-guangzhou")
    ap.add_argument("--db", required=True, help="库名，必须以 db_ 开头，例如 db_babygrowth")
    ap.add_argument("--user", help="账号名，默认库名去掉 db_")
    ap.add_argument("--host", default="%", help="账号的主机，默认 %%")
    ap.add_argument("--secret", required=True, help="密钥表键名，<地域>_<服务>_mysql_dsn，例如 gz_baby_mysql_dsn")
    ap.add_argument("--dsn-params", default="charset=utf8mb4&parseTime=True&loc=Asia%2FShanghai",
                    help="DSN 问号后的参数，默认按北京时间读写")
    args = ap.parse_args()

    if not DB_PATTERN.match(args.db):
        die(f"库名 {args.db} 不合规：要以 db_ 开头，只用小写字母、数字、下划线")
    user = args.user or args.db[len("db_"):]
    if not USER_PATTERN.match(user):
        die(f"账号名 {user} 不合规：小写字母开头，只用小写字母、数字、下划线，最长 32")

    client = new_client(args.region)
    addr = internal_addr(client, args.instance)
    print(f"实例 {args.instance}，内网 {addr}")

    if args.db in list_dbs(client, args.instance):
        print(f"库 {args.db} 已存在，跳过")
    else:
        req = models.CreateDatabaseRequest()
        req.InstanceId = args.instance
        req.DBName = args.db
        req.CharacterSetName = "utf8mb4"
        client.CreateDatabase(req)
        print(f"库 {args.db} 已建")

    account = models.Account()
    account.User = user
    account.Host = args.host
    password = None
    if has_account(client, args.instance, user, args.host):
        print(f"账号 {user}@{args.host} 已存在，不改密码，不写密钥表")
    else:
        password = new_password()
        req = models.CreateAccountsRequest()
        req.InstanceId = args.instance
        req.Accounts = [account]
        req.Password = password
        req.Description = f"{args.db} 业务账号"
        wait_async(client, client.CreateAccounts(req).AsyncRequestId, f"建账号 {user}@{args.host}")

    priv = models.DatabasePrivilege()
    priv.Database = args.db
    priv.Privileges = DB_PRIVILEGES
    req = models.ModifyAccountPrivilegesRequest()
    req.InstanceId = args.instance
    req.Accounts = [account]
    req.DatabasePrivileges = [priv]
    req.ModifyAction = "grant"
    wait_async(client, client.ModifyAccountPrivileges(req).AsyncRequestId, f"授权 {args.db}")

    if password:
        write_secret(args.secret, f"{user}:{password}@tcp({addr})/{args.db}?{args.dsn_params}")
        print(f"密钥表已写 {args.secret}")


if __name__ == "__main__":
    main()
