# Architecture – Bismilla Chicken v1.1.0

```
 Customer phone / tablet / PC (PWA)            Owner / staff phone (same PWA, role = admin/staff)
        │  React + service worker                     │  order board, rates, live location
        └──────────────── HTTPS ──────────────────────┘
                              │
                     Vercel (static + 1 Python function)
                     ├─ frontend/dist  (Vite build, CDN)
                     └─ api/index.py → main.py (FastAPI)
                             ├─ core/auth      mobile OTP → JWT, roles from ADMIN_PHONES / settings
                             ├─ core/catalog   paper rate → product prices
                             ├─ core/delivery  haversine × road factor, radius rules, ETA
                             ├─ core/orders    server-side pricing, status machine, UPI links
                             ├─ core/push      Web Push (VAPID) → customer + staff devices
                             ├─ core/store     Postgres (Neon via Vercel) > Upstash Redis > JSON file
                             └─ agent.py       tools + local LLM + loop (rule fallback)
                                     │
                         LLM_BASE_URL (Ollama / LM Studio via tunnel)
```

## Mapping to the class cheat-sheet
| Concept | Where |
|---|---|
| Model (LLM) | Local open-weights model via Ollama (`qwen2.5:7b` default) – no cloud API |
| Harness | `SYSTEM` prompt + live tools + history trimming in `agent.py` |
| Tool calling | 5 tools; numbers always come from tools, never from the model |
| Loop engineering | `chat()` – up to 5 rounds: model → tool calls → results → model → done |
| Context engineering | Only the last 8 messages + tool results; prices fetched fresh each call |
| Security & sandboxing | Server re-prices every order, OTP rate-limits (5 tries, 30 s resend), role check on every request, order ownership checks, secrets only in env |
| Evaluation | `tests/test_api.py` – known answers (3 km free, 2 kg rule, price formula, OTP roles) |

## Order status machine
`placed → accepted → preparing → (pickup) ready → picked_up`
`placed → accepted → preparing → (delivery) out_for_delivery → delivered`
`placed → cancelled` (customer can cancel only before acceptance)

## Live tracking
- ETA before dispatch = prep minutes + road km ÷ speed.
- When the rider taps **Share my location**, the phone posts GPS every ~12 s; the customer page polls every 10 s and recomputes ETA from the rider's position.
- Serverless-friendly (no websockets). Upgrade path: Ably/Pusher channel per order.

## Auth (v1.1)
- Customers: OTP once at checkout → HS256 app token (180 d). No passwords, no accounts.
- Admin: Clerk session JWT (RS256, verified with Clerk JWKS) → email checked against ADMIN_EMAILS / settings →
  app token (365 d). Role re-checked on every request, so removing an admin is instant.
- Roles: superadmin (provider) > admin (owner) > staff (delivery) > customer.

## Payments (v1.1)
| Method | When paid | Shop can start cutting |
|---|---|---|
| `cod` | Cash at door / counter | Immediately |
| `upi_delivery` | PhonePe at door (same QR on the tracking page) | Immediately |
| `prepaid` | Before preparation | Only after UTR is entered or owner taps **Mark paid** |
Optional `cod_max_amount`: orders above it must be prepaid.

## Payments (v1.0 notes)
v1: UPI intent (`phonepe://pay` / `upi://pay`) to the owner's UPI ID + QR on desktop → customer submits UTR → owner verifies in PhonePe and taps **Mark paid**.
v2: PhonePe Payment Gateway (merchant onboarding) with server-to-server callback → automatic "paid".

## Postgres tables
`orders` (one row per order, JSONB copy), `order_events` (every status/payment change), `customers`
(verified mobiles, order count, total spent), `audit_log` (rates, settings, logins, payments, billing),
plus `kv`/`zset` for app state.

## Data (keys, prefix `bc:`)
`settings`, `branches`, `products`, `user:{phone}`, `otp:{phone}` (TTL 300 s), `order:{code}`, `orders` (zset), `uorders:{phone}` (zset), `orderseq`, `push:{phone}`, `pushusers` (zset), `ratehist` (zset).
