"""Web Push notifications (works on Android Chrome, desktop browsers and installed iOS PWAs 16.4+).

Subscriptions are stored per phone. Admin/staff subscriptions also get "new order" alerts.
"""
import json
import time

from . import auth, catalog, config, store

try:
    from pywebpush import WebPushException, webpush
except Exception:  # pragma: no cover
    webpush = None
    WebPushException = Exception


def enabled() -> bool:
    return bool(webpush and config.VAPID_PUBLIC_KEY and config.VAPID_PRIVATE_KEY)


def subscribe(uid: str, sub: dict):
    """uid = phone for customers/OTP staff, 'email:<x>' for Clerk admins."""
    subs = store.get_json(f"push:{uid}", []) or []
    subs = [s for s in subs if s.get("endpoint") != sub.get("endpoint")] + [sub]
    store.set_json(f"push:{uid}", subs[-5:])  # keep last 5 devices
    store.zadd("pushusers", time.time(), uid)


def _send(phone: str, payload: dict) -> int:
    if not enabled():
        return 0
    subs = store.get_json(f"push:{phone}", []) or []
    keep, sent = [], 0
    for s in subs:
        try:
            webpush(subscription_info=s, data=json.dumps(payload),
                    vapid_private_key=config.VAPID_PRIVATE_KEY,
                    vapid_claims={"sub": config.VAPID_SUBJECT}, ttl=3600)
            keep.append(s)
            sent += 1
        except WebPushException as e:  # 404/410 = device unsubscribed -> drop it
            code = getattr(getattr(e, "response", None), "status_code", 0)
            if code not in (404, 410):
                keep.append(s)
        except Exception:
            keep.append(s)
    if len(keep) != len(subs):
        store.set_json(f"push:{phone}", keep)
    return sent


def notify_user(phone: str, title: str, body: str, url: str = "/"):
    return _send(phone, {"title": title, "body": body, "url": url, "tag": url})


def staff_phones() -> list:
    """All staff identities that should hear about new orders (phones + Clerk emails)."""
    s = catalog.get_settings()
    phones = config.ADMIN_PHONES + config.SUPERADMIN_PHONES + (s.get("admin_phones") or []) + (s.get("staff_phones") or [])
    emails = config.ADMIN_EMAILS + (s.get("admin_emails") or []) + (s.get("staff_emails") or [])
    return sorted(set(phones) | {f"email:{e}" for e in emails})


def notify_staff(title: str, body: str, url: str = "/admin"):
    return sum(_send(p, {"title": title, "body": body, "url": url, "tag": "admin"}) for p in staff_phones())


def broadcast(title: str, body: str, url: str = "/", customers_only=False) -> int:
    phones = store.zrevrange("pushusers", 0, -1)
    staff = set(staff_phones())
    n = 0
    for p in phones:
        if customers_only and p in staff:
            continue
        n += _send(p, {"title": title, "body": body, "url": url, "tag": "broadcast"})
    return n


__all__ = ["enabled", "subscribe", "notify_user", "notify_staff", "broadcast", "auth"]
