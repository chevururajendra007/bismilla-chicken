"""Evaluation: known answers for the rules that matter. Run: JWT_SECRET=x... pytest -q"""
import os
import tempfile

os.environ["LOCAL_DB_PATH"] = tempfile.mktemp(suffix=".json")
os.environ.setdefault("JWT_SECRET", "test-secret-test-secret-test-secret-1234")
os.environ["OTP_DEV_MODE"] = "true"
os.environ["KV_REST_API_URL"] = ""

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402

c = TestClient(app)
KOTA = (14.0386, 80.0467)


def login(phone):
    code = c.post("/api/auth/otp/request", json={"phone": phone}).json()["dev_code"]
    r = c.post("/api/auth/otp/verify", json={"phone": phone, "code": code}).json()
    return {"Authorization": "Bearer " + r["token"]}, r["user"]["role"]


def test_owner_is_admin_customer_is_not():
    _, role = login("7904711708")
    assert role == "admin"
    h, role = login("9123456789")
    assert role == "customer"
    assert c.get("/api/admin/orders", headers=h).status_code == 403


def test_delivery_rules():
    q = lambda lng, kg: c.post("/api/delivery/quote", json={"lat": KOTA[0], "lng": lng, "weight_kg": kg}).json()
    assert q(80.0567, 1)["deliverable"] and q(80.0567, 1)["fee"] == 0        # ~1.4 km free
    assert not q(80.0800, 1)["deliverable"]                                  # ~4.7 km, <2 kg
    assert q(80.0800, 2)["deliverable"]                                      # ~4.7 km, 2 kg ok
    assert not q(80.1200, 5)["deliverable"]                                  # >5 km pickup only


def test_paper_rate_prices():
    h, _ = login("7904711708")
    m = c.post("/api/admin/rate", json={"paper_rate": 140, "notify": False}, headers=h).json()
    p = {x["id"]: x["price"] for x in m["products"]}
    assert p["live-broiler"] == 140 and p["skinless-curry"] == round(140 * 1.75)
    assert p["natu-kodi"] == 480  # manual price untouched


def test_server_reprices_order():
    h, _ = login("9123456780")
    o = c.post("/api/orders", headers=h, json={"items": [{"product_id": "live-broiler", "qty": 2, "price": 1}],
               "fulfilment": "pickup", "payment_method": "cod", "branch_id": "kota"}).json()
    assert o["total"] == o["items"][0]["price"] * 2 > 2
