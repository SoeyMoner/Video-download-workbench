// yt-dlp \u8d35\u80c4\u5de5\u4f5c\u53f0 - Application Logic
'use strict';

// ===== State =====
var STATE = {
  tasks: {},
  parsedInfo: null,
  terminalOpen: false,
};

// ===== DOM helpers =====
var $ = function(sel) { return document.querySelector(sel); };
var $$ = function(sel) { return document.querySelectorAll(sel); };

// ===== Init =====
document.addEventListener('DOMContentLoaded', function() {
  // Collapse panels
  $$('.collapse-header').forEach(function(h) {
    h.addEventListener('click', function() {
      var id = h.dataset.collapse;
      document.getElementById(id).classList.toggle('open');
    });
  });

  // Format preset toggle
  $('#select-preset').addEventListener('change', function() {
    $('#input-format-custom').classList.toggle('hidden', this.value !== 'custom');
  });

  // Output template preset
  $('#select-template-preset').addEventListener('change', function() {
    if (this.value) $('#input-output-template').value = this.value;
  });

  // Parse button
  $('#btn-parse').addEventListener('click', doParse);

  // Download button
  $('#btn-download').addEventListener('click', function() { doDownload(); });

  // Browse folder
  $('#btn-browse').addEventListener('click', function() {
    fetch('/api/browse-folder').then(function(r) { return r.json(); }).then(function(data) {
      if (data.ok && data.path) $('#input-outdir').value = data.path;
    }).catch(function() {});
  });
  // Terminal toggle
  $('#terminal-bar').addEventListener('click', function(e) {
    if (e.target.closest('button')) return;
    STATE.terminalOpen = !STATE.terminalOpen;
    $('#terminal-wrap').classList.toggle('open', STATE.terminalOpen);
  });

  // Clear log
  $('#btn-clear-log').addEventListener('click', function(e) {
    e.stopPropagation();
    $('#terminal-content').innerHTML = '';
  });

  // Tweaks toggle
  $('#tweaks-toggle').addEventListener('click', function() {
    $('#tweaks-panel').classList.toggle('visible');
  });

  // Tweak: accent color
  $('#tweak-accent').addEventListener('change', function() {
    var hex = '#' + this.value;
    document.documentElement.style.setProperty('--accent', hex);
    document.documentElement.style.setProperty('--accent-dim', hex + '99');
    document.documentElement.style.setProperty('--border-active', hex);
  });

  // Tweak: terminal font size
  $('#tweak-font-size').addEventListener('input', function() {
    $('#terminal-content').style.fontSize = this.value + 'px';
    $('#tweak-font-val').textContent = this.value + 'px';
  });

  // Tweak: sidebar width
  $('#tweak-sidebar').addEventListener('input', function() {
    $('#sidebar').style.width = this.value + 'px';
    $('#tweak-sidebar-val').textContent = this.value + 'px';
  });

  // Tweak: animations on/off
  $('#tweak-anim').addEventListener('change', function() {
    var off = this.value === 'off';
    document.documentElement.style.setProperty('--transition', off ? '0s' : '300ms cubic-bezier(0.25, 0, 0.15, 1)');
    document.documentElement.style.setProperty('--transition-fast', off ? '0s' : '180ms cubic-bezier(0.25, 0, 0.15, 1)');
  });

  // Keyboard shortcuts
  document.addEventListener('keydown', function(e) {
    if (e.ctrlKey && e.key === 'Enter') { e.preventDefault(); doParse(); }
    if (e.ctrlKey && e.key === 'd' && !e.shiftKey) { e.preventDefault(); doDownload(); }
  });

  // Load version
  fetchVersion();
});

// ===== Toast =====
var toastTimer;
function showToast(msg, type) {
  clearTimeout(toastTimer);
  var el = $('#toast');
  el.textContent = msg;
  el.className = 'toast show';
  if (type === 'error') el.style.borderColor = 'var(--error)';
  else if (type === 'success') el.style.borderColor = 'var(--success)';
  else el.style.borderColor = '';
  toastTimer = setTimeout(function() { el.classList.remove('show'); el.style.borderColor = ''; }, 3000);
}

// ===== API =====
function api(method, path, body) {
  var opts = { method: method, headers: {} };
  if (body) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  return fetch(path, opts).then(function(r) { return r.json(); });
}

function fetchVersion() {
  api('GET', '/api/version').then(function(data) {
    $('#version-display').textContent = 'v' + (data.version || '?');
  }).catch(function() {
    $('#version-display').textContent = 'v?';
  });
}

// ===== Collect form options =====
function collectOptions(url) {
  var opts = { url: url };

  var outDir = $('#input-outdir').value.trim();
  if (outDir) opts.out_dir = outDir;

  // Format
  var preset = $('#select-preset').value;
  if (preset === 'custom') {
    var custom = $('#input-format-custom').value.trim();
    if (custom) opts.format = custom;
  } else {
    var res = $('#select-resolution').value;
    if (res && preset.indexOf('bestvideo') !== -1) {
      opts.format = 'bestvideo[height<=' + res + ']+bestaudio/best[height<=' + res + ']/best';
    } else if (res && preset === 'bestvideo/best') {
      opts.format = 'bestvideo[height<=' + res + ']/best[height<=' + res + ']/best';
    } else {
      opts.format = preset;
    }
  }

  // Output template
  var tmpl = $('#input-output-template').value.trim();
  if (tmpl) opts.output_template = tmpl;

  // Subtitles
  if ($('#chk-write-subs').checked) opts.write_subs = true;
  if ($('#chk-auto-subs').checked) opts.write_auto_subs = true;
  if ($('#chk-embed-subs').checked) opts.embed_subs = true;
  var subLangs = $('#input-sub-langs').value.trim();
  if (subLangs) opts.sub_lang = subLangs;

  // Playlist
  var n;
  n = parseInt($('#input-pl-start').value); if (!isNaN(n)) opts.playlist_start = n;
  n = parseInt($('#input-pl-end').value); if (!isNaN(n)) opts.playlist_end = n;
  if ($('#chk-pl-random').checked) opts.playlist_random = true;
  if ($('#chk-pl-reverse').checked) opts.playlist_reverse = true;

  // Network
  var proxy = $('#input-proxy').value.trim(); if (proxy) opts.proxy = proxy;
  var cb = $('#select-cookies-browser').value; if (cb) opts.cookies_from_browser = cb;
  var cf = $('#input-cookies-file').value.trim(); if (cf) opts.cookies = cf;
  var rl = $('#input-rate-limit').value.trim(); if (rl) opts.rate_limit = rl;
  n = parseInt($('#input-retries').value); if (!isNaN(n)) opts.retries = n;
  n = parseInt($('#input-concurrent').value); if (!isNaN(n)) opts.concurrent_fragments = n;

  // Post-processing
  if ($('#chk-extract-audio').checked) {
    opts.extract_audio = true;
    opts.audio_format = $('#select-audio-format').value;
  }
  var aq = $('#select-audio-quality').value; if (aq) opts.audio_quality = parseInt(aq);
  if ($('#chk-embed-thumb').checked) opts.embed_thumbnail = true;
  if ($('#chk-embed-meta').checked) opts.embed_metadata = true;
  var merge = $('#select-merge-format').value; if (merge) { opts.merge_output_format = merge; if (opts.format && opts.format.indexOf('bestvideo') > -1) { if (merge === 'mp4') { opts.format = opts.format.replace(/bestvideo(\[[^\]]*\])?/, function(m) { return m.indexOf('[') > -1 ? m.slice(0, -1) + '][ext=mp4]' : m + '[ext=mp4]'; }).replace(/\+bestaudio(\[[^\]]*\])?/, function(m) { return m.indexOf('[') > -1 ? '+' + m.slice(1, -1) + '][ext=m4a]' : m + '[ext=m4a]'; }); } else if (merge === 'webm') { opts.format = opts.format.replace(/bestvideo(\[[^\]]*\])?/, function(m) { return m.indexOf('[') > -1 ? m.slice(0, -1) + '][ext=webm]' : m + '[ext=webm]'; }).replace(/\+bestaudio(\[[^\]]*\])?/, function(m) { return m.indexOf('[') > -1 ? '+' + m.slice(1, -1) + '][ext=webm]' : m + '[ext=webm]'; }); } } }

  // SponsorBlock
  var sbm = $('#select-sb-mark').value; if (sbm) opts.sponsorblock_mark = sbm;
  var sbr = $('#select-sb-remove').value; if (sbr) opts.sponsorblock_remove = sbr;

  // Filters
  var da = $('#input-date-after').value.trim(); if (da) opts.dateafter = da;
  var db = $('#input-date-before').value.trim(); if (db) opts.datebefore = db;
  n = parseInt($('#input-min-duration').value); if (!isNaN(n)) opts.min_duration = n;
  n = parseInt($('#input-max-duration').value); if (!isNaN(n)) opts.max_duration = n;
  var mf = $('#input-max-filesize').value.trim(); if (mf) opts.max_filesize = mf;
  var uname = $('#input-username').value.trim(); if (uname) opts.username = uname;
  var pwd = $('#input-password').value; if (pwd) opts.password = pwd;
  if ($('#chk-ignore-errors').checked) opts.ignore_errors = true;

  return opts;
}

// ===== Parse URL =====
function doParse() {
  var urls = $('#input-url').value.trim().split('\\n').filter(Boolean);
  if (urls.length === 0) { showToast('\u8bf7\u8f93\u5165 URL', 'error'); return; }

  var btn = $('#btn-parse');
  btn.textContent = '\u89e3\u6790\u4e2d...';
  btn.disabled = true;

  // Collect network options for parse
  var parseOpts = { url: urls[0], flat: false, verbose: true };
  var proxy = $('#input-proxy').value.trim(); if (proxy) parseOpts.proxy = proxy;
  var cb = $('#select-cookies-browser').value; if (cb) parseOpts.cookies_from_browser = cb;
  var cf = $('#input-cookies-file').value.trim(); if (cf) parseOpts.cookies = cf;
  api('POST', '/api/parse', parseOpts).then(function(data) {
    if (!data.ok) {
      showToast(data.error || '\u89e3\u6790\u5931\u8d25', 'error');
      appendLogLine('[\u89e3\u6790\u5931\u8d25] ' + (data.error || '\u672a\u77e5\u9519\u8bef'));
      if (data.stderr_full && data.stderr_full !== data.error) { appendLogLine(data.stderr_full); }
      return;
    }

    STATE.parsedInfo = data;
    showToast('\u5df2\u89e3\u6790\uff1a' + (data.title || '\u672a\u77e5'), 'success');
    $('#btn-download').style.display = '';
    $('#btn-download').textContent = '\u4e0b\u8f7d';

    appendLogLine('[\u5df2\u89e3\u6790] ' + data.title + ' (' + (data.duration_string || '?') + ', ' + (data.format_count || 0) + ' \u79cd\u683c\u5f0f)');
    addPreviewCard(data);
  }).catch(function(e) {
    showToast('\u89e3\u6790\u5931\u8d25\uff1a' + e.message, 'error');
  }).then(function() {
    btn.textContent = '\u89e3\u6790';
    btn.disabled = false;
  });
}

function addPreviewCard(data) {
  $$('.preview-card').forEach(function(c) { c.remove(); });

  var div = document.createElement('div');
  div.className = 'task-card preview-card';
  div.innerHTML = '<div class="task-header"><span class="task-title">' + escHtml(data.title || '\u672a\u77e5') + '</span></div>' +
    '<div class="task-stats">' +
    '<span><span class="stat-label">\u65f6\u957f\uff1a</span> ' + (data.duration_string || '?') + '</span>' +
    '<span><span class="stat-label">\u4e0a\u4f20\u8005\uff1a</span> ' + escHtml(data.uploader || '?') + '</span>' +
    '<span><span class="stat-label">\u683c\u5f0f\uff1a</span> ' + (data.format_count || 0) + ' \u79cd</span>' +
    '</div>';

  $('#empty-state').classList.add('hidden');
  var qa = $('#queue-area');
  qa.insertBefore(div, qa.firstChild);
}

// ===== Download =====
function doDownload() {
  var urls = $('#input-url').value.trim().split('\\n').filter(Boolean);
  if (urls.length === 0) { showToast('\u8bf7\u8f93\u5165 URL', 'error'); return; }

  var btn = $('#btn-download');
  btn.textContent = '\u542f\u52a8\u4e2d...';
  btn.disabled = true;

  function downloadNext(i) {
    if (i >= urls.length) {
      btn.textContent = '\u4e0b\u8f7d';
      btn.disabled = false;
      return;
    }
    var url = urls[i];
    var opts = collectOptions(url);
    opts.title = (STATE.parsedInfo && STATE.parsedInfo.webpage_url === url) ? STATE.parsedInfo.title : url;

    api('POST', '/api/download', opts).then(function(data) {
      if (!data.ok) {
        showToast('\u4e0b\u8f7d\u5931\u8d25\uff1a' + (data.error || '\u9519\u8bef'), 'error');
      } else {
        createTaskCard(data.task_id, opts.title, url);
        startProgressStream(data.task_id);
        showToast('\u5df2\u5f00\u59cb\u4e0b\u8f7d', 'success');
      }
      downloadNext(i + 1);
    }).catch(function(e) {
      showToast('\u9519\u8bef\uff1a' + e.message, 'error');
      downloadNext(i + 1);
    });
  }

  downloadNext(0);
}

// ===== Task Card =====
function createTaskCard(taskId, title, url) {
  $('#empty-state').classList.add('hidden');

  var card = document.createElement('div');
  card.className = 'task-card downloading pulse';
  card.id = 'task-' + taskId;
  card.innerHTML = '<div class="task-header">' +
    '<span class="task-title">' + escHtml(title) + '</span>' +
    '<span class="task-badge badge-downloading">\u4e0b\u8f7d\u4e2d</span>' +
    '</div>' +
    '<div class="task-stats">' +
    '<span id="speed-' + taskId + '"><span class="stat-label">\u901f\u5ea6\uff1a</span> ---</span>' +
    '<span id="eta-' + taskId + '"><span class="stat-label">\u5269\u4f59\uff1a</span> ---</span>' +
    '<span id="progress-text-' + taskId + '"><span class="stat-label">\u8fdb\u5ea6\uff1a</span> 0%</span>' +
    '</div>' +
    '<div class="progress-wrap"><div class="progress-fill" id="progress-' + taskId + '" style="width:0%"></div></div>' +
    '<div class="task-actions">' +
    '<button class="btn btn-danger btn-sm" onclick="cancelTask(\'' + taskId + '\')">\u53d6\u6d88</button>' +
    '<button class="btn btn-ghost btn-sm" onclick="removeTaskCard(\'' + taskId + '\')">\u5173\u95ed</button>' +
    '</div>';

  $('#queue-area').appendChild(card);
}

function updateTaskCard(taskId, status) {
  var card = document.getElementById('task-' + taskId);
  if (!card) return;

  var pf = $('#progress-' + taskId);
  var pt = $('#progress-text-' + taskId);
  var sp = $('#speed-' + taskId);
  var et = $('#eta-' + taskId);

  if (pf) pf.style.width = (status.progress || 0) + '%';
  if (pt) pt.innerHTML = '<span class="stat-label">\u8fdb\u5ea6\uff1a</span> ' + (status.progress || 0).toFixed(1) + '%';
  if (sp) sp.innerHTML = '<span class="stat-label">\u901f\u5ea6\uff1a</span> ' + (status.speed || '---');
  if (et) et.innerHTML = '<span class="stat-label">\u5269\u4f59\uff1a</span> ' + (status.eta || '---');

  var badge = card.querySelector('.task-badge');
  card.classList.remove('downloading', 'pulse', 'completed', 'error', 'cancelled');

  if (status.status === 'downloading') {
    card.classList.add('downloading', 'pulse');
    if (badge) { badge.className = 'task-badge badge-downloading'; badge.textContent = '\u4e0b\u8f7d\u4e2d'; }
  } else if (status.status === 'completed') {
    card.classList.add('completed');
    if (badge) { badge.className = 'task-badge badge-completed'; badge.textContent = '\u5b8c\u6210'; }
  } else if (status.status === 'error') {
    card.classList.add('error');
    if (badge) { badge.className = 'task-badge badge-error'; badge.textContent = '\u5931\u8d25'; }
  } else if (status.status === 'cancelled') {
    card.classList.add('cancelled');
    if (badge) { badge.className = 'task-badge badge-cancelled'; badge.textContent = '\u5df2\u53d6\u6d88'; }
  }

  var tc = $('#terminal-content');
  if (tc) tc.scrollTop = tc.scrollHeight;
}

function cancelTask(taskId) {
  api('POST', '/api/cancel', { task_id: taskId });
  showToast('\u53d6\u6d88\u4e2d...');
}

function removeTaskCard(taskId) {
  var card = document.getElementById('task-' + taskId);
  if (card) card.remove();
  var qa = $('#queue-area');
  var cards = qa.querySelectorAll('.task-card');
  if (cards.length === 0) $('#empty-state').classList.remove('hidden');
}

// ===== Progress Stream (SSE) =====
function startProgressStream(taskId) {
  if (!STATE.terminalOpen) {
    STATE.terminalOpen = true;
    $('#terminal-wrap').classList.add('open');
  }

  var es = new EventSource('/api/progress?id=' + taskId);

  es.addEventListener('status', function(e) {
    var data = JSON.parse(e.data);
    updateTaskCard(taskId, data);
  });

  es.addEventListener('message', function(e) {
    var data = JSON.parse(e.data);
    if (data.line) appendLogLine(data.line);
  });

  es.addEventListener('error', function() {
    es.close();
  });
}

// ===== Terminal =====
function appendLogLine(line) {
  var div = document.createElement('div');
  div.className = 'terminal-line';
  div.textContent = line;
  var tc = $('#terminal-content');
  tc.appendChild(div);

  while (tc.children.length > 1000) {
    tc.firstChild.remove();
  }

  tc.scrollTop = tc.scrollHeight;
}

// ===== Helpers =====
function escHtml(s) {
  if (!s) return '';
  var div = document.createElement('div');
  div.textContent = s;
  return div.innerHTML;
}
