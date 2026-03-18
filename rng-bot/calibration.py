"""Calibration module for RNG manipulation.

After an RNG attempt, the user checks their Pokemon's stats and enters them.
This module compares the actual Pokemon against what was expected, determines
the actual advance that was hit, and calculates the timer adjustment needed.

Workflow:
  1. User enters observed stats (or nature) from the summary screen
  2. We search nearby advances for a match
  3. Calculate the offset: actual_advance - target_advance
  4. Convert advance offset to milliseconds adjustment
  5. Update calibration_offset_ms in state
"""

from __future__ import annotations

import json
from pathlib import Path

import rng_engine
import pokemon_data
import seed_data

BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "rng_state.json"

# NX frame rate
FRAME_RATE = 16777216 / 280896

# How far to search around the target advance for calibration
CALIBRATION_SEARCH_RANGE = 500


def load_state() -> dict:
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(st: dict):
    tmp = STATE_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=2)
    tmp.replace(STATE_FILE)


def find_actual_advance(
    initial_seed: int,
    tid: int,
    sid: int,
    pokemon_name: str,
    target_advance: int,
    *,
    observed_nature: str | None = None,
    observed_stats: dict | None = None,
    observed_gender: str | None = None,
    search_range: int = CALIBRATION_SEARCH_RANGE,
) -> list[dict]:
    """Search for the actual advance that was hit based on observed Pokemon properties.

    Returns a list of candidate matches sorted by distance from target.
    Each includes the full Pokemon data + advance offset.
    """
    min_adv = max(0, target_advance - search_range)
    max_adv = target_advance + search_range

    candidates = pokemon_data.generate_starter_spread(
        initial_seed, tid, sid, pokemon_name, min_adv, max_adv,
    )

    matches = []
    for pkmn in candidates:
        score = 0
        reasons = []

        if observed_nature is not None:
            if pkmn["nature"].lower() == observed_nature.lower():
                score += 10
                reasons.append("nature match")
            else:
                continue  # Nature must match if provided

        if observed_gender is not None:
            if pkmn["gender"].lower() == observed_gender.lower():
                score += 5
                reasons.append("gender match")
            else:
                continue  # Gender must match if provided

        if observed_stats is not None:
            # Check if observed stats match computed stats
            stats = pkmn["stats"]
            stat_match = True
            for stat_name, obs_val in observed_stats.items():
                if stat_name in stats and stats[stat_name] != obs_val:
                    stat_match = False
                    break
            if stat_match:
                score += 50
                reasons.append("stats match")
            else:
                continue  # Stats must match if provided

        offset = pkmn["advance"] - target_advance
        # Closer to target = higher score bonus
        score += max(0, 100 - abs(offset))

        matches.append({
            **pkmn,
            "offset": offset,
            "score": score,
            "match_reasons": reasons,
        })

    matches.sort(key=lambda m: (-m["score"], abs(m["offset"])))
    return matches


def advance_offset_to_ms(offset: int) -> float:
    """Convert an advance offset to milliseconds.

    In FRLG overworld, RNG advances at 2x speed (2 per frame).
    So 1 advance = 0.5 frames. At ~59.7 fps, 1 frame ≈ 16.74ms.
    1 advance ≈ 8.37ms.
    """
    frames = offset / 2  # 2x speed in overworld
    return (frames / FRAME_RATE) * 1000


def apply_calibration(actual_advance: int) -> dict:
    """Apply calibration based on the actual advance hit.

    Calculates the timer adjustment and saves it to state.
    """
    st = load_state()
    target = st.get("target_pokemon", {})
    target_advance = target.get("advance", 0)

    offset = actual_advance - target_advance
    offset_ms = advance_offset_to_ms(offset)

    # Update calibration offset (accumulate adjustments)
    old_cal = st.get("calibration_offset_ms", 0)
    # If we hit too late (positive offset), we need to start earlier (subtract from timer)
    # If we hit too early (negative offset), we need to start later (add to timer)
    new_cal = old_cal - offset_ms

    st["calibration_offset_ms"] = round(new_cal, 1)
    st["last_result"] = {
        "actual_advance": actual_advance,
        "target_advance": target_advance,
        "offset_advances": offset,
        "offset_ms": round(offset_ms, 1),
        "old_calibration_ms": old_cal,
        "new_calibration_ms": round(new_cal, 1),
    }
    save_state(st)

    return st["last_result"]


def reverse_calc_from_stats(
    pokemon_name: str,
    observed_stats: dict,
    nature_name: str,
    level: int = 5,
    evs: dict | None = None,
) -> dict:
    """Reverse-calculate IVs from observed stats.

    Returns possible IV ranges for each stat and whether the match is exact.
    """
    nature_id = rng_engine.NATURES.index(nature_name) if nature_name in rng_engine.NATURES else 0

    possible_ivs = pokemon_data.reverse_calc_ivs(
        pokemon_name, observed_stats, nature_id, level, evs,
    )

    exact = all(len(v) == 1 for v in possible_ivs.values())

    return {
        "possible_ivs": possible_ivs,
        "exact": exact,
        "nature_id": nature_id,
    }
