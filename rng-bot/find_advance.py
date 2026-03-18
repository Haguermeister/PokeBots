#!/usr/bin/env python3
"""Find the actual advance hit based on manually observed stats."""
import rng_engine
import pokemon_data
import seed_data
import json

st = json.load(open("rng_state.json"))
tid, sid = st["tid"], st["sid"]
seed_hex = st["selected_seed"]
target_advance = st["selected_advance"]

seeds = seed_data.load_or_download_seeds()
entry = seed_data.get_seed_by_hex(seeds, seed_hex)
initial_seed = entry["initial_seed"]

NATURES = [
    "Hardy", "Lonely", "Brave", "Adamant", "Naughty",
    "Bold", "Docile", "Relaxed", "Impish", "Lax",
    "Timid", "Hasty", "Serious", "Jolly", "Naive",
    "Modest", "Mild", "Quiet", "Bashful", "Rash",
    "Calm", "Gentle", "Sassy", "Careful", "Quirky",
]

observed_nature = "Naive"
# Stats at Lv5: HP=19, Atk=10, Def=10, SpA=11, SpD=9, Spe=13

print(f"Target advance: {target_advance}")
print(f"Seed: 0x{seed_hex}, initial_seed: 0x{initial_seed:04X}")
print(f"TID: {tid}, SID: {sid}")
print(f"Looking for Naive male Charmander within +/-500 of target...")
print()

# Advance to start of search range
seed = initial_seed
start = max(0, target_advance - 500)
for _ in range(start):
    seed = rng_engine.advance(seed)

matches = []
for adv in range(start, target_advance + 500):
    # Method 1: seed → PID_lo → PID_hi → IV1 → IV2
    s1 = rng_engine.advance(seed)
    s2 = rng_engine.advance(s1)
    s3 = rng_engine.advance(s2)
    s4 = rng_engine.advance(s3)

    pid_lo = rng_engine.high16(s1)
    pid_hi = rng_engine.high16(s2)
    pid = (pid_hi << 16) | pid_lo

    iv1 = rng_engine.high16(s3)
    iv2 = rng_engine.high16(s4)

    nature_idx = pid % 25
    nature = NATURES[nature_idx]
    shiny_value = tid ^ sid ^ pid_hi ^ pid_lo
    is_shiny = shiny_value < 8
    gender_val = pid & 0xFF
    is_male = gender_val >= 31  # Charmander 87.5% male

    if nature == observed_nature and is_male:
        # Extract IVs
        hp_iv = iv1 & 0x1F
        atk_iv = (iv1 >> 5) & 0x1F
        def_iv = (iv1 >> 10) & 0x1F
        spe_iv = iv2 & 0x1F
        spa_iv = (iv2 >> 5) & 0x1F
        spd_iv = (iv2 >> 10) & 0x1F

        offset = adv - target_advance
        matches.append({
            "advance": adv,
            "offset": offset,
            "pid": pid,
            "shiny": is_shiny,
            "ivs": {"hp": hp_iv, "atk": atk_iv, "def": def_iv,
                    "spa": spa_iv, "spd": spd_iv, "spe": spe_iv},
        })

    seed = rng_engine.advance(seed)

for m in matches:
    ivs = m["ivs"]
    print(f"  Advance {m['advance']} (offset {m['offset']:+d}): "
          f"PID={m['pid']:08X} shiny={m['shiny']} "
          f"IVs: {ivs['hp']}/{ivs['atk']}/{ivs['def']}/{ivs['spa']}/{ivs['spd']}/{ivs['spe']}")

print(f"\nTotal Naive male matches: {len(matches)}")
