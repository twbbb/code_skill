package testcase

// 本地用例的公共辅助：连本地进程、写证据文件、写替身、读日志。标准文件，由 svc-local-test 维护，不在工作区里改；
// 服务自己的辅助（建 client proxy、查状态）写在 common_test.go。
// 用例由 ./run NN 执行，它设好 ROUND 并建好证据文件；直接 go test 没有 ROUND 时整包跳过。

import (
	"bufio"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"testing"
	"time"

	"github.com/twbbb/toolbox/filter/rpcproxy"
	"gopkg.in/yaml.v3"
	"trpc.group/trpc-go/trpc-go/client"
	"trpc.group/trpc-go/trpc-go/errs"
)

// stubDir 被测进程 rpcproxy 的缓存目录，本地用例只往里放替身
const stubDir = "localstart/rpcproxy_cache"

// Case 一条用例在本轮的证据文件和 requestId
type Case struct {
	t         *testing.T
	Path      string    // result/<轮>/NN_<Method>.md
	RequestId string    // 证据文件头部的 requestId，调用时带给被测进程
	Start     time.Time // 证据文件头部的执行时间，数日志只数这之后的
}

// NewCase 从 result/$ROUND/NN_*.md 头部读 requestId 和执行时间
func NewCase(t *testing.T, nn string) *Case {
	t.Helper()
	round := os.Getenv("ROUND")
	if round == "" {
		t.Skip("没有 ROUND，用 ./run " + nn + " 执行")
	}
	files, _ := filepath.Glob(filepath.Join("result", round, nn+"_*.md"))
	if len(files) != 1 {
		t.Fatalf("result/%s 下 %s_*.md 有 %d 个，用 ./run 执行", round, nn, len(files))
	}
	b, err := os.ReadFile(files[0])
	if err != nil {
		t.Fatalf("读证据文件失败: %v", err)
	}
	c := &Case{t: t, Path: files[0]}
	if m := regexp.MustCompile(`(?m)^- requestId：(\S+)$`).FindSubmatch(b); m != nil {
		c.RequestId = string(m[1])
	}
	if m := regexp.MustCompile(`(?m)^- 执行时间：(.+)$`).FindSubmatch(b); m != nil {
		c.Start, _ = time.ParseInLocation("2006-01-02 15:04:05", string(m[1]), time.Local)
	}
	if c.RequestId == "" || c.Start.IsZero() {
		t.Fatalf("%s 头部没有 requestId 或执行时间", c.Path)
	}
	return c
}

// ClientOpts 连 env.yaml 里的进程（兄弟服务写「兄弟名:进程名」），每次调用都带上本条 requestId
func (c *Case) ClientOpts(proc string) []client.Option {
	return []client.Option{
		client.WithTarget(fmt.Sprintf("ip://127.0.0.1:%d", Port(c.t, proc))),
		client.WithTimeout(10 * time.Second),
		client.WithMetaData("requestId", []byte(c.RequestId)),
	}
}

// Record 把一次 RPC 调用写进「请求」「响应」。name 写 Service/Method，如 WxToken/GetAccessToken
func (c *Case) Record(name string, req, rsp any, err error) {
	c.t.Helper()
	c.append("请求", "接口：`"+name+"`\n\n"+jsonBlock(c.t, req))
	if err != nil {
		c.append("响应", jsonBlock(c.t, map[string]any{"code": errs.Code(err), "msg": errs.Msg(err)}))
		return
	}
	c.append("响应", jsonBlock(c.t, rsp))
}

// HTTPResult 一次 HTTP 调用的结果
type HTTPResult struct {
	Status int
	Header http.Header
	Raw    string         // 响应体原文
	Body   map[string]any // 响应体是 JSON 对象时解析出来的
}

// HTTP 给 env.yaml 里的进程发一个 HTTP 请求，请求和响应写进证据文件
func (c *Case) HTTP(proc, method, path, body string, header map[string]string) *HTTPResult {
	c.t.Helper()
	u := fmt.Sprintf("http://127.0.0.1:%d%s", Port(c.t, proc), path)
	req, err := http.NewRequest(method, u, strings.NewReader(body))
	if err != nil {
		c.t.Fatalf("组请求失败: %v", err)
	}
	keys := make([]string, 0, len(header))
	for k, v := range header {
		req.Header.Set(k, v)
		keys = append(keys, k)
	}
	sort.Strings(keys)
	head := ""
	for _, k := range keys {
		head += k + ": " + header[k] + "\n"
	}
	c.append("请求", "接口：`"+method+" "+path+"`（"+proc+"）\n\n```text\n"+head+"\n"+body+"\n```")
	rsp, err := (&http.Client{Timeout: 15 * time.Second}).Do(req)
	if err != nil {
		c.append("响应", "```text\n请求失败："+err.Error()+"\n```")
		c.t.Fatalf("%s %s 失败: %v", method, path, err)
	}
	defer rsp.Body.Close()
	raw, _ := io.ReadAll(rsp.Body)
	r := &HTTPResult{Status: rsp.StatusCode, Header: rsp.Header, Raw: string(raw)}
	_ = json.Unmarshal(raw, &r.Body)
	hk := make([]string, 0, len(rsp.Header))
	for k := range rsp.Header {
		if k != "Date" && k != "Content-Length" {
			hk = append(hk, k)
		}
	}
	sort.Strings(hk)
	out := fmt.Sprintf("HTTP %d\n", rsp.StatusCode)
	for _, k := range hk {
		out += k + ": " + rsp.Header.Get(k) + "\n"
	}
	c.append("响应", "```text\n"+out+"\n"+string(raw)+"\n```")
	return r
}

// AddRequestID 被测进程自己生成的 requestId（如网关）记进头部，取证时这些行也算本条的
func (c *Case) AddRequestID(id string) {
	c.t.Helper()
	if id == "" {
		return
	}
	b, err := os.ReadFile(c.Path)
	if err != nil {
		c.t.Fatalf("读证据文件失败: %v", err)
	}
	s := strings.Replace(string(b), "\n- 执行时间：", "\n- 关联 requestId："+id+"\n- 执行时间：", 1)
	if err := os.WriteFile(c.Path, []byte(s), 0o644); err != nil {
		c.t.Fatalf("写证据文件失败: %v", err)
	}
}

// StubRPC 写一份 trpc 下游替身。service 是被调服务名，req 写被测服务会发出的请求，md 是它带的用户身份 metadata
func (c *Case) StubRPC(service, method string, req, rsp any, md map[string]string) {
	c.t.Helper()
	file, err := rpcproxy.StubFile(stubDir, service, method, req, md)
	if err != nil {
		c.t.Fatalf("算替身文件名失败: %v", err)
	}
	c.writeStub(file, service+"/"+method, req, rsp)
}

// StubHTTP 写一份 HTTP 下游替身。url 带 query，body 是被测服务会发出的请求体原文
func (c *Case) StubHTTP(method, url, body string, rsp *rpcproxy.HTTPRsp) {
	c.t.Helper()
	file, err := rpcproxy.HTTPStubFile(stubDir, method, url, []byte(body))
	if err != nil {
		c.t.Fatalf("算替身文件名失败: %v", err)
	}
	req := &rpcproxy.HTTPReq{Method: strings.ToUpper(method), URL: url}
	if json.Valid([]byte(body)) {
		req.Body = json.RawMessage(body)
	} else {
		req.BodyText = body
	}
	c.writeStub(file, strings.ToUpper(method)+" "+url, req, rsp)
}

func (c *Case) writeStub(file, what string, req, rsp any) {
	c.t.Helper()
	if err := rpcproxy.WriteStub(file, req, rsp); err != nil {
		c.t.Fatalf("写替身失败: %v", err)
	}
	b, _ := os.ReadFile(file)
	c.append("替身", "**"+filepath.Base(file)+"**："+what+"\n\n```json\n"+string(b)+"\n```")
}

// Exec 在工作区执行一条命令（如起定时任务实例），失败即停
func (c *Case) Exec(name string, args ...string) {
	c.t.Helper()
	out, err := exec.Command(name, args...).CombinedOutput()
	if err != nil {
		c.t.Fatalf("%s %v 失败: %v\n%s", name, args, err, out)
	}
}

// Note 往「说明」里写一条
func (c *Case) Note(format string, a ...any) {
	c.t.Helper()
	c.append("说明", "- "+fmt.Sprintf(format, a...))
}

func jsonBlock(t *testing.T, v any) string {
	t.Helper()
	b, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		t.Errorf("序列化失败: %v", err)
	}
	return "```json\n" + string(b) + "\n```"
}

// append 把 text 追加到 section 分段末尾（下一个 ## 之前），与 scripts/evidence.py 的 append 一致
func (c *Case) append(section, text string) {
	c.t.Helper()
	b, err := os.ReadFile(c.Path)
	if err != nil {
		c.t.Fatalf("读证据文件失败: %v", err)
	}
	content := string(b)
	head := "\n## " + section + "\n"
	start := strings.Index(content, head)
	if start < 0 {
		c.t.Fatalf("%s 没有「%s」分段", c.Path, section)
	}
	bodyStart := start + len(head)
	end := len(content)
	if i := strings.Index(content[bodyStart:], "\n## "); i >= 0 {
		end = bodyStart + i + 1
	}
	body := strings.TrimRight(content[bodyStart:end], "\n")
	if strings.TrimSpace(body) != "" {
		body += "\n\n"
	} else {
		body = "\n"
	}
	body += strings.TrimRight(text, "\n") + "\n\n"
	if err := os.WriteFile(c.Path, []byte(content[:bodyStart]+body+content[end:]), 0o644); err != nil {
		c.t.Fatalf("写证据文件失败: %v", err)
	}
}

// ---------------------------------------------------------------- 配置

type envProc struct {
	Port int `yaml:"port"`
}

type envFile struct {
	Procs    map[string]envProc `yaml:"procs"`
	Siblings map[string]struct {
		Dir string `yaml:"dir"`
	} `yaml:"siblings"`
}

// procDir 进程引用对应的工作区和进程名：本服务直接写名字，兄弟服务写「兄弟名:进程名」
func procDir(t *testing.T, ref string) (string, string) {
	t.Helper()
	sib, name, ok := strings.Cut(ref, ":")
	if !ok {
		return ".", ref
	}
	var e envFile
	readYAML(t, "env.yaml", &e)
	s, ok := e.Siblings[sib]
	if !ok {
		t.Fatalf("env.yaml siblings 里没有 %s", sib)
	}
	return s.Dir, name
}

// Port env.yaml 里进程的端口
func Port(t *testing.T, ref string) int {
	t.Helper()
	dir, name := procDir(t, ref)
	var e envFile
	readYAML(t, filepath.Join(dir, "env.yaml"), &e)
	p, ok := e.Procs[name]
	if !ok {
		t.Fatalf("%s/env.yaml procs 里没有 %s", dir, name)
	}
	return p.Port
}

// Acc cases.yaml accounts 里的测试标识
func Acc(t *testing.T, role string) string {
	t.Helper()
	var cfg struct {
		Accounts map[string]string `yaml:"accounts"`
	}
	readYAML(t, "cases.yaml", &cfg)
	v, ok := cfg.Accounts[role]
	if !ok {
		t.Fatalf("cases.yaml accounts 里没有 %s", role)
	}
	return v
}

func readYAML(t *testing.T, path string, v any) {
	t.Helper()
	b, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("读 %s 失败: %v", path, err)
	}
	if err := yaml.Unmarshal(b, v); err != nil {
		t.Fatalf("解析 %s 失败: %v", path, err)
	}
}

// ---------------------------------------------------------------- 日志

// LogPath 进程的 trpc.log
func LogPath(t *testing.T, ref string) string {
	t.Helper()
	dir, name := procDir(t, ref)
	return filepath.Join(dir, "localstart", "log", name, "trpc.log")
}

// LogLines 进程日志里时间不早于 since、包含 kw 的行
func LogLines(t *testing.T, ref string, since time.Time, kw string) []string {
	t.Helper()
	f, err := os.Open(LogPath(t, ref))
	if err != nil {
		t.Fatalf("打开日志失败: %v", err)
	}
	defer f.Close()
	from := since.Format("2006-01-02 15:04:05")
	var out []string
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 1<<20), 1<<20)
	for sc.Scan() {
		l := sc.Text()
		if len(l) >= 19 && l[:19] >= from && strings.Contains(l, kw) {
			out = append(out, l)
		}
	}
	return out
}

// WaitLog 等到这些进程日志里 since 之后包含 kw 的行合计达到 n 行
func WaitLog(t *testing.T, procs []string, since time.Time, kw string, n int, timeout time.Duration) {
	t.Helper()
	deadline := time.Now().Add(timeout)
	for {
		got := 0
		for _, p := range procs {
			got += len(LogLines(t, p, since, kw))
		}
		if got >= n {
			return
		}
		if time.Now().After(deadline) {
			t.Fatalf("%v 等 %s 之后的「%s」%d 行，%s 内只等到 %d 行", procs, since.Format(time.TimeOnly), kw, n, timeout, got)
		}
		time.Sleep(200 * time.Millisecond)
	}
}

// WantCode 断言 trpc 错误码
func WantCode(t *testing.T, err error, want int) {
	t.Helper()
	if int(errs.Code(err)) != want {
		t.Errorf("错误码应为 %d，实际 %d（%v）", want, errs.Code(err), err)
	}
}
