"""Evaluation gates for phone safety & performance (added after the v1.5 "phone hangs" report).

These run with every test pass and fail the build if someone re-introduces:
  * code on customer pages that downloads / writes files or evaluates strings as code
  * inline scripts (blocked by our Content-Security-Policy) or a missing / weakened CSP
  * GPU-heavy CSS (blur filters, backdrop blur, fixed backgrounds, many endless animations)
  * oversized product photos
"""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
FE = ROOT / "frontend"
CUSTOMER_FILES = [p for p in (FE / "src").rglob("*.jsx") if p.name != "Admin.jsx"] + [FE / "src" / "api.js", FE / "public" / "sw.js", FE / "public" / "boot.js"]


def test_customer_code_never_downloads_or_evals():
    bad = re.compile(r"\.download\s*=|createObjectURL|\beval\(|new Function\(|document\.write|\.apk\b|showSaveFilePicker")
    hits = [f"{p.name}: {m.group(0)}" for p in CUSTOMER_FILES for m in bad.finditer(p.read_text())]
    assert not hits, hits


def test_csp_and_security_headers():
    v = json.loads((ROOT / "vercel.json").read_text())
    all_routes = next(h for h in v["headers"] if h["source"] == "/(.*)")
    hdr = {h["key"]: h["value"] for h in all_routes["headers"]}
    csp = hdr["Content-Security-Policy"]
    script_src = next(d for d in csp.split(";") if d.strip().startswith("script-src"))
    assert "'unsafe-inline'" not in script_src and "'unsafe-eval'" not in script_src and " https: " not in script_src + " "
    assert "object-src 'none'" in csp and "frame-ancestors 'none'" in csp
    assert hdr["X-Content-Type-Options"] == "nosniff" and hdr["X-Frame-Options"] == "DENY"
    assert "microphone=()" in hdr["Permissions-Policy"]


def test_no_inline_scripts_in_html():
    html = (FE / "index.html").read_text()
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html), "inline <script> would be blocked by CSP"


def test_css_is_light_for_budget_phones():
    css = (FE / "src" / "styles.css").read_text()
    assert "backdrop-filter" not in css
    assert "filter: blur" not in css
    assert "background-attachment: fixed" not in css
    assert css.count("infinite") == 0 and "@keyframes" not in css, "no animations at all (v1.7 light for every phone)"
    assert "content-visibility" not in css, "measured: content-visibility made scrolling 10x more expensive here"
    assert "html.lite" in css


def test_product_photos_are_right_sized():
    from core.catalog import DEFAULT_PRODUCTS
    for p in DEFAULT_PRODUCTS:
        img = p.get("image") or ""
        assert "/960px-" not in img and "w=640" not in img, p["id"]


def test_no_web_fonts_downloaded():
    html = (FE / "index.html").read_text()
    css = (FE / "src" / "styles.css").read_text()
    assert "fonts.googleapis" not in html and "@font-face" not in css, "use the phone's own fonts"


def test_heavy_screens_load_on_demand():
    app = (FE / "src" / "App.jsx").read_text()
    for page in ("Admin", "Checkout", "Track", "Chat", "VerifyPhone"):
        assert f"lazy(() => import('./" in app and f"{page} = lazy(" in app, f"{page} must be lazy-loaded"
    assert "react: 'preact/compat'" in (FE / "vite.config.js").read_text(), "Preact keeps the first download small"


def test_first_download_is_small():
    dist = FE / "dist" / "assets"
    if not dist.exists():
        return  # build not present in this environment
    html = (FE / "dist" / "index.html").read_text()
    entry = re.search(r'src="/assets/(index-[^"]+\.js)"', html).group(1)
    size_kb = (dist / entry).stat().st_size / 1024
    assert size_kb <= 60, f"home page JS is {size_kb:.0f} KB (budget 60 KB)"


def test_polling_pauses_in_background():
    for f in ("Track.jsx", "Admin.jsx"):
        src = (FE / "src" / "pages" / f).read_text()
        assert "visibilityState" in src, f"{f} must stop refreshing when the phone screen is off"
