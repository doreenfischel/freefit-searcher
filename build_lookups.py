#!/usr/bin/env python3
"""Extract taxonomy lookup tables (slug -> display name) from the FreeFit search page."""

import json
from pathlib import Path

import requests
from bs4 import BeautifulSoup

OUTPUT_DIR = Path(__file__).parent / "output"


def main():
    print("Fetching search page for taxonomy filters...")
    resp = requests.get("https://website.freefit.co.il/?s", timeout=30)
    soup = BeautifulSoup(resp.text, "lxml")

    lookups = {}
    for widget in soup.find_all(attrs={"data-settings": True}):
        try:
            settings = json.loads(widget.get("data-settings", ""))
        except json.JSONDecodeError:
            continue
        taxonomy = settings.get("taxonomy", "")
        if taxonomy not in ("club_city", "club_type", "club_activity"):
            continue

        mapping = {}
        for item in widget.find_all(class_="e-filter-item"):
            slug = item.get("data-filter", "")
            name = item.get_text(strip=True)
            if slug and name:
                mapping[slug] = name
        lookups[taxonomy] = mapping
        print(f"  {taxonomy}: {len(mapping)} terms")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / "lookups.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(lookups, f, ensure_ascii=False, indent=2)
    print(f"Saved {path}")


if __name__ == "__main__":
    main()
