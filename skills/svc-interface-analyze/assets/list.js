/* 清单页
 *
 * ?dir= 指向 analysis 目录或其子目录。
 * 有 interfaces.json，或带 interfaces 数组的 index.json，就画接口表。
 * 都没有，就列出该目录里带 tree 的解读 JSON。
 * 页头路径从 analysis 到当前目录，点上一级退回去。
 */
(function () {
  'use strict';

  var app = document.getElementById('mm-app') || document.body;

  function el(tag, cls) {
    var d = document.createElement(tag);
    if (cls) { d.className = cls; }
    return d;
  }

  function showBoot(msg, isErr) {
    app.innerHTML = '';
    var p = el('p', 'mm-boot-msg' + (isErr ? ' mm-boot-msg--err' : ''));
    p.textContent = msg;
    app.appendChild(p);
  }

  function comma(n) {
    var s = String(n == null ? 0 : n);
    if (!/^-?\d+$/.test(s)) { return s; }
    return s.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  }

  function queryDir() {
    try {
      return new URLSearchParams(location.search).get('dir') || '';
    } catch (e) {
      return '';
    }
  }

  function fileApi(abs) {
    return '/file?path=' + encodeURIComponent(abs);
  }

  function baseName(p) {
    var s = String(p || '');
    var i = s.lastIndexOf('/');
    return i >= 0 ? s.slice(i + 1) : s;
  }

  function pageFile(page) {
    var base = baseName(page);
    if (!base) { return ''; }
    return base.replace(/\.html?$/i, '.json');
  }

  function prefixed(service, name) {
    var out = [];
    function add(n) {
      if (n && out.indexOf(n) < 0) { out.push(n); }
    }
    if (service) {
      add(service + '-' + name + '.json');
      add(service + '-' + name.replace(/\//g, '-') + '.json');
      add(service + '-' + name.replace(/^.*\//, '') + '.json');
    }
    return out;
  }

  function matchFile(files, service, name, page) {
    var set = {};
    var i, f, leaf, tail, hit;
    for (i = 0; i < files.length; i++) { set[files[i]] = 1; }
    f = pageFile(page);
    if (f && set[f]) { return f; }
    var names = prefixed(service, name);
    for (i = 0; i < names.length; i++) {
      if (set[names[i]]) { return names[i]; }
    }
    leaf = name.replace(/^.*\//, '');
    tail = '-' + leaf + '.json';
    hit = '';
    for (i = 0; i < files.length; i++) {
      f = files[i];
      if (f === leaf + '.json') { continue; }
      if (f.slice(-tail.length) === tail) { hit = f; break; }
    }
    return hit;
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
        span = el('span');
        span.textContent = slice[i].name;
        nav.appendChild(span);
      } else {
        a = el('a');
        a.href = '/list?dir=' + encodeURIComponent(slice[i].path);
        a.textContent = slice[i].name;
        nav.appendChild(a);
      }
    }
    if (leaf) {
      nav.appendChild(document.createTextNode(' / '));
      span = el('span');
      span.textContent = leaf;
      nav.appendChild(span);
    }
  }

  function stem(name) {
    return String(name || '').replace(/\.json$/i, '');
  }

  function appendDirs(parent, dir, dirs) {
    if (!dirs || !dirs.length) { return; }
    var p = el('p', 'mm-dirs');
    dirs.forEach(function (name, i) {
      if (i) { p.appendChild(document.createTextNode(' · ')); }
      var a = el('a');
      a.href = '/list?dir=' + encodeURIComponent(dir + '/' + name);
      a.textContent = name + '/';
      p.appendChild(a);
    });
    parent.appendChild(p);
  }

  function renderPages(dir, listing) {
    var pages = (listing && listing.pages) || [];
    var dirs = (listing && listing.dirs) || [];
    var base = stem(dir.split('/').pop() || dir);
    var i, page, tr, tdName, tdFile, a;

    document.title = base;
    app.innerHTML = '';

    var head = el('div', 'mm-head');
    var crumb = el('nav', 'mm-crumb');
    fillCrumb(crumb, dir, '');
    head.appendChild(crumb);
    var h1 = el('h1');
    h1.textContent = base;
    head.appendChild(h1);
    var count = el('span', 'mm-meta');
    count.textContent = pages.length + ' 份解读';
    head.appendChild(count);
    app.appendChild(head);

    var list = el('div', 'mm-list');
    appendDirs(list, dir, dirs);
    if (!pages.length) {
      var empty = el('p');
      empty.textContent = '这个目录里没有解读 JSON。';
      list.appendChild(empty);
      app.appendChild(list);
      return;
    }

    var table = el('table');
    var thead = el('thead');
    var hr = el('tr');
    ['解读', '文件'].forEach(function (label) {
      var th = el('th');
      th.textContent = label;
      hr.appendChild(th);
    });
    thead.appendChild(hr);
    table.appendChild(thead);

    var tbody = el('tbody');
    for (i = 0; i < pages.length; i++) {
      page = pages[i] || {};
      tr = el('tr', 'has-page');
      tdName = el('td', 'mm-iface');
      a = el('a');
      a.href = '/view?json=' + encodeURIComponent(dir + '/' + page.name);
      a.textContent = page.title || stem(page.name);
      tdName.appendChild(a);
      tr.appendChild(tdName);
      tdFile = el('td', 'mono');
      tdFile.textContent = page.name || '';
      tr.appendChild(tdFile);
      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    list.appendChild(table);
    app.appendChild(list);
  }

  function render(data, pages, dir, dirs) {
    var meta = data.meta || {};
    var rows = data.interfaces || [];
    var service = meta.service || '';
    var title = (service ? service + ' ' : '') + '接口清单';
    var analyzed = 0;
    var i, item, file;

    document.title = title;
    app.innerHTML = '';

    var head = el('div', 'mm-head');
    var crumb = el('nav', 'mm-crumb');
    fillCrumb(crumb, dir, '');
    head.appendChild(crumb);
    var h1 = el('h1');
    h1.textContent = title;
    head.appendChild(h1);

    for (i = 0; i < rows.length; i++) {
      if (pages[i]) { analyzed += 1; }
    }
    var count = el('span', 'mm-meta');
    count.textContent = '共 ' + rows.length + ' 个接口 · 已分析 ' + analyzed + ' 个';
    head.appendChild(count);

    if (meta.start || meta.end) {
      var range = el('span', 'mm-meta');
      range.textContent = (meta.start || '') + ' → ' + (meta.end || '');
      head.appendChild(range);
    }
    if (meta.appId || meta.env) {
      var src = el('span', 'mm-meta');
      src.textContent = 'appId ' + (meta.appId == null ? '' : meta.appId) + ' · env ' + (meta.env || '');
      head.appendChild(src);
    }
    app.appendChild(head);

    var list = el('div', 'mm-list');
    var hint = el('p');
    hint.appendChild(document.createTextNode('数据来自被调监控 '));
    var mon = el('span', 'mono');
    mon.textContent = 'p_monitor_mult_analy';
    hint.appendChild(mon);
    hint.appendChild(document.createTextNode('，按该日请求量降序。左侧绿色竖条表示同目录已有页面 JSON。'));
    list.appendChild(hint);
    appendDirs(list, dir, dirs);

    var table = el('table');
    var thead = el('thead');
    var hr = el('tr');
    ['接口', 'service', '请求量', '状态', '说明'].forEach(function (label) {
      var th = el('th');
      th.textContent = label;
      hr.appendChild(th);
    });
    thead.appendChild(hr);
    table.appendChild(thead);

    var tbody = el('tbody');
    for (i = 0; i < rows.length; i++) {
      item = rows[i];
      file = pages[i];
      var tr = el('tr', file ? 'has-page' : '');
      var tdName = el('td', 'mm-iface');
      if (file) {
        var a = el('a');
        a.href = '/view?json=' + encodeURIComponent(file);
        a.textContent = item.name || '';
        tdName.appendChild(a);
      } else {
        tdName.textContent = item.name || '';
      }
      tr.appendChild(tdName);

      var tdSvc = el('td', 'mono');
      tdSvc.textContent = item.pService || '';
      tr.appendChild(tdSvc);

      var tdCnt = el('td', 'mono');
      tdCnt.textContent = comma(item.reqCnt);
      tr.appendChild(tdCnt);

      var tdSt = el('td', 'mm-status');
      tdSt.textContent = file ? '已分析' : '未分析';
      tr.appendChild(tdSt);

      var tdNote = el('td');
      tdNote.textContent = item.note || '';
      tr.appendChild(tdNote);

      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    list.appendChild(table);
    app.appendChild(list);
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

  (function enableFileDrop() {
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
  })();

  var dir = queryDir().replace(/\/$/, '');
  if (!dir) {
    showBoot('地址上缺 dir。\nserve.sh /path/to/analysis\n\n也可直接把 .json 文件拖到当前页面打开 /view?json=路径', true);
    return;
  }

  showBoot('加载目录 …');
  fetch('/files?dir=' + encodeURIComponent(dir), { cache: 'no-store' }).then(function (r) {
    if (!r.ok) { throw new Error('目录列表 HTTP ' + r.status); }
    return r.json();
  }).then(function (listing) {
    var files = (listing && listing.files) || [];
    var indexName = '';
    if (files.indexOf('interfaces.json') >= 0) { indexName = 'interfaces.json'; }
    else if (files.indexOf('index.json') >= 0) { indexName = 'index.json'; }
    if (!indexName) {
      renderPages(dir, listing);
      return null;
    }
    return fetch(fileApi(dir + '/' + indexName), { cache: 'no-store' }).then(function (r) {
      if (!r.ok) { throw new Error(indexName + ' HTTP ' + r.status); }
      return r.json();
    }).then(function (data) {
      if (indexName === 'index.json' && !Array.isArray(data.interfaces)) {
        renderPages(dir, listing);
        return;
      }
      var meta = data.meta || {};
      var rows = data.interfaces || [];
      var pagePaths = rows.map(function (item) {
        var name = matchFile(files, meta.service || '', item.name || '', item.page || '');
        return name ? (dir + '/' + name) : '';
      });
      render(data, pagePaths, dir, (listing && listing.dirs) || []);
    });
  }).catch(function (e) {
    showBoot(
      '无法打开这个目录\n' + (e && e.message ? e.message : e) +
      '\n\n用 svc-interface-analyze 的 assets/serve.sh，参数传 analysis 目录或其中一份 JSON。',
      true
    );
  });
})();
