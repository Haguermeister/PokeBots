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

# Default overworld frames (from Blissey tutorial)
# RNG runs at 2x in overworld, so 600 frames = 1200 RNG advances
DEFAULT_OVERWORLD_FRAMES = 600

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
    overworld_frames: int = DEFAULT_OVERWORLD_FRAMES,
    cal_offset_ms: float = 0,
) -> float:
    """Phase 2: Continue screen wait time.

    On the Continue/New Game screen, RNG advances at 1x per frame.
    The English version has a 249-advance offset (from ten-lines) that
    accounts for RNG consumed during save loading / dialogue setup.
    continue_screen_advances = (target_advance + 249) - (overworld_frames × 2)
    """
    effective_advance = target_advance + seed_data.ENGLISH_ADVANCE_OFFSET
    continue_screen_advances = effective_advance - (overworld_frames * 2)
    return (continue_screen_advances / FRAME_RATE) * 1000 + cal_offset_ms


def calculate_phase3_ms(overworld_frames: int = DEFAULT_OVERWORLD_FRAMES) -> float:
    """Phase 3: Overworld wait time (frames at video rate).

    RNG advances at 2x per frame in overworld, but the timer counts
    real frames.  600 frames ≈ 10 seconds = 1200 RNG advances.
    """
    return (overworld_frames / FRAME_RATE) * 1000


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


def run_three_phase(phase1_ms: float, phase2_ms: float, phase3_ms: float):
    """Execute the 3-phase timed sequence.

    Phase 1 (Seed):     Resume game, watch ENTIRE intro (no button presses!),
                         when timer fires HOLD A on Charizard title screen.
    Phase 2 (Continue):  On Continue/New Game screen (1x RNG), wait for timer,
                         then press A to select Continue.
    Phase 3 (Overworld): Mash through dialogue to reach "energetic" screen,
                         wait for timer, press A (Method 1 generation!).
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
    # After Continue, save loads → overworld → interact with pokeball →
    # many dialogue boxes → "This Pokemon is quite energetic." screen.
    # Mash A to reach "energetic" but STOP before blowing through it.
    time.sleep(1.5)  # save loading

    log("  Phase 3: Mashing through dialogue to 'energetic' screen...")
    # Dialogue flow after Continue → save load → overworld → walk to ball →
    # A to interact → Oak text → "So you want CHARMANDER?" → YES (need A) →
    # receive pokemon → Oak describes → "energetic!" → STOP HERE.
    #
    # Need ~10 A presses to get past the YES/NO prompt for sure.
    # After that, use B — it advances text but selects NO on prompts,
    # so overshooting past "energetic" into nickname will decline safely.
    for i in range(10):
        if stop_requested:
            return
        pico.send_cmd("press A 120")
        time.sleep(0.2)
    # B for the rest — safe if we overshoot past energetic
    for i in range(8):
        if stop_requested:
            return
        pico.send_cmd("press B 120")
        time.sleep(0.2)

    p3_target = p3_start + phase3_ms / 1000
    remaining = p3_target - time.perf_counter()
    if remaining > 0:
        log(f"  Waiting {remaining:.1f}s on 'energetic' screen...")
        precise_sleep(remaining)
    else:
        log(f"  WARNING: mashing took {-remaining:.1f}s longer than Phase 3 budget!")
    if stop_requested:
        return

    # Phase 3 beep → THE critical A press on "energetic"
    log("  A on 'energetic' — Method 1 generation!")
    pico.send_cmd("press A 120")


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


def navigate_to_summary():
    """Open menu and navigate to Pokemon summary screen.

    Pre-Pokédex menu (no Pokédex yet): POKéMON, BAG, [name], SAVE, OPTION, EXIT
    POKéMON is the first item, so: X → A → A → A → summary.
    """
    log("  Opening summary...")
    send_press("X", 120)
    time.sleep(1.5)                # Wait for menu to fully open
    send_press("A", 120)           # Select POKéMON (first menu item)
    time.sleep(1.0)                # Wait for party screen
    send_press("A", 120)           # Select Charmander
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

def find_all_sid_candidates(tid: int, max_advance: int = 500000) -> list[dict]:
    """Find all possible SID values by searching the LCRNG from seed 0."""
    results = []
    seed = 0
    for adv in range(max_advance + 1):
        if rng_engine.high16(seed) == tid:
            sid = rng_engine.high16(rng_engine.advance(seed))
            results.append({"advance": adv, "tid": tid, "sid": sid})
        seed = rng_engine.advance(seed)
    results.sort(key=lambda r: r["advance"])
    return results


def find_best_target_for_sid(
    tid: int,
    sid: int,
    pokemon_name: str,
    seeds: list[dict],
    min_advance: int = 1000,
    max_advance: int = 10000,
    min_continue_frames: int = 1100,
) -> dict | None:
    """Find the best shiny target for a given SID across all seeds.

    Per Blissey's tutorial:
    - Continue screen frames should be >= ~1100 (enough time to navigate)
    - Pick the target with the most comfortable timing
    """
    best = None
    overworld_frames = DEFAULT_OVERWORLD_FRAMES

    for entry in seeds:
        initial_seed = entry["initial_seed"]
        shinies = rng_engine.search_shinies_in_range(
            initial_seed, tid, sid, min_advance, max_advance,
        )
        for s in shinies:
            continue_frames = s["advance"] - (overworld_frames * 2)
            if continue_frames < min_continue_frames:
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
                    "continue_frames": continue_frames,
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
    log(f"  Continue frames: {target['continue_frames']}")

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
    target_pokemon = target.get("pokemon", st.get("selected_pokemon", "Bulbasaur"))
    seed_frame = st.get("selected_seed_frame", 0)
    timer_offset = st.get("timer_offset_ms", 0)
    cal_offset = st.get("calibration_offset_ms", 0)
    overworld_frames = st.get("overworld_frames", DEFAULT_OVERWORLD_FRAMES)

    phase1_ms = calculate_phase1_ms(seed_frame, timer_offset)
    phase2_ms = calculate_phase2_ms(target_advance, overworld_frames, cal_offset)
    phase3_ms = calculate_phase3_ms(overworld_frames)

    continue_advances = target_advance + seed_data.ENGLISH_ADVANCE_OFFSET - (overworld_frames * 2)

    attempt_num = st.get("attempts", 0) + 1
    log(f"{'='*60}")
    log(f"ATTEMPT #{attempt_num}")
    log(f"  Target: {target_pokemon} @ advance {target_advance} ({target_nature})")
    log(f"  Seed: 0x{st.get('selected_seed', '?')} frame={seed_frame}")
    log(f"  Phase 1 (seed):      {phase1_ms:.1f}ms ({phase1_ms/1000:.1f}s)")
    log(f"  Phase 2 (continue):  {phase2_ms:.1f}ms ({phase2_ms/1000:.1f}s) [{continue_advances} advances @ 1x]")
    log(f"  Phase 3 (overworld): {phase3_ms:.1f}ms ({phase3_ms/1000:.1f}s) [{overworld_frames} frames @ 2x]")
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
    run_three_phase(phase1_ms, phase2_ms, phase3_ms)
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

    navigate_to_summary()
    time.sleep(1.0)

    # Verify we landed on the summary page
    on_summary = reader.is_on_summary()
    if not on_summary:
        log("  Summary page not detected — retrying navigation...")
        # Back out and try again
        for _ in range(5):
            send_press("B", 120, 0.3)
        time.sleep(0.5)
        navigate_to_summary()
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
        navigate_to_summary()
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
    log(f"Target: {target.get('pokemon', '?')} @ advance {target.get('advance', '?')}")
    log(f"  Nature: {target.get('nature', '?')}  PID: {target.get('pid_hex', '?')}")
    log(f"  IVs: {target.get('ivs', {})}")
    log(f"  Seed: 0x{st['selected_seed']} | TID: {st['tid']} | SID: {st['sid']}")
    log(f"  Calibration: {st.get('calibration_offset_ms', 0):.1f}ms")

    reader = screen_reader.ScreenReader()
    if not args.dry_run:
        if not reader.open():
            log("ERROR: Could not open capture device")
            sys.exit(1)
        log("Screen reader initialized")

    write_status({"state": "starting", "target": target.get("pokemon", "?")})

    # Initialize SID candidates if not present
    if not st.get("sid_candidates") or len(st["sid_candidates"]) <= 1:
        log("Finding all SID candidates...")
        candidates = find_all_sid_candidates(st["tid"])
        st["sid_candidates"] = candidates
        st["current_sid_index"] = 0
        save_state(st)
        log(f"  Found {len(candidates)} SID candidates")
        for i, c in enumerate(candidates):
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
