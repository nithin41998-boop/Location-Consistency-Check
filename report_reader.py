"""
report_reader.py

Reads an incident report PDF and pulls out what the Location Consistency
Check needs:
  - the claimed location (address)
  - the claimed date and time
  - the accident photo embedded in the report

It looks first at the labelled fields ("Location of incident", "Date of
incident", "Time of incident"). If a field is missing it falls back to the
description paragraph ("... incident in/on/at <place>. ...").

Returns rows in the same shape main.py already uses for claims.csv:
    {"filename", "address", "date", "time", "_image_path", "_source"}
"""

import os
import re
from datetime import datetime

from pypdf import PdfReader

# Every label that can start a new field. A value runs until the next label.
LABELS = [
    "Full name", "Policy number", "Phone", "Email",
    "Date of incident", "Time of incident", "Location of incident", "Photo file",
    "Vehicle(s) shown", "Emergency services", "Visible damage",
]
SECTION_RE = re.compile(r"^\d+\.\s")          # "3. Description of incident"
DATE_FORMATS = ("%A %d %B %Y", "%d %B %Y", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d %b %Y")


def _page_text(reader):
    return "\n".join((p.extract_text() or "") for p in reader.pages)


def _fields(text):
    """Return {label: value} using the label lines in the PDF text."""
    lines = [ln.strip() for ln in text.splitlines()]
    found, current = {}, None
    for ln in lines:
        if ln in LABELS:
            current = ln
            found.setdefault(current, [])
        elif SECTION_RE.match(ln):
            current = None
        elif current and ln:
            found[current].append(ln)
    return {k: " ".join(v).strip() for k, v in found.items() if v}


def _normalise_date(raw):
    """Turn 'Monday 11 August 2025' (or similar) into DD/MM/YYYY."""
    raw = raw.strip()
    for fmt in DATE_FORMATS:
        try:
            d = datetime.strptime(raw, fmt)
            return f"{d.day}/{d.month}/{d.year}"
        except ValueError:
            continue
    return ""


def _fallback_location(text):
    """Description paragraph: '... motor vehicle incident <in|on|at> <place>. ...'"""
    flat = " ".join(text.split())
    m = re.search(r"incident\s+(?:in|on|at|near)\s+(.+?)\.\s", flat)
    return m.group(1).strip() if m else ""


def _fallback_date_time(text):
    flat = " ".join(text.split())
    m = re.search(r"On\s+(.+?)\s+at about\s+(\d{1,2}:\d{2}\s*[AP]M)", flat, re.I)
    if not m:
        return "", ""
    return _normalise_date(m.group(1)), m.group(2).strip()


def _save_first_image(reader, out_path_no_ext):
    for page in reader.pages:
        for img in page.images:
            ext = os.path.splitext(img.name)[1].lower() or ".jpg"
            if ext not in (".jpg", ".jpeg", ".png"):
                ext = ".jpg"
            path = out_path_no_ext + ext
            with open(path, "wb") as f:
                f.write(img.data)
            return path
    return ""


def read_report(pdf_path, image_dir):
    """Read one report. Returns a claim dict, or None if it can't be used."""
    reader = PdfReader(pdf_path)
    text = _page_text(reader)
    fields = _fields(text)

    address = fields.get("Location of incident", "")
    source = "field"
    if not address:
        address = _fallback_location(text)
        source = "description"

    date = _normalise_date(fields.get("Date of incident", ""))
    time = fields.get("Time of incident", "").strip()
    if not date or not time:
        fd, ft = _fallback_date_time(text)
        date = date or fd
        time = time or ft

    stem = os.path.splitext(os.path.basename(pdf_path))[0]
    claim_id = stem.replace("_incident_report", "")
    os.makedirs(image_dir, exist_ok=True)
    image_path = _save_first_image(reader, os.path.join(image_dir, claim_id))

    if not address:
        print(f"  {os.path.basename(pdf_path)}: no location found in the report")
    if not image_path:
        print(f"  {os.path.basename(pdf_path)}: no photo found in the report")

    return {
        "filename": os.path.basename(image_path) if image_path else claim_id,
        "address": address,
        "date": date,
        "time": time,
        "_image_path": image_path,
        "_source": f"{os.path.basename(pdf_path)} (location from {source})",
    }


def read_reports_in_folder(folder):
    """Read every *.pdf in the folder. Photos are saved to <folder>/_report_photos."""
    pdfs = sorted(f for f in os.listdir(folder) if f.lower().endswith(".pdf"))
    image_dir = os.path.join(folder, "_report_photos")
    rows = []
    for name in pdfs:
        row = read_report(os.path.join(folder, name), image_dir)
        if row:
            rows.append(row)
    return rows
