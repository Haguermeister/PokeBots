#!/usr/bin/env python3
"""Gen 3 RNG Engine — LCRNG, Method 1, IV/PID reverse search.

Standalone module for the SID Finder tool. Contains all the RNG math
needed to reverse-engineer a Secret ID from a random shiny Pokemon.
"""

# LCRNG constants (same as PokeFinder / Ten Lines)
MULT = 0x41C64E6D
ADD = 0x6073
MASK = 0xFFFFFFFF
REV_MULT = 0xEEB9EB65
REV_ADD = 0x0A3561A1

NATURES = [
    "Hardy", "Lonely", "Brave", "Adamant", "Naughty",
    "Bold", "Docile", "Relaxed", "Impish", "Lax",
    "Timid", "Hasty", "Serious", "Jolly", "Naive",
    "Modest", "Mild", "Quiet", "Bashful", "Rash",
    "Calm", "Gentle", "Sassy", "Careful", "Quirky",
]

# Nature stat modifiers: index -> (boosted_stat_idx, lowered_stat_idx)
# Stats: 1=Atk, 2=Def, 3=Spe, 4=SpA, 5=SpD
NATURE_MODIFIERS = {}
_stats = [1, 2, 3, 4, 5]
for _i in range(25):
    _up = _i // 5
    _down = _i % 5
    if _up != _down:
        NATURE_MODIFIERS[_i] = (_stats[_up], _stats[_down])

GENDER_THRESHOLDS = {
    "1:1": 127, "3:1": 63, "1:3": 191, "7:1": 31,
    "genderless": -1, "male_only": 0, "female_only": 254,
}


def advance(seed):
    return (seed * MULT + ADD) & MASK

def reverse(seed):
    return (seed * REV_MULT + REV_ADD) & MASK

def high16(seed):
    return (seed >> 16) & 0xFFFF


def method1_pokemon(seed, tid=0, sid=0):
    """Generate Method 1 Pokemon from seed state BEFORE first PID call."""
    seed = advance(seed)
    pid_low = high16(seed)
    seed = advance(seed)
    pid_high = high16(seed)
    pid = (pid_high << 16) | pid_low

    seed = advance(seed)
    iv1 = high16(seed)
    hp_iv = iv1 & 0x1F
    atk_iv = (iv1 >> 5) & 0x1F
    def_iv = (iv1 >> 10) & 0x1F

    seed = advance(seed)
    iv2 = high16(seed)
    spe_iv = iv2 & 0x1F
    spa_iv = (iv2 >> 5) & 0x1F
    spd_iv = (iv2 >> 10) & 0x1F

    nature_id = pid % 25
    shiny_value = tid ^ sid ^ pid_high ^ pid_low
    shiny = shiny_value < 8

    return {
        "pid": pid,
        "pid_hex": f"{pid:08X}",
        "nature": NATURES[nature_id],
        "nature_id": nature_id,
        "ability": pid & 1,
        "gender_value": pid & 0xFF,
        "shiny": shiny,
        "shiny_value": shiny_value,
        "ivs": {"hp": hp_iv, "atk": atk_iv, "def": def_iv,
                "spe": spe_iv, "spa": spa_iv, "spd": spd_iv},
    }


def find_pids_from_ivs(ivs):
    """Find all Method 1 PIDs that produce the given exact IVs.

    Method 1: Call3→IV1(HP/Atk/Def), Call4→IV2(Spe/SpA/SpD)
    We reconstruct Call3's upper 16 bits from IVs, try all 65536
    lower 16-bit values, check if the forward LCRNG gives matching
    Call4 upper bits, then reverse to get PID.

    Important: IVs only use bits 0-14 of the upper 16 bits. Bit 15
    is unused, so we must try both 0 and 1 for that bit (2 values
    for IV1 × 2 for IV2 = 4 combinations).

    Returns list of {pid, pid_hex, nature, nature_id, ability, gender_value}.
    """
    # Reconstruct bits 0-14 from IVs (bit 15 is unknown)
    iv1_base = (ivs["def"] << 10) | (ivs["atk"] << 5) | ivs["hp"]
    iv2_base = (ivs["spd"] << 10) | (ivs["spa"] << 5) | ivs["spe"]

    # Bit 15 unknown → try both 0 and 0x8000
    iv1_variants = [iv1_base, iv1_base | 0x8000]
    iv2_variants = [iv2_base, iv2_base | 0x8000]

    results = []
    for iv1_upper in iv1_variants:
        for iv2_upper in iv2_variants:
            for low16 in range(0x10000):
                seed3 = (iv1_upper << 16) | low16

                # Call 4 = LCRNG(Call 3)
                seed4 = (seed3 * MULT + ADD) & MASK
                if high16(seed4) != iv2_upper:
                    continue

                # Reverse Call 3 → Call 2 → Call 1
                seed2 = reverse(seed3)
                seed1 = reverse(seed2)

                pid_high = high16(seed2)
                pid_low = high16(seed1)
                pid = (pid_high << 16) | pid_low

                results.append({
                    "pid": pid,
                    "pid_hex": f"{pid:08X}",
                    "nature": NATURES[pid % 25],
                    "nature_id": pid % 25,
                    "ability": pid & 1,
                    "gender_value": pid & 0xFF,
                })

    return results


def find_sid_from_shiny(tid, pid):
    """Find all possible SIDs given TID and a shiny PID.

    Shiny: (TID ^ SID ^ PID_high ^ PID_low) < 8
    So SID = TID ^ PID_high ^ PID_low ^ shiny_value, for shiny_value 0-7.

    Returns list of 8 possible SIDs.
    """
    pid_high = (pid >> 16) & 0xFFFF
    pid_low = pid & 0xFFFF
    base = tid ^ pid_high ^ pid_low
    return [base ^ sv for sv in range(8)]


def find_sid_from_shiny_pokemon(tid, ivs, nature_name):
    """Full pipeline: IVs + nature → PID candidates → filter by nature → SID candidates.

    Returns list of {pid, pid_hex, nature, sids: [8 values]}.
    """
    pid_candidates = find_pids_from_ivs(ivs)

    # Filter PIDs that match the observed nature
    nature_idx = NATURES.index(nature_name) if nature_name in NATURES else -1
    matching = [p for p in pid_candidates if p["nature_id"] == nature_idx]

    results = []
    for p in matching:
        sids = find_sid_from_shiny(tid, p["pid"])
        results.append({
            **p,
            "sids": sids,
        })

    return results
