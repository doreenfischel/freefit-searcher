#!/usr/bin/env python3
"""Build the JS data files for the search page, with city name normalization."""

import json
import re
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "output"

# Explicit merges: variant -> canonical name
CITY_ALIASES = {
    "תל-אביב": "תל אביב",
    "תלאביב": "תל אביב",
    "ת\"א": "תל אביב",
    "ת\u05f4א": "תל אביב",
    "תל אביב יפו": "תל אביב",
    "תל אביב-יפו": "תל אביב",
    "תל אביב -יפו": "תל אביב",
    "תל אביב, יפו": "תל אביב",
    "תל אביב (מלון קראון פלאזה)": "תל אביב",
    "מלון דן פנורמה": "תל אביב",
    "אום-אל-פחם": "אום אל-פחם",
    "הקניון הגדול פתח תקווה": "פתח תקווה",
    "הרצליה (חניה ברחוב הדסה 15)": "הרצליה",
    "זכרון יעקב סטודיו עדנה": "זכרון יעקב",
    "חיפה (קריית חיים )": "חיפה",
    "יבנה קניון G": "יבנה",
    "מאחורי קניון גבעתיים": "גבעתיים",
    "קניון צים אורבן סנטר": "חיפה",
    "קרית אתא (קניון כפיר)": "קריית אתא",
    "רמת גן (קניון אילון)": "רמת גן",
    "ג'וליס": "גוליס",
}


def normalize_city(raw_city: str) -> str:
    raw_city = raw_city.strip()
    if raw_city in CITY_ALIASES:
        return CITY_ALIASES[raw_city]
    return raw_city


def main():
    with open(OUTPUT_DIR / "clubs_detailed.json", encoding="utf-8") as f:
        clubs = json.load(f)

    slim = []
    cities_set = set()
    for c in clubs:
        addr = c.get("address", "")
        city = ""
        if "," in addr:
            city = normalize_city(addr.split(",")[-1].strip())
            if city:
                cities_set.add(city)
        slim.append({
            "id": c["id"],
            "t": c["title"],
            "a": addr,
            "c": city,
            "d": c.get("description", ""),
        })

    cities_sorted = sorted(cities_set)

    with open(OUTPUT_DIR / "_clubs_data.js", "w", encoding="utf-8") as f:
        f.write("const CLUBS = ")
        json.dump(slim, f, ensure_ascii=False)
        f.write(";\nconst CITIES = ")
        json.dump(cities_sorted, f, ensure_ascii=False)
        f.write(";\n")

    print(f"Wrote {len(slim)} clubs, {len(cities_sorted)} cities")

    # Also rebuild coords JS
    try:
        with open(OUTPUT_DIR / "city_coords.json", encoding="utf-8") as f:
            raw_city = json.load(f)
    except FileNotFoundError:
        raw_city = {}
    try:
        with open(OUTPUT_DIR / "address_coords.json", encoding="utf-8") as f:
            raw_addr = json.load(f)
    except FileNotFoundError:
        raw_addr = {}

    city_coords = {}
    for city, data in raw_city.items():
        if data:
            canonical = normalize_city(city)
            city_coords[canonical] = [round(data["lat"], 5), round(data["lng"], 5)]

    clean_addr = {k: v for k, v in raw_addr.items() if v}

    with open(OUTPUT_DIR / "_city_coords.js", "w", encoding="utf-8") as f:
        f.write("const CITY_COORDS = ")
        json.dump(city_coords, f, ensure_ascii=False)
        f.write(";\nconst ADDR_COORDS = ")
        json.dump(clean_addr, f, ensure_ascii=False)
        f.write(";\n")

    print(f"Wrote {len(city_coords)} city coords + {len(clean_addr)} address coords")


if __name__ == "__main__":
    main()
