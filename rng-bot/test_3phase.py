#!/usr/bin/env python3
"""3-phase timer test — step by step with user confirmation.

Tests the full boot + 3-phase sequence from Blissey's tutorial.
Uses seed 49D1 (frame=2294) and target advance 7946.
"""
import time
import pico

FRAME_RATE = 16777216 / 280896  # ≈ 59.7275 fps
OVERWORLD_FRAMES = 600

# Seed 49D1 parameters
SEED_FRAME = 2294
TARGET_ADVANCE = 7946

# Calculate 3-phase timings
phase1_ms = (SEED_FRAME / FRAME_RATE) * 1000
continue_advances = TARGET_ADVANCE - (OVERWORLD_FRAMES * 2)
phase2_ms = (continue_advances / FRAME_RATE) * 1000
phase3_ms = (OVERWORLD_FRAMES / FRAME_RATE) * 1000

print("=" * 60)
print("3-PHASE TIMER TEST — Seed 49D1, Advance 7946")
print("=" * 60)
print(f"  Phase 1 (seed):     {phase1_ms:.1f}ms = {phase1_ms/1000:.1f}s")
print(f"  Phase 2 (continue): {phase2_ms:.1f}ms = {phase2_ms/1000:.1f}s [{continue_advances} advances @ 1x]")
print(f"  Phase 3 (overworld):{phase3_ms:.1f}ms = {phase3_ms/1000:.1f}s [{OVERWORLD_FRAMES} frames @ 2x = {OVERWORLD_FRAMES*2} advances]")
print(f"  Total advance: {continue_advances} + {OVERWORLD_FRAMES*2} = {TARGET_ADVANCE}")
print()

def send(cmd, desc, delay=0.0):
    result = pico.send_cmd(cmd)
    status = "OK" if result.startswith("OK") else f"FAIL: {result}"
    print(f"  {desc}: {status}")
    if delay > 0:
        time.sleep(delay)

def precise_sleep(seconds):
    if seconds <= 0:
        return
    if seconds > 0.005:
        time.sleep(seconds - 0.005)
    end = time.perf_counter() + 0.005
    while time.perf_counter() < end:
        pass

# ── Step 1: Close game ──
print("STEP 1: Close game")
send("press HOME 120", "HOME", 1.5)
send("press X 120", "X (close prompt)", 0.8)
send("press A 120", "A (confirm close)", 3.0)
print("  Game should be closed.\n")

# ── Step 2: Boot with HOME trick ──
print("STEP 2: Boot game (A → A → HOME)")
send("press A 120", "A (launch)", 2.0)
send("press A 120", "A (profile)", 0.5)
send("press HOME 120", "HOME (suspend)", 2.0)
print("  Game suspended on HOME screen.\n")

# ── Step 3: 3-Phase timed sequence ──
print("STEP 3: Resume + 3-phase timer")
print(f"  Starting timer now...")

timer_origin = time.perf_counter()
pico.send_cmd("press HOME 120")
print(f"  HOME pressed — game resuming, watching intro...")

# Phase 1: Watch intro (NO BUTTONS!)
p1_target = timer_origin + phase1_ms / 1000
remaining = p1_target - time.perf_counter()
print(f"  Phase 1: Waiting {remaining:.1f}s (intro plays)...")
if remaining > 0:
    precise_sleep(remaining)

# Phase 1 beep: HOLD A on title screen
p2_start = time.perf_counter()
print(f"  Phase 1 beep! HOLD A on title screen (1.8s hold)")
pico.send_cmd("press A 1800")
time.sleep(0.6)

# Phase 2: Continue screen
p2_target = p2_start + phase2_ms / 1000
remaining = p2_target - time.perf_counter()
if remaining > 0:
    print(f"  Phase 2: Continue screen ({remaining:.1f}s)...")
    precise_sleep(remaining)
else:
    print(f"  Phase 2: No wait needed (title hold consumed time)")

# Phase 2 beep: A on Continue
p3_start = time.perf_counter()
print(f"  Phase 2 beep! A → Continue")
pico.send_cmd("press A 120")

# Phase 3: Mash to energetic, then wait
print(f"  Phase 3: Save loading (1.5s)...")
time.sleep(1.5)

print(f"  Phase 3: Mashing A ×5 to reach 'energetic'...")
for i in range(5):
    send(f"press A 120", f"A #{i+1}", 0.4)

p3_target = p3_start + phase3_ms / 1000
remaining = p3_target - time.perf_counter()
if remaining > 0:
    print(f"  Waiting {remaining:.1f}s on 'energetic' screen...")
    precise_sleep(remaining)
else:
    print(f"  WARNING: Over Phase 3 budget by {-remaining:.1f}s!")

# Phase 3 beep: A on "energetic" — Method 1 generation!
elapsed_total = time.perf_counter() - timer_origin
print(f"  Phase 3 beep! A on 'energetic' — generating Pokemon! (total: {elapsed_total:.1f}s)")
pico.send_cmd("press A 120")

# ── Step 4: Post-selection ──
print("\nSTEP 4: Post-selection (nickname + rival)")
time.sleep(0.5)
send("press A 120", "A (dialogue)", 0.3)
send("press A 120", "A (dialogue)", 0.3)

print("  B-mashing ×40 (nickname decline + rival)...")
for i in range(40):
    pico.send_cmd("press B 120")
    time.sleep(0.2)
time.sleep(3.0)
print("  Post-selection done.")

# ── Step 5: Check summary ──
print("\nSTEP 5: Navigate to summary")
send("press X 120", "X (open menu)", 1.2)
send("press A 120", "A (POKéMON)", 0.5)
send("press A 120", "A (select Pokemon)", 0.5)
send("press A 120", "A (SUMMARY)", 0.5)
time.sleep(0.5)

# Capture screenshot
print("\nCapturing screenshot...")
import cv2
cap = cv2.VideoCapture(0, cv2.CAP_AVFOUNDATION)
for _ in range(15):
    cap.read()
ret, frame = cap.read()
if ret:
    cv2.imwrite("debug_3phase.png", frame)
    print("Saved debug_3phase.png — check it!")
cap.release()

print("\n" + "=" * 60)
print("TEST COMPLETE")
print("Check the screenshot to see if we're on the summary screen.")
print("Look for: shiny status, nature, and verify the Pokemon is correct.")
print("=" * 60)
