#!/usr/bin/env python3
"""Geocode club addresses to lat/lng using OpenStreetMap Nominatim."""

import json
import time
from pathlib import Path

import requests

OUTPUT_DIR = Path(__file__).parent / "output"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "FreeFit-Scraper/1.0 (personal project)",
})


def geocode_address(address: str) -> tuple[float, float] | None:
    resp = SESSION.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": address + ", ישראל", "format": "json", "limit": 1},
        timeout=10,
    )
    results = resp.json()
    if results:
        return float(results[0]["lat"]), float(results[0]["lon"])
    # Retry with countrycodes filter
    resp = SESSION.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": address, "format": "json", "limit": 1, "countrycodes": "il"},
        timeout=10,
    )
    results = resp.json()
    if results:
        return float(results[0]["lat"]), float(results[0]["lon"])
    return None


def main():
    with open(OUTPUT_DIR / "clubs_detailed.json", encoding="utf-8") as f:
        clubs = json.load(f)

    # Load existing coords
    coords_file = OUTPUT_DIR / "address_coords.json"
    if coords_file.exists():
        with open(coords_file, encoding="utf-8") as f:
            coords = json.load(f)
    else:
        coords = {}

    # Collect unique addresses to geocode (Tel Aviv only for now)
    unique_addrs = {}
    for c in clubs:
        addr = c.get("address", "")
        if addr and "תל אביב" in addr and addr not in coords:
            unique_addrs[addr] = True

    remaining = sorted(unique_addrs.keys())
    print(f"Geocoding {len(remaining)} Tel Aviv addresses ({len(coords)} already cached)...")

    for i, addr in enumerate(remaining):
        print(f"  [{i+1}/{len(remaining)}] {addr}...", end=" ", flush=True)
        try:
            result = geocode_address(addr)
            if result:
                coords[addr] = [round(result[0], 6), round(result[1], 6)]
                print(f"OK")
            else:
                coords[addr] = None
                print("NOT FOUND")
        except Exception as e:
            coords[addr] = None
            print(f"ERROR: {e}")

        if (i + 1) % 50 == 0:
            with open(coords_file, "w", encoding="utf-8") as f:
                json.dump(coords, f, ensure_ascii=False)

        time.sleep(2)

    with open(coords_file, "w", encoding="utf-8") as f:
        json.dump(coords, f, ensure_ascii=False, indent=2)

    found = sum(1 for v in coords.values() if v is not None)
    print(f"\nDone. {found}/{len(coords)} addresses geocoded.")


if __name__ == "__main__":
    main()
