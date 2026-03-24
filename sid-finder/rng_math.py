"""Gen 3 RNG Engine — re-exports from rng-bot's canonical rng_engine.py.

This module provides backward compatibility for sid-finder imports.
All RNG math lives in rng-bot/rng_engine.py.
"""
import sys
from pathlib import Path

# Add rng-bot to path so we can import the canonical module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "rng-bot"))

from rng_engine import (
    MULT, ADD, MASK, REV_MULT, REV_ADD,
    NATURES, NATURE_MODIFIERS, GENDER_THRESHOLDS,
    advance, reverse, high16, advance_n,
    method1_pokemon, gender_from_pid,
    hidden_power_type, hidden_power_power,
    find_pids_from_ivs, find_sid_from_shiny, find_sid_from_shiny_pokemon,
)
