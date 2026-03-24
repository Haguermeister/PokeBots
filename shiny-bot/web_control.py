#!/usr/bin/env python3
"""
Local web control panel for the shiny bot.
Run: python3 web_control.py
Open: http://localhost:5000
"""

import http.server
import json
import os
import subprocess
import time
import signal
from pathlib import Path
import pico

PORT = 8000
BOT_SCRIPT = Path(__file__).resolve().parent / "hunt_loop.py"
VENV_PYTHON = Path(__file__).resolve().parent / "venv" / "bin" / "python3"
PAUSE_FILE = Path(__file__).resolve().parent / "pause_requested.flag"
BASE_DIR = Path(__file__).resolve().parent

bot_process = None

HTML = """<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no">
<title>Shiny Bot Control</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { height: 100%; overflow: hidden; }
  body { font-family: -apple-system, sans-serif; background: radial-gradient(circle at top, #1f2430 0%, #11151d 45%, #0b0e14 100%); color: #f8f8f8; display: flex; justify-content: center; align-items: flex-start; padding: 12px; }
  .container { width: 100%; max-width: 500px; display: flex; flex-direction: column; gap: 14px; background: rgba(20, 24, 31, 0.93); border: 2px solid #2d3138; border-radius: 16px; padding: 14px; box-shadow: 0 10px 24px rgba(0,0,0,0.35); }
  h1 { text-align: center; font-size: 1.3em; letter-spacing: 0.03em; }
  .status { text-align: center; padding: 10px; border-radius: 10px; font-weight: bold; font-size: 0.95em; border: 1px solid rgba(255,255,255,0.12); }
  .status.running { background: #1f8f62; }
  .status.stopped { background: #b33a3a; }
  .section h2 { font-size: 0.8em; margin-bottom: 8px; color: #c2c7cf; text-transform: uppercase; letter-spacing: 1px; }
  .btn-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; }
  .btn-row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  button {
    padding: 20px 10px; border: none; border-radius: 12px; font-size: 1.2em;
    font-weight: bold; cursor: pointer; transition: transform 0.08s, opacity 0.08s;
    -webkit-tap-highlight-color: transparent; touch-action: manipulation;
  }
  button:active { transform: scale(0.93); opacity: 0.7; }
  .btn-a { background: #5ecf62; color: #111; }
  .btn-b { background: #e60012; color: #fff; }
  .btn-x { background: #00b8f0; color: #07253a; }
  .btn-start { background: #1f8f62; color: #fff; }
  .btn-stop { background: #b33a3a; color: #fff; }
  .btn-restart { background: #f57c00; color: #1f1f1f; }
  .btn-pause { background: #8e44ad; color: #fff; }
  .btn-resume { background: #2d98da; color: #fff; }
  .btn-check { background: #5f6b7a; color: #fff; }
  .btn-save { background: #f1c40f; color: #1f1f1f; }
  .log { background: #0d1117; border-radius: 10px; padding: 10px; font-family: monospace; font-size: 0.8em; height: 120px; overflow-y: auto; white-space: pre-wrap; -webkit-overflow-scrolling: touch; border: 1px solid #2d3138; }
</style>
</head>
<body>
<div class="container">
  <h1>Shiny Bot Control</h1>
  <div class="status" id="status">Checking...</div>

  <div class="section">
    <h2>Buttons</h2>
    <div class="btn-grid">
      <button class="btn-a" onclick="press('A')">A</button>
      <button class="btn-b" onclick="press('B')">B</button>
      <button class="btn-x" onclick="press('X')">X</button>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-top:10px;max-width:200px;margin-left:auto;margin-right:auto">
      <div></div>
      <button style="background:#5f6b7a;color:#fff;padding:14px;border:none;border-radius:8px;font-size:1.1em;cursor:pointer" onclick="press('DU')">&9650;</button>
      <div></div>
      <button style="background:#5f6b7a;color:#fff;padding:14px;border:none;border-radius:8px;font-size:1.1em;cursor:pointer" onclick="press('DL')">&9664;</button>
      <button style="background:#5f6b7a;color:#fff;padding:14px;border:none;border-radius:8px;font-size:1.1em;cursor:pointer" onclick="press('DD')">&9660;</button>
      <button style="background:#5f6b7a;color:#fff;padding:14px;border:none;border-radius:8px;font-size:1.1em;cursor:pointer" onclick="press('DR')">&9654;</button>
    </div>
    <div style="display:grid;grid-template-columns:1fr;gap:8px;margin-top:10px;max-width:200px;margin-left:auto;margin-right:auto">
      <button style="background:#2d98da;color:#fff;padding:12px;border:none;border-radius:8px;cursor:pointer" onclick="press('HOME')">Home</button>
    </div>
  </div>

  <div class="section">
    <h2>Bot Control</h2>
    <div class="btn-row">
      <button class="btn-start" onclick="botAction('start')">Start</button>
      <button class="btn-stop" onclick="botAction('stop')">Stop</button>
    </div>
    <div class="btn-row" style="margin-top:10px">
      <button class="btn-restart" onclick="botAction('restart')">Restart</button>
      <button class="btn-check" onclick="press('CHECK_STARTER')">Check Starter</button>
    </div>
    <div class="btn-row" style="margin-top:10px">
      <button class="btn-pause" onclick="botAction('pause')">Pause After Check</button>
      <button class="btn-resume" onclick="botAction('resume')">Resume</button>
    </div>
    <div class="btn-row" style="margin-top:10px; grid-template-columns: 1fr;">
      <button class="btn-save" onclick="press('SAVE_GAME')">Save Shiny</button>
    </div>
    <div class="btn-row" style="margin-top:10px; grid-template-columns: 1fr;">
      <button style="background:#e74c3c;color:#fff;padding:14px;border:none;border-radius:10px;font-size:1em;cursor:pointer" onclick="resetCounters()">Reset Counter &amp; Timer</button>
    </div>
  </div>

  <div class="section">
    <h2>Log</h2>
    <div class="log" id="log"></div>
  </div>
</div>
<script>
  const log = document.getElementById('log');
  const status = document.getElementById('status');

  function addLog(msg) {
    const time = new Date().toLocaleTimeString();
    log.textContent += time + ' ' + msg + '\\n';
    log.scrollTop = log.scrollHeight;
  }

  async function press(btn) {
    try {
      const res = await fetch('/press', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({button: btn}) });
      const data = await res.json();
      addLog(data.msg);
    } catch(e) { addLog('Error: ' + e); }
  }

  async function botAction(action) {
    try {
      const res = await fetch('/bot', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({action: action}) });
      const data = await res.json();
      addLog(data.msg);
      checkStatus();
    } catch(e) { addLog('Error: ' + e); }
  }

  async function resetCounters() {
    if (!confirm('Reset encounter counter, timer, and hunt state to 0?')) return;
    try {
      const res = await fetch('/reset_counters', { method: 'POST' });
      const data = await res.json();
      addLog(data.msg);
    } catch(e) { addLog('Error: ' + e); }
  }

  async function checkStatus() {
    try {
      const res = await fetch('/status');
      const data = await res.json();
      status.textContent = data.bot;
      status.className = 'status ' + (data.running ? 'running' : 'stopped');
    } catch(e) {}
  }

  checkStatus();
  setInterval(checkStatus, 3000);
</script>
</body>
</html>"""


def queue_commands(commands, *, clear_first=False, label="sequence"):
    if clear_first:
        clear_resp = pico.post('/clear').strip()
        if not clear_resp.startswith("OK"):
            return f"{label} failed: clear queue returned '{clear_resp}'"

    for cmd in commands:
        resp = pico.send_cmd(cmd)
        if not resp.startswith("OK"):
            return f"{label} failed at '{cmd}': {resp}"

    return f"Queued {label}"


def queue_save_sequence():
    """Save sequence from Pokemon summary screen: B×3 back out, DOWN×3 to save, A×2 confirm."""
    steps = [
        ("press B 120", 0.26),
        ("press B 120", 0.26),
        ("press B 120", 0.38),
        ("dpad DOWN 120", 0.22),
        ("dpad DOWN 120", 0.22),
        ("dpad DOWN 120", 0.26),
        ("press A 120", 0.65),
        ("press A 120", 0.0),
    ]
    for cmd, delay in steps:
        resp = pico.send_cmd(cmd)
        if not resp.startswith("OK"):
            return f"Save failed at '{cmd}': {resp}"
        if delay > 0:
            time.sleep(delay)
    return "Save sequence sent"


def queue_check_starter_sequence():
    """B×4 to back out, then X + A×6 to navigate to summary."""
    steps = [
        ("press B 120", 0.22),
        ("press B 120", 0.22),
        ("press B 120", 0.22),
        ("press B 120", 0.30),
        ("press X 120", 1.50),
        ("press A 120", 0.40),
        ("press A 120", 0.40),
        ("press A 120", 0.40),
        ("press A 120", 0.40),
        ("press A 120", 0.40),
        ("press A 120", 0.0),
    ]
    for cmd, delay in steps:
        resp = pico.send_cmd(cmd)
        if not resp.startswith("OK"):
            return f"Check starter failed at '{cmd}': {resp}"
        if delay > 0:
            time.sleep(delay)
    return "Check starter sequence sent"


def start_bot():
    global bot_process
    if bot_process and bot_process.poll() is None:
        return "Bot already running"
    bot_process = subprocess.Popen(
        [str(VENV_PYTHON), str(BOT_SCRIPT)],
        cwd=str(BOT_SCRIPT.parent),
        env={**os.environ},
    )
    return f"Bot started (PID {bot_process.pid})"


def reset_counters():
    """Reset encounter count, timer, and hunt state to 0."""
    enc_file = BASE_DIR / "encounter_count.txt"
    time_file = BASE_DIR / "encounter_time.txt"
    state_file = BASE_DIR / "hunt_state.json"

    enc_file.write_text("Soft Resets: 0", encoding="utf-8")
    time_file.write_text("00:00:00", encoding="utf-8")
    state_file.write_text(json.dumps({
        "attempt": 0,
        "total_runtime_seconds": 0,
        "recovery_attempts": 0,
    }), encoding="utf-8")
    return "Counter, timer, and hunt state reset to 0"


def request_pause():
    PAUSE_FILE.write_text("pause\n", encoding="utf-8")
    return "Pause requested: bot will pause after current shiny check"


def clear_pause():
    try:
        PAUSE_FILE.unlink()
    except FileNotFoundError:
        pass
    return "Resume requested"


def stop_bot():
    global bot_process
    if bot_process and bot_process.poll() is None:
        bot_process.send_signal(signal.SIGINT)
        try:
            bot_process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            bot_process.kill()
        msg = "Bot stopped"
        bot_process = None
        return msg
    bot_process = None
    return "Bot not running"


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # suppress default logging

    def _send_json(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html):
        body = html.encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == '/':
            self._send_html(HTML)
        elif self.path == '/status':
            running = bot_process is not None and bot_process.poll() is None
            self._send_json({
                'running': running,
                'bot': f"Bot running (PID {bot_process.pid})" if running else "Bot stopped",
            })
        else:
            self.send_error(404)

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length).decode() if length else '{}'
        data = json.loads(body)

        if self.path == '/press':
          btn = data.get('button', '')
          if btn == 'CHECK_STARTER':
            result = queue_check_starter_sequence()
            self._send_json({'msg': result})
          elif btn == 'SAVE_GAME':
            result = queue_save_sequence()
            self._send_json({'msg': result})
          elif btn in ('DU', 'DD', 'DL', 'DR'):
            dpad_map = {'DU': 'UP', 'DD': 'DOWN', 'DL': 'LEFT', 'DR': 'RIGHT'}
            result = pico.send_cmd(f'dpad {dpad_map[btn]} 120')
            self._send_json({'msg': f'D-pad {dpad_map[btn]}: {result}'})
          elif btn == 'START':
            result = pico.send_cmd('press + 120')
            self._send_json({'msg': f'Start (+): {result}'})
          else:
            result = pico.send_cmd(f'press {btn} 120')
            self._send_json({'msg': f'Pressed {btn}: {result}'})

        elif self.path == '/bot':
            action = data.get('action', '')
            if action == 'start':
                self._send_json({'msg': start_bot()})
            elif action == 'stop':
                self._send_json({'msg': stop_bot()})
            elif action == 'restart':
                stop_bot()
                self._send_json({'msg': start_bot()})
            elif action == 'pause':
                self._send_json({'msg': request_pause()})
            elif action == 'resume':
                self._send_json({'msg': clear_pause()})
            else:
                self._send_json({'msg': 'Unknown action'}, 400)

        elif self.path == '/reset_counters':
            self._send_json({'msg': reset_counters()})

        else:
            self.send_error(404)


if __name__ == '__main__':
    server = http.server.HTTPServer(('0.0.0.0', PORT), Handler)
    server.allow_reuse_address = True
    print(f"Control panel running at http://localhost:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        stop_bot()
        server.server_close()
        print("\nShutdown.")
