"""
main.py
-------
This is the file you actually run. It takes one claim (image + claimed
address + claimed date/time), runs every check module, and writes two
CSV files:
  - main_verdict.csv   (short, reviewer-facing summary)
  - audit_detail.csv   (every column, full evidence trail)

USAGE (see README.md for full setup steps):
    python3 main.py --image photo.jpg --address "200 George Street, Sydney NSW" --datetime "2026-08-15 14:30"

Each run APPENDS a new row to both CSVs, so you can process claims one
at a time or in a batch script that calls this repeatedly.
"""

import argparse
import csv
import os
from datetime import datetime

import config
import metadata
import geocoding
import weather
import vision_llm
import ocr_match
import scoring


MAIN_CSV_COLUMNS = [
    "claim_id", "image_filename", "claimed_address_text",
    "geocoded_latitude", "geocoded_longitude", "claimed_datetime",
    "overall_confidence_score", "flagged_for_review", "severity", "flag_reason",
]

AUDIT_CSV_COLUMNS = MAIN_CSV_COLUMNS + [
    "geocode_precision", "geocode_ambiguous",
    "exif_gps_present", "exif_gps_distance_m", "exif_timestamp_present", "exif_time_diff_min",
    "ocr_raw_text", "ocr_fuzzy_match_result", "ocr_similarity_score",
    "vision_place_match_result", "vision_place_reasoning", "tier1_agreement",
    "tier3_result", "tier3_notes",
    "tier4_claimed_type", "tier4_observed_type", "tier4_result", "tier4_reasoning",
    "weather_claimed_category", "weather_observed_category", "weather_mismatch_level", "weather_reasoning",
    "lighting_result", "lighting_reasoning",
    "evidence_level", "processed_timestamp",
]


def _write_row(path, columns, row_dict):
    file_exists = os.path.isfile(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        if not file_exists:
            writer.writeheader()
        writer.writerow({col: row_dict.get(col, "") for col in columns})


def verify_claim(claim_id, image_path, claimed_address_text, claimed_datetime):
    row = {
        "claim_id": claim_id,
        "image_filename": os.path.basename(image_path),
        "claimed_address_text": claimed_address_text,
        "claimed_datetime": claimed_datetime.isoformat() if claimed_datetime else "not provided",
        "processed_timestamp": datetime.now().isoformat(),
    }

    # --- Step 0: forward geocode the claimed address into coordinates ---
    geo = geocoding.forward_geocode(claimed_address_text)
    row["geocoded_latitude"] = geo["latitude"]
    row["geocoded_longitude"] = geo["longitude"]
    row["geocode_precision"] = geo["precision"]
    row["geocode_ambiguous"] = geo["ambiguous"]

    if not geo["resolved"]:
        # Can't run anything downstream without coordinates - report and stop here
        row["flagged_for_review"] = True
        row["severity"] = "high"
        row["flag_reason"] = "Could not geocode claimed address at all"
        row["overall_confidence_score"] = 0.0
        row["evidence_level"] = "no_signals_available"
        return row

    lat, lon = geo["latitude"], geo["longitude"]

    # --- Metadata / EXIF ---
    meta = metadata.check_metadata(image_path, lat, lon, claimed_datetime)
    row.update(meta)

    # --- Tier 3: reverse geocoding plausibility (always runs) ---
    tier3 = geocoding.check_tier3(lat, lon)
    row.update(tier3)

    # --- Tier 1: OCR + vision LLM place matching ---
    nearby_places = geocoding.find_nearby_places(lat, lon)
    ocr_result = ocr_match.check_tier1_ocr(image_path, nearby_places)
    row["ocr_raw_text"] = ocr_result["ocr_raw_text"]
    row["ocr_fuzzy_match_result"] = ocr_result["ocr_fuzzy_match_result"]
    row["ocr_similarity_score"] = ocr_result["ocr_similarity_score"]

    vision_place = vision_llm.check_scene_text_and_places(image_path, nearby_places)
    row["vision_place_match_result"] = vision_place["category"]
    row["vision_place_reasoning"] = vision_place["reasoning"] or vision_place["error"]

    # Tier 1 agreement between the two independent methods.
    # "only_non_location_text_found" (e.g. a bus destination board) is treated
    # the same as "no_text_visible" - it's not usable location evidence either way.
    NO_EVIDENCE_CATEGORIES = (None, "no_text_visible", "only_non_location_text_found")
    ocr_says_match = ocr_result["ocr_fuzzy_match_result"] == "MATCH"
    vision_says_match = vision_place["category"] == "match"
    if ocr_result["ocr_fuzzy_match_result"] == "N/A" and vision_place["category"] in NO_EVIDENCE_CATEGORIES:
        row["tier1_agreement"] = "N/A"
    elif ocr_says_match == vision_says_match:
        row["tier1_agreement"] = "AGREE"
    else:
        row["tier1_agreement"] = "PARTIAL"

    # --- Tier 4: property/environment type (vision LLM only - no plain-code equivalent) ---
    tier4 = vision_llm.check_property_type(image_path)
    row["tier4_observed_type"] = tier4["category"]
    row["tier4_reasoning"] = tier4["reasoning"] or tier4["error"]
    row["tier4_claimed_type"] = geo["precision"]  # best proxy we have from the address itself
    row["tier4_result"] = "N/A" if tier4["error"] else "MATCH"  # simple placeholder; refine with real property data if available

    # --- Weather: claimed record vs photo ---
    # Weather requires a specific claimed time (weather changes hour to hour),
    # so this whole check is skipped gracefully - not failed - when no
    # datetime was given for the claim.
    if claimed_datetime:
        claimed_weather = weather.fetch_claimed_weather(lat, lon, claimed_datetime)
        row["weather_claimed_category"] = claimed_weather["category"]

        observed_weather = vision_llm.check_weather_in_photo(image_path)
        row["weather_observed_category"] = observed_weather["category"]
        row["weather_reasoning"] = observed_weather["reasoning"] or observed_weather["error"]

        mismatch_level = weather.compare_weather(claimed_weather["category"], observed_weather["category"])
        row["weather_mismatch_level"] = mismatch_level
    else:
        row["weather_claimed_category"] = None
        row["weather_observed_category"] = None
        row["weather_reasoning"] = "No claimed date/time provided - weather check skipped"
        mismatch_level = "N/A"
        row["weather_mismatch_level"] = mismatch_level

    # --- Lighting check ---
    lighting = vision_llm.check_lighting(image_path)
    row["lighting_result"] = lighting["category"]
    row["lighting_reasoning"] = lighting["reasoning"] or lighting["error"]

    # --- Final scoring ---
    flagged, severity, reason = scoring.determine_flag(row["tier3_result"], mismatch_level)
    score, evidence_level = scoring.soft_confidence_score(row)

    row["flagged_for_review"] = flagged
    row["severity"] = severity
    row["flag_reason"] = reason
    row["overall_confidence_score"] = score
    row["evidence_level"] = evidence_level

    return row


def main():
    parser = argparse.ArgumentParser(description="Verify an accident claim's photo against claimed location/time.")
    parser.add_argument("--image", required=True, help="Path to the accident photo")
    parser.add_argument("--address", required=True, help="Claimed address or street name")
    parser.add_argument("--datetime", required=False, default=None,
                         help="Claimed date/time, e.g. '2026-08-15 14:30'. Optional - if omitted, "
                              "the weather check and EXIF time comparison are skipped, but every "
                              "location check (Tier 1/3/4, EXIF GPS) still runs normally.")
    parser.add_argument("--claim-id", default=None, help="Optional claim ID (defaults to image filename)")
    parser.add_argument("--outdir", default="output", help="Folder to write the CSV files into")
    args = parser.parse_args()

    claimed_dt = datetime.strptime(args.datetime, "%Y-%m-%d %H:%M") if args.datetime else None
    claim_id = args.claim_id or os.path.splitext(os.path.basename(args.image))[0]

    os.makedirs(args.outdir, exist_ok=True)

    result_row = verify_claim(claim_id, args.image, args.address, claimed_dt)

    _write_row(os.path.join(args.outdir, "main_verdict.csv"), MAIN_CSV_COLUMNS, result_row)
    _write_row(os.path.join(args.outdir, "audit_detail.csv"), AUDIT_CSV_COLUMNS, result_row)

    print(f"Claim {claim_id} processed.")
    print(f"  Flagged: {result_row['flagged_for_review']}  Severity: {result_row['severity']}")
    print(f"  Confidence score: {result_row['overall_confidence_score']}")
    print(f"  Results written to {args.outdir}/main_verdict.csv and {args.outdir}/audit_detail.csv")


if __name__ == "__main__":
    main()
