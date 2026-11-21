"""Authentication.

Customers  – no account. At checkout they type name + mobile (+ optional email) and confirm the mobile
             ONCE with an SMS OTP. The device then stays verified for CUSTOMER_SESSION_DAYS (default 180).
Admin      – signs in with Clerk (Google / email). The server verifies the Clerk session, checks the email
             against ADMIN_EMAILS / SUPERADMIN_EMAILS / settings, and issues an app session that stays
             logged in on that phone for ADMIN_SESSION_DAYS (default 365).
Staff      – delivery boys can also log in once by mobile OTP (ADMIN_OTP_LOGIN=true) if their number is
             in Admin -> Settings -> Team.

Roles: superadmin (platform provider) > admin (shop owner) > staff > customer
Every user dict has: id ("<phone>" or "email:<email>"), phone, email, name, role.
"""
import base64
import hashlib
import hmac
import re
import secrets
import time

import httpx
import jwt
from fastapi import Depends, Header, HTTPException

from . import catalog, config, store

OTP_TTL = 300
MAX_ATTEMPTS = 5
RESEND_GAP = 30
STAFF_ROLES = ("superadmin", "admin", "staff")
ADMIN_ROLES = ("superadmin", "admin")


def norm_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if not re.fullmatch(r"[6-9]\d{9}", digits):
        raise HTTPException(400, "Enter a valid 10-digit mobile number.")
    return digits


def norm_email(email: str | None) -> str:
    e = (email or "").strip().lower()
    if e and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", e):
        raise HTTPException(400, "Email looks wrong – leave it empty if you don't have one.")
    return e


# ------------------------------------------------------------------ roles
def role_for_phone(phone: str) -> str:
    s = catalog.get_settings()
    if phone in config.SUPERADMIN_PHONES:
        return "superadmin"
    if phone in config.ADMIN_PHONES or phone in (s.get("admin_phones") or []):
        return "admin"
    if phone in (s.get("staff_phones") or []):
        return "staff"
    return "customer"


def role_for_email(email: str) -> str | None:
    s = catalog.get_settings()
    email = email.lower()
    if email in config.SUPERADMIN_EMAILS:
        return "superadmin"
    if email in config.ADMIN_EMAILS or email in (s.get("admin_emails") or []):
        return "admin"
    if email in (s.get("staff_emails") or []):
        return "staff"
    return None


def role_for_id(uid: str) -> str:
    if uid.startswith("email:"):
        return role_for_email(uid[6:]) or "none"
    return role_for_phone(uid)


def _issue(uid: str, role: str) -> str:
    days = config.ADMIN_SESSION_DAYS if role in STAFF_ROLES else config.CUSTOMER_SESSION_DAYS
    return jwt.encode({"sub": uid, "role": role, "iat": int(time.time()), "exp": int(time.time()) + days * 86400},
                      config.JWT_SECRET, algorithm="HS256")


# ------------------------------------------------------------------ OTP (customers + optional staff)
def _hash(phone: str, code: str) -> str:
    return hmac.new(config.JWT_SECRET.encode(), f"{phone}:{code}".encode(), hashlib.sha256).hexdigest()


def _send_sms(phone: str, code: str) -> bool:
    try:
        if config.SMS_PROVIDER == "msg91" and config.MSG91_AUTH_KEY:
            r = httpx.post("https://control.msg91.com/api/v5/otp",
                           params={"template_id": config.MSG91_TEMPLATE_ID, "mobile": f"91{phone}", "otp": code},
                           headers={"authkey": config.MSG91_AUTH_KEY}, timeout=10)
            return r.status_code == 200
        if config.SMS_PROVIDER == "fast2sms" and config.FAST2SMS_API_KEY:
            r = httpx.post("https://www.fast2sms.com/dev/bulkV2", headers={"authorization": config.FAST2SMS_API_KEY},
                           json={"route": "otp", "variables_values": code, "numbers": phone}, timeout=10)
            return r.status_code == 200
    except Exception:
        return False
    return False


def request_otp(phone: str) -> dict:
    phone = norm_phone(phone)
    prev = store.get_json(f"otp:{phone}")
    if prev and time.time() - prev.get("sent", 0) < RESEND_GAP:
        raise HTTPException(429, f"Please wait {RESEND_GAP} seconds before asking for another OTP.")
    code = f"{secrets.randbelow(900000) + 100000}"
    store.set_json(f"otp:{phone}", {"h": _hash(phone, code), "tries": 0, "sent": time.time()}, ex=OTP_TTL)
    sent = _send_sms(phone, code)
    out = {"ok": True, "phone": phone, "sms_sent": sent, "expires_in": OTP_TTL}
    if not sent:
        if not config.OTP_DEV_MODE:
            raise HTTPException(503, "SMS service is not available right now. Please call the shop.")
        out["dev_code"] = code  # DEMO ONLY – turn off with OTP_DEV_MODE=false once SMS is live
    return out


def verify_otp(phone: str, code: str, name: str | None = None, email: str | None = None) -> dict:
    phone = norm_phone(phone)
    email = norm_email(email)
    rec = store.get_json(f"otp:{phone}")
    if not rec:
        raise HTTPException(400, "OTP expired. Tap 'Resend OTP'.")
    if rec["tries"] >= MAX_ATTEMPTS:
        store.delete(f"otp:{phone}")
        raise HTTPException(429, "Too many wrong attempts. Ask for a new OTP.")
    if not hmac.compare_digest(rec["h"], _hash(phone, str(code).strip())):
        rec["tries"] += 1
        store.set_json(f"otp:{phone}", rec, ex=OTP_TTL)
        raise HTTPException(400, "Wrong OTP. Please check the SMS.")
    store.delete(f"otp:{phone}")
    role = role_for_phone(phone)
    if role in STAFF_ROLES and not config.ADMIN_OTP_LOGIN:
        role = "customer"  # staff must use Clerk sign-in; this number can still order as a customer
    user = store.get_json(f"user:{phone}") or {"phone": phone, "name": "", "email": "", "created": time.time(), "addresses": []}
    if name:
        user["name"] = name.strip()[:60]
    if email:
        user["email"] = email
    user.update(id=phone, role=role, verified=True, last_login=time.time())
    store.set_json(f"user:{phone}", user)
    store.record_customer(phone, user["name"], user.get("email"), verified=True)
    if role in STAFF_ROLES:
        store.audit(phone, "login.otp", {"role": role})
    return {"token": _issue(phone, role), "user": user}


# ------------------------------------------------------------------ Clerk (admin)
_jwks = {}


def clerk_frontend_api() -> str:
    pk = config.CLERK_PUBLISHABLE_KEY
    if not pk:
        return ""
    try:
        b = pk.split("_", 2)[2]
        return base64.b64decode(b + "=" * (-len(b) % 4)).decode().rstrip("$")
    except Exception:
        return ""


def _clerk_email(claims: dict) -> str:
    for k in ("email", "primary_email", "email_address"):
        if claims.get(k):
            return str(claims[k]).lower()
    if config.CLERK_SECRET_KEY:
        r = httpx.get(f"https://api.clerk.com/v1/users/{claims['sub']}",
                      headers={"Authorization": f"Bearer {config.CLERK_SECRET_KEY}"}, timeout=10)
        r.raise_for_status()
        u = r.json()
        primary = u.get("primary_email_address_id")
        for e in u.get("email_addresses", []):
            if e.get("id") == primary or not primary:
                return e["email_address"].lower()
    raise HTTPException(400, "Could not read your email from Clerk. Set CLERK_SECRET_KEY on the server.")


def clerk_login(session_token: str) -> dict:
    host = clerk_frontend_api()
    if not host:
        raise HTTPException(400, "Clerk is not configured.")
    if host not in _jwks:
        _jwks[host] = jwt.PyJWKClient(f"https://{host}/.well-known/jwks.json", cache_keys=True)
    try:
        key = _jwks[host].get_signing_key_from_jwt(session_token).key
        claims = jwt.decode(session_token, key, algorithms=["RS256"], leeway=60, options={"verify_aud": False})
    except Exception:
        raise HTTPException(401, "Sign-in expired. Please sign in again.")
    email = _clerk_email(claims)
    role = role_for_email(email)
    if not role:
        store.audit(f"email:{email}", "login.denied", {})
        raise HTTPException(403, f"{email} is not an admin of this shop. Ask the owner to add you in Settings → Team.")
    uid = f"email:{email}"
    user = store.get_json(f"user:{uid}") or {"email": email, "phone": "", "created": time.time()}
    user.update(id=uid, email=email, role=role, name=claims.get("name") or user.get("name") or email.split("@")[0],
                last_login=time.time())
    store.set_json(f"user:{uid}", user)
    store.audit(uid, "login.clerk", {"role": role})
    return {"token": _issue(uid, role), "user": user}


# ------------------------------------------------------------------ request dependencies
def current_user(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Please verify your mobile number.")
    try:
        claims = jwt.decode(authorization.split(" ", 1)[1], config.JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Session expired. Please verify again.")
    uid = claims["sub"]
    user = store.get_json(f"user:{uid}") or {"phone": "" if uid.startswith("email:") else uid, "name": ""}
    user["id"] = uid
    user.setdefault("phone", "" if uid.startswith("email:") else uid)
    role = role_for_id(uid)  # re-checked every request: removing someone takes effect immediately
    if role in STAFF_ROLES and not uid.startswith("email:") and not config.ADMIN_OTP_LOGIN:
        role = "customer"
    if role == "none":
        raise HTTPException(401, "Access removed. Please sign in again.")
    user["role"] = role
    return user


def optional_user(authorization: str | None = Header(default=None)) -> dict | None:
    try:
        return current_user(authorization)
    except HTTPException:
        return None


def require_staff(user: dict = Depends(current_user)) -> dict:
    if user["role"] not in STAFF_ROLES:
        raise HTTPException(403, "Shop staff only.")
    return user


def require_admin(user: dict = Depends(current_user)) -> dict:
    if user["role"] not in ADMIN_ROLES:
        raise HTTPException(403, "Admin only.")
    return user


def require_superadmin(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "superadmin":
        raise HTTPException(403, "Platform provider only.")
    return user
