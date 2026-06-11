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

/* user message bubbles (right-aligned) */
.msg.user {
  align-self: flex-end; background: #1a2740; border: 1px solid #2c4a7a; color: #cfe0ff;
}
/* optimistic queued bubble — floats until its turn starts processing */
.msg.user.queued {
  background: #1e2230; border: 1px dashed #4a5570; color: #9aa6c0;
  opacity: .7; font-style: italic;
}

/* processing placeholder (verbose off) */
.msg.processing { color: #888; font-style: italic; }

/* model reasoning / verbose accordion */
details.think {
  align-self: flex-start; max-width: 92%;
  background: #161616; border: 1px solid #333;
  border-radius: 8px; padding: 6px 10px;
  font-family: monospace; font-size: 12px; color: #888;
}
details.think summary {
  cursor: pointer; color: #999; font-family: system-ui; font-size: 12px;
}
details.think .think-body {
  white-space: pre-wrap; word-break: break-word; margin-top: 6px; line-height: 1.5;
}

/* verbose toggle button */
#btn-verbose {
  padding: 5px 10px; font-size: 13px;
  background: #2a2a2a; color: #888;
  border: none; border-radius: 6px; cursor: pointer;
}
#btn-verbose.on { background: #1b3a5c; color: #cfe0ff; }

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
  <button id="btn-verbose" title="Mostrar razonamiento del modelo">&#129504;</button>
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
let liveStream = '';    // raw streamed text of the turn in progress
let liveBox    = null;  // live container: thinking accordion or "procesando…"
let pendingQueued = []; // optimistic queued bubbles awaiting their user_turn event
// Verbose = show the model's working stream live. Persisted per device
// (UI preference, not conversation state — the bus stays source of truth).
let verboseOn  = localStorage.getItem('mirach-verbose') !== '0';

// ── DOM refs ─────────────────────────────────────────────────────────
const dot        = document.getElementById('dot');
const transcript = document.getElementById('transcript');
const msgInput   = document.getElementById('msg');
const btnSend    = document.getElementById('btn-send');
const btnStop    = document.getElementById('btn-stop');
const btnVerbose = document.getElementById('btn-verbose');

// ── Utilities ────────────────────────────────────────────────────────
const esc = s => String(s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;')
  .replace(/>/g, '&gt;').replace(/"/g, '&quot;');

function scrollDown() { transcript.scrollTop = transcript.scrollHeight; }

// Keep optimistic queued bubbles pinned to the bottom (in FIFO order) so they
// visually "wait" below all settled content until their turn starts processing.
function floatQueued() {
  for (const p of pendingQueued) transcript.appendChild(p.el);
}

function api(path, body) {
  return fetch(path, {
    method: 'POST',
    headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + TOKEN},
    body: JSON.stringify(body),
  });
}

// ── Event renderers ──────────────────────────────────────────────────
function onQueued(ev) {
  // A turn was enqueued (not yet processing): show it as a pending bubble that
  // floats at the bottom until its user_turn event settles it.
  const d = document.createElement('div');
  d.className = 'msg user queued';
  d.textContent = ev.text;
  transcript.appendChild(d);
  pendingQueued.push({el: d, text: ev.text});
  scrollDown();
}

function onQueueCleared() {
  // The pending queue was dropped (stop / clear_queue): remove floating bubbles.
  for (const p of pendingQueued) p.el.remove();
  pendingQueued = [];
}

function onUserTurn(ev) {
  // A new user turn settles any still-open live stream (e.g. interrupted turn).
  if (liveBox || liveStream) onDone({content: ''});
  // Settle a matching optimistic queued bubble (FIFO by text); else render fresh
  // (voice turns and other devices have no local optimistic bubble).
  const i = pendingQueued.findIndex(p => p.text === ev.text);
  if (i !== -1) {
    const el = pendingQueued.splice(i, 1)[0].el;
    el.className = 'msg user';
    transcript.appendChild(el);  // re-anchor at bottom so its response follows it
  } else {
    const d = document.createElement('div');
    d.className = 'msg user';
    d.textContent = ev.text;
    transcript.appendChild(d);
  }
  scrollDown();
}

function onTextDelta(ev) {
  liveStream += ev.delta;
  if (!liveBox) {
    if (verboseOn) {
      liveBox = document.createElement('details');
      liveBox.className = 'think';
      liveBox.open = true;
      liveBox.innerHTML = '<summary>&#129504; trabajando…</summary><div class="think-body"></div>';
    } else {
      liveBox = document.createElement('div');
      liveBox.className = 'msg processing';
      liveBox.textContent = 'procesando…';
    }
    transcript.appendChild(liveBox);
  }
  const body = liveBox.querySelector ? liveBox.querySelector('.think-body') : null;
  if (body) body.textContent = liveStream;
  scrollDown();
}

function onDone(ev) {
  const streamed = liveStream;
  liveStream = '';
  if (liveBox) { liveBox.remove(); liveBox = null; }
  const content = ev.content || '';

  // If the stream carried noticeably more than the final answer, it contained
  // reasoning/work — keep it available in a collapsed accordion (verbose only).
  const hadVerbose = streamed && content && streamed.length > content.length * 1.5;
  if (verboseOn && hadVerbose) {
    const d = document.createElement('details');
    d.className = 'think';
    d.innerHTML = '<summary>&#129504; proceso</summary><div class="think-body"></div>';
    d.querySelector('.think-body').textContent = streamed;
    transcript.appendChild(d);
  }

  // Final answer bubble: done.content (clean, what TTS speaks). On interrupt
  // (empty content) keep whatever streamed so the partial turn stays readable.
  const finalText = content || streamed;
  if (finalText) {
    const m = document.createElement('div');
    m.className = 'msg done';
    m.textContent = finalText;
    transcript.appendChild(m);
  }
  scrollDown();
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
      case 'queued':                onQueued(ev); break;
      case 'queue_cleared':         onQueueCleared(); break;
      case 'user_turn':             onUserTurn(ev); break;
      case 'text_delta':            onTextDelta(ev); break;
      case 'done':                  onDone(ev); break;
      case 'tool_call':             onToolCall(ev); break;
      case 'tool_result':           onToolResult(ev); break;
      case 'awaiting_confirmation': onAwaitingConfirmation(ev); break;
      case 'error':                 onError(ev); break;
      // 'cost' intentionally not rendered in the basic widget
    }
    floatQueued();  // keep any still-queued bubbles anchored at the bottom
    scrollDown();
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
  // The pending bubble is driven by the server's 'queued' event (single source
  // of truth) so it replays on resume and shows on every device — not optimism.
  api('/turn', {text, interrupt: false, clear_queue: false})
    .finally(() => { btnSend.disabled = msgInput.value.trim().length === 0; });
}

msgInput.addEventListener('input',   () => { btnSend.disabled = msgInput.value.trim().length === 0; });
msgInput.addEventListener('keydown', e  => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } });
btnSend.addEventListener('click', send);

// Pending bubbles are cleared by the server's 'queue_cleared' event (round-trip),
// keeping the bus the single source of truth across reloads and devices.
btnStop.addEventListener('click', () => api('/stop', {}));

// ── Verbose toggle ───────────────────────────────────────────────────
function renderVerboseBtn() { btnVerbose.classList.toggle('on', verboseOn); }
btnVerbose.addEventListener('click', () => {
  verboseOn = !verboseOn;
  localStorage.setItem('mirach-verbose', verboseOn ? '1' : '0');
  renderVerboseBtn();
});
renderVerboseBtn();
</script>

</body>
</html>
"""
