/* interfaces-analyze 左右展开调用链脑图渲染器
 *
 * 数据来自 ?json= 的绝对路径（skill 常驻服务），或同名 .json / #mm-app[data-src]。HTML 只是壳。
 * 页头、图例、画布、右侧详情、术语表全部由这里生成。
 * 右侧改节点即改 JSON，保存写回（或下载）那份文件。
 * 数据格式见 skill 目录下的 HTML-FORMAT.md。
 */
(function () {
  'use strict';

  var TYPES = {
    root:    { label: '中心', color: '#111111' },
    section: { label: '章节', color: '#3d5a80' },
    quote:   { label: '原文', color: '#5c6b73' },
    proto:   { label: '协议', color: '#444444' },
    entry:   { label: '入口', color: '#6a4c93' },
    branch:  { label: '分支', color: '#b08900' },
    db:      { label: 'DB',   color: '#2d6a4f' },
    rpc:     { label: 'RPC',  color: '#1a5f7a' },
    cache:   { label: '缓存', color: '#c2410c' },
    loop:    { label: '循环', color: '#7a5195' },
    build:   { label: '组装', color: '#555555' },
    step:    { label: '步骤', color: '#9a9a8f' }
  };

  var LEGEND_ORDER = ['section', 'quote', 'proto', 'entry', 'branch', 'db', 'rpc', 'cache', 'loop', 'build', 'step'];
  var NODE_KEYS = ['t', 'type', 'src', 'log', 'note', 'code', 'sql', 'req', 'rsp', 'sample', 'shot', 'warn', 'todo', 'fold', 'open', 'kids'];
  var META_KEYS = ['kind', 'center', 'source', 'service', 'interface', 'proto', 'impl', 'branch', 'commit', 'index', 'openDepth'];
  var CARD_KEYS = { t: 1, type: 1, code: 1, sql: 1, req: 1, rsp: 1, sample: 1, shot: 1, warn: 1, todo: 1 };
  var FIELD_DEFS = [
    { key: 'src', label: '出处', kind: 'src', placeholder: 'path:line 或章节' },
    { key: 'log', label: '日志', kind: 'pre', placeholder: '日志格式串（文件:行）；没有日志写 无' },
    { key: 'note', label: '解读', kind: 'note' },
    { key: 'sql', label: 'SQL', kind: 'pre' },
    { key: 'req', label: '请求参数', kind: 'pre' },
    { key: 'rsp', label: '响应关键字段', kind: 'pre' },
    { key: 'code', label: '摘录', kind: 'pre' },
    { key: 'sample', label: '真实样例', kind: 'sample', placeholder: '原文摘录、日志；截图直接粘贴' },
    { key: 'warn', label: '材料和事实不一致', kind: 'warn' },
    { key: 'todo', label: '待确认', kind: 'todo' }
  ];

  function queryParam(name) {
    try { return new URLSearchParams(location.search).get(name) || ''; }
    catch (e) { return ''; }
  }

  function fileApi(abs) {
    return '/file?path=' + encodeURIComponent(abs);
  }

  function jsonAbs() {
    return queryParam('json');
  }

  function analysisDirOfJson() {
    var abs = jsonAbs();
    var i = abs.lastIndexOf('/');
    return i > 0 ? abs.slice(0, i) : '';
  }

  // 分析根目录名：analysis，也认旧名 jkanalysis
  var ROOT_NAMES = { jkanalysis: true, analysis: true };

  function pathSegs(abs) {
    var parts = String(abs || '').split('/');
    var segs = [];
    var cur = '';
    var i;
    for (i = 0; i < parts.length; i++) {
      if (!parts[i]) { continue; }
      cur += '/' + parts[i];
      segs.push({ name: parts[i], path: cur });
    }
    return segs;
  }

  function fillCrumb(nav, dir, leaf) {
    var segs = pathSegs(dir);
    var start = 0;
    var i, a, span, slice;
    nav.innerHTML = '';
    for (i = 0; i < segs.length; i++) {
      if (ROOT_NAMES[segs[i].name]) { start = i; break; }
    }
    slice = segs.slice(start);
    if (!slice.length) { nav.hidden = true; return; }
    nav.hidden = false;
    for (i = 0; i < slice.length; i++) {
      if (nav.childNodes.length) { nav.appendChild(document.createTextNode(' / ')); }
      if (i === slice.length - 1 && !leaf) {
        span = document.createElement('span');
        span.textContent = slice[i].name;
        nav.appendChild(span);
      } else {
        a = document.createElement('a');
        a.href = '/list?dir=' + encodeURIComponent(slice[i].path);
        a.textContent = slice[i].name;
        nav.appendChild(a);
      }
    }
    if (leaf) {
      nav.appendChild(document.createTextNode(' / '));
      span = document.createElement('span');
      span.textContent = leaf;
      nav.appendChild(span);
    }
  }

  function shotSrc(rel) {
    if (!rel) { return ''; }
    if (/^(https?:|data:|blob:)/i.test(rel) || rel.indexOf('/file?') === 0) { return rel; }
    var dir = analysisDirOfJson();
    if (!dir) { return rel; }
    var abs = rel.charAt(0) === '/' ? rel : (dir + '/' + String(rel).replace(/^\.\//, ''));
    return fileApi(abs);
  }

  function siblingJsonUrl() {
    var path = location.pathname || '';
    try { path = decodeURIComponent(path); } catch (e) {}
    var name = path.substring(path.lastIndexOf('/') + 1);
    if (!/\.html?$/i.test(name)) { return ''; }
    return name.replace(/\.html?$/i, '.json');
  }

  function jsonUrl() {
    var abs = jsonAbs();
    if (abs) { return fileApi(abs); }
    var app = document.getElementById('mm-app');
    var src = app && app.getAttribute('data-src');
    return src || siblingJsonUrl();
  }

  function readInline() {
    var el = document.getElementById('mm-data');
    if (!el) { return null; }
    var text = el.textContent;
    if (!text || !String(text).trim()) { return null; }
    return JSON.parse(text);
  }

  function showBoot(msg, isErr) {
    var app = document.getElementById('mm-app') || document.body;
    app.innerHTML = '';
    var p = document.createElement('p');
    p.className = 'mm-boot-msg' + (isErr ? ' mm-boot-msg--err' : '');
    p.textContent = msg;
    app.appendChild(p);
  }

  function start() {
    try {
      var inline = readInline();
      if (inline) { boot(inline, jsonUrl() || 'interface.json'); return; }
    } catch (e) {
      showBoot('内联 JSON 解析失败：' + e.message, true);
      return;
    }
    var url = jsonUrl();
    if (!url) {
      showBoot('地址上缺 json。\nanalyze_server /path/to/analysis/<中心>.json\n\n也可直接把 .json 文件拖到当前页面打开 /view?json=路径', true);
      return;
    }
    showBoot('加载 ' + (jsonAbs() || url) + ' …');
    fetch(url, { cache: 'no-store' }).then(function (r) {
      if (!r.ok) { throw new Error(url + ' HTTP ' + r.status); }
      return r.text();
    }).then(function (text) {
      var data;
      try { data = JSON.parse(text); }
      catch (e) { throw new Error(url + ' 不是合法 JSON：' + e.message); }
      boot(data, url);
    }).catch(function (e) {
      showBoot(
        '无法加载 ' + (jsonAbs() || url) + '\n' + e.message +
        '\n\n用 analyze_server 打开这份 JSON。',
        true
      );
    });
  }

  function boot(DATA, sourceUrl) {
    if (!DATA.meta) { DATA.meta = {}; }
    if (!DATA.terms) { DATA.terms = []; }
    if (!DATA.tree) { DATA.tree = { t: '未命名', type: 'root', kids: [] }; }
    var META = DATA.meta;
    var OPEN_DEPTH = typeof META.openDepth === 'number' ? META.openDepth : 2;
    var saveUrl = String(sourceUrl || 'interface.json');
    var dirty = false;
    var saveTimer = 0;
    var saving = false;
    var saveAgain = false;
    var nodes = [];
    var selected = null;
    var renderTimer = 0;
    var liveEdit = null;
    var showMeta = false;

    function reindex() {
      nodes = [];
      (function walk(node, depth, parent) {
        node._id = nodes.length;
        node._depth = depth;
        node._parent = parent;
        if (!Array.isArray(node.kids)) { node.kids = []; }
        node._kids = node.kids;
        if (typeof node._open !== 'boolean') {
          if (node.open === true) { node._open = true; }
          else if (node.fold === true) { node._open = false; }
          else { node._open = depth < OPEN_DEPTH; }
        }
        nodes.push(node);
        for (var i = 0; i < node.kids.length; i++) { walk(node.kids[i], depth + 1, node); }
        node._leafCount = node.kids.length ? node.kids.reduce(function (s, k) { return s + k._leafCount; }, 0) : 1;
      })(DATA.tree, 0, null);
    }
    reindex();

    function noLog(n) { return typeof n.log === 'string' && n.log.trim() === '无'; }
    function hasEvidence(n) { return !!(n.code || n.sql || n.req || n.rsp || n.sample || n.shot); }
    function fieldVisible(n, def) {
      if (def.key === 'sample') { return !!(n.sample || n.shot); }
      return !!n[def.key];
    }

    function pageTitle() {
      if (META.center) { return META.center; }
      return (META.service ? META.service + ' · ' : '') + (META.interface || DATA.tree.t || '脑图');
    }

    // ---------- 骨架 ----------

    var app = document.getElementById('mm-app') || document.body;
    app.innerHTML = '';

    var head = el('div', 'mm-head');
    var crumb = el('nav', 'mm-crumb');
    head.appendChild(crumb);
    var h1 = el('h1');
    head.appendChild(h1);
    var metaSlot = el('span', 'mm-meta-slot');
    head.appendChild(metaSlot);
    var spacer = el('span', 'mm-spacer');
    head.appendChild(spacer);
    head.appendChild(btn('全部展开', function () { setAll(true); }));
    head.appendChild(btn('收起到两层', function () { resetOpen(); }));
    var saveMsg = el('span', 'mm-save-msg');
    head.appendChild(saveMsg);
    app.appendChild(head);

    function paintHeadMeta() {
      metaSlot.innerHTML = '';
      ['source', 'proto', 'impl', 'branch', 'commit'].forEach(function (k) {
        if (!META[k]) { return; }
        var s = el('span', 'mm-meta');
        s.textContent = ({ source: '材料 ', proto: '协议 ', impl: '实现 ', branch: '分支 ', commit: 'commit ' })[k] + META[k];
        metaSlot.appendChild(s);
      });
      var dir = analysisDirOfJson();
      var abs = jsonAbs();
      var leaf = '';
      if (abs) {
        var slash = abs.lastIndexOf('/');
        leaf = slash >= 0 ? abs.slice(slash + 1) : abs;
      }
      fillCrumb(crumb, dir, leaf);
    }

    function syncHead() {
      h1.textContent = pageTitle();
      document.title = (dirty ? '* ' : '') + pageTitle();
      paintHeadMeta();
    }

    var legend = el('div', 'mm-legend');
    var used = {};
    nodes.forEach(function (n) {
      if (n.type && TYPES[n.type] && n.type !== 'root') { used[n.type] = 1; }
    });
    (LEGEND_ORDER.filter(function (k) { return used[k]; }).length
      ? LEGEND_ORDER.filter(function (k) { return used[k]; })
      : LEGEND_ORDER).forEach(function (k) {
      var s = el('span');
      var i = el('i');
      i.style.background = TYPES[k].color;
      s.appendChild(i);
      s.appendChild(document.createTextNode(TYPES[k].label));
      legend.appendChild(s);
    });
    var hint = el('span');
    hint.style.marginLeft = 'auto';
    hint.textContent = '点节点看证据 · 点右侧文字可改 · 空项用＋字段补 · 改完自动保存 · ⌘+滚轮缩放 · 方向键切换节点';
    legend.appendChild(hint);
    app.appendChild(legend);

    var body = el('div', 'mm-body');
    var stage = el('div', 'mm-stage');
    var wrap = el('div', 'mm-canvas-wrap');
    var sizer = el('div', 'mm-sizer');
    var canvas = el('div', 'mm-canvas');
    var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    canvas.appendChild(svg);
    sizer.appendChild(canvas);
    wrap.appendChild(sizer);
    stage.appendChild(wrap);
    var zoomBar = el('div', 'mm-zoom');
    zoomBar.title = '⌘ + 滚轮缩放';
    var zoomOutBtn = btn('−', function () { setZoom(zoom / 1.15); });
    var zoomPctBtn = btn('100%', function () { setZoom(1); });
    zoomPctBtn.title = '回到 100%';
    zoomPctBtn.classList.add('mm-zoom-pct');
    var zoomInBtn = btn('+', function () { setZoom(zoom * 1.15); });
    zoomBar.appendChild(zoomOutBtn);
    zoomBar.appendChild(zoomPctBtn);
    zoomBar.appendChild(zoomInBtn);
    stage.appendChild(zoomBar);
    body.appendChild(stage);
    var split = el('div', 'mm-split');
    split.setAttribute('role', 'separator');
    split.setAttribute('aria-orientation', 'vertical');
    split.setAttribute('aria-label', '拖动调整详情栏宽度');
    split.title = '拖动调整详情栏宽度';
    body.appendChild(split);
    var panel = el('div', 'mm-panel');
    body.appendChild(panel);
    app.appendChild(body);
    enableSplit(split, panel, body);
    enablePan(wrap);
    enableZoom(wrap);

    var termsBox = el('div', 'mm-terms');
    app.appendChild(termsBox);

    // ---------- 渲染 ----------

    var NODE_W = px('--node-w', 250);
    var COL_GAP = px('--col-gap', 66);
    var ROW_GAP = px('--row-gap', 14);

    function visibleTree(node, out) {
      out.push(node);
      if (node._open) { node._kids.forEach(function (k) { visibleTree(k, out); }); }
      return out;
    }

    function render() {
      var vis = visibleTree(DATA.tree, []);
      Array.prototype.slice.call(canvas.querySelectorAll('.mm-node')).forEach(function (n) { n.remove(); });

      vis.forEach(function (n) {
        var d = el('div', 'mm-node t-' + (n.type || 'step'));
        d.style.left = (n._depth * (NODE_W + COL_GAP)) + 'px';
        d.style.top = '0px';
        d.appendChild(title(n));
        if (hasEvidence(n) || n.warn || n.todo || noLog(n)) {
          var flags = el('div', 'mm-flags');
          if (noLog(n)) { flags.appendChild(flag('mm-flag--nolog', '∅')); }
          if (hasEvidence(n)) { flags.appendChild(flag('mm-flag--ev', '证')); }
          if (n.warn) { flags.appendChild(flag('mm-flag--warn', '!')); }
          if (n.todo) { flags.appendChild(flag('mm-flag--todo', '?')); }
          d.appendChild(flags);
        }
        if (n._kids.length) {
          var t = el('div', 'mm-toggle');
          t.textContent = n._open ? '−' : '+';
          if (!n._open) {
            var c = el('span', 'mm-cnt');
            c.textContent = n._leafCount > 1 ? String(n._leafCount) : '';
            t.textContent = '';
            t.appendChild(document.createTextNode('+'));
            if (c.textContent) { t.title = '展开 ' + n._leafCount + ' 个末端节点'; }
          }
          t.addEventListener('click', function (e) {
            e.stopPropagation();
            n._open = !n._open;
            render();
          });
          d.appendChild(t);
        }
        d.addEventListener('click', function () { select(n); });
        if (selected === n) { d.classList.add('is-sel'); }
        n._el = d;
        canvas.appendChild(d);
      });

      vis.forEach(function (n) { n._h = n._el.offsetHeight; });

      var cursor = 20;
      (function place(n) {
        if (n._open && n._kids.length) {
          n._kids.forEach(place);
          var first = n._kids[0], last = n._kids[n._kids.length - 1];
          n._y = (first._y + last._y) / 2;
        } else {
          n._y = cursor + n._h / 2;
          cursor += n._h + ROW_GAP;
        }
      })(DATA.tree);

      var maxX = 0, maxY = 0;
      vis.forEach(function (n) {
        n._x = n._depth * (NODE_W + COL_GAP);
        n._el.style.left = n._x + 'px';
        n._el.style.top = (n._y - n._h / 2) + 'px';
        maxX = Math.max(maxX, n._x + NODE_W);
        maxY = Math.max(maxY, n._y + n._h / 2);
      });

      baseW = maxX + 40;
      baseH = maxY + 40;
      canvas.style.width = baseW + 'px';
      canvas.style.height = baseH + 'px';
      svg.setAttribute('width', baseW);
      svg.setAttribute('height', baseH);
      applyZoom();

      while (svg.firstChild) { svg.removeChild(svg.firstChild); }
      vis.forEach(function (n) {
        if (!n._open) { return; }
        n._kids.forEach(function (k) {
          var x1 = n._x + NODE_W, y1 = n._y, x2 = k._x, y2 = k._y;
          var mx = x1 + (x2 - x1) / 2;
          var p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
          p.setAttribute('d', 'M' + x1 + ',' + y1 + ' C' + mx + ',' + y1 + ' ' + mx + ',' + y2 + ' ' + x2 + ',' + y2);
          svg.appendChild(p);
        });
      });
    }

    function title(n) {
      var box = el('span', 'mm-title');
      var parts = String(n.t || '').split('|');
      var act = el('span', 'mm-act');
      act.textContent = parts[0].trim() || '未命名';
      box.appendChild(act);
      if (parts[1] && parts[1].trim()) {
        box.appendChild(document.createTextNode(' '));
        var slot = el('span', 'mm-slot');
        slot.textContent = parts[1].trim();
        box.appendChild(slot);
      }
      if (parts[2] && parts[2].trim()) {
        box.appendChild(document.createElement('br'));
        var dep = el('span', 'mm-dep');
        dep.textContent = parts.slice(2).join('|').trim();
        box.appendChild(dep);
      }
      return box;
    }

    function scheduleRender() {
      clearTimeout(renderTimer);
      renderTimer = setTimeout(render, 80);
    }

    // ---------- 详情面板（可编辑） ----------

    function commitLive() {
      if (!liveEdit) { return; }
      var fn = liveEdit.commit;
      liveEdit = null;
      fn();
    }

    function select(n, force) {
      if (!n) { return; }
      var same = selected === n;
      selected = n;
      Array.prototype.slice.call(canvas.querySelectorAll('.mm-node')).forEach(function (d) { d.classList.remove('is-sel'); });
      if (n._el) {
        n._el.classList.add('is-sel');
        n._el.scrollIntoView({ block: 'nearest', inline: 'nearest' });
      }
      if (same && !force && panel.firstChild) { return; }
      commitLive();
      fillPanel(n);
    }

    function refill(n) {
      var y = panel.scrollTop;
      commitLive();
      fillPanel(n);
      panel.scrollTop = y;
    }

    function fillPanel(n) {
      panel.innerHTML = '';

      var bar = el('div', 'mm-panel-bar');
      var h = el('h2', 'mm-editable');
      h.tabIndex = 0;
      h.textContent = String(n.t || '').split('|')[0].trim() || '未命名';
      h.title = '点击修改标题';
      h.addEventListener('click', function () { editTitle(n, h); });
      bar.appendChild(h);
      bar.appendChild(moreMenu(n));
      panel.appendChild(bar);

      var kind = el('span', 'mm-kind');
      var ty = TYPES[n.type] || TYPES.step;
      kind.textContent = ty.label;
      kind.style.background = ty.color;
      if (n._parent) {
        kind.className += ' mm-editable';
        kind.tabIndex = 0;
        kind.title = '点击改类型';
        kind.addEventListener('click', function () { editType(n, kind); });
      }
      panel.appendChild(kind);

      FIELD_DEFS.forEach(function (def) {
        if (!fieldVisible(n, def)) { return; }
        panel.appendChild(viewField(n, def));
      });

      if (!n.src && !n.note && !hasEvidence(n) && !n.warn && !n.todo) {
        var empty = el('p', 'mm-empty');
        empty.textContent = '这个节点只做归纳，证据在它的子节点里。';
        panel.appendChild(empty);
      }

      var extras = el('div', 'mm-panel-extras');
      extras.appendChild(addFieldMenu(n));
      extras.appendChild(btn('＋ 子节点', function () { addChild(n); }));
      panel.appendChild(extras);

      if (!n._parent && showMeta) { metaFields(); }
    }

    function viewField(n, def) {
      var wrap = el('div', 'mm-field');
      wrap.setAttribute('data-key', def.key);
      var lab = el('h3');
      lab.textContent = def.label;
      wrap.appendChild(lab);
      if (def.kind === 'sample') {
        wrap.appendChild(sampleBox(n, wrap, def));
        return wrap;
      }
      var box = displayBox(def.kind, n[def.key]);
      box.title = '点击修改';
      box.addEventListener('click', function () { startEdit(wrap, n, def); });
      wrap.appendChild(box);
      return wrap;
    }

    function sampleBox(n, wrap, def) {
      var box = el('div', 'mm-sample');
      box.tabIndex = 0;
      box.title = '可直接粘贴截图';
      if (n.sample) {
        var pre = el('pre', 'mm-editable');
        pre.tabIndex = 0;
        pre.textContent = n.sample;
        pre.title = '点击修改文字';
        pre.addEventListener('click', function () { startEdit(wrap, n, def); });
        box.appendChild(pre);
      } else {
        var hint = el('p', 'mm-empty mm-editable');
        hint.tabIndex = 0;
        hint.textContent = n.shot ? '再写文字就点这里' : '写文字，或直接粘贴截图';
        hint.addEventListener('click', function () { startEdit(wrap, n, def); });
        box.appendChild(hint);
      }
      if (n.shot) { box.appendChild(shotFigure(n, wrap, def)); }
      box.addEventListener('paste', function (e) {
        acceptShot(e, n, function () { refill(n); });
      });
      return box;
    }

    function dropField(wrap) {
      wrap.remove();
      if (!selected) { return; }
      var n = selected;
      if (!n.src && !n.note && !hasEvidence(n) && !n.warn && !n.todo && !panel.querySelector('.mm-empty')) {
        var empty = el('p', 'mm-empty');
        empty.textContent = '这个节点只做归纳，证据在它的子节点里。';
        panel.insertBefore(empty, panel.querySelector('.mm-panel-extras'));
      }
    }

    function openShot(src) {
      if (!src) { return; }
      var prev = document.querySelector('.mm-lightbox');
      if (prev) { prev.remove(); }
      var box = el('div', 'mm-lightbox');
      box.setAttribute('role', 'dialog');
      box.setAttribute('aria-label', '贴图放大');
      var big = el('img');
      big.src = src;
      big.alt = '样例截图';
      box.appendChild(big);
      function close() {
        document.removeEventListener('keydown', onKey);
        box.remove();
      }
      function onKey(e) {
        if (e.key === 'Escape') { e.preventDefault(); close(); }
      }
      box.addEventListener('click', close);
      document.addEventListener('keydown', onKey);
      document.body.appendChild(box);
    }

    function shotFigure(n, wrap, def) {
      var fig = el('div', 'mm-shot');
      var img = el('img');
      img.src = shotSrc(n.shot);
      img.alt = '样例截图';
      img.title = '点击放大';
      img.addEventListener('mousedown', function (e) { e.preventDefault(); });
      img.addEventListener('click', function (e) {
        e.stopPropagation();
        openShot(shotSrc(n.shot));
      });
      fig.appendChild(img);
      var rm = btn('去掉贴图', function () {
        delete n.shot;
        markDirty();
        scheduleRender();
        if (wrap.classList.contains('is-edit')) {
          var slot = wrap.querySelector('.mm-shot-slot');
          if (slot) { slot.innerHTML = ''; }
          return;
        }
        if (!n.sample) { dropField(wrap); return; }
        refill(n);
      });
      rm.addEventListener('mousedown', function (e) { e.preventDefault(); });
      fig.appendChild(rm);
      return fig;
    }

    function clipImage(dt) {
      if (!dt) { return null; }
      var i, f;
      if (dt.files) {
        for (i = 0; i < dt.files.length; i++) {
          if (/^image\//.test(dt.files[i].type)) { return dt.files[i]; }
        }
      }
      if (dt.items) {
        for (i = 0; i < dt.items.length; i++) {
          if (dt.items[i].kind === 'file' && /^image\//.test(dt.items[i].type)) {
            f = dt.items[i].getAsFile();
            if (f) { return f; }
          }
        }
      }
      return null;
    }

    function acceptShot(e, n, onDone) {
      var file = clipImage(e.clipboardData);
      if (!file) { return false; }
      e.preventDefault();
      e.stopPropagation();
      var ext = file.type === 'image/jpeg' ? 'jpg' : file.type === 'image/gif' ? 'gif' : file.type === 'image/webp' ? 'webp' : 'png';
      var stemSrc = jsonAbs() || saveUrl.split('?')[0];
      var stem = stemSrc.replace(/^.*\//, '').replace(/\.json$/i, '').replace(/[^A-Za-z0-9._-]+/g, '_');
      var rel = 'assets/shots/' + stem + '-' + (n._id || 0) + '-' + Date.now() + '.' + ext;
      var dir = analysisDirOfJson();
      var upload = dir ? fileApi(dir + '/' + rel) : rel;
      setSaveMsg('上传贴图…');
      fetch(upload, {
        method: 'PUT',
        headers: { 'Content-Type': file.type || 'image/png' },
        body: file
      }).then(function (r) {
        if (!r.ok) { throw new Error('HTTP ' + r.status); }
        n.shot = rel;
        markDirty();
        scheduleRender();
        if (onDone) { onDone(); }
      }).catch(function () {
        setSaveMsg('贴图保存失败。确认 serve.sh 在跑，JSON 在某个 analysis 目录里');
      });
      return true;
    }

    function displayBox(kind, value) {
      var box;
      if (kind === 'pre') { box = el('pre'); }
      else if (kind === 'src') { box = el('p', 'mm-src'); }
      else if (kind === 'note') { box = el('p', 'mm-note'); }
      else if (kind === 'todo') { box = el('div', 'mm-todo'); }
      else if (kind === 'warn') { box = el('div', 'mm-warn'); }
      else { box = el('p'); }
      box.classList.add('mm-editable');
      box.tabIndex = 0;
      box.textContent = value;
      return box;
    }

    function makeEditor(kind, value, placeholder) {
      var box;
      if (kind === 'line' || kind === 'src') {
        box = el('input');
        box.type = 'text';
        if (kind === 'src') { box.className = 'mm-src'; }
      } else {
        box = el('textarea');
        if (kind === 'pre' || kind === 'sample') { box.className = 'mm-pre'; }
        else if (kind === 'todo') { box.className = 'mm-todo'; }
        else if (kind === 'warn') { box.className = 'mm-warn'; }
      }
      box.value = value || '';
      if (placeholder) { box.placeholder = placeholder; }
      return box;
    }

    function startEdit(wrap, n, def) {
      commitLive();
      var was = n[def.key] || '';
      while (wrap.lastChild && wrap.lastChild.tagName !== 'H3') { wrap.removeChild(wrap.lastChild); }
      if (!wrap.firstChild) {
        var lab = el('h3');
        lab.textContent = def.label;
        wrap.appendChild(lab);
      }
      var box = makeEditor(def.kind, was, def.placeholder);
      wrap.appendChild(box);
      var shotSlot = null;
      if (def.kind === 'sample') {
        shotSlot = el('div', 'mm-shot-slot');
        if (n.shot) { shotSlot.appendChild(shotFigure(n, wrap, def)); }
        var hint = el('p', 'mm-sample-hint');
        hint.textContent = '截图后在此粘贴，一张';
        wrap.appendChild(shotSlot);
        wrap.appendChild(hint);
        box.addEventListener('paste', function (e) {
          acceptShot(e, n, function () {
            if (!shotSlot) { return; }
            shotSlot.innerHTML = '';
            if (n.shot) { shotSlot.appendChild(shotFigure(n, wrap, def)); }
          });
        });
      }
      wrap.classList.add('is-edit');
      if (box.tagName === 'TEXTAREA') { autoresize(box); }
      function commit() {
        wrap.classList.remove('is-edit');
        var v = box.value;
        if (v !== was) {
          if (v) { n[def.key] = v; }
          else { delete n[def.key]; }
          markDirty();
          if (CARD_KEYS[def.key]) { scheduleRender(); }
        }
        while (wrap.lastChild && wrap.lastChild.tagName !== 'H3') { wrap.removeChild(wrap.lastChild); }
        if (!fieldVisible(n, def)) {
          dropField(wrap);
          return;
        }
        if (def.kind === 'sample') {
          wrap.appendChild(sampleBox(n, wrap, def));
          return;
        }
        var shown = displayBox(def.kind, n[def.key]);
        shown.title = '点击修改';
        shown.addEventListener('click', function () { startEdit(wrap, n, def); });
        wrap.appendChild(shown);
      }
      liveEdit = { commit: commit };
      box.addEventListener('blur', function () {
        if (!liveEdit) { return; }
        liveEdit = null;
        commit();
      });
      box.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
          e.preventDefault();
          box.value = was;
          box.blur();
        }
        if (e.key === 'Enter' && box.tagName === 'INPUT') {
          e.preventDefault();
          box.blur();
        }
      });
      box.focus();
      if (box.tagName === 'INPUT') { box.select(); }
    }

    function editTitle(n, h) {
      commitLive();
      var was = n.t || '';
      var box = el('input');
      box.type = 'text';
      box.value = was;
      box.placeholder = '动作 | 落点 | 依赖';
      h.replaceWith(box);
      function commit() {
        var v = box.value;
        if (v !== was) {
          n.t = v;
          markDirty();
          scheduleRender();
          if (!n._parent) { syncHead(); }
        }
        var next = el('h2', 'mm-editable');
        next.tabIndex = 0;
        next.textContent = String(n.t || '').split('|')[0].trim() || '未命名';
        next.title = '点击修改标题';
        next.addEventListener('click', function () { editTitle(n, next); });
        if (box.parentNode) { box.replaceWith(next); }
      }
      liveEdit = { commit: commit };
      box.addEventListener('blur', function () {
        if (!liveEdit) { return; }
        liveEdit = null;
        commit();
      });
      box.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') { e.preventDefault(); box.value = was; box.blur(); }
        if (e.key === 'Enter') { e.preventDefault(); box.blur(); }
      });
      box.focus();
      box.select();
    }

    function editType(n, kindEl) {
      commitLive();
      var was = n.type && TYPES[n.type] ? n.type : 'step';
      var box = el('select');
      Object.keys(TYPES).forEach(function (k) {
        var o = document.createElement('option');
        o.value = k;
        o.textContent = TYPES[k].label + ' · ' + k;
        box.appendChild(o);
      });
      box.value = was;
      kindEl.replaceWith(box);
      function paintKind() {
        var next = el('span', 'mm-kind mm-editable');
        var t = TYPES[n.type] || TYPES.step;
        next.textContent = t.label;
        next.style.background = t.color;
        next.tabIndex = 0;
        next.title = '点击改类型';
        next.addEventListener('click', function () { editType(n, next); });
        if (box.parentNode) { box.replaceWith(next); }
      }
      function commit() {
        if (box.value !== was) {
          n.type = box.value;
          markDirty();
          scheduleRender();
        }
        paintKind();
      }
      liveEdit = { commit: commit };
      box.addEventListener('change', function () { box.blur(); });
      box.addEventListener('blur', function () {
        if (!liveEdit) { return; }
        liveEdit = null;
        commit();
      });
      box.focus();
    }

    function addFieldMenu(n) {
      var box = el('details', 'mm-add');
      var sum = el('summary');
      sum.textContent = '＋ 字段';
      box.appendChild(sum);
      var list = el('div', 'mm-add-list');
      var missing = FIELD_DEFS.filter(function (def) { return !fieldVisible(n, def); });
      if (!missing.length) {
        var none = el('span', 'mm-empty');
        none.textContent = '字段都齐了';
        list.appendChild(none);
      } else {
        missing.forEach(function (def) {
          list.appendChild(btn(def.label, function () {
            box.open = false;
            addField(n, def);
          }));
        });
      }
      box.appendChild(list);
      return box;
    }

    function addField(n, def) {
      commitLive();
      var empty = panel.querySelector('.mm-empty');
      if (empty) { empty.remove(); }
      var wrap = el('div', 'mm-field');
      wrap.setAttribute('data-key', def.key);
      panel.insertBefore(wrap, panel.querySelector('.mm-panel-extras'));
      startEdit(wrap, n, def);
    }

    function moreMenu(n) {
      var box = el('details', 'mm-more');
      var sum = el('summary');
      sum.textContent = '⋯';
      sum.title = '结构调整';
      box.appendChild(sum);
      var menu = el('div', 'mm-more-menu');
      var i = n._parent ? n._parent.kids.indexOf(n) : -1;
      var up = btn('上移', function () { box.open = false; moveNode(n, -1); });
      var down = btn('下移', function () { box.open = false; moveNode(n, 1); });
      var del = btn('删除', function () { box.open = false; removeNode(n); });
      del.className += ' mm-btn--danger';
      up.disabled = !n._parent || i <= 0;
      down.disabled = !n._parent || i < 0 || i >= n._parent.kids.length - 1;
      del.disabled = !n._parent;
      menu.appendChild(up);
      menu.appendChild(down);
      menu.appendChild(del);
      menu.appendChild(check('默认展开', n.open === true, function (on) {
        if (on) { n.open = true; delete n.fold; }
        else { delete n.open; }
        markDirty();
      }));
      menu.appendChild(check('默认折叠', n.fold === true, function (on) {
        if (on) { n.fold = true; delete n.open; }
        else { delete n.fold; }
        markDirty();
      }));
      if (!n._parent) {
        menu.appendChild(btn(showMeta ? '收起页头' : '改页头', function () {
          showMeta = !showMeta;
          refill(n);
        }));
      }
      menu.appendChild(btn('＋ 术语', function () {
        box.open = false;
        addTerm();
      }));
      box.appendChild(menu);
      return box;
    }

    function check(label, on, fn) {
      var lab = el('label', 'mm-check');
      var box = el('input');
      box.type = 'checkbox';
      box.checked = on;
      box.addEventListener('change', function () { fn(box.checked, box); });
      lab.appendChild(box);
      lab.appendChild(document.createTextNode(' ' + label));
      return lab;
    }

    function metaFields() {
      var wrap = el('div', 'mm-field');
      var lab = el('label');
      lab.textContent = '页头';
      wrap.appendChild(lab);
      panel.appendChild(wrap);
      metaLine('kind', '种类');
      metaLine('center', '中心');
      metaLine('source', '材料');
      metaLine('service', '服务名');
      metaLine('interface', '接口名');
      metaLine('proto', '协议');
      metaLine('impl', '实现');
      metaLine('branch', '分支');
      metaLine('commit', 'commit');
      metaLine('index', '清单页');
      var od = el('div', 'mm-field');
      var odl = el('label');
      odl.textContent = '初始展开层数';
      od.appendChild(odl);
      var odi = el('input');
      odi.type = 'number';
      odi.min = '0';
      odi.max = '20';
      odi.value = String(typeof META.openDepth === 'number' ? META.openDepth : 2);
      odi.addEventListener('input', function () {
        var v = parseInt(odi.value, 10);
        if (isNaN(v)) { delete META.openDepth; }
        else { META.openDepth = v; OPEN_DEPTH = v; }
        markDirty();
      });
      od.appendChild(odi);
      panel.appendChild(od);
    }

    function metaLine(key, label) {
      var wrap = el('div', 'mm-field');
      var lab = el('label');
      lab.textContent = label;
      wrap.appendChild(lab);
      var box = el('input');
      box.type = 'text';
      box.value = META[key] || '';
      box.addEventListener('input', function () {
        var v = box.value;
        if (v) { META[key] = v; }
        else { delete META[key]; }
        markDirty();
        syncHead();
      });
      wrap.appendChild(box);
      panel.appendChild(wrap);
    }

    function addChild(parent) {
      var child = { t: '新步骤', type: 'step', kids: [] };
      parent.kids.push(child);
      parent._open = true;
      reindex();
      markDirty();
      render();
      select(child, true);
    }

    function removeNode(n) {
      if (!n._parent) { return; }
      if (n.kids && n.kids.length) {
        if (!window.confirm('删除「' + (n.t || '未命名') + '」以及它下面的节点？')) { return; }
      }
      var arr = n._parent.kids;
      var i = arr.indexOf(n);
      if (i < 0) { return; }
      arr.splice(i, 1);
      var parent = n._parent;
      reindex();
      markDirty();
      render();
      select(parent, true);
    }

    function moveNode(n, dir) {
      if (!n._parent) { return; }
      var arr = n._parent.kids;
      var i = arr.indexOf(n);
      var j = i + dir;
      if (i < 0 || j < 0 || j >= arr.length) { return; }
      arr.splice(i, 1);
      arr.splice(j, 0, n);
      reindex();
      markDirty();
      render();
      select(n, true);
    }

    // ---------- 术语 ----------

    function paintTerms() {
      termsBox.innerHTML = '';
      if (!DATA.terms.length) {
        termsBox.hidden = true;
        return;
      }
      termsBox.hidden = false;
      var th = el('h2');
      th.textContent = '新术语';
      termsBox.appendChild(th);
      var dl = el('dl');
      DATA.terms.forEach(function (t, idx) {
        var dt = el('dt', 'mm-editable');
        dt.tabIndex = 0;
        dt.textContent = t.term || '（未命名）';
        var dd = el('dd', 'mm-editable');
        dd.tabIndex = 0;
        dd.textContent = t.meaning || '';
        function edit() { editTerm(idx); }
        dt.title = '点击修改';
        dd.title = '点击修改';
        dt.addEventListener('click', edit);
        dd.addEventListener('click', edit);
        dl.appendChild(dt);
        dl.appendChild(dd);
      });
      termsBox.appendChild(dl);
      termsBox.appendChild(btn('＋ 术语', addTerm));
    }

    function editTerm(idx) {
      commitLive();
      var t = DATA.terms[idx];
      if (!t) { return; }
      paintTerms();
      var dl = termsBox.querySelector('dl');
      var dts = dl.querySelectorAll('dt');
      var dds = dl.querySelectorAll('dd');
      var dt = dts[idx];
      var dd = dds[idx];
      var row = el('div', 'mm-term-row');
      var a = el('input');
      a.type = 'text';
      a.placeholder = '术语';
      a.value = t.term || '';
      var b = el('input');
      b.type = 'text';
      b.placeholder = '理解';
      b.value = t.meaning || '';
      var rm = btn('删', function () {
        liveEdit = null;
        DATA.terms.splice(idx, 1);
        markDirty();
        paintTerms();
      });
      row.appendChild(a);
      row.appendChild(b);
      row.appendChild(rm);
      dt.replaceWith(row);
      dd.remove();
      function commit() {
        var term = a.value;
        var meaning = b.value;
        if (term !== (t.term || '') || meaning !== (t.meaning || '')) {
          t.term = term;
          t.meaning = meaning;
          markDirty();
        }
        if (!String(t.term || '').trim() && !String(t.meaning || '').trim()) {
          DATA.terms.splice(idx, 1);
        }
        paintTerms();
      }
      liveEdit = { commit: commit };
      function blurMaybe() {
        setTimeout(function () {
          if (!liveEdit) { return; }
          if (row.contains(document.activeElement)) { return; }
          liveEdit = null;
          commit();
        }, 0);
      }
      a.addEventListener('blur', blurMaybe);
      b.addEventListener('blur', blurMaybe);
      rm.addEventListener('mousedown', function (e) { e.preventDefault(); });
      a.focus();
    }

    function addTerm() {
      commitLive();
      DATA.terms.push({ term: '', meaning: '' });
      markDirty();
      paintTerms();
      editTerm(DATA.terms.length - 1);
    }

    // ---------- 保存 ----------

    function dumpNode(n) {
      var o = { t: n.t || '' };
      NODE_KEYS.forEach(function (k) {
        if (k === 't') { return; }
        if (k === 'kids') {
          var kids = (n.kids || []).map(dumpNode);
          if (kids.length) { o.kids = kids; }
          return;
        }
        var v = n[k];
        if (v == null || v === false || v === '') { return; }
        o[k] = v;
      });
      return o;
    }

    function dumpText() {
      var out = { meta: {}, tree: dumpNode(DATA.tree) };
      META_KEYS.forEach(function (k) {
        if (META[k] == null || META[k] === '') { return; }
        out.meta[k] = META[k];
      });
      var terms = DATA.terms.filter(function (t) {
        return (t.term && String(t.term).trim()) || (t.meaning && String(t.meaning).trim());
      }).map(function (t) { return { term: t.term || '', meaning: t.meaning || '' }; });
      if (terms.length) { out.terms = terms; }
      return JSON.stringify(out, null, 2) + '\n';
    }

    function markDirty() {
      dirty = true;
      document.title = '* ' + pageTitle();
      scheduleSave();
    }

    function setSaveMsg(msg) {
      saveMsg.textContent = msg || '';
    }

    function scheduleSave() {
      clearTimeout(saveTimer);
      setSaveMsg('保存中…');
      saveTimer = setTimeout(doSave, 400);
    }

    function doSave(keepalive) {
      if (saving) { saveAgain = true; return; }
      saving = true;
      var text = dumpText();
      fetch(saveUrl, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json; charset=utf-8' },
        body: text,
        keepalive: !!keepalive
      }).then(function (r) {
        if (!r.ok) { throw new Error('HTTP ' + r.status); }
        saving = false;
        if (saveAgain) { saveAgain = false; doSave(); return; }
        dirty = false;
        document.title = pageTitle();
        setSaveMsg('已保存');
      }).catch(function () {
        saving = false;
        saveAgain = false;
        setSaveMsg('自动保存失败。用 serve.sh 打开这份 JSON');
      });
    }

    document.addEventListener('paste', function (e) {
      if (!selected) { return; }
      var ae = document.activeElement;
      var tag = ae && ae.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') { return; }
      if (!clipImage(e.clipboardData)) { return; }
      acceptShot(e, selected, function () { refill(selected); });
    });
    document.addEventListener('keydown', function (e) {
      if (e.metaKey || e.ctrlKey) {
        if (e.key !== 's' && e.key !== 'S') { return; }
        e.preventDefault();
        clearTimeout(saveTimer);
        doSave();
        return;
      }
      if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown' && e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') { return; }
      if (e.altKey) { return; }
      var ae = document.activeElement;
      var tag = ae && ae.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') { return; }
      if (ae && ae.isContentEditable) { return; }
      e.preventDefault();
      moveSelection(e.key);
    });
    window.addEventListener('beforeunload', function () {
      if (!dirty) { return; }
      clearTimeout(saveTimer);
      doSave(true);
    });

    // ---------- 工具 ----------

    function moveSelection(key) {
      var cur = selected || DATA.tree;
      var next = null;
      if (key === 'ArrowLeft') {
        next = cur._parent;
      } else if (key === 'ArrowRight') {
        if (!cur._kids.length) { return; }
        if (!cur._open) {
          cur._open = true;
          render();
        }
        next = cur._kids[0];
      } else {
        var sibs = cur._parent ? cur._parent._kids : null;
        if (!sibs) { return; }
        var i = sibs.indexOf(cur);
        var j = key === 'ArrowUp' ? i - 1 : i + 1;
        if (j < 0 || j >= sibs.length) { return; }
        next = sibs[j];
      }
      if (next) { select(next); }
    }

    function setAll(open) {
      nodes.forEach(function (n) { if (n._kids.length) { n._open = open; } });
      render();
    }
    function resetOpen() {
      nodes.forEach(function (n) {
        if (n.open === true) { n._open = true; }
        else if (n.fold === true) { n._open = false; }
        else { n._open = n._depth < OPEN_DEPTH; }
      });
      render();
    }
    function el(tag, cls) {
      var d = document.createElement(tag);
      if (cls) { d.className = cls; }
      return d;
    }
    function btn(text, fn) {
      var b = el('button', 'mm-btn');
      b.type = 'button';
      b.textContent = text;
      b.addEventListener('click', fn);
      return b;
    }
    function flag(cls, text) {
      var f = el('span', 'mm-flag ' + cls);
      f.textContent = text;
      return f;
    }
    function autoresize(ta) {
      ta.style.height = 'auto';
      ta.style.height = Math.min(Math.max(ta.scrollHeight, 72), 420) + 'px';
    }
    function px(name, fallback) {
      var v = getComputedStyle(document.documentElement).getPropertyValue(name);
      var n = parseFloat(v);
      return isNaN(n) ? fallback : n;
    }
    function enableSplit(handle, pane, host) {
      var MIN_PANEL = 220;
      var MIN_CANVAS = 280;
      handle.addEventListener('mousedown', function (e) {
        if (e.button !== 0) { return; }
        e.preventDefault();
        var startX = e.clientX;
        var startW = pane.getBoundingClientRect().width;
        document.documentElement.classList.add('mm-resizing');
        function move(ev) {
          var max = host.getBoundingClientRect().width - MIN_CANVAS;
          var w = startW + (startX - ev.clientX);
          pane.style.width = Math.max(MIN_PANEL, Math.min(max, w)) + 'px';
        }
        function up() {
          document.removeEventListener('mousemove', move);
          document.removeEventListener('mouseup', up);
          document.documentElement.classList.remove('mm-resizing');
        }
        document.addEventListener('mousemove', move);
        document.addEventListener('mouseup', up);
      });
    }
    var ZOOM_MIN = 0.25;
    var ZOOM_MAX = 2.5;
    var zoom = 1;
    var baseW = 0;
    var baseH = 0;

    function applyZoom() {
      canvas.style.transform = 'scale(' + zoom + ')';
      sizer.style.width = Math.ceil(baseW * zoom) + 'px';
      sizer.style.height = Math.ceil(baseH * zoom) + 'px';
      zoomPctBtn.textContent = Math.round(zoom * 100) + '%';
      zoomOutBtn.disabled = zoom <= ZOOM_MIN + 1e-4;
      zoomInBtn.disabled = zoom >= ZOOM_MAX - 1e-4;
    }

    function setZoom(next, anchor) {
      var prev = zoom;
      next = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, next));
      if (baseW <= 0) {
        zoom = next;
        applyZoom();
        return;
      }
      var ax = wrap.clientWidth / 2;
      var ay = wrap.clientHeight / 2;
      if (anchor) {
        var rect = wrap.getBoundingClientRect();
        ax = anchor.x - rect.left;
        ay = anchor.y - rect.top;
      }
      var contentX = (wrap.scrollLeft + ax) / (prev || 1);
      var contentY = (wrap.scrollTop + ay) / (prev || 1);
      zoom = next;
      applyZoom();
      wrap.scrollLeft = contentX * zoom - ax;
      wrap.scrollTop = contentY * zoom - ay;
    }

    function enableZoom(scroller) {
      scroller.addEventListener('wheel', function (e) {
        if (!e.metaKey) { return; }
        e.preventDefault();
        var dy = e.deltaY;
        if (e.deltaMode === 1) { dy *= 16; }
        else if (e.deltaMode === 2) { dy *= scroller.clientHeight || 400; }
        setZoom(zoom * Math.exp(-dy * 0.0025), { x: e.clientX, y: e.clientY });
      }, { passive: false });
    }

    function enablePan(scroller) {
      var THRESH = 5;
      scroller.addEventListener('mousedown', function (e) {
        if (e.button !== 0) { return; }
        if (e.target.closest && e.target.closest('.mm-toggle')) { return; }
        var startX = e.clientX, startY = e.clientY;
        var sl = scroller.scrollLeft, st = scroller.scrollTop;
        var dragged = false;
        function move(ev) {
          var dx = ev.clientX - startX, dy = ev.clientY - startY;
          if (!dragged && dx * dx + dy * dy < THRESH * THRESH) { return; }
          if (!dragged) {
            dragged = true;
            document.documentElement.classList.add('mm-panning');
          }
          scroller.scrollLeft = sl - dx;
          scroller.scrollTop = st - dy;
          ev.preventDefault();
        }
        function up() {
          document.removeEventListener('mousemove', move);
          document.removeEventListener('mouseup', up);
          document.documentElement.classList.remove('mm-panning');
          if (!dragged) { return; }
          scroller.addEventListener('click', function eat(ev) {
            ev.stopPropagation();
            ev.preventDefault();
            scroller.removeEventListener('click', eat, true);
          }, true);
        }
        document.addEventListener('mousemove', move);
        document.addEventListener('mouseup', up);
      });
    }

    paintHeadMeta();
    paintTerms();
    render();
    select(DATA.tree, true);
    syncHead();
  }

  function encodePath(p) {
    return String(p || '').split('/').map(encodeURIComponent).join('/');
  }

  function cleanDroppedPath(raw) {
    var s = String(raw || '').trim();
    if (!s) { return ''; }
    if ((s.charAt(0) === '"' && s.slice(-1) === '"') || (s.charAt(0) === "'" && s.slice(-1) === "'")) {
      s = s.slice(1, -1).trim();
    }
    if (/^file:\/\//i.test(s)) {
      try { s = decodeURIComponent(new URL(s).pathname || ''); }
      catch (e) {
        try { s = decodeURIComponent(s.replace(/^file:\/\/(localhost)?/i, '')); }
        catch (e2) { s = ''; }
      }
    }
    if (!s || s.indexOf('/.file/id=') === 0) { return ''; }
    return (s.charAt(0) === '/' || s.indexOf('~/') === 0) ? s : '';
  }

  function extractDroppedPath(dt) {
    if (!dt) { return ''; }
    var i, raw, arr, lines, p;
    if (dt.files && dt.files.length && typeof dt.files[0].path === 'string') {
      p = cleanDroppedPath(dt.files[0].path);
      if (p) { return p; }
    }
    ['codefiles', 'resourceurls'].forEach(function (key) {
      if (p) { return; }
      try {
        raw = dt.getData(key);
        if (raw) {
          arr = JSON.parse(raw);
          if (Array.isArray(arr) && arr.length) { p = cleanDroppedPath(arr[0]); }
        }
      } catch (e) {}
    });
    if (p) { return p; }
    try {
      raw = dt.getData('codeeditors');
      if (raw) {
        arr = JSON.parse(raw);
        if (Array.isArray(arr) && arr.length && arr[0] && arr[0].resource) {
          p = cleanDroppedPath(arr[0].resource.fsPath || arr[0].resource.path || arr[0].resource.external);
          if (p) { return p; }
        }
      }
    } catch (e) {}
    ['text/uri-list', 'text/plain'].forEach(function (key) {
      if (p) { return; }
      try {
        raw = dt.getData(key);
        if (raw) {
          lines = raw.split(/\r?\n/);
          for (i = 0; i < lines.length; i++) {
            if (!lines[i] || lines[i].charAt(0) === '#') { continue; }
            p = cleanDroppedPath(lines[i]);
            if (p) { return; }
          }
        }
      } catch (e) {}
    });
    return p || '';
  }

  function isFileDrag(dt) {
    if (!dt || !dt.types) { return false; }
    var t = Array.prototype.slice.call(dt.types);
    return t.indexOf('Files') >= 0 || t.indexOf('codefiles') >= 0 || t.indexOf('resourceurls') >= 0 || t.indexOf('text/uri-list') >= 0;
  }

  function enableFileDrop() {
    var dragDepth = 0;
    window.addEventListener('dragenter', function (e) {
      if (!isFileDrag(e.dataTransfer)) { return; }
      e.preventDefault();
      dragDepth += 1;
      document.documentElement.classList.add('mm-file-drag');
    });
    window.addEventListener('dragover', function (e) {
      if (!isFileDrag(e.dataTransfer)) { return; }
      e.preventDefault();
      if (e.dataTransfer) { e.dataTransfer.dropEffect = 'copy'; }
    });
    window.addEventListener('dragleave', function (e) {
      if (!document.documentElement.classList.contains('mm-file-drag')) { return; }
      e.preventDefault();
      dragDepth = Math.max(0, dragDepth - 1);
      if (dragDepth === 0) { document.documentElement.classList.remove('mm-file-drag'); }
    });
    window.addEventListener('drop', function (e) {
      var dt = e.dataTransfer;
      var hint = extractDroppedPath(dt);
      var hasFile = dt && dt.files && dt.files.length > 0;
      if (!hint && !hasFile) { return; }
      if (!hint && hasFile && !/\.json$/i.test(dt.files[0].name)) { return; }
      e.preventDefault();
      e.stopPropagation();
      dragDepth = 0;
      document.documentElement.classList.remove('mm-file-drag');
      if (hint && hint.charAt(0) === '/' && /\.json$/i.test(hint)) {
        location.href = '/view?json=' + encodePath(hint);
        return;
      }
      var f = hasFile ? dt.files[0] : null;
      var qs = new URLSearchParams();
      if (f && f.name) { qs.set('name', f.name); }
      if (f && f.lastModified) { qs.set('mtime', String(f.lastModified)); }
      if (hint) { qs.set('path', hint); }
      fetch('/resolve?' + qs.toString(), { method: 'POST', body: f || null }).then(function (r) {
        return r.json().then(function (d) {
          if (!r.ok) { throw new Error((d && d.error) || ('HTTP ' + r.status)); }
          return d;
        });
      }).then(function (d) {
        if (d.kind === 'dir') { location.href = '/list?dir=' + encodePath(d.path); }
        else if (d.path) { location.href = '/view?json=' + encodePath(d.path); }
      }).catch(function (err) {
        showBoot(err && err.message ? err.message : String(err), true);
      });
    });
  }

  enableFileDrop();
  start();
})();
