#!/usr/bin/env python3
"""Pokemon base stats and stat calculation for Gen 3 FRLG.

Contains all Pokemon that can appear as random encounters on Routes 1-2
(for EV tracking), plus all Pokemon that could be a random shiny target.
"""

# Base stats: {hp, atk, def, spe, spa, spd}
# Level and gender ratio for each Pokemon

POKEMON_DATA = {
    # Starters
    "Bulbasaur":  {"base": {"hp":45,"atk":49,"def":49,"spe":45,"spa":65,"spd":65}, "level":5, "gender":"7:1"},
    "Ivysaur":    {"base": {"hp":60,"atk":62,"def":63,"spe":60,"spa":80,"spd":80}, "level":16, "gender":"7:1"},
    "Charmander": {"base": {"hp":39,"atk":52,"def":43,"spe":65,"spa":60,"spd":50}, "level":5, "gender":"7:1"},
    "Charmeleon": {"base": {"hp":58,"atk":64,"def":58,"spe":80,"spa":80,"spd":65}, "level":16, "gender":"7:1"},
    "Squirtle":   {"base": {"hp":44,"atk":48,"def":65,"spe":43,"spa":50,"spd":64}, "level":5, "gender":"7:1"},
    "Wartortle":  {"base": {"hp":59,"atk":63,"def":80,"spe":58,"spa":65,"spd":80}, "level":16, "gender":"7:1"},

    # Route 1 & 2 encounters (for EV tracking)
    "Pidgey":    {"base": {"hp":40,"atk":45,"def":40,"spe":56,"spa":35,"spd":35}, "level":3, "gender":"1:1"},
    "Rattata":   {"base": {"hp":30,"atk":56,"def":35,"spe":72,"spa":25,"spd":35}, "level":3, "gender":"1:1"},
    "Caterpie":  {"base": {"hp":45,"atk":30,"def":35,"spe":45,"spa":20,"spd":20}, "level":3, "gender":"1:1"},
    "Weedle":    {"base": {"hp":40,"atk":35,"def":30,"spe":50,"spa":20,"spd":20}, "level":3, "gender":"1:1"},
    "Pikachu":   {"base": {"hp":35,"atk":55,"def":30,"spe":90,"spa":50,"spd":40}, "level":3, "gender":"1:1"},
    "Spearow":   {"base": {"hp":40,"atk":60,"def":30,"spe":70,"spa":31,"spd":31}, "level":3, "gender":"1:1"},
    "Mankey":    {"base": {"hp":40,"atk":80,"def":35,"spe":70,"spa":35,"spd":45}, "level":3, "gender":"1:1"},

    # Common early-game Pokemon (might be shiny encounter)
    "Nidoran♀":  {"base": {"hp":55,"atk":47,"def":52,"spe":41,"spa":40,"spd":40}, "level":3, "gender":"female_only"},
    "Nidoran♂":  {"base": {"hp":46,"atk":57,"def":40,"spe":50,"spa":40,"spd":40}, "level":3, "gender":"male_only"},
    "Zubat":     {"base": {"hp":40,"atk":45,"def":35,"spe":55,"spa":30,"spd":40}, "level":7, "gender":"1:1"},
    "Geodude":   {"base": {"hp":40,"atk":80,"def":100,"spe":20,"spa":30,"spd":30}, "level":7, "gender":"1:1"},
    "Paras":     {"base": {"hp":35,"atk":70,"def":55,"spe":25,"spa":45,"spd":55}, "level":8, "gender":"1:1"},
    "Diglett":   {"base": {"hp":10,"atk":55,"def":25,"spe":95,"spa":35,"spd":45}, "level":15, "gender":"1:1"},
    "Oddish":    {"base": {"hp":45,"atk":50,"def":55,"spe":30,"spa":75,"spd":65}, "level":12, "gender":"1:1"},
    "Bellsprout":{"base": {"hp":50,"atk":75,"def":35,"spe":40,"spa":70,"spd":30}, "level":12, "gender":"1:1"},
    "Meowth":    {"base": {"hp":40,"atk":45,"def":35,"spe":90,"spa":40,"spd":40}, "level":10, "gender":"1:1"},
    "Abra":      {"base": {"hp":25,"atk":20,"def":15,"spe":90,"spa":105,"spd":55}, "level":8, "gender":"3:1"},
    "Jigglypuff":{"base": {"hp":115,"atk":45,"def":20,"spe":20,"spa":45,"spd":25}, "level":3, "gender":"1:3"},
    "Tentacool": {"base": {"hp":40,"atk":40,"def":35,"spe":70,"spa":50,"spd":100}, "level":5, "gender":"1:1"},
    "Magikarp":  {"base": {"hp":20,"atk":10,"def":55,"spe":80,"spa":15,"spd":20}, "level":5, "gender":"1:1"},
}

# EV yields for Route 1 & 2 Pokemon
EV_YIELDS = {
    "Pidgey":   {"spe": 1},
    "Rattata":  {"spe": 1},
    "Caterpie": {"hp": 1},
    "Weedle":   {"spe": 1},
    "Pikachu":  {"spe": 2},
    "Spearow":  {"spe": 1},
    "Mankey":   {"atk": 1},
    "Nidoran♀": {"hp": 1},
    "Nidoran♂": {"hp": 1},
    "Zubat":    {"spe": 1},
    "Geodude":  {"def": 1},
    "Paras":    {"atk": 1},
    "Diglett":  {"spe": 1},
    "Oddish":   {"spa": 1},
    "Bellsprout":{"atk": 1},
    "Meowth":   {"spe": 1},
    "Abra":     {"spa": 1},
    "Jigglypuff":{"hp": 2},
    "Tentacool":{"spd": 1},
    "Magikarp": {"spe": 1},
}

# Route encounter tables for EV tracking
ROUTE_ENCOUNTERS = {
    "Route 1": {
        "FR": [("Pidgey", "1 Spe"), ("Rattata", "1 Spe")],
        "LG": [("Pidgey", "1 Spe"), ("Rattata", "1 Spe")],
    },
    "Route 2": {
        "FR": [("Pidgey", "1 Spe"), ("Rattata", "1 Spe"), ("Caterpie", "1 HP")],
        "LG": [("Pidgey", "1 Spe"), ("Rattata", "1 Spe"), ("Weedle", "1 Spe")],
    },
    "Viridian Forest": {
        "FR": [("Caterpie", "1 HP"), ("Metapod", "—"), ("Pikachu", "2 Spe"), ("Weedle", "1 Spe"), ("Kakuna", "—")],
        "LG": [("Weedle", "1 Spe"), ("Kakuna", "—"), ("Pikachu", "2 Spe"), ("Caterpie", "1 HP"), ("Metapod", "—")],
    },
}


def calc_stat(base, iv, ev, level, nature_mod, is_hp):
    """Calculate a Gen 3 stat value."""
    ev4 = ev // 4
    if is_hp:
        return ((2 * base + iv + ev4) * level // 100) + level + 10
    else:
        return int((((2 * base + iv + ev4) * level // 100) + 5) * nature_mod)


def calc_all_stats(pokemon_name, ivs, level=None, evs=None, nature_id=0):
    """Calculate all 6 stats."""
    from rng_math import NATURE_MODIFIERS
    data = POKEMON_DATA[pokemon_name]
    base = data["base"]
    if level is None:
        level = data["level"]
    if evs is None:
        evs = {"hp":0,"atk":0,"def":0,"spe":0,"spa":0,"spd":0}

    mods = NATURE_MODIFIERS.get(nature_id)
    stats = {}
    for stat_name, stat_idx in [("hp",0),("atk",1),("def",2),("spe",3),("spa",4),("spd",5)]:
        is_hp = stat_name == "hp"
        nature_mod = 1.0
        if mods and not is_hp:
            if stat_idx == mods[0]:
                nature_mod = 1.1
            elif stat_idx == mods[1]:
                nature_mod = 0.9
        stats[stat_name] = calc_stat(base[stat_name], ivs[stat_name],
                                      evs.get(stat_name, 0), level, nature_mod, is_hp)
    return stats


def reverse_calc_ivs(pokemon_name, observed_stats, nature_id, level=None, evs=None):
    """Reverse-calculate possible IVs from observed stats.

    Returns dict mapping stat name to list of possible IV values (0-31).
    """
    from rng_math import NATURE_MODIFIERS
    data = POKEMON_DATA[pokemon_name]
    base = data["base"]
    if level is None:
        level = data["level"]
    if evs is None:
        evs = {"hp":0,"atk":0,"def":0,"spe":0,"spa":0,"spd":0}

    mods = NATURE_MODIFIERS.get(nature_id)
    possible = {}
    for stat_name, stat_idx in [("hp",0),("atk",1),("def",2),("spe",3),("spa",4),("spd",5)]:
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
            computed = calc_stat(base[stat_name], iv, evs.get(stat_name, 0),
                                level, nature_mod, is_hp)
            if computed == target:
                candidates.append(iv)
        possible[stat_name] = candidates
    return possible


def narrow_ivs_with_levels(pokemon_name, stat_rows, nature_id, evs_at_levels=None):
    """Narrow IVs using stats at multiple levels (after rare candy / leveling).

    stat_rows: list of {"level": int, "stats": {hp, atk, def, spe, spa, spd}}
    evs_at_levels: dict mapping level -> evs dict (if None, assumes 0 EVs at each)

    Returns dict mapping stat name to list of possible IV values.
    """
    all_possible = None
    for row in stat_rows:
        level = row["level"]
        stats = row["stats"]
        evs = (evs_at_levels or {}).get(level, {"hp":0,"atk":0,"def":0,"spe":0,"spa":0,"spd":0})
        possible = reverse_calc_ivs(pokemon_name, stats, nature_id, level, evs)
        if all_possible is None:
            all_possible = possible
        else:
            # Intersect
            for k in all_possible:
                all_possible[k] = [v for v in all_possible[k] if v in possible[k]]
    return all_possible or {}
