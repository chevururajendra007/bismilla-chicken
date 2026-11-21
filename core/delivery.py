"""Delivery rules, nearest branch, distance and ETA.

Rules (all editable in Admin -> Settings):
  * 0 – 3 km   : FREE door delivery (minimum 0.5 kg)
  * 3 – 5 km   : door delivery only for orders of 2 kg or more, fee ₹30 (set fee to 0 to make it free)
  * beyond 5 km: pickup only
"""
import math

from . import catalog


def haversine_km(lat1, lng1, lat2, lng2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def road_km(lat1, lng1, lat2, lng2, factor: float) -> float:
    return round(haversine_km(lat1, lng1, lat2, lng2) * factor, 2)


def nearest_branch(lat: float, lng: float, branch_id: str | None = None):
    s = catalog.get_settings()
    f = s["delivery"]["road_factor"]
    branches = [b for b in catalog.get_branches() if b.get("open", True)] or catalog.get_branches()
    if branch_id:
        chosen = [b for b in branches if b["id"] == branch_id]
        if chosen:
            b = chosen[0]
            return b, road_km(b["lat"], b["lng"], lat, lng, f)
    best = min(branches, key=lambda b: haversine_km(b["lat"], b["lng"], lat, lng))
    return best, road_km(best["lat"], best["lng"], lat, lng, f)


def eta_minutes(distance_km: float, include_prep=True) -> int:
    d = catalog.get_settings()["delivery"]
    travel = (distance_km / max(d["speed_kmph"], 1)) * 60
    return int(math.ceil((d["prep_minutes"] if include_prep else 0) + travel + 3))


def quote(lat: float, lng: float, weight_kg: float, branch_id: str | None = None) -> dict:
    d = catalog.get_settings()["delivery"]
    branch, km = nearest_branch(lat, lng, branch_id)
    res = {
        "branch_id": branch["id"],
        "branch_name": branch["name"],
        "distance_km": km,
        "deliverable": False,
        "fee": 0,
        "reason": "",
        "eta_minutes": eta_minutes(km),
        "rules": d,
    }
    if km <= d["free_radius_km"]:
        if weight_kg < d["min_kg_inner"]:
            res["reason"] = f"Minimum {d['min_kg_inner']} kg for door delivery."
        else:
            res.update(deliverable=True, fee=0, reason=f"Free delivery (within {d['free_radius_km']:g} km).")
    elif km <= d["max_radius_km"]:
        if weight_kg >= d["min_kg_outer"]:
            fee = int(d["fee_outer"])
            res.update(deliverable=True, fee=fee,
                       reason=("Free delivery" if fee == 0 else f"Delivery fee ₹{fee}")
                       + f" ({d['free_radius_km']:g}–{d['max_radius_km']:g} km, {d['min_kg_outer']:g} kg+ order).")
        else:
            res["reason"] = (f"You are {km:.1f} km away. Door delivery between {d['free_radius_km']:g}–"
                             f"{d['max_radius_km']:g} km needs at least {d['min_kg_outer']:g} kg. Add more or choose pickup.")
    else:
        res["reason"] = f"You are {km:.1f} km away – beyond our {d['max_radius_km']:g} km delivery area. Pickup available."
    return res
