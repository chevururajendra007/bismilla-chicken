"""Shop data: settings, branches, products, and the daily "paper rate" pricing engine.

Pricing model
-------------
Every morning the newspaper publishes the broiler "paper rate" (₹/kg, live bird).
The admin enters it once; each product is priced from it automatically:

    price/kg = round(paper_rate * multiplier + offset)

A product can be switched to MANUAL, in which case `manual_price` is used and
the paper rate is ignored for it (e.g. Natu Kodi / country chicken, eggs).
The admin can also switch the whole shop to manual mode (rate_mode = "manual").
"""
import time
from datetime import datetime, timedelta, timezone

from . import store

IST = timezone(timedelta(hours=5, minutes=30))

DEFAULT_SETTINGS = {
    "paper_rate": 120,               # ₹/kg live broiler, from today's newspaper
    "paper_rate_date": None,          # YYYY-MM-DD (IST) when last updated
    "rate_mode": "paper",            # "paper" = auto from paper rate, "manual" = per-product prices only
    "delivery": {
        "free_radius_km": 3.0,        # free door delivery up to this distance
        "max_radius_km": 5.0,         # no door delivery beyond this (pickup only)
        "min_kg_outer": 2.0,          # 3–5 km band needs at least this many kg
        "fee_outer": 30,              # ₹ fee in the 3–5 km band (set 0 to make it free)
        "min_kg_inner": 0.5,          # minimum order for delivery inside the free radius
        "prep_minutes": 15,           # cut + clean + pack time
        "speed_kmph": 18,             # average two-wheeler speed in town
        "road_factor": 1.3,           # straight line -> road distance
    },
    "shop_open": True,
    # Payment options shown to customers
    "accept_cod": True,              # Cash on delivery / cash at shop
    "accept_upi_delivery": True,     # Pay by PhonePe/UPI at the door (scan QR when delivered)
    "accept_prepaid": True,          # Pay now (PhonePe/UPI) – shop starts cutting only after payment
    "cod_max_amount": 0,             # orders above this ₹ must be prepaid (0 = no limit)
    "staff_phones": [],              # delivery boys / counter staff (mobile OTP login)
    "staff_emails": [],              # staff who sign in with Clerk (Google / email)
    "admin_phones": [],              # extra admins by mobile
    "admin_emails": [],              # extra admins by email (Clerk)
    # Monthly maintenance plan – only the platform provider (superadmin) can change this
    "subscription": {"plan": "Standard", "monthly_fee": 499, "paid_until": None, "provider": "Rajendra Chevuru",
                     "provider_phone": "", "notes": ""},
    "announcement": "Fresh chicken cut in front of you. Daily paper rate.",
}

# Coordinates are APPROXIMATE town centres – the admin must drag the pin to the exact shop
# location in Admin -> Branches before going live.
DEFAULT_BRANCHES = [
    {
        "id": "kota",
        "name": "Bismilla Chicken – Kota",
        "name_te": "బిస్మిల్లా చికెన్ – కోట",
        "address": "Opposite Extra Mart, Kota, Tirupati Dist., Andhra Pradesh",
        "lat": 14.0386, "lng": 80.0467,
        "phone": "7904711708",
        "open": True, "hours": "6:00 AM – 9:00 PM",
    },
    {
        "id": "vidyanagar",
        "name": "Bismilla Chicken – Vidyanagar",
        "name_te": "బిస్మిల్లా చికెన్ – విద్యానగర్",
        "address": "Vidyanagar, Kota Mandal, Tirupati Dist., Andhra Pradesh (update exact address)",
        "lat": 14.0790, "lng": 80.0680,
        "phone": "7904711708",
        "open": True, "hours": "6:00 AM – 9:00 PM",
    },
]

# multiplier/offset are starting points; the owner tunes them in Admin -> Rates.
DEFAULT_PRODUCTS = [
    {"id": "live-broiler", "name": "Live Broiler Bird (per kg live weight)", "name_te": "బ్రాయిలర్ కోడి (లైవ్)",
     "category": "Live", "unit": "kg", "pricing": "paper", "multiplier": 1.0, "offset": 0, "manual_price": 120,
     "emoji": "🐔", "available": True, "desc": "Choose your bird; weighed live and cut fresh."},
    {"id": "skin-curry", "name": "Chicken With Skin – Curry Cut", "name_te": "చికెన్ స్కిన్‌తో – కర్రీ కట్",
     "category": "Broiler", "unit": "kg", "pricing": "paper", "multiplier": 1.5, "offset": 0, "manual_price": 180,
     "emoji": "🍗", "available": True, "desc": "Fresh curry-cut pieces with skin."},
    {"id": "skinless-curry", "name": "Skinless Chicken – Curry Cut", "name_te": "స్కిన్‌లెస్ చికెన్ – కర్రీ కట్",
     "category": "Broiler", "unit": "kg", "pricing": "paper", "multiplier": 1.75, "offset": 0, "manual_price": 210,
     "emoji": "🥩", "available": True, "desc": "Tender skinless curry cut. Most ordered."},
    {"id": "boneless", "name": "Boneless Chicken", "name_te": "బోన్‌లెస్ చికెన్",
     "category": "Broiler", "unit": "kg", "pricing": "paper", "multiplier": 2.6, "offset": 0, "manual_price": 320,
     "emoji": "🍖", "available": True, "desc": "Breast & thigh boneless cubes."},
    {"id": "legs", "name": "Chicken Leg Pieces", "name_te": "లెగ్ పీసెస్",
     "category": "Broiler", "unit": "kg", "pricing": "paper", "multiplier": 2.0, "offset": 0, "manual_price": 240,
     "emoji": "🍗", "available": True, "desc": "Drumsticks + thighs. Great for fry & tandoori."},
    {"id": "wings", "name": "Chicken Wings", "name_te": "చికెన్ వింగ్స్",
     "category": "Broiler", "unit": "kg", "pricing": "paper", "multiplier": 1.6, "offset": 0, "manual_price": 190,
     "emoji": "🍗", "available": True, "desc": "Fresh wings."},
    {"id": "liver-gizzard", "name": "Liver & Gizzard", "name_te": "లివర్ & గిజర్డ్",
     "category": "Broiler", "unit": "kg", "pricing": "manual", "multiplier": 1.0, "offset": 0, "manual_price": 160,
     "emoji": "🫀", "available": True, "desc": "Cleaned liver and gizzard."},
    {"id": "natu-kodi", "name": "Natu Kodi (Country Chicken) – Live", "name_te": "నాటు కోడి",
     "category": "Country", "unit": "kg", "pricing": "manual", "multiplier": 1.0, "offset": 0, "manual_price": 480,
     "emoji": "🐓", "available": True, "desc": "Desi country chicken, live weight."},
    {"id": "sonali", "name": "Sonali / Kadaknath Cross – Live", "name_te": "సోనాలి కోడి",
     "category": "Country", "unit": "kg", "pricing": "manual", "multiplier": 1.0, "offset": 0, "manual_price": 320,
     "emoji": "🐓", "available": True, "desc": "Semi-desi bird, live weight."},
    {"id": "eggs", "name": "Eggs – Tray of 30", "name_te": "గుడ్లు – 30 ట్రే",
     "category": "Eggs", "unit": "tray", "pricing": "manual", "multiplier": 1.0, "offset": 0, "manual_price": 190,
     "emoji": "🥚", "available": True, "desc": "Farm fresh eggs."},
]


def today_ist() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


def now_ts() -> float:
    return time.time()


# ---- getters with lazy seeding ---------------------------------------------------
def get_settings() -> dict:
    s = store.get_json("settings")
    if s is None:
        s = {**DEFAULT_SETTINGS, "paper_rate_date": today_ist()}
        store.set_json("settings", s)
    # forward-compatible defaults
    merged = {**DEFAULT_SETTINGS, **s}
    merged["delivery"] = {**DEFAULT_SETTINGS["delivery"], **(s.get("delivery") or {})}
    merged["subscription"] = {**DEFAULT_SETTINGS["subscription"], **(s.get("subscription") or {})}
    if "accept_phonepe" in s and "accept_prepaid" not in s:  # v1.0 setting name
        merged["accept_prepaid"] = merged["accept_upi_delivery"] = s["accept_phonepe"]
    return merged


def save_settings(s: dict):
    store.set_json("settings", s)


def get_branches() -> list:
    b = store.get_json("branches")
    if b is None:
        b = DEFAULT_BRANCHES
        store.set_json("branches", b)
    return b


def save_branches(b: list):
    store.set_json("branches", b)


def get_raw_products() -> list:
    p = store.get_json("products")
    if p is None:
        p = DEFAULT_PRODUCTS
        store.set_json("products", p)
    return p


def save_products(p: list):
    store.set_json("products", p)


def unit_price(product: dict, settings: dict) -> int:
    if settings.get("rate_mode") == "manual" or product.get("pricing") == "manual":
        return int(round(float(product.get("manual_price") or 0)))
    paper = float(settings.get("paper_rate") or 0)
    return int(round(paper * float(product.get("multiplier") or 1) + float(product.get("offset") or 0)))


def get_menu() -> dict:
    s = get_settings()
    items = []
    for p in get_raw_products():
        items.append({**p, "price": unit_price(p, s)})
    return {
        "paper_rate": s["paper_rate"],
        "paper_rate_date": s["paper_rate_date"],
        "rate_is_today": s["paper_rate_date"] == today_ist(),
        "rate_mode": s["rate_mode"],
        "shop_open": s["shop_open"],
        "announcement": s["announcement"],
        "products": items,
    }


def set_paper_rate(rate: float, by: str):
    s = get_settings()
    s["paper_rate"] = round(float(rate), 2)
    s["paper_rate_date"] = today_ist()
    save_settings(s)
    store.zadd("ratehist", now_ts(), f"{today_ist()}|{s['paper_rate']}|{by}|{int(now_ts())}")
    return s


def rate_history(limit=30):
    out = []
    for m in store.zrevrange("ratehist", 0, limit - 1):
        d, r, by, ts = (m.split("|") + ["", "", "", ""])[:4]
        out.append({"date": d, "rate": float(r or 0), "by": by, "ts": int(ts or 0)})
    return out
