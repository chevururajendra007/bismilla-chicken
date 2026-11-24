# Bismilla Chicken – Online Ordering App (v1.7.0)

Fresh chicken ordering for **Bismilla Chicken**, Kota (opp. Extra Mart) & Vidyanagar, Andhra Pradesh.
Customers order from mobile, tablet or desktop (installable PWA). The owner manages the daily **paper rate**, orders, payments and deliveries from the same app after logging in with **mobile OTP**.

Built on the class framework **Model (LLM) + Harness = Agent**, deployed on **Vercel**, with a **local LLM** instead of Azure.

## Files (same shape as the class framework)

| File | What it does |
|---|---|
| `.env` | Secrets & settings (local LLM URL, JWT secret, VAPID keys, KV store). **Never commit it.** See `.env.example`. |
| `agent.py` | The **tools** (rates, shop info, delivery check, quantity advice, order status), the **model** (local OpenAI-compatible LLM) and the **agent loop** (`chat`). Rule-based fallback when the LLM is offline. |
| `main.py` | FastAPI server – all `/api/*` routes (OTP auth, menu, delivery quote, orders, admin, push, `POST /api/chat`). |
| `api/index.py` | Vercel entrypoint (exposes `main.app` as one Python function). |
| `core/` | `catalog` (paper-rate pricing), `delivery` (radius rules, nearest branch, ETA), `orders`, `auth` (OTP + roles), `push` (web push), `store` (Upstash Redis / local file). |
| `frontend/src/App.jsx` | React PWA shell: routing, install prompt, update banner, push opt-in, chat box. |
| `frontend/src/pages/*` | `Home` (menu + owner), `Checkout` (map, delivery/pickup, COD/PhonePe), `Track` (live status + map + UPI QR), `Orders`, `Admin`. |
| `frontend/public/sw.js` | Service worker: offline shell, push notifications, app updates. |
| `requirements.txt` | fastapi, httpx, python-dotenv, pyjwt, pywebpush |

## Features

**Customers**
- Menu priced live from today's paper rate (₹/kg), Telugu + English names
- Door delivery: **free within 3 km**; **3–5 km only for 2 kg+ orders** (₹30 fee, editable); beyond 5 km → pickup
- Pick location on map (Google Maps if key set, else OpenStreetMap) or "use my location"; nearest branch auto-selected
- Pickup from Kota or Vidyanagar branch
- Pay **Cash on delivery** or **PhonePe / any UPI** (deep link + QR + UTR confirmation)
- Live tracking: status steps, ETA from distance, rider's live location on the map (polled every 10 s)
- Push notifications for every status change and daily rate updates
- AI helper (chat) for rates, delivery charges, "how much for 8 people", order status
- Installable on Android, iPhone (16.4+ for push), tablets and desktops

**Owner / admin** (login with 7904711708 → OTP → Admin)
- Enter today's paper rate once → all prices update → optional push to all customers
- Per-product: paper-rate formula (× multiplier + offset) or manual price, in-stock toggle; whole-shop manual mode
- Live order board with sound alert, accept → cutting → out for delivery → delivered, mark paid, UTR check
- "Share my location" turns the owner's/rider's phone into the live tracker
- Delivery rules, branch addresses & exact map pins, open/closed, COD/PhonePe toggles
- Add staff (delivery boys) and extra admins by phone number
- Broadcast offers ("Natu Kodi in stock today")

## Who logs in how (v1.1)

| Person | How | Stays signed in |
|---|---|---|
| Customer | No account. Name + mobile (+ optional email) at checkout, mobile confirmed **once** by SMS OTP | 180 days on that phone |
| Shop owner (admin) | **Clerk** – "Continue with Google" or email code | 365 days on that phone |
| Delivery boy / counter staff | Mobile OTP once (number added in Settings → Team) | 365 days |
| You (platform provider) | Clerk email in `SUPERADMIN_EMAILS` (or `SUPERADMIN_PHONES`) → **Platform** tab | 365 days |

### Set up Clerk (5 minutes)
1. dashboard.clerk.com → **Create application** "Bismilla Chicken" → enable **Google** and **Email**.
2. Copy keys into Vercel env: `CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY`.
3. Set `ADMIN_EMAILS=<owner's gmail>` and `SUPERADMIN_EMAILS=<your email>`; redeploy.
4. Clerk → Sessions → set **maximum lifetime** to the longest allowed (the app session itself lasts 365 days).
5. Optional: set `ADMIN_OTP_LOGIN=false` to allow admin access only through Clerk.

### Database (Vercel → Storage → Neon Postgres)
Vercel → project **bismilla-chicken** → **Storage** → **Create Database** → **Neon (Postgres)** → region **Mumbai/Singapore** →
connect to the project. That adds `DATABASE_URL`; the app creates its tables on first request. Query history any time
from Neon's SQL editor, e.g.:
```sql
SELECT date_trunc('day', created_at AT TIME ZONE 'Asia/Kolkata') d, count(*), sum(total)
FROM orders WHERE status <> 'cancelled' GROUP BY 1 ORDER BY 1 DESC;
```

## Release checks (run before every push)
```bash
pytest -q                                   # API + 9 phone-safety gates
cd frontend && npm run build && npx vite preview --port 4173 &   # with uvicorn main:app on :8000
python scripts/perf_eval.py http://localhost:4173/      # budget & mid-range phone CPU budget
python scripts/e2e_journeys.py http://localhost:4173    # 16 customer + owner journeys
```

## Run locally

```bash
cp .env.example .env            # set JWT_SECRET
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

cd frontend && npm install && npm run dev   # http://localhost:5173 (proxies /api to :8000)
```

### Local LLM (no Azure)
```bash
# install https://ollama.com then
ollama pull qwen2.5:7b          # or llama3.1:8b / gemma3:4b
ollama serve                    # exposes http://localhost:11434/v1 (OpenAI-compatible)
```
`LLM_BASE_URL` can point to any OpenAI-compatible server (LM Studio, llama.cpp, vLLM).
On Vercel the function can't see your laptop's `localhost`. Expose the local model through a tunnel
(`cloudflared tunnel --url http://localhost:11434`) and set `LLM_BASE_URL` to the tunnel URL + `/v1`.
Without it, the chat automatically uses the built-in rule engine – prices and delivery answers stay correct.

## Deploy (Vercel)
1. Repo is linked to Vercel project **bismilla-chicken** (team *chevurushafoundation*); every push to `main` deploys.
2. **Storage:** Vercel → Storage → connect the Upstash Redis store to this project (adds `KV_REST_API_URL/TOKEN`). Keys are prefixed `bc:` so the store can be shared.
3. Env vars: `JWT_SECRET`, `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `ADMIN_PHONES`, `UPI_ID`, `OTP_DEV_MODE`, optional `GOOGLE_MAPS_API_KEY`, `SMS_PROVIDER` + key.
4. Custom domain: add later in Vercel → Domains.

## Go-live checklist
- [ ] Confirm the owner's PhonePe UPI ID and set `UPI_ID` (better: free **PhonePe Business** merchant QR for shop payments)
- [ ] SMS OTP: MSG91 or Fast2SMS (DLT template), then `OTP_DEV_MODE=false`
- [ ] Admin → Settings → Branches: drop exact pins for Kota (opp. Extra Mart) and Vidyanagar, update Vidyanagar address
- [ ] Admin → Rates: tune multipliers for skinless/boneless to match the shop's board prices
- [ ] Google Maps key (Maps JavaScript API) restricted to the domain
- [ ] Connect Upstash Redis store (orders are not durable without it)

See `docs/ARCHITECTURE.md` and `docs/GO_TO_MARKET.md`. Version history in `CHANGELOG.md`.
