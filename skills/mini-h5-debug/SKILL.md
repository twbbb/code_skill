---
name: mini-h5-debug
description: 用 wxa-runner 在浏览器里跑原生小程序（小程序转 H5），后台连本机 common_server，wx.login 走替身登录。用在不开开发者工具调试小程序、在 H5 里点页面测功能时。
---

# 小程序转 H5 调试

wxa-runner 用微信官方基础库在浏览器里跑小程序编译产物。浏览器拿不到真实的 `wx.login` code，所以登录走**替身**：setup 把 code 固定住，本机 wxtoken 的 `jscode2session` 替身把这个 code 换成固定 openid。登录链路是 小程序 → 网关 `/api/auth/WxLogin` → auth → wxtoken `Proxy` → 替身。

记号：`<小程序>` 是 `project.config.json` 所在目录；`<common_server>` 是 common_server 仓库；`<skill>` 是本目录。

## 步骤

1. **确认能跑。** 读 `<小程序>/project.config.json`：`compileType` 是 `game`（小游戏，产物是 `game.json`）时停下，告诉用户 wxa-runner 只支持带 `app.json` 的小程序，小游戏走开发者工具。再读小程序的请求层，找到 `API_BASE` 和 `wx_appid`。
   完成：`miniprogramRoot` 下有 `app.json`；`API_BASE` 指向本机网关（如 `http://127.0.0.1:18112`），不是就先改，并提醒用户上线前改回。

2. **起后台。** 按 fabutai skill 的「本机启动」用 `start_local` 起 wxtoken、auth、业务服务、网关（依赖顺序）。本机库缺什么就补：业务库的建表 SQL、common_server `sql/` 里这个产品的路由 SQL（`t_app`、`t_client`、`t_gw_service`、`t_gw_method`）。
   - auth 启动时把 `t_client` 读进内存。补了 `t_client` 要重启 auth，否则登录报「没有这个端」。
   - 网关同样启动时载入路由。补了 `t_gw_service` 后重启网关，否则报「没有这个服务」。
   完成：`POST <API_BASE>/api/<业务>/Ping` 返回 HTTP 200、`code` 0。

3. **替身登录。** 在 `<小程序>/wxa.setup.js` 固定 code（已有就沿用）：
   ```js
   // H5 里 wx.login 给的是假 code，真实微信不认。固定成 local-h5，本机 wxtoken 的替身按它回 openid。
   export default { mock: { login: { code: "local-h5" } } };
   ```
   再写替身和测试 secret：
   ```bash
   python3 <skill>/scripts/stub_wx_login.py --common-server <common_server> --appid <wx_appid> --code local-h5
   ```
   要多个账号（如创建者和家人）时，每个账号一个 code，各跑一次脚本、`--openid` 各给一个；切账号就改 setup 里的 code，再清存储刷新。
   完成：`curl -X POST <API_BASE>/api/auth/WxLogin -H 'Content-Type: application/json' -d '{"wx_appid":"<wx_appid>","code":"local-h5"}'` 返回 `code` 0 且带 `sid`。

4. **起 H5。** 后台跑，不加 `--no-setup`，Playwright 浏览器已装时带 `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1`，不重装：
   ```bash
   PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 npx --yes wxa-runner dev <小程序> --port 3000 --open
   ```
   用可见的浏览器打开 `http://localhost:3000` 给用户看，截图读图。setup 文件是新建的，要重启 wxa-runner 才会加载；改已有的 setup 页面会自动刷新。
   完成：终端启动信息里有 `setup <小程序>/wxa.setup.js`；页面不是白屏；网关日志 `server request:/api/auth/WxLogin` 后面紧跟业务接口的请求；本机 `db_auth.t_user` 有 `f_userkey` 为替身 openid 的一行。

## 报错对照

wxa-runner 把逻辑层的 `console.warn` / `console.error` 转到终端，先看那里。

| 现象 | 原因 | 处理 |
|---|---|---|
| `dist 下没有 app.json` | 小游戏或产物目录不对 | 回第 1 步 |
| `没有这个端` | auth 内存里没有这个 `wx_appid` 的 `t_client` | 补 `t_client`，重启 auth |
| `没有这个服务` | 网关没载入 `t_gw_service` | 补路由，重启网关 |
| `调微信失败，请稍后再试` | 替身没命中，或 `t_wx_app` 没有这个 appid | 重跑第 3 步的脚本；code 和 setup 里的一致 |
| 页面白屏、终端没报错 | 首页还在等登录 | 等几秒点模拟器下方「刷新」，再看终端 |
