"""Tiny key-value store.

Production: Upstash Redis over REST (the store Vercel provisions as KV_REST_API_URL / KV_REST_API_TOKEN).
Local dev: a JSON file with the same commands, so the app runs with zero setup.

Only a handful of Redis commands are used: GET SET(EX) DEL INCR ZADD ZREVRANGE ZREM.
All keys are prefixed with KV_PREFIX so the store can be shared safely with other apps.
"""
import json
import os
import threading
import time

import httpx

from . import config

P = config.KV_PREFIX


def _k(key: str) -> str:
    return P + key


class UpstashStore:
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
                zs = z.setdefault(args[1], {})
                zs[str(args[3])] = float(args[2])
                self._save()
                return 1
            if op == "ZREM":
                z.get(args[1], {}).pop(str(args[2]), None)
                self._save()
                return 1
            if op == "ZREVRANGE":
                zs = z.get(args[1], {})
                items = sorted(zs.items(), key=lambda x: -x[1])
                start, stop = int(args[2]), int(args[3])
                stop = len(items) if stop == -1 else stop + 1
                return [m for m, _ in items[start:stop]]
            raise NotImplementedError(op)


_store = None


def store():
    global _store
    if _store is None:
        if config.KV_REST_API_URL and config.KV_REST_API_TOKEN:
            _store = UpstashStore(config.KV_REST_API_URL, config.KV_REST_API_TOKEN)
        else:
            path = config.LOCAL_DB_PATH
            if os.getenv("VERCEL") and not path.startswith("/tmp"):
                path = "/tmp/bc-localdb.json"  # read-only FS on Vercel; data is NOT durable here
            _store = LocalStore(path)
    return _store


def backend_name() -> str:
    return "upstash-redis" if isinstance(store(), UpstashStore) else "local-file (not durable)"


# ---- JSON helpers -------------------------------------------------------------
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
