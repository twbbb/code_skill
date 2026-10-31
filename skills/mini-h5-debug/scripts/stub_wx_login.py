#!/usr/bin/env python3
"""给本机 wxtoken 写一份 jscode2session 替身，让 H5 里固定的 wx.login code 换出固定 openid。

做两件事：
1. 在 wxtoken 本地配置 rpcProxyArg.localFilePath 指向的目录里写替身文件，文件名和 rpcproxy 的算法一致。
2. 往本机 db_wxtoken.t_wx_app 写这个 appid 的测试 secret（明文 sec-<appid>，按版本 1 主密钥加密），
   f_refresh_token=0，不去真实微信刷 access_token。替身 URL 里的 secret 就是这个明文。

用法：
  stub_wx_login.py --common-server <common_server 目录> --appid wx123 --code local-h5 --openid o-local-h5
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from urllib.parse import urlencode

CODE_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


def die(msg):
    print("error: " + msg, file=sys.stderr)
    sys.exit(1)


def stub_dir(wxtoken_conf):
    with open(wxtoken_conf, encoding="utf-8") as conf_file:
        text = conf_file.read()
    if not re.search(r"^rpcProxyArg:\s*$", text, re.M):
        die(wxtoken_conf + " 里没有 rpcProxyArg，wxtoken 本地没开替身")
    match = re.search(r"^\s+localFilePath:\s*\"?([^\"\n]+)\"?\s*$", text, re.M)
    if not match:
        die(wxtoken_conf + " 的 rpcProxyArg 没配 localFilePath")
    return match.group(1).strip()


def stub_file(directory, appid, code):
    # wxtoken 按参数名排序重新编码 query，md5 输入是「方法 host+path?query\n请求体」，GET 没有请求体
    query = urlencode(sorted({
        "appid": appid,
        "grant_type": "authorization_code",
        "js_code": code,
        "secret": "sec-" + appid,
    }.items()))
    key = hashlib.md5(("GET api.weixin.qq.com/sns/jscode2session?" + query + "\n").encode()).hexdigest()
    name = "http.api.weixin.qq.com.sns_jscode2session_" + key + ".json"
    return os.path.join(directory, name), "https://api.weixin.qq.com/sns/jscode2session?" + query


def encrypt_secret(wxtoken_dir, wxtoken_conf, plain):
    binary = os.path.join(wxtoken_dir, "testcase/localstart/bin/encsecret")
    if os.access(binary, os.X_OK):
        cmd = [binary, "-conf", wxtoken_conf, "-ver", "1"]
    else:
        cmd = ["go", "run", "./cmd/encsecret", "-conf", wxtoken_conf, "-ver", "1"]
    result = subprocess.run(cmd, cwd=wxtoken_dir, input=plain + "\n", capture_output=True, text=True)
    if result.returncode != 0:
        die("加密 secret 失败：" + result.stderr.strip())
    return result.stdout.strip().splitlines()[-1]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--common-server", required=True, help="common_server 仓库目录")
    parser.add_argument("--appid", required=True, help="小程序 appid，和 project.config.json 一致")
    parser.add_argument("--code", default="local-h5", help="wxa.setup 里 mock 的 wx.login code")
    parser.add_argument("--openid", default="", help="替身返回的 openid，默认 o-<code>")
    parser.add_argument("--name", default="", help="t_wx_app.f_name，默认用 appid")
    parser.add_argument("--mysql", default="mysql -h127.0.0.1 -uroot", help="连本机 MySQL 的命令")
    args = parser.parse_args()

    if not CODE_PATTERN.match(args.code):
        die("code 只用字母、数字、_、-，否则 query 编码和 Go 对不上")
    openid = args.openid or "o-" + args.code
    wxtoken_dir = os.path.join(os.path.abspath(args.common_server), "wxtoken")
    wxtoken_conf = os.path.join(wxtoken_dir, "config/local/app.yaml")
    if not os.path.isfile(wxtoken_conf):
        die("找不到 " + wxtoken_conf)

    path, url = stub_file(stub_dir(wxtoken_conf), args.appid, args.code)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    entry = {
        "req": {"method": "GET", "url": url},
        "rsp": {"header": {"Content-Type": "application/json"},
                "body": {"openid": openid, "session_key": "sk-" + args.code}},
    }
    with open(path, "w", encoding="utf-8") as out:
        json.dump(entry, out, ensure_ascii=False, indent=2)
        out.write("\n")
    print("替身：" + path)

    enc = encrypt_secret(wxtoken_dir, wxtoken_conf, "sec-" + args.appid)
    name = (args.name or args.appid).replace("'", "''")
    sql = (
        "INSERT INTO db_wxtoken.t_wx_app (f_wx_appid, f_name, f_secret_enc, f_key_ver, f_status, f_refresh_token) "
        f"VALUES ('{args.appid}', '{name}', '{enc}', 1, 0, 0) "
        "ON DUPLICATE KEY UPDATE f_secret_enc=VALUES(f_secret_enc), f_key_ver=1, f_status=0, f_refresh_token=0;"
    )
    result = subprocess.run(args.mysql.split() + ["--default-character-set=utf8mb4", "-e", sql],
                            capture_output=True, text=True)
    if result.returncode != 0:
        die("写 t_wx_app 失败：" + result.stderr.strip())
    print(f"t_wx_app：{args.appid} 已写测试 secret，不刷新 access_token")
    print(f"code {args.code} → openid {openid}")


if __name__ == "__main__":
    main()
