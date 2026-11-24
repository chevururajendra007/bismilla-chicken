# Incident report – "App hangs my phone / malware in File Manager" (24 Nov 2026)

**Reported by:** a customer, via the owner · **Version affected:** v1.2 – v1.5 · **Fixed in:** v1.6.0

## What we checked (evidence)
| Check | Result |
|---|---|
| GitHub commits | Only our own commits; none from anyone else |
| Vercel deployments & domains | Only our deployments; only `bismilla-chicken.vercel.app` |
| Live code vs our build | Identical file fingerprints (`index-CZZUCf0h.js`) – not tampered |
| Download / file-write / eval code on customer pages | **None** (only the owner's Excel export in /admin) |
| Third-party scripts | None – only Google Fonts CSS, photos, map tiles |
| Library vulnerabilities | Website libraries: 0. Server: Starlette & python-dotenv advisories → upgraded |
| Budget-phone simulation (6× slower CPU, no GPU) | Page kept the CPU busy **2.36 s of every 7 s** while idle; **6 endless animations**; 2.1 MB download |

## Root cause
1. **Heavy visual effects** added in the v1.2 redesign: a 28 px-blurred spinning glow (repainted every frame),
   8 blur/backdrop-blur layers, a fixed multi-layer gradient background, endless bobbing/shine animations.
   On budget Android phones this pins the CPU/GPU → heat, lag, Chrome freezing; weak or old-battery phones can shut down.
2. **Oversized photos**: product photos were downloaded at 960 px but shown at ~300 px (2.1 MB page).

## Not caused by this app
A website opened in Chrome cannot install apps or put files into the File Manager unless the user taps a download.
Our customer pages contain no download code (verified, and now enforced by an automated test and by the
Content-Security-Policy). Likely sources: an ad or another app on the phone, a fake "cleaner/antivirus" app showing
scary warnings, or a wrong/look-alike link. If the customer "installed" our app, Chrome creates a small
"Bismilla Chicken" app package – that is ours and safe.

## Fix (v1.6.0)
- Removed blur filters, backdrop blur, fixed background and endless animations (marquee only, and off on budget phones)
- **Lite mode** auto-enabled on phones with ≤3 GB RAM, ≤4 cores, Data Saver or 2G
- Photos right-sized (Wikimedia 960→500 px, Unsplash 640→480 px, hero 900→600 px), fewer font weights
- Security headers: strict Content-Security-Policy (no inline/third-party scripts except Clerk/Google Maps),
  nosniff, no framing, Permissions-Policy (no mic/USB/Bluetooth); inline script moved to `/boot.js`
- Upgraded FastAPI/Starlette, python-dotenv, PyJWT, pywebpush, psycopg, Vite 8

## Results (same eval, budget phone)
| | Before | After |
|---|---|---|
| CPU busy in 7 s (budget phone) | 2,364 ms | **57 ms** |
| CPU busy in 7 s (mid-range) | 2,626 ms | **1,451 ms** |
| Endless animations | 6 | 0 (budget) / 1 (mid-range) |

## Guards so it can't come back
- `tests/test_phone_safety.py` – fails the build on download/eval code in customer pages, missing CSP,
  inline scripts, blur/backdrop/fixed backgrounds, >2 endless animations, oversized photos
- `scripts/perf_eval.py` – budget & mid-range phone simulation with a CPU budget (run before each release)

## Advice for the customer
1. Open only **https://bismilla-chicken.vercel.app** (or the shop's QR code).
2. Play Store → profile → **Play Protect → Scan**. Remove unknown "cleaner/booster/antivirus" apps.
3. Delete unknown files in Downloads; don't open APK files.
4. Send a screenshot of the warning / file names if it happens again.
