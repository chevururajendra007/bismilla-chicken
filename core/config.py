"""Central configuration. Everything secret comes from environment variables (.env locally, Vercel env in prod)."""
import os

from dotenv import load_dotenv

load_dotenv()

APP_VERSION = "1.6.0"

SHOP_NAME = os.getenv("SHOP_NAME", "Bismilla Chicken")
SHOP_PHONE = os.getenv("SHOP_PHONE", "7904711708")
# PhonePe / UPI ID that receives payments. PhonePe personal IDs usually look like <number>@ybl / @ibl / @axl.
# CONFIRM the exact ID in the owner's PhonePe app (Profile -> UPI IDs) and set UPI_ID in Vercel.
UPI_ID = os.getenv("UPI_ID", "7904711708@ybl")
UPI_PAYEE_NAME = os.getenv("UPI_PAYEE_NAME", "Bismilla Chicken")

# Phones that become admin automatically on OTP login (comma separated, 10 digits).
ADMIN_PHONES = [p.strip()[-10:] for p in os.getenv("ADMIN_PHONES", SHOP_PHONE).split(",") if p.strip()]

JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-change-me")
CUSTOMER_SESSION_DAYS = int(os.getenv("CUSTOMER_SESSION_DAYS", "180"))  # verified phone stays remembered
ADMIN_SESSION_DAYS = int(os.getenv("ADMIN_SESSION_DAYS", "365"))        # admin stays logged in on the device

# Admin sign-in with Clerk (Google / email). Only the publishable key is required to verify sessions;
# the secret key lets the server read the signed-in user's email.
CLERK_PUBLISHABLE_KEY = os.getenv("CLERK_PUBLISHABLE_KEY", "")
CLERK_SECRET_KEY = os.getenv("CLERK_SECRET_KEY", "")
_emails = lambda v: [e.strip().lower() for e in os.getenv(v, "").split(",") if e.strip()]
ADMIN_EMAILS = _emails("ADMIN_EMAILS")            # shop owner(s)
SUPERADMIN_EMAILS = _emails("SUPERADMIN_EMAILS")  # platform provider (you): history, billing, audit
SUPERADMIN_PHONES = [p.strip()[-10:] for p in os.getenv("SUPERADMIN_PHONES", "").split(",") if p.strip()]
# Allow admin/staff login by mobile OTP too (delivery boys without Google accounts). Set false to force Clerk.
ADMIN_OTP_LOGIN = os.getenv("ADMIN_OTP_LOGIN", "true").lower() == "true"

# OTP delivery. OTP_DEV_MODE=true returns the code in the API response (for demos only).
OTP_DEV_MODE = os.getenv("OTP_DEV_MODE", "true").lower() == "true"
SMS_PROVIDER = os.getenv("SMS_PROVIDER", "")  # "msg91" | "fast2sms" | "" (none)
MSG91_AUTH_KEY = os.getenv("MSG91_AUTH_KEY", "")
MSG91_TEMPLATE_ID = os.getenv("MSG91_TEMPLATE_ID", "")
FAST2SMS_API_KEY = os.getenv("FAST2SMS_API_KEY", "")

# Storage priority: Postgres (Vercel -> Storage -> Neon) > Upstash Redis > local JSON file.
DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or ""
# Storage: Upstash Redis REST (Vercel KV). Falls back to a local JSON file when not set.
KV_REST_API_URL = os.getenv("KV_REST_API_URL", "")
KV_REST_API_TOKEN = os.getenv("KV_REST_API_TOKEN", "")
KV_PREFIX = os.getenv("KV_PREFIX", "bc:")
LOCAL_DB_PATH = os.getenv("LOCAL_DB_PATH", os.path.join(os.path.dirname(os.path.dirname(__file__)), ".localdb.json"))

# Web push (VAPID). Generate with: python scripts/gen_vapid.py
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_SUBJECT = os.getenv("VAPID_SUBJECT", "mailto:admin@bismillachicken.in")

# Local LLM (OpenAI-compatible: Ollama, LM Studio, llama.cpp server, vLLM).
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5:7b")
LLM_API_KEY = os.getenv("LLM_API_KEY", "ollama")
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "25"))

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
