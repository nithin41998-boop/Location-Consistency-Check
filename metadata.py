"""
metadata.py
-----------
Extracts EXIF GPS + timestamp from an image and compares it against the
claimant's stated location/time. This is the strongest signal WHEN present,
but is very often missing (WhatsApp, Facebook, gallery re-saves strip EXIF),
so every result here can legitimately be "N/A" - that is NOT a failure.
"""

from PIL import Image, ExifTags
from datetime import datetime
import math


def _dms_to_decimal(dms, ref):
    """Convert EXIF GPS (degrees, minutes, seconds) to plain decimal degrees."""
    degrees, minutes, seconds = dms
    decimal = float(degrees) + float(minutes) / 60 + float(seconds) / 3600
    if ref in ["S", "W"]:
        decimal = -decimal
    return decimal


def extract_exif(image_path):
    """
    Returns a dict:
      gps_present, latitude, longitude,
      time_present, datetime_original
    Any field is None if not found in the file.
    """
    result = {
        "gps_present": False,
        "latitude": None,
        "longitude": None,
        "time_present": False,
        "datetime_original": None,
    }

    try:
        img = Image.open(image_path)
        exif_raw = img._getexif()
    except Exception:
        return result  # not a valid image or no EXIF block at all

    if not exif_raw:
        return result

    # Map numeric EXIF tag IDs to human-readable names
    exif = {ExifTags.TAGS.get(k, k): v for k, v in exif_raw.items()}

    # ---- Timestamp ----
    for tag in ("DateTimeOriginal", "DateTime"):
        if tag in exif:
            try:
                result["datetime_original"] = datetime.strptime(
                    exif[tag], "%Y:%m:%d %H:%M:%S"
                )
                result["time_present"] = True
                break
            except Exception:
                pass

    # ---- GPS ----
    gps_info = exif.get("GPSInfo")
    if gps_info:
        gps = {ExifTags.GPSTAGS.get(k, k): v for k, v in gps_info.items()}
        try:
            lat = _dms_to_decimal(gps["GPSLatitude"], gps["GPSLatitudeRef"])
            lon = _dms_to_decimal(gps["GPSLongitude"], gps["GPSLongitudeRef"])
            result["latitude"] = lat
            result["longitude"] = lon
            result["gps_present"] = True
        except Exception:
            pass

    return result


def haversine_m(lat1, lon1, lat2, lon2):
    """Distance in metres between two lat/lon points."""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def check_metadata(image_path, claimed_lat, claimed_lon, claimed_dt):
    """
    Compares EXIF (if present) against the claim.
    Returns a dict ready to drop straight into the CSV row.
    """
    exif = extract_exif(image_path)
    out = {
        "exif_gps_present": exif["gps_present"],
        "exif_gps_distance_m": None,
        "exif_timestamp_present": exif["time_present"],
        "exif_time_diff_min": None,
    }

    if exif["gps_present"]:
        out["exif_gps_distance_m"] = round(
            haversine_m(exif["latitude"], exif["longitude"], claimed_lat, claimed_lon), 1
        )

    if exif["time_present"] and claimed_dt:
        diff = abs((exif["datetime_original"] - claimed_dt).total_seconds()) / 60
        out["exif_time_diff_min"] = round(diff, 1)

    return out
