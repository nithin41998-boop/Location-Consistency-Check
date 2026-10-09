"""
find_dates.py - for each test claim, searches dates near the original one and
lists the closest dates where the historical weather (Open-Meteo) matches what
the photo shows, so the claim will be Approved.
Run:  python find_dates.py
"""
from datetime import datetime, timedelta
import requests

# name: (lat, lon, original date, hour, what the PHOTO shows)
CLAIMS = {
    "gntest2": (-36.1406609, 147.0012188, "2018-11-04", 15, "clear"),
    "gntest4": (-33.6798272, 150.9501674, "2025-12-18", 12, "rain"),
    "gntest5": (-31.9411224, 115.8523348, "2026-07-26", 15, "cloudy"),
    "gntest6": (-28.9459777, 152.2164074, "2025-08-12", 15, "rain"),
}
WINDOW_DAYS = 14

WMO = {0:"clear",1:"clear",2:"cloudy",3:"cloudy",45:"fog",48:"fog",
       51:"rain",53:"rain",55:"rain",56:"rain",57:"rain",61:"rain",63:"rain",
       65:"rain",66:"rain",67:"rain",71:"snow",73:"snow",75:"snow",77:"snow",
       80:"rain",81:"rain",82:"rain",85:"snow",86:"snow",95:"storm",96:"storm",99:"storm"}

for name, (lat, lon, d, hour, want) in CLAIMS.items():
    d0 = datetime.strptime(d, "%Y-%m-%d")
    start, end = d0 - timedelta(days=WINDOW_DAYS), d0 + timedelta(days=WINDOW_DAYS)
    try:
        r = requests.get("https://archive-api.open-meteo.com/v1/archive", params={
            "latitude": lat, "longitude": lon,
            "start_date": start.strftime("%Y-%m-%d"), "end_date": end.strftime("%Y-%m-%d"),
            "hourly": "weather_code,precipitation", "timezone": "auto"}, timeout=30)
        r.raise_for_status()
        h = r.json()["hourly"]
    except Exception as e:
        print(f"{name}: request failed: {e}"); continue

    hits = []
    for i, t in enumerate(h["time"]):
        dt = datetime.fromisoformat(t)
        if dt.hour != hour:
            continue
        cat = WMO.get(h["weather_code"][i], "unknown")
        # also require the day before to be consistent for rain (wet roads) - skip, keep simple
        if cat == want:
            hits.append((abs((dt - d0).days), dt.strftime("%d/%m/%Y"), h["precipitation"][i]))
    hits.sort()
    print(f"\n{name}  (photo shows: {want}, original date {d0:%d/%m/%Y} {hour}:00)")
    if not hits:
        print("  no matching dates in the window - raise WINDOW_DAYS")
    for gap, ds, p in hits[:4]:
        print(f"  {ds}  ({gap} days away, rain that hour: {p} mm)")
