"""Bismilla Chicken assistant – the TOOLS, the MODEL and the AGENT LOOP (chat).

Model  : any OpenAI-compatible LOCAL LLM (Ollama / LM Studio / llama.cpp / vLLM).
         Default: Ollama at http://localhost:11434/v1 with qwen2.5:7b (good tool-calling, runs on a laptop).
         No Azure, no paid API.
Harness: system prompt + live shop context + tools + loop (max 5 tool rounds).
Fallback: if the LLM is unreachable (e.g. on Vercel without a tunnel), a rule-based responder
          answers from the SAME tools, so customers always get correct prices and delivery info.
"""
import json
import re

import httpx

from core import catalog, config, delivery, orders

# ----------------------------------------------------------------------------- TOOLS


def get_today_rates() -> dict:
    """Today's paper rate and per-kg price of every item."""
    m = catalog.get_menu()
    return {
        "paper_rate_per_kg": m["paper_rate"], "rate_date": m["paper_rate_date"], "shop_open": m["shop_open"],
        "items": [{"name": p["name"], "telugu": p.get("name_te"), "price": p["price"], "unit": p["unit"],
                   "available": p["available"]} for p in m["products"]],
    }


def get_shop_info() -> dict:
    """Branches, addresses, hours, phone, payment options and delivery rules."""
    s = catalog.get_settings()
    return {
        "shop": config.SHOP_NAME, "phone": config.SHOP_PHONE,
        "branches": [{k: b[k] for k in ("name", "address", "hours", "phone", "open")} for b in catalog.get_branches()],
        "payments": ["Cash on delivery"] * bool(s["accept_cod"]) + ["PhonePe / any UPI"] * bool(s["accept_phonepe"]),
        "delivery_rules": s["delivery"],
    }


def check_delivery(distance_km: float, weight_kg: float) -> dict:
    """Is door delivery possible for this distance (km from shop) and weight (kg)? Returns fee and ETA."""
    d = catalog.get_settings()["delivery"]
    km, kg = float(distance_km), float(weight_kg)
    if km <= d["free_radius_km"]:
        ok, fee = kg >= d["min_kg_inner"], 0
    elif km <= d["max_radius_km"]:
        ok, fee = kg >= d["min_kg_outer"], d["fee_outer"]
    else:
        ok, fee = False, None
    return {"deliverable": ok, "fee": fee if ok else None, "eta_minutes": delivery.eta_minutes(km), "rules": d}


def suggest_quantity(people: int, dish: str = "curry") -> dict:
    """How much chicken to buy for N people (curry ~250 g/person, biryani ~300 g/person, fry ~200 g/person)."""
    per = {"biryani": 0.3, "fry": 0.2, "curry": 0.25}.get((dish or "curry").lower(), 0.25)
    kg = max(0.5, round(int(people) * per * 4) / 4)
    return {"people": int(people), "dish": dish, "recommended_kg": kg}


def get_order_status(order_code: str, _phone: str | None = None) -> dict:
    """Status and ETA of one of the logged-in customer's orders."""
    if not _phone:
        return {"error": "Please login to check your orders."}
    try:
        o = orders.public(orders.get(order_code.strip().upper()))
    except Exception:
        return {"error": "Order not found."}
    if o["phone"] != _phone:
        return {"error": "That order belongs to a different number."}
    return {"code": o["code"], "status": o["status_label"], "eta_minutes": o.get("live_eta_minutes"),
            "total": o["total"], "payment": o["payment_status"]}


TOOLS = {
    "get_today_rates": get_today_rates,
    "get_shop_info": get_shop_info,
    "check_delivery": check_delivery,
    "suggest_quantity": suggest_quantity,
    "get_order_status": get_order_status,
}

TOOL_SPECS = [
    {"type": "function", "function": {"name": "get_today_rates", "description": get_today_rates.__doc__,
                                      "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "get_shop_info", "description": get_shop_info.__doc__,
                                      "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "check_delivery", "description": check_delivery.__doc__,
                                      "parameters": {"type": "object", "properties": {
                                          "distance_km": {"type": "number"}, "weight_kg": {"type": "number"}},
                                          "required": ["distance_km", "weight_kg"]}}},
    {"type": "function", "function": {"name": "suggest_quantity", "description": suggest_quantity.__doc__,
                                      "parameters": {"type": "object", "properties": {
                                          "people": {"type": "integer"},
                                          "dish": {"type": "string", "enum": ["curry", "biryani", "fry"]}},
                                          "required": ["people"]}}},
    {"type": "function", "function": {"name": "get_order_status", "description": get_order_status.__doc__,
                                      "parameters": {"type": "object", "properties": {
                                          "order_code": {"type": "string"}}, "required": ["order_code"]}}},
]

SYSTEM = f"""You are the friendly helper of {config.SHOP_NAME}, a fresh chicken shop in Kota (opp. Extra Mart) and
Vidyanagar, Andhra Pradesh. Reply in the customer's language (Telugu or English, short and warm).
ALWAYS call tools for prices, delivery rules, shop info and order status – never guess numbers.
Prices change daily with the newspaper (paper) rate. To order, tell the customer to add items to the cart and checkout.
Payments: cash on delivery or PhonePe/UPI. Keep answers under 80 words."""

# ----------------------------------------------------------------------------- MODEL


def _llm(messages: list) -> dict:
    r = httpx.post(f"{config.LLM_BASE_URL.rstrip('/')}/chat/completions",
                   headers={"Authorization": f"Bearer {config.LLM_API_KEY}"},
                   json={"model": config.LLM_MODEL, "messages": messages, "tools": TOOL_SPECS, "temperature": 0.3},
                   timeout=config.LLM_TIMEOUT)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]


def _run_tool(name: str, args: dict, phone: str | None):
    fn = TOOLS.get(name)
    if not fn:
        return {"error": f"unknown tool {name}"}
    try:
        if name == "get_order_status":
            return fn(args.get("order_code", ""), _phone=phone)
        return fn(**args)
    except Exception as e:
        return {"error": str(e)}

# ----------------------------------------------------------------------------- AGENT LOOP


def chat(message: str, history: list | None = None, phone: str | None = None) -> dict:
    messages = [{"role": "system", "content": SYSTEM}]
    for h in (history or [])[-8:]:
        if h.get("role") in ("user", "assistant") and isinstance(h.get("content"), str):
            messages.append({"role": h["role"], "content": h["content"][:1000]})
    messages.append({"role": "user", "content": message[:1000]})
    tools_used = []
    try:
        for _ in range(5):  # prompt -> model -> tool calls -> check -> loop again or done
            msg = _llm(messages)
            calls = msg.get("tool_calls") or []
            if not calls:
                return {"reply": (msg.get("content") or "").strip() or fallback(message, phone)["reply"],
                        "tools": tools_used, "engine": f"local-llm:{config.LLM_MODEL}"}
            messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
            for c in calls:
                name = c["function"]["name"]
                try:
                    args = json.loads(c["function"].get("arguments") or "{}")
                except Exception:
                    args = {}
                result = _run_tool(name, args, phone)
                tools_used.append(name)
                messages.append({"role": "tool", "tool_call_id": c.get("id", name), "name": name,
                                 "content": json.dumps(result, ensure_ascii=False)})
        return {"reply": "Sorry, I couldn't finish that. Please call " + config.SHOP_PHONE, "tools": tools_used,
                "engine": "local-llm"}
    except Exception:
        return fallback(message, phone)

# ----------------------------------------------------------------------------- FALLBACK (no LLM)


def fallback(message: str, phone: str | None = None) -> dict:
    t = message.lower()
    used = []
    code = re.search(r"\bbc\d{6,}\b", t)
    if code:
        used.append("get_order_status")
        o = get_order_status(code.group(0), _phone=phone)
        reply = o.get("error") or (f"Order {o['code']}: {o['status']}."
                                   + (f" ETA ~{o['eta_minutes']} min." if o.get("eta_minutes") else "")
                                   + f" Total ₹{o['total']}.")
    elif m := re.search(r"(\d+)\s*(people|persons|members|mandi|guests)", t):
        dish = "biryani" if "biryani" in t else "fry" if "fry" in t else "curry"
        used.append("suggest_quantity")
        q = suggest_quantity(int(m.group(1)), dish)
        reply = f"For {q['people']} people ({dish}) take about {q['recommended_kg']} kg. Add it to the cart 👍"
    elif any(w in t for w in ("deliver", "delivery", "km", "distance", "free")):
        used.append("get_shop_info")
        d = catalog.get_settings()["delivery"]
        reply = (f"Free door delivery within {d['free_radius_km']:g} km. Between {d['free_radius_km']:g}–"
                 f"{d['max_radius_km']:g} km we deliver orders of {d['min_kg_outer']:g} kg or more"
                 + (f" (₹{d['fee_outer']} fee)." if d['fee_outer'] else " for free.")
                 + " Beyond that, pickup is available. Pick your location at checkout to see your exact fee and ETA.")
    elif any(w in t for w in ("address", "where", "branch", "location", "timing", "time", "open", "phone", "number")):
        used.append("get_shop_info")
        i = get_shop_info()
        reply = " | ".join(f"{b['name']}: {b['address']} ({b['hours']})" for b in i["branches"]) + f" · Call {i['phone']}"
    elif any(w in t for w in ("pay", "phonepe", "upi", "cash", "cod")):
        used.append("get_shop_info")
        reply = "You can pay Cash on Delivery or by PhonePe / any UPI app. After UPI payment, enter the transaction ID on the order page."
    else:
        used.append("get_today_rates")
        r = get_today_rates()
        top = ", ".join(f"{i['name'].split('(')[0].strip()} ₹{i['price']}/{i['unit']}" for i in r["items"][:5] if i["available"])
        reply = f"Today's paper rate ₹{r['paper_rate_per_kg']}/kg ({r['rate_date']}). {top}. Add items to cart to order!"
    return {"reply": reply, "tools": used, "engine": "rules (local LLM offline)"}


def llm_status() -> dict:
    try:
        r = httpx.get(f"{config.LLM_BASE_URL.rstrip('/')}/models", timeout=3,
                      headers={"Authorization": f"Bearer {config.LLM_API_KEY}"})
        return {"reachable": r.status_code == 200, "base_url": config.LLM_BASE_URL, "model": config.LLM_MODEL}
    except Exception:
        return {"reachable": False, "base_url": config.LLM_BASE_URL, "model": config.LLM_MODEL}
