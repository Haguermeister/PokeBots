#!/usr/bin/env python3
"""
Local web control panel for the shiny bot (UART version).
Run: python3 web_control.py [--port /dev/tty.usbserial-XXX]
Open: http://localhost:8000

NOTE: Manual Pico buttons (A/B/X, Save, Check Starter) only work when
the bot is stopped, since the serial port is exclusive.
"""

import argparse
import http.server
import json
import os
import subprocess
import time
import signal
import sys
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
  html, body { height: 100%; }
  body { font-family: -apple-system, sans-serif; background: #0b0e14; color: #f8f8f8; display: flex; justify-content: center; padding: 12px; }
  .container { width: 100%; max-width: 420px; display: flex; flex-direction: column; gap: 0; }
  h1 { text-align: center; font-size: 1.2em; padding: 10px 0; }
  .status { text-align: center; padding: 8px; border-radius: 10px; font-weight: 600; font-size: 0.9em; margin-bottom: 10px; }
  .status.running { background: #1a3d2a; border: 1px solid #2ecc71; color: #2ecc71; }
  .status.stopped { background: #3d1a1a; border: 1px solid #c0392b; color: #e74c3c; }
  /* Tabs */
  .tabs { display: flex; gap: 0; margin-bottom: 12px; background: #14181f; border-radius: 10px; border: 1px solid #2d3138; overflow: hidden; }
  .tab { flex: 1; padding: 10px; text-align: center; font-weight: 600; font-size: 0.85em; cursor: pointer; color: #8b949e; border: none; background: none; border-radius: 0; }
  .tab.active { background: #3a7bd5; color: #fff; }
  .tab:not(.active):active { background: rgba(255,255,255,0.05); }
  /* Panels */
  .panel { display: none; }
  .panel.active { display: flex; flex-direction: column; gap: 12px; }
  /* Buttons */
  .btn-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  button {
    padding: 16px 8px; border: none; border-radius: 12px; font-size: 1.1em;
    font-weight: 700; cursor: pointer; transition: transform 0.06s;
    -webkit-tap-highlight-color: transparent; touch-action: manipulation;
  }
  button:active { transform: scale(0.93); opacity: 0.8; }
  .btn-a { background: #48c855; color: #111; }
  .btn-b { background: #e8374a; color: #fff; }
  .btn-x { background: #4aa8d8; color: #0a2a3d; }
  .btn-home { background: #3a7bd5; color: #fff; }
  .btn-dpad { background: #3a3f4a; color: #ccc; font-size: 1.4em; padding: 18px; border-radius: 10px; }
  .btn-start { background: #2ecc71; color: #111; }
  .btn-stop { background: #c0392b; color: #fff; }
  .btn-restart { background: #e67e22; color: #111; }
  .btn-pause { background: #7c52a5; color: #fff; }
  .btn-resume { background: #3498db; color: #fff; }
  .btn-check { background: #606d7d; color: #fff; }
  .btn-save { background: #f0c730; color: #111; }
  .btn-reset { background: #6b3a3a; color: #ddd; }
  .log { background: #0d1117; border-radius: 10px; padding: 10px; font-family: 'SF Mono', monospace; font-size: 0.75em; height: 140px; overflow-y: auto; white-space: pre-wrap; -webkit-overflow-scrolling: touch; border: 1px solid #2d3138; color: #8b949e; }
  .section-label { font-size: 0.75em; color: #6b7280; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 4px; }
</style>
</head>
<body>
<div class="container">
  <h1>&#127918; Shiny Bot</h1>
  <div class="status" id="status">Checking...</div>

  <div class="tabs">
    <div class="tab active" onclick="switchTab('controller')">Controller</div>
    <div class="tab" onclick="switchTab('bot')">Bot</div>
    <div class="tab" onclick="switchTab('log')">Log</div>
  </div>

  <!-- CONTROLLER TAB -->
  <div class="panel active" id="panel-controller">
    <div class="btn-row">
      <button class="btn-a" onclick="press('A')">A</button>
      <button class="btn-b" onclick="press('B')">B</button>
    </div>
    <div class="btn-row">
      <button class="btn-home" onclick="press('HOME')">Home</button>
      <button class="btn-x" onclick="press('Y')">X</button>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;max-width:240px;margin:4px auto">
      <div></div>
      <button class="btn-dpad" onclick="press('DU')">&#9650;</button>
      <div></div>
      <button class="btn-dpad" onclick="press('DL')">&#9664;</button>
      <button class="btn-dpad" onclick="press('DD')">&#9660;</button>
      <button class="btn-dpad" onclick="press('DR')">&#9654;</button>
    </div>
  </div>

  <!-- BOT TAB -->
  <div class="panel" id="panel-bot">
    <div class="btn-row">
      <button class="btn-start" onclick="botAction('start')">&#9654; Start</button>
      <button class="btn-stop" onclick="botAction('stop')">&#9724; Stop</button>
    </div>
    <div class="btn-row">
      <button class="btn-restart" onclick="botAction('restart')">&#8635; Restart</button>
      <button class="btn-check" onclick="press('CHECK_STARTER')">&#128270; Check</button>
    </div>
    <div class="btn-row">
      <button class="btn-pause" onclick="botAction('pause')">&#10074;&#10074; Pause</button>
      <button class="btn-resume" onclick="botAction('resume')">&#9654; Resume</button>
    </div>
    <button class="btn-save" onclick="press('SAVE_GAME')" style="width:100%">&#11088; Save Shiny</button>
    <button class="btn-reset" onclick="resetCounters()" style="width:100%">Reset Counter &amp; Timer</button>
  </div>

  <!-- LOG TAB -->
  <div class="panel" id="panel-log">
    <div class="log" id="log"></div>
  </div>
</div>
<script>
  const log = document.getElementById('log');
  const status = document.getElementById('status');

  function switchTab(name) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    document.querySelector('.tab[onclick*=\"' + name + '\"]').classList.add('active');
    document.getElementById('panel-' + name).classList.add('active');
  }

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


def queue_save_sequence():
    """Save sequence from Pokemon summary screen: B*3 back out, DOWN*3 to save, A*2 confirm."""
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
    """B*4 to back out, then X + A*6 to navigate to summary."""
    steps = [
        ("press B 120", 0.22),
        ("press B 120", 0.22),
        ("press B 120", 0.22),
        ("press B 120", 0.30),
        ("press Y 120", 1.50),
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
    # Release serial port so the bot process can use it
    pico.close()
    bot_process = subprocess.Popen(
        [str(VENV_PYTHON), str(BOT_SCRIPT)],
        cwd=str(BOT_SCRIPT.parent),
        env={**os.environ},  # inherit current env (includes IMESSAGE_TO etc.)
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
        bot_process = None
        # Re-open serial for manual control
        try:
            pico.connect()
        except Exception:
            pass
        return "Bot stopped"
    bot_process = None
    return "Bot not running"


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

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
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", help="Serial port (e.g. /dev/tty.usbserial-0001)")
    args = parser.parse_args()

    pico.connect(port=args.port)
    print(f"Serial: {pico._port}")

    server = http.server.HTTPServer(('0.0.0.0', PORT), Handler)
    server.allow_reuse_address = True
    print(f"Control panel running at http://localhost:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        stop_bot()
        pico.close()
        server.server_close()
        print("\nShutdown.")
