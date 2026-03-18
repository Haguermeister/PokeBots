"""Pokemon data for FRLG starters, game corner, and static encounters.

Contains base stats, stat formulas for Gen 3, and IV reverse calculation.
"""

from __future__ import annotations

import rng_engine

# FRLG starter base stats
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

# FireRed Game Corner prizes (Celadon Game Corner)
GAME_CORNER_FR = {
    "Abra": {
        "dex": 63,
        "types": ["Psychic"],
        "base": {"hp": 25, "atk": 20, "def": 15, "spe": 90, "spa": 105, "spd": 55},
        "gender_ratio": "3:1",
        "ability_0": "Synchronize",
        "ability_1": "Inner Focus",
        "level": 9,
    },
    "Clefairy": {
        "dex": 35,
        "types": ["Normal"],
        "base": {"hp": 70, "atk": 45, "def": 48, "spe": 35, "spa": 60, "spd": 65},
        "gender_ratio": "1:3",
        "ability_0": "Cute Charm",
        "ability_1": "Cute Charm",
        "level": 8,
    },
    "Scyther": {
        "dex": 123,
        "types": ["Bug", "Flying"],
        "base": {"hp": 70, "atk": 110, "def": 80, "spe": 105, "spa": 55, "spd": 80},
        "gender_ratio": "1:1",
        "ability_0": "Swarm",
        "ability_1": "Swarm",
        "level": 25,
    },
    "Dratini": {
        "dex": 147,
        "types": ["Dragon"],
        "base": {"hp": 41, "atk": 64, "def": 45, "spe": 50, "spa": 50, "spd": 50},
        "gender_ratio": "1:1",
        "ability_0": "Shed Skin",
        "ability_1": "Shed Skin",
        "level": 18,
    },
    "Porygon": {
        "dex": 137,
        "types": ["Normal"],
        "base": {"hp": 65, "atk": 60, "def": 70, "spe": 40, "spa": 85, "spd": 75},
        "gender_ratio": "genderless",
        "ability_0": "Trace",
        "ability_1": "Trace",
        "level": 26,
    },
}

# LeafGreen Game Corner prizes
GAME_CORNER_LG = {
    "Abra": GAME_CORNER_FR["Abra"],
    "Clefairy": GAME_CORNER_FR["Clefairy"],
    "Pinsir": {
        "dex": 127,
        "types": ["Bug"],
        "base": {"hp": 65, "atk": 125, "def": 100, "spe": 85, "spa": 55, "spd": 70},
        "gender_ratio": "1:1",
        "ability_0": "Hyper Cutter",
        "ability_1": "Hyper Cutter",
        "level": 25,
    },
    "Dratini": GAME_CORNER_FR["Dratini"],
    "Porygon": GAME_CORNER_FR["Porygon"],
}

# Other gift/static Pokemon (Static 1 method)
STATIC_POKEMON = {
    "Eevee": {
        "dex": 133,
        "types": ["Normal"],
        "base": {"hp": 55, "atk": 55, "def": 50, "spe": 55, "spa": 45, "spd": 65},
        "gender_ratio": "7:1",
        "ability_0": "Run Away",
        "ability_1": "Run Away",
        "level": 25,
    },
    "Hitmonlee": {
        "dex": 106,
        "types": ["Fighting"],
        "base": {"hp": 50, "atk": 120, "def": 53, "spe": 87, "spa": 35, "spd": 110},
        "gender_ratio": "male_only",
        "ability_0": "Limber",
        "ability_1": "Limber",
        "level": 25,
    },
    "Hitmonchan": {
        "dex": 107,
        "types": ["Fighting"],
        "base": {"hp": 50, "atk": 105, "def": 79, "spe": 76, "spa": 35, "spd": 110},
        "gender_ratio": "male_only",
        "ability_0": "Keen Eye",
        "ability_1": "Keen Eye",
        "level": 25,
    },
    "Lapras": {
        "dex": 131,
        "types": ["Water", "Ice"],
        "base": {"hp": 130, "atk": 85, "def": 80, "spe": 60, "spa": 85, "spd": 95},
        "gender_ratio": "1:1",
        "ability_0": "Water Absorb",
        "ability_1": "Shell Armor",
        "level": 25,
    },
    "Togepi": {
        "dex": 175,
        "types": ["Normal"],
        "base": {"hp": 35, "atk": 20, "def": 65, "spe": 20, "spa": 40, "spd": 65},
        "gender_ratio": "7:1",
        "ability_0": "Hustle",
        "ability_1": "Serene Grace",
        "level": 5,
    },
}

# Combined lookup for all Pokemon (starters + game corner + static)
ALL_POKEMON = {**STARTERS, **GAME_CORNER_FR, **GAME_CORNER_LG, **STATIC_POKEMON}

# Encounter type categories for the UI
ENCOUNTER_CATEGORIES = {
    "starters": list(STARTERS.keys()),
    "game_corner": list({**GAME_CORNER_FR, **GAME_CORNER_LG}.keys()),
    "static": list(STATIC_POKEMON.keys()),
}

# Generation trigger info per Pokemon (from Blissey's legendary tutorial)
# "trigger" = what generates the Pokemon (determines when to press A)
# "has_npcs" = whether wandering NPCs are nearby (need start menu trick)
# "animation_frames" = if the Pokemon has a long pre-battle animation, may need
#                       more overworld frames (0 = default 600 is fine)
GENERATION_TRIGGERS = {
    # Starters — "energetic" screen
    "Bulbasaur":  {"trigger": "energetic_screen", "has_npcs": False, "animation_frames": 0},
    "Charmander": {"trigger": "energetic_screen", "has_npcs": False, "animation_frames": 0},
    "Squirtle":   {"trigger": "energetic_screen", "has_npcs": False, "animation_frames": 0},
    # Game Corner — press A to confirm exchange
    "Abra":     {"trigger": "confirm_receive", "has_npcs": True, "animation_frames": 0},
    "Clefairy": {"trigger": "confirm_receive", "has_npcs": True, "animation_frames": 0},
    "Scyther":  {"trigger": "confirm_receive", "has_npcs": True, "animation_frames": 0},
    "Dratini":  {"trigger": "confirm_receive", "has_npcs": True, "animation_frames": 0},
    "Porygon":  {"trigger": "confirm_receive", "has_npcs": True, "animation_frames": 0},
    "Pinsir":   {"trigger": "confirm_receive", "has_npcs": True, "animation_frames": 0},
    # Gifts — press A to receive
    "Eevee":      {"trigger": "confirm_receive", "has_npcs": False, "animation_frames": 0},
    "Hitmonlee":  {"trigger": "confirm_receive", "has_npcs": False, "animation_frames": 0},
    "Hitmonchan": {"trigger": "confirm_receive", "has_npcs": False, "animation_frames": 0},
    "Lapras":     {"trigger": "confirm_receive", "has_npcs": False, "animation_frames": 0},
    "Togepi":     {"trigger": "confirm_receive", "has_npcs": False, "animation_frames": 0},
    # Legendary birds — press A IN FRONT (first interaction, not last dialogue!)
    "Articuno": {"trigger": "first_a_press", "has_npcs": False, "animation_frames": 0},
    "Zapdos":   {"trigger": "first_a_press", "has_npcs": False, "animation_frames": 0},
    "Moltres":  {"trigger": "first_a_press", "has_npcs": False, "animation_frames": 0},
    # Other legendaries
    "Mewtwo":  {"trigger": "first_a_press", "has_npcs": False, "animation_frames": 0},
    "Deoxys":  {"trigger": "first_a_press", "has_npcs": False, "animation_frames": 1200},
    # Stationary wilds
    "Snorlax": {"trigger": "first_a_press", "has_npcs": False, "animation_frames": 0},
    "Hypno":   {"trigger": "first_a_press", "has_npcs": True, "animation_frames": 0},
    # Ho-Oh/Lugia — press UP to walk (no A press!)
    "Ho-Oh": {"trigger": "walk_up", "has_npcs": False, "animation_frames": 600},
    "Lugia": {"trigger": "walk_up", "has_npcs": False, "animation_frames": 600},
}

def get_trigger_info(pokemon_name: str) -> dict:
    """Get generation trigger info for a Pokemon, with safe defaults."""
    return GENERATION_TRIGGERS.get(pokemon_name, {
        "trigger": "confirm_receive",
        "has_npcs": False,
        "animation_frames": 0,
    })

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
        pokemon_name: Key in ALL_POKEMON dict
        ivs: Dict with hp, atk, def, spe, spa, spd
        level: Override level (default from data)
        evs: Dict with stat EVs (default: all 0)
        nature_id: Nature index 0-24

    Returns:
        Dict with all calculated stats
    """
    data = ALL_POKEMON[pokemon_name]
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
    data = ALL_POKEMON[pokemon_name]
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
    """Create a full summary for a generated Pokemon, including stats."""
    data = ALL_POKEMON[pokemon_name]
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


def generate_pokemon_spread(
    initial_seed: int,
    tid: int,
    sid: int,
    pokemon_name: str,
    min_advance: int,
    max_advance: int,
    *,
    shiny_only: bool = False,
) -> list[dict]:
    """Generate full Pokemon summaries across an advance range."""
    raw = rng_engine.generate_range(
        initial_seed, tid, sid, min_advance, max_advance, shiny_only=shiny_only,
    )
    return [pokemon_summary(p, pokemon_name) for p in raw]


# Keep old name for compatibility
generate_starter_spread = generate_pokemon_spread
