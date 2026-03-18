#!/usr/bin/env python3
"""Button sequence for one shiny hunt attempt (HTTP/WiFi version)."""
import random
import time
import pico

RESET_TIME = 3.5


def press(button, delay=0.5):
    pico.send_cmd(f"press {button} 120")
    time.sleep(delay)


def hold_button(button, ms):
    pico.send_cmd(f"press {button} {ms}")
    time.sleep(ms / 1000 + 0.05)


def repeat_press(button, delay, count):
    for _ in range(count):
        press(button, delay)


def rand_wait(lo, hi):
    delay = random.uniform(lo, hi)
    print(f"Random wait: {delay:.2f} seconds")
    time.sleep(delay)


def run():
    """Execute the full reset-to-summary sequence. Returns 0 on success."""
    start = time.time()
    print("Starting sequence...")

    pico.send_cmd("reset")
    time.sleep(RESET_TIME)

    # Title screen — rand wait on Charizard, hold A through it
    repeat_press("A", 0.4, 2)
    rand_wait(0.17, 2)
    hold_button("A", 1800)
    time.sleep(0.6)

    # Load save + pick pokemon
    press("A", 1.2)
    repeat_press("A", 0.2, 30)
    press("A", 0.9)

    # "This pokemon is energetic" — rand wait, then decline rename + rival picks
    rand_wait(0.17, 2)
    repeat_press("B", 0.2, 40)
    time.sleep(2.3)

    # Open menu + navigate to summary
    press("X", 1.2)
    repeat_press("A", 0.3, 7)
    time.sleep(0.5)

    elapsed = time.time() - start
    print(f"Sequence complete")
    print(f"Runtime: {elapsed:.3f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
