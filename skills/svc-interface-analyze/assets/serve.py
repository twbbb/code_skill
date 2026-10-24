#!/usr/bin/env python3
"""常驻本地服务。HTML/JS/CSS 在 skill 里，只按路径读写 analysis/ 下的 JSON 和贴图。"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

PORT_DEFAULT = 8765
MAX_JSON = 8 * 1024 * 1024
MAX_IMG = 12 * 1024 * 1024
IMG_EXT = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
SHOT_RE = re.compile(r'^[A-Za-z0-9._-]+$')
MARKER = 'service-interfaces'

STATIC_ENV = {
    '/list': ('SI_LIST_HTML', 'text/html; charset=utf-8'),
    '/view': ('SI_VIEW_HTML', 'text/html; charset=utf-8'),
    '/assets/list.js': ('SI_LIST_JS', 'text/javascript; charset=utf-8'),
    '/assets/mindmap.js': ('SI_MINDMAP_JS', 'text/javascript; charset=utf-8'),
    '/assets/mindmap.css': ('SI_MINDMAP_CSS', 'text/css; charset=utf-8'),
    '/example.html': ('SI_EXAMPLE_HTML', 'text/html; charset=utf-8'),
    '/example.json': ('SI_EXAMPLE_JSON', 'application/json; charset=utf-8'),
}

HELP = """service-interfaces

清单   /list?dir=<analysis 绝对路径>
调用链 /view?json=<json 绝对路径>
示例   /example.html
"""

HOME_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>service-interfaces</title>
<link rel="stylesheet" href="/assets/mindmap.css">
</head>
<body class="mm-has-drop-box">
<div class="mm-head">
  <h1>service-interfaces</h1>
  <span class="mm-meta">127.0.0.1:8765</span>
  <span class="mm-spacer"></span>
  <a href="/example.html">示例</a>
</div>
<div class="mm-home">
  <div id="mm-drop" class="mm-drop" tabindex="0" role="button" aria-label="拖入或选择 JSON 文件">
    <p class="mm-drop-title">把 <code>.json</code> 文件拖到这里，直接打开 <code>/view?json=路径</code></p>
    <p class="mm-drop-sub">支持从 Cursor / VSCode、Finder 拖入文件或 <code>analysis</code> 目录，也可点击选择文件或按 ⌘V 粘贴路径</p>
    <input id="mm-file" type="file" accept=".json,application/json" hidden>
  </div>
  <form id="mm-path-form" class="mm-path-form">
    <input id="mm-path-input" type="text" placeholder="/path/to/analysis/.../xxx.json 或目录路径" autocomplete="off" spellcheck="false">
    <button type="submit" class="mm-btn">打开</button>
  </form>
  <p id="mm-drop-msg" class="mm-drop-msg" hidden></p>
  <pre class="mm-home-help">清单   /list?dir=&lt;analysis 绝对路径&gt;
调用链 /view?json=&lt;json 绝对路径&gt;
示例   <a href="/example.html">/example.html</a></pre>
</div>
<script>
(function () {
  'use strict';

  var dropBox = document.getElementById('mm-drop');
  var fileInput = document.getElementById('mm-file');
  var form = document.getElementById('mm-path-form');
  var pathInput = document.getElementById('mm-path-input');
  var msgBox = document.getElementById('mm-drop-msg');
  var dragDepth = 0;

  function showMsg(text, isErr) {
    if (!text) {
      msgBox.hidden = true;
      msgBox.textContent = '';
      msgBox.className = 'mm-drop-msg';
      return;
    }
    msgBox.hidden = false;
    msgBox.textContent = text;
    msgBox.className = 'mm-drop-msg' + (isErr ? ' mm-boot-msg--err' : '');
  }

  function encodePath(p) {
    return String(p || '').split('/').map(encodeURIComponent).join('/');
  }

  function goTarget(kind, absPath) {
    if (!absPath) { return; }
    if (kind === 'dir') {
      location.href = '/list?dir=' + encodePath(absPath);
    } else {
      location.href = '/view?json=' + encodePath(absPath);
    }
  }

  function fileUrlToPath(raw) {
    var s = String(raw || '').trim();
    if (!/^file:\\/\\//i.test(s)) { return ''; }
    try {
      var u = new URL(s);
      return decodeURIComponent(u.pathname || '');
    } catch (e) {
      try {
        return decodeURIComponent(s.replace(/^file:\\/\\/(localhost)?/i, ''));
      } catch (e2) {
        return '';
      }
    }
  }

  function cleanRawPath(raw) {
    var s = String(raw || '').trim();
    if (!s) { return ''; }
    if ((s.charAt(0) === '"' && s.slice(-1) === '"') || (s.charAt(0) === "'" && s.slice(-1) === "'")) {
      s = s.slice(1, -1).trim();
    }
    if (/^file:\\/\\//i.test(s)) {
      s = fileUrlToPath(s);
    }
    if (!s || s.indexOf('/.file/id=') === 0) { return ''; }
    if (s.charAt(0) === '/' || s.indexOf('~/') === 0) {
      return s;
    }
    return '';
  }

  function extractDroppedPath(dt) {
    if (!dt) { return ''; }
    var i, raw, arr, lines, p;
    if (dt.files && dt.files.length && typeof dt.files[0].path === 'string') {
      p = cleanRawPath(dt.files[0].path);
      if (p) { return p; }
    }
    try {
      raw = dt.getData('codefiles');
      if (raw) {
        arr = JSON.parse(raw);
        if (Array.isArray(arr) && arr.length) {
          p = cleanRawPath(arr[0]);
          if (p) { return p; }
        }
      }
    } catch (e) {}
    try {
      raw = dt.getData('resourceurls');
      if (raw) {
        arr = JSON.parse(raw);
        if (Array.isArray(arr) && arr.length) {
          p = cleanRawPath(arr[0]);
          if (p) { return p; }
        }
      }
    } catch (e) {}
    try {
      raw = dt.getData('codeeditors');
      if (raw) {
        arr = JSON.parse(raw);
        if (Array.isArray(arr) && arr.length && arr[0] && arr[0].resource) {
          p = cleanRawPath(arr[0].resource.fsPath || arr[0].resource.path || arr[0].resource.external);
          if (p) { return p; }
        }
      }
    } catch (e) {}
    try {
      raw = dt.getData('text/uri-list');
      if (raw) {
        lines = raw.split(/\\r?\\n/);
        for (i = 0; i < lines.length; i++) {
          if (!lines[i] || lines[i].charAt(0) === '#') { continue; }
          p = cleanRawPath(lines[i]);
          if (p) { return p; }
        }
      }
    } catch (e) {}
    try {
      raw = dt.getData('text/plain');
      if (raw) {
        lines = raw.split(/\\r?\\n/);
        for (i = 0; i < lines.length; i++) {
          p = cleanRawPath(lines[i]);
          if (p) { return p; }
        }
      }
    } catch (e) {}
    return '';
  }

  function resolveOnServer(params, bodyFile) {
    var qs = new URLSearchParams();
    Object.keys(params || {}).forEach(function (k) {
      if (params[k] != null && params[k] !== '') {
        qs.set(k, String(params[k]));
      }
    });
    showMsg('正在定位文件路径 …');
    return fetch('/resolve?' + qs.toString(), {
      method: 'POST',
      body: bodyFile || null
    }).then(function (r) {
      return r.json().then(function (data) {
        if (!r.ok) {
          throw new Error((data && data.error) || ('HTTP ' + r.status));
        }
        return data;
      });
    }).then(function (data) {
      goTarget(data.kind || 'json', data.path);
    }).catch(function (err) {
      showMsg(err && err.message ? err.message : String(err), true);
    });
  }

  function findFirstJsonInDir(dirEntry, relPrefix, depth, cb) {
    if (depth > 4) { cb(null); return; }
    var reader = dirEntry.createReader();
    reader.readEntries(function (entries) {
      if (!entries || !entries.length) { cb(null); return; }
      var i;
      for (i = 0; i < entries.length; i++) {
        if (entries[i].isFile && /\\.json$/i.test(entries[i].name)) {
          var rel = (relPrefix ? relPrefix + '/' : '') + entries[i].name;
          entries[i].file(function (f) { cb({ file: f, rel: rel }); }, function () { cb(null); });
          return;
        }
      }
      var dirs = entries.filter(function (e) {
        return e.isDirectory && e.name.charAt(0) !== '.' && e.name !== 'parts' && e.name !== 'assets';
      });
      var idx = 0;
      function next() {
        if (idx >= dirs.length) { cb(null); return; }
        var d = dirs[idx++];
        var subRel = (relPrefix ? relPrefix + '/' : '') + d.name;
        findFirstJsonInDir(d, subRel, depth + 1, function (found) {
          if (found) { cb(found); } else { next(); }
        });
      }
      next();
    }, function () { cb(null); });
  }

  function openByPathString(raw) {
    var p = cleanRawPath(raw);
    if (!p) {
      showMsg('请输入或拖入本地 .json 绝对路径', true);
      return;
    }
    if (p.charAt(0) === '/' && /\\.json$/i.test(p)) {
      goTarget('json', p);
      return;
    }
    resolveOnServer({ path: p }, null);
  }

  function handleTransfer(dt) {
    if (!dt) { return false; }
    var hint = extractDroppedPath(dt);
    if (hint && hint.charAt(0) === '/' && /\\.json$/i.test(hint)) {
      goTarget('json', hint);
      return true;
    }
    if (dt.items && dt.items.length && typeof dt.items[0].webkitGetAsEntry === 'function') {
      var entry = dt.items[0].webkitGetAsEntry();
      if (entry && entry.isDirectory) {
        if (hint) {
          resolveOnServer({ path: hint }, null);
          return true;
        }
        findFirstJsonInDir(entry, '', 0, function (found) {
          if (found && found.file) {
            resolveOnServer({
              name: found.file.name,
              mtime: found.file.lastModified || 0,
              rel: found.rel
            }, found.file);
          } else {
            resolveOnServer({ dir: entry.name }, null);
          }
        });
        return true;
      }
    }
    if (dt.files && dt.files.length) {
      var f = dt.files[0];
      resolveOnServer({
        name: f.name,
        mtime: f.lastModified || 0,
        path: hint
      }, f);
      return true;
    }
    if (hint) {
      openByPathString(hint);
      return true;
    }
    return false;
  }

  window.addEventListener('dragenter', function (e) {
    e.preventDefault();
    dragDepth += 1;
    document.documentElement.classList.add('mm-file-drag');
    dropBox.classList.add('is-over');
  });

  window.addEventListener('dragover', function (e) {
    e.preventDefault();
    if (e.dataTransfer) { e.dataTransfer.dropEffect = 'copy'; }
    dropBox.classList.add('is-over');
  });

  window.addEventListener('dragleave', function (e) {
    e.preventDefault();
    dragDepth = Math.max(0, dragDepth - 1);
    if (dragDepth === 0) {
      document.documentElement.classList.remove('mm-file-drag');
      dropBox.classList.remove('is-over');
    }
  });

  window.addEventListener('drop', function (e) {
    e.preventDefault();
    e.stopPropagation();
    dragDepth = 0;
    document.documentElement.classList.remove('mm-file-drag');
    dropBox.classList.remove('is-over');
    handleTransfer(e.dataTransfer);
  });

  dropBox.addEventListener('click', function () {
    fileInput.value = '';
    fileInput.click();
  });

  dropBox.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      fileInput.value = '';
      fileInput.click();
    }
  });

  fileInput.addEventListener('change', function () {
    if (fileInput.files && fileInput.files.length) {
      var f = fileInput.files[0];
      var p = typeof f.path === 'string' ? cleanRawPath(f.path) : '';
      if (p && p.charAt(0) === '/' && /\\.json$/i.test(p)) {
        goTarget('json', p);
        return;
      }
      resolveOnServer({ name: f.name, mtime: f.lastModified || 0, path: p }, f);
    }
  });

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    openByPathString(pathInput.value);
  });

  document.addEventListener('paste', function (e) {
    if (document.activeElement === pathInput) { return; }
    if (handleTransfer(e.clipboardData)) {
      e.preventDefault();
    }
  });
})();
</script>
</body>
</html>
"""


REV = str(int(os.stat(__file__).st_mtime))


def code_rev():
    return REV


# 分析根目录名：analysis，也认旧名 jkanalysis
ROOT_NAMES = ('jkanalysis', 'analysis')
KNOWN_ROOTS = set()
SKIP_FIND_PARTS = (
    '/go/pkg/', '/node_modules/', '/venv/', '/.venv/',
    '/target/', '/Cellar/', '/vendor/', '/.git/',
)


def remember_root(root):
    if root and os.path.isdir(root):
        KNOWN_ROOTS.add(root)


def split_analysis(raw):
    """返回 (analysis 根的真实路径, 目标真实路径)。目标必须落在这个根里面。"""
    if not raw or '\x00' in raw:
        return None
    lexical = os.path.abspath(os.path.expanduser(raw))
    parts = lexical.split(os.sep)
    idx = next((i for i, p in enumerate(parts) if p in ROOT_NAMES), None)
    if idx is None:
        return None
    lexical_root = os.sep.join(parts[:idx + 1]) or os.sep
    if not os.path.isdir(lexical_root):
        return None
    root = os.path.realpath(lexical_root)

    if os.path.exists(lexical):
        target = os.path.realpath(lexical)
    else:
        parent_lex = os.path.dirname(lexical)
        name = os.path.basename(lexical)
        if not name or name in ('.', '..'):
            return None
        rel_parent = os.path.relpath(parent_lex, lexical_root)
        if rel_parent == os.path.join('assets', 'shots'):
            target = os.path.join(root, 'assets', 'shots', name)
        elif os.path.isdir(parent_lex):
            parent = os.path.realpath(parent_lex)
            target = os.path.join(parent, name)
        else:
            return None
    try:
        if os.path.commonpath([root, target]) != root:
            return None
    except ValueError:
        return None
    remember_root(root)
    return root, target


def iter_known_roots():
    roots = list(KNOWN_ROOTS)
    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.abspath(os.path.join(here, '..', '..', '..'))
    for sub in ('localtest', 'codespace'):
        base = os.path.join(repo_root, sub)
        if not os.path.isdir(base):
            continue
        try:
            children = os.listdir(base)
        except OSError:
            continue
        for child in children:
            cp = os.path.join(base, child)
            if not os.path.isdir(cp):
                continue
            for rn in ROOT_NAMES:
                rp = os.path.join(cp, rn)
                if os.path.isdir(rp):
                    roots.append(rp)
    if os.path.isdir('/tmp'):
        roots.append('/tmp')
    seen = set()
    out = []
    for r in roots:
        real = os.path.realpath(r)
        if real not in seen and os.path.isdir(real):
            seen.add(real)
            out.append(real)
    return out


def walk_roots_for_name(roots, name):
    out = []
    for root in roots:
        is_tmp = root in ('/tmp', '/private/tmp')
        for dp, dns, fns in os.walk(root):
            if is_tmp:
                rel = os.path.relpath(dp, root)
                depth = 0 if rel == '.' else rel.count(os.sep) + 1
                if depth >= 4:
                    dns[:] = []
            dns[:] = [
                d for d in dns
                if not d.startswith('.') and d not in ('parts', 'assets', 'node_modules', 'vendor')
            ]
            if name in fns:
                out.append(os.path.join(dp, name))
    return out


def mdfind_by_name(name):
    if not shutil.which('mdfind'):
        return []
    safe = name.replace('\\', '\\\\').replace('"', '\\"')
    try:
        res = subprocess.run(
            ['mdfind', f'kMDItemFSName == "{safe}"'],
            capture_output=True, text=True, timeout=2.5,
        )
    except Exception:
        return []
    out = []
    for line in res.stdout.splitlines():
        p = line.strip()
        if not p or any(skip in p for skip in SKIP_FIND_PARTS):
            continue
        out.append(p)
    return out


def rank_file_candidates(candidates, body, mtime_sec):
    exact = []
    fallback = []
    seen = set()
    for cand in candidates:
        real = os.path.realpath(cand)
        if real in seen or not os.path.isfile(real):
            continue
        seen.add(real)
        try:
            st = os.stat(real)
        except OSError:
            continue
        in_analysis = 0 if split_analysis(real) is not None else 1
        mtime_diff = abs(st.st_mtime - mtime_sec) if mtime_sec > 0 else 0.0
        if body:
            if st.st_size == len(body):
                try:
                    with open(real, 'rb') as f:
                        if f.read() == body:
                            exact.append((in_analysis, mtime_diff, real))
                            continue
                except OSError:
                    pass
        if in_analysis == 0:
            fallback.append((mtime_diff, real))
    if exact:
        exact.sort()
        return exact[0][2], exact[0][0] == 0 and exact[0][1] < 1.0
    if not body and fallback:
        fallback.sort()
        return fallback[0][1], False
    return None, False


def locate_file(name, body, mtime_sec):
    if not name or '/' in name or '\\' in name or '\x00' in name:
        return None
    fast_cands = walk_roots_for_name(iter_known_roots(), name)
    best, exact_recent = rank_file_candidates(fast_cands, body, mtime_sec)
    if best and exact_recent:
        return best
    all_cands = fast_cands + mdfind_by_name(name)
    best, _ = rank_file_candidates(all_cands, body, mtime_sec)
    if best:
        return best
    root_dirs = []
    for rn in ROOT_NAMES:
        for p in mdfind_by_name(rn):
            if os.path.isdir(p):
                remember_root(os.path.realpath(p))
                root_dirs.append(p)
    if root_dirs:
        extra = walk_roots_for_name(root_dirs, name)
        best, _ = rank_file_candidates(all_cands + extra, body, mtime_sec)
        if best:
            return best
    if body:
        best, _ = rank_file_candidates(all_cands, b'', mtime_sec)
        if best:
            return best
    return None


def locate_dir(dir_name):
    if not dir_name or '/' in dir_name or '\\' in dir_name or '\x00' in dir_name:
        return None
    cands = []
    for r in iter_known_roots():
        if os.path.basename(r) == dir_name and split_analysis(r):
            cands.append(r)
        sub = os.path.join(r, dir_name)
        if os.path.isdir(sub) and split_analysis(sub):
            cands.append(os.path.realpath(sub))
    for p in mdfind_by_name(dir_name):
        if os.path.isdir(p) and split_analysis(p):
            cands.append(os.path.realpath(p))
    if not cands:
        return None
    cands.sort(key=lambda p: -os.path.getmtime(p) if os.path.exists(p) else 0)
    return cands[0]


def file_kind(root, target):
    rel = os.path.relpath(target, root).replace('\\', '/')
    if rel.startswith('../') or rel == '..':
        return None
    ext = os.path.splitext(target)[1].lower()
    if ext == '.json':
        return 'json'
    if ext in IMG_EXT and rel.startswith('assets/shots/'):
        name = rel[len('assets/shots/'):]
        if name and '/' not in name and SHOT_RE.match(name):
            return 'img'
    return None


def looks_like_image(body, ext):
    if ext == '.png' and body.startswith(b'\x89PNG\r\n\x1a\n'):
        return True
    if ext in ('.jpg', '.jpeg') and body.startswith(b'\xff\xd8\xff'):
        return True
    if ext == '.gif' and body.startswith((b'GIF87a', b'GIF89a')):
        return True
    if ext == '.webp' and body.startswith(b'RIFF') and body[8:12] == b'WEBP':
        return True
    return False


SKIP_DIRS = {'assets', 'parts'}


def text_field(value):
    return value.strip() if isinstance(value, str) else ''


def page_title(path):
    """解读页根上有 tree。返回标题；不是解读页则 None。"""
    try:
        if os.path.getsize(path) > MAX_JSON:
            return None
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return None
    if not isinstance(data, dict) or not isinstance(data.get('tree'), dict):
        return None
    meta = data.get('meta') if isinstance(data.get('meta'), dict) else {}
    tree = data['tree']
    return text_field(meta.get('center')) or text_field(meta.get('interface')) or text_field(tree.get('t'))


def inside(root, path):
    real = os.path.realpath(path)
    try:
        return os.path.commonpath([root, real]) == root
    except ValueError:
        return False


def list_analysis(root, target):
    """列出 analysis 根或其子目录。files 是文件名；pages 是带 tree 的解读 JSON。"""
    if not inside(root, target) or not os.path.isdir(target):
        return None
    files, dirs, pages = [], [], []
    try:
        names = sorted(os.listdir(target))
    except OSError:
        return None
    for name in names:
        if name.startswith('.'):
            continue
        path = os.path.join(target, name)
        if not inside(root, path):
            continue
        if os.path.isdir(path):
            if name not in SKIP_DIRS:
                dirs.append(name)
            continue
        if not os.path.isfile(path):
            continue
        files.append(name)
        if not name.endswith('.json'):
            continue
        if name in ('interfaces.json', 'index.json') or name.endswith(('-skeleton.json', '.ref.json')):
            continue
        title = page_title(path)
        if title is None:
            continue
        pages.append({'name': name, 'title': title})
    return {'files': files, 'dirs': dirs, 'pages': pages}


class Handler(BaseHTTPRequestHandler):
    server_version = 'service-interfaces'
    protocol_version = 'HTTP/1.1'

    def do_GET(self):
        self.route(True)

    def do_HEAD(self):
        self.route(False)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != '/resolve':
            self.reply(403, b'only /resolve', 'text/plain; charset=utf-8')
            return
        qs = parse_qs(parsed.query)
        raw_path = (qs.get('path') or [''])[0].strip()
        name = os.path.basename((qs.get('name') or [''])[0].strip())
        dir_name = os.path.basename((qs.get('dir') or [''])[0].strip())
        rel = (qs.get('rel') or [''])[0].strip().replace('\\', '/').strip('/')
        try:
            mtime_ms = float((qs.get('mtime') or ['0'])[0])
        except ValueError:
            mtime_ms = 0.0
        mtime_sec = mtime_ms / 1000.0 if mtime_ms > 1e11 else mtime_ms

        try:
            n = int(self.headers.get('Content-Length') or '0')
        except ValueError:
            n = 0
        if n < 0 or n > MAX_JSON:
            self.reply_json(413, {'error': '文件过大'})
            return
        body = self.rfile.read(n) if n > 0 else b''

        if raw_path and not raw_path.startswith('/.file/id='):
            lex = os.path.abspath(os.path.expanduser(raw_path))
            if os.path.isdir(lex):
                real = os.path.realpath(lex)
                split_analysis(real)
                self.reply_json(200, {'kind': 'dir', 'path': real})
                return
            if os.path.isfile(lex) or lex.lower().endswith('.json'):
                real = os.path.realpath(lex) if os.path.exists(lex) else lex
                split_analysis(real)
                self.reply_json(200, {'kind': 'json', 'path': real})
                return

        if name:
            matched = locate_file(name, body, mtime_sec)
            if matched:
                if rel:
                    steps = [p for p in rel.split('/') if p and p != '.']
                    cur = matched
                    for _ in steps:
                        cur = os.path.dirname(cur)
                    self.reply_json(200, {'kind': 'dir', 'path': cur})
                    return
                self.reply_json(200, {'kind': 'json', 'path': matched})
                return

        if dir_name:
            matched_dir = locate_dir(dir_name)
            if matched_dir:
                self.reply_json(200, {'kind': 'dir', 'path': matched_dir})
                return

        self.reply_json(404, {'error': '未找到该文件的本地路径，请确认文件在本机或直接粘贴绝对路径'})

    def do_PUT(self):
        parsed = urlparse(self.path)
        if parsed.path != '/file':
            self.reply(403, b'only /file', 'text/plain; charset=utf-8')
            return
        raw = (parse_qs(parsed.query).get('path') or [''])[0]
        found = split_analysis(raw)
        if not found:
            self.reply(403, b'path must stay inside an analysis directory', 'text/plain; charset=utf-8')
            return
        root, target = found
        kind = file_kind(root, target)
        if kind == 'json':
            limit = MAX_JSON
        elif kind == 'img':
            limit = MAX_IMG
        else:
            self.reply(403, b'only .json or assets/shots image', 'text/plain; charset=utf-8')
            return
        try:
            n = int(self.headers.get('Content-Length') or '0')
        except ValueError:
            self.reply(400, b'bad length', 'text/plain; charset=utf-8')
            return
        if n <= 0 or n > limit:
            self.reply(413 if n > limit else 400, b'bad length', 'text/plain; charset=utf-8')
            return
        body = self.rfile.read(n)
        if kind == 'json':
            try:
                json.loads(body.decode('utf-8'))
            except Exception:
                self.reply(400, b'invalid json', 'text/plain; charset=utf-8')
                return
        else:
            ext = os.path.splitext(target)[1].lower()
            if not looks_like_image(body, ext):
                self.reply(400, b'not an image', 'text/plain; charset=utf-8')
                return
        parent = os.path.dirname(target)
        if not os.path.isdir(parent):
            rel = os.path.relpath(parent, root).replace('\\', '/')
            if rel != 'assets/shots':
                self.reply(404, b'missing directory', 'text/plain; charset=utf-8')
                return
            os.makedirs(parent, exist_ok=True)
        tmp = target + '.tmp'
        with open(tmp, 'wb') as f:
            f.write(body)
        os.replace(tmp, target)
        self.reply(204, b'', 'text/plain; charset=utf-8')

    def route(self, write_body):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == '/health':
            body = ('ok %s %s\n' % (MARKER, code_rev())).encode('ascii')
            self.reply(200, body, 'text/plain; charset=utf-8', write_body)
            return
        if path == '/':
            qs = parse_qs(parsed.query)
            if qs.get('json'):
                self.redirect('/view?json=' + quote(qs['json'][0]))
                return
            if qs.get('dir'):
                self.redirect('/list?dir=' + quote(qs['dir'][0]))
                return
            if parsed.query.startswith(('/view?', '/list?')):
                self.redirect(parsed.query)
                return
            self.reply(200, HOME_HTML.encode('utf-8'), 'text/html; charset=utf-8', write_body)
            return
        static = STATIC_ENV.get(path)
        if static:
            env, ctype = static
            file_path = os.environ.get(env) or ''
            if not file_path or not os.path.isfile(file_path):
                self.reply(500, b'missing skill file', 'text/plain; charset=utf-8', write_body)
                return
            with open(file_path, 'rb') as f:
                body = f.read()
            self.reply(200, body, ctype, write_body)
            return
        raw = (parse_qs(parsed.query).get('path' if path == '/file' else 'dir') or [''])[0]
        if path == '/files':
            found = split_analysis(raw)
            if not found:
                self.reply(403, b'path must stay inside an analysis directory', 'text/plain; charset=utf-8', write_body)
                return
            listed = list_analysis(*found)
            if listed is None:
                self.reply(404, b'not an analysis directory', 'text/plain; charset=utf-8', write_body)
                return
            body = json.dumps(listed, ensure_ascii=False).encode('utf-8')
            self.reply(200, body, 'application/json; charset=utf-8', write_body)
            return
        if path != '/file':
            self.reply(404, b'not found', 'text/plain; charset=utf-8', write_body)
            return
        found = split_analysis(raw)
        if not found:
            self.reply(403, b'path must stay inside an analysis directory', 'text/plain; charset=utf-8', write_body)
            return
        root, target = found
        kind = file_kind(root, target)
        if not kind or not os.path.isfile(target):
            self.reply(404, b'not found', 'text/plain; charset=utf-8', write_body)
            return
        if kind == 'json':
            ctype = 'application/json; charset=utf-8'
        else:
            ext = os.path.splitext(target)[1].lower()
            ctype = {
                '.png': 'image/png',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.gif': 'image/gif',
                '.webp': 'image/webp',
            }[ext]
        with open(target, 'rb') as f:
            body = f.read()
        self.reply(200, body, ctype, write_body)

    def reply(self, code, body, content_type, write_body=True):
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        if write_body and body:
            self.wfile.write(body)

    def reply_json(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.reply(code, body, 'application/json; charset=utf-8', True)

    def redirect(self, location):
        self.send_response(302)
        self.send_header('Location', location)
        self.send_header('Content-Length', '0')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()

    def log_message(self, fmt, *args):
        sys.stderr.write('%s - %s\n' % (self.address_string(), fmt % args))


class Server(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def daemonize(pidfile, logfile):
    if os.fork() > 0:
        os._exit(0)
    os.setsid()
    if os.fork() > 0:
        os._exit(0)
    os.chdir('/')
    fd = os.open(logfile, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    os.dup2(fd, 1)
    os.dup2(fd, 2)
    if fd > 2:
        os.close(fd)
    devnull = os.open(os.devnull, os.O_RDONLY)
    os.dup2(devnull, 0)
    if devnull > 2:
        os.close(devnull)
    with open(pidfile, 'w') as f:
        f.write(str(os.getpid()))


def check_static():
    missing = []
    for env, _ctype in STATIC_ENV.values():
        path = os.environ.get(env) or ''
        if not path or not os.path.isfile(path):
            missing.append('%s (%s)' % (env, path or 'unset'))
    if missing:
        sys.exit('缺少页面文件: ' + ', '.join(missing))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=PORT_DEFAULT)
    ap.add_argument('--daemon', action='store_true')
    ap.add_argument('--pidfile', default='')
    ap.add_argument('--logfile', default='')
    args = ap.parse_args()
    check_static()
    if args.daemon:
        if not args.pidfile or not args.logfile:
            sys.exit('daemon 需要 --pidfile 和 --logfile')
        daemonize(args.pidfile, args.logfile)
    try:
        httpd = Server(('127.0.0.1', args.port), Handler)
    except OSError as e:
        sys.exit('端口 %s 起不来: %s' % (args.port, e))
    sys.stderr.write('listening 127.0.0.1:%s rev %s\n' % (args.port, code_rev()))
    httpd.serve_forever()


if __name__ == '__main__':
    main()
