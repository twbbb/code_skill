# 数据脚本和 test 代码

svc-local-test 第 3、4 步写产物时读这份。只用 `kit_test.go` 和 `common_test.go` 里的辅助。

## 生成标记

生成的每个 test 函数、数据脚本，第一行带 `@gen 用例NN`；`cases.yaml` 每条用例写 `mark: "@gen 用例NN"`。手工改过的产物，用户把它改成 `@manual`。重新生成只改写 `@gen` 的产物；`@manual` 的原样保留，要改时在用例下加 `- 待复核：<原因>` 交给用户。

## 数据脚本

写法见 [CASES.md](CASES.md)「数据脚本」。测试标识取自用例文档「测试数据」，写进 `cases.yaml` 的 `accounts`；要调工具才算得出的值（如用本地主密钥加密 secret）在 `cases.yaml` 的 `render` 定义占位符。全表扫描的用例先清掉所有带前缀的行，再清会抢的锁。

## test 函数

```go
// @gen 用例10：Proxy 遇到 40001，换 token 重试一次
func Test_10_Proxy(t *testing.T) {
	c := NewCase(t, "10")
	a := Acc(t, "P10")
	// 替身：旧 token 回 40001，新 token 成功；新 token 由 stable_token 的替身发
	c.StubHTTP("POST", wxHost+"/wxa/msg_sec_check?access_token=tok-lt10-stale", `{"content":"hello"}`,
		&rpcproxy.HTTPRsp{Body: json.RawMessage(`{"errcode":40001}`)})
	stable := c.StubHTTP("POST", wxHost+"/cgi-bin/stable_token", stableBody(a),
		&rpcproxy.HTTPRsp{Body: json.RawMessage(`{"access_token":"tok-lt10-new","expires_in":7200}`)})
	c.StubHTTP("POST", wxHost+"/wxa/msg_sec_check?access_token=tok-lt10-new", `{"content":"hello"}`,
		&rpcproxy.HTTPRsp{Body: json.RawMessage(`{"errcode":0}`)})
	req := &wxtokenpb.ProxyReq{ /* 用例文档的参数 */ }
	rsp, err := wxtokenpb.NewWxTokenClientProxy(c.ClientOpts("wx1")...).Proxy(context.Background(), req)
	c.Record("WxToken/Proxy", req, rsp, err)
	if err != nil {
		t.Fatalf("Proxy 失败: %v", err)
	}
	// 断言用例文档「预期结果-响应」里的字段；状态和流程由 run_case.py 取证
	if n := StubHits(t, []string{"wx1"}, c.Start, stable); n != 1 {
		t.Errorf("应只换一次 token，stable_token 替身命中 %d 次", n)
	}
}
```

- **RPC 入口**：`c.ClientOpts(<进程>)` 建 proxy，它带上本条 requestId；`c.Record` 传发请求用的同一个 `req`。
- **HTTP 入口**：`c.HTTP(<进程>, method, path, body, header)`。被测进程自己生成 requestId 的（如网关），从响应里取出来调 `c.AddRequestID`。
- **替身**：外部下游的每一次调用写一份。trpc 用 `c.StubRPC(被调服务名, 方法名, 被测服务会发出的请求, 返回, 身份 metadata)`，HTTP 用 `c.StubHTTP(method, 带 query 的 URL, 请求体原文, 返回)`。请求照代码里拼请求的地方逐字段写（JSON 字段顺序、query 编码方式都要一致），命中才算数；命中本身就是请求内容的证据。要数调用次数用 `StubHits`。
- **定时任务入口**：先写替身，再 `c.Exec("localstart/startserver.sh", "start", <实例>)` 起定时任务实例，`WaitLog` 等任务结束那行；`cases.yaml` 的 `after` 停实例，`also` 写匹配定时任务 requestId 的正则。多实例抢锁的起两个，`proc` 写两个。
- **拆段**：一条用例要多次调用、中间改数据或换替身时，拆成 `Test_NNa_`、`Test_NNb_`，后一段的数据改动写成 `data/NNb.*`。
- 按入口分组拆文件（`token_test.go`、`proxy_test.go`）；服务自己的辅助（建 client、拼下游请求体、常量）放 `common_test.go`，名字避开 kit 导入的包名（如 `client`）。

## cases.yaml

每条用例一项，格式见 [CASES.md](CASES.md)：`pre` 覆盖「前置条件」，`post` 覆盖「预期结果-状态」，`flow` 取公共流程链路加本用例的分支节点（标「无日志」的节点改在核对表里用状态核对）。
