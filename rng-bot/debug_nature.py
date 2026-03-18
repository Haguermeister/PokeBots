#!/usr/bin/env python3
"""Debug script to analyze saved frames and test nature detection."""
import cv2
import numpy as np
import sys
sys.path.insert(0, '.')
import screen_reader

# Check what images we have
for name in ['attempt_3.png', 'shiny_detected.png', 'stat_colors_debug.png']:
    img = cv2.imread(name)
    if img is not None:
        h, w = img.shape[:2]
        print(f'{name}: {w}x{h}')
    else:
        print(f'{name}: NOT FOUND')

# Load attempt_3 
img = cv2.imread('attempt_3.png')
if img is None:
    img = cv2.imread('shiny_detected.png')
    if img is None:
        print("No debug images found!")
        exit(1)
    print("Using shiny_detected.png")

h, w = img.shape[:2]
print(f'\nCapture dimensions: {w}x{h}')

# Test game area detection
game_area = screen_reader.detect_game_area(img)
print(f'\nGame area: {game_area}')
if game_area:
    x0, y0, x1, y1 = game_area
    game_w = x1 - x0
    game_h = y1 - y0
    print(f'Game dimensions: {game_w}x{game_h}')
    print(f'GBA aspect (should be 1.5): {game_w/game_h:.3f}')

# Test screen state detection
reader = screen_reader.ScreenReader()
reader.cap_w = w
reader.cap_h = h
state = reader.detect_screen_state(img)
print(f'\nScreen state: {state}')

# Test is_on_stats_page
on_stats = reader.is_on_stats_page(img)
print(f'On stats page: {on_stats}')

# Test nature detection (scan-based)
nature = reader.detect_nature(img)
print(f'Nature detected: {nature}')

# Test scan-based specifically
scan_result = reader._scan_nature(img)
print(f'Scan-based nature: {scan_result}')

# Show what the scan sees
if game_area:
    x0, y0, x1, y1 = game_area
    game_w = x1 - x0
    game_h = y1 - y0
    
    search_x0 = x0
    search_x1 = x0 + int(game_w * 0.35)
    search_y0 = y0 + int(game_h * 0.2)
    search_y1 = y0 + int(game_h * 0.9)
    
    region = img[search_y0:search_y1, search_x0:search_x1]
    rf = region[:,:,2].astype(float)
    gf = region[:,:,1].astype(float)
    bf = region[:,:,0].astype(float)
    brightness = np.maximum(np.maximum(rf, gf), bf)
    
    r_excess = rf - np.maximum(gf, bf)
    red_mask = (r_excess > 20) & (brightness > 80)
    
    b_excess = bf - np.maximum(rf, gf)
    blue_mask = (b_excess > 20) & (brightness > 80)
    
    print(f'\nScan region: ({search_x0},{search_y0}) to ({search_x1},{search_y1})')
    print(f'Red-tinted pixels: {red_mask.sum()}')
    print(f'Blue-tinted pixels: {blue_mask.sum()}')
    
    if red_mask.sum() > 0:
        ry = np.where(red_mask)[0]
        rx = np.where(red_mask)[1]
        print(f'  Red Y range: {ry.min()}-{ry.max()}, X range: {rx.min()}-{rx.max()}')
    if blue_mask.sum() > 0:
        by = np.where(blue_mask)[0]
        bx = np.where(blue_mask)[1]
        print(f'  Blue Y range: {by.min()}-{by.max()}, X range: {bx.min()}-{bx.max()}')
