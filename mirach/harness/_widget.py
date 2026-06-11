"""Vanilla HTML/CSS/JS widget served inline by MirachServer at GET /.

The placeholder __MIRACH_TOKEN__ is replaced at serve time with the
loopback device token so the page auto-authenticates on load.

Reconnect strategy: EventSource does not carry `id:` frames, so the browser's
built-in Last-Event-ID reconnect would replay from the start.  Instead, the JS
tracks `since` (number of events received) and on onerror closes the EventSource
manually, then calls connect() after 2 s — reconnecting to /events?since=N.
This is simpler than adding `id:` wrappers to every SSE frame in server.py.
"""

WIDGET_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mirach</title>
<style>
/* ── Reset & base ───────────────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: system-ui, -apple-system, sans-serif;
  background: #0f0f0f; color: #e0e0e0;
  height: 100dvh; display: flex; flex-direction: column; overflow: hidden;
}

/* ── Header ─────────────────────────────────────────────────────── */
#header {
  padding: 10px 14px; background: #1a1a1a;
  border-bottom: 1px solid #2a2a2a;
  display: flex; align-items: center; gap: 10px; flex-shrink: 0;
}
#dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: #555; flex-shrink: 0; transition: background .3s;
}
#dot.on  { background: #4caf50; }
#dot.err { background: #f44336; }
#header h1 { font-size: 15px; font-weight: 600; flex: 1; }
#btn-stop {
  padding: 5px 12px; font-size: 13px;
  background: #c62828; color: #fff;
  border: none; border-radius: 6px; cursor: pointer;
}
#btn-stop:hover { background: #8e0000; }

/* ── Transcript ─────────────────────────────────────────────────── */
#transcript {
  flex: 1; overflow-y: auto; padding: 14px;
  display: flex; flex-direction: column; gap: 8px;
}

/* assistant text bubbles */
.msg {
  max-width: 88%; padding: 9px 13px; border-radius: 10px;
  line-height: 1.55; font-size: 14px;
  white-space: pre-wrap; word-break: break-word; align-self: flex-start;
}
.msg.live { background: #1e2a1e; border: 1px solid #4caf50; }
.msg.done { background: #1e2a1e; border: 1px solid #2a3a2a; }

/* error notice */
.err-notice {
  align-self: flex-start; max-width: 88%;
  padding: 8px 12px; border-radius: 8px; font-size: 13px;
  background: #2a1010; border: 1px solid #5a2222; color: #ff8080;
}

/* tool_call */
.tool-call {
  align-self: flex-start; max-width: 92%;
  background: #11142a; border: 1px solid #252860;
  border-radius: 8px; padding: 8px 12px; font-family: monospace; font-size: 12px;
}
.tool-call .tc-name { color: #8080e0; font-weight: bold; margin-bottom: 4px; }
.tool-call .tc-args { color: #6868b8; white-space: pre-wrap; word-break: break-all; }

/* tool_result */
.tool-result {
  align-self: flex-start; max-width: 92%;
  background: #0f1e10; border: 1px solid #1e4020;
  border-radius: 8px; padding: 8px 12px; font-family: monospace; font-size: 12px;
}
.tool-result .tr-label { color: #60c060; font-weight: bold; margin-bottom: 4px; }
.tool-result .tr-body  { color: #4a9a4a; white-space: pre-wrap; word-break: break-all; }

/* awaiting_confirmation */
.confirm-block {
  align-self: flex-start; max-width: 92%;
  background: #1e1200; border: 1px solid #4e3000;
  border-radius: 8px; padding: 10px 14px;
}
.confirm-block .cb-title {
  color: #ffa030; font-weight: 600; margin-bottom: 4px; font-size: 13px;
}
.confirm-block .cb-args {
  font-family: monospace; font-size: 12px; color: #cc8830;
  white-space: pre-wrap; word-break: break-all; margin-bottom: 8px;
}
.confirm-block .cb-btns { display: flex; gap: 8px; }
.btn-ok { padding: 6px 14px; background: #2e7d32; color: #fff; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; }
.btn-ok:hover     { background: #1b5e20; }
.btn-ok:disabled  { opacity: .45; cursor: not-allowed; }
.btn-no { padding: 6px 14px; background: #b71c1c; color: #fff; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; }
.btn-no:hover     { background: #7f0000; }
.btn-no:disabled  { opacity: .45; cursor: not-allowed; }

/* ── Input bar ──────────────────────────────────────────────────── */
#input-bar {
  padding: 10px 14px; background: #1a1a1a;
  border-top: 1px solid #2a2a2a; display: flex; gap: 8px; flex-shrink: 0;
}
#msg {
  flex: 1; padding: 9px 13px;
  background: #252525; color: #e0e0e0;
  border: 1px solid #383838; border-radius: 8px; font-size: 14px; outline: none;
}
#msg:focus { border-color: #4caf50; }
#btn-send {
  padding: 9px 16px; font-size: 14px;
  background: #2e7d32; color: #fff;
  border: none; border-radius: 8px; cursor: pointer;
}
#btn-send:hover    { background: #1b5e20; }
#btn-send:disabled { opacity: .45; cursor: not-allowed; }
</style>
</head>
<body>

<div id="header">
  <div id="dot"></div>
  <h1>Mirach</h1>
  <button id="btn-stop">Stop</button>
</div>

<div id="transcript"></div>

<div id="input-bar">
  <input id="msg" type="text" placeholder="Type a message…" autocomplete="off">
  <button id="btn-send" disabled>Send</button>
</div>

<script>
// ── Config (token injected at serve time) ────────────────────────────
const TOKEN = "__MIRACH_TOKEN__";

// ── State ────────────────────────────────────────────────────────────
let since      = 0;     // next event index for ?since= on reconnect
let es         = null;
let liveBubble = null;  // streaming bubble in progress, or null

// ── DOM refs ─────────────────────────────────────────────────────────
const dot        = document.getElementById('dot');
const transcript = document.getElementById('transcript');
const msgInput   = document.getElementById('msg');
const btnSend    = document.getElementById('btn-send');
const btnStop    = document.getElementById('btn-stop');

// ── Utilities ────────────────────────────────────────────────────────
const esc = s => String(s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;')
  .replace(/>/g, '&gt;').replace(/"/g, '&quot;');

function scrollDown() { transcript.scrollTop = transcript.scrollHeight; }

function api(path, body) {
  return fetch(path, {
    method: 'POST',
    headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + TOKEN},
    body: JSON.stringify(body),
  });
}

// ── Event renderers ──────────────────────────────────────────────────
function onTextDelta(ev) {
  if (!liveBubble) {
    liveBubble = document.createElement('div');
    liveBubble.className = 'msg live';
    transcript.appendChild(liveBubble);
  }
  liveBubble.textContent += ev.delta;
  scrollDown();
}

function onDone(ev) {
  if (liveBubble) {
    liveBubble.className = 'msg done';
    liveBubble = null;
  } else if (ev.content) {
    // Replay path: turn already finished, render final text directly
    const d = document.createElement('div');
    d.className = 'msg done';
    d.textContent = ev.content;
    transcript.appendChild(d);
    scrollDown();
  }
}

function onToolCall(ev) {
  const args = JSON.stringify(ev.arguments, null, 2);
  const d = document.createElement('div');
  d.className = 'tool-call';
  d.innerHTML = `<div class="tc-name">⚙ ${esc(ev.name)}</div><div class="tc-args">${esc(args)}</div>`;
  transcript.appendChild(d);
  scrollDown();
}

function onToolResult(ev) {
  const d = document.createElement('div');
  d.className = 'tool-result';
  const label = ev.error ? '✗ error' : '✓ result';
  d.innerHTML = `<div class="tr-label">${label}</div><div class="tr-body">${esc(ev.result)}</div>`;
  transcript.appendChild(d);
  scrollDown();
}

function onAwaitingConfirmation(ev) {
  const args = JSON.stringify(ev.arguments, null, 2);
  const d = document.createElement('div');
  d.className = 'confirm-block';
  d.innerHTML = `
    <div class="cb-title">⚠ Confirm: ${esc(ev.name)}</div>
    <div class="cb-args">${esc(args)}</div>
    <div class="cb-btns">
      <button class="btn-ok">Confirm</button>
      <button class="btn-no">Deny</button>
    </div>`;
  const freeze = () => d.querySelectorAll('button').forEach(b => { b.disabled = true; });
  d.querySelector('.btn-ok').addEventListener('click', () => {
    freeze(); api('/confirm', {tool_call_id: ev.tool_call_id});
  });
  d.querySelector('.btn-no').addEventListener('click', () => {
    freeze(); api('/deny', {tool_call_id: ev.tool_call_id});
  });
  transcript.appendChild(d);
  scrollDown();
}

function onError(ev) {
  const d = document.createElement('div');
  d.className = 'err-notice';
  d.textContent = '⚠ ' + ev.message;
  transcript.appendChild(d);
  scrollDown();
}

// ── SSE connection ───────────────────────────────────────────────────
function connect() {
  if (es) { es.close(); es = null; }
  const url = '/events?token=' + encodeURIComponent(TOKEN) + '&since=' + since;
  es = new EventSource(url);

  es.onopen = () => { dot.className = 'on'; };

  es.onmessage = e => {
    let ev;
    try { ev = JSON.parse(e.data); } catch { return; }
    since++;
    switch (ev.type) {
      case 'text_delta':            onTextDelta(ev); break;
      case 'done':                  onDone(ev); break;
      case 'tool_call':             onToolCall(ev); break;
      case 'tool_result':           onToolResult(ev); break;
      case 'awaiting_confirmation': onAwaitingConfirmation(ev); break;
      case 'error':                 onError(ev); break;
      // 'cost' intentionally not rendered in the basic widget
    }
  };

  es.onerror = () => {
    dot.className = 'err';
    // Close to prevent browser auto-reconnect (which ignores ?since=).
    // Our manual reconnect below passes the updated cursor.
    es.close(); es = null;
    setTimeout(connect, 2000);
  };
}

connect();

// ── Text input ───────────────────────────────────────────────────────
function send() {
  const text = msgInput.value.trim();
  if (!text) return;
  msgInput.value = '';
  btnSend.disabled = true;
  api('/turn', {text, interrupt: false, clear_queue: false})
    .finally(() => { btnSend.disabled = msgInput.value.trim().length === 0; });
}

msgInput.addEventListener('input',   () => { btnSend.disabled = msgInput.value.trim().length === 0; });
msgInput.addEventListener('keydown', e  => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } });
btnSend.addEventListener('click', send);

btnStop.addEventListener('click', () => api('/stop', {}));
</script>

</body>
</html>
"""
