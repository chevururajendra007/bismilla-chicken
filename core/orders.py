"""Orders: pricing is always recomputed on the server (never trust client prices)."""
import math
import time
from urllib.parse import quote as urlq

from fastapi import HTTPException

from . import catalog, config, delivery, push, store

STATUSES = ["placed", "accepted", "preparing", "ready", "out_for_delivery", "delivered", "picked_up", "cancelled"]
LABELS = {
    "placed": "Order placed",
    "accepted": "Order accepted by shop",
    "preparing": "Cutting & cleaning your chicken",
    "ready": "Ready for pickup",
    "out_for_delivery": "Out for delivery",
    "delivered": "Delivered",
    "picked_up": "Picked up",
    "cancelled": "Cancelled",
}
FINAL = {"delivered", "picked_up", "cancelled"}


def upi_link(amount: float, order_code: str) -> str:
    return (f"upi://pay?pa={urlq(config.UPI_ID)}&pn={urlq(config.UPI_PAYEE_NAME)}"
            f"&am={amount:.2f}&cu=INR&tn={urlq('Order ' + order_code)}")


def phonepe_link(amount: float, order_code: str) -> str:
    # Opens PhonePe directly on Android; other UPI apps can use upi_link.
    return upi_link(amount, order_code).replace("upi://pay", "phonepe://pay")


def _price_cart(items: list) -> tuple[list, float, float]:
    s = catalog.get_settings()
    products = {p["id"]: p for p in catalog.get_raw_products()}
    lines, subtotal, weight = [], 0.0, 0.0
    for it in items:
        p = products.get(it.get("product_id"))
        if not p or not p.get("available", True):
            raise HTTPException(400, f"Item not available: {it.get('product_id')}")
        qty = float(it.get("qty") or 0)
        if qty <= 0 or qty > 50:
            raise HTTPException(400, "Invalid quantity.")
        if p["unit"] == "kg":
            qty = round(qty * 4) / 4  # 250 g steps
        else:
            qty = math.floor(qty)
        price = catalog.unit_price(p, s)
        amount = round(price * qty)
        lines.append({"product_id": p["id"], "name": p["name"], "name_te": p.get("name_te", ""), "unit": p["unit"],
                      "qty": qty, "price": price, "amount": amount, "note": (it.get("note") or "")[:120]})
        subtotal += amount
        if p["unit"] == "kg":
            weight += qty
    if not lines:
        raise HTTPException(400, "Cart is empty.")
    return lines, subtotal, weight


def create(user: dict, body: dict) -> dict:
    s = catalog.get_settings()
    if not s.get("shop_open", True):
        raise HTTPException(400, "Shop is closed right now. Please try later.")
    lines, subtotal, weight = _price_cart(body.get("items") or [])
    mode = body.get("fulfilment")
    pay = body.get("payment_method")
    if mode not in ("delivery", "pickup"):
        raise HTTPException(400, "Choose delivery or pickup.")
    if pay not in ("cod", "phonepe"):
        raise HTTPException(400, "Choose a payment method.")
    if pay == "cod" and not s.get("accept_cod", True):
        raise HTTPException(400, "Cash on delivery is paused today.")
    if pay == "phonepe" and not s.get("accept_phonepe", True):
        raise HTTPException(400, "PhonePe is paused today.")

    fee, km, eta, addr, lat, lng = 0, None, None, None, None, None
    branch_id = body.get("branch_id")
    if mode == "delivery":
        loc = body.get("location") or {}
        try:
            lat, lng = float(loc["lat"]), float(loc["lng"])
        except Exception:
            raise HTTPException(400, "Pick your delivery location on the map.")
        q = delivery.quote(lat, lng, weight, branch_id)
        if not q["deliverable"]:
            raise HTTPException(400, q["reason"])
        fee, km, eta, branch_id = q["fee"], q["distance_km"], q["eta_minutes"], q["branch_id"]
        addr = (body.get("address") or "").strip()[:300]
        if len(addr) < 5:
            raise HTTPException(400, "Enter house no / street / landmark.")
    else:
        branches = {b["id"]: b for b in catalog.get_branches()}
        if branch_id not in branches:
            raise HTTPException(400, "Choose a pickup branch.")
        eta = s["delivery"]["prep_minutes"]

    seq = store.incr("orderseq")
    code = f"BC{catalog.today_ist()[2:].replace('-', '')}{seq:04d}"
    now = time.time()
    total = round(subtotal + fee)
    order = {
        "code": code, "phone": user["phone"], "name": (body.get("name") or user.get("name") or "").strip()[:60],
        "branch_id": branch_id, "items": lines, "subtotal": round(subtotal), "delivery_fee": fee, "total": total,
        "weight_kg": round(weight, 2), "fulfilment": mode, "payment_method": pay,
        "payment_status": "pending", "utr": None,
        "address": addr, "lat": lat, "lng": lng, "distance_km": km, "eta_minutes": eta,
        "notes": (body.get("notes") or "").strip()[:200],
        "status": "placed", "history": [{"status": "placed", "ts": now}],
        "rider": None, "created": now, "updated": now, "promised_at": now + (eta or 20) * 60,
        "paper_rate": s["paper_rate"],
    }
    store.set_json(f"order:{code}", order)
    store.zadd("orders", now, code)
    store.zadd(f"uorders:{user['phone']}", now, code)
    # remember address for next time
    if mode == "delivery":
        u = store.get_json(f"user:{user['phone']}") or {"phone": user["phone"]}
        saved = [a for a in (u.get("addresses") or []) if a.get("address") != addr][:3]
        u["addresses"] = [{"address": addr, "lat": lat, "lng": lng}] + saved
        if order["name"] and not u.get("name"):
            u["name"] = order["name"]
        store.set_json(f"user:{user['phone']}", u)
    push.notify_staff(f"🆕 New order {code} – ₹{total}",
                      f"{order['weight_kg']} kg · {mode} · {'COD' if pay == 'cod' else 'PhonePe'}", f"/admin?order={code}")
    return public(order)


def get(code: str) -> dict:
    o = store.get_json(f"order:{code}")
    if not o:
        raise HTTPException(404, "Order not found.")
    return o


def public(o: dict) -> dict:
    out = dict(o)
    out["status_label"] = LABELS.get(o["status"], o["status"])
    b = {x["id"]: x for x in catalog.get_branches()}.get(o["branch_id"]) or {}
    out["branch"] = {k: b.get(k) for k in ("id", "name", "address", "lat", "lng", "phone")}
    # live ETA
    if o["status"] not in FINAL:
        if (o["status"] == "out_for_delivery" and o.get("rider") and o["rider"].get("lat") is not None
                and o.get("lat") is not None):
            r = o["rider"]
            d = delivery.road_km(r["lat"], r["lng"], o["lat"], o["lng"], catalog.get_settings()["delivery"]["road_factor"])
            out["live_eta_minutes"] = delivery.eta_minutes(d, include_prep=False)
            out["rider_distance_km"] = d
        else:
            out["live_eta_minutes"] = max(1, int((o["promised_at"] - time.time()) / 60))
    if o["payment_method"] == "phonepe" and o["payment_status"] != "paid":
        out["upi_link"] = upi_link(o["total"], o["code"])
        out["phonepe_link"] = phonepe_link(o["total"], o["code"])
        out["upi_id"] = config.UPI_ID
    return out


def for_user(phone: str, limit=30) -> list:
    out = []
    for c in store.zrevrange(f"uorders:{phone}", 0, limit - 1):
        o = store.get_json(f"order:{c}")
        if o:
            out.append(public(o))
    return out


def all_orders(limit=100, active_only=False) -> list:
    out = []
    for c in store.zrevrange("orders", 0, limit - 1):
        o = store.get_json(f"order:{c}")
        if o and (not active_only or o["status"] not in FINAL):
            out.append(public(o))
    return out


def set_status(code: str, status: str, by: dict) -> dict:
    if status not in STATUSES:
        raise HTTPException(400, "Bad status.")
    o = get(code)
    if o["status"] in FINAL and status != o["status"]:
        raise HTTPException(400, "Order already closed.")
    if status == "ready" and o["fulfilment"] == "delivery":
        status = "out_for_delivery"
    o["status"] = status
    o["history"].append({"status": status, "ts": time.time(), "by": by["phone"]})
    o["updated"] = time.time()
    if status == "accepted":
        o["promised_at"] = time.time() + (o["eta_minutes"] or 20) * 60
    if status == "out_for_delivery" and not o.get("rider"):
        o["rider"] = {"phone": by["phone"], "name": by.get("name") or "Delivery partner", "lat": None, "lng": None, "ts": None}
    if status in ("delivered", "picked_up") and o["payment_method"] == "cod":
        o["payment_status"] = "paid"
    store.set_json(f"order:{code}", o)
    eta = ""
    if status in ("accepted", "out_for_delivery") and o.get("eta_minutes"):
        eta = f" · ETA ~{public(o).get('live_eta_minutes', o['eta_minutes'])} min"
    push.notify_user(o["phone"], f"{config.SHOP_NAME}: {LABELS[status]}", f"Order {code}{eta}", f"/track/{code}")
    return public(o)


def rider_location(code: str, lat: float, lng: float, by: dict) -> dict:
    o = get(code)
    if o["status"] != "out_for_delivery":
        raise HTTPException(400, "Order is not out for delivery.")
    o["rider"] = {**(o.get("rider") or {}), "phone": by["phone"], "name": (o.get("rider") or {}).get("name") or by.get("name") or "Delivery partner",
                  "lat": float(lat), "lng": float(lng), "ts": time.time()}
    store.set_json(f"order:{code}", o)
    return public(o)


def claim_payment(code: str, utr: str, user: dict) -> dict:
    o = get(code)
    if o["phone"] != user["phone"]:
        raise HTTPException(403, "Not your order.")
    utr = "".join(ch for ch in (utr or "") if ch.isalnum())[:22]
    if len(utr) < 6:
        raise HTTPException(400, "Enter the UPI transaction ID / UTR shown in PhonePe.")
    o["utr"] = utr
    o["payment_status"] = "claimed"
    store.set_json(f"order:{code}", o)
    push.notify_staff(f"💰 Payment claimed {code}", f"₹{o['total']} · UTR {utr} – verify in PhonePe", f"/admin?order={code}")
    return public(o)


def mark_paid(code: str, paid: bool) -> dict:
    o = get(code)
    o["payment_status"] = "paid" if paid else "pending"
    store.set_json(f"order:{code}", o)
    if paid:
        push.notify_user(o["phone"], f"{config.SHOP_NAME}: Payment received ✅", f"₹{o['total']} for order {code}", f"/track/{code}")
    return public(o)


def stats() -> dict:
    today = catalog.today_ist()
    todays = [o for o in all_orders(300) if time.strftime("%Y-%m-%d", time.gmtime(o["created"] + 19800)) == today]
    valid = [o for o in todays if o["status"] != "cancelled"]
    return {
        "orders_today": len(valid),
        "kg_today": round(sum(o["weight_kg"] for o in valid), 2),
        "revenue_today": sum(o["total"] for o in valid),
        "pending_payments": sum(o["total"] for o in valid if o["payment_status"] != "paid"),
        "active": len([o for o in valid if o["status"] not in FINAL]),
        "delivery_share": round(100 * len([o for o in valid if o["fulfilment"] == "delivery"]) / len(valid)) if valid else 0,
    }
