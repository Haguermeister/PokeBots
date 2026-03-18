#!/usr/bin/env python3
"""Filter advances by observed stats to find exact hit."""
import sys, math
sys.path.insert(0, '.')
from rng_engine import generate_range
from pokemon_data import STARTERS

# Charmander base stats
base = STARTERS["Charmander"]["base"]

# Observed: Naive male Lv5, HP=19 Atk=10 Def=10 SpA=11 SpD=9 Spe=13
# Naive: +Spe, -SpD
observed = {"hp": 19, "atk": 10, "def": 10, "spa": 11, "spd": 9, "spe": 13}

def calc_stat_lv5(base_stat, iv, nature_mult=1.0):
    val = ((2 * base_stat + iv) * 5) // 100 + 5
    return math.floor(val * nature_mult)

def calc_hp_lv5(base_hp, iv):
    return ((2 * base_hp + iv) * 5) // 100 + 5 + 10

# Naive nature multipliers
nature_mults = {"hp": 1.0, "atk": 1.0, "def": 1.0, "spa": 1.0, "spd": 0.9, "spe": 1.1}

# Find valid IV ranges for each stat
print("=== IV ranges from observed stats ===")
for stat_name in ["hp", "atk", "def", "spa", "spd", "spe"]:
    valid = []
    for iv in range(32):
        if stat_name == "hp":
            calc = calc_hp_lv5(base["hp"], iv)
        else:
            calc = calc_stat_lv5(base[stat_name], iv, nature_mults[stat_name])
        if calc == observed[stat_name]:
            valid.append(iv)
    if valid:
        print(f"  {stat_name}: base={base[stat_name]}, observed={observed[stat_name]}, valid IVs={valid[0]}-{valid[-1]} ({len(valid)} values)")
    else:
        print(f"  {stat_name}: base={base[stat_name]}, observed={observed[stat_name]}, NO VALID IVs!")

# Search advances using generate_range
target = 7946
tid = 31735
sid = 65215
seed = 0x49D1

print(f"\n=== Searching advances {target-500} to {target+500} ===")
pokemon_list = generate_range(seed, tid, sid, target - 500, target + 500)

matches = []
for pkmn in pokemon_list:
    if pkmn["nature"] != "Naive":
        continue
    # Charmander gender ratio 7:1 -> threshold 31: Male if gender_value >= 31
    if pkmn["gender_value"] < 31:
        continue
    
    ivs = pkmn["ivs"]
    all_match = True
    for stat_name in ["hp", "atk", "def", "spa", "spd", "spe"]:
        iv = ivs[stat_name]
        if stat_name == "hp":
            calc = calc_hp_lv5(base["hp"], iv)
        else:
            calc = calc_stat_lv5(base[stat_name], iv, nature_mults[stat_name])
        if calc != observed[stat_name]:
            all_match = False
            break
    
    if all_match:
        advance = pkmn["advance"]
        offset = advance - target
        print(f"  MATCH: advance {advance} (offset {offset:+d})")
        print(f"    IVs: HP={ivs['hp']} Atk={ivs['atk']} Def={ivs['def']} SpA={ivs['spa']} SpD={ivs['spd']} Spe={ivs['spe']}")
        print(f"    Shiny: {pkmn['shiny']}")
        print(f"    PID: {pkmn['pid']:08X}")
        matches.append((advance, offset))

if not matches:
    print("  No exact matches found in +/-500! Expanding to +/-2000...")
    pokemon_list2 = generate_range(seed, tid, sid, target - 2000, target + 2000)
    for pkmn in pokemon_list2:
        if pkmn["nature"] != "Naive":
            continue
        if pkmn["gender_value"] < 31:
            continue
        ivs = pkmn["ivs"]
        all_match = True
        for stat_name in ["hp", "atk", "def", "spa", "spd", "spe"]:
            iv = ivs[stat_name]
            if stat_name == "hp":
                calc = calc_hp_lv5(base["hp"], iv)
            else:
                calc = calc_stat_lv5(base[stat_name], iv, nature_mults[stat_name])
            if calc != observed[stat_name]:
                all_match = False
                break
        if all_match:
            advance = pkmn["advance"]
            offset = advance - target
            print(f"  MATCH: advance {advance} (offset {offset:+d})")
            print(f"    IVs: HP={ivs['hp']} Atk={ivs['atk']} Def={ivs['def']} SpA={ivs['spa']} SpD={ivs['spd']} Spe={ivs['spe']}")
            print(f"    Shiny: {pkmn['shiny']}")
            matches.append((advance, offset))

print(f"\nTotal matches: {len(matches)}")
if matches:
    fps = 16777216 / 280896
    ms_per_advance = 1000.0 / fps
    print(f"\nCalibration: target was {target}")
    for adv, off in matches:
        ms_offset = off * ms_per_advance
        print(f"  Advance {adv}: offset {off:+d} = {ms_offset:+.1f}ms")
