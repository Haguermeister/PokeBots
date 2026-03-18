# rng-bot

**RNG manipulation bot** for frame-perfect shiny starters in **Pokemon FireRed/LeafGreen** on Nintendo Switch (GBA Virtual Console).

Based on [Blissey's FRLG Switch shiny starter tutorial](https://www.youtube.com/watch?v=example) — uses a 3-phase timer model to hit a specific RNG advance for a guaranteed shiny with desired nature/IVs.

## How It Works

Unlike shiny-bot/uart-bot which brute-force soft reset, rng-bot **targets a specific RNG frame**:

1. **Seed Selection** — The game's initial seed is determined by the boot timing. There are ~551 possible seeds. The web UI lets you browse all seeds and find which ones contain shiny Pokemon at reachable advances.
2. **TID/SID Detection** — Reads your Trainer ID from the trainer card screen via OCR, then derives the Secret ID from the LCRNG sequence.
3. **3-Phase Timer** — Three frame-perfect timing windows:
   - **Phase 1 (Seed):** Hold A on the title screen for a precise duration to hit the target seed
   - **Phase 2 (Continue):** Wait on the Continue/New Game screen, then press A at the right frame
   - **Phase 3 (Overworld):** Mash through dialogue, then press A on the final timing frame
4. **Calibration** — After each attempt, the bot reads the resulting nature/IVs from the summary screen, calculates which advance was actually hit, and auto-adjusts the timer offset.

## Setup

### Prerequisites

- Raspberry Pi Pico W flashed with the Wi-Fi firmware (same as shiny-bot)
- USB capture card connected to the Switch
- macOS with Python 3.9+

### Install

```bash
cd rng-bot
python3 -m venv venv
source venv/bin/activate
pip install opencv-python numpy requests
```

### Configure Pico IP

```bash
export PICO_IP=192.168.1.100
```

Or edit the default in `pico.py`.

## Usage

### Web Control Panel (recommended)

```bash
python3 web_control.py
# Open http://localhost:5001
```

The web UI (`index.html`) provides:
- **Seed Browser** — view all 551 initial seeds with timing info
- **Shiny Finder** — for each seed, find all shiny Pokemon within an advance range
- **Target Selector** — pick a specific shiny to hunt (e.g., Modest Charmander with 31 SpA)
- **Timer Controls** — start/stop the 3-phase automated timer
- **Calibration Panel** — view attempt history, adjust timing offsets
- **Manual Buttons** — A, B, D-pad for testing

### Command Line

```bash
# Full automation loop
python3 rng_bot.py

# Single attempt (for testing)
python3 rng_bot.py --once

# Dry run (print timing without pressing buttons)
python3 rng_bot.py --dry-run
```

### Workflow

1. Start the web UI and browse seeds to find a good shiny target.
2. Use "Read TID" to capture your Trainer ID from the trainer card.
3. Select a target seed + advance + Pokemon.
4. Run the bot — it will loop attempts, calibrating after each one.
5. The bot stops automatically when the target shiny is hit.

## Files

### Core

| File | Purpose |
|------|---------|
| `rng_bot.py` | Main automation loop (3-phase timer, attempt management) |
| `rng_engine.py` | Gen 3 LCRNG implementation (Method 1 PID/IV generation) |
| `pokemon_data.py` | FRLG starter base stats, gender ratios, abilities |
| `seed_data.py` | Seed data downloader (Google Sheets community data + local cache) |
| `calibration.py` | Post-attempt analysis, advance offset calculation, timer tuning |
| `tid_sid.py` | Trainer ID reading + Secret ID derivation from LCRNG |
| `screen_reader.py` | Nature/shiny detection via pixel color sampling |
| `pico.py` | Pico W HTTP communication module |

### Web

| File | Purpose |
|------|---------|
| `web_control.py` | HTTP API server (port 5001) |
| `index.html` | Rich single-page web frontend |

### Testing & Debug

| File | Purpose |
|------|---------|
| `test_rng.py` | Unit tests for LCRNG, Method 1 generation, IV/nature math |
| `test_boot.py` | Boot sequence timing tests |
| `test_pick.py` | Starter selection timing tests |
| `debug_boot.py` | Boot sequence debugging with Pico feedback |
| `debug_nature.py` | Nature detection debugging |
| `diag_boot.py` | Boot diagnostics |
| `diagnose_nature.py` | Nature diagnosis from frames |
| `find_target.py` | Search all seeds for a specific shiny |
| `find_advance.py` | Find advance range by nature/IV |
| `filter_advance.py` | Filter advances by nature |
| `read_tid_debug.py` | Debug TID reading from trainer card |
| `scan_card.py` | Scan trainer card for TID |
| `record_phase3.py` | Record phase 3 overworld sequence by keyboard |
| `nav_trainer_card.py` | Navigate UI to trainer card |

### Reference

| File | Purpose |
|------|---------|
| `blissey_transcript.txt` | Notes from Blissey's tutorial (timing specs, strategy) |
