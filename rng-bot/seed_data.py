"""FRLG seed data downloader and parser.

Downloads initial seed data from the community Google Sheets for
Fire Red English on Nintendo Switch (NX). Parses into a sorted list
of (initial_seed, seed_frame) pairs for the seed browser.

Seed data source: Community-farmed seeds via ten-lines project.
Each row: seed_frame, pokemon_data...
The initial_seed is computed by advancing the LCRNG from seed 0
by seed_frame steps.
"""

from __future__ import annotations

import csv
import io
import json
import struct
from pathlib import Path

import rng_engine

BASE_DIR = Path(__file__).resolve().parent
SEED_CACHE = BASE_DIR / "seed_data_cache.json"

# Google Sheets CSV export URL for Fire Red English NX seeds
FR_ENG_NX_SHEET = (
    "https://docs.google.com/spreadsheets/d/"
    "1mbn2-XAtmV7HZ1p4esgvUG710VX6FlfhN_HYL_zLJSk/"
    "gviz/tq?tqx=out:csv&sheet=FireRed%20Seeds"
)

# FR English NX constants from ten-lines
STARTING_FRAME = 1821
FRAME_SIZE = 1

# FRLG advance offset for English version (added to target advance for timer)
ENGLISH_ADVANCE_OFFSET = 249


def download_seed_csv(url: str = FR_ENG_NX_SHEET) -> str:
    """Download seed data CSV from Google Sheets."""
    import urllib.request
    import ssl

    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"User-Agent": "PokeBots-RNG/1.0"})
    with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
        return resp.read().decode("utf-8")


def parse_seed_csv(csv_text: str) -> list[dict]:
    """Parse the seed CSV into a list of seed entries.

    The Google Sheet format for FR English NX is:
      Column 0: frame number (VBlank frame this seed appears at)
      Column 1: seed time in ms
      Column 2: initial seed in hex (16-bit — FRLG uses 16-bit timer seeds)

    In FRLG, the initial RNG seed is determined by the console's timer at boot.
    These are 16-bit values (0x0000–0xFFFF). The LCRNG then advances from
    this 16-bit seed as a 32-bit state (upper bits start as 0).
    """
    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)

    if not rows:
        return []

    seeds = []
    for row in rows[1:]:
        if not row or len(row) < 3:
            continue
        try:
            frame_str = row[0].strip()
            seed_hex_str = row[2].strip()

            if not frame_str or not seed_hex_str:
                continue

            frame = int(frame_str)
            initial_seed = int(seed_hex_str, 16) & 0xFFFF  # 16-bit FRLG seed

            seeds.append({
                "initial_seed": initial_seed,
                "seed_frame": frame,
                "seed_hex": f"{initial_seed:04X}",
            })
        except (ValueError, IndexError):
            continue

    seeds.sort(key=lambda s: s["seed_frame"])
    return seeds


def compute_seeds_from_lcrng(count: int = 0x10000) -> list[dict]:
    """Fallback: generate all possible 16-bit initial seeds.

    FRLG uses a 16-bit timer value as the initial RNG seed.
    All 65536 possible seeds are valid; the frame mapping is unknown
    without community data, so we assign synthetic frame numbers.
    """
    seeds = []
    for seed_val in range(count):
        seeds.append({
            "initial_seed": seed_val,
            "seed_frame": STARTING_FRAME + seed_val,
            "seed_hex": f"{seed_val:04X}",
        })
    return seeds


def load_or_download_seeds(force_download: bool = False) -> list[dict]:
    """Load cached seed data or download fresh from Google Sheets."""
    if not force_download and SEED_CACHE.exists():
        try:
            with open(SEED_CACHE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data and isinstance(data, list) and "initial_seed" in data[0]:
                return data
        except (json.JSONDecodeError, OSError, KeyError):
            pass

    # Try to download from Google Sheets
    try:
        csv_text = download_seed_csv()
        seeds = parse_seed_csv(csv_text)
        if seeds:
            _save_cache(seeds)
            return seeds
    except Exception as e:
        print(f"Warning: could not download seed data: {e}")

    # Fallback to computed seeds
    print("Using computed LCRNG seed table as fallback...")
    seeds = compute_seeds_from_lcrng()
    _save_cache(seeds)
    return seeds


def _save_cache(seeds: list[dict]):
    """Save seed data to local cache file."""
    tmp = SEED_CACHE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(seeds, f)
    tmp.replace(SEED_CACHE)


def get_seed_by_frame(seeds: list[dict], target_frame: int) -> dict | None:
    """Find a seed entry by its frame number."""
    for s in seeds:
        if s["seed_frame"] == target_frame:
            return s
    return None


def get_seed_by_hex(seeds: list[dict], hex_str: str) -> dict | None:
    """Find a seed entry by its hex value."""
    target = hex_str.upper().lstrip("0").lstrip("X").zfill(4)
    for s in seeds:
        if s["seed_hex"].lstrip("0").zfill(4) == target:
            return s
    return None


def frame_to_ms(frame: int, frame_rate: float = 16777216 / 280896) -> float:
    """Convert a VBlank frame count to milliseconds.

    Default frame_rate is NX (Switch 1): 16777216 / 280896 ≈ 59.7275 fps
    """
    return (frame / frame_rate) * 1000.0


def ms_to_frame(ms: float, frame_rate: float = 16777216 / 280896) -> int:
    """Convert milliseconds to the nearest VBlank frame count."""
    return round((ms / 1000.0) * frame_rate)
