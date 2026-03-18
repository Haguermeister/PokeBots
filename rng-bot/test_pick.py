#!/usr/bin/env python3
"""Navigate from GBA intro through to picking Charmander."""
import pico
import time

def send(cmd, desc, delay=0.0):
    result = pico.send_cmd(cmd)
    print(f"  {desc}: {result}")
    if delay > 0:
        time.sleep(delay)

# Navigate intro to Continue screen
print("Mashing A through intro/title...")
for i in range(8):
    send("press A 120", f"A #{i+1}", 0.5)

# Hold A through title animation
send("press A 1800", "Hold A through title", 1.5)

print("\nShould be at Continue/New Game menu now.")
print("Pressing A to load save...")
send("press A 120", "A = Continue", 1.5)

print("In overworld now. Waiting for overworld RNG to advance...")
# For advance 7946: overworld time = (7946 + 249) / 2 / 59.7275 * 1000
# = 8195 / 2 / 59.7275 * 1000 = 4097.5 / 59.7275 * 1000 = ~68,610 ms = 68.6s
FRAME_RATE = 16777216 / 280896
target_advance = 7946
english_offset = 249
total_advances = target_advance + english_offset
overworld_frames = total_advances / 2
wait_ms = (overworld_frames / FRAME_RATE) * 1000
wait_s = wait_ms / 1000

print(f"Phase 3: Waiting {wait_s:.1f}s in overworld for advance {target_advance}...")
time.sleep(wait_s)

# Pick Charmander!
print("\nPicking Charmander NOW!")
send("press A 120", "A = interact with starter", 1.2)

# A-spam through dialogue
print("Mashing A through dialogue...")
for i in range(30):
    send("press A 120", f"dialogue A #{i+1}", 0.2)

# Final confirm
send("press A 120", "final confirm", 0.85)

# Decline nickname + rival dialogue
print("Declining nickname, rival picks...")
for i in range(40):
    send("press B 120", f"B #{i+1}", 0.2)

# Wait for rival battle
print("Waiting for rival battle to finish...")
time.sleep(3.0)

print("\nStarter should be picked! Now checking it...")
# Open menu
send("press X 120", "X = open menu", 1.2)

# Navigate: Down once for trainer card (pre-Pokemon menu), but now we HAVE
# a Pokemon so the menu is: POKeDEX, POKeMON, BAG, [name], SAVE, OPTION, EXIT
# We want POKeMON (2nd item) -> Summary
send("dpad DOWN 120", "Down to POKeMON", 0.3)
send("press A 120", "A = select POKeMON", 0.5)
send("press A 120", "A = select Pokemon", 0.5)
send("press A 120", "A = Summary", 0.5)
send("press A 120", "A (menu)", 0.5)
send("press A 120", "A (menu)", 0.5)
send("press A 120", "A (confirm)", 0.5)

print("\nShould be on summary screen. Capturing...")
import cv2
cap = cv2.VideoCapture(0, cv2.CAP_AVFOUNDATION)
for _ in range(15):
    cap.read()
ret, frame = cap.read()
if ret:
    cv2.imwrite("debug_summary.png", frame)
    print("Saved debug_summary.png")
cap.release()

print("\nDone! Check the summary screen to see what we got.")
