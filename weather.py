"""
weather.py
----------
Fetches the historical weather record for the claimed location/time using
Open-Meteo (free, no API key). Converts Open-Meteo's numeric WMO weather
code into one of our simple categories, then compares it against the
LLM's visual read of the photo to produce MATCH / MINOR / MAJOR.
"""

import requests
import config


# WMO weather codes -> our simplified categories
# https://open-meteo.com/en/docs (weather_code field)
WMO_CODE_MAP = {
    0: "clear", 1: "clear", 2: "cloudy", 3: "cloudy",
    45: "fog", 48: "fog",
    51: "rain", 53: "rain", 55: "rain", 56: "rain", 57: "rain",
    61: "rain", 63: "rain", 65: "rain", 66: "rain", 67: "rain",
    71: "snow", 73: "snow", 75: "snow", 77: "snow",
    80: "rain", 81: "rain", 82: "rain",
    85: "snow", 86: "snow",
    95: "storm", 96: "storm", 99: "storm",
}

# Which category pairs count as MAJOR vs MINOR when they disagree.
# Anything not listed here defaults to MINOR (cautious default -
# avoids over-flagging on categories we haven't explicitly classified).
MAJOR_PAIRS = {
    frozenset(["snow", "clear"]),
    frozenset(["snow", "cloudy"]),
    frozenset(["storm", "clear"]),
    frozenset(["fog", "clear"]),
    frozenset(["rain", "clear"]),   # heavy rain vs clear sky
}


def fetch_claimed_weather(lat, lon, claimed_datetime):
    """
    Returns dict: category ("clear"/"rain"/"snow"/etc.), raw_wmo_code,
    temperature_c, precipitation_mm, or an error note if the call fails.
    """
    date_str = claimed_datetime.strftime("%Y-%m-%d")
    hour = claimed_datetime.hour

    result = {
        "category": None,
        "raw_wmo_code": None,
        "temperature_c": None,
        "precipitation_mm": None,
        "error": None,
    }

    try:
        resp = requests.get(
            config.OPEN_METEO_ARCHIVE,
            params={
                "latitude": lat,
                "longitude": lon,
                "start_date": date_str,
                "end_date": date_str,
                "hourly": "temperature_2m,precipitation,weather_code",
                "timezone": "auto",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        result["error"] = f"weather request failed: {e}"
        return result

    hourly = data.get("hourly", {})
    codes = hourly.get("weather_code", [])
    temps = hourly.get("temperature_2m", [])
    precip = hourly.get("precipitation", [])

    if not codes or hour >= len(codes):
        result["error"] = "no hourly data returned for requested date/hour"
        return result

    wmo_code = codes[hour]
    result["raw_wmo_code"] = wmo_code
    result["category"] = WMO_CODE_MAP.get(wmo_code, "unknown")
    result["temperature_c"] = temps[hour] if hour < len(temps) else None
    result["precipitation_mm"] = precip[hour] if hour < len(precip) else None

    return result


def compare_weather(claimed_category, observed_category):
    """
    claimed_category: from Open-Meteo (objective record)
    observed_category: from the vision LLM reading the photo (subjective)
    Returns "MATCH" / "MINOR_MISMATCH" / "MAJOR_MISMATCH" / "N/A"
    """
    if not claimed_category or not observed_category or observed_category == "unclear":
        return "N/A"

    if claimed_category == observed_category:
        return "MATCH"

    pair = frozenset([claimed_category, observed_category])
    if pair in MAJOR_PAIRS:
        return "MAJOR_MISMATCH"

    return "MINOR_MISMATCH"
