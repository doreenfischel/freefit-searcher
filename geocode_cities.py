#!/usr/bin/env python3
"""Geocode unique city names to lat/lng using OpenStreetMap Nominatim."""

import json
import time
from pathlib import Path

import requests

OUTPUT_DIR = Path(__file__).parent / "output"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "FreeFit-Scraper/1.0 (personal project)",
})


def geocode_city(city_name: str) -> tuple[float, float] | None:
    """Geocode an Israeli city name to (lat, lng)."""
    resp = SESSION.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": f"{city_name}, ישראל", "format": "json", "limit": 1},
        timeout=10,
    )
    results = resp.json()
    if results:
        return float(results[0]["lat"]), float(results[0]["lon"])
    # Retry without Israel suffix
    resp = SESSION.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": city_name, "format": "json", "limit": 1, "countrycodes": "il"},
        timeout=10,
    )
    results = resp.json()
    if results:
        return float(results[0]["lat"]), float(results[0]["lon"])
    return None


def main():
    with open(OUTPUT_DIR / "clubs_detailed.json", encoding="utf-8") as f:
        clubs = json.load(f)

    # Extract unique cities from addresses
    cities = set()
    for c in clubs:
        addr = c.get("address", "")
        if "," in addr:
            city = addr.split(",")[-1].strip()
            if city:
                cities.add(city)

    print(f"Geocoding {len(cities)} unique cities...")

    # Load existing progress
    geo_file = OUTPUT_DIR / "city_coords.json"
    if geo_file.exists():
        with open(geo_file, encoding="utf-8") as f:
            coords = json.load(f)
        print(f"  Loaded {len(coords)} existing entries")
    else:
        coords = {}

    remaining = [c for c in sorted(cities) if c not in coords]
    print(f"  {len(remaining)} cities to geocode")

    for i, city in enumerate(remaining):
        print(f"  [{i+1}/{len(remaining)}] {city}...", end=" ")
        try:
            result = geocode_city(city)
            if result:
                coords[city] = {"lat": result[0], "lng": result[1]}
                print(f"OK ({result[0]:.4f}, {result[1]:.4f})")
            else:
                coords[city] = None
                print("NOT FOUND")
        except Exception as e:
            coords[city] = None
            print(f"ERROR: {e}")

        # Checkpoint every 50
        if (i + 1) % 50 == 0:
            with open(geo_file, "w", encoding="utf-8") as f:
                json.dump(coords, f, ensure_ascii=False, indent=2)

        time.sleep(1.1)  # Nominatim rate limit: 1 req/sec

    with open(geo_file, "w", encoding="utf-8") as f:
        json.dump(coords, f, ensure_ascii=False, indent=2)

    found = sum(1 for v in coords.values() if v is not None)
    print(f"\nDone. {found}/{len(coords)} cities geocoded.")
    print(f"Saved {geo_file}")


if __name__ == "__main__":
    main()
