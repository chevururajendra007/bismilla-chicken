"""Performance eval – run: python scripts/perf_eval.py http://localhost:4173/
Low-end Android simulation: 6x CPU slowdown, 390x844, no GPU (headless = software rendering).
Measures main-thread busy time while the user just looks at the home page for 5 s."""
import asyncio, sys, json
from playwright.async_api import async_playwright
OFF = "*{animation:none!important;backdrop-filter:none!important;-webkit-backdrop-filter:none!important}.halo{display:none!important}body{background-attachment:scroll!important}"
async def run(url, disable=False, phone='budget'):
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--disable-gpu"])
        ctx = await b.new_context(viewport={'width':390,'height':844}, device_scale_factor=2, is_mobile=True, has_touch=True)
        mem, cores = (2, 4) if phone == 'budget' else (8, 8)
        await ctx.add_init_script(f"Object.defineProperty(navigator,'deviceMemory',{{get:()=>{mem}}});Object.defineProperty(navigator,'hardwareConcurrency',{{get:()=>{cores}}})")
        pg = await ctx.new_page(); cdp = await ctx.new_cdp_session(pg)
        await cdp.send('Emulation.setCPUThrottlingRate', {'rate': 6}); await cdp.send('Performance.enable')
        await pg.goto(url); await pg.wait_for_timeout(2500)
        if disable: await pg.add_style_tag(content=OFF)
        m0 = {m['name']: m['value'] for m in (await cdp.send('Performance.getMetrics'))['metrics']}
        await pg.wait_for_timeout(5000)                      # user just looking
        for _ in range(6): await pg.mouse.wheel(0, 600); await pg.wait_for_timeout(300)   # user scrolling
        m1 = {m['name']: m['value'] for m in (await cdp.send('Performance.getMetrics'))['metrics']}
        d = lambda k: round((m1[k]-m0[k])*1000)
        out = {'busy_ms_in_7s': d('TaskDuration'), 'style_ms': d('RecalcStyleDuration'), 'layout_ms': d('LayoutDuration'), 'script_ms': d('ScriptDuration'),
               'running_animations': await pg.evaluate("document.getAnimations().length")}
        await b.close(); return out
BUDGET_BUSY_MS = 1600   # main-thread busy time allowed in 7 s on a 6x-slowed phone
BUDGET_ANIMATIONS = 1   # endless animations allowed on the home page


async def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:4173/"
    ok = True
    for phone in ("budget", "midrange"):
        r = await run(url, phone=phone)
        print(phone.ljust(9), json.dumps(r))
        ok = ok and r["busy_ms_in_7s"] <= BUDGET_BUSY_MS and r["running_animations"] <= BUDGET_ANIMATIONS
    print("PASS" if ok else "FAIL", f"(budget: busy <= {BUDGET_BUSY_MS} ms, animations <= {BUDGET_ANIMATIONS})")
    sys.exit(0 if ok else 1)
asyncio.run(main())
