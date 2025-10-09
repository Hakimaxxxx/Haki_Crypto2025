"""Unified Redis read-through cache layer (Phase 4 Standard DoD).

Features:
- Lazy singleton client
- Read-through get_or_set with serializer
- Versioned key support (portfolio_version / global)
- Hit/Miss counters (Redis hash + in-process fallback)
- Graceful degradation if Redis unavailable (fallback to loader)
- Convenience helpers for common namespaces (prices, ohlcv, whales, dominance, fg, marketcap)
"""

from __future__ import annotations
import sys ,os, json, time, hashlib, threading
from typing import Callable, Any, Optional
import streamlit as st

# st.write("Python exec:", sys.executable)
# st.write("VENV:", os.getenv("VIRTUAL_ENV"))


print("[DEBUG] setup Redis client")

# Optional redis import (graceful degradation if not installed in current interpreter)
try:
    import redis  # type: ignore
    _REDIS_IMPORT_ERROR = None
except ModuleNotFoundError as _e:  # user might run with wrong python (global vs venv)
    redis = None  # type: ignore
    _REDIS_IMPORT_ERROR = _e
    print("[WARN] redis module not found – cache layer disabled. (Activate venv?)")

# Kết nối Redis (only if redis module available)
redis_uri = os.getenv("REDIS_URI", "redis://localhost:6379/0")
if redis is not None:
    try:
        redis_client = redis.Redis.from_url(redis_uri)
    except Exception as _conn_e:
        redis_client = None  # type: ignore
        print(f"[WARN] Initial Redis client creation failed: {_conn_e}")
else:
    redis_client = None  # type: ignore



_LOCK = threading.Lock()
_client = None
_STATS_LOCAL = {"hit": 0, "miss": 0, "error": 0}
_DEFAULT_TTL = 60

REDIS_URI_ENV = "REDIS_URI"

# Key namespaces
# cache:v{version}:{domain}:{...}
# If version None -> use v0

def _hash(s: str) -> str:
    return hashlib.sha1(s.encode('utf-8')).hexdigest()[:12]

def get_client():
    global _client
    if redis is None:
        return None
    if _client is not None:
        print("[DEBUG] Redis client reused")
        return _client
    # if redis.Redis is None:
    #     import redis
    #     print("[DEBUG] Redis library not available")
    #     pass
    with _LOCK:
        if _client is None:
            try:
                _client = redis.Redis.from_url(redis_uri, decode_responses=True)
                # test ping
                _client.ping()
                print("[DEBUG] Redis connection established")
            except Exception as e:
                # Keep None; caller will treat as unavailable
                _client = None
                print(f"[ERROR] Redis connection failed: {e}")
    return _client

def reset_client():
    """Force reset the cached Redis client (for health panel retry)."""
    global _client
    with _LOCK:
        _client = None

def redis_latency_ms() -> float | None:
    """Measure ping latency in milliseconds (best effort)."""
    c = get_client()
    if not c:
        return None
    try:
        import time as _t
        t0 = _t.perf_counter()
        c.ping()
        return ( _t.perf_counter() - t0 ) * 1000.0
    except Exception:
        return None

def redis_available() -> bool:
    if redis is None:
        return False
    c = get_client()
    if not c:
        return False
    try:
        c.ping()
        return True
    except Exception:
        return False

def redis_diagnostics() -> dict:
    """Return diagnostics about redis import / connection state."""
    info = {"import_ok": _REDIS_IMPORT_ERROR is None}
    if _REDIS_IMPORT_ERROR is not None:
        info["import_error"] = str(_REDIS_IMPORT_ERROR)
    c = _client
    info["client_created"] = c is not None
    if c is not None:
        try:
            info["ping"] = bool(c.ping())
        except Exception as e:
            info["ping_error"] = str(e)
    return info

# Portfolio version (for invalidation)
PORTFOLIO_VERSION_KEY = "cache:portfolio_version"


def get_portfolio_version() -> int:
    c = get_client()
    if not c:
        return 0
    try:
        v = c.get(PORTFOLIO_VERSION_KEY)
        return int(v) if v else 0
    except Exception:
        return 0


def bump_portfolio_version() -> Optional[int]:
    c = get_client()
    if not c:
        return None
    try:
        return c.incr(PORTFOLIO_VERSION_KEY)
    except Exception:
        return None


def _record_stat(key: str):
    _STATS_LOCAL[key] = _STATS_LOCAL.get(key, 0) + 1
    c = get_client()
    if not c:
        return
    try:
        c.hincrby("cache:stats", key, 1)
    except Exception:
        pass


def get_cache_stats() -> dict:
    stats = dict(_STATS_LOCAL)
    c = get_client()
    if not c:
        return stats
    try:
        h = c.hgetall("cache:stats") or {}
        for k, v in h.items():
            try:
                stats[k] = int(v)
            except Exception:
                stats[k] = v
    except Exception:
        pass
    return stats


def _build_key(domain: str, parts: list[str], version: Optional[int] = None) -> str:
    ver = version if version is not None else 0
    suffix = ":".join(parts)
    return f"cache:v{ver}:{domain}:{suffix}"


def get_or_set(domain: str,
               identity_parts: list[str],
               loader: Callable[[], Any],
               ttl: int = _DEFAULT_TTL,
               version: Optional[int] = None,
               serializer = json.dumps,
               deserializer = json.loads) -> Any:
    """Read-through cache getter.

    If redis unavailable or any error -> returns loader() result.
    """
    key = _build_key(domain, identity_parts, version)
    print(f"[DEBUG] Generated Redis key: {key}")  # Log the generated key

    if not redis_available():
        print("[DEBUG] Redis unavailable, skip cache, use loader only")
        return loader()
    last_exception = None
    for attempt in range(2):
        c = get_client()
        if not c:
            last_exception = Exception("Redis not available")
            time.sleep(0.1)
            continue
        try:
            val = c.get(key)
            if val is not None:
                _record_stat("hit")
                print(f"[DEBUG][cache:{domain}] HIT {key} (attempt {attempt+1})")
                try:
                    return deserializer(val)
                except Exception:
                    print(f"[DEBUG][cache:{domain}] Decode error -> invalidate and retry")
                    break
            # Check if key already exists before setting
            exists = c.exists(key)
            print(f"[DEBUG][cache:{domain}] EXISTS check {key} -> {exists}")  # Log the existence check
            if exists:
                print(f"[DEBUG][cache:{domain}] Key already exists but get() returned None -> race? overwriting")
            else:
                print(f"[DEBUG][cache:{domain}] MISS {key} -> computing & set TTL={ttl}s")
            # miss, try to set
            data = loader()
            try:
                c.set(key, serializer(data), ex=ttl)
                print(f"[DEBUG][cache:{domain}] SET {key} TTL={ttl}s")
            except Exception:
                st.write("Warning: Không lưu được cache Redis.")
                last_exception = Exception("Set cache failed")
                time.sleep(0.1)
                continue
            _record_stat("miss")
            print(f"[DEBUG][cache:{domain}] MISS return (attempt {attempt+1})")
            return data
        except Exception as e:
            last_exception = e
            print(f"[DEBUG][cache:{domain}] ERROR attempt {attempt+1}: {e}")
            time.sleep(0.1)
            continue
    # Nếu qua 5 lần vẫn fail
    try:
        _record_stat("miss")
        print(f"[DEBUG][cache:{domain}] MISS fallback (after retries)")
        return loader()
    except Exception as e:
        _record_stat("error")
        print(f"[DEBUG][cache:{domain}] ERROR fallback loader failed")
        raise last_exception if last_exception else e

# Convenience wrappers -------------------------------------------------------

def cache_prices(coins: list[str], fetch_fn: Callable[[], Any], ttl: int = 80):
    identity = [ _hash(",".join(sorted(coins))) ]
    # Prices không phụ thuộc portfolio version => version None
    print("[DEBUG] cache price.....")
    return get_or_set("prices", identity, fetch_fn, ttl=ttl, version=None)

def cache_ohlcv(symbol: str, bar: str, fetch_fn: Callable[[], Any], ttl: int = 90):
    # Caching temporarily disabled for OHLCV (pass-through)
    return fetch_fn()

def cache_whales(chain: str, token: str, fetch_fn: Callable[[], Any], ttl: int = 80):
    # Caching temporarily disabled for whale events (pass-through)
    return fetch_fn()

def cache_metric(metric: str, fetch_fn: Callable[[], Any], ttl: int = 300):
    identity = [metric]
    print("[DEBUG] cache metric.....")
    return get_or_set("metric", identity, fetch_fn, ttl=ttl, version=None)

def invalidate_prefix(domain: str):
    """Best-effort invalidation (scan & delete). Use sparingly (O(n))."""
    c = get_client()
    if not c:
        return 0
    try:
        pattern = f"cache:v*: {domain}:*"  # (not used currently, reserved)
        # Simpler: just bump version logic for portfolio-related domains.
        return 0
    except Exception:
        return 0

# Portfolio-related derived data (e.g. distribution, pnl breakdown) có thể gắn version.
# Khi update_portfolio_data -> bump_portfolio_version().

__all__ = [
    "get_client", "redis_available", "get_or_set", "get_portfolio_version",
    "bump_portfolio_version", "cache_prices", "cache_ohlcv", "cache_whales",
    "cache_metric", "get_cache_stats", "reset_client", "redis_latency_ms"
]
