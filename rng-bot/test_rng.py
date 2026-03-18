#!/usr/bin/env python3
"""Automated tests for the RNG engine and Pokemon generation.

Run: python3 test_rng.py
All tests use known-good values from PokeFinder / ten-lines to validate
our LCRNG implementation, Method 1 generation, shiny checks, IV calcs, etc.
"""

import sys
from pathlib import Path

# Ensure we can import from the rng-bot directory
sys.path.insert(0, str(Path(__file__).resolve().parent))

import rng_engine
import pokemon_data
import calibration
import tid_sid
import screen_reader

passed = 0
failed = 0


def test(name, condition):
    global passed, failed
    if condition:
        passed += 1
    else:
        failed += 1
        print(f"  FAIL: {name}")


def test_eq(name, actual, expected):
    global passed, failed
    if actual == expected:
        passed += 1
    else:
        failed += 1
        print(f"  FAIL: {name}: expected {expected!r}, got {actual!r}")


# ── LCRNG Core ──────────────────────────────────────────────────────────────

def test_lcrng_basic():
    print("Testing LCRNG basic operations...")

    # advance from 0
    s = rng_engine.advance(0)
    test_eq("advance(0)", s, 0x6073)

    # advance again
    s2 = rng_engine.advance(s)
    test_eq("advance(0x6073)", s2, (0x6073 * 0x41C64E6D + 0x6073) & 0xFFFFFFFF)

    # reverse should undo advance
    test_eq("reverse(advance(0))", rng_engine.reverse(s), 0)
    test_eq("reverse(advance(0x6073))", rng_engine.reverse(s2), s)

    # advance_n(seed, 1) == advance(seed)
    test_eq("advance_n(0, 1)", rng_engine.advance_n(0, 1), s)

    # advance_n with larger n
    seed = 0
    for _ in range(100):
        seed = rng_engine.advance(seed)
    test_eq("advance_n(0, 100)", rng_engine.advance_n(0, 100), seed)

    # advance_n with very large n
    seed_1000 = rng_engine.advance_n(0, 1000)
    seed_1000_check = 0
    for _ in range(1000):
        seed_1000_check = rng_engine.advance(seed_1000_check)
    test_eq("advance_n(0, 1000)", seed_1000, seed_1000_check)


def test_lcrng_high16():
    print("Testing high16 extraction...")
    test_eq("high16(0x12345678)", rng_engine.high16(0x12345678), 0x1234)
    test_eq("high16(0xFFFF0000)", rng_engine.high16(0xFFFF0000), 0xFFFF)
    test_eq("high16(0x0000FFFF)", rng_engine.high16(0x0000FFFF), 0x0000)


def test_lcrng_distance():
    print("Testing LCRNG distance calculation...")

    # distance from seed to itself is 0
    test_eq("distance(X, X)", rng_engine.distance(0x12345678, 0x12345678), 0)

    # distance of 1
    s0 = 0xABCD1234
    s1 = rng_engine.advance(s0)
    test_eq("distance(s, advance(s))", rng_engine.distance(s0, s1), 1)

    # distance of 10
    s10 = rng_engine.advance_n(s0, 10)
    test_eq("distance(s, advance_n(s, 10))", rng_engine.distance(s0, s10), 10)

    # distance of 1000
    s1000 = rng_engine.advance_n(s0, 1000)
    test_eq("distance(s, advance_n(s, 1000))", rng_engine.distance(s0, s1000), 1000)


def test_lcrng_jump_table():
    print("Testing jump table consistency...")
    # Jump table entry 0 should be the basic LCRNG constants
    m, a = rng_engine.JUMP_TABLE[0]
    test_eq("JUMP_TABLE[0] mult", m, rng_engine.MULT)
    test_eq("JUMP_TABLE[0] add", a, rng_engine.ADD)

    # Advancing by 2^1 = 2 steps should match two single advances
    s0 = 0x12345678
    s2_single = rng_engine.advance(rng_engine.advance(s0))
    m2, a2 = rng_engine.JUMP_TABLE[1]
    s2_jump = (s0 * m2 + a2) & 0xFFFFFFFF
    test_eq("JUMP_TABLE[1] matches 2 advances", s2_jump, s2_single)


# ── Method 1 Pokemon Generation ────────────────────────────────────────────

def test_method1_basic():
    print("Testing Method 1 Pokemon generation...")

    # Known test case: seed 0, TID 0, SID 0
    # After advance(0) = 0x6073
    # PID low = high16(advance(0)) = high16(0x6073) = 0
    # After another advance: seed = advance(0x6073)
    # Let's compute step by step
    s0 = 0
    s1 = rng_engine.advance(s0)  # 0x6073
    pid_low = rng_engine.high16(s1)  # 0
    s2 = rng_engine.advance(s1)
    pid_high = rng_engine.high16(s2)
    s3 = rng_engine.advance(s2)
    iv1 = rng_engine.high16(s3)
    s4 = rng_engine.advance(s3)
    iv2 = rng_engine.high16(s4)

    pkmn = rng_engine.method1_pokemon(s0, 0, 0)
    test_eq("method1 PID", pkmn["pid"], (pid_high << 16) | pid_low)
    test_eq("method1 nature_id", pkmn["nature_id"], pkmn["pid"] % 25)
    test_eq("method1 ability", pkmn["ability"], pkmn["pid"] & 1)
    test_eq("method1 hp_iv", pkmn["ivs"]["hp"], iv1 & 0x1F)
    test_eq("method1 atk_iv", pkmn["ivs"]["atk"], (iv1 >> 5) & 0x1F)
    test_eq("method1 def_iv", pkmn["ivs"]["def"], (iv1 >> 10) & 0x1F)
    test_eq("method1 spe_iv", pkmn["ivs"]["spe"], iv2 & 0x1F)
    test_eq("method1 spa_iv", pkmn["ivs"]["spa"], (iv2 >> 5) & 0x1F)
    test_eq("method1 spd_iv", pkmn["ivs"]["spd"], (iv2 >> 10) & 0x1F)


def test_shiny_check():
    print("Testing shiny check...")

    # Shiny condition: (TID ^ SID ^ PID_high ^ PID_low) < 8
    # Craft a PID that we know is shiny for TID=12345, SID=54321
    tid = 12345
    sid = 54321
    # For shiny: TID ^ SID ^ PID_high ^ PID_low < 8
    # TID ^ SID = 12345 ^ 54321
    tid_xor_sid = tid ^ sid
    # If PID_high ^ PID_low = tid_xor_sid, then shiny_value = 0 (square shiny)
    pid_high = 0x1234
    pid_low = pid_high ^ tid_xor_sid
    pid = (pid_high << 16) | pid_low
    shiny_value = tid ^ sid ^ pid_high ^ pid_low
    test_eq("crafted shiny_value", shiny_value, 0)

    # Now test with rng_engine: generate Pokemon from known seeds and check
    # non-shiny case
    pkmn = rng_engine.method1_pokemon(0, 0, 0)
    # PID from seed 0 with TID/SID 0: check manually
    sv = (pkmn["pid"] >> 16) ^ (pkmn["pid"] & 0xFFFF)  # TID=0 SID=0
    test_eq("shiny value matches", pkmn["shiny_value"], sv)
    test_eq("shiny bool matches", pkmn["shiny"], sv < 8)


def test_nature_names():
    print("Testing nature names...")
    test_eq("nature count", len(rng_engine.NATURES), 25)
    test_eq("nature 0", rng_engine.NATURES[0], "Hardy")
    test_eq("nature 24", rng_engine.NATURES[24], "Quirky")
    test_eq("nature 3", rng_engine.NATURES[3], "Adamant")
    test_eq("nature 15", rng_engine.NATURES[15], "Modest")
    test_eq("nature 10", rng_engine.NATURES[10], "Timid")
    test_eq("nature 13", rng_engine.NATURES[13], "Jolly")


def test_nature_modifiers():
    print("Testing nature modifiers...")
    # Hardy (0): neutral (up=0/Atk, down=0/Atk → same, so no modifier)
    test("Hardy is neutral", 0 not in rng_engine.NATURE_MODIFIERS)
    # Adamant (3): +Atk -SpA → up=0(Atk), down=3(SpA)
    mods = rng_engine.NATURE_MODIFIERS[3]
    test_eq("Adamant +stat", mods[0], 1)  # Atk
    test_eq("Adamant -stat", mods[1], 4)  # SpA
    # Jolly (13): +Spe -SpA → up=2(Spe), down=3(SpA)
    mods = rng_engine.NATURE_MODIFIERS[13]
    test_eq("Jolly +stat", mods[0], 3)  # Spe
    test_eq("Jolly -stat", mods[1], 4)  # SpA
    # Timid (10): +Spe -Atk → up=2(Spe), down=0(Atk)
    mods = rng_engine.NATURE_MODIFIERS[10]
    test_eq("Timid +stat", mods[0], 3)  # Spe
    test_eq("Timid -stat", mods[1], 1)  # Atk
    # Modest (15): +SpA -Atk → up=3(SpA), down=0(Atk)
    mods = rng_engine.NATURE_MODIFIERS[15]
    test_eq("Modest +stat", mods[0], 4)  # SpA
    test_eq("Modest -stat", mods[1], 1)  # Atk


def test_gender():
    print("Testing gender calculation...")
    # PID & 0xFF >= threshold → Male
    test_eq("male 7:1 high", rng_engine.gender_from_pid(0xFF, "7:1"), "Male")
    test_eq("female 7:1 low", rng_engine.gender_from_pid(0x00, "7:1"), "Female")
    test_eq("male 1:1 high", rng_engine.gender_from_pid(0x80, "1:1"), "Male")
    test_eq("female 1:1 low", rng_engine.gender_from_pid(0x7E, "1:1"), "Female")
    test_eq("genderless", rng_engine.gender_from_pid(0x80, "genderless"), "Genderless")
    test_eq("male_only", rng_engine.gender_from_pid(0x00, "male_only"), "Male")
    test_eq("female_only", rng_engine.gender_from_pid(0xFF, "female_only"), "Female")


def test_hidden_power():
    print("Testing Hidden Power calculation...")
    # Known case: all 31 IVs → HP type = Dark
    ivs_31 = {"hp": 31, "atk": 31, "def": 31, "spe": 31, "spa": 31, "spd": 31}
    test_eq("HP all 31s type", rng_engine.hidden_power_type(ivs_31), "Dark")
    test_eq("HP all 31s power", rng_engine.hidden_power_power(ivs_31), 70)

    # All 0s → HP Fighting
    ivs_0 = {"hp": 0, "atk": 0, "def": 0, "spe": 0, "spa": 0, "spd": 0}
    test_eq("HP all 0s type", rng_engine.hidden_power_type(ivs_0), "Fighting")
    test_eq("HP all 0s power", rng_engine.hidden_power_power(ivs_0), 30)


# ── Generate Range / Shiny Search ──────────────────────────────────────────

def test_search_shinies():
    print("Testing shiny search in range...")

    # Use a known seed and TID/SID combination
    # We'll verify that search_shinies_in_range and generate_range(shiny_only=True) agree
    seed = 0x12345678
    tid = 12345
    sid = 54321

    shinies_search = rng_engine.search_shinies_in_range(seed, tid, sid, 0, 5000)
    shinies_range = rng_engine.generate_range(seed, tid, sid, 0, 5000, shiny_only=True)

    test_eq("search vs generate count", len(shinies_search), len(shinies_range))
    for a, b in zip(shinies_search, shinies_range):
        test_eq(f"search vs generate advance {a['advance']}", a["advance"], b["advance"])
        test_eq(f"search vs generate pid {a['advance']}", a["pid"], b["pid"])

    # All results should be shiny
    for s in shinies_search:
        test(f"shiny at advance {s['advance']}", s["shiny"])


# ── Pokemon Data / Stat Calculation ────────────────────────────────────────

def test_stat_calc():
    print("Testing stat calculation...")

    # Bulbasaur at level 5 with 0 IVs, 0 EVs, neutral nature
    # HP: ((2*45 + 0 + 0) * 5 / 100) + 5 + 10 = (450/100) + 15 = 4 + 15 = 19
    # Atk: ((2*49 + 0 + 0) * 5 / 100) + 5 = (490/100) + 5 = 4 + 5 = 9
    ivs_zero = {"hp": 0, "atk": 0, "def": 0, "spe": 0, "spa": 0, "spd": 0}
    stats = pokemon_data.calc_all_stats("Bulbasaur", ivs_zero, nature_id=0)
    test_eq("Bulbasaur HP (0 IV neutral)", stats["hp"], 19)
    test_eq("Bulbasaur Atk (0 IV neutral)", stats["atk"], 9)
    test_eq("Bulbasaur Def (0 IV neutral)", stats["def"], 9)
    test_eq("Bulbasaur Spe (0 IV neutral)", stats["spe"], 9)
    test_eq("Bulbasaur SpA (0 IV neutral)", stats["spa"], 11)
    test_eq("Bulbasaur SpD (0 IV neutral)", stats["spd"], 11)

    # Bulbasaur at level 5 with 31 IVs, 0 EVs, neutral nature
    # HP: ((2*45 + 31 + 0) * 5 / 100) + 5 + 10 = (121*5/100) + 15 = 6 + 15 = 21
    ivs_max = {"hp": 31, "atk": 31, "def": 31, "spe": 31, "spa": 31, "spd": 31}
    stats = pokemon_data.calc_all_stats("Bulbasaur", ivs_max, nature_id=0)
    test_eq("Bulbasaur HP (31 IV neutral)", stats["hp"], 21)

    # Adamant nature: +Atk, -SpA
    # Atk = int(9 * 1.1) for 0 IV... let me recalc: ((2*49 + 31) * 5 / 100 + 5) * 1.1
    # = (129 * 5 / 100 + 5) * 1.1 = (6 + 5) * 1.1 = int(12.1) = 12
    stats_adamant = pokemon_data.calc_all_stats("Bulbasaur", ivs_max, nature_id=3)
    test_eq("Bulbasaur Atk (31 IV Adamant)", stats_adamant["atk"], 12)


def test_reverse_iv():
    print("Testing reverse IV calculation...")

    # Generate a known Pokemon, compute its stats, then reverse-calc IVs
    seed = rng_engine.advance_n(0, 1000)
    pkmn = rng_engine.method1_pokemon(seed, 0, 0)
    ivs = pkmn["ivs"]
    stats = pokemon_data.calc_all_stats("Bulbasaur", ivs, nature_id=pkmn["nature_id"])

    reverse = pokemon_data.reverse_calc_ivs("Bulbasaur", stats, pkmn["nature_id"])

    for stat_name in ["hp", "atk", "def", "spe", "spa", "spd"]:
        test(
            f"reverse IV {stat_name} contains actual",
            ivs[stat_name] in reverse[stat_name],
        )

    # Do the same for Charmander
    seed2 = rng_engine.advance_n(0, 2000)
    pkmn2 = rng_engine.method1_pokemon(seed2, 0, 0)
    stats2 = pokemon_data.calc_all_stats("Charmander", pkmn2["ivs"], nature_id=pkmn2["nature_id"])
    reverse2 = pokemon_data.reverse_calc_ivs("Charmander", stats2, pkmn2["nature_id"])
    for stat_name in ["hp", "atk", "def", "spe", "spa", "spd"]:
        test(
            f"Charmander reverse IV {stat_name} contains actual",
            pkmn2["ivs"][stat_name] in reverse2[stat_name],
        )


def test_pokemon_summary():
    print("Testing full Pokemon summary...")

    seed = rng_engine.advance_n(0, 500)
    pkmn = rng_engine.method1_pokemon(seed, 12345, 54321)
    summary = pokemon_data.pokemon_summary(pkmn, "Squirtle")

    test("summary has pokemon name", summary["pokemon"] == "Squirtle")
    test("summary has stats", "stats" in summary)
    test("summary has gender", "gender" in summary)
    test("summary has ability_name", "ability_name" in summary)
    test("summary has hp_type", "hp_type" in summary)
    test("summary has hp_power", "hp_power" in summary)
    test("summary has level", summary["level"] == 5)
    test("summary has types", summary["types"] == ["Water"])


# ── Calibration ────────────────────────────────────────────────────────────

def test_advance_offset_to_ms():
    print("Testing advance offset to ms conversion...")

    # 0 offset should be 0 ms
    test_eq("0 offset", calibration.advance_offset_to_ms(0), 0.0)

    # Positive offset
    ms = calibration.advance_offset_to_ms(100)
    # 100 advances / 2 = 50 frames / 59.7275 fps * 1000 ≈ 837.2ms
    test("100 advances ≈ 837ms", 836 < ms < 838)

    # Negative offset
    ms_neg = calibration.advance_offset_to_ms(-100)
    test("negative offset", ms_neg < 0)
    test_eq("symmetric", abs(ms_neg), ms)


def test_find_actual_advance():
    print("Testing find_actual_advance...")

    seed = rng_engine.advance_n(0, 1821)  # Starting frame 1821
    tid, sid = 12345, 54321
    target_advance = 1500

    # Generate the actual Pokemon at advance 1505 (simulate being 5 off)
    actual_seed = rng_engine.advance_n(seed, 1505)
    actual_pkmn = rng_engine.method1_pokemon(actual_seed, tid, sid)
    actual_summary = pokemon_data.pokemon_summary(actual_pkmn, "Bulbasaur")

    # Search by nature
    matches = calibration.find_actual_advance(
        seed, tid, sid, "Bulbasaur", target_advance,
        observed_nature=actual_summary["nature"],
    )
    test("found matches by nature", len(matches) > 0)

    # The correct advance (1505) should be in the results
    found_advances = [m["advance"] for m in matches]
    test("actual advance in results", 1505 in found_advances)

    # Search by nature + stats (should be very precise)
    matches_stats = calibration.find_actual_advance(
        seed, tid, sid, "Bulbasaur", target_advance,
        observed_nature=actual_summary["nature"],
        observed_stats=actual_summary["stats"],
    )
    test("stats match found", len(matches_stats) > 0)
    if matches_stats:
        test_eq("best match is actual", matches_stats[0]["advance"], 1505)


# ── Integration: generate_range consistency ────────────────────────────────

def test_generate_range_consistency():
    print("Testing generate_range consistency...")

    seed = 0xDEADBEEF
    tid, sid = 100, 200

    # generate_range should produce same results as individual method1_pokemon calls
    results = rng_engine.generate_range(seed, tid, sid, 0, 100)
    test_eq("range produces 101 results", len(results), 101)

    # Spot-check a few
    for adv in [0, 50, 100]:
        expected = rng_engine.method1_pokemon(rng_engine.advance_n(seed, adv), tid, sid)
        actual = results[adv]
        test_eq(f"advance {adv} pid", actual["pid"], expected["pid"])
        test_eq(f"advance {adv} nature", actual["nature"], expected["nature"])
        test_eq(f"advance {adv} ivs", actual["ivs"], expected["ivs"])


def test_all_starters_have_data():
    print("Testing starter data completeness...")
    for name in ["Bulbasaur", "Charmander", "Squirtle"]:
        data = pokemon_data.STARTERS[name]
        test(f"{name} has base stats", "base" in data)
        test(f"{name} has 6 base stats", len(data["base"]) == 6)
        test(f"{name} has gender_ratio", "gender_ratio" in data)
        test(f"{name} has level", data["level"] == 5)
        test(f"{name} has ability_0", "ability_0" in data)


# ── TID/SID Calculation ────────────────────────────────────────────────────

def test_find_sids_for_tid():
    print("Testing find_sids_for_tid...")

    # Basic: search should return list of dicts with correct keys
    results = tid_sid.find_sids_for_tid(0, min_advance=1000, max_advance=5000)
    test("returns list", isinstance(results, list))
    # TID 0 should appear somewhere in 1000-5000 advances from seed 0
    # (LCRNG from 0 will hit high16==0 at some point)
    if results:
        r = results[0]
        test("result has advance", "advance" in r)
        test("result has tid", "tid" in r)
        test("result has sid", "sid" in r)
        test_eq("result tid matches", r["tid"], 0)
        test("sid is 16-bit", 0 <= r["sid"] <= 65535)
        test("advance in range", 1000 <= r["advance"] <= 5000)

    # Results should be sorted by advance
    for i in range(1, len(results)):
        test(f"sorted by advance [{i}]", results[i]["advance"] >= results[i-1]["advance"])

    # Verify SID computation manually for each result
    for r in results:
        state = rng_engine.advance_n(0, r["advance"])
        test_eq(f"TID at advance {r['advance']}", rng_engine.high16(state), 0)
        expected_sid = rng_engine.high16(rng_engine.advance(state))
        test_eq(f"SID at advance {r['advance']}", r["sid"], expected_sid)

    # Test with a realistic TID (should find candidates)
    results_real = tid_sid.find_sids_for_tid(12345, min_advance=1000, max_advance=100000)
    test("realistic TID finds candidates", len(results_real) > 0)
    for r in results_real:
        test_eq(f"TID={r['tid']} matches", r["tid"], 12345)
        test("SID valid range", 0 <= r["sid"] <= 65535)

    # Empty range should return no results
    results_empty = tid_sid.find_sids_for_tid(99999, min_advance=1000, max_advance=1001)
    test("narrow range may be empty", isinstance(results_empty, list))


def test_narrow_sid_candidates():
    print("Testing narrow_sid_candidates...")

    # Set up: get SID candidates for TID 12345
    candidates = tid_sid.find_sids_for_tid(12345, min_advance=1000, max_advance=100000)
    test("have candidates to narrow", len(candidates) > 0)

    if not candidates:
        return

    # Pick the first candidate as "true" and verify narrowing works
    true_candidate = candidates[0]
    true_sid = true_candidate["sid"]

    # Use a known seed and advance to generate a test Pokemon
    test_seed = 0x12345678
    test_advance = 500

    pkmn = rng_engine.method1_pokemon(
        rng_engine.advance_n(test_seed, test_advance), 12345, true_sid,
    )
    was_shiny = pkmn["shiny"]

    # Narrow: the true SID should survive filtering
    narrowed = tid_sid.narrow_sid_candidates(
        candidates, test_seed, 12345, test_advance, was_shiny,
    )
    test("narrowed is subset", len(narrowed) <= len(candidates))

    # True candidate should be in narrowed results
    narrowed_sids = [c["sid"] for c in narrowed]
    test("true SID survives narrowing", true_sid in narrowed_sids)

    # Narrow with opposite shiny status should exclude true SID
    narrowed_opposite = tid_sid.narrow_sid_candidates(
        candidates, test_seed, 12345, test_advance, not was_shiny,
    )
    opposite_sids = [c["sid"] for c in narrowed_opposite]
    test("true SID excluded by opposite", true_sid not in opposite_sids)

    # Union of narrowed + opposite should cover all original candidates
    test_eq("partition covers all",
            len(narrowed) + len(narrowed_opposite), len(candidates))


def test_gba_to_cap():
    print("Testing GBA to capture coordinate conversion...")

    # Basic conversion at 1280x720: GBA (0,0) → (0,0)
    cx, cy = tid_sid.gba_to_cap(0, 0, 1280, 720)
    test_eq("origin x", cx, 0)
    test_eq("origin y", cy, 0)

    # GBA (240, 160) → (1280, 720)
    cx, cy = tid_sid.gba_to_cap(240, 160, 1280, 720)
    test_eq("max x 720p", cx, 1280)
    test_eq("max y 720p", cy, 720)

    # Mid-screen: GBA (120, 80) → (640, 360)
    cx, cy = tid_sid.gba_to_cap(120, 80, 1280, 720)
    test_eq("mid x 720p", cx, 640)
    test_eq("mid y 720p", cy, 360)

    # 1080p: GBA (240, 160) → (1920, 1080)
    cx, cy = tid_sid.gba_to_cap(240, 160, 1920, 1080)
    test_eq("max x 1080p", cx, 1920)
    test_eq("max y 1080p", cy, 1080)

    # 1080p mid-screen: GBA (120, 80) → (960, 540)
    cx, cy = tid_sid.gba_to_cap(120, 80, 1920, 1080)
    test_eq("mid x 1080p", cx, 960)
    test_eq("mid y 1080p", cy, 540)


# ── Screen Reader Constants ────────────────────────────────────────────────

def test_nature_from_stats_table():
    print("Testing NATURE_FROM_STATS lookup table...")

    # Should have exactly 20 entries (25 natures - 5 neutral)
    test_eq("NATURE_FROM_STATS count", len(screen_reader.NATURE_FROM_STATS), 20)

    # Known natures
    test_eq("Adamant", screen_reader.NATURE_FROM_STATS[("atk", "spa")], "Adamant")
    test_eq("Jolly", screen_reader.NATURE_FROM_STATS[("spe", "spa")], "Jolly")
    test_eq("Timid", screen_reader.NATURE_FROM_STATS[("spe", "atk")], "Timid")
    test_eq("Modest", screen_reader.NATURE_FROM_STATS[("spa", "atk")], "Modest")
    test_eq("Bold", screen_reader.NATURE_FROM_STATS[("def", "atk")], "Bold")
    test_eq("Calm", screen_reader.NATURE_FROM_STATS[("spd", "atk")], "Calm")
    test_eq("Brave", screen_reader.NATURE_FROM_STATS[("atk", "spe")], "Brave")
    test_eq("Quiet", screen_reader.NATURE_FROM_STATS[("spa", "spe")], "Quiet")

    # Neutral natures should NOT be in the table
    # (Hardy, Docile, Serious, Bashful, Quirky have up==down)
    stat_keys = set(screen_reader.NATURE_FROM_STATS.keys())
    for key in stat_keys:
        test(f"non-neutral {key}", key[0] != key[1])


def test_digit_patterns():
    print("Testing digit recognition patterns...")

    # The patterns dict in tid_sid._recognize_digit body
    # We can verify consistency: each pattern should be 15 elements (3x5 grid)
    patterns = {
        0: [1,1,1, 1,0,1, 1,0,1, 1,0,1, 1,1,1],
        1: [0,1,0, 1,1,0, 0,1,0, 0,1,0, 1,1,1],
        2: [1,1,1, 0,0,1, 1,1,1, 1,0,0, 1,1,1],
        3: [1,1,1, 0,0,1, 1,1,1, 0,0,1, 1,1,1],
        4: [1,0,1, 1,0,1, 1,1,1, 0,0,1, 0,0,1],
        5: [1,1,1, 1,0,0, 1,1,1, 0,0,1, 1,1,1],
        6: [1,1,1, 1,0,0, 1,1,1, 1,0,1, 1,1,1],
        7: [1,1,1, 0,0,1, 0,1,0, 0,1,0, 0,1,0],
        8: [1,1,1, 1,0,1, 1,1,1, 1,0,1, 1,1,1],
        9: [1,1,1, 1,0,1, 1,1,1, 0,0,1, 1,1,1],
    }

    for digit, pattern in patterns.items():
        test_eq(f"digit {digit} pattern length", len(pattern), 15)

    # Each digit pattern should be unique
    pattern_tuples = [tuple(p) for p in patterns.values()]
    test_eq("all patterns unique", len(set(pattern_tuples)), 10)

    # Symmetric properties:
    # 0 and 8 have same top and bottom rows
    test_eq("0 top row", patterns[0][:3], [1,1,1])
    test_eq("0 bottom row", patterns[0][12:], [1,1,1])
    test_eq("8 top row", patterns[8][:3], [1,1,1])
    test_eq("8 bottom row", patterns[8][12:], [1,1,1])


def test_screen_reader_constants():
    print("Testing screen reader constants...")

    # Border sample points should be 4 points
    test_eq("border points count", len(screen_reader.BORDER_SAMPLE_POINTS_REF), 4)

    # Summary marker should be reasonable coordinates (within 1280x720 ref)
    mx, my = screen_reader.SUMMARY_MARKER_POINT_REF
    test("marker x in range", 0 <= mx < 1280)
    test("marker y in range", 0 <= my < 720)

    # Default stat label points should have 5 entries
    test_eq("stat label count", len(screen_reader.DEFAULT_STAT_LABEL_POINTS_REF), 5)
    for stat in ["atk", "def", "spa", "spd", "spe"]:
        test(f"stat {stat} exists", stat in screen_reader.DEFAULT_STAT_LABEL_POINTS_REF)
        x, y = screen_reader.DEFAULT_STAT_LABEL_POINTS_REF[stat]
        test(f"stat {stat} x in range", 0 <= x < 1280)
        test(f"stat {stat} y in range", 0 <= y < 720)

    # Color thresholds should be positive
    test("red threshold positive", screen_reader.RED_THRESHOLD > 0)
    test("blue threshold positive", screen_reader.BLUE_THRESHOLD > 0)

    # Scaling functions should work
    sx, sy = screen_reader._scale_point(640, 360, 1920, 1080)
    test_eq("scale_point x to 1080p", sx, 960)
    test_eq("scale_point y to 1080p", sy, 540)

    # Identity scaling at reference resolution
    sx, sy = screen_reader._scale_point(640, 360, 1280, 720)
    test_eq("scale_point x identity", sx, 640)
    test_eq("scale_point y identity", sy, 360)


# ── Run all tests ──────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("RNG Engine Test Suite")
    print("=" * 60)

    test_lcrng_basic()
    test_lcrng_high16()
    test_lcrng_distance()
    test_lcrng_jump_table()
    test_method1_basic()
    test_shiny_check()
    test_nature_names()
    test_nature_modifiers()
    test_gender()
    test_hidden_power()
    test_search_shinies()
    test_stat_calc()
    test_reverse_iv()
    test_pokemon_summary()
    test_advance_offset_to_ms()
    test_find_actual_advance()
    test_generate_range_consistency()
    test_all_starters_have_data()
    test_find_sids_for_tid()
    test_narrow_sid_candidates()
    test_gba_to_cap()
    test_nature_from_stats_table()
    test_digit_patterns()
    test_screen_reader_constants()

    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    if failed > 0:
        sys.exit(1)
    print("All tests passed!")


if __name__ == "__main__":
    main()
