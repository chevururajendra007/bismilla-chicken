"""Mobile-OTP login for customers, staff and admin.

Role resolution on every login:
  admin    -> phone in ADMIN_PHONES env (default: shop owner 7904711708) or settings.admin_phones
  staff    -> phone in settings.staff_phones (riders / counter)
  customer -> everyone else
"""
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


def norm_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if not re.fullmatch(r"[6-9]\d{9}", digits):
        raise HTTPException(400, "Enter a valid 10-digit Indian mobile number.")
    return digits


def role_for(phone: str) -> str:
    s = catalog.get_settings()
    if phone in config.ADMIN_PHONES or phone in (s.get("admin_phones") or []):
        return "admin"
    if phone in (s.get("staff_phones") or []):
        return "staff"
    return "customer"


def _hash(phone: str, code: str) -> str:
    return hmac.new(config.JWT_SECRET.encode(), f"{phone}:{code}".encode(), hashlib.sha256).hexdigest()


def _send_sms(phone: str, code: str) -> bool:
    try:
        if config.SMS_PROVIDER == "msg91" and config.MSG91_AUTH_KEY:
            r = httpx.post(
                "https://control.msg91.com/api/v5/otp",
                params={"template_id": config.MSG91_TEMPLATE_ID, "mobile": f"91{phone}", "otp": code},
                headers={"authkey": config.MSG91_AUTH_KEY}, timeout=10)
            return r.status_code == 200
        if config.SMS_PROVIDER == "fast2sms" and config.FAST2SMS_API_KEY:
            r = httpx.post(
                "https://www.fast2sms.com/dev/bulkV2",
                headers={"authorization": config.FAST2SMS_API_KEY},
                json={"route": "otp", "variables_values": code, "numbers": phone}, timeout=10)
            return r.status_code == 200
    except Exception:
        return False
    return False


def request_otp(phone: str) -> dict:
    phone = norm_phone(phone)
    prev = store.get_json(f"otp:{phone}")
    if prev and time.time() - prev.get("sent", 0) < RESEND_GAP:
        raise HTTPException(429, f"Please wait {RESEND_GAP} seconds before requesting another OTP.")
    code = f"{secrets.randbelow(900000) + 100000}"
    store.set_json(f"otp:{phone}", {"h": _hash(phone, code), "tries": 0, "sent": time.time()}, ex=OTP_TTL)
    sent = _send_sms(phone, code)
    out = {"ok": True, "phone": phone, "sms_sent": sent, "expires_in": OTP_TTL}
    if config.OTP_DEV_MODE and not sent:
        out["dev_code"] = code  # demo mode only – disable with OTP_DEV_MODE=false once SMS is configured
    if not sent and not config.OTP_DEV_MODE:
        raise HTTPException(503, "SMS service not configured. Contact the shop.")
    return out


def verify_otp(phone: str, code: str, name: str | None = None) -> dict:
    phone = norm_phone(phone)
    rec = store.get_json(f"otp:{phone}")
    if not rec:
        raise HTTPException(400, "OTP expired. Request a new one.")
    if rec["tries"] >= MAX_ATTEMPTS:
        store.delete(f"otp:{phone}")
        raise HTTPException(429, "Too many wrong attempts. Request a new OTP.")
    if not hmac.compare_digest(rec["h"], _hash(phone, str(code).strip())):
        rec["tries"] += 1
        store.set_json(f"otp:{phone}", rec, ex=OTP_TTL)
        raise HTTPException(400, "Wrong OTP.")
    store.delete(f"otp:{phone}")
    user = store.get_json(f"user:{phone}") or {"phone": phone, "name": "", "created": time.time(), "addresses": []}
    if name:
        user["name"] = name.strip()[:60]
    user["role"] = role_for(phone)
    user["last_login"] = time.time()
    store.set_json(f"user:{phone}", user)
    token = jwt.encode({"sub": phone, "role": user["role"], "exp": int(time.time()) + config.JWT_DAYS * 86400},
                       config.JWT_SECRET, algorithm="HS256")
    return {"token": token, "user": user}


def current_user(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Login required.")
    try:
        claims = jwt.decode(authorization.split(" ", 1)[1], config.JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Session expired. Please login again.")
    phone = claims["sub"]
    user = store.get_json(f"user:{phone}") or {"phone": phone, "name": ""}
    user["role"] = role_for(phone)  # re-check every request so removing an admin takes effect immediately
    return user


def optional_user(authorization: str | None = Header(default=None)) -> dict | None:
    try:
        return current_user(authorization)
    except HTTPException:
        return None


def require_staff(user: dict = Depends(current_user)) -> dict:
    if user["role"] not in ("admin", "staff"):
        raise HTTPException(403, "Staff only.")
    return user


def require_admin(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only.")
    return user
