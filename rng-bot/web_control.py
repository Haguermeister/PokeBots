#!/usr/bin/env python3
"""
RNG Manipulation Web Control for FRLG Shiny Starters.

Run: python3 web_control.py
Open: http://localhost:5000

Features:
  - Seed browser: view all initial seeds with timing info
  - Shiny finder: for each seed, find all shiny Pokemon in advance range
  - Target selector: pick a specific shiny to hit
  - Timer: 3-stage Eon Timer equivalent for automation
  - Calibration: adjust timing based on actual results
  - Manual controls: button presses for testing
"""

import http.server
import json
import threading
import subprocess
import signal
import time
from pathlib import Path

import pico
import rng_engine
import seed_data
import pokemon_data
import calibration
import tid_sid

PORT = 5001
BASE_DIR = Path(__file__).resolve().parent
VENV_PYTHON = BASE_DIR / "venv" / "bin" / "python3"

# ── State ────────────────────────────────────────────────────────────────────
STATE_FILE = BASE_DIR / "rng_state.json"

DEFAULT_STATE = {
    "tid": 0,
    "sid": 0,
    "tid_set": False,
    "selected_seed": None,          # hex string
    "selected_seed_frame": None,
    "selected_advance": None,
    "selected_pokemon": "Bulbasaur",
    "target_pokemon": None,         # full pokemon dict when target is locked
    "min_advance": 1000,
    "max_advance": 100000,
    "calibration_offset_ms": 0.0,
    "timer_offset_ms": 0.0,        # NX = 0, NX2 = -750
    "attempts": 0,
    "last_result": None,
}

state = dict(DEFAULT_STATE)
state_lock = threading.Lock()
seeds_cache: list[dict] = []
shiny_counts_cache: dict[str, int] = {}  # seed_hex -> shiny count
shiny_cache_key: str = ""  # "tid:sid:min:max" — invalidated on change
shiny_cache_ready = threading.Event()
shiny_cache_computing = False
bot_process = None


def load_state():
    global state
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            for k, v in saved.items():
                if k in state:
                    state[k] = v
        except (json.JSONDecodeError, OSError):
            pass


def save_state():
    tmp = STATE_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    tmp.replace(STATE_FILE)


def init_seeds():
    global seeds_cache
    seeds_cache = seed_data.load_or_download_seeds()
    print(f"Loaded {len(seeds_cache)} initial seeds")


def _compute_shiny_counts_bg():
    """Background thread: compute shiny counts for all seeds."""
    global shiny_counts_cache, shiny_cache_key, shiny_cache_computing
    shiny_cache_computing = True
    shiny_cache_ready.clear()

    tid = state["tid"]
    sid = state["sid"]
    min_adv = state["min_advance"]
    max_adv = state["max_advance"]
    key = f"{tid}:{sid}:{min_adv}:{max_adv}"

    print(f"Computing shiny counts for {len(seeds_cache)} seeds (TID={tid} SID={sid} range={min_adv}-{max_adv})...")
    counts: dict[str, int] = {}
    for i, s in enumerate(seeds_cache):
        counts[s["seed_hex"]] = rng_engine.count_shinies_in_range(
            s["initial_seed"], tid, sid, min_adv, max_adv,
        )

    with state_lock:
        shiny_counts_cache = counts
        shiny_cache_key = key
    shiny_cache_computing = False
    shiny_cache_ready.set()
    total = sum(counts.values())
    print(f"Shiny count computation complete: {total} total shiny frames across {len(counts)} seeds")


def start_shiny_count_bg():
    """Start or restart shiny count computation in background."""
    if not state["tid_set"]:
        return
    key = f"{state['tid']}:{state['sid']}:{state['min_advance']}:{state['max_advance']}"
    if key == shiny_cache_key and shiny_cache_ready.is_set():
        return  # already computed
    t = threading.Thread(target=_compute_shiny_counts_bg, daemon=True)
    t.start()


# ── HTML UI ──────────────────────────────────────────────────────────────────

def _load_html() -> str:
    html_path = BASE_DIR / "index.html"
    with open(html_path, "r", encoding="utf-8") as f:
        return f.read()

HTML = _load_html()


# ── Request Handler ──────────────────────────────────────────────────────────

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _json(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, html):
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            self._html(HTML)
        else:
            self.send_error(404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode() if length else "{}"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            self._json({"error": "Invalid JSON"}, 400)
            return

        path = self.path
        if not path.startswith("/api/"):
            self.send_error(404)
            return

        endpoint = path[5:]  # strip /api/

        try:
            result = handle_api(endpoint, data)
            self._json(result)
        except Exception as e:
            self._json({"error": str(e)}, 500)


def handle_api(endpoint: str, data: dict) -> dict:
    """Route API calls to handler functions."""
    with state_lock:
        if endpoint == "status":
            return api_status()
        elif endpoint == "set_tid":
            return api_set_tid(data)
        elif endpoint == "set_pokemon":
            return api_set_pokemon(data)
        elif endpoint == "set_range":
            return api_set_range(data)
        elif endpoint == "set_calibration":
            return api_set_calibration(data)
        elif endpoint == "refresh_seeds":
            return api_refresh_seeds()
        elif endpoint == "get_seeds":
            return api_get_seeds(data)
        elif endpoint == "select_seed":
            return api_select_seed(data)
        elif endpoint == "get_shinies":
            return api_get_shinies(data)
        elif endpoint == "lock_target":
            return api_lock_target(data)
        elif endpoint == "press":
            return api_press(data)
        elif endpoint == "sequence":
            return api_sequence(data)
        elif endpoint == "start_automation":
            return api_start_automation()
        elif endpoint == "stop_automation":
            return api_stop_automation()
        elif endpoint == "bot_status":
            return api_bot_status()
        elif endpoint == "bot_log":
            return api_bot_log(data)
        elif endpoint == "calibrate":
            return api_calibrate(data)
        elif endpoint == "reverse_ivs":
            return api_reverse_ivs(data)
        elif endpoint == "auto_detect_tid":
            return api_auto_detect_tid()
        elif endpoint == "compute_sid":
            return api_compute_sid(data)
        else:
            return {"error": f"Unknown endpoint: {endpoint}"}


def api_status() -> dict:
    pico_ok = False
    try:
        r = pico.post("/ping")
        pico_ok = "OK" in r or "pong" in r.lower() or r.strip() != ""
    except Exception:
        pass

    return {
        **state,
        "seed_count": len(seeds_cache),
        "pico_ok": pico_ok,
    }


def api_set_tid(data: dict) -> dict:
    tid = int(data.get("tid", 0)) & 0xFFFF
    sid = int(data.get("sid", 0)) & 0xFFFF
    state["tid"] = tid
    state["sid"] = sid
    state["tid_set"] = True
    save_state()
    start_shiny_count_bg()
    return {"msg": f"TID={tid} SID={sid} saved"}


def api_set_pokemon(data: dict) -> dict:
    name = data.get("pokemon", "Bulbasaur")
    if name in pokemon_data.STARTERS:
        state["selected_pokemon"] = name
        save_state()
        return {"msg": f"Pokemon set to {name}"}
    return {"error": "Invalid pokemon name"}


def api_set_range(data: dict) -> dict:
    state["min_advance"] = max(0, int(data.get("min_advance", 1000)))
    state["max_advance"] = max(1, int(data.get("max_advance", 100000)))
    save_state()
    start_shiny_count_bg()
    return {"msg": f"Range set to {state['min_advance']}–{state['max_advance']}"}


def api_set_calibration(data: dict) -> dict:
    state["timer_offset_ms"] = float(data.get("timer_offset_ms", 0))
    state["calibration_offset_ms"] = float(data.get("calibration_offset_ms", 0))
    save_state()
    return {"msg": "Calibration saved"}


def api_refresh_seeds() -> dict:
    global seeds_cache
    seeds_cache = seed_data.load_or_download_seeds(force_download=True)
    return {"msg": f"Downloaded {len(seeds_cache)} seeds"}


def api_get_seeds(data: dict) -> dict:
    """Return seeds with shiny counts from background cache."""
    if not state["tid_set"]:
        result = []
        for s in seeds_cache:
            result.append({
                "seed_hex": s["seed_hex"],
                "seed_frame": s["seed_frame"],
                "time_ms": seed_data.frame_to_ms(s["seed_frame"]),
                "shiny_count": 0,
            })
        return {"seeds": result, "computing": False}

    # Start background computation if needed
    start_shiny_count_bg()

    computing = not shiny_cache_ready.is_set()
    result = []
    for s in seeds_cache:
        result.append({
            "seed_hex": s["seed_hex"],
            "seed_frame": s["seed_frame"],
            "time_ms": seed_data.frame_to_ms(s["seed_frame"]),
            "shiny_count": shiny_counts_cache.get(s["seed_hex"], 0),
        })

    return {"seeds": result, "computing": computing}


def api_select_seed(data: dict) -> dict:
    state["selected_seed"] = data.get("seed_hex", "")
    state["selected_seed_frame"] = int(data.get("seed_frame", 0))
    save_state()
    return {"msg": f"Selected seed {state['selected_seed']}"}


def api_get_shinies(data: dict) -> dict:
    """Get all shiny Pokemon for the selected seed."""
    if not state["selected_seed"]:
        return {"error": "No seed selected", "shinies": []}
    if not state["tid_set"]:
        return {"error": "Set TID/SID first", "shinies": []}

    seed_hex = state["selected_seed"]
    seed_entry = seed_data.get_seed_by_hex(seeds_cache, seed_hex)
    if not seed_entry:
        return {"error": f"Seed {seed_hex} not found", "shinies": []}

    pokemon_name = data.get("pokemon", state["selected_pokemon"])
    if pokemon_name not in pokemon_data.STARTERS:
        pokemon_name = state["selected_pokemon"]

    tid, sid = state["tid"], state["sid"]
    min_adv = state["min_advance"]
    max_adv = state["max_advance"]

    shinies = pokemon_data.generate_starter_spread(
        seed_entry["initial_seed"], tid, sid, pokemon_name,
        min_adv, max_adv, shiny_only=True,
    )

    return {
        "shinies": shinies,
        "seed_hex": seed_hex,
        "seed_frame": seed_entry["seed_frame"],
        "min_advance": min_adv,
        "max_advance": max_adv,
        "pokemon": pokemon_name,
    }


def api_lock_target(data: dict) -> dict:
    target = data.get("target")
    if not target:
        return {"error": "No target provided"}
    state["target_pokemon"] = target
    state["selected_advance"] = target.get("advance")
    save_state()
    return {"msg": f"Target locked: {target.get('pokemon', '?')} @ advance {target.get('advance', '?')}"}


def api_press(data: dict) -> dict:
    btn = data.get("button", "")
    if not btn:
        return {"error": "No button specified"}

    # Map D-pad names
    dpad_map = {"DU": "dpad UP", "DD": "dpad DOWN", "DL": "dpad LEFT", "DR": "dpad RIGHT"}
    if btn in dpad_map:
        result = pico.send_cmd(f"{dpad_map[btn]} 120")
    else:
        result = pico.send_cmd(f"press {btn} 120")
    return {"msg": f"{btn}: {result}"}


def api_sequence(data: dict) -> dict:
    name = data.get("name", "")
    if name == "soft_reset":
        pico.post("/reset")
        return {"msg": "Soft reset sent"}
    elif name == "check_starter":
        return _run_check_starter()
    elif name == "save_game":
        return _run_save_game()
    return {"error": f"Unknown sequence: {name}"}


def _run_check_starter() -> dict:
    steps = [
        ("press B 120", 0.22), ("press B 120", 0.22),
        ("press B 120", 0.22), ("press B 120", 0.30),
        ("press X 120", 1.50),
        ("press A 120", 0.40), ("press A 120", 0.40),
        ("press A 120", 0.40), ("press A 120", 0.40),
        ("press A 120", 0.40), ("press A 120", 0.0),
    ]
    for cmd, delay in steps:
        r = pico.send_cmd(cmd)
        if not r.startswith("OK"):
            return {"msg": f"Check starter failed at '{cmd}': {r}"}
        if delay > 0:
            time.sleep(delay)
    return {"msg": "Check starter sequence sent"}


def _run_save_game() -> dict:
    steps = [
        ("press B 120", 0.26), ("press B 120", 0.26), ("press B 120", 0.38),
        ("dpad DOWN 120", 0.22), ("dpad DOWN 120", 0.22), ("dpad DOWN 120", 0.26),
        ("press A 120", 0.65), ("press A 120", 0.0),
    ]
    for cmd, delay in steps:
        r = pico.send_cmd(cmd)
        if not r.startswith("OK"):
            return {"msg": f"Save failed at '{cmd}': {r}"}
        if delay > 0:
            time.sleep(delay)
    return {"msg": "Save sequence sent"}


def api_start_automation() -> dict:
    """Start the automated RNG manipulation loop."""
    global bot_process
    if bot_process and bot_process.poll() is None:
        return {"msg": "Automation already running"}
    if not state["target_pokemon"]:
        return {"error": "No target selected"}

    # Save current state so the bot script can read it
    save_state()

    bot_script = BASE_DIR / "rng_bot.py"
    if not bot_script.exists():
        return {"error": "rng_bot.py not found"}

    python = str(VENV_PYTHON) if VENV_PYTHON.exists() else "python3"
    bot_process = subprocess.Popen(
        [python, str(bot_script)],
        cwd=str(BASE_DIR),
    )
    return {"msg": f"Automation started (PID {bot_process.pid})"}


def api_stop_automation() -> dict:
    """Stop the running automation bot."""
    global bot_process
    if bot_process and bot_process.poll() is None:
        bot_process.send_signal(signal.SIGINT)
        try:
            bot_process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            bot_process.kill()
        bot_process = None
        return {"msg": "Automation stopped"}
    bot_process = None
    return {"msg": "Automation not running"}


def api_bot_status() -> dict:
    """Get the automation bot's current status."""
    status_file = BASE_DIR / "rng_bot_status.json"
    bot_running = bot_process is not None and bot_process.poll() is None
    status = {"running": bot_running}

    if status_file.exists():
        try:
            with open(status_file, "r") as f:
                status.update(json.load(f))
        except (json.JSONDecodeError, OSError):
            pass

    return status


def api_bot_log(data: dict) -> dict:
    """Get recent lines from the bot log file."""
    log_file = BASE_DIR / "rng_log.txt"
    lines_wanted = int(data.get("lines", 50))

    if not log_file.exists():
        return {"log": ""}

    try:
        with open(log_file, "r") as f:
            all_lines = f.readlines()
        recent = all_lines[-lines_wanted:]
        return {"log": "".join(recent)}
    except OSError:
        return {"log": ""}


def api_calibrate(data: dict) -> dict:
    """Find what advance was actually hit and calculate timer adjustment."""
    if not state["selected_seed"] or not state["target_pokemon"]:
        return {"error": "No seed/target selected"}

    seed_entry = seed_data.get_seed_by_hex(seeds_cache, state["selected_seed"])
    if not seed_entry:
        return {"error": "Seed not found"}

    target = state["target_pokemon"]
    pokemon_name = data.get("pokemon", target.get("pokemon", state["selected_pokemon"]))
    target_advance = target.get("advance", 0)

    matches = calibration.find_actual_advance(
        seed_entry["initial_seed"],
        state["tid"], state["sid"],
        pokemon_name,
        target_advance,
        observed_nature=data.get("nature"),
        observed_stats=data.get("stats"),
        observed_gender=data.get("gender"),
        search_range=int(data.get("search_range", 500)),
    )

    return {
        "matches": matches[:20],  # top 20
        "target_advance": target_advance,
        "pokemon": pokemon_name,
    }


def api_reverse_ivs(data: dict) -> dict:
    """Reverse-calculate IVs from observed stats."""
    pokemon_name = data.get("pokemon", state["selected_pokemon"])
    nature_name = data.get("nature", "Hardy")
    observed_stats = data.get("stats", {})
    level = int(data.get("level", 5))

    result = calibration.reverse_calc_from_stats(
        pokemon_name, observed_stats, nature_name, level,
    )
    return result


def api_auto_detect_tid() -> dict:
    """Auto-detect TID from trainer card and compute SID."""
    result = tid_sid.auto_detect_tid_sid()

    # If successful, update state
    if result["status"] in ("success", "success_multiple") and result["tid"] is not None:
        state["tid"] = result["tid"]
        state["sid"] = result["sid"]
        state["tid_set"] = True
        if result["sid_candidates"]:
            state["sid_candidates"] = result["sid_candidates"]
        save_state()
        start_shiny_count_bg()

    return result


def api_compute_sid(data: dict) -> dict:
    """Compute SID candidates from a manually-entered TID."""
    tid = int(data.get("tid", 0)) & 0xFFFF
    candidates = tid_sid.find_sids_for_tid(tid)

    if not candidates:
        return {"error": "No SID candidates found", "tid": tid, "candidates": []}

    # Auto-set TID and best SID
    state["tid"] = tid
    state["sid"] = candidates[0]["sid"]
    state["tid_set"] = True
    state["sid_candidates"] = candidates
    save_state()
    start_shiny_count_bg()

    return {
        "tid": tid,
        "sid": candidates[0]["sid"],
        "candidates": candidates,
        "msg": f"TID={tid}, found {len(candidates)} SID candidate(s). Using SID={candidates[0]['sid']}.",
    }


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    load_state()
    init_seeds()

    server = http.server.HTTPServer(("0.0.0.0", PORT), Handler)
    server.allow_reuse_address = True
    print(f"RNG Shiny Hunter running at http://localhost:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        if bot_process and bot_process.poll() is None:
            bot_process.send_signal(signal.SIGINT)
            bot_process.wait(timeout=10)
        server.server_close()
        print("\nShutdown.")
