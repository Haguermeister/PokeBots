#!/usr/bin/env python3
"""Diagnostic boot sequence — captures frames at each step to find correct timing."""
import time
import pico
import screen_reader

r = screen_reader.ScreenReader()
r.open()

def snap(label):
    f = r.grab_frame()
    if f is not None:
        state = r.detect_screen_state(f)
        r.save_debug_frame(f, f"boot_{label}")
        print(f"  [{label}] state={state}")

print("=== BOOT TIMING DIAGNOSTIC ===")
print("Step 0: Current state")
snap("0_before")

print("\nStep 1: Press A to launch game")
pico.send_cmd("press A 120")
for i in range(8):
    time.sleep(0.5)
    snap(f"1_after_launch_{(i+1)*500}ms")

print("\nStep 2: Press A for profile select")
pico.send_cmd("press A 120")
for i in range(6):
    time.sleep(0.25)
    snap(f"2_after_profile_{(i+1)*250}ms")

print("\nStep 3: Press HOME to suspend")
pico.send_cmd("press HOME 120")
for i in range(4):
    time.sleep(0.5)
    snap(f"3_after_home_{(i+1)*500}ms")

print("\nDone! Check boot_*.png files")
r.close()
