"""FastAPI server – all routes live under /api. On Vercel it runs as one Python function (api/index.py)."""
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import agent
from core import auth, catalog, config, delivery, orders, push, store

app = FastAPI(title="Bismilla Chicken API", version=config.APP_VERSION)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# --------------------------------------------------------------------------- models
class OtpReq(BaseModel):
    phone: str


class OtpVerify(BaseModel):
    phone: str
    code: str
    name: str | None = None


class QuoteReq(BaseModel):
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
    paper_rate: float
    notify: bool = True


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
        "accept_cod": s["accept_cod"], "accept_phonepe": s["accept_phonepe"], "upi_id": config.UPI_ID,
    }


@app.get("/api/menu")
def menu():
    return catalog.get_menu()


@app.post("/api/delivery/quote")
def quote(q: QuoteReq):
    return delivery.quote(q.lat, q.lng, q.weight_kg, q.branch_id)


@app.post("/api/chat")
def chat(req: ChatReq, user: dict | None = Depends(auth.optional_user)):
    if not req.message.strip():
        raise HTTPException(400, "Empty message")
    return agent.chat(req.message, req.history, user["phone"] if user else None)


# --------------------------------------------------------------------------- auth
@app.post("/api/auth/otp/request")
def otp_request(r: OtpReq):
    return auth.request_otp(r.phone)


@app.post("/api/auth/otp/verify")
def otp_verify(r: OtpVerify):
    return auth.verify_otp(r.phone, r.code, r.name)


@app.get("/api/me")
def me(user: dict = Depends(auth.current_user)):
    return user


@app.post("/api/push/subscribe")
def push_subscribe(sub: dict, user: dict = Depends(auth.current_user)):
    if not sub.get("endpoint"):
        raise HTTPException(400, "Bad subscription")
    push.subscribe(user["phone"], sub)
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
    if o["phone"] != user["phone"] and user["role"] not in ("admin", "staff"):
        raise HTTPException(403, "Not your order.")
    return orders.public(o)


@app.post("/api/orders/{code}/utr")
def claim_paid(code: str, r: UtrReq, user: dict = Depends(auth.current_user)):
    return orders.claim_payment(code, r.utr, user)


@app.post("/api/orders/{code}/cancel")
def cancel(code: str, user: dict = Depends(auth.current_user)):
    o = orders.get(code)
    if o["phone"] != user["phone"]:
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
    return orders.mark_paid(code, r.paid)


@app.post("/api/admin/rate")
def admin_rate(r: RateReq, admin: dict = Depends(auth.require_admin)):
    if not (30 <= r.paper_rate <= 1000):
        raise HTTPException(400, "Paper rate looks wrong (₹30–₹1000).")
    catalog.set_paper_rate(r.paper_rate, admin["phone"])
    sent = 0
    if r.notify:
        m = catalog.get_menu()
        sk = next((p for p in m["products"] if p["id"] == "skinless-curry"), None)
        body = f"Paper rate ₹{r.paper_rate:g}/kg" + (f" · Skinless ₹{sk['price']}/kg" if sk else "")
        sent = push.broadcast(f"🐔 Today's chicken rate – {config.SHOP_NAME}", body, "/", customers_only=True)
    return {**catalog.get_menu(), "notified": sent}


@app.get("/api/admin/rate/history")
def admin_rate_hist(admin: dict = Depends(auth.require_admin)):
    return catalog.rate_history()


@app.put("/api/admin/products")
def admin_products(products: list[dict], admin: dict = Depends(auth.require_admin)):
    allowed = {"id", "name", "name_te", "category", "unit", "pricing", "multiplier", "offset", "manual_price",
               "emoji", "available", "desc"}
    clean = []
    for p in products:
        if not p.get("id") or not p.get("name"):
            raise HTTPException(400, "Each product needs id and name.")
        q = {k: v for k, v in p.items() if k in allowed}
        q["pricing"] = "manual" if q.get("pricing") == "manual" else "paper"
        q["unit"] = q.get("unit") or "kg"
        for k in ("multiplier", "offset", "manual_price"):
            q[k] = float(q.get(k) or 0)
        clean.append(q)
    catalog.save_products(clean)
    return catalog.get_menu()


@app.get("/api/admin/settings")
def admin_get_settings(admin: dict = Depends(auth.require_admin)):
    return {"settings": catalog.get_settings(), "branches": catalog.get_branches(), "env_admins": config.ADMIN_PHONES}


@app.put("/api/admin/settings")
def admin_put_settings(body: dict, admin: dict = Depends(auth.require_admin)):
    s = catalog.get_settings()
    for k in ("rate_mode", "shop_open", "accept_cod", "accept_phonepe", "announcement"):
        if k in body:
            s[k] = body[k]
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
    return {"sent": push.broadcast(r.title[:60], r.body[:160], "/", customers_only=True)}
