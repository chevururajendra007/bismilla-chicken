"""FastAPI server – all routes live under /api. On Vercel it runs as one Python function (api/index.py)."""
import base64
import re
import time
from datetime import datetime, timedelta

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import agent
from core import auth, catalog, config, delivery, geo, orders, push, store

app = FastAPI(title="Bismilla Chicken API", version=config.APP_VERSION)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# --------------------------------------------------------------------------- models
class OtpReq(BaseModel):
    phone: str


class OtpVerify(BaseModel):
    phone: str
    code: str
    name: str | None = None
    email: str | None = None


class ClerkReq(BaseModel):
    token: str


class SubReq(BaseModel):
    plan: str = "Standard"
    monthly_fee: float = 499
    paid_until: str | None = None
    provider: str = "Rajendra Chevuru"
    provider_phone: str = ""
    notes: str = ""


class QuoteReq(BaseModel):  # weight_kg includes cooked plates (0.5 kg each)
    lat: float
    lng: float
    weight_kg: float = 1
    branch_id: str | None = None


class ChatReq(BaseModel):
    message: str
    history: list = []


class StatusReq(BaseModel):
    status: str


class LocReq(BaseModel):
    lat: float
    lng: float


class UtrReq(BaseModel):
    utr: str


class PaidReq(BaseModel):
    paid: bool = True


class RateReq(BaseModel):
    live_rate: float | None = None
    broiler_rate: float | None = None
    paper_rate: float | None = None  # v1.1 clients: treated as live rate
    notify: bool = True


class ImageReq(BaseModel):
    data_url: str


class BroadcastReq(BaseModel):
    title: str
    body: str


# --------------------------------------------------------------------------- public
@app.get("/api/health")
def health():
    return {"ok": True, "version": config.APP_VERSION, "storage": store.backend_name(),
            "push": push.enabled(), "llm": agent.llm_status()}


@app.get("/api/config")
def public_config():
    s = catalog.get_settings()
    return {
        "shop_name": config.SHOP_NAME, "shop_phone": config.SHOP_PHONE, "version": config.APP_VERSION,
        "google_maps_key": config.GOOGLE_MAPS_API_KEY, "vapid_public_key": config.VAPID_PUBLIC_KEY,
        "branches": catalog.get_branches(), "delivery": s["delivery"],
        "accept_cod": s["accept_cod"], "accept_upi_delivery": s["accept_upi_delivery"],
        "accept_prepaid": s["accept_prepaid"], "cod_max_amount": s.get("cod_max_amount") or 0, "upi_id": config.UPI_ID,
        "clerk_publishable_key": config.CLERK_PUBLISHABLE_KEY, "clerk_frontend_api": auth.clerk_frontend_api(),
        "admin_otp_login": config.ADMIN_OTP_LOGIN,
    }


@app.get("/api/menu")
def menu():
    return catalog.get_menu()


@app.get("/api/geocode")
def geocode(q: str, town: str = ""):
    """Address -> map suggestions (biased to Kota / Vidyanagar)."""
    return {"results": geo.search(q[:120], town[:40])}


@app.get("/api/geocode/reverse")
def geocode_reverse(lat: float, lng: float):
    return geo.reverse(lat, lng)


@app.post("/api/delivery/quote")
def quote(q: QuoteReq):
    return delivery.quote(q.lat, q.lng, q.weight_kg, q.branch_id)


@app.post("/api/chat")
def chat(req: ChatReq, user: dict | None = Depends(auth.optional_user)):
    if not req.message.strip():
        raise HTTPException(400, "Empty message")
    return agent.chat(req.message, req.history, (user or {}).get("phone") or None)


# --------------------------------------------------------------------------- auth
@app.post("/api/auth/otp/request")
def otp_request(r: OtpReq):
    return auth.request_otp(r.phone)


@app.post("/api/auth/otp/verify")
def otp_verify(r: OtpVerify):
    return auth.verify_otp(r.phone, r.code, r.name, r.email)


@app.post("/api/auth/clerk")
def clerk_login(r: ClerkReq):
    """Exchange a Clerk session token for a long-lived admin session on this device."""
    return auth.clerk_login(r.token)


@app.get("/api/me")
def me(user: dict = Depends(auth.current_user)):
    return user


@app.post("/api/push/subscribe")
def push_subscribe(sub: dict, user: dict = Depends(auth.current_user)):
    if not sub.get("endpoint"):
        raise HTTPException(400, "Bad subscription")
    push.subscribe(user["id"], sub)
    return {"ok": True}


# --------------------------------------------------------------------------- customer orders
@app.post("/api/orders")
def create_order(body: dict, user: dict = Depends(auth.current_user)):
    return orders.create(user, body)


@app.get("/api/orders")
def my_orders(user: dict = Depends(auth.current_user)):
    return orders.for_user(user["phone"])


@app.get("/api/orders/{code}")
def get_order(code: str, user: dict = Depends(auth.current_user)):
    o = orders.get(code)
    if o["phone"] != user.get("phone") and user["role"] not in auth.STAFF_ROLES:
        raise HTTPException(403, "Not your order.")
    return orders.public(o)


@app.post("/api/orders/{code}/utr")
def claim_paid(code: str, r: UtrReq, user: dict = Depends(auth.current_user)):
    return orders.claim_payment(code, r.utr, user)


@app.post("/api/orders/{code}/cancel")
def cancel(code: str, user: dict = Depends(auth.current_user)):
    o = orders.get(code)
    if o["phone"] != user.get("phone"):
        raise HTTPException(403, "Not your order.")
    if o["status"] != "placed":
        raise HTTPException(400, "Order already accepted – please call the shop to cancel.")
    return orders.set_status(code, "cancelled", user)


# --------------------------------------------------------------------------- staff / admin
@app.get("/api/admin/orders")
def admin_orders(active: bool = False, staff: dict = Depends(auth.require_staff)):
    return {"orders": orders.all_orders(150, active_only=active), "stats": orders.stats()}


@app.post("/api/admin/orders/{code}/status")
def admin_status(code: str, r: StatusReq, staff: dict = Depends(auth.require_staff)):
    return orders.set_status(code, r.status, staff)


@app.post("/api/admin/orders/{code}/location")
def rider_loc(code: str, r: LocReq, staff: dict = Depends(auth.require_staff)):
    return orders.rider_location(code, r.lat, r.lng, staff)


@app.post("/api/admin/orders/{code}/paid")
def admin_paid(code: str, r: PaidReq, staff: dict = Depends(auth.require_staff)):
    return orders.mark_paid(code, r.paid, staff)


@app.post("/api/admin/rate")
def admin_rate(r: RateReq, admin: dict = Depends(auth.require_admin)):
    cur = catalog.get_settings()["rates"]
    live = r.live_rate if r.live_rate is not None else (r.paper_rate if r.paper_rate is not None else cur["live"])
    broiler = r.broiler_rate if r.broiler_rate is not None else cur["broiler"]
    for name, v in (("Live", live), ("Broiler", broiler)):
        if not (30 <= float(v) <= 1500):
            raise HTTPException(400, f"{name} rate looks wrong (₹30–₹1500).")
    catalog.set_rates(live, broiler, admin["id"])
    store.audit(admin["id"], "rate.update", {"from": cur, "to": {"live": live, "broiler": broiler}})
    sent = 0
    if r.notify:
        body = f"Live ₹{live:g}/kg · Broiler ₹{broiler:g}/kg – order fresh now"
        sent = push.broadcast(f"🐔 Today's paper rate – {config.SHOP_NAME}", body, "/", customers_only=True)
    return {**catalog.get_menu(), "notified": sent}


@app.get("/api/admin/rate/history")
def admin_rate_hist(admin: dict = Depends(auth.require_admin)):
    return catalog.rate_history()


@app.put("/api/admin/products")
def admin_products(products: list[dict], admin: dict = Depends(auth.require_admin)):
    allowed = {"id", "name", "name_te", "category", "unit", "pricing", "basis", "multiplier", "offset", "manual_price",
               "emoji", "available", "desc", "image", "badge", "credit", "serving", "equiv_kg", "prep_extra"}
    clean = []
    for p in products:
        if not p.get("id") or not p.get("name"):
            raise HTTPException(400, "Each product needs id and name.")
        q = {k: v for k, v in p.items() if k in allowed}
        q["pricing"] = "manual" if q.get("pricing") == "manual" else "paper"
        q["basis"] = "live" if q.get("basis") == "live" else "broiler"
        q["unit"] = q.get("unit") or "kg"
        for k in ("multiplier", "offset", "manual_price"):
            q[k] = float(q.get(k) or 0)
        clean.append(q)
    catalog.save_products(clean)
    store.audit(admin["id"], "products.update", {"count": len(clean)})
    return catalog.get_menu()


def billing_status(s: dict) -> dict:
    sub = s["subscription"]
    out = {**sub, "state": "unknown", "days_left": None}
    if sub.get("paid_until"):
        days = (datetime.strptime(sub["paid_until"], "%Y-%m-%d").date() - datetime.strptime(catalog.today_ist(), "%Y-%m-%d").date()).days
        out["days_left"] = days
        out["state"] = "active" if days > 5 else "due_soon" if days >= 0 else "overdue"
    return out


@app.post("/api/admin/products/{pid}/image")
def admin_product_image(pid: str, r: ImageReq, admin: dict = Depends(auth.require_admin)):
    """Owner uploads his own photo (resized on the phone to ~800px JPEG). Stored in the database."""
    m = re.fullmatch(r"data:(image/(?:jpeg|png|webp));base64,([A-Za-z0-9+/=]+)", r.data_url.strip())
    if not m:
        raise HTTPException(400, "Please choose a JPG, PNG or WEBP photo.")
    raw = base64.b64decode(m.group(2))
    if len(raw) > 600_000:
        raise HTTPException(400, "Photo too large – please use a smaller photo.")
    products = catalog.get_raw_products()
    if pid not in {p["id"] for p in products}:
        raise HTTPException(404, "Product not found.")
    store.set_json(f"img:{pid}", {"ct": m.group(1), "b64": m.group(2)})
    ver = int(time.time())
    for p in products:
        if p["id"] == pid:
            p["image"] = f"/api/img/{pid}?v={ver}"
            p.pop("credit", None)
    catalog.save_products(products)
    store.audit(admin["id"], "product.photo", {"id": pid, "bytes": len(raw)})
    return catalog.get_menu()


@app.get("/api/img/{pid}")
def product_image(pid: str):
    rec = store.get_json(f"img:{pid}")
    if not rec:
        raise HTTPException(404, "No photo")
    return Response(content=base64.b64decode(rec["b64"]), media_type=rec["ct"],
                    headers={"Cache-Control": "public, max-age=31536000, immutable"})


@app.get("/api/admin/settings")
def admin_get_settings(admin: dict = Depends(auth.require_admin)):
    s = catalog.get_settings()
    return {"settings": s, "branches": catalog.get_branches(), "env_admins": config.ADMIN_PHONES,
            "env_admin_emails": config.ADMIN_EMAILS, "billing": billing_status(s), "me": admin}


@app.put("/api/admin/settings")
def admin_put_settings(body: dict, admin: dict = Depends(auth.require_admin)):
    s = catalog.get_settings()
    for k in ("rate_mode", "shop_open", "accept_cod", "accept_upi_delivery", "accept_prepaid", "announcement"):
        if k in body:
            s[k] = body[k]
    if "cod_max_amount" in body:
        s["cod_max_amount"] = float(body["cod_max_amount"] or 0)
    for k in ("staff_emails", "admin_emails"):
        if k in body:
            s[k] = sorted({auth.norm_email(e) for e in body[k] if str(e).strip()})
    if s["rate_mode"] not in ("paper", "manual"):
        s["rate_mode"] = "paper"
    if "delivery" in body:
        for k, v in body["delivery"].items():
            if k in s["delivery"]:
                s["delivery"][k] = float(v)
    for k in ("staff_phones", "admin_phones"):
        if k in body:
            s[k] = sorted({auth.norm_phone(p) for p in body[k] if str(p).strip()})
    catalog.save_settings(s)
    store.audit(admin["id"], "settings.update", {k: body[k] for k in body if k not in ("branches", "subscription", "settings", "billing", "me")})
    if "branches" in body:
        bs = []
        for b in body["branches"]:
            bs.append({"id": b["id"], "name": b["name"], "name_te": b.get("name_te", ""), "address": b["address"],
                       "lat": float(b["lat"]), "lng": float(b["lng"]), "phone": b.get("phone", config.SHOP_PHONE),
                       "open": bool(b.get("open", True)), "hours": b.get("hours", "")})
        catalog.save_branches(bs)
    return admin_get_settings(admin)


@app.post("/api/admin/broadcast")
def admin_broadcast(r: BroadcastReq, admin: dict = Depends(auth.require_admin)):
    store.audit(admin["id"], "broadcast", {"title": r.title})
    return {"sent": push.broadcast(r.title[:60], r.body[:160], "/", customers_only=True)}


# --------------------------------------------------------------------------- history & reports
@app.get("/api/admin/history")
def admin_history(date_from: str | None = None, date_to: str | None = None, q: str = "", status: str = "",
                  admin: dict = Depends(auth.require_admin)):
    today = catalog.today_ist()
    d1, d2 = date_from or today, date_to or today
    rows = store.history(d1, d2, q, status)
    customers = {}
    for o in rows:
        if o["status"] == "cancelled":
            continue
        c = customers.setdefault(o["phone"], {"phone": o["phone"], "name": o.get("name"), "orders": 0, "total": 0, "kg": 0})
        c["orders"] += 1
        c["total"] += o["total"]
        c["kg"] = round(c["kg"] + o["weight_kg"], 2)
    return {"from": d1, "to": d2, "orders": [orders.public(o) for o in rows], "summary": orders.summarize(rows),
            "top_customers": sorted(customers.values(), key=lambda c: -c["total"])[:20]}


@app.get("/api/admin/orders/{code}/events")
def admin_order_events(code: str, staff: dict = Depends(auth.require_staff)):
    o = orders.get(code)
    return {"history": o.get("history", []), "payment_status": o["payment_status"], "utr": o.get("utr")}


@app.get("/api/admin/audit")
def admin_audit(admin: dict = Depends(auth.require_admin)):
    return store.audit_log(200)


# --------------------------------------------------------------------------- platform (provider / superadmin)
@app.get("/api/platform")
def platform(sa: dict = Depends(auth.require_superadmin)):
    s = catalog.get_settings()
    today = datetime.strptime(catalog.today_ist(), "%Y-%m-%d")
    this_m = today.replace(day=1)
    last_m = (this_m - timedelta(days=1)).replace(day=1)
    usage = {
        "this_month": orders.summarize(store.history(this_m.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"))),
        "last_month": orders.summarize(store.history(last_m.strftime("%Y-%m-%d"), (this_m - timedelta(days=1)).strftime("%Y-%m-%d"))),
    }
    return {"version": config.APP_VERSION, "storage": store.backend_name(), "push": push.enabled(),
            "llm": agent.llm_status(), "clerk": bool(config.CLERK_PUBLISHABLE_KEY), "sms": config.SMS_PROVIDER or None,
            "otp_dev_mode": config.OTP_DEV_MODE, "billing": billing_status(s), "usage": usage,
            "admins": {"emails": config.ADMIN_EMAILS + (s.get("admin_emails") or []),
                       "phones": config.ADMIN_PHONES + (s.get("admin_phones") or [])}}


@app.put("/api/platform/subscription")
def platform_subscription(r: SubReq, sa: dict = Depends(auth.require_superadmin)):
    if r.paid_until:
        datetime.strptime(r.paid_until, "%Y-%m-%d")
    s = catalog.get_settings()
    s["subscription"] = r.model_dump()
    catalog.save_settings(s)
    store.audit(sa["id"], "subscription.update", r.model_dump())
    return billing_status(s)
