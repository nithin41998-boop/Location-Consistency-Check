"""
geocoding.py
------------
Handles two jobs:

1. FORWARD geocoding: turn a claimed address/street name (text) into
   lat/lon coordinates, since clients often give a street name, not
   coordinates.

2. TIER 3: reverse-geocoding plausibility check - does the resolved
   point actually sit on a real road? And Tier 3-adjacent: find nearby
   named places (shops, streets) for Tier 1's OCR/vision matching.

Uses OpenStreetMap's Nominatim + Overpass - both free, no API key.
Please be a good citizen of these free services: this module sleeps
briefly between calls per Nominatim's usage policy.
"""

import requests
import time
import config


HEADERS = {"User-Agent": config.USER_AGENT}


def forward_geocode(address_text):
    """
    Turns a text address/street name into coordinates.

    Returns a dict:
      resolved (bool), latitude, longitude, display_name,
      precision ("exact" | "street" | "suburb" | "unknown"),
      ambiguous (bool), candidate_count
    """
    result = {
        "resolved": False,
        "latitude": None,
        "longitude": None,
        "display_name": None,
        "precision": "unknown",
        "ambiguous": False,
        "candidate_count": 0,
    }

    try:
        resp = requests.get(
            f"{config.NOMINATIM_BASE}/search",
            params={"q": address_text, "format": "json", "addressdetails": 1, "limit": 5},
            headers=HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        result["display_name"] = f"geocoding request failed: {e}"
        return result

    if not data:
        return result  # resolved stays False - address not found at all

    result["candidate_count"] = len(data)
    result["ambiguous"] = len(data) > 1

    top = data[0]
    result["resolved"] = True
    result["latitude"] = float(top["lat"])
    result["longitude"] = float(top["lon"])
    result["display_name"] = top.get("display_name")

    # Rough precision guess based on OSM's "class"/"type" fields
    osm_type = top.get("type", "")
    if osm_type in ("house", "building"):
        result["precision"] = "exact"
    elif osm_type in ("road", "residential", "primary", "secondary", "tertiary"):
        result["precision"] = "street"
    elif osm_type in ("suburb", "city", "town", "village"):
        result["precision"] = "suburb"
    else:
        result["precision"] = "street"  # sensible default for ambiguous OSM types

    time.sleep(1)  # be polite to the free Nominatim service
    return result


def reverse_geocode(lat, lon):
    """
    Tier 3: checks whether a coordinate resolves to a real road/address.
    Returns dict: on_road (bool), address, road_name, distance_note
    """
    result = {"on_road": False, "address": None, "road_name": None}

    try:
        resp = requests.get(
            f"{config.NOMINATIM_BASE}/reverse",
            params={"lat": lat, "lon": lon, "format": "json", "addressdetails": 1},
            headers=HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        result["address"] = f"reverse geocoding request failed: {e}"
        return result

    if "error" in data:
        return result  # point resolves to nothing - e.g. middle of the ocean

    address = data.get("address", {})
    road = address.get("road")
    result["address"] = data.get("display_name")
    result["road_name"] = road
    # If Nominatim can name a road/residential area near this point, treat as plausible
    result["on_road"] = bool(road or address.get("residential") or address.get("suburb"))

    time.sleep(1)
    return result


def check_tier3(lat, lon):
    """
    Runs the Tier 3 plausibility check and returns a CSV-ready result.
    """
    rev = reverse_geocode(lat, lon)
    out = {
        "tier3_result": "PASS" if rev["on_road"] else "FAIL",
        "tier3_notes": rev["address"] or "No resolvable address found for these coordinates",
    }
    return out


def find_nearby_places(lat, lon, radius_m=150):
    """
    Tier 1 support: pulls named shops/amenities/streets near the claimed
    point via Overpass, for OCR/vision text matching later.
    Returns a list of plain-text names, e.g. ["Coles Chatswood", "George Street"].
    """
    query = f"""
    [out:json][timeout:15];
    (
      node["shop"](around:{radius_m},{lat},{lon});
      node["amenity"](around:{radius_m},{lat},{lon});
      way["highway"]["name"](around:{radius_m},{lat},{lon});
    );
    out tags;
    """
    try:
        resp = requests.post(config.OVERPASS_BASE, data={"data": query}, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    names = set()
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name")
        if name:
            names.add(name)

    return sorted(names)
