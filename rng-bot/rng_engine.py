"""Gen 3 Linear Congruential RNG engine and Method 1 Pokemon generator.

LCRNG: seed = (seed * 0x41C64E6D + 0x6073) & 0xFFFFFFFF
Reverse: seed = (seed * 0xEEB9EB65 + 0x0A3561A1) & 0xFFFFFFFF

Method 1 Static:
  Call 1-2 → PID (low 16 bits, then high 16 bits)
  Call 3-4 → IVs (HP/Atk/Def from call 3, SpA/SpD/Spe from call 4)
"""

from __future__ import annotations

MULT = 0x41C64E6D
ADD = 0x6073
MASK = 0xFFFFFFFF

REV_MULT = 0xEEB9EB65
REV_ADD = 0x0A3561A1

# Nature names indexed by PID % 25
NATURES = [
    "Hardy", "Lonely", "Brave", "Adamant", "Naughty",
    "Bold", "Docile", "Relaxed", "Impish", "Lax",
    "Timid", "Hasty", "Serious", "Jolly", "Naive",
    "Modest", "Mild", "Quiet", "Bashful", "Rash",
    "Calm", "Gentle", "Sassy", "Careful", "Quirky",
]

# Stat modifier table: [nature_id] -> (boosted_stat, lowered_stat) or None if neutral
# Stats: 0=HP (never modified), 1=Atk, 2=Def, 3=Spe, 4=SpA, 5=SpD
NATURE_MODIFIERS: dict[int, tuple[int, int]] = {}
_stats = [1, 2, 3, 4, 5]  # Atk, Def, Spe, SpA, SpD
for _i in range(25):
    _up = _i // 5
    _down = _i % 5
    if _up != _down:
        NATURE_MODIFIERS[_i] = (_stats[_up], _stats[_down])

# Gender thresholds for Gen 3 (PID & 0xFF compared against threshold)
GENDER_THRESHOLDS = {
    "1:1": 127,    # 50% male / 50% female
    "3:1": 63,     # 75% male / 25% female
    "1:3": 191,    # 25% male / 75% female
    "7:1": 31,     # 87.5% male / 12.5% female
    "genderless": -1,
    "male_only": 0,
    "female_only": 254,
}

# Jump table for LCRNG advance by 2^i steps (used for distance calculation)
# Each entry is (multiplier, increment) for advancing 2^i steps at once
JUMP_TABLE: list[tuple[int, int]] = []

def _build_jump_table():
    m, a = MULT, ADD
    for _ in range(32):
        JUMP_TABLE.append((m & MASK, a & MASK))
        a = ((m + 1) * a) & MASK
        m = (m * m) & MASK

_build_jump_table()


def advance(seed: int) -> int:
    """Advance LCRNG by one step."""
    return (seed * MULT + ADD) & MASK


def reverse(seed: int) -> int:
    """Reverse LCRNG by one step."""
    return (seed * REV_MULT + REV_ADD) & MASK


def advance_n(seed: int, n: int) -> int:
    """Advance LCRNG by n steps using jump table (O(log n))."""
    for i in range(32):
        if n & (1 << i):
            m, a = JUMP_TABLE[i]
            seed = (seed * m + a) & MASK
    return seed


def high16(seed: int) -> int:
    """Extract upper 16 bits of a 32-bit value."""
    return (seed >> 16) & 0xFFFF


def distance(seed_a: int, seed_b: int) -> int | None:
    """Calculate the number of advances from seed_a to seed_b.

    Uses baby-step giant-step on the LCRNG. Returns None if
    seed_b is not reachable from seed_a within 2^32 steps (shouldn't happen
    for same-LCRNG seeds, but protects against bugs).
    """
    # Baby steps: build table of (seed_a advanced by j) for j in 0..65535
    baby_size = 1 << 16
    baby = {}
    s = seed_a
    for j in range(baby_size):
        baby[s] = j
        s = advance(s)

    # Giant step multiplier: advance by baby_size steps
    giant_mult, giant_add = JUMP_TABLE[16]  # 2^16 steps

    # Giant steps: check seed_b stepped back by i*baby_size
    # Equivalent: advance seed_b by -i*baby_size, check if in baby table
    # But easier: advance a "probe" from seed_b and check baby table
    # Actually: we want advance_n(seed_a, j + i*baby_size) == seed_b
    # Rearranging: advance_n(seed_a, j) == reverse_n(seed_b, i*baby_size)
    # So we reverse seed_b by giant steps and look up in baby table.
    s = seed_b
    rev_giant_mult, rev_giant_add = _reverse_jump(giant_mult, giant_add)
    for i in range(baby_size):
        if s in baby:
            return i * baby_size + baby[s]
        s = (s * rev_giant_mult + rev_giant_add) & MASK

    return None


def _reverse_jump(mult: int, add: int) -> tuple[int, int]:
    """Compute the reverse of a jump (mult, add) pair."""
    # Reverse multiplier via modular inverse
    rev_m = pow(mult, -1, 1 << 32) & MASK
    rev_a = (-(rev_m * add)) & MASK
    return rev_m, rev_a


def method1_pokemon(seed: int, tid: int, sid: int) -> dict:
    """Generate a Method 1 Pokemon from the given seed state.

    The seed should be the state BEFORE the first PID call.
    Returns dict with pid, nature, ability, gender_value, shiny, ivs, etc.
    """
    # Call 1: PID low
    seed = advance(seed)
    pid_low = high16(seed)

    # Call 2: PID high
    seed = advance(seed)
    pid_high = high16(seed)

    pid = (pid_high << 16) | pid_low

    # Call 3: IVs part 1 (HP, Atk, Def)
    seed = advance(seed)
    iv1 = high16(seed)
    hp_iv = iv1 & 0x1F
    atk_iv = (iv1 >> 5) & 0x1F
    def_iv = (iv1 >> 10) & 0x1F

    # Call 4: IVs part 2 (Spe, SpA, SpD)
    seed = advance(seed)
    iv2 = high16(seed)
    spe_iv = iv2 & 0x1F
    spa_iv = (iv2 >> 5) & 0x1F
    spd_iv = (iv2 >> 10) & 0x1F

    nature_id = pid % 25
    ability = pid & 1
    gender_value = pid & 0xFF

    # Shiny check: (TID ^ SID ^ PID_high ^ PID_low) < 8
    shiny_value = tid ^ sid ^ pid_high ^ pid_low
    shiny = shiny_value < 8
    square = shiny_value == 0
    star = shiny and not square

    return {
        "seed": seed & MASK,
        "pid": pid,
        "pid_hex": f"{pid:08X}",
        "nature": NATURES[nature_id],
        "nature_id": nature_id,
        "ability": ability,
        "gender_value": gender_value,
        "shiny": shiny,
        "square": square,
        "star": star,
        "shiny_value": shiny_value,
        "ivs": {
            "hp": hp_iv,
            "atk": atk_iv,
            "def": def_iv,
            "spe": spe_iv,
            "spa": spa_iv,
            "spd": spd_iv,
        },
        "iv_sum": hp_iv + atk_iv + def_iv + spe_iv + spa_iv + spd_iv,
    }


def gender_from_pid(pid: int, ratio: str) -> str:
    """Determine gender from PID and gender ratio string."""
    if ratio == "genderless":
        return "Genderless"
    if ratio == "male_only":
        return "Male"
    if ratio == "female_only":
        return "Female"
    threshold = GENDER_THRESHOLDS.get(ratio, 127)
    return "Male" if (pid & 0xFF) >= threshold else "Female"


def hidden_power_type(ivs: dict) -> str:
    """Calculate Hidden Power type from IVs."""
    types = [
        "Fighting", "Flying", "Poison", "Ground", "Rock", "Bug",
        "Ghost", "Steel", "Fire", "Water", "Grass", "Electric",
        "Psychic", "Ice", "Dragon", "Dark",
    ]
    hp = ivs["hp"] & 1
    atk = ivs["atk"] & 1
    df = ivs["def"] & 1
    spe = ivs["spe"] & 1
    spa = ivs["spa"] & 1
    spd = ivs["spd"] & 1
    val = (hp | (atk << 1) | (df << 2) | (spe << 3) | (spa << 4) | (spd << 5)) * 15 // 63
    return types[val]


def hidden_power_power(ivs: dict) -> int:
    """Calculate Hidden Power base power from IVs (Gen 3)."""
    hp = (ivs["hp"] >> 1) & 1
    atk = (ivs["atk"] >> 1) & 1
    df = (ivs["def"] >> 1) & 1
    spe = (ivs["spe"] >> 1) & 1
    spa = (ivs["spa"] >> 1) & 1
    spd = (ivs["spd"] >> 1) & 1
    return (hp | (atk << 1) | (df << 2) | (spe << 3) | (spa << 4) | (spd << 5)) * 40 // 63 + 30


def generate_pokemon_at_advances(
    initial_seed: int,
    tid: int,
    sid: int,
    advances_list: list[int],
) -> list[dict]:
    """Generate Method 1 Pokemon at specific advance counts from initial_seed.

    Each advance count means: advance the seed that many times from initial_seed,
    then generate Method 1 from that state.
    """
    results = []
    for adv in advances_list:
        seed_at_advance = advance_n(initial_seed, adv)
        pkmn = method1_pokemon(seed_at_advance, tid, sid)
        pkmn["advance"] = adv
        pkmn["initial_seed"] = initial_seed
        results.append(pkmn)
    return results


def search_shinies_in_range(
    initial_seed: int,
    tid: int,
    sid: int,
    min_advance: int,
    max_advance: int,
) -> list[dict]:
    """Search for shiny Pokemon in a range of advances."""
    results = []
    seed = advance_n(initial_seed, min_advance)
    for adv in range(min_advance, max_advance + 1):
        pkmn = method1_pokemon(seed, tid, sid)
        pkmn["advance"] = adv
        pkmn["initial_seed"] = initial_seed
        if pkmn["shiny"]:
            results.append(pkmn)
        seed = advance(seed)
    return results


def count_shinies_in_range(
    initial_seed: int,
    tid: int,
    sid: int,
    min_advance: int,
    max_advance: int,
) -> int:
    """Fast shiny count — no dict creation, just PID math.

    For each advance, we generate PID from 2 LCRNG calls and check shiny.
    The seed before each advance is the initial_seed advanced by `adv` steps.
    """
    count = 0
    seed = advance_n(initial_seed, min_advance)
    _mult = MULT
    _add = ADD
    _mask = MASK
    for _ in range(max_advance - min_advance + 1):
        # Generate PID from seed (without modifying the loop seed)
        s1 = (seed * _mult + _add) & _mask
        pid_low = (s1 >> 16) & 0xFFFF
        s2 = (s1 * _mult + _add) & _mask
        pid_high = (s2 >> 16) & 0xFFFF
        if (tid ^ sid ^ pid_high ^ pid_low) < 8:
            count += 1
        # Advance loop seed by 1
        seed = (seed * _mult + _add) & _mask
    return count


def generate_range(
    initial_seed: int,
    tid: int,
    sid: int,
    min_advance: int,
    max_advance: int,
    *,
    shiny_only: bool = False,
) -> list[dict]:
    """Generate all Method 1 Pokemon in an advance range."""
    results = []
    seed = advance_n(initial_seed, min_advance)
    for adv in range(min_advance, max_advance + 1):
        pkmn = method1_pokemon(seed, tid, sid)
        pkmn["advance"] = adv
        pkmn["initial_seed"] = initial_seed
        if not shiny_only or pkmn["shiny"]:
            results.append(pkmn)
        seed = advance(seed)
    return results
