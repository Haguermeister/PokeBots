#!/usr/bin/env python3
"""Navigate to trainer card and capture the screen."""
import pico, time, cv2

def press(btn, hold=120, delay=0.5):
    r = pico.send_cmd(f"press {btn} {hold}")
    print(f"  {btn}: {r}")
    time.sleep(delay)

# Back out of current menu
print("Backing out...")
press("B", delay=0.5)
press("B", delay=1.0)

# Open menu (X = GBA Start on NSO)
print("Opening menu...")
press("X", delay=1.0)

# Pre-starter menu: trainer card is the FIRST item (no POKeDEX/POKeMON yet)
print("Selecting trainer card (first item)...")
press("A", delay=2.0)

# Capture the trainer card screen
print("Capturing trainer card...")
cap = cv2.VideoCapture(0, cv2.CAP_AVFOUNDATION)
for _ in range(15):
    cap.read()
ret, frame = cap.read()
if ret:
    cv2.imwrite("debug_trainer_card.png", frame)
    h, w = frame.shape[:2]
    print(f"Frame: {w}x{h}")
    print("Saved debug_trainer_card.png")
else:
    print("Failed to capture frame")
cap.release()
