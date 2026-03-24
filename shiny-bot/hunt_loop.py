#!/usr/bin/env python3
import json
import sys
import time
import tty
import termios
import select
import threading
import subprocess
from pathlib import Path
import pico
import run_sequence

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import notify

BASE_DIR = Path(__file__).resolve().parent
STAR_SCRIPT = BASE_DIR / "check_border.py"
STATE_FILE = BASE_DIR / "hunt_state.json"
ENCOUNTER_FILE = BASE_DIR / "encounter_count.txt"
TIME_FILE = BASE_DIR / "encounter_time.txt"
PAUSE_FILE = BASE_DIR / "pause_requested.flag"

WATCH_SECONDS = 3
STATE_CHECK_SECONDS = 1.2
DEFAULT_TOTAL_RUNTIME_SECONDS = 22 * 60 * 60

stop_requested = False


# Return codes from check_border.py --state-check
STATE_SUMMARY_READY = 0
STATE_STARTER_NOT_CHOSEN = 10
STATE_STARTER_CHOSEN_NOT_SUMMARY = 11


def run_step_sequence(steps, label: str) -> bool:
    global stop_requested
    print(f"Running recovery sequence: {label}")
    for command, delay in steps:
        if stop_requested:
            return False
        result = pico.send_cmd(command)
        if not result.startswith("OK"):
            print(f"Recovery step failed at '{command}': {result}")
            return False
        time.sleep(delay)
    return True


def _press_steps(button: str, delay: float, count: int) -> list:
    return [(f"press {button} 120", delay)] * count


def recover_to_summary(state_code: int) -> bool:
    bail_out = _press_steps("B", 0.22, 8) + _press_steps("B", 0.40, 1)
    to_summary = [
        ("press X 120", 1.20),
    ] + _press_steps("A", 0.30, 6) + [("press A 120", 0.50)]

    if state_code == STATE_STARTER_CHOSEN_NOT_SUMMARY:
        return run_step_sequence(bail_out + to_summary, "chosen->summary")

    if state_code == STATE_STARTER_NOT_CHOSEN:
        steps = list(bail_out)
        steps += [("press A 120", 1.20)]               # interact with starter
        steps += _press_steps("A", 0.20, 30)           # confirm choice + text
        steps += [("press A 120", 0.85)]                # final confirm
        steps += _press_steps("B", 0.20, 40)            # decline rename + rival text
        steps += [("press B 120", 2.00)]                 # wait for rival animation
        steps += [("press X 120", 1.20)]                 # open menu
        steps += _press_steps("A", 0.30, 7)             # navigate to summary
        steps += [("press A 120", 0.50)]                 # render wait
        return run_step_sequence(steps, "not-chosen->choose->summary")

    return False


def is_pause_requested():
    return PAUSE_FILE.exists()


def wait_if_paused():
    global stop_requested
    if not is_pause_requested():
        return

    print("Pause requested. Bot will stay idle between attempts.")
    print("Use Resume in the web app to continue.")
    while is_pause_requested() and not stop_requested:
        time.sleep(0.5)


def format_hms(total_seconds):
    total_seconds = max(0, int(total_seconds))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02}:{minutes:02}:{seconds:02}"


DEFAULT_STATE = {"attempt": 0, "total_runtime_seconds": DEFAULT_TOTAL_RUNTIME_SECONDS, "recovery_attempts": 0}


def load_state():
    if not STATE_FILE.exists():
        return dict(DEFAULT_STATE)

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            "attempt": int(data.get("attempt", 0)),
            "total_runtime_seconds": int(
                data.get("total_runtime_seconds", DEFAULT_TOTAL_RUNTIME_SECONDS)
            ),
            "recovery_attempts": int(data.get("recovery_attempts", 0)),
        }
    except (json.JSONDecodeError, OSError, ValueError) as e:
        print(f"Warning: could not read {STATE_FILE.name}: {e}")
        return dict(DEFAULT_STATE)


def write_encounter_count(attempt):
    try:
        with open(ENCOUNTER_FILE, "w", encoding="utf-8") as f:
            f.write(f"Soft Resets: {attempt}\n")
    except OSError as e:
        print(f"Warning: could not save {ENCOUNTER_FILE.name}: {e}")


def write_time_file(total_runtime_seconds):
    try:
        with open(TIME_FILE, "w", encoding="utf-8") as f:
            f.write(f"{format_hms(total_runtime_seconds)}\n")
    except OSError as e:
        print(f"Warning: could not save {TIME_FILE.name}: {e}")


def write_state_file(state):
    """Write JSON state atomically."""
    tmp_file = STATE_FILE.with_suffix(".tmp")
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    tmp_file.replace(STATE_FILE)


def save_state(attempt, total_runtime_seconds, *, full=True, recovery_attempts=0):
    state = {"attempt": int(attempt), "total_runtime_seconds": int(total_runtime_seconds), "recovery_attempts": int(recovery_attempts)}
    try:
        write_state_file(state)
        write_time_file(total_runtime_seconds)
        if full:
            write_encounter_count(attempt)
    except OSError as e:
        print(f"Warning: could not save state: {e}")


def keyboard_watcher():
    global stop_requested

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    try:
        tty.setcbreak(fd)

        while not stop_requested:
            rlist, _, _ = select.select([sys.stdin], [], [], 0.1)
            if rlist:
                ch = sys.stdin.read(1)
                if ch == "\x1b":
                    stop_requested = True
                    print("\nESC pressed. Stopping after current step...")
                    break
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def time_updater(previous_runtime, start_time, attempt_tracker, recovery_tracker):
    """Update time file every 5 seconds."""
    global stop_requested

    last_write = time.time()

    while not stop_requested:
        current_time = time.time()
        if current_time - last_write >= 5:
            session_runtime = int(current_time - start_time)
            current_total = previous_runtime + session_runtime

            save_state(attempt_tracker["value"], current_total, full=False, recovery_attempts=recovery_tracker["value"])
            last_write = current_time

        time.sleep(0.5)


def _run_check(*args):
    """Run check_border.py with given args, suppressing macOS AVCapture warnings."""
    result = subprocess.run(
        [sys.executable, str(STAR_SCRIPT)] + list(args),
        cwd=BASE_DIR,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode


def run_star_check():
    return _run_check("--watch-seconds", str(WATCH_SECONDS))


def run_state_check():
    return _run_check("--state-check", "--state-seconds", str(STATE_CHECK_SECONDS))


def main():
    global stop_requested

    print("Press ESC at any time to stop.\n")

    state = load_state()
    completed_attempts = state["attempt"]
    previous_runtime = state["total_runtime_seconds"]
    recovery_count = state["recovery_attempts"]

    save_state(completed_attempts, previous_runtime, recovery_attempts=recovery_count)

    watcher = threading.Thread(target=keyboard_watcher, daemon=True)
    watcher.start()

    start_time = time.time()
    attempt = completed_attempts + 1
    attempt_tracker = {"value": attempt}  # Shared dict for timer_thread to reference
    recovery_tracker = {"value": recovery_count}

    print(f"Loaded saved attempt count: {completed_attempts}")
    print(f"Loaded total runtime: {format_hms(previous_runtime)}")
    print(f"Recovery attempts: {recovery_count}")
    print(f"Starting at attempt #{attempt}")
    notify.bot_started("shiny-bot")

    timer_thread = threading.Thread(
        target=time_updater,
        args=(previous_runtime, start_time, attempt_tracker, recovery_tracker),
        daemon=True
    )
    timer_thread.start()

    try:
        while not stop_requested:
            print("\n" + "=" * 50)
            print(f"Attempt #{attempt}")
            print("=" * 50)

            rc = run_sequence.run()
            if rc != 0:
                print(f"run_sequence failed with code {rc} — soft resetting...")
                pico.send_cmd("reset")
                time.sleep(3.5)
                continue

            if stop_requested:
                break

            state_rc = run_state_check()
            if state_rc != STATE_SUMMARY_READY:
                recovery_count += 1
                recovery_tracker["value"] = recovery_count
                recovered = False
                for retry in range(2):
                    print(f"State check returned {state_rc}. Recovery attempt {retry + 1}/2...")
                    if not recover_to_summary(state_rc):
                        print("Recovery sequence failed to send commands.")
                        break

                    verify_rc = run_state_check()
                    if verify_rc == STATE_SUMMARY_READY:
                        print("Recovery successful. Summary confirmed.")
                        recovered = True
                        break
                    print(f"Recovery did not reach summary (state={verify_rc}). Retrying...")
                    state_rc = verify_rc

                if not recovered:
                    print("Recovery failed after all attempts — soft resetting...")
                    pico.send_cmd("reset")
                    time.sleep(3.5)
                    continue

            detect_rc = run_star_check()

            session_runtime = int(time.time() - start_time)
            total_runtime = previous_runtime + session_runtime

            if detect_rc == 0:
                save_state(attempt, total_runtime, recovery_attempts=recovery_count)
                runtime_str = f"{total_runtime//3600}:{(total_runtime%3600)//60:02d}:{total_runtime%60:02d}"
                notify.shiny_found("Starter", resets=attempt, runtime=runtime_str)
                print("Save it manually on the Switch.")
                print(f"Saved attempt count: {attempt}")
                break
            elif detect_rc == 1:
                save_state(attempt, total_runtime, recovery_attempts=recovery_count)
            else:
                print(f"Detector failed with code {detect_rc} — soft resetting...")
                pico.send_cmd("reset")
                time.sleep(3.5)
                continue

            wait_if_paused()
            if stop_requested:
                break

            attempt += 1
            attempt_tracker["value"] = attempt  # Keep shared tracker in sync

    except KeyboardInterrupt:
        print("\nStopped with Ctrl+C.")
    finally:
        stop_requested = True

        session_runtime = int(time.time() - start_time)
        total_runtime = previous_runtime + session_runtime
        last_saved = load_state()["attempt"]

        save_state(last_saved, total_runtime, recovery_attempts=recovery_count)

        runtime_str = format_hms(total_runtime)
        notify.bot_stopped("shiny-bot", resets=last_saved, runtime=runtime_str)

        print("\nBot stopped.")
        print(f"Last saved attempt: {last_saved}")
        print(f"Recovery attempts: {recovery_count}")
        print(f"Session runtime: {format_hms(session_runtime)}")
        print(f"Total runtime: {format_hms(total_runtime)}")


if __name__ == "__main__":
    main()