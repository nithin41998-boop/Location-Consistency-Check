"""
ocr_match.py
------------
Tier 1: extracts any visible text from the photo using Tesseract OCR
(local, free, fast) and fuzzy-matches it against the list of nearby
places pulled from OpenStreetMap. This runs alongside the vision LLM
check (vision_llm.check_scene_text_and_places) - having both is the
point: two independent methods agreeing is much stronger evidence than
either one alone.
"""

import pytesseract
from PIL import Image
from difflib import SequenceMatcher


def extract_text(image_path):
    """Runs Tesseract OCR on the image, returns raw extracted text."""
    try:
        img = Image.open(image_path)
        text = pytesseract.image_to_string(img)
        return text.strip()
    except Exception as e:
        return f"[OCR failed: {e}]"


def _similarity(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def fuzzy_match_against_places(ocr_text, nearby_places, threshold=0.6):
    """
    Compares OCR text against each nearby place name and returns the
    best match above the threshold, or None if nothing matches well
    enough.

    Returns dict: result ("MATCH"/"NO_MATCH"/"N/A"), best_match,
    similarity_score
    """
    if not ocr_text or ocr_text.startswith("[OCR failed"):
        return {"result": "N/A", "best_match": None, "similarity_score": None}

    if not nearby_places:
        return {"result": "N/A", "best_match": None, "similarity_score": None}

    # Compare each OCR line against each place name, keep the best hit
    ocr_lines = [line.strip() for line in ocr_text.split("\n") if line.strip()]
    if not ocr_lines:
        return {"result": "N/A", "best_match": None, "similarity_score": None}

    best_score = 0.0
    best_place = None
    for line in ocr_lines:
        for place in nearby_places:
            score = _similarity(line, place)
            if score > best_score:
                best_score = score
                best_place = place

    if best_score >= threshold:
        return {"result": "MATCH", "best_match": best_place, "similarity_score": round(best_score, 2)}
    else:
        return {"result": "NO_MATCH", "best_match": best_place, "similarity_score": round(best_score, 2)}


def check_tier1_ocr(image_path, nearby_places):
    """Convenience wrapper combining extraction + matching for the CSV row."""
    raw_text = extract_text(image_path)
    match = fuzzy_match_against_places(raw_text, nearby_places)
    return {
        "ocr_raw_text": raw_text.replace("\n", " | "),  # keep CSV-safe, single line
        "ocr_fuzzy_match_result": match["result"],
        "ocr_best_match": match["best_match"],
        "ocr_similarity_score": match["similarity_score"],
    }
