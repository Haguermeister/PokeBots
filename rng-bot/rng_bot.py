#!/usr/bin/env python3
"""RNG Manipulation Bot — full automated loop.

Based on Blissey's FRLG Switch shiny starter tutorial.

3-Phase Timer Model (triple frame-perfect):
  Phase 1 (Seed):     MS timer — watch entire intro, HOLD A on title screen
  Phase 2 (Continue): 1x speed — wait on Continue/New Game screen, press A
  Phase 3 (Overworld): 2x speed — mash to "energetic" screen, press A on timer

Boot sequence:
  Close game → A (launch) → A (profile) → HOME (before GBA screen)
  Wait on HOME → resume + start timer → watch full intro

Usage:
  python3 rng_bot.py           # run full automation loop
  python3 rng_bot.py --once    # single attempt (for testing)
  python3 rng_bot.py --dry-run # print timing, don't press buttons
"""

from __future__ import annotations

import json
import sys
import time
import signal
from pathlib import Path

import pico
import rng_engine
import pokemon_data
import seed_data
import calibration
import screen_reader
import cv2

BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "rng_state.json"
LOG_FILE = BASE_DIR / "rng_log.txt"
STATUS_FILE = BASE_DIR / "rng_bot_status.json"

# NX frame rate
FRAME_RATE = 16777216 / 280896  # ≈ 59.7275 fps

# Ten Lines overworld frames setting (produces 1000 RNG advances at 2x speed)
TEN_LINES_OVERWORLD_FRAMES = 500

# EonTimer Phase 3 frame count (accounts for screen transitions/delays)
# Per Papa Jefe: 574 frames → actual 1000 overworld RNG advances on
# cutscene-less Static encounters/Gifts
EONTIMER_OVERWORLD_FRAMES = 574

# Overworld RNG advances = TEN_LINES_OVERWORLD_FRAMES * 2 = 1000
OVERWORLD_ADVANCES = TEN_LINES_OVERWORLD_FRAMES * 2

# How many attempts before giving up
MAX_ATTEMPTS = 100

# Stop flag for graceful shutdown
stop_requested = False


def _handle_sigint(sig, frame):
    global stop_requested
    stop_requested = True
    log("Interrupt received, stopping after current step...")


signal.signal(signal.SIGINT, _handle_sigint)


# ── Logging ──────────────────────────────────────────────────────────────────

def log(msg: str):
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


# ── State Management ────────────────────────────────────────────────────────

def load_state() -> dict:
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(st: dict):
    tmp = STATE_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=2)
    tmp.replace(STATE_FILE)


def write_status(status: dict):
    """Write bot status for the web UI to read."""
    tmp = STATUS_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(status, f, indent=2)
    tmp.replace(STATUS_FILE)


# ── Timing ───────────────────────────────────────────────────────────────────

def precise_sleep(seconds: float):
    """High-precision sleep that can be interrupted by Ctrl-C."""
    if seconds <= 0:
        return
    deadline = time.perf_counter() + seconds
    # Sleep in 0.5s chunks so Ctrl-C can interrupt
    while True:
        remaining = deadline - time.perf_counter()
        if remaining <= 0 or stop_requested:
            return
        if remaining > 0.5:
            time.sleep(0.5)
        elif remaining > 0.005:
            time.sleep(remaining - 0.005)
        else:
            # Busy-wait for final milliseconds
            while time.perf_counter() < deadline:
                pass
            return


def send_press(button: str, hold_ms: int = 120, delay_after: float = 0.0) -> bool:
    """Send a button press with one retry. Returns True on success."""
    result = pico.send_cmd(f"press {button} {hold_ms}")
    if not result.startswith("OK"):
        time.sleep(0.5)
        result = pico.send_cmd(f"press {button} {hold_ms}")
    if not result.startswith("OK"):
        log(f"  Button failed: {button} -> {result}")
        return False
    if delay_after > 0:
        time.sleep(delay_after)
    return True


def send_dpad(direction: str, hold_ms: int = 120, delay_after: float = 0.0) -> bool:
    """Send a d-pad press with one retry. Returns True on success."""
    result = pico.send_cmd(f"dpad {direction} {hold_ms}")
    if not result.startswith("OK"):
        time.sleep(0.5)
        result = pico.send_cmd(f"dpad {direction} {hold_ms}")
    if not result.startswith("OK"):
        log(f"  D-pad failed: {direction} -> {result}")
        return False
    if delay_after > 0:
        time.sleep(delay_after)
    return True


# ── Timer Calculation ────────────────────────────────────────────────────────

def calculate_phase1_ms(seed_frame: int, timer_offset_ms: float = 0) -> float:
    """Phase 1: Time from game resume to A press on Charizard title screen.

    This is the seed timing — derived from which VBlank frame our target
    seed appears at in the community seed data.
    """
    return (seed_frame / FRAME_RATE) * 1000 + timer_offset_ms


def calculate_phase2_ms(
    target_advance: int,
    cal_offset_ms: float = 0,
) -> float:
    """Phase 2: Continue screen wait time.

    On the Continue/New Game screen, RNG advances at 1x per frame.
    Continue screen advances = target_advance - OVERWORLD_ADVANCES (1000).
    No English offset here — that's only for TID/SID calculation.
    """
    continue_screen_advances = target_advance - OVERWORLD_ADVANCES
    return (continue_screen_advances / FRAME_RATE) * 1000 + cal_offset_ms


def calculate_phase3_ms() -> float:
    """Phase 3: Overworld wait time.

    EonTimer uses 574 frames (not 500) to account for screen transitions
    and delays between pressing A and actual RNG consumption.
    574 frames ≈ 9613ms.
    """
    return (EONTIMER_OVERWORLD_FRAMES / FRAME_RATE) * 1000


# ── Game Sequences ───────────────────────────────────────────────────────────

def close_game():
    """Close the game and get to Switch HOME screen.

    Uses screen detection to determine current state and act accordingly.
    Falls back to brute-force method if capture card isn't available.
    """
    log("Closing game...")

    reader = screen_reader.ScreenReader()
    if reader.open():
        frame = reader.grab_frame()
        state = reader.detect_screen_state(frame)
        log(f"  Current screen state: {state}")

        if state == "game":
            # Game is visible — press HOME to go to HOME menu
            send_press("HOME", 120)
            time.sleep(1.0)
            # Verify we're on HOME
            if reader.wait_for_home(timeout=3.0):
                log("  On HOME menu")
            else:
                log("  HOME not confirmed, pressing HOME again...")
                send_press("HOME", 120)
                time.sleep(1.0)
        elif state == "home_menu":
            log("  Already on HOME menu")
        else:
            # Unknown state — brute force
            log(f"  Unknown state '{state}', brute-forcing to HOME...")
            for i in range(3):
                send_press("HOME", 120)
                time.sleep(0.8)
                send_press("B", 120)
                time.sleep(0.5)

        reader.close()
    else:
        # No capture card — brute force approach
        log("  No capture card, brute-forcing to HOME...")
        for i in range(3):
            send_press("HOME", 120)
            time.sleep(0.8)
            send_press("B", 120)
            time.sleep(0.5)

    # Now close the game from HOME screen
    send_press("X", 120)           # "Close Software?" dialog
    time.sleep(1.0)
    send_press("A", 120)           # Confirm close
    time.sleep(3.0)                # Wait for game to fully close
    log("  Game closed, at home menu")


def boot_game():
    """Launch game with HOME-button trick for consistent seeds.

    A (launch) → wait for loading to start → A (profile) → HOME before GBA screen.
    Uses screen detection to wait for the dark loading screen,
    then presses HOME immediately to suspend before GBA BIOS appears.
    """
    log("Booting game with HOME trick...")
    send_press("A", 120)           # Launch game
    time.sleep(2.0)                # Wait for launch to register

    # Press A for profile select, then watch for dark screen (game loading).
    # HOME must be pressed DURING the black loading screen, BEFORE the
    # GBA BIOS/logo appears. The window is tight, so we press HOME
    # the instant we detect darkness.
    pico.send_cmd("press A 120")
    log("  Profile A sent, watching for dark screen...")

    reader = screen_reader.ScreenReader()
    home_sent = False
    if reader.open():
        start = time.perf_counter()

        # Wait 200ms for A press to register, then poll aggressively
        time.sleep(0.2)
        saw_light = False
        consecutive_dark = 0

        while time.perf_counter() - start < 4.0:
            frame = reader.grab_frame()
            if frame is not None:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                mean_br = float(gray.mean())

                if mean_br > 20:
                    saw_light = True
                    consecutive_dark = 0
                elif mean_br < 15:
                    consecutive_dark += 1
                    needed = 1 if saw_light else 3
                    if consecutive_dark >= needed:
                        # Press HOME IMMEDIATELY — don't log first
                        pico.send_cmd("press HOME 120")
                        home_sent = True
                        elapsed = (time.perf_counter() - start) * 1000
                        log(f"  Dark at {elapsed:.0f}ms → HOME sent (saw_light={saw_light})")
                        break
            time.sleep(0.02)  # 20ms polling for faster reaction

        if not home_sent:
            elapsed = (time.perf_counter() - start) * 1000
            log(f"  No dark screen after {elapsed:.0f}ms — pressing HOME anyway")
        reader.close()

    if not home_sent:
        # Fallback: fixed timing or no capture device
        time.sleep(1.0)
        pico.send_cmd("press HOME 120")
        log("  HOME pressed (fixed timing fallback)")

    log("  Waiting for HOME screen to stabilize...")
    time.sleep(5.0)                # Stabilization on HOME screen


def run_three_phase(phase1_ms: float, phase2_ms: float, phase3_ms: float,
                     encounter_type: str = "game_corner"):
    """Execute the 3-phase timed sequence.

    Phase 1 (Seed):     Resume game, watch ENTIRE intro (no button presses!),
                         when timer fires HOLD A on Charizard title screen.
    Phase 2 (Continue):  On Continue/New Game screen (1x RNG), wait for timer,
                         then press A to select Continue.
    Phase 3 (Overworld): Mash through dialogue to reach the critical A-press
                         screen, wait for timer, press A (Method 1 generation!).

    For game_corner/static: critical A = confirm YES to receive Pokemon
    For starters: critical A = "This Pokemon is quite energetic" screen
    """
    # ── Resume game — timer starts NOW ──
    timer_origin = time.perf_counter()
    pico.send_cmd("press HOME 120")
    log(f"  Game resumed, 3-phase timer started")

    # ── Phase 1: Watch intro (DO NOT PRESS ANYTHING!) ──
    p1_target = timer_origin + phase1_ms / 1000
    remaining = p1_target - time.perf_counter()
    if remaining > 0:
        log(f"  Phase 1: Watching intro ({remaining:.1f}s)...")
        precise_sleep(remaining)
    if stop_requested:
        return

    # Phase 1 beep → HOLD A through title screen
    p2_start = time.perf_counter()
    log("  HOLD A on title screen")
    pico.send_cmd("press A 1800")  # blocks ~1.8s while Pico holds A
    time.sleep(0.6)                # settle on Continue/New Game

    # ── Phase 2: Wait on Continue screen (1x RNG speed) ──
    p2_target = p2_start + phase2_ms / 1000
    remaining = p2_target - time.perf_counter()
    if remaining > 0:
        log(f"  Phase 2: Continue screen ({remaining:.1f}s)...")
        precise_sleep(remaining)
    else:
        log(f"  Phase 2: Continue screen (title hold consumed all time)")
    if stop_requested:
        return

    # Phase 2 beep → press A on Continue
    log("  A → Continue")
    p3_start = time.perf_counter()
    pico.send_cmd("press A 120")

    # ── Phase 3: Overworld (2x RNG speed) ──
    time.sleep(1.5)  # save loading

    if encounter_type == "starter":
        _phase3_mash_starter()
    elif encounter_type == "game_corner":
        _phase3_mash_game_corner()
    else:
        _phase3_mash_static()

    p3_target = p3_start + phase3_ms / 1000
    remaining = p3_target - time.perf_counter()
    if remaining > 0:
        log(f"  Waiting {remaining:.1f}s for Phase 3 timer...")
        precise_sleep(remaining)
    else:
        log(f"  WARNING: mashing took {-remaining:.1f}s longer than Phase 3 budget!")
    if stop_requested:
        return

    # Phase 3 beep → THE critical A press (Method 1 generation!)
    log("  A → Method 1 generation!")
    pico.send_cmd("press A 120")


def _phase3_mash_starter():
    """Phase 3 mashing for starters in Oak's Lab.

    After Continue, the save loads and you're near the starter ball.
    Press A to interact → Oak dialogue → "So you want POKEMON?" → YES →
    receive pokemon → more dialogue → "This Pokemon is quite energetic" → STOP.
    We mash A to get through all dialogue, then switch to B to safely
    decline the nickname if we overshoot. Stop before the critical screen.
    """
    log("  Phase 3: Mashing through starter dialogue...")
    # A presses to interact with ball and get through Oak's text + YES prompt
    for i in range(10):
        if stop_requested:
            return
        pico.send_cmd("press A 120")
        time.sleep(0.2)
    # B for safety — declines nickname if we overshoot past "energetic"
    for i in range(5):
        if stop_requested:
            return
        pico.send_cmd("press B 120")
        time.sleep(0.2)


def _phase3_mash_game_corner():
    """Phase 3 mashing for Game Corner prizes.

    After Continue, you're standing in front of the Pokemon/counter.
    Press A to interact → exchange coins dialogue → YES prompt → STOP.
    Game corner has less dialogue than starters.
    """
    log("  Phase 3: Mashing through game corner dialogue...")
    # A presses to interact and get through exchange dialogue
    for i in range(5):
        if stop_requested:
            return
        pico.send_cmd("press A 120")
        time.sleep(0.25)
    # B for safety
    for i in range(3):
        if stop_requested:
            return
        pico.send_cmd("press B 120")
        time.sleep(0.2)


def _phase3_mash_static():
    """Phase 3 mashing for static/gift Pokemon (Eevee, Lapras, etc.)."""
    log("  Phase 3: Mashing through static encounter dialogue...")
    for i in range(7):
        if stop_requested:
            return
        pico.send_cmd("press A 120")
        time.sleep(0.2)
    for i in range(4):
        if stop_requested:
            return
        pico.send_cmd("press B 120")
        time.sleep(0.2)


def post_selection():
    """Handle post-selection: remaining dialogue, nickname decline, rival.

    After the critical A on 'energetic':
    - More dialogue text boxes
    - 'Do you want to nickname?' → B to decline (cursor defaults to NO)
    - Rival picks pokemon, more dialogue
    - Eventually back in overworld
    """
    log("  Post-selection: dialogue + nickname + rival...")
    time.sleep(0.5)

    # First: a few A presses to advance any remaining pre-nickname dialogue
    for _ in range(5):
        if stop_requested:
            return
        send_press("A", 120, 0.3)

    # Now alternate B presses to decline nickname + skip rival dialogue
    # B declines nickname (NO is default) and also dismisses dialogue
    for _ in range(40):
        if stop_requested:
            return
        send_press("B", 120, 0.2)

    # Wait for rival to finish picking + any lingering dialogue
    time.sleep(3.0)
    log("  Post-selection complete")


def navigate_to_summary(has_pokedex: bool = False):
    """Open menu and navigate to Pokemon summary screen.

    Pre-Pokédex menu: POKéMON, BAG, [name], SAVE, OPTION, EXIT
    Post-Pokédex menu: POKéDEX, POKéMON, BAG, [name], SAVE, OPTION, EXIT

    POKéMON is the first item pre-dex, second item post-dex.
    """
    log("  Opening summary...")
    send_press("X", 120)
    time.sleep(1.5)                # Wait for menu to fully open
    if has_pokedex:
        send_dpad("DOWN", 120, 0.4)  # Skip POKéDEX
    send_press("A", 120)           # Select POKéMON
    time.sleep(1.0)                # Wait for party screen
    send_press("A", 120)           # Select the Pokemon
    time.sleep(1.0)                # Wait for submenu to open
    send_press("A", 120)           # Select SUMMARY (first submenu item)
    time.sleep(1.0)                # Wait for summary to load
    log("  On summary page")


def navigate_to_stats_page():
    """Press Right to get from info page to stats page.

    Tries multiple times and verifies navigation succeeded.
    In FRLG summary: RIGHT cycles INFO → SKILLS (stats) → MOVES.
    """
    for attempt in range(3):
        ok = send_dpad("RIGHT", 200, 0.8)
        if not ok:
            log(f"  D-pad RIGHT failed (attempt {attempt + 1}/3), retrying...")
            time.sleep(0.3)
            continue
        log(f"  RIGHT pressed (attempt {attempt + 1})")
        break
    else:
        log("  WARNING: All D-pad RIGHT attempts failed!")
    time.sleep(0.3)
    log("  On stats page")


def save_game_from_summary():
    """Save the game — starting from summary screen."""
    log("Saving game!")
    # Back out of summary
    send_press("B", 120, 0.26)
    send_press("B", 120, 0.26)
    send_press("B", 120, 0.38)

    # D-pad down to Save option
    send_dpad("DOWN", 120, 0.22)
    send_dpad("DOWN", 120, 0.22)
    send_dpad("DOWN", 120, 0.26)
    send_press("A", 120, 0.65)
    send_press("A", 120, 1.0)
    log("  Game saved!")


# ── Calibration Logic ────────────────────────────────────────────────────────

def identify_hit_advance(
    st: dict,
    observed_nature: str | None,
    was_shiny: bool,
) -> dict | None:
    """Identify what advance was actually hit based on observed nature."""
    target = st.get("target_pokemon", {})
    target_advance = target.get("advance", 0)

    seeds = seed_data.load_or_download_seeds()
    seed_entry = seed_data.get_seed_by_hex(seeds, st.get("selected_seed", ""))
    if not seed_entry:
        return None

    tid, sid = st["tid"], st["sid"]
    pokemon_name = target.get("pokemon", st.get("selected_pokemon", "Bulbasaur"))

    matches = calibration.find_actual_advance(
        seed_entry["initial_seed"], tid, sid, pokemon_name, target_advance,
        observed_nature=observed_nature,
        search_range=500,
    )

    if matches:
        return matches[0]
    return None


def apply_calibration_offset(st: dict, actual_advance: int) -> float:
    """Apply timer offset based on actual advance hit. Returns ms adjustment."""
    target = st.get("target_pokemon", {})
    target_advance = target.get("advance", 0)
    offset = actual_advance - target_advance
    offset_ms = calibration.advance_offset_to_ms(offset)

    old_cal = st.get("calibration_offset_ms", 0)
    new_cal = old_cal - offset_ms
    st["calibration_offset_ms"] = round(new_cal, 1)
    save_state(st)

    return -offset_ms


# ── SID Cycling ─────────────────────────────────────────────────────────────

def find_all_sid_candidates(tid: int, custom_rival_name: bool = True) -> list[dict]:
    """Find all possible SID values using Lincoln's tool method.

    Uses TID hex as LCRNG initial seed, searches around advance 3498
    ((1500 + 249) * 2) for potential SIDs. Custom rival name = even
    advances only, preset name = odd advances only.
    """
    import tid_sid
    return tid_sid.find_sids_for_tid(tid, custom_rival_name=custom_rival_name)


def find_best_target_for_sid(
    tid: int,
    sid: int,
    pokemon_name: str,
    seeds: list[dict],
    min_advance: int = 1000,
    max_advance: int = 5000,
    min_continue_advances: int = 400,
) -> dict | None:
    """Find the best shiny target for a given SID across all seeds.

    Per Blissey's tutorial:
    - Continue screen advances should be >= ~400 (enough time to navigate)
    - Pick an early, comfortable target
    - continue_advances = target_advance - 1000 (overworld uses 1000 RNG advances)
    """
    best = None

    for entry in seeds:
        initial_seed = entry["initial_seed"]
        shinies = rng_engine.search_shinies_in_range(
            initial_seed, tid, sid, min_advance, max_advance,
        )
        for s in shinies:
            continue_advances = s["advance"] - OVERWORLD_ADVANCES
            if continue_advances < min_continue_advances:
                continue  # too tight for Continue screen timing

            if best is None or s["advance"] < best["advance"]:
                best = {
                    "pokemon": pokemon_name,
                    "advance": s["advance"],
                    "seed_hex": entry.get("seed_hex", f"{initial_seed:04X}"),
                    "seed_frame": entry["seed_frame"],
                    "initial_seed": initial_seed,
                    "nature": s["nature"],
                    "pid": f"{s['pid']:08X}",
                    "ivs": s["ivs"],
                    "continue_advances": continue_advances,
                }
    return best


def cycle_to_next_sid(st: dict) -> bool:
    """Move to the next SID candidate and find a new target.

    Returns True if a new SID/target was found, False if exhausted.
    """
    sid_candidates = st.get("sid_candidates", [])
    current_sid_index = st.get("current_sid_index", 0)
    next_index = current_sid_index + 1

    if next_index >= len(sid_candidates):
        log("All SID candidates exhausted!")
        return False

    new_sid = sid_candidates[next_index]["sid"]
    tid = st["tid"]
    pokemon_name = st.get("target_pokemon", {}).get("pokemon", "Charmander")

    log(f"Cycling to SID candidate #{next_index + 1}: SID={new_sid}")

    seeds = seed_data.load_or_download_seeds()
    target = find_best_target_for_sid(tid, new_sid, pokemon_name, seeds)

    if not target:
        log(f"  No shiny {pokemon_name} found for SID={new_sid}, skipping...")
        st["current_sid_index"] = next_index
        save_state(st)
        return cycle_to_next_sid(st)

    log(f"  New target: {target['nature']} {pokemon_name}")
    log(f"  Seed: 0x{target['seed_hex']} | Advance: {target['advance']}")
    log(f"  Continue advances: {target['continue_advances']}")

    st["sid"] = new_sid
    st["current_sid_index"] = next_index
    st["selected_seed"] = target["seed_hex"]
    st["selected_seed_frame"] = target["seed_frame"]
    st["selected_advance"] = target["advance"]
    st["target_pokemon"] = target
    st["calibration_offset_ms"] = 0.0
    st["timer_offset_ms"] = 0.0
    st["sid_confirmed"] = False
    st["advance_confirmed"] = False
    save_state(st)
    return True


# ── Main Automation Loop ────────────────────────────────────────────────────

def run_single_attempt(st: dict, reader: screen_reader.ScreenReader, dry_run: bool = False) -> dict:
    """Execute one full RNG manipulation attempt.

    Returns result dict with action: "save" | "calibrate" | "retry" | "stopped"
    """
    target = st.get("target_pokemon", {})
    target_advance = target.get("advance", 0)
    target_nature = target.get("nature", "")
    target_pokemon = target.get("pokemon", st.get("selected_pokemon", "Scyther"))
    seed_frame = st.get("selected_seed_frame", 0)
    timer_offset = st.get("timer_offset_ms", 0)
    cal_offset = st.get("calibration_offset_ms", 0)
    encounter_type = st.get("encounter_type", "game_corner")
    has_pokedex = st.get("has_pokedex", True)

    phase1_ms = calculate_phase1_ms(seed_frame, timer_offset)
    phase2_ms = calculate_phase2_ms(target_advance, cal_offset)
    phase3_ms = calculate_phase3_ms()

    continue_advances = target_advance - OVERWORLD_ADVANCES

    attempt_num = st.get("attempts", 0) + 1
    log(f"{'='*60}")
    log(f"ATTEMPT #{attempt_num}")
    log(f"  Target: {target_pokemon} @ advance {target_advance} ({target_nature})")
    log(f"  Seed: 0x{st.get('selected_seed', '?')} frame={seed_frame}")
    log(f"  Encounter type: {encounter_type}")
    log(f"  Phase 1 (seed):      {phase1_ms:.1f}ms ({phase1_ms/1000:.1f}s)")
    log(f"  Phase 2 (continue):  {phase2_ms:.1f}ms ({phase2_ms/1000:.1f}s) [{continue_advances} advances @ 1x]")
    log(f"  Phase 3 (overworld): {phase3_ms:.1f}ms ({phase3_ms/1000:.1f}s) [574 EonTimer frames]")
    log(f"  Calibration offset: {cal_offset:.1f}ms")

    if dry_run:
        log("  [DRY RUN — no buttons pressed]")
        return {"shiny": False, "nature": None, "action": "retry"}

    write_status({"state": "running", "attempt": attempt_num,
                  "phase": "closing_game", "target": target_pokemon,
                  "target_advance": target_advance})

    # Step 1: Close game and get to home menu
    close_game()
    if stop_requested:
        return {"action": "stopped"}
    time.sleep(1.0)

    # Step 2: Boot game with HOME trick
    write_status({"state": "running", "attempt": attempt_num, "phase": "boot"})
    boot_game()
    if stop_requested:
        return {"action": "stopped"}

    # Step 3: Run the 3-phase timed sequence
    write_status({"state": "running", "attempt": attempt_num, "phase": "three_phase_timer"})
    run_three_phase(phase1_ms, phase2_ms, phase3_ms, encounter_type)
    if stop_requested:
        return {"action": "stopped"}

    # Step 4: Post-selection (nickname decline, rival dialogue)
    write_status({"state": "running", "attempt": attempt_num, "phase": "post_selection"})
    post_selection()
    if stop_requested:
        return {"action": "stopped"}

    # Step 5: Navigate to summary
    write_status({"state": "running", "attempt": attempt_num, "phase": "checking"})

    # First verify the game is actually visible (not stuck on nickname/other screen)
    frame = reader.grab_frame()
    if frame is not None:
        state = reader.detect_screen_state(frame)
        log(f"  Screen state before summary: {state}")
        reader.save_debug_frame(frame, f"pre_summary_{attempt_num}")
        if state != "game":
            log("  WARNING: Game not visible — may be stuck. Pressing B to recover...")
            for _ in range(10):
                send_press("B", 120, 0.3)
            time.sleep(1.0)

    navigate_to_summary(has_pokedex)
    time.sleep(1.0)

    # Verify we landed on the summary page
    on_summary = reader.is_on_summary()
    if not on_summary:
        log("  Summary page not detected — retrying navigation...")
        # Back out and try again
        for _ in range(5):
            send_press("B", 120, 0.3)
        time.sleep(0.5)
        navigate_to_summary(has_pokedex)
        time.sleep(1.0)
        on_summary = reader.is_on_summary()
        if not on_summary:
            log("  WARNING: Still can't detect summary page")

    # Step 7: Check for shiny
    log("Checking for shiny...")
    is_shiny = reader.check_shiny(seconds=3.0)
    log(f"  Shiny: {'YES!' if is_shiny else 'No'}")

    # Step 8: Navigate to stats page and read nature
    log("Navigating to stats page...")
    navigate_to_stats_page()
    time.sleep(1.0)

    # Save a debug frame of the stats page for analysis
    frame_before = reader.grab_frame()
    if frame_before is not None:
        reader.save_debug_frame(frame_before, f"stats_page_{attempt_num}")
        on_stats = reader.is_on_stats_page(frame_before)
        log(f"  Stats page detected: {on_stats}")

    log("Reading nature from stats page...")
    nature = reader.detect_nature_stable(num_reads=5)
    log(f"  Detected nature: {nature}")

    # Save a debug frame every attempt for review
    frame = reader.grab_frame()
    if frame is not None:
        reader.save_debug_frame(frame, f"attempt_{attempt_num}")

    # Step 9: Evaluate
    result = {
        "shiny": is_shiny,
        "nature": nature,
        "advance_hit": None,
        "offset": None,
        "action": "retry",
    }

    if is_shiny and nature == target_nature:
        log("TARGET HIT! Saving game...")
        result["action"] = "save"
        save_game_from_summary()
        return result

    if is_shiny and nature is None:
        # Shiny but couldn't read nature — assume it's our target
        log("SHINY detected! Nature unreadable — saving as precaution")
        result["action"] = "save"
        save_game_from_summary()
        return result

    if is_shiny and nature == "neutral":
        # Shiny but nature shows "neutral" — probably failed to navigate
        # to stats page. Try again with more aggressive navigation.
        log("  SHINY but nature reads 'neutral' — retrying stats page navigation...")
        # Press B to exit summary, then re-navigate
        send_press("B", 120, 0.3)
        send_press("B", 120, 0.3)
        send_press("B", 120, 0.5)
        navigate_to_summary(has_pokedex)
        time.sleep(1.0)
        # Navigate to stats page more aggressively
        navigate_to_stats_page()
        time.sleep(1.5)
        nature2 = reader.detect_nature_stable(num_reads=8)
        log(f"  Second nature read: {nature2}")
        frame_retry = reader.grab_frame()
        if frame_retry is not None:
            reader.save_debug_frame(frame_retry, f"nature_retry_{attempt_num}")
        if nature2 and nature2 != "neutral":
            nature = nature2
            result["nature"] = nature
        else:
            # Still neutral — save the shiny anyway as precaution
            log("  Still reading neutral — saving shiny as precaution")
            result["action"] = "save"
            save_game_from_summary()
            return result

    if is_shiny:
        log(f"  Shiny but wrong nature: got {nature}, want {target_nature}")

    # Try to calibrate by identifying what advance we hit
    if nature and nature != "neutral":
        match = identify_hit_advance(st, nature, is_shiny)
        if match:
            result["advance_hit"] = match["advance"]
            result["offset"] = match["offset"]
            log(f"  Matched advance: {match['advance']} (offset {match['offset']:+d})")

            if match["offset"] == 0 and not is_shiny:
                # We hit the EXACT target advance but it wasn't shiny
                # → This SID is WRONG. Cycle to next candidate.
                log("  HIT EXACT ADVANCE but NOT SHINY → SID is wrong!")
                result["action"] = "sid_wrong"
            else:
                adj_ms = apply_calibration_offset(st, match["advance"])
                log(f"  Timer adjusted by {adj_ms:+.1f}ms")
                result["action"] = "calibrate"
        else:
            log("  Could not match nature to any nearby advance")
    elif nature == "neutral":
        log("  Neutral nature detected — multiple possibilities, retrying without adjustment")
    else:
        log("  Nature unreadable — retrying without adjustment")

    # Update state
    st["attempts"] = attempt_num
    st["last_result"] = {
        "attempt": attempt_num,
        "shiny": is_shiny,
        "nature": nature,
        "advance_hit": result["advance_hit"],
        "offset": result["offset"],
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    save_state(st)

    return result


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Single attempt only")
    parser.add_argument("--dry-run", action="store_true", help="Print timing without pressing buttons")
    args = parser.parse_args()

    global stop_requested

    log("")
    log("=" * 60)
    log("RNG MANIPULATION BOT STARTING")
    log("=" * 60)

    st = load_state()
    if not st.get("target_pokemon"):
        log("ERROR: No target selected. Use the web UI to pick a seed and shiny.")
        sys.exit(1)
    if not st.get("tid_set"):
        log("ERROR: TID/SID not set. Enter your Trainer IDs in the web UI.")
        sys.exit(1)
    if not st.get("selected_seed"):
        log("ERROR: No seed selected. Pick a seed in the web UI.")
        sys.exit(1)

    target = st["target_pokemon"]
    encounter_type = st.get("encounter_type", "game_corner")
    log(f"Target: {target.get('pokemon', '?')} @ advance {target.get('advance', '?')}")
    log(f"  Nature: {target.get('nature', '?')}  PID: {target.get('pid', '?')}")
    log(f"  IVs: {target.get('ivs', {})}")
    log(f"  Seed: 0x{st['selected_seed']} | TID: {st['tid']} | SID: {st['sid']}")
    log(f"  Encounter type: {encounter_type}")
    log(f"  Calibration: {st.get('calibration_offset_ms', 0):.1f}ms")
    log(f"  Continue advances: {target.get('advance', 0) - OVERWORLD_ADVANCES}")
    log(f"  Phase 3 EonTimer frames: {EONTIMER_OVERWORLD_FRAMES}")

    reader = screen_reader.ScreenReader()
    if not args.dry_run:
        if not reader.open():
            log("ERROR: Could not open capture device")
            sys.exit(1)
        log("Screen reader initialized")

    write_status({"state": "starting", "target": target.get("pokemon", "?")})

    # Initialize SID candidates if SID not already confirmed
    sid_confirmed = st.get("sid_confirmed", False)
    if sid_confirmed:
        log(f"SID confirmed: {st['sid']} — skipping SID candidate search")
    elif not st.get("sid_candidates") or len(st["sid_candidates"]) <= 1:
        custom_name = st.get("custom_rival_name", True)
        log(f"Finding SID candidates (Lincoln's method, {'custom' if custom_name else 'preset'} rival name)...")
        candidates = find_all_sid_candidates(st["tid"], custom_rival_name=custom_name)
        st["sid_candidates"] = candidates
        st["current_sid_index"] = 0
        save_state(st)
        log(f"  Found {len(candidates)} SID candidates")
        for i, c in enumerate(candidates[:10]):
            marker = " ← current" if c["sid"] == st["sid"] else ""
            log(f"    #{i+1}: advance {c['advance']}, SID={c['sid']}{marker}")

    attempt = 0
    success = False

    while not stop_requested and attempt < MAX_ATTEMPTS:
        attempt += 1

        result = run_single_attempt(st, reader, dry_run=args.dry_run)

        if result["action"] == "stopped":
            log("Bot stopped by user")
            break

        if result["action"] == "save":
            log("")
            log("=" * 60)
            log("SUCCESS! Target shiny caught and saved!")
            log(f"  Took {attempt} attempt(s)")
            log(f"  Confirmed SID: {st['sid']}")
            log("=" * 60)
            st["sid_confirmed"] = True
            save_state(st)
            write_status({"state": "success", "attempt": attempt,
                          "nature": result.get("nature")})
            success = True
            break

        if result["action"] == "sid_wrong":
            if sid_confirmed:
                # SID is known-good — this means we hit the exact advance but
                # weren't shiny due to a calibration/seed mismatch. Keep trying.
                log("  Hit exact advance but not shiny (SID confirmed) — recalibrating...")
            else:
                log("")
                log(f"SID {st['sid']} ELIMINATED — cycling to next candidate")
                if cycle_to_next_sid(st):
                    st = load_state()
                    target = st["target_pokemon"]
                    log(f"New target: {target['nature']} {target['pokemon']} @ advance {target['advance']}")
                    log(f"New SID: {st['sid']} | Seed: 0x{st['selected_seed']}")
                else:
                    log("All SID candidates exhausted! Cannot find correct SID.")
                    break

        if result["action"] == "calibrate":
            log(f"  Calibration applied. Offset was {result.get('offset', '?')} advances")

        if args.once or args.dry_run:
            log("Single attempt mode — stopping")
            break

        # Reload state (calibration may have updated it)
        st = load_state()

        # Next attempt will close_game() + boot_game() at the start
        log("Starting next attempt...")
        time.sleep(2.0)

    if not success and not stop_requested and attempt >= MAX_ATTEMPTS:
        log(f"Max attempts ({MAX_ATTEMPTS}) reached without hitting target")

    reader.close()
    write_status({"state": "stopped", "attempts": attempt, "success": success})
    log("Bot shutdown")


if __name__ == "__main__":
    main()
