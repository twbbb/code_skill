// 从指定 Go 入口函数展开本模块调用图。
//
// 用法（在目标服务目录下）：
//
//	go run /path/to/gocalls -entry GetAccessToken
//	go run /path/to/gocalls -entry GetAccessToken -algo cha -format tree
package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"go/types"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"golang.org/x/tools/go/callgraph"
	"golang.org/x/tools/go/callgraph/cha"
	"golang.org/x/tools/go/callgraph/rta"
	"golang.org/x/tools/go/callgraph/static"
	"golang.org/x/tools/go/callgraph/vta"
	"golang.org/x/tools/go/packages"
	"golang.org/x/tools/go/ssa"
	"golang.org/x/tools/go/ssa/ssautil"
)

type outNode struct {
	Name    string     `json:"name"`
	Pkg     string     `json:"pkg"`
	File    string     `json:"file,omitempty"`
	Line    int        `json:"line,omitempty"`
	EndLine int        `json:"endLine,omitempty"` // 方法体最后一行，读方法体时用
	InMod   bool       `json:"inModule"`
	Calls   []*outNode `json:"calls,omitempty"`
	Skipped string     `json:"skipped,omitempty"`
	Break   string     `json:"break,omitempty"` // static 跟不下去的接口/动态调用
	// 多实现断点的候选：「实现名 文件:行」
	Candidates []string `json:"candidates,omitempty"`
}

func main() {
	dir := flag.String("dir", ".", "Go 模块目录")
	patterns := flag.String("patterns", "./...", "packages.Load 的 pattern，默认全模块；可写成 . 避开 client")
	entry := flag.String("entry", "", "入口函数名子串，如 GetAccessToken")
	algo := flag.String("algo", "static", "算法：static | cha | rta | vta（cha/vta 更全也更吵）")
	format := flag.String("format", "tree", "输出：tree | json")
	modPrefix := flag.String("module", "", "只保留此前缀的包；空则读 go.mod")
	maxDepth := flag.Int("maxdepth", 100, "最大展开层数")
	maxKids := flag.Int("maxkids", 400, "每个节点最多展示多少条出边")
	showExt := flag.Bool("ext", false, "叶子上保留仓库外调用（只记一层，不下钻）")
	allHits := flag.Bool("allhits", false, "入口匹配不限制本模块（会命中 proto/mock）")
	flag.Parse()

	if *entry == "" {
		fmt.Fprintln(os.Stderr, "必须指定 -entry，例如 -entry GetAccessToken")
		os.Exit(2)
	}
	absDir, err := filepath.Abs(*dir)
	must(err)
	if *modPrefix == "" {
		*modPrefix = readModulePath(absDir)
	}
	if *modPrefix == "" {
		must(fmt.Errorf("读不到 module path，请用 -module 指定"))
	}

	fmt.Fprintf(os.Stderr, "dir=%s module=%s algo=%s entry=%s\n", absDir, *modPrefix, *algo, *entry)

	cfg := &packages.Config{
		Mode: packages.NeedName | packages.NeedFiles | packages.NeedCompiledGoFiles |
			packages.NeedImports | packages.NeedDeps | packages.NeedTypes |
			packages.NeedTypesInfo | packages.NeedSyntax | packages.NeedModule,
		Dir: absDir,
	}
	loadArgs := strings.Fields(*patterns)
	if len(loadArgs) == 0 {
		loadArgs = []string{"./..."}
	}
	pkgs, err := packages.Load(cfg, loadArgs...)
	must(err)
	filtered := pkgs[:0]
	for _, p := range pkgs {
		if strings.Contains(p.PkgPath, "/client") {
			continue
		}
		filtered = append(filtered, p)
	}
	pkgs = filtered
	if packages.PrintErrors(pkgs) > 0 {
		fmt.Fprintln(os.Stderr, "packages.Load 有错误，继续尝试建图（结果可能不全）")
	}

	prog, ssaPkgs := ssautil.AllPackages(pkgs, ssa.InstantiateGenerics)
	prog.Build()
	_ = ssaPkgs

	cg := buildGraph(prog, *algo)
	roots := findRoots(cg, *entry, *modPrefix, *allHits)
	if len(roots) == 0 {
		fmt.Fprintf(os.Stderr, "找不到包含 %q 的函数。可试 -entry WxTokenImpl.GetAccessToken\n", *entry)
		os.Exit(1)
	}

	fmt.Fprintf(os.Stderr, "命中 %d 个入口：\n", len(roots))
	for _, n := range roots {
		fmt.Fprintf(os.Stderr, "  %s\n", funcName(n.Func))
	}

	w := &walker{
		cg:           cg,
		mod:          *modPrefix,
		absDir:       absDir,
		maxKids:      *maxKids,
		showExt:      *showExt,
		seen:         map[string]int{},
		varToHandler: mapIfaceGlobalImpls(cg, *modPrefix),
	}
	forest := make([]*outNode, 0, len(roots))
	for _, n := range roots {
		forest = append(forest, w.walk(n, *maxDepth))
	}

	if *format == "json" {
		enc := json.NewEncoder(os.Stdout)
		enc.SetIndent("", "  ")
		must(enc.Encode(forest))
		return
	}
	for i, t := range forest {
		if i > 0 {
			fmt.Println()
		}
		printTree(t, "", true, true)
	}
}

func buildGraph(prog *ssa.Program, algo string) *callgraph.Graph {
	switch strings.ToLower(algo) {
	case "static":
		return static.CallGraph(prog)
	case "rta":
		var roots []*ssa.Function
		for fn := range ssautil.AllFunctions(prog) {
			if fn.Name() == "main" && fn.Pkg != nil && fn.Pkg.Pkg.Name() == "main" {
				roots = append(roots, fn)
			}
		}
		if len(roots) == 0 {
			fmt.Fprintln(os.Stderr, "rta 找不到 main，回退 cha")
			return cha.CallGraph(prog)
		}
		return rta.Analyze(roots, true).CallGraph
	case "vta":
		return vta.CallGraph(ssautil.AllFunctions(prog), cha.CallGraph(prog))
	default:
		return cha.CallGraph(prog)
	}
}

func findRoots(cg *callgraph.Graph, needle, mod string, allHits bool) []*callgraph.Node {
	var hits []*callgraph.Node
	for fn, n := range cg.Nodes {
		if fn == nil {
			continue
		}
		name := funcName(fn)
		if !strings.Contains(name, needle) {
			continue
		}
		if noiseName(name) {
			continue
		}
		if !allHits && !inModule(fn, mod) {
			continue
		}
		hits = append(hits, n)
	}
	sort.Slice(hits, func(i, j int) bool { return funcName(hits[i].Func) < funcName(hits[j].Func) })
	return hits
}

func noiseName(name string) bool {
	switch {
	case strings.Contains(name, "Mock"):
		return true
	case strings.Contains(name, "Unimplemented"):
		return true
	case strings.Contains(name, "$bound"):
		return true
	case strings.HasSuffix(name, ".Descriptor"),
		strings.HasSuffix(name, ".ProtoMessage"),
		strings.HasSuffix(name, ".ProtoReflect"),
		strings.HasSuffix(name, ".Reset"):
		return true
	}
	return false
}

type walker struct {
	cg           *callgraph.Graph
	mod          string
	absDir       string
	maxKids      int
	showExt      bool
	seen         map[string]int
	varToHandler map[string]*callgraph.Node
}

func (w *walker) walk(n *callgraph.Node, depth int) *outNode {
	fn := n.Func
	out := w.baseNode(fn)
	if !out.InMod {
		out.Skipped = "模块外"
		return out
	}
	key := funcName(fn)
	if returnsIfaceSlice(fn) {
		expand := w.seen[key] == 0 && depth > 0
		if w.seen[key] == 0 {
			w.seen[key]++
		}
		w.attachSliceBuilders(out, fn, depth, expand)
		if !expand {
			if depth <= 0 {
				out.Skipped = "达到 maxdepth，仅列顺序"
			} else {
				out.Skipped = "已展开过，仅列顺序"
			}
		}
		return out
	}
	if w.seen[key] > 0 {
		out.Skipped = "已展开过"
		return out
	}
	// 2) range []接口 再 invoke：执行器，顺序在构造函数里，这里只标断点
	if invs := ifaceSliceInvokes(fn); len(invs) > 0 || isSliceExecutor(fn) {
		w.seen[key]++
		out.Break = "断点: 遍历 []接口 后 invoke，static 无顺序"
		if len(invs) == 0 {
			invs = interfaceInvokes(fn)
		}
		for _, inv := range invs {
			if isCommonIface(inv.method) {
				continue
			}
			out.Calls = append(out.Calls, &outNode{
				Name:  inv.String(),
				Break: "实现顺序看返回 []接口 的那个函数，不要读本节点出边",
			})
		}
		return out
	}
	if depth <= 0 {
		out.Skipped = "达到 maxdepth"
		return out
	}
	w.seen[key]++

	shown := 0
	for _, c := range uniqueCallex(n) {
		if c.Func == nil || skipCallee(c.Func) {
			continue
		}
		childIn := inModule(c.Func, w.mod)
		if !childIn {
			if !w.showExt || skipExt(c.Func) {
				continue
			}
			out.Calls = append(out.Calls, &outNode{Name: shortName(c.Func), Pkg: pkgPath(c.Func), InMod: false, Skipped: "模块外"})
			shown++
			continue
		}
		if shown >= w.maxKids {
			out.Calls = append(out.Calls, &outNode{Name: "…", Skipped: "maxkids"})
			break
		}
		out.Calls = append(out.Calls, w.walk(c, depth-1))
		shown++
	}

	// 3) 单个接口 invoke（GET().Foo()）：按类型找本模块实现。
	// 唯一实现直接下钻、不算断点；没有实现是桩/仓库外；多个实现才留断点并列出候选。
	for _, inv := range interfaceInvokes(fn) {
		if isCommonIface(inv.method) {
			continue
		}
		impls := w.concreteImpls(inv)
		bn := &outNode{Name: inv.String()}
		switch len(impls) {
		case 0:
			bn.Skipped = "桩/仓库外：本模块没有实现"
		case 1:
			bn.InMod = true
			bn.Calls = append(bn.Calls, w.walk(impls[0], depth-1))
		default:
			bn.Break = fmt.Sprintf("断点: 接口 invoke，%d 个实现，不展开以免乱序", len(impls))
			for _, im := range impls {
				bn.Candidates = append(bn.Candidates, fmt.Sprintf("%s %s:%d", shortName(im.Func), w.fileOf(im.Func), w.lineOf(im.Func)))
			}
		}
		out.Calls = append(out.Calls, bn)
	}
	return out
}

func returnsIfaceSlice(fn *ssa.Function) bool {
	if fn == nil || fn.Signature == nil {
		return false
	}
	res := fn.Signature.Results()
	if res == nil || res.Len() == 0 {
		return false
	}
	for i := 0; i < res.Len(); i++ {
		if isIfaceSlice(res.At(i).Type()) {
			return true
		}
	}
	return false
}

func isIfaceSlice(t types.Type) bool {
	sl, ok := t.Underlying().(*types.Slice)
	if !ok {
		return false
	}
	_, ok = sl.Elem().Underlying().(*types.Interface)
	return ok
}

func isIface(t types.Type) bool {
	if t == nil {
		return false
	}
	if _, ok := t.Underlying().(*types.Interface); ok {
		return true
	}
	// 包级 var X I 在 SSA 里是 *I
	if p, ok := t.Underlying().(*types.Pointer); ok {
		_, ok = p.Elem().Underlying().(*types.Interface)
		return ok
	}
	return false
}

// 每个 return 块一组：本块里「返回 []接口的调用」+「类型为接口的全局变量」，按指令顺序。
func isSliceExecutor(fn *ssa.Function) bool {
	if fn.Signature == nil || fn.Signature.Params() == nil {
		return false
	}
	has := false
	for i := 0; i < fn.Signature.Params().Len(); i++ {
		if isIfaceSlice(fn.Signature.Params().At(i).Type()) {
			has = true
			break
		}
	}
	return has && len(interfaceInvokes(fn)) > 0
}

func (w *walker) attachSliceBuilders(out *outNode, fn *ssa.Function, depth int, expand bool) {
	for _, b := range fn.Blocks {
		if !blockReturns(b) {
			continue
		}
		steps := w.collectSliceSteps(b)
		if len(steps) == 0 {
			continue
		}
		grp := &outNode{Name: fmt.Sprintf("拼出 []接口（return @%s）", w.blockPos(b))}
		for i, s := range steps {
			if s.call != nil {
				child := w.walk(s.call, depth-1)
				child.Name = fmt.Sprintf("%d. 展开 %s", i+1, shortName(s.call.Func))
				grp.Calls = append(grp.Calls, child)
				continue
			}
			n := &outNode{Name: fmt.Sprintf("%d. %s", i+1, s.global.Name())}
			key := globalKey(s.global)
			if h := w.varToHandler[key]; h != nil {
				n.Name = fmt.Sprintf("%d. %s → %s", i+1, s.global.Name(), shortName(h.Func))
				n.File = w.fileOf(h.Func)
				n.Line = w.lineOf(h.Func)
				if expand {
					n.Calls = w.walk(h, depth-1).Calls
				}
			} else {
				n.Break = "断点: 接口变量，未找到赋值的具体类型"
			}
			grp.Calls = append(grp.Calls, n)
		}
		out.Calls = append(out.Calls, grp)
	}
}

type sliceStep struct {
	call   *callgraph.Node
	global *ssa.Global
}

func (w *walker) collectSliceSteps(b *ssa.BasicBlock) []sliceStep {
	var steps []sliceStep
	seenG := map[string]bool{}
	seenC := map[string]bool{}
	seenV := map[ssa.Value]bool{}
	var walkVal func(v ssa.Value)
	addCall := func(cal *ssa.Function) {
		if cal == nil || !returnsIfaceSlice(cal) {
			return
		}
		k := funcName(cal)
		if seenC[k] {
			return
		}
		seenC[k] = true
		n := w.cg.Nodes[cal]
		if n == nil {
			n = &callgraph.Node{Func: cal}
		}
		steps = append(steps, sliceStep{call: n})
	}
	addGlobal := func(g *ssa.Global) {
		if g == nil || g.Type() == nil || !isIface(g.Type()) {
			return
		}
		k := globalKey(g)
		if seenG[k] {
			return
		}
		seenG[k] = true
		steps = append(steps, sliceStep{global: g})
	}
	walkVal = func(v ssa.Value) {
		if v == nil || seenV[v] {
			return
		}
		seenV[v] = true
		if g := peelGlobal(v); g != nil {
			addGlobal(g)
		}
		switch x := v.(type) {
		case *ssa.Call:
			if cal := x.Call.StaticCallee(); cal != nil {
				addCall(cal)
			}
			for _, arg := range x.Call.Args {
				walkVal(arg)
			}
		case *ssa.Phi:
			for _, e := range x.Edges {
				walkVal(e)
			}
		case *ssa.Extract:
			walkVal(x.Tuple)
		case *ssa.MakeInterface:
			walkVal(x.X)
		case *ssa.ChangeType:
			walkVal(x.X)
		case *ssa.Slice:
			walkVal(x.X)
		case *ssa.UnOp:
			walkVal(x.X)
		case *ssa.Index:
			walkVal(x.X)
		case *ssa.IndexAddr:
			walkVal(x.X)
		}
		if instr, ok := v.(ssa.Instruction); ok {
			for _, op := range instr.Operands(nil) {
				if op != nil {
					walkVal(*op)
				}
			}
		}
	}
	ret, ok := b.Instrs[len(b.Instrs)-1].(*ssa.Return)
	if !ok {
		return steps
	}
	for _, r := range ret.Results {
		walkVal(r)
	}
	// 同块 + 单后继前驱：字面量/append 常和 return 拆开
	for _, blk := range linearPreds(b) {
		for _, instr := range blk.Instrs {
			if c, ok := instr.(*ssa.Call); ok {
				addCall(c.Call.StaticCallee())
				for _, arg := range c.Call.Args {
					walkVal(arg)
				}
			}
			if st, ok := instr.(*ssa.Store); ok {
				walkVal(st.Val)
			}
			for _, op := range instr.Operands(nil) {
				if op != nil {
					if g := peelGlobal(*op); g != nil {
						addGlobal(g)
					}
				}
			}
		}
	}
	return steps
}

func linearPreds(b *ssa.BasicBlock) []*ssa.BasicBlock {
	seen := map[*ssa.BasicBlock]bool{}
	var out []*ssa.BasicBlock
	var walk func(*ssa.BasicBlock)
	walk = func(cur *ssa.BasicBlock) {
		if cur == nil || seen[cur] {
			return
		}
		seen[cur] = true
		out = append(out, cur)
		for _, p := range cur.Preds {
			if len(p.Succs) == 1 {
				walk(p)
			}
		}
	}
	walk(b)
	return out
}

func blockReturns(b *ssa.BasicBlock) bool {
	if b == nil || len(b.Instrs) == 0 {
		return false
	}
	_, ok := b.Instrs[len(b.Instrs)-1].(*ssa.Return)
	return ok
}

func (w *walker) blockPos(b *ssa.BasicBlock) string {
	if b == nil || len(b.Instrs) == 0 || b.Instrs[0].Pos() == 0 {
		return "?"
	}
	fn := b.Parent()
	if fn == nil || fn.Prog == nil {
		return "?"
	}
	p := fn.Prog.Fset.Position(b.Instrs[0].Pos())
	return fmt.Sprintf("%s:%d", relPath(p.Filename, w.absDir), p.Line)
}

func globalKey(g *ssa.Global) string {
	if g.Pkg != nil {
		return g.Pkg.Pkg.Path() + "." + g.Name()
	}
	return g.Name()
}

// 任意「接口全局变量 = 具体类型」赋值，不限定 Init / 包名。
func mapIfaceGlobalImpls(cg *callgraph.Graph, mod string) map[string]*callgraph.Node {
	byRecv := map[string]*callgraph.Node{}
	for fn, n := range cg.Nodes {
		if fn == nil || fn.Signature == nil || fn.Signature.Recv() == nil || !inModule(fn, mod) {
			continue
		}
		recv := recvKey(fn.Signature.Recv().Type())
		if recv != "" {
			byRecv[recv+"."+fn.Name()] = n
			if fn.Name() == "Handler" {
				byRecv[recv] = n
			}
		}
	}
	out := map[string]*callgraph.Node{}
	for fn := range cg.Nodes {
		if fn == nil {
			continue
		}
		for _, b := range fn.Blocks {
			for _, instr := range b.Instrs {
				st, ok := instr.(*ssa.Store)
				if !ok {
					continue
				}
				g, ok := st.Addr.(*ssa.Global)
				if !ok || !isIface(g.Type()) {
					continue
				}
				impl := recvNameFromValue(st.Val)
				if impl == "" {
					continue
				}
				if h := byRecv[impl]; h != nil {
					out[globalKey(g)] = h
					continue
				}
				if h := byRecv[impl+".Handler"]; h != nil {
					out[globalKey(g)] = h
				}
			}
		}
	}
	return out
}

func recvKey(t types.Type) string {
	if t == nil {
		return ""
	}
	return strings.TrimPrefix(types.TypeString(t, func(*types.Package) string { return "" }), "*")
}

func recvNameFromValue(v ssa.Value) string {
	switch x := v.(type) {
	case *ssa.MakeInterface:
		return recvNameFromValue(x.X)
	case *ssa.ChangeType:
		return recvNameFromValue(x.X)
	case *ssa.Alloc:
		t := x.Type()
		if p, ok := t.Underlying().(*types.Pointer); ok {
			return types.TypeString(p.Elem(), func(*types.Package) string { return "" })
		}
	}
	if v != nil && v.Type() != nil {
		return strings.TrimPrefix(types.TypeString(v.Type(), func(*types.Package) string { return "" }), "*")
	}
	return ""
}

func peelGlobal(v ssa.Value) *ssa.Global {
	for v != nil {
		switch x := v.(type) {
		case *ssa.Global:
			return x
		case *ssa.UnOp:
			v = x.X
		case *ssa.MakeInterface:
			v = x.X
		case *ssa.ChangeType:
			v = x.X
		case *ssa.Extract:
			v = x.Tuple
		default:
			return nil
		}
	}
	return nil
}

func ifaceSliceInvokes(fn *ssa.Function) []invoke {
	var out []invoke
	seen := map[string]bool{}
	for _, b := range fn.Blocks {
		for _, instr := range b.Instrs {
			c, ok := instr.(*ssa.Call)
			if !ok || !c.Call.IsInvoke() || c.Call.Method == nil {
				continue
			}
			if !recvFromIfaceSlice(c.Call.Value) {
				continue
			}
			m := c.Call.Method.Name()
			if isCommonIface(m) {
				continue
			}
			inv := invoke{
				iface:  types.TypeString(c.Call.Value.Type(), pkgName),
				method: m,
			}
			if seen[inv.String()] {
				continue
			}
			seen[inv.String()] = true
			out = append(out, inv)
		}
	}
	return out
}

func recvFromIfaceSlice(v ssa.Value) bool {
	for i := 0; i < 8 && v != nil; i++ {
		if isIfaceSlice(v.Type()) {
			return true
		}
		switch x := v.(type) {
		case *ssa.Extract:
			if next, ok := x.Tuple.(*ssa.Next); ok && next.IsString == false {
				if rng, ok := next.Iter.(*ssa.Range); ok {
					return isIfaceSlice(rng.X.Type())
				}
			}
			v = x.Tuple
		case *ssa.Index:
			return isIfaceSlice(x.X.Type())
		case *ssa.UnOp:
			v = x.X
		case *ssa.MakeInterface:
			v = x.X
		case *ssa.ChangeType:
			v = x.X
		case *ssa.Parameter:
			return isIfaceSlice(x.Type())
		default:
			return false
		}
	}
	return false
}

type invoke struct {
	iface, method string
	typ           *types.Interface // 被调接口；拿不到（如类型参数）时为 nil，退回按方法名匹配
}

func (i invoke) String() string {
	if i.iface != "" {
		return i.iface + "." + i.method
	}
	return i.method
}

func interfaceInvokes(fn *ssa.Function) []invoke {
	seen := map[string]bool{}
	var out []invoke
	for _, b := range fn.Blocks {
		for _, instr := range b.Instrs {
			c, ok := instr.(*ssa.Call)
			if !ok || !c.Call.IsInvoke() || c.Call.Method == nil {
				continue
			}
			m := c.Call.Method.Name()
			if m == "Error" || m == "String" {
				continue
			}
			iface := ""
			var typ *types.Interface
			if c.Call.Value != nil {
				iface = types.TypeString(c.Call.Value.Type(), func(p *types.Package) string {
					if p != nil {
						return p.Name()
					}
					return ""
				})
				typ, _ = c.Call.Value.Type().Underlying().(*types.Interface)
			}
			key := iface + "." + m
			if seen[key] {
				continue
			}
			seen[key] = true
			out = append(out, invoke{iface: iface, method: m, typ: typ})
		}
	}
	return out
}

// 本模块里真正实现了 inv.typ 的 inv.method。只按方法名匹配会把 redis.Cmdable.Get
// 误连到任意一个 Get 方法上。
func (w *walker) concreteImpls(inv invoke) []*callgraph.Node {
	var out []*callgraph.Node
	for fn, n := range w.cg.Nodes {
		if fn == nil || fn.Name() != inv.method || fn.Signature.Recv() == nil || !inModule(fn, w.mod) {
			continue
		}
		if noiseName(funcName(fn)) || strings.Contains(funcName(fn), "$") {
			continue
		}
		recv := fn.Signature.Recv().Type()
		if _, ok := recv.Underlying().(*types.Interface); ok {
			continue
		}
		if inv.typ != nil && !implements(recv, inv.typ) {
			continue
		}
		out = append(out, n)
	}
	sort.Slice(out, func(i, j int) bool { return funcName(out[i].Func) < funcName(out[j].Func) })
	return out
}

// recv 是 T 或 *T；T 和 *T 有一个实现了 iface 就算。
func implements(recv types.Type, iface *types.Interface) bool {
	if p, ok := recv.(*types.Pointer); ok {
		recv = p.Elem()
	}
	return types.Implements(recv, iface) || types.Implements(types.NewPointer(recv), iface)
}

func isCommonIface(name string) bool {
	switch name {
	case "Error", "String", "GoString", "Format":
		return true
	}
	return false
}

func pkgName(p *types.Package) string {
	if p == nil {
		return ""
	}
	return p.Name()
}

func skipCallee(fn *ssa.Function) bool {
	if fn == nil {
		return true
	}
	if fn.Name() == "Handler" || fn.Name() == "NeedRun" {
		return true
	}
	if strings.Contains(fn.Name(), "$") {
		return true
	}
	return noiseName(funcName(fn))
}

func (w *walker) baseNode(fn *ssa.Function) *outNode {
	out := &outNode{Name: shortName(fn), Pkg: pkgPath(fn), InMod: inModule(fn, w.mod)}
	out.File = w.fileOf(fn)
	out.Line = w.lineOf(fn)
	if s := fn.Syntax(); s != nil && fn.Prog != nil && s.End().IsValid() {
		out.EndLine = fn.Prog.Fset.Position(s.End()).Line
	}
	return out
}

func (w *walker) fileOf(fn *ssa.Function) string {
	if fn == nil || !fn.Pos().IsValid() || fn.Prog == nil {
		return ""
	}
	return relPath(fn.Prog.Fset.Position(fn.Pos()).Filename, w.absDir)
}

func (w *walker) lineOf(fn *ssa.Function) int {
	if fn == nil || !fn.Pos().IsValid() || fn.Prog == nil {
		return 0
	}
	return fn.Prog.Fset.Position(fn.Pos()).Line
}

func uniqueCallex(n *callgraph.Node) []*callgraph.Node {
	seen := map[string]*callgraph.Node{}
	for _, e := range n.Out {
		if e.Callee == nil || e.Callee.Func == nil {
			continue
		}
		seen[funcName(e.Callee.Func)] = e.Callee
	}
	out := make([]*callgraph.Node, 0, len(seen))
	for _, c := range seen {
		out = append(out, c)
	}
	sort.Slice(out, func(i, j int) bool { return funcName(out[i].Func) < funcName(out[j].Func) })
	return out
}

func printTree(n *outNode, prefix string, last, root bool) {
	if root {
		fmt.Printf("%s%s\n", n.Name, nodeExtra(n))
		for i, c := range n.Calls {
			printTree(c, "", i == len(n.Calls)-1, false)
		}
		return
	}
	branch := "├─ "
	next := prefix + "│  "
	if last {
		branch = "└─ "
		next = prefix + "   "
	}
	fmt.Printf("%s%s%s%s\n", prefix, branch, n.Name, nodeExtra(n))
	for i, c := range n.Calls {
		printTree(c, next, i == len(n.Calls)-1, false)
	}
}

func nodeExtra(n *outNode) string {
	extra := ""
	if n.File != "" {
		extra = fmt.Sprintf("  %s:%d", n.File, n.Line)
	}
	if n.Skipped != "" {
		extra += "  [" + n.Skipped + "]"
	}
	if n.Break != "" {
		extra += "  [" + n.Break + "]"
	}
	return extra
}

func funcName(fn *ssa.Function) string {
	if fn == nil {
		return "<nil>"
	}
	if fn.Pkg != nil {
		return fn.Pkg.Pkg.Path() + "." + fn.RelString(fn.Pkg.Pkg)
	}
	return fn.String()
}

func shortName(fn *ssa.Function) string {
	if fn == nil {
		return "<nil>"
	}
	if recv := fn.Signature.Recv(); recv != nil {
		return strings.TrimPrefix(types.TypeString(recv.Type(), func(p *types.Package) string { return "" }), "*") + "." + fn.Name()
	}
	if fn.Pkg != nil {
		return fn.Pkg.Pkg.Name() + "." + fn.Name()
	}
	return fn.Name()
}

func pkgPath(fn *ssa.Function) string {
	if fn == nil || fn.Pkg == nil {
		return ""
	}
	return fn.Pkg.Pkg.Path()
}

func skipExt(fn *ssa.Function) bool {
	p := pkgPath(fn)
	if p == "" {
		return true
	}
	for _, pre := range []string{
		"context", "fmt", "log", "time", "sync", "sort", "strings", "strconv",
		"bytes", "errors", "io", "os", "path", "reflect", "runtime", "unsafe",
		"encoding/", "net/", "crypto/", "golang.org/x/", "google.golang.org/",
		"github.com/golang/",
	} {
		if p == strings.TrimSuffix(pre, "/") || strings.HasPrefix(p, pre) {
			return true
		}
	}
	name := fn.Name()
	if name == "Value" || name == "Deadline" || name == "Done" || name == "Err" {
		return true
	}
	return false
}

func inModule(fn *ssa.Function, mod string) bool {
	p := pkgPath(fn)
	return p == mod || strings.HasPrefix(p, mod+"/")
}

func relPath(file, absDir string) string {
	if r, err := filepath.Rel(absDir, file); err == nil && !strings.HasPrefix(r, "..") {
		return r
	}
	return file
}

func readModulePath(dir string) string {
	b, err := os.ReadFile(filepath.Join(dir, "go.mod"))
	if err != nil {
		return ""
	}
	for _, line := range strings.Split(string(b), "\n") {
		line = strings.TrimSpace(line)
		if strings.HasPrefix(line, "module ") {
			return strings.TrimSpace(strings.TrimPrefix(line, "module "))
		}
	}
	return ""
}

func must(err error) {
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
