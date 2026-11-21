"""Shop data: settings, branches, products, and the daily "paper rate" pricing engine.

Pricing model (v1.2)
--------------------
The Nellore edition of the Telugu papers prints TWO broiler rates every morning:
  * LIVE rate     – per kg live bird  (బ్రాయిలర్ లైవ్)
  * BROILER rate  – per kg dressed / skinless chicken (స్కిన్‌లెస్)
The admin types both once a day; every product is priced from the rate it is linked to:

    price/kg = round(rate[basis] * multiplier + offset)      basis = "live" | "broiler"

A product can be MANUAL (country chicken, eggs, liver) – then `manual_price` is used.
The whole shop can also be switched to manual mode (rate_mode = "manual").
"""
import time
from datetime import datetime, timedelta, timezone

from . import store

IST = timezone(timedelta(hours=5, minutes=30))

DEFAULT_SETTINGS = {
    # Nellore paper rates (₹/kg). Defaults = latest public Nellore market rates found (Jul 2026):
    # live ₹220, skinless ₹280. The owner overwrites them every morning from the paper.
    "rates": {"live": 220, "broiler": 280},
    "paper_rate": 220,               # kept for v1.0/1.1 compatibility (= live rate)
    "paper_rate_date": None,          # YYYY-MM-DD (IST) when last updated
    "catalog_version": 4,
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

# Real photos of raw chicken from Wikimedia Commons (licence requires the credit line shown on the card)
COMMONS = {'legs': ('https://thumb.wikimedia.org/wikipedia/commons/thumb/d/dc/Raw_leg_chicken_quarters.jpg/960px-Raw_leg_chicken_quarters.jpg', 'Photo: Baoothersks, CC BY-SA 4.0, Wikimedia Commons'), 'wings': ('https://thumb.wikimedia.org/wikipedia/commons/thumb/8/8c/Raw_chicken_wings.jpg/960px-Raw_chicken_wings.jpg', 'Photo: ProjectManhattan, CC BY-SA 3.0, Wikimedia Commons'), 'liver-gizzard': ('https://thumb.wikimedia.org/wikipedia/commons/thumb/9/94/Chicken_Liver_and_Gizzard_-_Howrah_2015-04-19_8195.JPG/960px-Chicken_Liver_and_Gizzard_-_Howrah_2015-04-19_8195.JPG', 'Photo: Biswarup Ganguly, CC BY 3.0, Wikimedia Commons')}


# Free photos (Unsplash License) as placeholders – the owner can replace each with his own shop photo
# from Admin -> Rates -> 📷. multiplier/offset are starting points the owner tunes.
def IMG(pid: str) -> str:
    return f"https://images.unsplash.com/photo-{pid}?auto=format&fit=crop&w=640&q=70"


DEFAULT_PRODUCTS = [
    {"id": "live-broiler", "name": "Live Broiler Bird", "name_te": "బ్రాయిలర్ కోడి (లైవ్)",
     "category": "Live", "unit": "kg", "pricing": "paper", "basis": "live", "multiplier": 1.0, "offset": 0,
     "manual_price": 220, "image": IMG("1721778468488-504bbf626b9f"), "emoji": "🐔", "available": True,
     "desc": "Pick your bird – weighed live, cut fresh in front of you.", "badge": "Live rate"},
    {"id": "skinless-curry", "name": "Skinless Chicken – Curry Cut", "name_te": "స్కిన్‌లెస్ చికెన్ – కర్రీ కట్",
     "category": "Broiler", "unit": "kg", "pricing": "paper", "basis": "broiler", "multiplier": 1.0, "offset": 0,
     "manual_price": 280, "image": IMG("1587593810167-a84920ea0781"), "emoji": "🥩", "available": True,
     "desc": "Tender skinless curry cut. Most ordered.", "badge": "Bestseller"},
    {"id": "skin-curry", "name": "Chicken With Skin – Curry Cut", "name_te": "చికెన్ స్కిన్‌తో – కర్రీ కట్",
     "category": "Broiler", "unit": "kg", "pricing": "paper", "basis": "broiler", "multiplier": 1.0, "offset": -20,
     "manual_price": 260, "image": IMG("1759493321741-883fbf9f433c"), "emoji": "🍗", "available": True,
     "desc": "Juicy curry-cut pieces with skin."},
    {"id": "boneless", "name": "Boneless Chicken", "name_te": "బోన్‌లెస్ చికెన్",
     "category": "Broiler", "unit": "kg", "pricing": "paper", "basis": "broiler", "multiplier": 1.5, "offset": 0,
     "manual_price": 420, "image": IMG("1633096013004-e2cb4023b560"), "emoji": "🍖", "available": True,
     "desc": "Breast & thigh boneless cubes – biryani, 65, kebab."},
    {"id": "legs", "name": "Chicken Leg Pieces", "name_te": "లెగ్ పీసెస్",
     "category": "Broiler", "unit": "kg", "pricing": "paper", "basis": "broiler", "multiplier": 1.15, "offset": 0,
     "manual_price": 320, "image": COMMONS["legs"][0], "credit": COMMONS["legs"][1], "emoji": "🍗", "available": True,
     "desc": "Drumsticks + thighs. Great for fry & tandoori."},
    {"id": "wings", "name": "Chicken Wings", "name_te": "చికెన్ వింగ్స్",
     "category": "Broiler", "unit": "kg", "pricing": "paper", "basis": "broiler", "multiplier": 0.95, "offset": 0,
     "manual_price": 266, "image": COMMONS["wings"][0], "credit": COMMONS["wings"][1], "emoji": "🍗", "available": True,
     "desc": "Fresh wings for fry & lollipop."},
    {"id": "liver-gizzard", "name": "Liver & Gizzard", "name_te": "లివర్ & గిజర్డ్",
     "category": "Broiler", "unit": "kg", "pricing": "manual", "basis": "broiler", "multiplier": 1.0, "offset": 0,
     "manual_price": 190, "image": COMMONS["liver-gizzard"][0], "credit": COMMONS["liver-gizzard"][1], "emoji": "🫀", "available": True,
     "desc": "Cleaned liver and gizzard."},
    {"id": "natu-kodi", "name": "Natu Kodi (Country Chicken)", "name_te": "నాటు కోడి",
     "category": "Country", "unit": "kg", "pricing": "manual", "basis": "live", "multiplier": 1.0, "offset": 0,
     "manual_price": 450, "image": IMG("1759211321222-09f769570583"), "emoji": "🐓", "available": True,
     "desc": "Desi country chicken, live weight.", "badge": "Desi"},
    {"id": "sonali", "name": "Sonali / Pandem Cross", "name_te": "సోనాలి కోడి",
     "category": "Country", "unit": "kg", "pricing": "manual", "basis": "live", "multiplier": 1.0, "offset": 0,
     "manual_price": 320, "image": IMG("1763517174823-61148e142c8e"), "emoji": "🐓", "available": True,
     "desc": "Semi-desi bird, live weight."},
    {"id": "eggs", "name": "Eggs – Tray of 30", "name_te": "గుడ్లు – 30 ట్రే",
     "category": "Eggs", "unit": "tray", "pricing": "manual", "basis": "broiler", "multiplier": 1.0, "offset": 0,
     "manual_price": 190, "image": IMG("1635843125569-b7fb33d26fab"), "emoji": "🥚", "available": True,
     "desc": "Farm fresh eggs."},
]



# ---- Bismilla Kitchen: cooked chicken dishes (sample prices – owner edits them in Admin -> Rates) ----
KITCHEN = [
    {"id": "k-chicken-curry", "name": "Andhra Chicken Curry", "name_te": "కోడి కూర", "category": "Kitchen", "unit": "plate",
     "pricing": "manual", "basis": "broiler", "multiplier": 1.0, "offset": 0, "manual_price": 180, "emoji": "🍛",
     "serving": "500 ml · 6–7 pieces · serves 2", "equiv_kg": 0.5, "prep_extra": 20, "available": True,
     "desc": "Home-style spicy gravy, made fresh on order.", "badge": "Hot",
     "image": "https://thumb.wikimedia.org/wikipedia/commons/thumb/b/b7/Chicken_curry_Trivandrum.jpg/960px-Chicken_curry_Trivandrum.jpg",
     "credit": "Photo: Abhilashsnair, CC0, Wikimedia Commons"},
    {"id": "k-chicken-65", "name": "Chicken 65", "name_te": "చికెన్ 65", "category": "Kitchen", "unit": "plate",
     "pricing": "manual", "basis": "broiler", "multiplier": 1.0, "offset": 0, "manual_price": 200, "emoji": "🌶️",
     "serving": "250 g · crispy & spicy", "equiv_kg": 0.5, "prep_extra": 20, "available": True,
     "desc": "Deep-fried, curry-leaf tempered, restaurant style.", "badge": "Bestseller",
     "image": "https://thumb.wikimedia.org/wikipedia/commons/thumb/5/5d/Chicken_65_%28Dish%29.jpg/960px-Chicken_65_%28Dish%29.jpg",
     "credit": "Photo: Amiyashrivastava, CC BY-SA 3.0, Wikimedia Commons"},
    {"id": "k-liver-fry", "name": "Chicken Liver Fry", "name_te": "లివర్ ఫ్రై", "category": "Kitchen", "unit": "plate",
     "pricing": "manual", "basis": "broiler", "multiplier": 1.0, "offset": 0, "manual_price": 150, "emoji": "🍳",
     "serving": "250 g · pepper masala fry", "equiv_kg": 0.5, "prep_extra": 20, "available": True,
     "desc": "Soft liver tossed with onion, pepper and masala.",
     "image": "https://thumb.wikimedia.org/wikipedia/commons/thumb/7/74/Fried_Chicken_Liver.jpg/960px-Fried_Chicken_Liver.jpg",
     "credit": "Photo: Kevin628, CC BY-SA 4.0, Wikimedia Commons"},
    {"id": "k-chicken-pakoda", "name": "Chicken Pakoda", "name_te": "చికెన్ పకోడి", "category": "Kitchen", "unit": "plate",
     "pricing": "manual", "basis": "broiler", "multiplier": 1.0, "offset": 0, "manual_price": 160, "emoji": "🍗",
     "serving": "250 g · evening snack", "equiv_kg": 0.5, "prep_extra": 20, "available": True,
     "desc": "Crunchy boneless fritters with onion & chilli.",
     "image": "https://thumb.wikimedia.org/wikipedia/commons/thumb/c/c7/Chicken_Pakora_-_Kolkata_2013-10-11_3286.JPG/960px-Chicken_Pakora_-_Kolkata_2013-10-11_3286.JPG",
     "credit": "Photo: Biswarup Ganguly, CC BY 3.0, Wikimedia Commons"},
]
DEFAULT_PRODUCTS = DEFAULT_PRODUCTS + KITCHEN


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
    if not s.get("rates"):  # v1.0/1.1 had one placeholder paper_rate -> start from the Nellore defaults
        merged["rates"] = dict(DEFAULT_SETTINGS["rates"])
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
    if p is None or not all("basis" in x for x in p):
        # first run, or catalog from v1.0/1.1 -> move to the two-rate catalog with photos
        old = {x["id"]: x for x in (p or [])}
        p = [{**d, "available": old.get(d["id"], {}).get("available", True)} for d in DEFAULT_PRODUCTS]
        store.set_json("products", p)
        s = get_settings()
        s["catalog_version"] = 3
        if not (store.get_json("settings") or {}).get("rates"):
            s["rates"] = dict(DEFAULT_SETTINGS["rates"])
            s["paper_rate"] = s["rates"]["live"]
            save_settings(s)
    # v1.2.2: full-body hen for Natu Kodi instead of the close-up behind a fence
    for x in p:
        if "1761284827145-06ea2fe270bd" in (x.get("image") or ""):
            x["image"] = IMG("1759211321222-09f769570583")
            store.set_json("products", p)
    # v1.4: add any new default products (e.g. Bismilla Kitchen dishes) without touching the owner's edits
    have = {x["id"] for x in p}
    missing = [d for d in DEFAULT_PRODUCTS if d["id"] not in have]
    if missing:
        p = p + missing
        store.set_json("products", p)
    # v1.3.1: real raw-chicken photos for legs / wings / liver where no owner photo exists yet
    changed = False
    for x in p:
        if x["id"] in COMMONS and not x.get("image"):
            x["image"], x["credit"] = COMMONS[x["id"]]
            changed = True
    if changed:
        store.set_json("products", p)
    # v1.2.1: stock photos that did not match the product (legs/wings/liver) -> photo placeholder
    bad = ("1682991136736-a2b44623eeba", "1527477396000-e27163b481c2", "1600180786608-28d06391d25c")
    if any(any(b in (x.get("image") or "") for b in bad) for x in p):
        for x in p:
            if any(b in (x.get("image") or "") for b in bad):
                x["image"] = ""
        store.set_json("products", p)
    return p


def save_products(p: list):
    store.set_json("products", p)


def unit_price(product: dict, settings: dict) -> int:
    if settings.get("rate_mode") == "manual" or product.get("pricing") == "manual":
        return int(round(float(product.get("manual_price") or 0)))
    rates = settings.get("rates") or {}
    base = float(rates.get(product.get("basis") or "broiler") or settings.get("paper_rate") or 0)
    return int(round(base * float(product.get("multiplier") or 1) + float(product.get("offset") or 0)))


def get_menu() -> dict:
    s = get_settings()
    items = []
    for p in get_raw_products():
        items.append({**p, "price": unit_price(p, s)})
    return {
        "rates": s["rates"],
        "paper_rate": s["rates"]["live"],
        "paper_rate_date": s["paper_rate_date"],
        "rate_is_today": s["paper_rate_date"] == today_ist(),
        "rate_mode": s["rate_mode"],
        "shop_open": s["shop_open"],
        "announcement": s["announcement"],
        "products": items,
    }


def set_rates(live: float, broiler: float, by: str):
    s = get_settings()
    s["rates"] = {"live": round(float(live), 2), "broiler": round(float(broiler), 2)}
    s["paper_rate"] = s["rates"]["live"]
    s["paper_rate_date"] = today_ist()
    save_settings(s)
    store.zadd("ratehist", now_ts(), f"{today_ist()}|{s['rates']['live']}|{by}|{int(now_ts())}|{s['rates']['broiler']}")
    return s


def rate_history(limit=30):
    out = []
    for m in store.zrevrange("ratehist", 0, limit - 1):
        d, r, by, ts, b = (m.split("|") + ["", "", "", "", ""])[:5]
        out.append({"date": d, "live": float(r or 0), "broiler": float(b) if b else None, "by": by, "ts": int(ts or 0)})
    return out
