"""Storage.

Priority:
  1. Postgres  (DATABASE_URL / POSTGRES_URL – Vercel -> Storage -> Neon)   <- production, full history
  2. Upstash Redis REST (KV_REST_API_URL / KV_REST_API_TOKEN)
  3. Local JSON file (development only, not durable on Vercel)

All backends speak the same small Redis-like command set (GET SET DEL INCR ZADD ZREM ZREVRANGE) so the
app code is backend-agnostic. Postgres additionally keeps proper relational tables for reporting:
  orders, order_events, customers, audit_log   (query them from the Neon SQL editor any time)
"""
import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone

import httpx

from . import config

P = config.KV_PREFIX
IST = timezone(timedelta(hours=5, minutes=30))


def _k(key: str) -> str:
    return P + key


# ============================================================================ backends
class UpstashStore:
    name = "upstash-redis"

    def __init__(self, url: str, token: str):
        self.url = url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {token}"}
        self.client = httpx.Client(timeout=10)

    def cmd(self, *args):
        r = self.client.post(self.url, headers=self.headers, json=[str(a) for a in args])
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            raise RuntimeError(data["error"])
        return data.get("result")


class LocalStore:
    """JSON-file emulation of the Redis subset we use."""
    name = "local-file (not durable)"

    def __init__(self, path: str):
        self.path = path
        self.lock = threading.Lock()
        self.data = {"kv": {}, "exp": {}, "z": {}}
        if os.path.exists(path):
            try:
                with open(path) as f:
                    self.data = json.load(f)
            except Exception:
                pass

    def _save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.data, f)
        os.replace(tmp, self.path)

    def _alive(self, key):
        exp = self.data["exp"].get(key)
        if exp and exp < time.time():
            self.data["kv"].pop(key, None)
            self.data["exp"].pop(key, None)
            return False
        return key in self.data["kv"]

    def cmd(self, *args):
        op = args[0].upper()
        with self.lock:
            kv, z = self.data["kv"], self.data["z"]
            if op == "GET":
                return kv.get(args[1]) if self._alive(args[1]) else None
            if op == "SET":
                kv[args[1]] = str(args[2])
                self.data["exp"].pop(args[1], None)
                if len(args) >= 5 and str(args[3]).upper() == "EX":
                    self.data["exp"][args[1]] = time.time() + int(args[4])
                self._save()
                return "OK"
            if op == "DEL":
                n = 0
                for k in args[1:]:
                    n += 1 if kv.pop(k, None) is not None or z.pop(k, None) is not None else 0
                self._save()
                return n
            if op == "INCR":
                v = int(kv.get(args[1], 0)) + 1
                kv[args[1]] = str(v)
                self._save()
                return v
            if op == "ZADD":
                z.setdefault(args[1], {})[str(args[3])] = float(args[2])
                self._save()
                return 1
            if op == "ZREM":
                z.get(args[1], {}).pop(str(args[2]), None)
                self._save()
                return 1
            if op == "ZREVRANGE":
                items = sorted(z.get(args[1], {}).items(), key=lambda x: -x[1])
                start, stop = int(args[2]), int(args[3])
                stop = len(items) if stop == -1 else stop + 1
                return [m for m, _ in items[start:stop]]
            raise NotImplementedError(op)


SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL, expires_at TIMESTAMPTZ);
CREATE TABLE IF NOT EXISTS zset (key TEXT, member TEXT, score DOUBLE PRECISION NOT NULL, PRIMARY KEY (key, member));
CREATE INDEX IF NOT EXISTS zset_key_score ON zset (key, score DESC);
CREATE TABLE IF NOT EXISTS orders (
  code TEXT PRIMARY KEY, phone TEXT, name TEXT, email TEXT, branch_id TEXT, fulfilment TEXT,
  status TEXT, payment_method TEXT, payment_status TEXT, utr TEXT,
  subtotal NUMERIC, delivery_fee NUMERIC, total NUMERIC, weight_kg NUMERIC, distance_km NUMERIC,
  paper_rate NUMERIC, created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ, data JSONB);
CREATE INDEX IF NOT EXISTS orders_created ON orders (created_at DESC);
CREATE INDEX IF NOT EXISTS orders_phone ON orders (phone);
CREATE TABLE IF NOT EXISTS order_events (
  id BIGSERIAL PRIMARY KEY, code TEXT, event TEXT, actor TEXT, detail JSONB, created_at TIMESTAMPTZ DEFAULT now());
CREATE INDEX IF NOT EXISTS order_events_code ON order_events (code);
CREATE TABLE IF NOT EXISTS customers (
  phone TEXT PRIMARY KEY, name TEXT, email TEXT, verified_at TIMESTAMPTZ, first_order_at TIMESTAMPTZ,
  last_order_at TIMESTAMPTZ, orders_count INT DEFAULT 0, total_spent NUMERIC DEFAULT 0);
CREATE TABLE IF NOT EXISTS audit_log (
  id BIGSERIAL PRIMARY KEY, actor TEXT, action TEXT, detail JSONB, created_at TIMESTAMPTZ DEFAULT now());
CREATE INDEX IF NOT EXISTS audit_created ON audit_log (created_at DESC);
"""


class PostgresStore:
    name = "postgres"

    def __init__(self, url: str):
        import psycopg  # noqa: F401  (imported lazily so the dependency is only needed with Postgres)
        self.url = url
        self.conn = None
        self.lock = threading.Lock()
        self._connect()
        with self.lock:
            self.conn.execute(SCHEMA)

    def _connect(self):
        import psycopg
        self.conn = psycopg.connect(self.url, autocommit=True, connect_timeout=10)

    def q(self, sql, params=(), fetch="all"):
        for attempt in (1, 2):
            try:
                with self.lock:
                    cur = self.conn.execute(sql, params)
                    if fetch == "one":
                        return cur.fetchone()
                    if fetch == "all":
                        return cur.fetchall() if cur.description else []
                    return None
            except Exception:
                if attempt == 2:
                    raise
                try:
                    self._connect()  # serverless instances may hold a stale connection
                except Exception:
                    pass

    def cmd(self, *args):
        op = args[0].upper()
        if op == "GET":
            r = self.q("SELECT value FROM kv WHERE key=%s AND (expires_at IS NULL OR expires_at > now())", (args[1],), "one")
            return r[0] if r else None
        if op == "SET":
            exp = None
            if len(args) >= 5 and str(args[3]).upper() == "EX":
                exp = datetime.now(timezone.utc) + timedelta(seconds=int(args[4]))
            self.q("INSERT INTO kv (key, value, expires_at) VALUES (%s,%s,%s) ON CONFLICT (key) DO UPDATE "
                   "SET value=EXCLUDED.value, expires_at=EXCLUDED.expires_at", (args[1], str(args[2]), exp), None)
            return "OK"
        if op == "DEL":
            keys = list(args[1:])
            self.q("DELETE FROM kv WHERE key = ANY(%s)", (keys,), None)
            self.q("DELETE FROM zset WHERE key = ANY(%s)", (keys,), None)
            return len(keys)
        if op == "INCR":
            r = self.q("INSERT INTO kv (key, value) VALUES (%s,'1') ON CONFLICT (key) DO UPDATE "
                       "SET value=(kv.value::bigint + 1)::text RETURNING value", (args[1],), "one")
            return int(r[0])
        if op == "ZADD":
            self.q("INSERT INTO zset (key, member, score) VALUES (%s,%s,%s) ON CONFLICT (key, member) "
                   "DO UPDATE SET score=EXCLUDED.score", (args[1], str(args[3]), float(args[2])), None)
            return 1
        if op == "ZREM":
            self.q("DELETE FROM zset WHERE key=%s AND member=%s", (args[1], str(args[2])), None)
            return 1
        if op == "ZREVRANGE":
            start, stop = int(args[2]), int(args[3])
            limit = None if stop == -1 else max(0, stop - start + 1)
            rows = self.q("SELECT member FROM zset WHERE key=%s ORDER BY score DESC OFFSET %s LIMIT %s",
                          (args[1], start, limit))
            return [r[0] for r in rows]
        raise NotImplementedError(op)


# ============================================================================ factory
_store = None


def store():
    global _store
    if _store is None:
        if config.DATABASE_URL:
            _store = PostgresStore(config.DATABASE_URL)
        elif config.KV_REST_API_URL and config.KV_REST_API_TOKEN:
            _store = UpstashStore(config.KV_REST_API_URL, config.KV_REST_API_TOKEN)
        else:
            path = config.LOCAL_DB_PATH
            if os.getenv("VERCEL") and not path.startswith("/tmp"):
                path = "/tmp/bc-localdb.json"  # read-only FS on Vercel; NOT durable
            _store = LocalStore(path)
    return _store


def backend_name() -> str:
    return store().name


def is_pg() -> bool:
    return isinstance(store(), PostgresStore)


# ============================================================================ KV helpers
def get_json(key, default=None):
    raw = store().cmd("GET", _k(key))
    if raw is None:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def set_json(key, value, ex: int | None = None):
    payload = json.dumps(value, separators=(",", ":"), default=str)
    if ex:
        return store().cmd("SET", _k(key), payload, "EX", ex)
    return store().cmd("SET", _k(key), payload)


def delete(key):
    return store().cmd("DEL", _k(key))


def incr(key) -> int:
    return int(store().cmd("INCR", _k(key)))


def zadd(key, score: float, member: str):
    return store().cmd("ZADD", _k(key), score, member)


def zrem(key, member: str):
    return store().cmd("ZREM", _k(key), member)


def zrevrange(key, start=0, stop=-1):
    return store().cmd("ZREVRANGE", _k(key), start, stop) or []


# ============================================================================ history / reporting
def _ts(t):
    return datetime.fromtimestamp(float(t), timezone.utc) if t else None


def record_order(o: dict):
    """Mirror an order into the relational table (Postgres only)."""
    if not is_pg():
        return
    s = store()
    s.q("""INSERT INTO orders (code, phone, name, email, branch_id, fulfilment, status, payment_method, payment_status, utr,
             subtotal, delivery_fee, total, weight_kg, distance_km, paper_rate, created_at, updated_at, data)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (code) DO UPDATE SET status=EXCLUDED.status, payment_status=EXCLUDED.payment_status,
             utr=EXCLUDED.utr, updated_at=EXCLUDED.updated_at, data=EXCLUDED.data""",
        (o["code"], o["phone"], o.get("name"), o.get("email"), o.get("branch_id"), o["fulfilment"], o["status"],
         o["payment_method"], o["payment_status"], o.get("utr"), o["subtotal"], o["delivery_fee"], o["total"],
         o["weight_kg"], o.get("distance_km"), o.get("paper_rate"), _ts(o["created"]), _ts(o["updated"]),
         json.dumps(o, default=str)), None)


def record_customer(phone: str, name: str, email: str | None, order_total: float | None = None, verified=False):
    if not is_pg():
        return
    s = store()
    now = datetime.now(timezone.utc)
    s.q("""INSERT INTO customers (phone, name, email, verified_at, first_order_at, last_order_at, orders_count, total_spent)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (phone) DO UPDATE SET
             name=COALESCE(NULLIF(EXCLUDED.name,''), customers.name),
             email=COALESCE(NULLIF(EXCLUDED.email,''), customers.email),
             verified_at=COALESCE(EXCLUDED.verified_at, customers.verified_at),
             first_order_at=COALESCE(customers.first_order_at, EXCLUDED.first_order_at),
             last_order_at=COALESCE(EXCLUDED.last_order_at, customers.last_order_at),
             orders_count=customers.orders_count + EXCLUDED.orders_count,
             total_spent=customers.total_spent + EXCLUDED.total_spent""",
        (phone, name or "", email or "", now if verified else None, now if order_total is not None else None,
         now if order_total is not None else None, 1 if order_total is not None else 0, order_total or 0), None)


def event(code: str, ev: str, actor: str, detail: dict | None = None):
    if is_pg():
        store().q("INSERT INTO order_events (code, event, actor, detail) VALUES (%s,%s,%s,%s)",
                  (code, ev, actor, json.dumps(detail or {}, default=str)), None)


def audit(actor: str, action: str, detail: dict | None = None):
    """Who changed what – rates, settings, logins, payments. Kept in every backend."""
    entry = {"actor": actor, "action": action, "detail": detail or {}, "ts": time.time()}
    if is_pg():
        store().q("INSERT INTO audit_log (actor, action, detail) VALUES (%s,%s,%s)",
                  (actor, action, json.dumps(detail or {}, default=str)), None)
    else:
        zadd("audit", entry["ts"], json.dumps(entry, separators=(",", ":"), default=str))


def audit_log(limit=200) -> list:
    if is_pg():
        rows = store().q("SELECT actor, action, detail, extract(epoch from created_at) FROM audit_log "
                         "ORDER BY created_at DESC LIMIT %s", (limit,))
        return [{"actor": a, "action": b, "detail": c, "ts": float(t)} for a, b, c, t in rows]
    out = []
    for m in zrevrange("audit", 0, limit - 1):
        try:
            out.append(json.loads(m))
        except Exception:
            pass
    return out


def history(date_from: str, date_to: str, search: str = "", status: str = "", limit: int = 3000) -> list:
    """Orders between two IST dates (inclusive). Returns raw order dicts, newest first."""
    d1 = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=IST)
    d2 = datetime.strptime(date_to, "%Y-%m-%d").replace(tzinfo=IST) + timedelta(days=1)
    search = (search or "").strip().lower()
    if is_pg():
        sql = "SELECT data FROM orders WHERE created_at >= %s AND created_at < %s"
        params = [d1, d2]
        if status:
            sql += " AND status = %s"
            params.append(status)
        if search:
            sql += " AND (phone LIKE %s OR lower(code) LIKE %s OR lower(coalesce(name,'')) LIKE %s)"
            params += [f"%{search}%"] * 3
        sql += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)
        return [r[0] if isinstance(r[0], dict) else json.loads(r[0]) for r in store().q(sql, tuple(params))]
    out = []
    for code in zrevrange("orders", 0, limit - 1):
        o = get_json(f"order:{code}")
        if not o:
            continue
        t = datetime.fromtimestamp(o["created"], timezone.utc)
        if t < d1:
            break
        if t >= d2 or (status and o["status"] != status):
            continue
        if search and search not in f"{o['phone']} {o['code'].lower()} {(o.get('name') or '').lower()}":
            continue
        out.append(o)
    return out
