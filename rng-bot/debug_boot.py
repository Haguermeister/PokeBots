#!/usr/bin/env python3
"""Step-by-step boot debug with screen captures at each step."""
import cv2
import time
import numpy as np
import pico

def grab(label):
    cap = cv2.VideoCapture(0, cv2.CAP_AVFOUNDATION)
    for _ in range(10):
        cap.read()
    ret, frame = cap.read()
    cap.release()
    if not ret:
        print(f"  [{label}] FAILED to capture")
        return
    avg = np.mean(frame)
    cv2.imwrite(f"debug_{label}.png", frame)
    print(f"  [{label}] avg_brightness={avg:.0f}  saved debug_{label}.png")

def send(cmd, desc, delay=0.5):
    result = pico.send_cmd(cmd)
    print(f"  {desc}: {result.strip()}")
    time.sleep(delay)

print("=" * 50)
print("BOOT DEBUG — screen capture at each step")
print("=" * 50)

print("\n0. Current screen:")
grab("0_current")

# The game might be running or closed. First ensure we're on HOME.
print("\n1. Press HOME (ensure we're on home screen):")
send("press HOME 120", "HOME", 1.5)
grab("1_home")

# Close the game if running: X to open close dialog, A to confirm
print("\n2. Press X (close game prompt):")
send("press X 120", "X", 1.0)
grab("2_after_X")

print("\n3. Press A (confirm close):")
send("press A 120", "A", 3.0)
grab("3_after_close")

# Now we should be on HOME with no game running.
# Press A to launch the game (cursor should be on the game icon)
print("\n4. Press A (launch game from home):")
send("press A 120", "A", 3.0)
grab("4_after_launch")

# Press A for profile select
print("\n5. Press A (profile select):")
send("press A 120", "A", 1.0)
grab("5_after_profile")

# Press HOME immediately to suspend
print("\n6. Press HOME (suspend before GBA screen):")
send("press HOME 120", "HOME", 1.0)
grab("6_after_suspend")

print("\n7. Waiting 5s for stabilization...")
time.sleep(5.0)
grab("7_stabilized")

# Press HOME to resume
print("\n8. Press HOME (resume game):")
send("press HOME 120", "HOME", 5.0)
grab("8_after_resume")

print("\nDone! Check the debug_*.png files.")
