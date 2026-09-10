"""
download_test_images.py
------------------------
Downloads 20 REAL photographs from Google's Street View Static API (not
AI-generated) and builds a ground-truth CSV pairing each image with a
claimed address/date/time.

- gntest1..10.jpg  -> claimed address MATCHES where the photo was actually taken
- fltest1..10.jpg  -> claimed address does NOT match where the photo was
                      actually taken (a real photo, paired with a wrong claim)

This gives genuinely verifiable ground truth: every image comes from a
real, exact, known coordinate (that's what Street View guarantees), and
the "wrong" cases are wrong on purpose and by design, not by accident.

REQUIRES: a Google Maps API key with the "Street View Static API" enabled
(this is a paid API beyond a small free monthly quota - check Google Cloud
pricing before running this on a large batch).

Usage:
    python download_test_images.py
"""

import os
import requests
import csv

# Reuse the same key config.py already expects, or set directly here.
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")

STREETVIEW_URL = "https://maps.googleapis.com/maps/api/streetview"
OUTPUT_DIR = "test_images"

# Each entry: the REAL address to fetch the photo from, a short scenario
# description (for your own reference), and - for the "false" set only -
# a deliberately WRONG address to put in the ground-truth CSV instead.
#
# Feel free to swap these addresses for ones more relevant to your test
# needs - this list is just a starting point covering varied scenarios
# (clear signage, no signage, secluded road, driveway-style, highway, etc).

GENUINE_CASES = [
    {"real_address": "200 George Street, Sydney NSW", "date": "2026-03-10", "time": "14:00",
     "scenario": "urban street, multiple shopfronts visible"},
    {"real_address": "1 Bridge Street, Sydney NSW", "date": "2026-03-11", "time": "10:30",
     "scenario": "clear street signage visible"},
    {"real_address": "Anzac Parade, Kensington NSW", "date": "2026-03-12", "time": "16:00",
     "scenario": "wide road, some signage"},
    {"real_address": "Parramatta Road, Camperdown NSW", "date": "2026-03-13", "time": "09:00",
     "scenario": "busy arterial road, shopfronts"},
    {"real_address": "Oxford Street, Paddington NSW", "date": "2026-03-14", "time": "13:00",
     "scenario": "retail strip, clear shop names"},
    {"real_address": "The Grand Parade, Brighton-Le-Sands NSW", "date": "2026-03-15", "time": "11:00",
     "scenario": "coastal road, minimal signage"},
    {"real_address": "Old Northern Road, Glenorie NSW", "date": "2026-03-16", "time": "15:00",
     "scenario": "secluded rural road, no landmarks"},
    {"real_address": "Mona Vale Road, Ingleside NSW", "date": "2026-03-17", "time": "12:00",
     "scenario": "bushland road, no street sign visible"},
    {"real_address": "Hume Highway, Mittagong NSW", "date": "2026-03-18", "time": "10:00",
     "scenario": "highway, no buildings"},
    {"real_address": "King Street, Newtown NSW", "date": "2026-03-19", "time": "17:00",
     "scenario": "dense urban strip, many shop names"},
]

FALSE_CASES = [
    {"real_address": "200 George Street, Sydney NSW", "claimed_address": "Bondi Beach, NSW",
     "date": "2026-04-01", "time": "14:00", "scenario": "urban CBD photo claimed as beach location"},
    {"real_address": "1 Bridge Street, Sydney NSW", "claimed_address": "Katoomba, NSW",
     "date": "2026-04-02", "time": "10:30", "scenario": "CBD street claimed as mountains town"},
    {"real_address": "Anzac Parade, Kensington NSW", "claimed_address": "Parramatta Road, Camperdown NSW",
     "date": "2026-04-03", "time": "16:00", "scenario": "correct suburb, wrong specific street"},
    {"real_address": "Parramatta Road, Camperdown NSW", "claimed_address": "Hume Highway, Mittagong NSW",
     "date": "2026-04-04", "time": "09:00", "scenario": "arterial road claimed as rural highway"},
    {"real_address": "Oxford Street, Paddington NSW", "claimed_address": "Old Northern Road, Glenorie NSW",
     "date": "2026-04-05", "time": "13:00", "scenario": "retail strip claimed as secluded rural road"},
    {"real_address": "The Grand Parade, Brighton-Le-Sands NSW", "claimed_address": "King Street, Newtown NSW",
     "date": "2026-04-06", "time": "11:00", "scenario": "coastal road claimed as inner-city strip"},
    {"real_address": "Old Northern Road, Glenorie NSW", "claimed_address": "200 George Street, Sydney NSW",
     "date": "2026-04-07", "time": "15:00", "scenario": "secluded road claimed as CBD address"},
    {"real_address": "Mona Vale Road, Ingleside NSW", "claimed_address": "Oxford Street, Paddington NSW",
     "date": "2026-04-08", "time": "12:00", "scenario": "bushland road claimed as retail strip"},
    {"real_address": "Hume Highway, Mittagong NSW", "claimed_address": "The Grand Parade, Brighton-Le-Sands NSW",
     "date": "2026-04-09", "time": "10:00", "scenario": "highway claimed as coastal road"},
    {"real_address": "King Street, Newtown NSW", "claimed_address": "1 Bridge Street, Sydney NSW",
     "date": "2026-04-10", "time": "17:00", "scenario": "inner-city strip claimed as different CBD street"},
]


def download_streetview_image(address, filepath):
    """Downloads one Street View still for the given address. Returns True/False for success."""
    if not GOOGLE_MAPS_API_KEY:
        print(f"  SKIPPED (no GOOGLE_MAPS_API_KEY set): {filepath}")
        return False

    params = {
        "size": "640x640",
        "location": address,
        "fov": 90,
        "key": GOOGLE_MAPS_API_KEY,
    }
    try:
        resp = requests.get(STREETVIEW_URL, params=params, timeout=20)
        resp.raise_for_status()
        # Google returns a 1x1 grey placeholder image (not an error) if no
        # imagery is available for that address - check content length as
        # a rough signal, though not foolproof.
        if len(resp.content) < 2000:
            print(f"  WARNING - response very small, may be a 'no imagery available' placeholder: {address}")
        with open(filepath, "wb") as f:
            f.write(resp.content)
        return True
    except Exception as e:
        print(f"  FAILED to download for '{address}': {e}")
        return False


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    csv_rows = []

    print("Downloading GENUINE (matching) test cases...")
    for i, case in enumerate(GENUINE_CASES, start=1):
        filename = f"gntest{i}.jpg"
        filepath = os.path.join(OUTPUT_DIR, filename)
        print(f"[{filename}] fetching real photo at: {case['real_address']}")
        success = download_streetview_image(case["real_address"], filepath)
        csv_rows.append({
            "filename": filename,
            "address": case["real_address"],  # claimed = actual -> MATCH
            "date": case["date"],
            "time": case["time"],
            "expected_result": "MATCH",
            "scenario_description": case["scenario"],
            "download_success": success,
        })

    print("\nDownloading FALSE (mismatched) test cases...")
    for i, case in enumerate(FALSE_CASES, start=1):
        filename = f"fltest{i}.jpg"
        filepath = os.path.join(OUTPUT_DIR, filename)
        print(f"[{filename}] fetching real photo at: {case['real_address']} "
              f"(will be claimed as: {case['claimed_address']})")
        success = download_streetview_image(case["real_address"], filepath)
        csv_rows.append({
            "filename": filename,
            "address": case["claimed_address"],  # deliberately WRONG claim
            "date": case["date"],
            "time": case["time"],
            "expected_result": "MISMATCH",
            "scenario_description": case["scenario"],
            "download_success": success,
        })

    csv_path = "ground_truth.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "filename", "address", "date", "time", "expected_result",
            "scenario_description", "download_success"
        ])
        writer.writeheader()
        writer.writerows(csv_rows)

    print(f"\nDone. Ground-truth file written to {csv_path}")
    print(f"Images saved to {OUTPUT_DIR}/")
    print("\nNote: the 'address' column is the CLAIMED address to feed into main.py --address.")
    print("It intentionally matches reality for gntest files and does NOT for fltest files.")


if __name__ == "__main__":
    main()
