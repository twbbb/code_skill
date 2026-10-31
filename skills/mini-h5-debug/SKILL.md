---
name: mini-h5-debug
description: 小程序转 H5：用 wxa-runner 在浏览器里跑原生小程序，后台连本机 common_server，wx.login 走替身登录。用在不开开发者工具调试、测小程序页面时。
---

# 小程序转 H5 调试

浏览器拿不到真实的 `wx.login` code：setup 把 code 固定住，本机 wxtoken 的 `jscode2session` 替身把它换成固定 openid。

源码里的 `API_BASE` 保持线上地址。这次测试打本机网关：第 2 步换成 `http://127.0.0.1:18112`。离开这次测试时跑第 7 步，把 `API_BASE` 改回线上。

## 步骤

1. **确认能跑。** `project.config.json` 的 `compileType` 是 `game` 就停下：小游戏走开发者工具。
   完成：`miniprogramRoot` 下有 `app.json`；请求层的 `API_BASE` 是 `https://` 开头的线上地址。

2. **请求改打本机。**
   ```bash
   python3 <本目录>/scripts/swap_api_base.py <请求层文件> local
   ```
   完成：该文件的 `API_BASE` 是 `http://127.0.0.1:18112`，脚本已记下原来的线上地址。

3. **起后台。** 用 fabutai 的 `start_local` 依次起 wxtoken、auth、业务服务、网关；本机缺的业务库和 common_server `sql/` 里的路由 SQL 先补上。
   完成：`POST http://127.0.0.1:18112/api/<业务>/Ping` 返回 200、`code` 0。

4. **替身登录。** `<小程序>/wxa.setup.js`：
   ```js
   export default { mock: { login: { code: "local-h5" } } };
   ```
   ```bash
   python3 <本目录>/scripts/stub_wx_login.py --common-server <common_server> --appid <wx_appid> --code local-h5
   ```
   多账号就每个账号一个 code、各跑一次。
   完成：用这个 code 调 `/api/auth/WxLogin` 返回 `code` 0 且带 `sid`。

5. **起 H5。**
   ```bash
   PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 npx --yes wxa-runner dev <小程序> --port 3000 --open
   ```
   新建的 setup 要重启 wxa-runner 才加载。用可见浏览器打开 `http://localhost:3000`，截图读图。
   完成：启动信息里有 `setup`；页面不是白屏；网关日志 `WxLogin` 后跟着业务请求。

6. **截图取证。** 用户让测试时，截图是结论的证据：用户看到截图才信。每个测过的场景截一张，按场景命名存进小程序项目的 `tmp/`，回复里逐场景嵌入截图，配一句看到了什么。
   完成：每个场景都有一张 `tmp/` 下的截图嵌在回复里，通过、失败都附图。

7. **改回线上。**
   ```bash
   python3 <本目录>/scripts/swap_api_base.py <请求层文件> restore
   ```
   完成：请求层的 `API_BASE` 回到第 2 步记下的线上地址。

## 报错

wxa-runner 把逻辑层报错转到终端。

| 报错 | 处理 |
|---|---|
| `没有 app.json` | 小游戏或目录不对，回第 1 步 |
| `没有这个端` | 补 `t_client` 后重启 auth（启动时才载入） |
| `没有这个服务` | 补 `t_gw_service` 后重启网关 |
| `调微信失败` | 替身没命中：重跑第 4 步，code 和 setup 一致 |
