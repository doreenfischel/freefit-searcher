#!/usr/bin/env python3
"""
FreeFit.co.il Scraper
Collects fitness club and activity data from the FreeFit WordPress site.

Usage:
    python scrape.py                  # Full scrape (API + page details)
    python scrape.py --api-only       # Only fetch from WP REST API (fast)
    python scrape.py --resume         # Resume from where you left off
    python scrape.py --club-id 8401   # Scrape a single club's detail page
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://website.freefit.co.il"
API_URL = f"{BASE_URL}/wp-json/wp/v2"
OUTPUT_DIR = Path(__file__).parent / "output"
PER_PAGE = 50  # WP API max per page for this site

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "FreeFit-Scraper/1.0 (personal data collection)",
    "Accept-Language": "he-IL,he;q=0.9,en;q=0.5",
})


def api_get(endpoint: str, params: dict | None = None) -> requests.Response:
    """Make a GET request to the WP REST API with retry logic."""
    url = f"{API_URL}/{endpoint}"
    for attempt in range(3):
        try:
            resp = SESSION.get(url, params=params, timeout=30)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            if attempt == 2:
                raise
            print(f"  Retry {attempt + 1} for {url}: {e}")
            time.sleep(2 ** attempt)


def fetch_all_posts(post_type: str) -> list[dict]:
    """Paginate through all posts of a given type via WP REST API."""
    all_posts = []
    page = 1

    while True:
        print(f"  Fetching {post_type} page {page}...")
        try:
            resp = api_get(post_type, {"per_page": PER_PAGE, "page": page})
        except requests.HTTPError as e:
            if e.response.status_code == 400:
                break  # past last page
            raise

        posts = resp.json()
        if not posts:
            break

        all_posts.extend(posts)
        print(f"    Got {len(posts)} items (total: {len(all_posts)})")

        if len(posts) < PER_PAGE:
            break
        page += 1
        time.sleep(0.5)

    return all_posts


def extract_taxonomy_ids(class_list: list[str], prefix: str) -> list[str]:
    """Extract taxonomy term IDs from WordPress CSS class list."""
    ids = []
    for cls in class_list:
        if cls.startswith(prefix):
            term_id = cls[len(prefix):]
            if term_id.isdigit():
                ids.append(term_id)
            else:
                ids.append(term_id)
    return ids


def parse_club_from_api(raw: dict) -> dict:
    """Parse a club entry from the WP REST API response."""
    class_list = raw.get("class_list", [])
    return {
        "id": raw["id"],
        "title": BeautifulSoup(raw["title"]["rendered"], "html.parser").get_text(),
        "slug": raw["slug"],
        "url": raw["link"],
        "status": raw["status"],
        "date_created": raw["date"],
        "date_modified": raw["modified"],
        "city_ids": extract_taxonomy_ids(class_list, "club_city-"),
        "type_ids": extract_taxonomy_ids(class_list, "club_type-"),
        "activity_ids": extract_taxonomy_ids(class_list, "club_activity-"),
    }


def parse_activity_from_api(raw: dict) -> dict:
    """Parse an activity entry from the WP REST API response."""
    return {
        "id": raw["id"],
        "title": BeautifulSoup(raw["title"]["rendered"], "html.parser").get_text(),
        "slug": raw["slug"],
        "url": raw["link"],
        "content": BeautifulSoup(raw["content"]["rendered"], "html.parser").get_text().strip(),
        "date_created": raw["date"],
        "date_modified": raw["modified"],
    }


def scrape_club_page(club_id: int) -> dict:
    """Scrape the individual club page for detailed info using Elementor structure.

    Page layout follows a consistent pattern:
      h2: Club Name
        > address (icon-list widget)
        > description (text-editor widget)
      h2: מידע שימושי (Useful Info)
        > address again
      h2: שעות פתיחה (Opening Hours)
        > day: HH:MM-HH:MM lines
      h2: חשוב לדעת (Important to Know)
        > notes, waze link
    """
    url = f"{BASE_URL}/?p={club_id}"
    for attempt in range(3):
        try:
            resp = SESSION.get(url, timeout=30)
            resp.raise_for_status()
            break
        except requests.RequestException as e:
            if attempt == 2:
                print(f"  FAILED to fetch club {club_id}: {e}")
                return {}
            time.sleep(2 ** attempt)

    soup = BeautifulSoup(resp.text, "lxml")
    details = {"address": "", "description": ""}

    # First h2 is the club name; its sibling widgets are: address, then description
    for h2 in soup.find_all("h2"):
        container = h2.find_parent(class_="elementor-widget")
        if not container:
            continue
        siblings = []
        for sib in container.find_next_siblings(class_="elementor-widget"):
            t = sib.get_text(strip=True)
            if t:
                siblings.append(t)
        if len(siblings) >= 1:
            details["address"] = siblings[0]
        if len(siblings) >= 2:
            details["description"] = siblings[1]
        break

    return details


def save_json(data: list | dict, filename: str):
    """Save data as JSON."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Saved {path} ({len(data)} items)")


def save_csv(data: list[dict], filename: str):
    """Save data as CSV."""
    if not data:
        return
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / filename

    # Flatten nested dicts for CSV
    flat_data = []
    for item in data:
        flat = {}
        for k, v in item.items():
            if isinstance(v, (list, dict)):
                flat[k] = json.dumps(v, ensure_ascii=False)
            else:
                flat[k] = v
        flat_data.append(flat)

    all_keys = []
    for item in flat_data:
        for k in item:
            if k not in all_keys:
                all_keys.append(k)

    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=all_keys)
        writer.writeheader()
        writer.writerows(flat_data)
    print(f"Saved {path} ({len(data)} rows)")


def load_progress() -> set[int]:
    """Load the set of already-scraped club IDs."""
    progress_file = OUTPUT_DIR / ".progress.json"
    if progress_file.exists():
        with open(progress_file) as f:
            return set(json.load(f))
    return set()


def save_progress(scraped_ids: set[int]):
    """Save progress for resume capability."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    progress_file = OUTPUT_DIR / ".progress.json"
    with open(progress_file, "w") as f:
        json.dump(sorted(scraped_ids), f)


def main():
    parser = argparse.ArgumentParser(description="Scrape FreeFit.co.il fitness data")
    parser.add_argument("--api-only", action="store_true", help="Only fetch API data (no page scraping)")
    parser.add_argument("--resume", action="store_true", help="Resume scraping from last checkpoint")
    parser.add_argument("--club-id", type=int, help="Scrape a single club by ID")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between page requests (seconds)")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Single club mode
    if args.club_id:
        print(f"Scraping club {args.club_id}...")
        details = scrape_club_page(args.club_id)
        print(json.dumps(details, ensure_ascii=False, indent=2))
        return

    # Step 1: Fetch all clubs from API
    print("=" * 60)
    print("Step 1: Fetching all clubs from WP REST API...")
    print("=" * 60)
    raw_clubs = fetch_all_posts("club")
    clubs = [parse_club_from_api(c) for c in raw_clubs]
    save_json(clubs, "clubs_api.json")
    save_csv(clubs, "clubs_api.csv")

    # Step 2: Fetch all activities from API
    print("\n" + "=" * 60)
    print("Step 2: Fetching all activities from WP REST API...")
    print("=" * 60)
    raw_activities = fetch_all_posts("activity")
    activities = [parse_activity_from_api(a) for a in raw_activities]
    save_json(activities, "activities.json")
    save_csv(activities, "activities.csv")

    if args.api_only:
        print(f"\nDone (API only). {len(clubs)} clubs, {len(activities)} activities.")
        return

    # Step 3: Scrape individual club pages for details
    print("\n" + "=" * 60)
    print(f"Step 3: Scraping {len(clubs)} club detail pages...")
    print("=" * 60)

    scraped_ids = load_progress() if args.resume else set()
    if scraped_ids:
        print(f"  Resuming: {len(scraped_ids)} already done, {len(clubs) - len(scraped_ids)} remaining")

    # Load existing details if resuming
    details_file = OUTPUT_DIR / "clubs_detailed.json"
    if args.resume and details_file.exists():
        with open(details_file, encoding="utf-8") as f:
            clubs_detailed = json.load(f)
    else:
        clubs_detailed = []

    for i, club in enumerate(clubs):
        if club["id"] in scraped_ids:
            continue

        print(f"  [{i + 1}/{len(clubs)}] {club['title']} (ID: {club['id']})...")
        details = scrape_club_page(club["id"])
        merged = {**club, **details}
        clubs_detailed.append(merged)
        scraped_ids.add(club["id"])

        # Checkpoint every 50 clubs
        if len(scraped_ids) % 50 == 0:
            save_json(clubs_detailed, "clubs_detailed.json")
            save_progress(scraped_ids)
            print(f"  Checkpoint: {len(scraped_ids)} clubs saved")

        time.sleep(args.delay)

    # Final save
    save_json(clubs_detailed, "clubs_detailed.json")
    save_csv(clubs_detailed, "clubs_detailed.csv")
    save_progress(scraped_ids)

    # Clean up progress file
    progress_file = OUTPUT_DIR / ".progress.json"
    if progress_file.exists():
        progress_file.unlink()

    print("\n" + "=" * 60)
    print(f"Done! {len(clubs_detailed)} clubs, {len(activities)} activities")
    print(f"Output: {OUTPUT_DIR}/")
    print("=" * 60)


if __name__ == "__main__":
    main()
