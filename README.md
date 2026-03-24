# PokeBots

Automated shiny hunting and RNG manipulation bots for **Pokemon FireRed/LeafGreen** on Nintendo Switch (GBA Virtual Console), powered by a **Raspberry Pi Pico W** acting as a USB HID controller.

## Bots

| Bot | Purpose | Pico Connection | Web UI |
|-----|---------|-----------------|--------|
| **[shiny-bot](shiny-bot/)** | Brute-force shiny starter hunting via soft resets | Wi-Fi (HTTP) | `http://localhost:8000` |
| **[uart-bot](uart-bot/)** | Same shiny hunt loop, wired via UART/serial | USB-TTL serial | `http://localhost:8000` |
| **[rng-bot](rng-bot/)** | RNG manipulation for frame-perfect shiny starters | Wi-Fi (HTTP) | `http://localhost:5001` |
| **[sid-finder](sid-finder/)** | Find your Secret ID from a random shiny | — | `http://localhost:5002` |

## How It Works

1. A **Pico W** is connected to the Switch's USB port and enumerates as a Pro Controller (USB HID).
2. The Python bot on your Mac sends button commands to the Pico (over Wi-Fi or UART).
3. The Pico translates commands into real controller inputs (A, B, D-pad, etc.).
4. A **USB capture card** feeds the Switch video to the Mac for frame analysis (shiny detection, state recovery, nature/IV reading).

## Hardware Requirements

- **Raspberry Pi Pico W** — flashed with the appropriate firmware (Wi-Fi or UART variant)
- **USB capture card** — any USB device recognized by macOS as a camera (e.g., Elgato, generic HDMI-to-USB)
- **Nintendo Switch** with GBA Virtual Console (FireRed or LeafGreen)
- **Mac** running macOS (uses AVFoundation via OpenCV for capture)
- For uart-bot: a **USB-to-TTL serial adapter** (CP2102, CH340, etc.)

## Quick Start

### 1. Flash the Pico W Firmware

Each bot has firmware in `pico-fw/`. See the bot-specific README for build instructions, or flash the pre-built `.uf2` file:

```bash
# Hold BOOTSEL on the Pico, plug in via USB, then:
cp shiny-bot/pico-fw/build/shinybot_pico_fw.uf2 /Volumes/RPI-RP2/
```

### 2. Set Up Python

Each bot has its own virtual environment:

```bash
cd shiny-bot
python3 -m venv venv
source venv/bin/activate
pip install opencv-python numpy pyserial  # pyserial only needed for uart-bot
```

### 3. Configure the Pico IP (Wi-Fi bots)

Set the `PICO_IP` environment variable, or edit `pico.py` directly:

```bash
export PICO_IP=192.168.1.100
```

### 4. Run

```bash
# Start the web control panel
python3 web_control.py

# Or run the hunt loop directly
python3 hunt_loop.py
```

## Project Structure

```
PokeBots/
├── README.md
├── .gitignore
├── notify.py               # → shared/notify.py (symlink)
├── shared/                 # Common modules (single source of truth)
│   ├── check_border.py     # Shiny detection via pixel sampling
│   ├── pixel_tools.py      # Live pixel coordinate probing
│   └── notify.py           # iMessage/macOS/ntfy/Discord notifications
├── shiny-bot/              # Wi-Fi shiny hunter
│   ├── hunt_loop.py        # Main automation loop
│   ├── run_sequence.py     # Button sequence for one attempt
│   ├── check_border.py     # → shared/check_border.py (symlink)
│   ├── pixel_tools.py      # → shared/pixel_tools.py (symlink)
│   ├── web_control.py      # Web UI server
│   ├── pico.py             # Pico HTTP communication
│   └── pico-fw/            # Pico W Wi-Fi firmware (C)
├── uart-bot/               # Wired (UART) shiny hunter
│   ├── hunt_loop.py        # Main automation loop
│   ├── run_sequence.py     # Button sequence for one attempt
│   ├── check_border.py     # → shared/check_border.py (symlink)
│   ├── pixel_tools.py      # → shared/pixel_tools.py (symlink)
│   ├── web_control.py      # Web UI server
│   ├── pico.py             # Pico serial communication
│   └── pico-fw/            # Pico W UART firmware (C)
├── rng-bot/                # RNG manipulation bot
│   ├── rng_bot.py          # Main 3-phase timer loop
│   ├── rng_engine.py       # Gen 3 LCRNG + PID reverse search
│   ├── pokemon_data.py     # Base stats, generation triggers
│   ├── web_control.py      # Seed browser + timer UI
│   ├── screen_reader.py    # Nature/shiny detection
│   ├── pico.py             # Pico HTTP communication
│   └── index.html          # Rich web frontend
└── sid-finder/             # SID from random shiny tool
    ├── sid_finder.py       # Web server + API
    ├── rng_math.py         # Re-exports from rng-bot/rng_engine.py
    ├── pokemon_data.py     # Stat calc + EV tracker data
    └── index.html          # 4-step SID finder UI
```

## Acknowledgments

- **[Blissey (imablisy)](https://www.youtube.com/@imablisy)** — FRLG Switch RNG tutorials (starter, legendary/static), seed data, [retailrng.com](https://retailrng.com/)
- **[YoggTwo](https://www.youtube.com/@yoggtwo)** — Static RNG tutorial, RNG overview, and community discoveries
- **Papa Jefe** — Seed farming, RNG method discovery, EonTimer overworld frame correction
- **[Lincoln](https://lincoln-lm.github.io/ten-lines-Pokemon-RNG/)** — [Ten Lines](https://lincoln-lm.github.io/ten-lines-Pokemon-RNG/) tool and SID calculation method
- **[DasAmpharos](https://dasampharos.github.io/EonTimer/)** — [EonTimer](https://dasampharos.github.io/EonTimer/) web timer
- **[Admiral Fish](https://github.com/Admiral-Fish/PokeFinder)** — PokeFinder RNG tool
- **Pico SDK** — Raspberry Pi Pico C/C++ SDK
- **TinyUSB** — USB HID stack for the Pico

## Resources

- [Ten Lines RNG Tool](https://lincoln-lm.github.io/ten-lines-Pokemon-RNG/)
- [EonTimer](https://dasampharos.github.io/EonTimer/)
- [PokeFinder](https://github.com/Admiral-Fish/PokeFinder)
- [Retail RNG Guides](https://retailrng.com/)
- [Pokemon RNG Wiki](https://pokemon-rng.com/)
- [PokemonRNG.net](https://pokemonrng.net/)
