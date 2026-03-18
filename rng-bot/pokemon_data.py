"""Pokemon data for FRLG starters and IV/stat calculation.

Contains base stats, level-up data, and stat formulas for Gen 3.
Also includes IV reverse calculation from observed stats.
"""

from __future__ import annotations

import rng_engine

# FRLG starter base stats: [HP, Atk, Def, Spe, SpA, SpD]
# Order matches Gen 3 internal stat order
STARTERS = {
    "Bulbasaur": {
        "dex": 1,
        "types": ["Grass", "Poison"],
        "base": {"hp": 45, "atk": 49, "def": 49, "spe": 45, "spa": 65, "spd": 65},
        "gender_ratio": "7:1",
        "ability_0": "Overgrow",
        "ability_1": "Overgrow",
        "level": 5,
    },
    "Charmander": {
        "dex": 4,
        "types": ["Fire"],
        "base": {"hp": 39, "atk": 52, "def": 43, "spe": 65, "spa": 60, "spd": 50},
        "gender_ratio": "7:1",
        "ability_0": "Blaze",
        "ability_1": "Blaze",
        "level": 5,
    },
    "Squirtle": {
        "dex": 7,
        "types": ["Water"],
        "base": {"hp": 44, "atk": 48, "def": 65, "spe": 43, "spa": 50, "spd": 64},
        "gender_ratio": "7:1",
        "ability_0": "Torrent",
        "ability_1": "Torrent",
        "level": 5,
    },
}

# Pokemon that appear in early-game battles (for EV tracking during calibration)
# Rival's starter is based on your choice:
#   Bulbasaur -> Charmander, Charmander -> Squirtle, Squirtle -> Bulbasaur
RIVAL_STARTERS = {
    "Bulbasaur": "Charmander",
    "Charmander": "Squirtle",
    "Squirtle": "Bulbasaur",
}

# Route 1 wild Pokemon (for EV tracking if needed for level-up calibration)
ROUTE1_POKEMON = {
    "Pidgey": {
        "base": {"hp": 40, "atk": 45, "def": 40, "spe": 56, "spa": 35, "spd": 35},
        "ev_yield": {"spe": 1},
        "level_range": (2, 5),
    },
    "Rattata": {
        "base": {"hp": 30, "atk": 56, "def": 35, "spe": 72, "spa": 25, "spd": 35},
        "ev_yield": {"spe": 1},
        "level_range": (2, 5),
    },
}


def calc_stat(base: int, iv: int, ev: int, level: int, nature_mod: float, is_hp: bool) -> int:
    """Calculate a Gen 3 stat value.

    HP: ((2*Base + IV + EV/4) * Level / 100) + Level + 10
    Other: (((2*Base + IV + EV/4) * Level / 100) + 5) * nature_mod
    """
    ev4 = ev // 4
    if is_hp:
        return ((2 * base + iv + ev4) * level // 100) + level + 10
    else:
        return int((((2 * base + iv + ev4) * level // 100) + 5) * nature_mod)


def calc_all_stats(
    pokemon_name: str,
    ivs: dict,
    level: int | None = None,
    evs: dict | None = None,
    nature_id: int = 0,
) -> dict:
    """Calculate all stats for a Pokemon.

    Args:
        pokemon_name: Key in STARTERS dict
        ivs: Dict with hp, atk, def, spe, spa, spd
        level: Override level (default: starter level)
        evs: Dict with stat EVs (default: all 0)
        nature_id: Nature index 0-24

    Returns:
        Dict with all calculated stats
    """
    data = STARTERS[pokemon_name]
    base = data["base"]
    if level is None:
        level = data["level"]
    if evs is None:
        evs = {"hp": 0, "atk": 0, "def": 0, "spe": 0, "spa": 0, "spd": 0}

    mods = rng_engine.NATURE_MODIFIERS.get(nature_id, None)

    stats = {}
    for stat_name, stat_idx in [("hp", 0), ("atk", 1), ("def", 2), ("spe", 3), ("spa", 4), ("spd", 5)]:
        is_hp = stat_name == "hp"
        nature_mod = 1.0
        if mods and not is_hp:
            if stat_idx == mods[0]:
                nature_mod = 1.1
            elif stat_idx == mods[1]:
                nature_mod = 0.9
        stats[stat_name] = calc_stat(
            base[stat_name], ivs[stat_name], evs.get(stat_name, 0),
            level, nature_mod, is_hp,
        )

    return stats


def reverse_calc_ivs(
    pokemon_name: str,
    observed_stats: dict,
    nature_id: int,
    level: int | None = None,
    evs: dict | None = None,
) -> dict[str, list[int]]:
    """Reverse-calculate possible IVs from observed stats.

    Returns dict mapping stat name to list of possible IV values (0-31).
    """
    data = STARTERS[pokemon_name]
    base = data["base"]
    if level is None:
        level = data["level"]
    if evs is None:
        evs = {"hp": 0, "atk": 0, "def": 0, "spe": 0, "spa": 0, "spd": 0}

    mods = rng_engine.NATURE_MODIFIERS.get(nature_id, None)

    possible_ivs = {}
    for stat_name, stat_idx in [("hp", 0), ("atk", 1), ("def", 2), ("spe", 3), ("spa", 4), ("spd", 5)]:
        is_hp = stat_name == "hp"
        nature_mod = 1.0
        if mods and not is_hp:
            if stat_idx == mods[0]:
                nature_mod = 1.1
            elif stat_idx == mods[1]:
                nature_mod = 0.9

        target = observed_stats[stat_name]
        candidates = []
        for iv in range(32):
            computed = calc_stat(
                base[stat_name], iv, evs.get(stat_name, 0),
                level, nature_mod, is_hp,
            )
            if computed == target:
                candidates.append(iv)
        possible_ivs[stat_name] = candidates

    return possible_ivs


def pokemon_summary(pkmn: dict, pokemon_name: str) -> dict:
    """Create a full summary for a generated Pokemon, including stats.

    Takes output from rng_engine.method1_pokemon() and adds computed stats,
    gender, ability name, hidden power, etc.
    """
    data = STARTERS[pokemon_name]
    ivs = pkmn["ivs"]
    stats = calc_all_stats(pokemon_name, ivs, nature_id=pkmn["nature_id"])
    gender = rng_engine.gender_from_pid(pkmn["pid"], data["gender_ratio"])
    ability_name = data["ability_0"] if pkmn["ability"] == 0 else data["ability_1"]
    hp_type = rng_engine.hidden_power_type(ivs)
    hp_power = rng_engine.hidden_power_power(ivs)

    return {
        **pkmn,
        "pokemon": pokemon_name,
        "stats": stats,
        "gender": gender,
        "ability_name": ability_name,
        "hp_type": hp_type,
        "hp_power": hp_power,
        "level": data["level"],
        "types": data["types"],
    }


def generate_starter_spread(
    initial_seed: int,
    tid: int,
    sid: int,
    pokemon_name: str,
    min_advance: int,
    max_advance: int,
    *,
    shiny_only: bool = False,
) -> list[dict]:
    """Generate full Pokemon summaries for a starter across an advance range."""
    raw = rng_engine.generate_range(
        initial_seed, tid, sid, min_advance, max_advance, shiny_only=shiny_only,
    )
    return [pokemon_summary(p, pokemon_name) for p in raw]
