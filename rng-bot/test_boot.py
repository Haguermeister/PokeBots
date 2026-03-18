#!/usr/bin/env python3
"""Step-by-step test of the NSO boot timing sequence."""
import pico
import time
import sys

def send(cmd, desc, delay=0.0):
    print(f"  [{desc}] sending: {cmd}")
    result = pico.send_cmd(cmd)
    print(f"    -> {result}")
    if delay > 0:
        print(f"    waiting {delay}s...")
        time.sleep(delay)
    return result

# ── Step 1: Close the game ──
print("=" * 50)
print("STEP 1: Close the game")
print("=" * 50)
# We're on home menu with game suspended. Press X to get close prompt.
send("press X 120", "X = close game prompt", 0.8)
send("press A 120", "A = confirm close", 3.0)
print("Game should be closed now. Should be on home menu with Fire Red icon.\n")

input("Press Enter when you confirm game is fully closed (or just wait)...")

# ── Step 2: Launch game ──
print("=" * 50)
print("STEP 2: Launch game")
print("=" * 50)
send("press A 120", "A = launch game", 2.0)
print("Profile picker should appear now.\n")

# ── Step 3: Select profile ──
print("=" * 50)
print("STEP 3: Select profile")
print("=" * 50)
send("press A 120", "A = select profile", 1.0)
print("Game should be starting to boot.\n")

# ── Step 4: Press HOME to suspend ──
print("=" * 50)
print("STEP 4: Press HOME to suspend game")
print("=" * 50)
send("press HOME 120", "HOME = suspend game", 0.5)
print("Should be on Switch home menu now with game suspended in background.\n")

# ── Step 5: Wait precise time ──
# Seed 49D1 frame = 2294, frame rate = 59.7275 fps
# ms = 2294 / 59.7275 * 1000 = ~38410ms = 38.4 seconds
SEED_FRAME = 2294
FRAME_RATE = 16777216 / 280896
wait_ms = (SEED_FRAME / FRAME_RATE) * 1000
wait_s = wait_ms / 1000

print("=" * 50)
print(f"STEP 5: Wait {wait_s:.3f}s for seed frame {SEED_FRAME}")
print("=" * 50)
print(f"  Waiting {wait_s:.1f} seconds...")

# High-precision sleep
if wait_s > 0.005:
    time.sleep(wait_s - 0.005)
end = time.perf_counter() + 0.005
while time.perf_counter() < end:
    pass

print("  Wait complete!\n")

# ── Step 6: Resume game ──
print("=" * 50)
print("STEP 6: Press HOME to resume game (seed locks now!)")
print("=" * 50)
send("press HOME 120", "HOME = resume game, seed locked!", 3.0)

print("\nDone! Game should be loading with seed 49D1.")
print("You should see the GBA intro / title screen now.")
print("What do you see on screen?")
