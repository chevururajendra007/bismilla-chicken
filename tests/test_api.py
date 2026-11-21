"""Evaluation: known answers for the rules that matter.
Run:  pytest -q                       (local JSON store)
      TEST_DATABASE_URL=postgresql://... pytest -q   (Postgres)
"""
import os
import tempfile
from datetime import datetime, timedelta, timezone

os.environ["LOCAL_DB_PATH"] = tempfile.mktemp(suffix=".json")
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "")
os.environ.setdefault("JWT_SECRET", "test-secret-test-secret-test-secret-1234")
os.environ["OTP_DEV_MODE"] = "true"
os.environ["KV_REST_API_URL"] = ""
os.environ["SUPERADMIN_PHONES"] = "9000000009"

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402

c = TestClient(app)
KOTA = (14.0386, 80.0467)
TODAY = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d")


def login(phone, name="Test", email=None):
    code = c.post("/api/auth/otp/request", json={"phone": phone}).json()["dev_code"]
    r = c.post("/api/auth/otp/verify", json={"phone": phone, "code": code, "name": name, "email": email}).json()
    return {"Authorization": "Bearer " + r["token"]}, r["user"]["role"]


ADMIN, _ = login("7904711708")


def order(h, pay="cod", qty=1.5, mode="delivery", lng=80.0567):
    body = {"items": [{"product_id": "skinless-curry", "qty": qty}], "fulfilment": mode, "payment_method": pay,
            "name": "Ravi", "location": {"lat": KOTA[0], "lng": lng}, "address": "4-12 Gandhi street", "branch_id": "kota"}
    return c.post("/api/orders", json=body, headers=h)


def test_roles():
    _, role = login("7904711708")
    assert role == "admin"
    h, role = login("9123456789")
    assert role == "customer"
    assert c.get("/api/admin/orders", headers=h).status_code == 403
    _, role = login("9000000009")
    assert role == "superadmin"


def test_menu_without_login():
    assert c.get("/api/menu").status_code == 200
    assert c.post("/api/orders", json={}).status_code == 401  # ordering needs a verified mobile


def test_delivery_rules():
    q = lambda lng, kg: c.post("/api/delivery/quote", json={"lat": KOTA[0], "lng": lng, "weight_kg": kg}).json()
    assert q(80.0567, 1)["deliverable"] and q(80.0567, 1)["fee"] == 0
    assert not q(80.0800, 1)["deliverable"]
    assert q(80.0800, 2)["deliverable"]
    assert not q(80.1200, 5)["deliverable"]


def test_two_paper_rates_prices():
    m = c.post("/api/admin/rate", json={"live_rate": 210, "broiler_rate": 270, "notify": False}, headers=ADMIN).json()
    p = {x["id"]: x["price"] for x in m["products"]}
    assert m["rates"] == {"live": 210, "broiler": 270}
    assert p["live-broiler"] == 210 and p["skinless-curry"] == 270 and p["skin-curry"] == 250
    assert p["boneless"] == round(270 * 1.5)
    assert p["natu-kodi"] == 450  # manual price untouched
    assert c.post("/api/admin/rate", json={"live_rate": 5}, headers=ADMIN).status_code == 400


def test_products_have_photos_and_owner_upload():
    m = c.get("/api/menu").json()
    imgs = {x["id"]: x["image"] for x in m["products"]}
    assert imgs["skinless-curry"].startswith("https://images.unsplash.com") and "Raw_leg_chicken_quarters" in imgs["legs"]
    assert all(imgs[k] for k in ("wings", "liver-gizzard", "legs"))
    png = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    m = c.post("/api/admin/products/eggs/image", json={"data_url": png}, headers=ADMIN).json()
    url = next(x["image"] for x in m["products"] if x["id"] == "eggs")
    assert url.startswith("/api/img/eggs")
    r = c.get(url)
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"


def test_prepaid_blocks_cutting_until_paid():
    h, _ = login("9123456781", "Sita", "sita@example.com")
    o = order(h, "prepaid").json()
    assert o["awaiting_payment"] and o["upi_link"] and o["email"] == "sita@example.com"
    r = c.post(f"/api/admin/orders/{o['code']}/status", json={"status": "accepted"}, headers=ADMIN)
    assert r.status_code == 400
    c.post(f"/api/orders/{o['code']}/utr", json={"utr": "412345678901"}, headers=h)
    assert c.post(f"/api/admin/orders/{o['code']}/status", json={"status": "accepted"}, headers=ADMIN).status_code == 200


def test_payment_methods_and_cod_limit():
    h, _ = login("9123456782")
    assert order(h, "upi_delivery").json()["payment_label"] == "UPI at delivery"
    c.put("/api/admin/settings", json={"cod_max_amount": 200}, headers=ADMIN)
    assert order(h, "cod", qty=2).status_code == 400
    c.put("/api/admin/settings", json={"cod_max_amount": 0}, headers=ADMIN)


def test_cod_paid_on_delivery_and_history():
    h, _ = login("9123456783")
    o = order(h, "cod").json()
    for s in ["accepted", "preparing", "ready", "delivered"]:
        x = c.post(f"/api/admin/orders/{o['code']}/status", json={"status": s}, headers=ADMIN).json()
    assert x["payment_status"] == "paid"
    hist = c.get(f"/api/admin/history?date_from={TODAY}&date_to={TODAY}", headers=ADMIN).json()
    assert any(r["code"] == o["code"] for r in hist["orders"]) and hist["summary"]["collected"] >= o["total"]
    assert c.get(f"/api/admin/history?q={o['code'].lower()}&date_from={TODAY}&date_to={TODAY}", headers=ADMIN).json()["orders"][0]["code"] == o["code"]


def test_server_reprices_order():
    h, _ = login("9123456780")
    o = c.post("/api/orders", headers=h, json={"items": [{"product_id": "live-broiler", "qty": 2, "price": 1}], "name": "Anil",
               "fulfilment": "pickup", "payment_method": "cod", "branch_id": "kota"}).json()
    assert o["total"] == o["items"][0]["price"] * 2 > 2


def test_audit_and_platform():
    assert any(a["action"] == "rate.update" for a in c.get("/api/admin/audit", headers=ADMIN).json())
    assert c.get("/api/platform", headers=ADMIN).status_code == 403
    sa, _ = login("9000000009")
    r = c.put("/api/platform/subscription", json={"plan": "Standard", "monthly_fee": 499, "paid_until": TODAY}, headers=sa).json()
    assert r["state"] == "due_soon"
    assert c.get("/api/admin/settings", headers=ADMIN).json()["billing"]["state"] == "due_soon"
    p = c.get("/api/platform", headers=sa).json()
    assert p["usage"]["this_month"]["orders"] >= 1


def test_structured_address_rules():
    h, _ = login("9123456784")
    base = {"items": [{"product_id": "skinless-curry", "qty": 1}], "fulfilment": "delivery", "payment_method": "cod",
            "name": "Lakshmi", "location": {"lat": KOTA[0], "lng": 80.0567}}
    r = c.post("/api/orders", headers=h, json={**base, "address_parts": {"street": "Gandhi Nagar", "town": "Kota"}})
    assert r.status_code == 400 and "landmark" in r.json()["detail"]
    o = c.post("/api/orders", headers=h, json={**base, "address_parts": {"street": "Gandhi Nagar", "landmark": "Ramalayam", "town": "Kota"}}).json()
    assert o["address"] == "No door no., Gandhi Nagar, near Ramalayam, Kota"
    o = c.post("/api/orders", headers=h, json={**base, "address_parts": {"door_no": "4-12", "street": "Gandhi Nagar", "town": "Vidyanagar"}}).json()
    assert o["address"].startswith("D.No 4-12, Gandhi Nagar")
