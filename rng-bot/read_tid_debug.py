#!/usr/bin/env python3
"""Capture and analyze the trainer card for TID reading."""
import cv2
import tid_sid

# Capture the trainer card (should already be on screen)
cap = cv2.VideoCapture(0, cv2.CAP_AVFOUNDATION)
for _ in range(15):
    cap.read()
ret, frame = cap.read()
cap.release()

if not ret:
    print("Failed to capture")
    exit()

cv2.imwrite("debug_trainer_card.png", frame)
h, w = frame.shape[:2]
print(f"Frame: {w}x{h}")

# Crop the ID region and save debug images
cfg = tid_sid.ID_REGION_GBA
x1, y1 = tid_sid.gba_to_cap(cfg["x_start"] - 4, cfg["y"] - 2, w, h)
total_w_gba = cfg["num_digits"] * (cfg["digit_w"] + cfg["digit_gap"]) + 8
x2, y2 = tid_sid.gba_to_cap(cfg["x_start"] + total_w_gba, cfg["y"] + cfg["digit_h"] + 2, w, h)
print(f"ID region: ({x1},{y1}) to ({x2},{y2})")

# Save a wider area for visual inspection
wide_x1, wide_x2 = max(0, x1 - 300), min(w, x2 + 300)
wide_y1, wide_y2 = max(0, y1 - 80), min(h, y2 + 80)
wide_roi = frame[wide_y1:wide_y2, wide_x1:wide_x2]
cv2.imwrite("debug_tid_wide.png", wide_roi)
print(f"Wide ROI saved: {wide_x2-wide_x1}x{wide_y2-wide_y1}")

# Save the narrow ID ROI
roi = frame[y1:y2, x1:x2]
cv2.imwrite("debug_tid_region.png", roi)
print(f"ID ROI size: {roi.shape}")

# Try TID auto-read
tid = tid_sid.read_tid_from_frame(frame)
print(f"TID auto-read: {tid}")

# Debug: pixel info from the ID area
avg = roi.mean(axis=(0, 1))
print(f"ID ROI avg BGR: ({avg[0]:.0f}, {avg[1]:.0f}, {avg[2]:.0f})")
mid_y = roi.shape[0] // 2
for px in range(0, min(roi.shape[1], 60), 5):
    b, g, r = roi[mid_y, px]
    print(f"  pixel ({px},{mid_y}): RGB=({r},{g},{b})")
