"""Orders: pricing is always recomputed on the server (never trust client prices).

Payment methods
  cod           Cash on delivery / cash at the shop counter
  upi_delivery  Pay by PhonePe / UPI when the chicken arrives (customer scans the shop QR)
  prepaid       Pay now by PhonePe / UPI. The shop does NOT start cutting until payment is
                claimed (UTR entered) or confirmed by the owner.  ("phonepe" from v1.0 == prepaid)
Every order is placed by a customer whose mobile number was verified by OTP.
"""
import math
import time
from urllib.parse import quote as urlq

from fastapi import HTTPException

from . import auth, catalog, config, delivery, push, store

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
PAY_LABELS = {"cod": "Cash", "upi_delivery": "UPI at delivery", "prepaid": "Prepaid (UPI)", "phonepe": "Prepaid (UPI)"}
FINAL = {"delivered", "picked_up", "cancelled"}


def upi_link(amount: float, order_code: str) -> str:
    return (f"upi://pay?pa={urlq(config.UPI_ID)}&pn={urlq(config.UPI_PAYEE_NAME)}"
            f"&am={amount:.2f}&cu=INR&tn={urlq('Order ' + order_code)}")


def phonepe_link(amount: float, order_code: str) -> str:
    return upi_link(amount, order_code).replace("upi://pay", "phonepe://pay")


def _save(o: dict, ev: str | None = None, actor: str = "", detail: dict | None = None):
    o["updated"] = time.time()
    store.set_json(f"order:{o['code']}", o)
    store.record_order(o)
    if ev:
        store.event(o["code"], ev, actor, detail)


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
        qty = round(qty * 4) / 4 if p["unit"] == "kg" else math.floor(qty)
        price = catalog.unit_price(p, s)
        amount = round(price * qty)
        lines.append({"product_id": p["id"], "name": p["name"], "name_te": p.get("name_te", ""), "unit": p["unit"],
                      "image": p.get("image"),
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
    if not user.get("phone"):
        raise HTTPException(400, "Please verify your mobile number to order.")
    lines, subtotal, weight = _price_cart(body.get("items") or [])
    mode = body.get("fulfilment")
    pay = body.get("payment_method")
    pay = "prepaid" if pay == "phonepe" else pay
    if mode not in ("delivery", "pickup"):
        raise HTTPException(400, "Choose door delivery or pickup.")
    allowed = {"cod": s["accept_cod"], "upi_delivery": s["accept_upi_delivery"], "prepaid": s["accept_prepaid"]}
    if pay not in allowed:
        raise HTTPException(400, "Choose a payment method.")
    if not allowed[pay]:
        raise HTTPException(400, f"{PAY_LABELS[pay]} is not available today.")
    name = (body.get("name") or user.get("name") or "").strip()[:60]
    if len(name) < 2:
        raise HTTPException(400, "Please enter your name.")
    email = auth.norm_email(body.get("email") or user.get("email"))

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
        ap = body.get("address_parts") or {}
        door = (ap.get("door_no") or "").strip()[:30]
        street = (ap.get("street") or "").strip()[:120]
        landmark = (ap.get("landmark") or "").strip()[:120]
        town = (ap.get("town") or "").strip()[:60]
        if ap:
            if len(street) < 3:
                raise HTTPException(400, "Enter your street / colony / area.")
            if not door and len(landmark) < 3:
                raise HTTPException(400, "No door number? Please give a landmark near your house (temple, school, shop).")
            addr = ", ".join(x for x in [f"D.No {door}" if door else "No door no.", street,
                                         f"near {landmark}" if landmark else "", town] if x)
        else:  # v1.1 clients
            addr = (body.get("address") or "").strip()[:300]
            if len(addr) < 5:
                raise HTTPException(400, "Enter house no / street / landmark.")
    else:
        if branch_id not in {b["id"] for b in catalog.get_branches()}:
            raise HTTPException(400, "Choose a pickup branch.")
        eta = s["delivery"]["prep_minutes"]

    total = round(subtotal + fee)
    cap = float(s.get("cod_max_amount") or 0)
    if cap and total > cap and pay != "prepaid":
        raise HTTPException(400, f"Orders above ₹{cap:g} must be prepaid. Please choose 'Pay now'.")

    seq = store.incr("orderseq")
    code = f"BC{catalog.today_ist()[2:].replace('-', '')}{seq:04d}"
    now = time.time()
    order = {
        "code": code, "phone": user["phone"], "name": name, "email": email,
        "branch_id": branch_id, "items": lines, "subtotal": round(subtotal), "delivery_fee": fee, "total": total,
        "weight_kg": round(weight, 2), "fulfilment": mode, "payment_method": pay,
        "payment_status": "pending", "utr": None,
        "address": addr, "address_parts": body.get("address_parts") or None, "lat": lat, "lng": lng, "distance_km": km, "eta_minutes": eta,
        "notes": (body.get("notes") or "").strip()[:200],
        "status": "placed", "history": [{"status": "placed", "ts": now}],
        "rider": None, "created": now, "updated": now, "promised_at": now + (eta or 20) * 60,
        "paper_rate": s["rates"]["live"], "rates": s["rates"],
    }
    _save(order, "placed", user["phone"], {"total": total, "payment_method": pay})
    store.zadd("orders", now, code)
    store.zadd(f"uorders:{user['phone']}", now, code)

    u = store.get_json(f"user:{user['phone']}") or {"phone": user["phone"]}
    u["name"], u["email"] = name, email or u.get("email", "")
    if mode == "delivery":
        saved = [a for a in (u.get("addresses") or []) if a.get("address") != addr][:3]
        u["addresses"] = [{"address": addr, "parts": body.get("address_parts"), "lat": lat, "lng": lng}] + saved
    store.set_json(f"user:{user['phone']}", u)
    store.record_customer(user["phone"], name, email, order_total=total)

    tag = {"cod": "💵 COD", "upi_delivery": "📱 UPI at door", "prepaid": "⏳ PREPAID – wait for payment"}[pay]
    push.notify_staff(f"🆕 New order {code} – ₹{total}", f"{order['weight_kg']} kg · {mode} · {tag}", f"/admin?order={code}")
    return public(order)


def get(code: str) -> dict:
    o = store.get_json(f"order:{code}")
    if not o:
        raise HTTPException(404, "Order not found.")
    if o.get("payment_method") == "phonepe":
        o["payment_method"] = "prepaid"
    return o


def public(o: dict) -> dict:
    out = dict(o)
    out["status_label"] = LABELS.get(o["status"], o["status"])
    out["payment_label"] = PAY_LABELS.get(o["payment_method"], o["payment_method"])
    out["awaiting_payment"] = o["payment_method"] == "prepaid" and o["payment_status"] == "pending" and o["status"] == "placed"
    b = {x["id"]: x for x in catalog.get_branches()}.get(o["branch_id"]) or {}
    out["branch"] = {k: b.get(k) for k in ("id", "name", "address", "lat", "lng", "phone")}
    if o["status"] not in FINAL:
        r = o.get("rider") or {}
        if o["status"] == "out_for_delivery" and r.get("lat") is not None and o.get("lat") is not None:
            d = delivery.road_km(r["lat"], r["lng"], o["lat"], o["lng"], catalog.get_settings()["delivery"]["road_factor"])
            out["live_eta_minutes"] = delivery.eta_minutes(d, include_prep=False)
            out["rider_distance_km"] = d
        else:
            out["live_eta_minutes"] = max(1, int((o["promised_at"] - time.time()) / 60))
    if o["payment_method"] in ("prepaid", "upi_delivery", "phonepe") and o["payment_status"] != "paid":
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
    if (status in ("accepted", "preparing") and o["payment_method"] == "prepaid"
            and o["payment_status"] == "pending" and by.get("role") != "customer"):
        raise HTTPException(400, "Prepaid order – payment not received yet. Ask the customer to pay, or tap 'Mark paid'.")
    if status == "ready" and o["fulfilment"] == "delivery":
        status = "out_for_delivery"
    actor = by.get("id") or by.get("phone")
    o["status"] = status
    o["history"].append({"status": status, "ts": time.time(), "by": actor})
    if status == "accepted":
        o["promised_at"] = time.time() + (o["eta_minutes"] or 20) * 60
    if status == "out_for_delivery" and not o.get("rider"):
        o["rider"] = {"id": actor, "name": by.get("name") or "Delivery partner", "lat": None, "lng": None, "ts": None}
    if status in ("delivered", "picked_up") and o["payment_method"] in ("cod", "upi_delivery"):
        o["payment_status"] = "paid"
    _save(o, f"status:{status}", actor)
    eta = ""
    if status in ("accepted", "out_for_delivery") and o.get("eta_minutes"):
        eta = f" · ETA ~{public(o).get('live_eta_minutes', o['eta_minutes'])} min"
    push.notify_user(o["phone"], f"{config.SHOP_NAME}: {LABELS[status]}", f"Order {code}{eta}", f"/track/{code}")
    return public(o)


def rider_location(code: str, lat: float, lng: float, by: dict) -> dict:
    o = get(code)
    if o["status"] != "out_for_delivery":
        raise HTTPException(400, "Order is not out for delivery.")
    r = o.get("rider") or {}
    o["rider"] = {**r, "id": by.get("id"), "name": r.get("name") or by.get("name") or "Delivery partner",
                  "lat": float(lat), "lng": float(lng), "ts": time.time()}
    store.set_json(f"order:{code}", o)  # frequent – not mirrored to history tables
    return public(o)


def claim_payment(code: str, utr: str, user: dict) -> dict:
    o = get(code)
    if o["phone"] != user.get("phone"):
        raise HTTPException(403, "Not your order.")
    utr = "".join(ch for ch in (utr or "") if ch.isalnum())[:22]
    if len(utr) < 6:
        raise HTTPException(400, "Enter the UPI transaction ID / UTR shown in PhonePe.")
    o["utr"] = utr
    o["payment_status"] = "claimed"
    _save(o, "payment:claimed", user["phone"], {"utr": utr, "amount": o["total"]})
    push.notify_staff(f"💰 Payment claimed {code}", f"₹{o['total']} · UTR {utr} – check PhonePe", f"/admin?order={code}")
    return public(o)


def mark_paid(code: str, paid: bool, by: dict) -> dict:
    o = get(code)
    o["payment_status"] = "paid" if paid else "pending"
    _save(o, "payment:paid" if paid else "payment:unpaid", by.get("id"), {"amount": o["total"], "utr": o.get("utr")})
    store.audit(by.get("id"), "payment.mark_paid" if paid else "payment.mark_unpaid", {"code": code, "amount": o["total"]})
    if paid:
        push.notify_user(o["phone"], f"{config.SHOP_NAME}: Payment received ✅", f"₹{o['total']} for order {code}", f"/track/{code}")
    return public(o)


def summarize(orders_list: list) -> dict:
    valid = [o for o in orders_list if o["status"] != "cancelled"]
    by_pay = {}
    for o in valid:
        k = PAY_LABELS.get(o["payment_method"], o["payment_method"])
        by_pay[k] = by_pay.get(k, 0) + o["total"]
    return {
        "orders": len(valid),
        "cancelled": len(orders_list) - len(valid),
        "kg": round(sum(o["weight_kg"] for o in valid), 2),
        "revenue": sum(o["total"] for o in valid),
        "collected": sum(o["total"] for o in valid if o["payment_status"] == "paid"),
        "pending_payments": sum(o["total"] for o in valid if o["payment_status"] != "paid"),
        "by_payment": by_pay,
        "customers": len({o["phone"] for o in valid}),
        "delivery_share": round(100 * len([o for o in valid if o["fulfilment"] == "delivery"]) / len(valid)) if valid else 0,
    }


def stats() -> dict:
    today = catalog.today_ist()
    s = summarize(store.history(today, today))
    active = len([o for o in all_orders(100, active_only=True)])
    return {"orders_today": s["orders"], "kg_today": s["kg"], "revenue_today": s["revenue"],
            "pending_payments": s["pending_payments"], "active": active, "delivery_share": s["delivery_share"]}
