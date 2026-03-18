#!/usr/bin/env python3
"""Scan the trainer card to find where the ID number actually is."""
import cv2
import numpy as np

frame = cv2.imread("debug_trainer_card.png")
if frame is None:
    print("No debug_trainer_card.png found")
    exit()

h, w = frame.shape[:2]
print(f"Frame: {w}x{h}")

# The GBA game is rendered inside the 1920x1080 frame.
# NSO might add black borders. Let's find the actual game area.
# Convert to grayscale and find non-black region
gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

# Find rows/columns that aren't black (threshold > 10)
row_means = gray.mean(axis=1)
col_means = gray.mean(axis=0)

# Find first/last non-black row
rows_nonblack = np.where(row_means > 10)[0]
cols_nonblack = np.where(col_means > 10)[0]

if len(rows_nonblack) > 0 and len(cols_nonblack) > 0:
    game_y1, game_y2 = rows_nonblack[0], rows_nonblack[-1]
    game_x1, game_x2 = cols_nonblack[0], cols_nonblack[-1]
    game_w = game_x2 - game_x1 + 1
    game_h = game_y2 - game_y1 + 1
    print(f"Game area: ({game_x1},{game_y1}) to ({game_x2},{game_y2}) = {game_w}x{game_h}")
    print(f"Aspect ratio: {game_w/game_h:.3f} (GBA should be 1.5)")
else:
    print("Could not find game area")
    exit()

# Save the game area
game_roi = frame[game_y1:game_y2+1, game_x1:game_x2+1]
cv2.imwrite("debug_game_area.png", game_roi)

# Now scan for dark pixels on light background (text regions)
# The trainer card has dark text on light background
game_gray = gray[game_y1:game_y2+1, game_x1:game_x2+1]

# Look for dark regions (potential text) - pixels much darker than average
avg_brightness = game_gray.mean()
print(f"Game area avg brightness: {avg_brightness:.0f}")

# Find dark pixel clusters (text)
dark_mask = game_gray < (avg_brightness * 0.5)
# Find rows with significant dark content (text rows)
dark_per_row = dark_mask.sum(axis=1)
text_rows = np.where(dark_per_row > 20)[0]
if len(text_rows) > 0:
    print(f"Text rows (top 20): {text_rows[:20].tolist()}")
    print(f"Text rows range: {text_rows[0]} to {text_rows[-1]}")

# Save horizontal slices at different heights for visual inspection
for frac_name, frac in [("top-quarter", 0.25), ("top-third", 0.33), ("mid", 0.5)]:
    y = int(game_h * frac)
    stripe = game_roi[max(0,y-15):y+15, :]
    cv2.imwrite(f"debug_stripe_{frac_name}.png", stripe)
    print(f"Saved stripe at {frac_name} (y={y})")

# Sample specific spots across the card to locate the ID number
# The IDNo. text should be dark on the light card background
print("\nSampling grid across game area:")
for fy_pct in [20, 25, 30, 35, 40]:
    row_data = []
    y = int(game_h * fy_pct / 100)
    for fx_pct in range(10, 100, 10):
        x = int(game_w * fx_pct / 100)
        b, g, r = game_roi[y, x]
        is_dark = "D" if (r + g + b) / 3 < 100 else "."
        row_data.append(is_dark)
    print(f"  y={fy_pct}%: {''.join(row_data)}")
