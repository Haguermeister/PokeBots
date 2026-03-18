#!/usr/bin/env python3
"""Search all 551 seeds for a shiny modest Charmander with 31 SpA IV."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import rng_engine
import seed_data

TID = 31735
SID = 65215
TARGET_NATURE = "Modest"  # nature_id = 15
TARGET_SPA_IV = 31
MAX_ADVANCE = 100000

seeds = seed_data.load_or_download_seeds()
print(f"Searching {len(seeds)} seeds for shiny Modest Charmander with 31 SpA...")

results = []
for entry in seeds:
    seed = entry["initial_seed"]
    shinies = rng_engine.search_shinies_in_range(seed, TID, SID, 0, MAX_ADVANCE)
    for s in shinies:
        if s["nature"] == TARGET_NATURE and s["ivs"]["spa"] == TARGET_SPA_IV:
            results.append({
                "seed_hex": entry.get("seed_hex", f"{seed:04X}"),
                "advance": s["advance"],
                "pid": f"{s['pid']:08X}",
                "nature": s["nature"],
                "ivs": s["ivs"],
                "shiny_value": s["shiny_value"],
                "time_ms": entry.get("time_ms", 0),
            })

results.sort(key=lambda r: r["advance"])

print(f"\nFound {len(results)} matches:\n")
for i, r in enumerate(results[:30]):
    ivs = r["ivs"]
    iv_str = f"HP:{ivs['hp']:2d} Atk:{ivs['atk']:2d} Def:{ivs['def']:2d} SpA:{ivs['spa']:2d} SpD:{ivs['spd']:2d} Spe:{ivs['spe']:2d}"
    print(f"  #{i+1}  Seed {r['seed_hex']}  Advance {r['advance']:6d}  PID {r['pid']}  {r['nature']:7s}  {iv_str}  SV={r['shiny_value']}  Timer={r['time_ms']}ms")
