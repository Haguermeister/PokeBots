#!/usr/bin/env python3
"""Analyze debug screenshots to diagnose nature detection issues."""
import cv2
import numpy as np
import sys
sys.path.insert(0, '.')
from screen_reader import detect_game_area, ScreenReader

for fname in ["stats_page_7.png", "stats_page_6.png", "nature_detection.png"]:
    frame = cv2.imread(fname)
    if frame is None:
        print(f"--- {fname}: NOT FOUND ---")
        continue

    print(f"\n{'='*60}")
    print(f"=== {fname} ({frame.shape[1]}x{frame.shape[0]}) ===")
    print(f"{'='*60}")

    ga = detect_game_area(frame)
    print(f"Game area: {ga}")
    if not ga:
        print("  No game area detected!")
        continue

    x0, y0, x1, y1 = ga
    gw, gh = x1 - x0, y1 - y0
    print(f"Game size: {gw}x{gh}")

    # Search region used by _scan_nature
    sx0 = x0
    sx1 = x0 + int(gw * 0.35)
    sy0 = y0 + int(gh * 0.2)
    sy1 = y0 + int(gh * 0.9)
    print(f"Scan region: x={sx0}-{sx1}, y={sy0}-{sy1}")

    region = frame[sy0:sy1, sx0:sx1]
    rf = region[:, :, 2].astype(np.float32)
    gf = region[:, :, 1].astype(np.float32)
    bf = region[:, :, 0].astype(np.float32)
    brightness = np.maximum(np.maximum(rf, gf), bf)

    median_br = float(np.median(brightness))
    print(f"Median brightness: {median_br:.1f}")

    r_excess = rf - np.maximum(gf, bf)
    b_excess = bf - np.maximum(rf, gf)

    red_mask = (r_excess > 40) & (brightness > 160)
    blue_mask = (b_excess > 40) & (brightness > 160)

    red_count = int(red_mask.sum())
    blue_count = int(blue_mask.sum())
    print(f"Red pixels: {red_count}, Blue pixels: {blue_count}")

    region_h = sy1 - sy0
    stats = ["atk", "def", "spa", "spd", "spe"]

    if red_count > 15:
        red_ys = np.where(red_mask)[0]
        red_center = float(np.median(red_ys))
        ratio = red_center / region_h
        idx = min(4, max(0, int(ratio * 5)))
        print(f"RED: center_y={red_center:.0f}, ratio={ratio:.3f}, idx={idx} -> boosted={stats[idx]}")
        for i in range(5):
            lo = int(region_h * i / 5)
            hi = int(region_h * (i + 1) / 5)
            cnt = int(red_mask[lo:hi].sum())
            if cnt > 0:
                print(f"  Band {i} ({stats[i]}): y={lo}-{hi}, red_px={cnt}")

    if blue_count > 15:
        blue_ys = np.where(blue_mask)[0]
        blue_center = float(np.median(blue_ys))
        ratio = blue_center / region_h
        idx = min(4, max(0, int(ratio * 5)))
        print(f"BLUE: center_y={blue_center:.0f}, ratio={ratio:.3f}, idx={idx} -> lowered={stats[idx]}")
        for i in range(5):
            lo = int(region_h * i / 5)
            hi = int(region_h * (i + 1) / 5)
            cnt = int(blue_mask[lo:hi].sum())
            if cnt > 0:
                print(f"  Band {i} ({stats[i]}): y={lo}-{hi}, blue_px={cnt}")

    if red_count > 15 and blue_count > 15:
        red_ys = np.where(red_mask)[0]
        blue_ys = np.where(blue_mask)[0]
        r_center = float(np.median(red_ys))
        b_center = float(np.median(blue_ys))
        r_idx = min(4, max(0, int((r_center / region_h) * 5)))
        b_idx = min(4, max(0, int((b_center / region_h) * 5)))
        from screen_reader import NATURE_FROM_STATS
        key = (stats[r_idx], stats[b_idx])
        nature = NATURE_FROM_STATS.get(key, "UNKNOWN")
        print(f"\nDETECTED: boosted={stats[r_idx]}, lowered={stats[b_idx]} -> {nature}")

    # Also try the ScreenReader directly
    reader = ScreenReader.__new__(ScreenReader)
    reader.cap = None
    result = reader._scan_nature(frame)
    print(f"ScreenReader._scan_nature() returned: {result}")

    # Also check if the frame looks like a stats page
    # Sample some pixel regions to understand layout
    print("\nPixel samples from game area:")
    for label, rx, ry in [
        ("top-left", 0.05, 0.05),
        ("header-bar", 0.25, 0.12),
        ("stat-area", 0.15, 0.45),
        ("center", 0.5, 0.5),
        ("bottom-text", 0.5, 0.85),
    ]:
        px = x0 + int(gw * rx)
        py = y0 + int(gh * ry)
        if py < frame.shape[0] and px < frame.shape[1]:
            b, g, r = frame[py, px]
            print(f"  {label:15s} ({px},{py}): R={r} G={g} B={b}")
