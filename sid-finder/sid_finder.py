#!/usr/bin/env python3
"""SID Finder — Web tool for finding your Secret ID from a random shiny.

Run: python3 sid_finder.py
Open: http://localhost:5002

Workflow:
  1. Enter your TID and the shiny Pokemon's species + nature
  2. Enter stats at level caught (and optionally after leveling up)
  3. Track EVs gained from battles on Route 1/2
  4. Tool calculates IVs → finds matching PIDs → computes possible SIDs
"""

import http.server
import json
import itertools
from pathlib import Path

import rng_math
import pokemon_data

PORT = 5002
BASE_DIR = Path(__file__).resolve().parent


def _load_html():
    with open(BASE_DIR / "index.html", "r", encoding="utf-8") as f:
        return f.read()


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _json(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, html):
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            self._html(_load_html())
        else:
            self.send_error(404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode() if length else "{}"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            self._json({"error": "Invalid JSON"}, 400)
            return

        path = self.path
        try:
            if path == "/api/reverse_ivs":
                self._json(api_reverse_ivs(data))
            elif path == "/api/find_sid":
                self._json(api_find_sid(data))
            elif path == "/api/calc_stats":
                self._json(api_calc_stats(data))
            elif path == "/api/pokemon_list":
                self._json(api_pokemon_list())
            elif path == "/api/ev_yields":
                self._json(api_ev_yields())
            else:
                self.send_error(404)
        except Exception as e:
            self._json({"error": str(e)}, 500)


def api_pokemon_list():
    """Return all available Pokemon with base stats."""
    result = {}
    for name, data in pokemon_data.POKEMON_DATA.items():
        result[name] = {
            "base": data["base"],
            "level": data["level"],
            "gender": data["gender"],
        }
    return {"pokemon": result, "natures": rng_math.NATURES}


def api_ev_yields():
    """Return EV yields and route encounter tables."""
    return {
        "yields": pokemon_data.EV_YIELDS,
        "routes": pokemon_data.ROUTE_ENCOUNTERS,
    }


def api_reverse_ivs(data):
    """Reverse-calculate IVs from observed stats at one or more levels."""
    pokemon_name = data.get("pokemon", "Pidgey")
    nature_name = data.get("nature", "Hardy")
    stat_rows = data.get("stat_rows", [])

    if pokemon_name not in pokemon_data.POKEMON_DATA:
        return {"error": f"Unknown Pokemon: {pokemon_name}"}
    if nature_name not in rng_math.NATURES:
        return {"error": f"Unknown nature: {nature_name}"}

    nature_id = rng_math.NATURES.index(nature_name)
    evs_at_levels = {}
    for row in stat_rows:
        level = row.get("level", 5)
        evs = row.get("evs", {"hp":0,"atk":0,"def":0,"spe":0,"spa":0,"spd":0})
        evs_at_levels[level] = evs

    possible = pokemon_data.narrow_ivs_with_levels(
        pokemon_name, stat_rows, nature_id, evs_at_levels,
    )

    # Check if IVs are fully determined (each stat has exactly 1 candidate)
    exact = all(len(v) == 1 for v in possible.values())
    exact_ivs = None
    if exact:
        exact_ivs = {k: v[0] for k, v in possible.items()}

    return {
        "possible_ivs": possible,
        "exact": exact,
        "exact_ivs": exact_ivs,
        "pokemon": pokemon_name,
        "nature": nature_name,
    }


def api_find_sid(data):
    """Full SID search: IVs + nature + TID → SID candidates."""
    tid = int(data.get("tid", 0)) & 0xFFFF
    ivs = data.get("ivs")
    nature_name = data.get("nature", "Hardy")
    gender = data.get("gender")

    if not ivs or not all(k in ivs for k in ["hp","atk","def","spe","spa","spd"]):
        return {"error": "Need exact IVs for all 6 stats"}

    # Validate IVs are single values
    for k, v in ivs.items():
        if not isinstance(v, int) or v < 0 or v > 31:
            return {"error": f"Invalid IV for {k}: {v}"}

    results = rng_math.find_sid_from_shiny_pokemon(tid, ivs, nature_name)

    # Filter by gender if provided
    if gender:
        threshold = rng_math.GENDER_THRESHOLDS.get(data.get("gender_ratio", "1:1"), 127)
        if gender.lower() == "male":
            results = [r for r in results if r["gender_value"] >= threshold]
        elif gender.lower() == "female":
            results = [r for r in results if r["gender_value"] < threshold]

    # Collect unique SIDs across all matching PIDs
    all_sids = set()
    for r in results:
        all_sids.update(r["sids"])

    return {
        "tid": tid,
        "pid_candidates": len(results),
        "results": results[:50],  # Limit to avoid huge responses
        "unique_sids": sorted(all_sids),
        "sid_count": len(all_sids),
    }


def api_calc_stats(data):
    """Calculate stats for given IVs, EVs, nature, level."""
    pokemon_name = data.get("pokemon", "Pidgey")
    ivs = data.get("ivs", {"hp":0,"atk":0,"def":0,"spe":0,"spa":0,"spd":0})
    evs = data.get("evs", {"hp":0,"atk":0,"def":0,"spe":0,"spa":0,"spd":0})
    level = int(data.get("level", 5))
    nature_name = data.get("nature", "Hardy")

    if pokemon_name not in pokemon_data.POKEMON_DATA:
        return {"error": f"Unknown Pokemon: {pokemon_name}"}

    nature_id = rng_math.NATURES.index(nature_name) if nature_name in rng_math.NATURES else 0
    stats = pokemon_data.calc_all_stats(pokemon_name, ivs, level, evs, nature_id)
    return {"stats": stats}


if __name__ == "__main__":
    server = http.server.HTTPServer(("0.0.0.0", PORT), Handler)
    server.allow_reuse_address = True
    print(f"SID Finder running at http://localhost:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
        print("\nShutdown.")
