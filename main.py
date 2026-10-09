"""
main.py
-------
This is the file you actually run.

INPUT: a folder (e.g. on your Desktop) containing:
  - all the claim photos
  - ONE csv file with columns: filename, address, date, time
    (time is optional - leave it blank if you don't have it)

The program checks every row against its matching photo and writes ONE
CSV file INTO THAT SAME FOLDER: results.csv (one row per claim, with
the verdict plus full plain-language detail for each check).

USAGE (see README.md for full setup steps):
    python main.py --folder "C:/Users/you/Desktop/ClaimsToCheck"

(A single-claim mode is also still available for quick one-off tests -
see the --image/--address/--datetime options below.)
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


RESULTS_CSV_COLUMNS = [
    "claim_id", "image_filename", "claimed_address_text", "claimed_datetime",
    "geocoded_latitude", "geocoded_longitude",
    "overall_confidence_score", "verdict", "severity", "flag_reason",
    "geocode_precision", "geocode_ambiguous",
    "exif_gps_present",
    "tier1_signage_check", "tier3_location_plausibility_check", "tier4_property_type_check",
    "weather_claimed_category", "weather_observed_category", "weather_mismatch_level", "weather_reasoning",
    "lighting_result", "lighting_reasoning",
    "evidence_level",
]


def _write_row(path, columns, row_dict):
    file_exists = os.path.isfile(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        if not file_exists:
            writer.writeheader()
        writer.writerow({col: row_dict.get(col, "") for col in columns})


def parse_claim_datetime(date_str, time_str=""):
    """
    Accepts a date in ISO (2026-07-15) or day-first (6/11/2024, 26/06/2025,
    26-06-2025) format, plus an optional time in 24-hour ('14:00') or
    12-hour ('2:00 PM') format. Returns a datetime, or None if no usable
    date was given. Prints a warning if a date was given but could not be
    read, so weather is never skipped silently.
    """
    date_str = (date_str or "").strip()
    time_str = (time_str or "").strip().upper()
    if not date_str:
        return None

    date_formats = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d.%m.%Y")
    time_formats = ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M%p", "%I:%M:%S %p", "%I %p", "%I%p")

    for dfmt in date_formats:
        if not time_str:
            try:
                return datetime.strptime(date_str, dfmt)
            except ValueError:
                continue
        for tfmt in time_formats:
            try:
                return datetime.strptime(f"{date_str} {time_str}", f"{dfmt} {tfmt}")
            except ValueError:
                continue

    print(f"  WARNING: could not read date/time '{date_str} {time_str}' - weather check will be skipped")
    return None


def verify_claim(claim_id, image_path, claimed_address_text, claimed_datetime):
    row = {
        "claim_id": claim_id,
        "image_filename": os.path.basename(image_path),
        "claimed_address_text": claimed_address_text,
        "claimed_datetime": claimed_datetime.isoformat() if claimed_datetime else "not provided",
    }

    # --- Step 0: forward geocode the claimed address into coordinates ---
    geo = geocoding.forward_geocode(claimed_address_text)
    row["geocoded_latitude"] = geo["latitude"]
    row["geocoded_longitude"] = geo["longitude"]
    row["geocode_precision"] = geo["precision"]
    row["geocode_ambiguous"] = geo["ambiguous"]

    if not geo["resolved"]:
        # Can't run anything downstream without coordinates - report and stop here
        row["verdict"] = "Flagged"
        row["severity"] = "high"
        row["flag_reason"] = "Could not geocode claimed address at all"
        row["overall_confidence_score"] = 0
        row["evidence_level"] = "no_signals_available"
        row["tier1_signage_check"] = "Not run - address could not be located"
        row["tier3_location_plausibility_check"] = "FAIL - claimed address does not resolve to any real location"
        row["tier4_property_type_check"] = "Not run - address could not be located"
        row["exif_gps_present"] = ""
        row["weather_claimed_category"] = None
        row["weather_observed_category"] = None
        row["weather_reasoning"] = "Not run - address could not be located"
        row["weather_mismatch_level"] = "N/A"
        row["lighting_result"] = None
        row["lighting_reasoning"] = "Not run - address could not be located"
        return row

    lat, lon = geo["latitude"], geo["longitude"]

    # --- Metadata / EXIF (used internally for scoring; only the simple
    # presence flag is exposed in the CSV, not the raw numbers) ---
    meta = metadata.check_metadata(image_path, lat, lon, claimed_datetime)
    row["exif_gps_present"] = meta["exif_gps_present"]

    # --- Tier 3: reverse geocoding plausibility (always runs) ---
    tier3 = geocoding.check_tier3(lat, lon)
    tier3_result = tier3["tier3_result"]
    if tier3_result == "PASS":
        row["tier3_location_plausibility_check"] = f"PASS - {tier3['tier3_notes']}"
    else:
        row["tier3_location_plausibility_check"] = f"FAIL - {tier3['tier3_notes']}"

    # --- Tier 1: OCR + vision LLM place matching (two independent methods) ---
    nearby_places = geocoding.find_nearby_places(lat, lon)
    ocr_result = ocr_match.check_tier1_ocr(image_path, nearby_places)
    vision_place = vision_llm.check_scene_text_and_places(image_path, nearby_places)

    NO_EVIDENCE_CATEGORIES = (None, "no_text_visible", "only_non_location_text_found")
    ocr_says_match = ocr_result["ocr_fuzzy_match_result"] == "MATCH"
    vision_says_match = vision_place["category"] == "match"
    if not ocr_says_match and vision_place["category"] in NO_EVIDENCE_CATEGORIES:
        # Neither method found a positive location clue -> no evidence either way.
        tier1_agreement = "N/A"
    elif ocr_says_match == vision_says_match:
        tier1_agreement = "AGREE"
    else:
        tier1_agreement = "PARTIAL"

    vision_reasoning = vision_place["reasoning"] or vision_place["error"] or "No reasoning returned"
    row["tier1_signage_check"] = f"[{tier1_agreement}] {vision_reasoning}"

    # --- Tier 4: property/environment type (vision LLM only - no plain-code equivalent) ---
    tier4 = vision_llm.check_property_type(image_path)
    tier4_reasoning = tier4["reasoning"] or tier4["error"] or "No reasoning returned"
    tier4_observed = tier4["category"] or "unknown"
    row["tier4_property_type_check"] = f"Observed: {tier4_observed}. {tier4_reasoning}"
    tier4_result_internal = "N/A" if tier4["error"] else "MATCH"

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
    flagged, severity, reason = scoring.determine_flag(tier3_result, mismatch_level)
    scoring_inputs = {
        "tier1_agreement": tier1_agreement,
        "tier4_result": tier4_result_internal,
        "weather_mismatch_level": mismatch_level,
        "exif_gps_present": meta["exif_gps_present"],
        "exif_gps_distance_m": meta["exif_gps_distance_m"],
        "lighting_check_result": "PASS" if lighting["category"] == "daytime" else lighting["category"],
    }
    score, evidence_level = scoring.soft_confidence_score(scoring_inputs)

    # If no actual street name / shop name / fixed location signage was
    # found anywhere in the photo (tier1_agreement "N/A" means neither OCR
    # nor the vision check found usable location-indicating text), the
    # score cannot be treated as fully confident - cap it at 90, even if
    # every other check passed.
    if tier1_agreement == "N/A":
        score = min(score, config.NO_STREET_NAME_SCORE_CAP)

    verdict = scoring.determine_verdict(flagged, score)

    row["verdict"] = verdict
    row["severity"] = severity
    row["flag_reason"] = reason
    row["overall_confidence_score"] = score
    row["evidence_level"] = evidence_level

    return row


def process_folder(folder):
    """
    Looks for one CSV file in the folder (columns: filename, address,
    date, time), runs every row against its matching image, and writes
    results.csv into that same folder.
    """
    if not os.path.isdir(folder):
        print(f"ERROR: folder not found: {folder}")
        return

    exclude = {"results.csv"}
    csv_candidates = [f for f in os.listdir(folder)
                       if f.lower().endswith(".csv") and f not in exclude]
    if not csv_candidates:
        print(f"ERROR: no input CSV found in {folder}")
        print("Expected a CSV with columns: filename, address, date, time")
        return

    input_csv = os.path.join(folder, csv_candidates[0])
    print(f"Using input CSV: {input_csv}")

    results_out = os.path.join(folder, "results.csv")

    with open(input_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"Found {len(rows)} claim(s) to check.\n")
    last = vision_llm.get_usage()

    for row in rows:
        filename = (row.get("filename") or "").strip()
        address = (row.get("address") or "").strip()
        date_str = (row.get("date") or "").strip()
        time_str = (row.get("time") or "").strip()

        if not filename:
            print("SKIPPED a row - no filename given")
            continue

        image_path = os.path.join(folder, filename)
        if not os.path.isfile(image_path):
            print(f"SKIPPED {filename} - image file not found in {folder}")
            continue

        claim_id = os.path.splitext(filename)[0]
        claimed_dt = parse_claim_datetime(date_str, time_str)

        print(f"Checking {filename} ...")
        result_row = verify_claim(claim_id, image_path, address, claimed_dt)

        _write_row(results_out, RESULTS_CSV_COLUMNS, result_row)

        print(f"  Verdict: {result_row['verdict']}  Score: {result_row['overall_confidence_score']}/100")
        now = vision_llm.get_usage()
        print(f"  Tokens this claim: {now['input_tokens'] - last['input_tokens']} in / "
              f"{now['output_tokens'] - last['output_tokens']} out "
              f"({now['calls'] - last['calls']} AI calls)\n")
        last = now

    total = vision_llm.get_usage()
    print("TOKEN USAGE FOR THIS RUN")
    print(f"  AI calls:      {total['calls']}")
    print(f"  Input tokens:  {total['input_tokens']:,}")
    print(f"  Output tokens: {total['output_tokens']:,}")
    print(f"  Total tokens:  {total['input_tokens'] + total['output_tokens']:,}\n")
    print(f"Done. Results written to:\n  {results_out}")


def main():
    parser = argparse.ArgumentParser(description="Verify accident claim photos against claimed location/time.")
    parser.add_argument("--folder", default=None,
                         help="Folder containing claim photos + one CSV (filename,address,date,time). "
                              "Results are written into this same folder.")

    # Single-claim mode, kept for quick one-off tests
    parser.add_argument("--image", default=None, help="Path to a single accident photo")
    parser.add_argument("--address", default=None, help="Claimed address or street name (single-claim mode)")
    parser.add_argument("--datetime", default=None,
                         help="Claimed date/time, e.g. '2026-08-15 14:30' (single-claim mode)")
    parser.add_argument("--claim-id", default=None, help="Optional claim ID (defaults to image filename)")
    parser.add_argument("--outdir", default="output", help="Folder to write CSVs into (single-claim mode only)")
    args = parser.parse_args()

    if args.folder:
        process_folder(args.folder)
        return

    if not args.image or not args.address:
        parser.error("Either --folder, or both --image and --address, are required.")

    claimed_dt = datetime.strptime(args.datetime, "%Y-%m-%d %H:%M") if args.datetime else None
    claim_id = args.claim_id or os.path.splitext(os.path.basename(args.image))[0]

    os.makedirs(args.outdir, exist_ok=True)
    result_row = verify_claim(claim_id, args.image, args.address, claimed_dt)

    results_path = os.path.join(args.outdir, "results.csv")
    _write_row(results_path, RESULTS_CSV_COLUMNS, result_row)

    print(f"Claim {claim_id} processed.")
    print(f"  Verdict: {result_row['verdict']}  Severity: {result_row['severity']}")
    print(f"  Confidence score: {result_row['overall_confidence_score']}/100")
    print(f"  Results written to {results_path}")


if __name__ == "__main__":
    main()
