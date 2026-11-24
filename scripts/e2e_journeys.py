"""End-to-end journeys on a budget-phone profile (run: python scripts/e2e_journeys.py http://localhost:4173).
Customer: browse -> cart -> verify mobile (OTP) -> address -> prepaid order -> track -> chat.
Owner: OTP login -> accept order after payment -> update paper rates -> history."""
import asyncio, re, sys
from playwright.async_api import async_playwright
URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:4173"
results = []
def ok(name, cond): results.append((name, bool(cond))); print(("PASS " if cond else "FAIL ") + name)

async def otp(pg, phone, name=None):
    if name: await pg.fill('input[autocomplete=name]', name)
    await pg.fill('input[autocomplete=tel-national]', phone)
    await pg.get_by_role('button', name=re.compile('Send OTP')).click(); await pg.wait_for_timeout(800)
    await pg.fill('input.otp', (await pg.locator('.dev b').inner_text()).strip())
    await pg.get_by_role('button', name=re.compile('Verify')).click(); await pg.wait_for_timeout(1500)

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--disable-gpu"]); errs = []
        ctx = await b.new_context(viewport={'width': 360, 'height': 740}, is_mobile=True, has_touch=True,
                                  geolocation={'latitude': 14.0420, 'longitude': 80.0560}, permissions=['geolocation'])
        pg = await ctx.new_page(); pg.on('pageerror', lambda e: errs.append(str(e)))
        cdp = await ctx.new_cdp_session(pg); await cdp.send('Emulation.setCPUThrottlingRate', {'rate': 6})
        await pg.goto(URL); await pg.wait_for_timeout(2000)
        ok("home shows products", await pg.locator('.card2').count() >= 10)
        ok("kitchen section present", await pg.locator('#kitchen').count() == 1)
        ok("no animations running", await pg.evaluate("document.getAnimations().length") == 0)
        ok("no admin link for customers", await pg.locator('text=/admin/i').count() == 0)
        await pg.get_by_role('button', name=re.compile('ADD')).nth(1).click()
        await pg.get_by_text('View cart').click(); await pg.wait_for_timeout(2500)
        ok("checkout + map loaded on demand", await pg.locator('.addr').count() == 1)
        await pg.fill('input[placeholder="e.g. 4-12"]', '4-12')
        await pg.fill('input[placeholder^="e.g. Gandhi"]', 'Gandhi Nagar')
        await pg.get_by_text("I'm at home").click(); await pg.wait_for_timeout(2000)
        await otp(pg, '9876500011', 'Ravi Kumar')
        ok("mobile verified", await pg.locator('.verified').count() == 1)
        await pg.get_by_text('Pay now (prepaid)').click()
        await pg.get_by_role('button', name=re.compile('Place order')).click(); await pg.wait_for_timeout(3000)
        ok("order placed -> tracking page", '/track/' in pg.url)
        ok("prepaid waits for payment", await pg.locator('text=/Prepaid order/').count() >= 1)
        await pg.fill('input[placeholder^="UPI transaction"]', '412345678901')
        await pg.get_by_role('button', name="I've paid").click(); await pg.wait_for_timeout(1200)
        ok("UTR accepted", await pg.locator('text=/received your transaction ID/').count() == 1)
        await pg.goto(URL); await pg.wait_for_timeout(1500)
        await pg.locator('.chat-fab').click(); await pg.wait_for_timeout(1500)
        await pg.locator('.chips button').first.click(); await pg.wait_for_timeout(2500)
        ok("chat answers rates", await pg.locator('.bubble.assistant').count() >= 2)
        # owner
        a = await (await b.new_context(viewport={'width': 360, 'height': 740}, is_mobile=True)).new_page(); a.on('pageerror', lambda e: errs.append(str(e)))
        await a.goto(URL + '/admin'); await a.wait_for_timeout(2000)
        ok("admin page uses BC Admin manifest", await a.eval_on_selector('#mf', 'e=>e.getAttribute("href")') == '/manifest-admin.webmanifest')
        await a.get_by_role('button', name=re.compile('mobile OTP')).click(); await otp(a, '7904711708')
        ok("owner logged in", await a.locator('.tabs button').count() >= 5)
        await a.get_by_role('button', name=re.compile('Accept')).first.click(); await a.wait_for_timeout(1500)
        ok("owner accepted paid order", await a.locator('text=/Order accepted/').count() >= 1)
        await a.get_by_role('button', name=re.compile('Rates')).click(); await a.wait_for_timeout(1500)
        await a.locator('.rate-in.live input').fill('215'); await a.locator('.rate-in.broiler input').fill('275')
        await a.get_by_role('button', name=re.compile("Update today")).click(); await a.wait_for_timeout(1500)
        ok("paper rates updated", await a.locator('text=/Rates updated/').count() == 1)
        await a.get_by_role('button', name=re.compile('History')).click(); await a.wait_for_timeout(2000)
        ok("history lists the order", await a.locator('.htable tbody tr').count() >= 1)
        ok("no JavaScript errors", not errs); errs and print(errs[:3])
        await b.close()
    failed = [n for n, r in results if not r]
    print(f"\n{len(results) - len(failed)}/{len(results)} journeys passed"); sys.exit(1 if failed else 0)
asyncio.run(main())
