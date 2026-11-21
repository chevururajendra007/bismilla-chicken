"""Address search for the delivery map.

Google Geocoding is used when GOOGLE_MAPS_API_KEY is set; otherwise OpenStreetMap Nominatim (free, no key).
Searches are biased to Kota / Vidyanagar and cached for 7 days so we stay well inside Nominatim's fair-use limits.
"""
import hashlib
import re

import httpx

from . import catalog, config, store

UA = {"User-Agent": f"BismillaChickenApp/{config.APP_VERSION} (orders; contact +91{config.SHOP_PHONE})"}
# lon_min, lat_max, lon_max, lat_min  – box around Kota, Vidyanagar and nearby villages
VIEWBOX = "79.90,14.20,80.20,13.90"


def _key(kind: str, q: str) -> str:
    return f"geo:{kind}:" + hashlib.sha1(q.lower().encode()).hexdigest()[:16]


def _short(display: str) -> str:
    parts = [p.strip() for p in display.split(",")]
    drop = {"india", "andhra pradesh"}
    parts = [p for p in parts if p.lower() not in drop and not re.fullmatch(r"\d{6}", p)]
    return ", ".join(parts[:4])


def search(q: str, town: str = "") -> list:
    q = (q or "").strip()
    if len(q) < 3:
        return []
    full = f"{q}, {town}" if town and town.lower() not in q.lower() else q
    ck = _key("s", full)
    hit = store.get_json(ck)
    if hit is not None:
        return hit
    out = []
    try:
        if config.GOOGLE_MAPS_API_KEY:
            r = httpx.get("https://maps.googleapis.com/maps/api/geocode/json", timeout=8,
                          params={"address": full, "key": config.GOOGLE_MAPS_API_KEY, "region": "in",
                                  "bounds": "13.90,79.90|14.20,80.20"})
            for g in r.json().get("results", [])[:5]:
                loc = g["geometry"]["location"]
                out.append({"label": _short(g["formatted_address"]), "lat": loc["lat"], "lng": loc["lng"]})
        else:
            for attempt in (full, f"{q}, Kota, Andhra Pradesh"):
                r = httpx.get("https://nominatim.openstreetmap.org/search", headers=UA, timeout=8,
                              params={"q": attempt, "format": "jsonv2", "countrycodes": "in", "limit": 5,
                                      "viewbox": VIEWBOX, "bounded": 0, "addressdetails": 0})
                for g in r.json():
                    out.append({"label": _short(g["display_name"]), "lat": float(g["lat"]), "lng": float(g["lon"])})
                if out:
                    break
    except Exception:
        out = []
    # keep results near the shop first (within ~40 km), then the rest
    b = catalog.get_branches()[0]
    near = lambda o: abs(o["lat"] - b["lat"]) + abs(o["lng"] - b["lng"])
    out = sorted(out, key=near)[:5]
    store.set_json(ck, out, ex=7 * 86400)
    return out


def reverse(lat: float, lng: float) -> dict:
    ck = _key("r", f"{lat:.4f},{lng:.4f}")
    hit = store.get_json(ck)
    if hit is not None:
        return hit
    res = {"label": "", "area": ""}
    try:
        if config.GOOGLE_MAPS_API_KEY:
            r = httpx.get("https://maps.googleapis.com/maps/api/geocode/json", timeout=8,
                          params={"latlng": f"{lat},{lng}", "key": config.GOOGLE_MAPS_API_KEY})
            g = (r.json().get("results") or [{}])[0]
            res["label"] = _short(g.get("formatted_address", ""))
        else:
            r = httpx.get("https://nominatim.openstreetmap.org/reverse", headers=UA, timeout=8,
                          params={"lat": lat, "lon": lng, "format": "jsonv2", "zoom": 17, "addressdetails": 1})
            g = r.json()
            a = g.get("address", {})
            res["label"] = _short(g.get("display_name", ""))
            res["area"] = ", ".join(x for x in [a.get("road"), a.get("neighbourhood") or a.get("suburb"),
                                                a.get("village") or a.get("town") or a.get("city")] if x)
    except Exception:
        pass
    store.set_json(ck, res, ex=7 * 86400)
    return res
