# Changelog

## v1.2.2 – 2026-11-21
- Hero: full live golden rooster with a playful speech bubble ("Hey! Want to taste me? 😋" / నన్ను రుచి చూడాలనుందా?).
- Logo: rooster photo with a BC badge. Clean white product cards with net-weight chips. Full-body hen for Natu Kodi.

## v1.2.1 – 2026-11-21
- Removed 3 stock photos that did not match the product (leg pieces, wings, liver) – "shop photo coming soon" tile until the owner uploads his own.

## v1.2.0 – 2026-11-21
- **Two Nellore paper rates**: Live (లైవ్) and Broiler/skinless (స్కిన్‌లెస్). Each product is linked to one rate
  (× multiplier + offset) or a manual price. Defaults: Live ₹220, Broiler ₹280 (latest public Nellore rates found);
  the owner updates both every morning and can push them to customers.
- **Real product photos** (free Unsplash photos as placeholders) + **owner photo upload** from the phone camera in
  Admin → Rates (resized on the phone, stored in Postgres, served from /api/img/<id>).
- **New "Ruby & Saffron" glossy design**: gradient background with gold/saffron glows, glass rate cards, animated
  offer ribbon, how-it-works steps, trust badges, photo product cards, owner spotlight, Baloo Tammudu 2 (Telugu) font.
- Automatic upgrade of v1.0/1.1 catalogs to the two-rate catalog (keeps in-stock flags).

## v1.1.0 – 2026-11-21
- **Customers need no account**: browse freely; at checkout enter name + mobile (+ optional email) and confirm the
  mobile once with OTP. The phone stays verified for 180 days.
- **Three payment options**: Cash on delivery · PhonePe/UPI at delivery · Prepaid (pay now). Prepaid orders cannot be
  accepted/cut until payment is claimed or marked paid. Optional rule: orders above ₹X must be prepaid.
- **Admin sign-in with Clerk** (Google / email) – sign in once, stays logged in for 365 days. Mobile-OTP login kept for
  delivery boys (can be switched off with ADMIN_OTP_LOGIN=false).
- **Postgres (Vercel → Storage → Neon)** as the main database: orders, order_events, customers, audit_log tables.
- **Admin History tab**: date range, search by mobile/name/order, totals by payment type, top customers, CSV export,
  activity log (who changed rates/settings/payments).
- **Platform tab (provider only)**: system health, monthly usage, maintenance plan (fee, paid-until, +1/+3/+12 months)
  with a due-date reminder banner for the owner.

## v1.0.1 – 2026-11-21
- Serve API from Mumbai (bom1) for lower latency in AP

## v1.0.0 – 2026-11-21
First release.
- Customer PWA: menu at daily paper rate, cart, delivery/pickup, map location, COD & PhonePe/UPI, live tracking, push
- Delivery rules: free ≤3 km, 3–5 km for 2 kg+ (₹30 fee, configurable), pickup beyond 5 km; nearest of 2 branches
- Admin (mobile OTP, owner 7904711708 auto-admin): order board, paper-rate pricing, product editor, settings, staff, broadcast
- AI helper: tools + local OpenAI-compatible LLM (Ollama) + agent loop, with rule fallback
- Vercel deployment (Vite static + FastAPI Python function), Upstash Redis storage
- Owner photo on home page
