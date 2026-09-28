"""Seoul weather for the trip window (Open-Meteo, free, no API key)."""

import math

import requests

URL = "https://api.open-meteo.com/v1/forecast"
SEOUL = (37.5665, 126.9780)
RAIN_PROB = 50      # % chance in any trip hour that counts as "rain likely"
RAIN_MM = 1.0       # or this much total precipitation
INDOOR_BONUS = 3    # score shift toward indoor places when rain is likely


def outlook(day, start_min, hours):
    """Weather over the trip window, or None if unavailable (offline, date out of range)."""
    try:
        r = requests.get(URL, timeout=8, params={
            "latitude": SEOUL[0], "longitude": SEOUL[1], "timezone": "Asia/Seoul",
            "hourly": "precipitation_probability,precipitation,temperature_2m",
            "start_date": day.isoformat(), "end_date": day.isoformat(),
        })
        r.raise_for_status()
        h = r.json()["hourly"]
    except Exception:
        return None
    first, last = start_min // 60, min(23, math.ceil((start_min + hours * 60) / 60) - 1)
    idx = [k for k, t in enumerate(h["time"]) if first <= int(t[11:13]) <= last]
    if not idx:
        return None
    prob = max((h["precipitation_probability"][k] or 0) for k in idx)
    mm = sum((h["precipitation"][k] or 0) for k in idx)
    temps = [h["temperature_2m"][k] for k in idx if h["temperature_2m"][k] is not None]
    return {
        "prob": prob, "mm": round(mm, 1),
        "tmin": round(min(temps)) if temps else None, "tmax": round(max(temps)) if temps else None,
        "rainy": prob >= RAIN_PROB or mm >= RAIN_MM,
    }


def describe(w):
    if not w:
        return "Weather unavailable for this date"
    icon = "🌧️" if w["rainy"] else ("🌦️" if w["prob"] >= 30 else "🌤️")
    temp = f"{w['tmin']}–{w['tmax']}°C" if w["tmin"] is not None else ""
    return f"{icon} {temp} · up to {w['prob']}% chance of rain during your trip"


def adapt(scores, pois):
    """Nudge scores toward indoor places."""
    indoor = {p["id"] for p in pois if "indoor" in p["tags"]}
    return {k: max(0, min(10, v + (INDOOR_BONUS if k in indoor else -INDOOR_BONUS)))
            for k, v in scores.items()}
