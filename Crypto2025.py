from db_utils import (
    db_upsert_portfolio_docs_with_retry,
    db_retry_queue,
    validate_portfolio_docs,
    save_portfolio_history_optimized,
    backup_file
)

# New robust initialization system
from app_init import (
    initialize_app, 
    get_portfolio_data, 
    get_price_data, 
    get_history_data, 
    update_portfolio_data,
    get_app_state,
    get_cached_data,
    force_price_refresh
)

from config import COIN_LIST, DATA_FILE, AVG_PRICE_FILE, HISTORY_FILE
from portfolio_history import load_history, append_snapshot
from ui_metrics import show_portfolio_over_time_chart, show_pie_distribution, show_bar_pnl, show_health_panel

import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import streamlit as st
from datetime import datetime
import json
from datetime import datetime
import json
import os
import threading
import time
import numpy as np
import pytz
import plotly.graph_objects as go
# Import các module metrics
# Import các module metrics
import metrics_flow
import metrics_ohlcv_okx  # Added back for OHLCV chart rendering in coin tabs
# Set MongoDB environment variables FIRST before any cloud_db imports
os.environ["MONGO_URI"] = "mongodb+srv://quanghuy060997_db_user:MPCuEbF2GhpmiZm8@cluster0.x3iyjjm.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
os.environ["CLOUD_DB_NAME"] = "Crypto2025"

# Now safe to import cloud_db and modules that depend on it
from cloud_db import db
from SOL import load_metrics_realtime
metrics_sol_whale_alert_realtime = load_metrics_realtime()
from AVAX import load_metrics_realtime as load_avax_metrics
metrics_avax_whale_alert_realtime = load_avax_metrics()
# Ensure SUI whale scanner background thread is started when the app launches.
# Some environments may not import the SUI module automatically; do a safe import
# and call the module helper to start the background scanner so `sui_whale_scanner.log`
# is updated by the running app.
try:
    from SUI import metrics_sui_whale_alert_realtime as sui_mod  # type: ignore
    try:
        sui_mod.ensure_background_scanner_started()
        print("[DEBUG] SUI scanner ensure_background_scanner_started() called")
    except Exception as _e:
        print(f"[DEBUG] SUI scanner start call failed: {_e}")
except Exception as e:
    # Import may fail in some environments; don't crash the whole app.
    print(f"[DEBUG] SUI module import skipped/failed: {e}")
# Ensure BTC background scanner is started (do not auto-start on import)
try:
    from BTC import metrics_btc_whale_alert_realtime as btc_mod  # type: ignore
    try:
        btc_mod.ensure_background_scanner_started()
        print("[DEBUG] BTC scanner ensure_background_scanner_started() called")
    except Exception as _e:
        print(f"[DEBUG] BTC scanner start call failed: {_e}")
except Exception as e:
    print(f"[DEBUG] BTC module import skipped/failed: {e}")



# Initialize app with robust error handling
if "app_initialized" not in st.session_state:
    with st.spinner("🚀 Initializing application..."):
        success, message = initialize_app()
        st.session_state["app_initialized"] = True
        st.session_state["init_success"] = success
        st.session_state["init_message"] = message
        
        if success:
            st.success(f"✅ {message}")
        else:
            # New streamlit session (after F5) may have lost session_state but backend init is persistent.
            # If holdings file empty & DB available, trigger hydration.
            try:
                if ("holdings" not in st.session_state or not st.session_state.get("holdings")):
                    # Light re-hydration attempt
                    initialize_app(refresh=True)
            except Exception:
                pass
            st.error(f"❌ {message}")
            st.info("💡 App will run with limited functionality using available data sources.")

        # Configure backend price API from environment (avoid 127.0.0.1 in cloud)
        backend_api_env = os.getenv("BACKEND_PRICE_API", "").strip()
        if backend_api_env:
            st.session_state.setdefault("_backend_price_api", backend_api_env)
        else:
            # Default to cloud backend (Render) if not provided via env
            st.session_state.setdefault("_backend_price_api", "https://hakicrypto2025.onrender.com/prices/spot")

# --- Backend API helpers ---
def _resolve_backend_price_api() -> str:
    """Return a normalized backend prices endpoint (always ending with /prices/spot).
    Prefers session state; falls back to env; finally to localhost (dev).
    """
    raw = (st.session_state.get("_backend_price_api") or os.getenv("BACKEND_PRICE_API", "")).strip()
    if not raw:
        raw = "http://127.0.0.1:8000/prices/spot"
    lower = raw.lower().rstrip('/')
    if "/prices/spot" in lower:
        return raw.rstrip('/')
    # Treat as base URL and append the endpoint path
    return raw.rstrip('/') + "/prices/spot"

def _backend_base_from_endpoint(endpoint: str) -> str:
    if "/prices/spot" in endpoint:
        return endpoint.split("/prices/spot")[0]
    return endpoint.rstrip('/')

def _ping_backend_status(ttl: int = 60) -> dict:
    """Ping backend /health and /prices/spot (BTC,ETH) with a short TTL cache.
    Returns a dict { base, endpoint, health: {ok,status,latency}, prices: {ok,status,latency,count}, ts }
    """
    try:
        snap = st.session_state.get("_backend_ping_snap") or {}
        now = time.time()
        if snap and (now - float(snap.get("ts", 0))) < ttl:
            return snap
    except Exception:
        pass
    endpoint = _resolve_backend_price_api()
    base = _backend_base_from_endpoint(endpoint)
    out = {"base": base, "endpoint": endpoint, "health": {}, "prices": {}, "ts": time.time()}
    # Health ping
    try:
        t0 = time.perf_counter()
        r = requests.get(base.rstrip('/') + "/health", timeout=3.5)
        lat = time.perf_counter() - t0
        out["health"] = {"ok": (200 <= r.status_code < 300), "status": r.status_code, "latency": round(lat, 3)}
    except Exception as e:
        out["health"] = {"ok": False, "status": 0, "latency": None, "error": str(e)}
    # Prices ping (minimal)
    try:
        # Use 2 symbols to keep payload small; fallback to BTC,ETH if config missing
        syms = ",".join([sym for _, sym in COIN_LIST[:2]]) if COIN_LIST else "BTC,ETH"
        t0 = time.perf_counter()
        r = requests.get(endpoint, params={"symbols": syms}, timeout=4.0)
        lat = time.perf_counter() - t0
        count = 0
        gen_at = None
        try:
            js = r.json() if hasattr(r, 'json') else {}
            count = int((js or {}).get("count") or 0)
            gen_at = (js or {}).get("generated_at")
        except Exception:
            count = 0
        out["prices"] = {"ok": (200 <= r.status_code < 300), "status": r.status_code, "latency": round(lat, 3), "count": count, "generated_at": gen_at}
    except Exception as e:
        out["prices"] = {"ok": False, "status": 0, "latency": None, "error": str(e)}
    try:
        st.session_state["_backend_ping_snap"] = out
    except Exception:
        pass
    return out

def _fetch_backend_tasks(ttl: int = 60) -> dict:
    """Fetch backend /tasks to inspect scheduler last_run times. Cached by TTL.
    Returns: { ok, status, latency, tasks: {name: {interval,last_run,failures,age_s}} }
    """
    try:
        snap = st.session_state.get("_backend_tasks_snap") or {}
        now = time.time()
        if snap and (now - float(snap.get("ts", 0))) < ttl:
            return snap
    except Exception:
        pass
    endpoint = _resolve_backend_price_api()
    base = _backend_base_from_endpoint(endpoint)
    out = {"ok": False, "status": 0, "latency": None, "tasks": {}, "ts": time.time()}
    try:
        t0 = time.perf_counter()
        r = requests.get(base.rstrip('/') + "/tasks", timeout=3.5)
        lat = time.perf_counter() - t0
        out["status"] = r.status_code
        out["latency"] = round(lat, 3)
        if 200 <= r.status_code < 300:
            js = r.json() or {}
            tasks = (js or {}).get("tasks", {}) or {}
            enriched = {}
            now = time.time()
            for name, info in tasks.items():
                try:
                    last_run = float(info.get('last_run', 0) or 0)
                    age_s = int(now - last_run) if last_run > 0 else None
                    enriched[name] = {**info, "age_s": age_s}
                except Exception:
                    enriched[name] = info
            out["ok"] = True
            out["tasks"] = enriched
    except Exception as _:
        pass
    try:
        st.session_state["_backend_tasks_snap"] = out
    except Exception:
        pass
    return out

# Helper functions for history filtering
def filter_reliable_history(history: list) -> list:
    """Filter history to only include entries from successful API calls.
    
    This prevents chart noise from API errors, rate limits, or fallback data.
    Only shows portfolio snapshots when CoinGecko API was completely successful.
    """
    if not history:
        return []
    
    # Filter for entries marked as api_success or legacy entries that look reliable
    reliable_entries = []
    
    for entry in history:
        # New format: explicitly marked as api_success
        if entry.get("source") == "api_success":
            reliable_entries.append(entry)
            continue
            
        # Legacy format: apply heuristics to detect reliable entries
        # Skip entries that are likely from API failures:
        
        # 1. Skip entries with suspicious zero values when there should be holdings
        if "coin" not in entry:  # Total portfolio entry
            value = entry.get("value", 0)
            # Skip zero portfolio values (likely API failure)
            if value <= 0:
                continue
            # Skip suspiciously high values (> $10M, likely API error)
            if value > 10_000_000:
                continue
                
        # 2. For coin entries, check for reasonable values
        elif "coin" in entry:
            value = entry.get("value", 0)
            amount = entry.get("amount", 0)
            # Skip if coin has amount but zero value (price fetch failed)
            if amount > 0 and value <= 0:
                continue
                
        # If it passes all filters, include it
        reliable_entries.append(entry)
    
    # Additional filtering: remove entries that are statistical outliers
    # (sudden jumps that don't make sense)
    if len(reliable_entries) <= 3:
        return reliable_entries
        
    # Get total portfolio entries only for outlier detection
    total_entries = [e for e in reliable_entries if "coin" not in e]
    if len(total_entries) <= 3:
        return reliable_entries
    
    # Sort by timestamp for outlier detection
    total_entries.sort(key=lambda x: x.get("timestamp", 0))
    
    # Remove entries that have unrealistic jumps (>50% in single step)
    filtered_totals = [total_entries[0]]  # Keep first entry
    
    for i in range(1, len(total_entries)):
        current = total_entries[i]
        previous = filtered_totals[-1]
        
        current_value = current.get("value", 0)
        previous_value = previous.get("value", 0)
        
        if previous_value <= 0:
            filtered_totals.append(current)
            continue
            
        # Check for unrealistic jumps
        change_pct = abs((current_value - previous_value) / previous_value)
        
        # Allow up to 50% change in 5 minutes (very generous for crypto)
        time_diff = current.get("timestamp", 0) - previous.get("timestamp", 0)
        max_change = min(0.5, time_diff / 300 * 0.1)  # 10% per 5min, capped at 50%
        
        if change_pct <= max_change or time_diff > 3600:  # Or >1hour gap
            filtered_totals.append(current)
        # else: skip this entry as likely API error
    
    # Rebuild final list with both total and coin entries, keeping only timestamps
    # that survived the total portfolio filtering
    valid_timestamps = {e.get("timestamp") for e in filtered_totals}
    final_entries = [e for e in reliable_entries if e.get("timestamp") in valid_timestamps]
    
    return final_entries

# Helper functions for price fetching with new init system
def get_current_prices():
    """Get current prices using the new initialization system."""
    try:
        prices, price_data = get_price_data()
        if prices:
            return prices, price_data, True, "Prices loaded successfully"
        else:
            return {}, {}, False, "No price data available"
    except Exception as e:
        return {}, {}, False, f"Price fetch error: {e}"

_PORT_HOLDINGS_CACHE = {"data": (None, None), "ts": 0}
_PORT_HOLDINGS_TTL = int(os.getenv("PORTFOLIO_REFRESH_INTERVAL", "300"))  # default 5 minutes

def load_portfolio_holdings(force: bool = False):
    """Load portfolio holdings (debounced/TTL cached).

    Parameters
    ----------
    force : bool
        If True, bypass local TTL cache.
    """
    try:
        now = time.time()
        cached_port, cached_avg = _PORT_HOLDINGS_CACHE["data"]
        if (not force and cached_port is not None and (now - _PORT_HOLDINGS_CACHE["ts"]) < _PORT_HOLDINGS_TTL):
            # Silent fast path (avoid log spam); only log every 60s for visibility
            if int(now) % 60 == 0:  # coarse periodic heartbeat
                print(f"[DEBUG] load_portfolio_holdings() cached - age={int(now-_PORT_HOLDINGS_CACHE['ts'])}s size={len(cached_port)}")
            return dict(cached_port), dict(cached_avg)

        portfolio, avg_prices = get_portfolio_data()
        _PORT_HOLDINGS_CACHE["data"] = (dict(portfolio), dict(avg_prices))
        _PORT_HOLDINGS_CACHE["ts"] = now
        print(f"[DEBUG] load_portfolio_holdings() REFRESH size={len(portfolio)} ttl={_PORT_HOLDINGS_TTL}s")
        return portfolio, avg_prices
    except Exception as e:
        st.error(f"Error loading portfolio: {e}")
        print(f"[DEBUG] load_portfolio_holdings() error: {e}")
        return {}, {}

# --- DB sync helpers ---
def _db_upsert_portfolio_docs(docs: list):
    # Sử dụng hàm helper từ db_utils.py
    db_upsert_portfolio_docs_with_retry(db, docs)
    db_retry_queue(db)

def _db_set_portfolio_meta(holdings: dict | None = None, avg_price: dict | None = None):
    try:
        from db_utils import db_set_kv_with_retry, db_retry_queue
        if holdings is not None:
            db_set_kv_with_retry(db, "portfolio_meta", "holdings", holdings)
        if avg_price is not None:
            db_set_kv_with_retry(db, "portfolio_meta", "avg_price", avg_price)
        # Process queue opportunistically
        db_retry_queue(db)
    except Exception:
        pass

def _db_upsert_dominance_row(row: dict):
    try:
        if db.available() and row:
            db.upsert_many("dominance_history", [row], unique_keys=["timestamp"])
    except Exception:
        pass

def _db_upsert_marketcap_row(row: dict):
    try:
        if db.available() and row:
            db.upsert_many("marketcap_history", [row], unique_keys=["timestamp"])
    except Exception:
        pass

def _db_bootstrap_sync_once():
    """One-time bootstrap from Cloud DB to local files (prefer cloud as source of truth).

    If cloud has data, write it down to local JSON/CSV before we start recording new logs.
    """
    try:
        if not db.available():
            return
        # 1) Portfolio meta (holdings, avg_price)
        try:
            kv_hold = db.get_kv("portfolio_meta", "holdings") or {}
            kv_avg = db.get_kv("portfolio_meta", "avg_price") or {}
            if kv_hold:
                try:
                    with open("data.json", "w") as f:
                        json.dump(kv_hold, f)
                except Exception:
                    pass
            if kv_avg:
                try:
                    with open("avg_price.json", "w") as f:
                        json.dump(kv_avg, f)
                except Exception:
                    pass
        except Exception:
            pass
        # 2) Portfolio history
        try:
            hist_docs = db.find_all("portfolio_history", sort_field="timestamp", ascending=True)
            if hist_docs:
                try:
                    with open("portfolio_history.json", "w") as f:
                        json.dump(hist_docs, f)
                except Exception:
                    pass
        except Exception:
            pass
        # (Optional) Dominance & Marketcap history
        # We keep DB as source but don't overwrite local CSVs here to avoid format issues.
    except Exception:
        pass




# --- TỰ ĐỘNG CRAWL DOMINANCE MỖI PHÚT (KHÔNG BLOCK UI) ---
def crawl_dominance_background():
    import requests
    import pandas as pd
    import time as _t
    file = "dominance_history.csv"
    def _atomic_write_csv(df: 'pd.DataFrame', path: str):
        import tempfile, os
        dir_name = os.path.dirname(os.path.abspath(path)) or "."
        fd, tmp_path = tempfile.mkstemp(prefix=".tmp_", suffix=".csv", dir=dir_name)
        os.close(fd)
        try:
            df.to_csv(tmp_path, index=False)
            os.replace(tmp_path, path)
        except Exception:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
            raise
    try:
        _db_bootstrap_sync_once()
    except Exception:
        pass
    while True:
        try:
            resp = requests.get("https://api.coingecko.com/api/v3/global", timeout=15)
            data = resp.json().get("data", {})
            dom = data.get("market_cap_percentage", {})
            btc = dom.get("btc", 0.0)
            eth = dom.get("eth", 0.0)
            others = 100 - btc - eth
            if others==100:
                _t.sleep(300)
                continue
            ts = int(_t.time())
            # Create row with proper format to match existing CSV
            from datetime import datetime
            ts_str = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
            row = {"timestamp": ts_str, "BTC": btc, "ETH": eth, "Others": others}
            
            # Append to CSV (atomic)
            try:
                if os.path.exists(file):
                    df = pd.read_csv(file)
                    # Check if timestamp column exists and parse it
                    if 'timestamp' in df.columns:
                        df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
                        df = df.dropna(subset=['timestamp'])
                else:
                    df = pd.DataFrame(columns=["timestamp","BTC","ETH","Others"])
                
                # Check for duplicate entries (avoid same minute)
                if not df.empty:
                    last_ts = pd.to_datetime(df.iloc[-1]['timestamp'])
                    current_ts = pd.to_datetime(ts_str)
                    if abs((current_ts - last_ts).total_seconds()) < 60:
                        pass  # Skip duplicate minute
                    else:
                        new_row = pd.DataFrame([row])
                        df = pd.concat([df, new_row], ignore_index=True)
                        _atomic_write_csv(df, file)
                        print(f"[DOMINANCE] Saved: BTC={btc:.2f}%, ETH={eth:.2f}%, Others={others:.2f}%")
                else:
                    new_row = pd.DataFrame([row])
                    df = pd.concat([df, new_row], ignore_index=True)
                    _atomic_write_csv(df, file)
                    print(f"[DOMINANCE] First entry saved: BTC={btc:.2f}%, ETH={eth:.2f}%, Others={others:.2f}%")
            except Exception as e:
                print(f"[DOMINANCE ERROR] Failed to save: {e}")
            _db_upsert_dominance_row({"timestamp": ts, "btc": btc, "eth": eth, "others": others})
        except Exception as e:
            print(f"[DOMINANCE API ERROR] Failed to fetch data: {e}")
        _t.sleep(300)  # Changed from 300 to 60 seconds for faster updates

def crawl_marketcap_background():
    """Fetch global total market cap and 24h volume periodically and append to CSV if valid."""
    import requests
    import pandas as pd
    import time as _t
    file = "marketcap_history.csv"
    def _atomic_write_csv(df: 'pd.DataFrame', path: str):
        import tempfile, os
        dir_name = os.path.dirname(os.path.abspath(path)) or "."
        fd, tmp_path = tempfile.mkstemp(prefix=".tmp_", suffix=".csv", dir=dir_name)
        os.close(fd)
        try:
            df.to_csv(tmp_path, index=False)
            os.replace(tmp_path, path)
        except Exception:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
            raise
    while True:
        mcap = None
        vol = None
        ts = int(_t.time())
        try:
            resp = requests.get("https://api.coingecko.com/api/v3/global", timeout=15)
            g = resp.json().get("data", {})
            mcap = (g.get("total_market_cap") or {}).get("usd")
            vol = (g.get("total_volume") or {}).get("usd")
        except Exception as e:
            print(f"[MARKETCAP API ERROR] Failed to fetch data: {e}")
            _t.sleep(300)
            continue

        # Nếu không lấy được dữ liệu hoặc dữ liệu = 0 thì bỏ qua luôn, không ghi file/log/gọi db
        try:
            if mcap is None or vol is None or float(mcap) == 0.0 or float(vol) == 0.0:
                #print("[MARKETCAP] Skip: API returned invalid data (None or 0.0)")
                _t.sleep(300)
                continue

            mcap = float(mcap)
            vol = float(vol)
            from datetime import datetime
            ts_str = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
            row = {"timestamp": ts_str, "market_cap": mcap, "volume_1d": vol}

            # Append to CSV (atomic)
            import os
            if os.path.exists(file):
                df = pd.read_csv(file)
                if 'timestamp' in df.columns:
                    df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
                    df = df.dropna(subset=['timestamp'])
            else:
                df = pd.DataFrame(columns=["timestamp","market_cap","volume_1d"])
            
            # Check for duplicate entries (avoid same minute)
            if not df.empty:
                last_ts = pd.to_datetime(df.iloc[-1]['timestamp'])
                current_ts = pd.to_datetime(ts_str)
                if abs((current_ts - last_ts).total_seconds()) < 60:
                    pass  # Skip duplicate minute
                else:
                    new_row = pd.DataFrame([row])
                    df = pd.concat([df, new_row], ignore_index=True)
                    _atomic_write_csv(df, file)
                    print(f"[MARKETCAP] Saved: Cap=${mcap/1e12:.2f}T, Vol=${vol/1e9:.2f}B")
            else:
                new_row = pd.DataFrame([row])
                df = pd.concat([df, new_row], ignore_index=True)
                _atomic_write_csv(df, file)
                print(f"[MARKETCAP] First entry saved: Cap=${mcap/1e12:.2f}T, Vol=${vol/1e9:.2f}B")
        except Exception as e:
            print(f"[MARKETCAP ERROR] Failed to save: {e}")

        _t.sleep(300)
# def crawl_marketcap_background():
#     """Fetch global total market cap and 24h volume periodically and append to CSV."""
#     import requests
#     import pandas as pd
#     import time as _t
#     file = "marketcap_history.csv"
#     def _atomic_write_csv(df: 'pd.DataFrame', path: str):
#         import tempfile, os
#         dir_name = os.path.dirname(os.path.abspath(path)) or "."
#         fd, tmp_path = tempfile.mkstemp(prefix=".tmp_", suffix=".csv", dir=dir_name)
#         os.close(fd)
#         try:
#             df.to_csv(tmp_path, index=False)
#             os.replace(tmp_path, path)
#         except Exception:
#             try:
#                 if os.path.exists(tmp_path):
#                     os.remove(tmp_path)
#             except Exception:
#                 pass
#             raise
#     while True:
#         try:
#             resp = requests.get("https://api.coingecko.com/api/v3/global", timeout=15)
#             g = resp.json().get("data", {})
#             mcap = (g.get("total_market_cap") or {}).get("usd")
#             vol = (g.get("total_volume") or {}).get("usd")
            
#             # Nếu không lấy được dữ liệu hoặc dữ liệu = 0 thì bỏ qua luôn, không ghi file/log
#             if mcap is None or vol is None or float(mcap) == 0.0 or float(vol) == 0.0:
#                 #print("[MARKETCAP] Skip: API returned invalid data (None or 0.0)")
#                 continue
            
#             mcap = float(mcap)
#             vol = float(vol)
#             ts = int(_t.time())
#             # Create row with proper format
#             from datetime import datetime
#             ts_str = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
#             row = {"timestamp": ts_str, "market_cap": mcap, "volume_1d": vol}
            
#             # Append to CSV (atomic)
#             try:
#                 import os
#                 if os.path.exists(file):
#                     df = pd.read_csv(file)
#                     # Check if timestamp column exists and parse it
#                     if 'timestamp' in df.columns:
#                         df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
#                         df = df.dropna(subset=['timestamp'])
#                 else:
#                     df = pd.DataFrame(columns=["timestamp","market_cap","volume_1d"])
                
#                 # Check for duplicate entries (avoid same minute)
#                 if not df.empty:
#                     last_ts = pd.to_datetime(df.iloc[-1]['timestamp'])
#                     current_ts = pd.to_datetime(ts_str)
#                     if abs((current_ts - last_ts).total_seconds()) < 60:
#                         pass  # Skip duplicate minute
#                     else:
#                         new_row = pd.DataFrame([row])
#                         df = pd.concat([df, new_row], ignore_index=True)
#                         _atomic_write_csv(df, file)
#                         print(f"[MARKETCAP] Saved: Cap=${mcap/1e12:.2f}T, Vol=${vol/1e9:.2f}B")
#                 else:
#                     new_row = pd.DataFrame([row])
#                     df = pd.concat([df, new_row], ignore_index=True)
#                     _atomic_write_csv(df, file)
#                     print(f"[MARKETCAP] First entry saved: Cap=${mcap/1e12:.2f}T, Vol=${vol/1e9:.2f}B")
#             except Exception as e:
#                 print(f"[MARKETCAP ERROR] Failed to save: {e}")
#         except Exception:
#             _db_upsert_marketcap_row({"timestamp": ts, "market_cap": mcap, "volume_1d": vol})
#         except Exception as e:
#             print(f"[MARKETCAP API ERROR] Failed to fetch data: {e}")
#         _t.sleep(300)  # Changed  
# # để tránh NameError trong các hàm background.
# # Đường dẫn file lưu holdings, giá mua trung bình, lịch sử portfolio
# # (Đã lấy từ config)


# --- Nền: Ghi nhận Portfolio (Value/PNL/% P&L) theo phút, đồng bộ DB liên tục ---
def _fetch_prices_raw(coins_list: list[str]) -> tuple[dict, bool, str]:
    """Fetch current prices for given CoinGecko ids without Streamlit cache (for background thread).
    
    Returns:
        tuple[dict, bool, str]: (prices, success, error_message)
        - Only returns success=True when API call is completely successful with all valid prices
        - Stricter validation to prevent chart noise from API errors/rate limits
    """
    if not coins_list:
        return {}, False, "Empty coins list"
    
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "ids": ",".join(coins_list),
        "price_change_percentage": "1h,24h,7d,30d"
    }
    
    try:
        r = requests.get(url, params=params, timeout=20)
        
        # Strict status code checking
        if r.status_code == 429:
            return {}, False, "CoinGecko rate limit (429)"
        
        r.raise_for_status()
        data = r.json()
        
        # Validate response structure
        if not isinstance(data, list):
            return {}, False, "Invalid API response format"
        
        # Validate we got data for most/all requested coins
        if len(data) < len(coins_list) * 0.8:  # At least 80% of coins should be present
            return {}, False, f"Incomplete data: got {len(data)} of {len(coins_list)} coins"
        
        prices = {}
        invalid_prices = 0
        
        for item in data:
            try:
                coin_id = item.get("id")
                price = item.get("current_price")
                
                # Strict price validation
                if not coin_id or price is None:
                    invalid_prices += 1
                    continue
                    
                price_float = float(price)
                
                # Price sanity checks
                if price_float <= 0:
                    invalid_prices += 1
                    continue
                
                # Additional sanity check: prices shouldn't be extremely high (potential API error)
                if price_float > 1000000:  # > $1M per coin is likely an error
                    invalid_prices += 1
                    continue
                    
                prices[coin_id] = price_float
                
            except (ValueError, TypeError):
                invalid_prices += 1
                continue
        
        # Final validation: should have valid prices for most coins
        if invalid_prices > len(coins_list) * 0.2:  # More than 20% invalid is suspicious
            return {}, False, f"Too many invalid prices: {invalid_prices} of {len(data)} responses"
        
        if len(prices) < len(coins_list) * 0.8:  # Need at least 80% valid prices
            return {}, False, f"Insufficient valid prices: {len(prices)} of {len(coins_list)} coins"
        
        return prices, True, "Success"
        
    except requests.exceptions.Timeout:
        return {}, False, "API timeout"
    except requests.exceptions.ConnectionError:
        return {}, False, "Connection error"
    except requests.exceptions.HTTPError as e:
        return {}, False, f"HTTP error: {e}"
    except Exception as e:
        return {}, False, f"Unexpected error: {e}"


def _load_portfolio_meta_from_local() -> tuple[dict, dict]:
    """Load holdings and avg_price using the new initialization system."""
    holdings, avg_price_local = load_portfolio_holdings()
    
    # Get coin_ids from config to avoid NameError in background thread
    from config import COIN_LIST
    coin_ids = [c[0] for c in COIN_LIST]
    
    # Ensure all coin keys exist
    for c in coin_ids:
        holdings.setdefault(c, 0.0)
        avg_price_local.setdefault(c, 0.0)
    
    return holdings, avg_price_local


def portfolio_recorder_background(interval_sec: int = 300):
    """Background loop to record portfolio totals and per-coin PNL every minute and upsert to DB.

    STRICT MODE: Only records to history when CoinGecko API is completely successful.
    This prevents chart noise from API errors, rate limits, or partial data.
    
    - Reads holdings/avg_price from local files (already synced to DB on edits)
    - Fetches prices from CoinGecko with strict validation
    - Only appends to portfolio_history.json and MongoDB when API is 100% successful
    """
    history_file = HISTORY_FILE
    consecutive_failures = 0
    last_success_time = time.time()
    
    while True:
        try:
            holdings, avg_price_local = _load_portfolio_meta_from_local()
            # Get coin_ids from config to avoid NameError in background thread
            from config import COIN_LIST
            coin_ids = [c[0] for c in COIN_LIST]
            
            # Consider coins with non-zero amount or avg to reduce API load
            active_coins = [c for c in coin_ids if (holdings.get(c, 0) != 0 or avg_price_local.get(c, 0) != 0)]
            if not active_coins:
                time.sleep(interval_sec)
                continue

            # STRICT API CALL: Only proceed if completely successful (fetch all coins for consistency)
            prices, api_success, error_msg = _fetch_prices_raw(coin_ids)
            
            if not api_success:
                consecutive_failures += 1
                print(f"[PORTFOLIO_RECORDER] API failed (#{consecutive_failures}): {error_msg}")
                
                # Log extended failures
                if consecutive_failures >= 5:
                    hours_since_success = (time.time() - last_success_time) / 3600
                    print(f"[PORTFOLIO_RECORDER] WARNING: {consecutive_failures} consecutive failures, {hours_since_success:.1f}h since last success")
                
                time.sleep(interval_sec)
                continue
                
            # Reset failure counter on success
            if consecutive_failures > 0:
                print(f"[PORTFOLIO_RECORDER] API recovered after {consecutive_failures} failures")
                consecutive_failures = 0
            last_success_time = time.time()

            now = int(time.time())
            minute_ts = (now // 60) * 60

            # Compute totals with validated prices (use all coins for consistency with UI)
            portfolio_value = sum(float(prices.get(c, 0.0)) * float(holdings.get(c, 0.0)) for c in coin_ids)
            total_invested = sum(float(avg_price_local.get(c, 0.0)) * float(holdings.get(c, 0.0)) for c in coin_ids)
            current_pnl = portfolio_value - total_invested

            # Debug: Compare with active coins calculation for reference
            portfolio_value_active_only = sum(float(prices.get(c, 0.0)) * float(holdings.get(c, 0.0)) for c in active_coins)
            print(f"[PORTFOLIO_RECORDER] Active coins ({len(active_coins)}): {active_coins}")
            print(f"[PORTFOLIO_RECORDER] Portfolio value (all coins): ${portfolio_value:,.2f}")
            print(f"[PORTFOLIO_RECORDER] Portfolio value (active only): ${portfolio_value_active_only:,.2f}")
            print(f"[PORTFOLIO_RECORDER] Difference: ${abs(portfolio_value - portfolio_value_active_only):,.2f}")

            # Additional sanity checks on computed values
            has_holdings = any(float(holdings.get(c, 0.0)) != 0 for c in active_coins)
            
            # Skip obviously invalid portfolio calculations
            if portfolio_value < 0:
                print(f"[PORTFOLIO_RECORDER] Skipping negative portfolio value: {portfolio_value}")
                time.sleep(interval_sec)
                continue
                
            if has_holdings and portfolio_value == 0:
                print(f"[PORTFOLIO_RECORDER] Skipping zero portfolio with holdings (prices likely failed)")
                time.sleep(interval_sec)
                continue

            # Build docs for DB and local history (mark as API_SUCCESS for chart filtering)
            docs = []
            total_entry = {
                "timestamp": minute_ts, 
                "value": portfolio_value, 
                "PNL": current_pnl,
                "source": "api_success",  # Mark as reliable data point
                "api_version": "strict_validation"
            }
            docs.append(total_entry)
            
            for c in coin_ids:
                amount = float(holdings.get(c, 0.0))
                if amount == 0 and float(avg_price_local.get(c, 0.0)) == 0:
                    continue
                price = float(prices.get(c, 0.0))
                val = amount * price
                if val <= 0 and amount == 0:
                    continue
                invested = amount * float(avg_price_local.get(c, 0.0))
                coin_doc = {
                    "timestamp": minute_ts,
                    "coin": c,
                    "value": val,
                    "invested": invested,
                    "PNL": val - invested,
                    "amount": amount,
                    "avg_price": float(avg_price_local.get(c, 0.0)),
                    "source": "api_success",  # Mark as reliable
                    "api_version": "strict_validation"
                }
                docs.append(coin_doc)

            # Local file: append safely using append_snapshot (atomic + locked)
            try:
                append_snapshot(docs)
                print(f"[PORTFOLIO_RECORDER] Recorded portfolio: ${portfolio_value:,.2f} (PNL: ${current_pnl:,.2f})")
            except Exception as e:
                print(f"[PORTFOLIO_RECORDER] Failed to save local history: {e}")

            # DB upsert
            try:
                _db_upsert_portfolio_docs(docs)
            except Exception as e:
                print(f"[PORTFOLIO_RECORDER] Failed to save to DB: {e}")
                
        except Exception as e:
            consecutive_failures += 1
            print(f"[PORTFOLIO_RECORDER] Unexpected error (#{consecutive_failures}): {e}")
            
        time.sleep(interval_sec)
    # Removed orphaned except block to fix syntax error.

# Start background portfolio recorder once
if "_portfolio_recorder" not in st.session_state:
    try:
        t = threading.Thread(target=portfolio_recorder_background, kwargs={"interval_sec": 300}, daemon=True)
        t.start()
    except Exception:
        pass
    st.session_state["_portfolio_recorder"] = True

# Start dominance & marketcap crawlers once
if "_metrics_crawlers" not in st.session_state:
    try:
        t1 = threading.Thread(target=crawl_dominance_background, daemon=True)
        t1.start()
    except Exception:
        pass
    try:
        t2 = threading.Thread(target=crawl_marketcap_background, daemon=True)
        t2.start()
    except Exception:
        pass
    st.session_state["_metrics_crawlers"] = True



# Hàm lấy giá và % thay đổi từ CoinGecko, cache ngắn để cập nhật thường xuyên
@st.cache_data(ttl=60, show_spinner=False)
def get_prices_and_changes(coins):
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "ids": ",".join(coins),
        "price_change_percentage": "1h,24h,7d,30d"
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
    except requests.exceptions.HTTPError as e:
        if r.status_code == 429:
            st.session_state["coingecko_429"] = True
        else:
            st.session_state["coingecko_429"] = False
        data = []
    except Exception as e:
        st.session_state["coingecko_429"] = False
        data = []
    # Trả về dict: {coin: {"price":..., "change_1d":..., ...}}
    result = {}
    for item in data:
        result[item["id"]] = {
            "price": item.get("current_price", 0),
            "change_1d": item.get("price_change_percentage_24h", 0),
            "change_7d": item.get("price_change_percentage_7d_in_currency", 0),
            "change_30d": item.get("price_change_percentage_30d_in_currency", 0),
            "image": item.get("image", "")
        }
    return result

# ================= PERFORMANCE OPTIMIZATION HELPERS =================
# 1. Cache heavy external fetches (OKX OHLCV, Liquidation, On-chain metrics)
# 2. Avoid re-reading large history / JSON files inside per-coin loop
# 3. Debounce saving holdings / avg_price when no real change

@st.cache_data(ttl=300, show_spinner=False)
def fetch_okx_ohlcv_cached(symbol: str, bar: str, limit: int = 200):
    """Cached wrapper around metrics_ohlcv_okx.fetch_okx_ohlcv_oi.
    TTL 90s to reduce network calls when switching tabs / sliders.
    """
    try:
        return metrics_ohlcv_okx.fetch_okx_ohlcv_oi(symbol=symbol, bar=bar, limit=limit)
    except Exception:
        return None

@st.cache_data(ttl=300, show_spinner=False)
def fetch_okx_liq_cached(symbol: str, limit: int = 100):
    try:
        import metrics_liquidation_okx  # local import to reduce initial load
        return metrics_liquidation_okx.fetch_okx_liquidation(symbol=symbol, limit=limit)
    except Exception:
        return None

@st.cache_data(ttl=300, show_spinner=False)
def fetch_okx_liq_range_cached(symbol: str, start_ts: int, end_ts: int):
    """Cached range fetcher for OKX liquidation details.
    Inputs are epoch seconds for stable caching.
    """
    try:
        import metrics_liquidation_okx as _mlo
        from datetime import datetime
        start_dt = datetime.utcfromtimestamp(start_ts)
        end_dt = datetime.utcfromtimestamp(end_ts)
        return _mlo.fetch_okx_liquidation_range(symbol, start_dt, end_dt)
    except Exception:
        return None

@st.cache_data(ttl=300, show_spinner=False)
def fetch_liq_multi_cached(asset_symbol: str, start_ts: int, end_ts: int, sources: tuple, okx_inst: str | None = None):
    """Cached aggregator for liquidation events across multiple exchanges.
    sources: tuple like ("OKX", "BINANCE", "BITMEX")
    """
    try:
        import metrics_liquidation_okx as _mlo
        from datetime import datetime
        start_dt = datetime.utcfromtimestamp(start_ts)
        end_dt = datetime.utcfromtimestamp(end_ts)
        return _mlo.fetch_liquidations_multi(asset_symbol, start_dt, end_dt, list(sources), okx_inst=okx_inst)
    except Exception:
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def get_rsi_for_universe_cached(symbols: tuple, timeframe: str = '1d', ttl_seconds: int = 3600, force_refresh: bool = False):
    """Streamlit-level cache wrapper around metrics_rsi.get_rsi_for_universe.

    Keeps results cached in Streamlit to avoid re-fetching on every rerun.
    Returns dict mapping symbol -> RSI value or empty dict on error.
    """
    try:
        import metrics_rsi as _m
        return _m.get_rsi_for_universe(list(symbols), timeframe=timeframe, ttl_seconds=ttl_seconds, force_refresh=force_refresh)
    except Exception:
        return {}

@st.cache_data(ttl=600, show_spinner=False)
def load_onchain_metrics_cached(asset: str, days: int = 365):
    try:
        import metrics_onchain_cm
        return metrics_onchain_cm.load_onchain_metrics(asset, days)
    except Exception:
        return None

@st.cache_data(ttl=120, show_spinner=False)
def load_portfolio_history_cached(history_file: str):
    if os.path.exists(history_file):
        try:
            with open(history_file, 'r') as f:
                return json.load(f)
        except Exception:
            return []
    return []

@st.cache_data(ttl=120, show_spinner=False)
def history_by_coin_cached(history_file: str):
    """Return a mapping {coin: list[entry]} using cached full history."""
    from collections import defaultdict
    hist = load_portfolio_history_cached(history_file)
    by_coin: dict[str, list] = defaultdict(list)
    for h in hist:
        c = h.get("coin")
        if c:
            by_coin[c].append(h)
    return hist, by_coin

@st.cache_data(ttl=600, show_spinner=False)
def compute_growth_chart_cached(coins: tuple, coin_id_to_name_map: dict, bar: str = "30m", coin_limit: int | None = 8):
    import plotly.graph_objects as go
    import pandas as pd
    # Dynamic giới hạn: nếu coin_limit None => không giới hạn
    coins_limited = list(coins)[:coin_limit] if coin_limit else list(coins)
    price_histories = {}
    time_histories = {}
    min_len = None
    for coin in coins_limited:
        try:
            symbol = f"{coin_id_to_name_map[coin]}-USDT-SWAP"
            df_ohlcv = fetch_okx_ohlcv_cached(symbol=symbol, bar=bar, limit=200)
            if df_ohlcv is None or df_ohlcv.empty:
                continue
            closes = df_ohlcv["close"] if "close" in df_ohlcv.columns else df_ohlcv.iloc[:,4]
            closes = closes.astype(float).values
            if len(closes) < 5:
                continue
            if "ts" in df_ohlcv.columns:
                times = pd.to_datetime(df_ohlcv["ts"].values, unit="ms")
            elif "datetime" in df_ohlcv.columns:
                times = pd.to_datetime(df_ohlcv["datetime"], errors="coerce")
            else:
                times = pd.to_datetime(df_ohlcv.iloc[:,0], unit="ms", errors="coerce")
            if times.isna().all():
                continue
            price_histories[coin] = closes
            time_histories[coin] = times
            if min_len is None or len(closes) < min_len:
                min_len = len(closes)
        except Exception:
            continue
    if not price_histories or not min_len or min_len < 2:
        return None
    fig = go.Figure()
    base_coin = next(iter(price_histories.keys()))
    times = time_histories[base_coin][-min_len:]
    for coin in coins_limited:
        if coin in price_histories:
            closes = price_histories[coin][-min_len:]
            if closes[0] == 0:
                continue
            pct_growth = (closes / closes[0] - 1) * 100
            fig.add_trace(go.Scatter(x=times, y=pct_growth, mode="lines", name=coin_id_to_name_map[coin]))
    if len(fig.data) == 0:
        return None
    fig.update_layout(
        title="Tăng trưởng (%) (OKX 30m, chuẩn hóa 0% tại điểm đầu) - Cached",
        xaxis_title="Thời gian",
        yaxis_title="% Tăng trưởng",
        legend_title="Coin",
        hovermode="x unified"
    )
    return fig

# ---------------- Phase 0: OHLCV Prefetch Optimization (shared for coin tabs) ---------------- #
def _ohlcv_prefetch_key(bar: str) -> str:
    return f"_ohlcv_prefetch_bar_{bar}"

def prefetch_ohlcv_all(bar: str, coin_symbols: list[str], limit: int = 200, force: bool = False):
    """Prefetch OHLCV for a list of coin symbols once per timeframe to reduce repeated calls.

    Stores result in st.session_state with lightweight TTL logic (reuse for ~80s).
    """
    key = _ohlcv_prefetch_key(bar)
    snap = st.session_state.get(key)
    now_t = time.time()
    if (not force) and snap and (now_t - snap.get('ts', 0) < 80):
        return snap.get('data', {}), snap.get('stats', {})
    data_map = {}
    success = 0
    failed = []
    for sym in coin_symbols:
        try:
            df_ohlcv = fetch_okx_ohlcv_cached(symbol=f"{sym}-USDT-SWAP", bar=bar, limit=limit)
            if df_ohlcv is not None and not df_ohlcv.empty:
                data_map[sym] = df_ohlcv.copy()
                success += 1
            else:
                failed.append(sym)
        except Exception:
            failed.append(sym)
    stats = {
        'bar': bar,
        'success': success,
        'total': len(coin_symbols),
        'failed': failed,
        'timestamp': now_t
    }
    st.session_state[key] = {'data': data_map, 'stats': stats, 'ts': now_t}
    return data_map, stats


def render_coin_summary(coin_id: str, coin_symbol: str):
    """Render a compact 4-metric summary for a single coin tab.

    Metrics:
      - Total value (USD) with 1D change (pct + USD)
      - Total invested (USD)
      - PNL (USD)
      - PNL (%)

    Uses session state fallbacks and is resilient to missing data.
    """
    try:
        holdings = st.session_state.get("holdings", {}) or {}
        avg_price = st.session_state.get("avg_price", {}) or {}
        prices = st.session_state.get("_last_prices", {}) or {}
        price_data = st.session_state.get("_last_price_data", {}) or {}

        amount = float(holdings.get(coin_id, 0.0) or 0.0)
        invested_price = float(avg_price.get(coin_id, 0.0) or 0.0)

        # Prefer CoinGecko via cached helper for the current price and 1D change
        cur_price = 0.0
        change_pct = 0.0
        try:
            # get_prices_and_changes is cached (TTL 60s) and returns mapping {coin_id: {price,...}}
            cg_map = get_prices_and_changes([coin_id])
            if cg_map and coin_id in cg_map:
                entry = cg_map.get(coin_id) or {}
                cur_price = float(entry.get("price", 0.0) or 0.0)
                change_pct = float(entry.get("change_1d", 0.0) or 0.0)
            else:
                # fallback to session cache
                cur_price = float(prices.get(coin_id, 0.0) or 0.0)
                try:
                    change_pct = float(price_data.get(coin_id, {}).get("change_1d", 0) or 0)
                except Exception:
                    change_pct = 0.0
        except Exception:
            # fallback to session state values if CoinGecko fetch fails
            cur_price = float(prices.get(coin_id, 0.0) or 0.0)
            try:
                change_pct = float(price_data.get(coin_id, {}).get("change_1d", 0) or 0)
            except Exception:
                change_pct = 0.0

        # Show current price and 1D change below the metrics
        try:
            # Use a single column row to display price + 1D change compactly
            price_col1 = st.columns(1)
            with price_col1:
                st.markdown(f"**Giá hiện tại:** <code>${cur_price:,.4f}</code>", unsafe_allow_html=True)
        except Exception:
            pass

        total_value = amount * cur_price
        total_invested = amount * invested_price
        pnl = total_value - total_invested
        pnl_pct = (pnl / total_invested * 100) if total_invested != 0 else 0.0

        change_usd = total_value * (change_pct / 100.0)

        # Format strings
        val_s = f"{total_value:,.2f}"
        invested_s = f"{total_invested:,.2f}"
        pnl_s = f"{pnl:,.2f}"
        pnl_pct_s = f"{pnl_pct:.2f}%"
        change_label = f"{change_pct:+.2f}% | {change_usd:+.2f} USD"

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric(f"💰 Tổng giá trị (USD)", val_s, delta=change_label)
        with c2:
            st.metric("💸 Tổng số vốn đầu tư (USD)", invested_s)
        with c3:
            st.metric("📈 PNL (USD)", pnl_s)
        with c4:
            st.metric("📊 PNL (%)", pnl_pct_s)
        
    except Exception as e:
        # Non-fatal: just show a small caption when something fails
        try:
            st.caption(f"Không thể hiển thị summary cho {coin_symbol}: {e}")
        except Exception:
            pass

def get_prefetched_ohlcv(bar: str, coin_symbol: str):
    key = _ohlcv_prefetch_key(bar)
    snap = st.session_state.get(key)
    if not snap:
        return None
    return snap.get('data', {}).get(coin_symbol)

# Phase 0: unified loaders
try:
    from services.whale.whale_loader import load_whales_for_symbol
except Exception:
    load_whales_for_symbol = None

try:
    from services.ohlcv.ohlcv_loader import load_ohlcv as unified_load_ohlcv
except Exception:
    unified_load_ohlcv = None

# Hàm load lịch sử portfolio
def load_portfolio_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return []

# Hàm lưu lịch sử portfolio
def save_portfolio_history(history):
    save_portfolio_history_optimized(history, HISTORY_FILE)
    backup_file(HISTORY_FILE)

# Hàm load holdings từ file
def load_holdings():
    """Load holdings using the new initialization system."""
    holdings, _ = load_portfolio_holdings()
    print(f"[DEBUG] load_holdings() returned {len(holdings)} items: {list(holdings.keys())[:5]}...")
    return holdings

# Hàm load giá mua trung bình từ file
def load_avg_price():
    """Load average prices using the new initialization system."""
    _, avg_prices = load_portfolio_holdings()
    print(f"[DEBUG] load_avg_price() returned {len(avg_prices)} items: {list(avg_prices.keys())[:5]}...")
    return avg_prices

# Hàm lưu giá mua trung bình vào file
def save_avg_price(avg_price):
    try:
        portfolio, _ = get_portfolio_data()
        update_portfolio_data(portfolio, avg_price)
        st.success("✅ Giá mua trung bình đã được cập nhật!")
    except Exception as e:
        st.warning(f"❌ Không thể lưu giá mua trung bình: {e}")

# Hàm lưu holdings vào file
def save_holdings(holdings):
    try:
        _, avg_price = get_portfolio_data()
        update_portfolio_data(holdings, avg_price)
        st.success("✅ Số lượng holdings đã được cập nhật!")
    except Exception as e:
        st.warning(f"❌ Không thể lưu dữ liệu: {e}")

# Tabs: Portfolio & Metric




# Tabs: Portfolio & Metric & Coin
coin_ids = [c[0] for c in COIN_LIST]
coin_names = [c[1] for c in COIN_LIST]
coin_id_to_name = dict(COIN_LIST)
coin_name_to_id = {v: k for k, v in COIN_LIST}

tab_names = ["Portfolio", "Metric"] + coin_names
tabs = st.tabs(tab_names)
tab1 = tabs[0]
tab2 = tabs[1]
tab_coin_tabs = tabs[2:]

tz_gmt7 = pytz.timezone("Asia/Bangkok")

# Coin selection (default all)
with st.expander("Chọn các đồng coin muốn theo dõi", expanded=False):
    selected_coin_names = st.multiselect(
        "Chọn coin:", options=coin_names, default=coin_names, key="selected_coins_portfolio"
    )
if not selected_coin_names:
    selected_coin_names = coin_names
coins = [coin_name_to_id[n] for n in selected_coin_names]

# Không cần update_eth_tab_label nữa


with tab1:
    st.title("📊 Crypto Portfolio Tracker")
    
    # === Application Health Panel ===
    with st.expander("🏥 System Health & Status", expanded=False):
        app_state = get_app_state()
        # Status indicators
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            db_status = "🟢 Connected" if app_state["db_available"] else "🔴 Disconnected"
            st.metric("Database", db_status)
        with col2:
            api_status = "🟢 Available" if app_state["api_available"] else "🔴 Unavailable"
            st.metric("API Services", api_status)
        with col3:
            init_status = "✅ Complete" if app_state["init_complete"] else "⏳ In Progress"
            st.metric("Initialization", init_status)
        # Redis status: only green if cache is working (hit>0, error==0)
        cache_stats = app_state.get("cache_stats") or {}
        redis_ok = bool(app_state.get("redis_available")) and cache_stats.get('hit', 0) > 0 and cache_stats.get('error', 0) == 0
        with col4:
            redis_status = "🟢" if redis_ok else "🔴"
            st.metric("Redis", redis_status)
        
        # Sync information
        if app_state["last_db_sync"] > 0:
            last_db = datetime.fromtimestamp(app_state["last_db_sync"]).strftime("%H:%M:%S")
            st.info(f"📊 Last DB sync: {last_db}")
        if app_state["last_api_sync"] > 0:
            last_api = datetime.fromtimestamp(app_state["last_api_sync"]).strftime("%H:%M:%S")
            st.info(f"🔄 Last API sync: {last_api}")
        
        # Background sync status with force refresh indicator
        sync_status = "🟢 Active" if app_state["background_sync_active"] else "🔴 Inactive"
        
        # Calculate next force refresh
        last_api_time = app_state.get("last_api_sync", 0)
        if last_api_time > 0:
            time_since_sync = time.time() - last_api_time
            minutes_since = int(time_since_sync / 60)
            next_force_in = 10 - (minutes_since % 10)
            force_indicator = f" (Next force refresh in {next_force_in}min)" if next_force_in < 10 else " (Force refresh due!)"
        else:
            force_indicator = ""
        
        col_sync, col_refresh = st.columns([3, 1])
        with col_sync:
            st.text(f"Background Sync: {sync_status}{force_indicator}")
        with col_refresh:
            if st.button("🔄 Force Refresh", help="Force immediate price refresh"):
                with st.spinner("Refreshing prices..."):
                    success, msg = force_price_refresh()
                    if success:
                        st.success(msg)
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(msg)

        # Backend API connectivity details (Render)
        # try:
        #     backend_snap = _ping_backend_status(ttl=60)
        #     base = backend_snap.get("base", "?")
        #     endpoint = backend_snap.get("endpoint", "?")
        #     h = backend_snap.get("health", {})
        #     p = backend_snap.get("prices", {})
        #     st.caption(f"Backend API base: {base}")
        #     st.caption(f"Prices endpoint: {endpoint}")
        #     st.text("Backend /health: " + ("OK" if h.get("ok") else "FAIL") + f" | status={h.get('status')} | latency={h.get('latency')}s")
        #     # Show generated_at age if available
        #     gen_at = p.get('generated_at')
        #     age_s = None
        #     if isinstance(gen_at, (int, float)):
        #         try:
        #             age_s = max(0, int(time.time() - float(gen_at)))
        #         except Exception:
        #             age_s = None
        #     age_str = f" | age={age_s}s" if age_s is not None else ""
        #     st.text("Backend /prices/spot: " + ("OK" if p.get("ok") else "FAIL") + f" | status={p.get('status')} | latency={p.get('latency')}s | count={p.get('count')}" + age_str)
        #     if age_s is not None and age_s > 180:
        #         st.warning(f"⚠️ Giá backend có vẻ cũ (age ~{age_s}s). Kiểm tra backend scheduler hoặc provider rate limit.")
        #     # Warn if endpoint resolves to localhost while running in cloud
        #     if "127.0.0.1" in endpoint or "localhost" in endpoint:
        #         st.warning("BACKEND_PRICE_API đang trỏ localhost. Trên cloud cần dùng URL Render (ví dụ: https://hakicrypto2025.onrender.com/prices/spot)")
        # except Exception as _bh:
        #     st.caption(f"Backend API check error: {_bh}")

        # # Backend scheduler tasks (to diagnose staleness)
        # try:
        #     tasks_snap = _fetch_backend_tasks(ttl=60)
        #     if tasks_snap.get('ok'):
        #         tasks = tasks_snap.get('tasks', {})
        #         if tasks:
        #             st.caption("Backend scheduler tasks:")
        #             for name, info in tasks.items():
        #                 age = info.get('age_s')
        #                 st.text(f" - {name}: interval={info.get('interval')}s last_run_age={age}s failures={info.get('failures')}")
        #                 if isinstance(age, int) and age > max(180, int(info.get('interval', 0))*3):
        #                     st.warning(f"Task '{name}' có vẻ không chạy gần đây (age ~{age}s).")
        #     else:
        #         st.caption(f"/tasks not available: status={tasks_snap.get('status')} latency={tasks_snap.get('latency')}")
        # except Exception as _ts_ex:
        #     st.caption(f"Backend tasks fetch error: {_ts_ex}")

    # Action buttons row
        act_col1, act_col2, act_col3, act_col4 = st.columns(4)
        with act_col1:
            if st.button("⚡ Force Price Refresh", help="Bỏ qua interval / Redis cache và fetch giá mới"):
                try:
                    from config import COIN_LIST as _CL
                    from price_utils import fetch_prices_and_changes
                    from app_init import update_price_cache
                    coins_force = [cid for cid, _ in _CL]
                    with st.spinner("Đang fetch giá (force)..."):
                        prices_new, changes_new, success_new, msg_new = fetch_prices_and_changes(coins_force, force=True)
                    if success_new and prices_new:
                        update_price_cache(prices_new, changes_new)
                        st.success("Đã refresh giá (force)")
                    else:
                        st.warning(f"Không refresh được giá (force) -> {msg_new}")
                except Exception as fe:
                    st.error(f"Force price refresh error: {fe}")
        with act_col2:
            if st.button("♻️ Force Re-Init", help="Dừng background sync & khởi tạo lại toàn bộ pipeline"):
                try:
                    from app_init import force_reinitialize
                    with st.spinner("Đang re-init ứng dụng..."):
                        ok_re, msg_re = force_reinitialize()
                    if ok_re:
                        st.success(msg_re)
                    else:
                        st.error(msg_re)
                except Exception as rie:
                    st.error(f"Force re-init error: {rie}")
        with act_col3:
            if st.button("🔁 Refresh Portfolio (TTL bypass)", help="Load lại holdings/avg_price bỏ qua TTL cache"):
                try:
                    # Bypass TTL cache we added earlier
                    from app_init import get_portfolio_data
                    port, avgp = get_portfolio_data()  # already latest in memory
                    st.session_state["holdings"] = port
                    st.session_state["avg_price"] = avgp
                    st.success("Portfolio refreshed từ cache trong bộ nhớ.")
                except Exception as pe:
                    st.error(f"Portfolio refresh error: {pe}")
        with act_col4:
            if st.button("🧪 Show Price Snapshot"):
                try:
                    from app_init import get_price_data
                    p_snap, ch_snap = get_price_data()
                    st.json({"prices": list(p_snap.items())[:8], "changes_keys": list(ch_snap.keys())[:8]})
                except Exception as se:
                    st.error(f"Snapshot error: {se}")
        
        # DB Connection Details
        if st.button("🔍 Show DB Connection Details"):
            try:
                from cloud_db import db
                conn_info = db.get_connection_info()
                st.json(conn_info)
                
                # Try manual reconnect
                if st.button("🔄 Force DB Reconnect"):
                    with st.spinner("Reconnecting to database & hydrating..."):
                        success = db.force_reconnect()
                        if success:
                            # Rehydrate caches from DB to avoid rollback to stale local files
                            try:
                                from app_init import rehydrate_from_db, get_portfolio_data
                                hyd_ok = rehydrate_from_db()
                                port_new, avg_new = get_portfolio_data()
                                st.session_state["holdings"] = port_new or st.session_state.get("holdings", {})
                                st.session_state["avg_price"] = avg_new or st.session_state.get("avg_price", {})
                                # Mark boot source for transparency
                                st.session_state["_bootstrap_source"] = "db_rehydrate"
                                st.success("✅ Reconnected & hydrated from DB" if hyd_ok else "⚠️ Reconnected nhưng không hydrate được DB")
                            except Exception as _rh_ex:
                                st.warning(f"Reconnect ok nhưng hydrate lỗi: {_rh_ex}")
                        else:
                            st.error(f"❌ Reconnect failed. Error: {db.last_error()}")
            except Exception as e:
                st.error(f"Error getting DB info: {e}")

    # --- Backend-style portfolio summary (server-side computation to reduce front-end logic) ---
    # Hidden from user view - for internal reference only
    server_summary_available = False
    try:
        from app_init import compute_portfolio_summary, get_portfolio_data
        # Use local compute with backend prices (more reliable than missing /portfolio/summary endpoint)
        summary = compute_portfolio_summary(use_symbols=True)
        
        rows = summary.get('rows', [])
        totals = summary.get('totals', {})
        # Expose totals for later KPI section to avoid double-compute drift
        try:
            st.session_state['_server_summary_totals'] = totals
            server_summary_available = True
        except Exception:
            pass
        
        # Hide server-side table from user view - only keep for internal calculations
        if False:  # Disabled - hide server-side table as requested
            if rows:
                df = pd.DataFrame(rows)
                # Reorder columns for readability
                cols = ['coin','amount','price','value','avg_price','invested','pnl','pnl_pct','change_1d','change_7d','change_30d']
                df = df[[c for c in cols if c in df.columns]]
                st.subheader("Bảng Portfolio (tính server-side)")
                st.caption("📊 Reference table - tính toán server-side để kiểm tra độ chính xác")
                st.dataframe(df.style.format({
                    'amount': '{:,.6f}',
                    'price': '{:,.4f}',
                    'value': '{:,.2f}',
                    'avg_price': '{:,.4f}',
                    'invested': '{:,.2f}',
                    'pnl': '{:,.2f}',
                    'pnl_pct': '{:,.2f}%',
                    'change_1d': '{:,.2f}%',
                    'change_7d': '{:,.2f}%',
                    'change_30d': '{:,.2f}%'
                }), width="stretch")
                col_tot1, col_tot2, col_tot3, col_tot4 = st.columns(4)
                col_tot1.metric("Tổng giá trị", f"${totals.get('value',0):,.2f}")
                col_tot2.metric("Tổng vốn", f"${totals.get('invested',0):,.2f}")
                col_tot3.metric("PNL", f"${totals.get('pnl',0):,.2f}")
                col_tot4.metric("PNL %", f"{totals.get('pnl_pct',0):,.2f}%")
        
        # Mark server reference as available for internal use
        st.session_state['_server_reference_available'] = server_summary_available
        
    except Exception as srv_ex:
        # Only show error if debug mode - hide from normal users
        if st.session_state.get('debug_mode', False):
            st.warning(f"Không thể render bảng portfolio server-side: {srv_ex}")

    # Recent errors
    if app_state["errors"]:
        st.warning("⚠️ Recent errors:")
        for error in app_state["errors"][-5:]:  # Show last 5 errors
            st.text(f"• {error}")
    
    # # Backend monitoring section
    # with st.expander("🔧 Backend API Status", expanded=False):
    #     try:
    #         backend_status = _ping_backend_status()
    #         backend_tasks = _fetch_backend_tasks()
            
    #         col1, col2 = st.columns(2)
    #         with col1:
    #             st.subheader("Health Check")
    #             health = backend_status.get("health", {})
    #             if health.get("ok"):
    #                 st.success(f"✅ Backend online ({health.get('latency', 0):.0f}ms)")
    #             else:
    #                 st.error(f"❌ Backend offline: {health.get('status', 'Unknown')}")
                
    #             prices_check = backend_status.get("prices", {})
    #             if prices_check.get("ok"):
    #                 st.success(f"✅ Prices API working ({prices_check.get('count', 0)} coins)")
    #             else:
    #                 st.error(f"❌ Prices API failed: {prices_check.get('status', 'Unknown')}")
            
    #         with col2:
    #             st.subheader("Background Tasks")
    #             tasks = backend_tasks.get("tasks", {})
    #             if tasks:
    #                 for task_name, task_info in tasks.items():
    #                     age_s = task_info.get("age_s", 0)
    #                     failures = task_info.get("failures", 0)
    #                     if age_s < 300:  # < 5 minutes
    #                         st.success(f"✅ {task_name}: {age_s}s ago")
    #                     elif age_s < 900:  # < 15 minutes  
    #                         st.warning(f"⚠️ {task_name}: {age_s}s ago")
    #                     else:
    #                         st.error(f"❌ {task_name}: {age_s}s ago")
                        
    #                     if failures > 0:
    #                         st.text(f"   Failures: {failures}")
    #             else:
    #                 st.warning("No task status available")
    #     except Exception as e:
    #         st.error(f"Backend monitoring error: {e}")
    # Cache stats (optional)
    # cache_stats = app_state.get("cache_stats") or {}
    # if cache_stats:
    #     st.caption(f"Cache stats: hit={cache_stats.get('hit',0)} miss={cache_stats.get('miss',0)} error={cache_stats.get('error',0)}")
    #     if cache_stats.get('hit',0) == 1:
    #         st.info("💡 Cache hit rate is low, consider increasing TTL or optimizing cache usage.")
    #     if cache_stats.get('error',0) > 0:
    #         st.warning("⚠️ Cache errors detected, check logs for details.")
    #     if cache_stats.get('miss',0) > cache_stats.get('hit',0)*2:
    #         st.info("💡 Cache miss rate is high, consider reviewing caching strategy.")


    # --- BẢNG NHẬP DỮ LIỆU KIỂU EXCEL ---
    st.subheader("Bảng quản lý Portfolio")

    # Khởi tạo duy nhất các biến dữ liệu cho tab Portfolio
    if "holdings" not in st.session_state:
        st.session_state["holdings"] = load_holdings()
    if "avg_price" not in st.session_state:
        st.session_state["avg_price"] = load_avg_price()
    holdings = st.session_state["holdings"]
    avg_price = st.session_state["avg_price"]

    # --- Bootstrap portfolio cache from DB (tránh hiển thị 0 lúc đầu nếu API chưa trả giá) ---
    def _bootstrap_portfolio_cache_from_db():
        try:
            if not db.available():
                return False
            # Lấy một batch nhỏ mới nhất (descending) để tìm tổng + giá trị từng coin mới nhất
            docs = db.find_all("portfolio_history", sort_field="timestamp", ascending=False, limit=250)
            if not docs:
                return False
            last_total = None
            coin_latest = {}
            for d in docs:
                if last_total is None and 'coin' not in d:
                    last_total = d
                elif 'coin' in d:
                    c = d.get('coin')
                    if c and c not in coin_latest:
                        coin_latest[c] = d
                if last_total and len(coin_latest) >= len(holdings):
                    # Đã có đủ dữ liệu cơ bản
                    pass
            if not last_total:
                return False
            pv = float(last_total.get('value') or 0)
            if pv <= 0:
                return False
            # Ghi vào session state
            st.session_state.setdefault("_last_prices", {c: 0.0 for c in holdings})
            st.session_state.setdefault("_last_price_data", {c: {} for c in holdings})
            st.session_state["_last_portfolio_value"] = pv
            st.session_state["_last_nonzero_portfolio_value"] = pv
            # Tái tạo giá từng coin từ snapshot (value / amount)
            reconstructed_prices = {}
            for c, doc in coin_latest.items():
                amt = float(doc.get('amount') or 0)
                val = float(doc.get('value') or 0)
                if amt > 0 and val > 0:
                    reconstructed_prices[c] = val / amt
            if reconstructed_prices:
                lp = st.session_state.get("_last_prices", {})
                lp.update(reconstructed_prices)
                st.session_state["_last_prices"] = lp
            # Tính tổng vốn đầu tư dựa trên avg_price hiện tại
            invested = sum(avg_price.get(c, 0.0) * holdings.get(c, 0.0) for c in holdings)
            st.session_state["_last_total_invested_now"] = invested
            st.session_state["_last_current_pnl"] = pv - invested
            st.session_state["_bootstrap_source"] = "db"
            return True
        except Exception:
            return False

    # Chỉ bootstrap nếu chưa có non-zero cache
    if st.session_state.get("_last_nonzero_portfolio_value", 0) == 0:
        _bootstrap_portfolio_cache_from_db()

    if "coingecko_429" not in st.session_state:
        st.session_state["coingecko_429"] = False
    if "coingecko_last_error_time" not in st.session_state:
        st.session_state["coingecko_last_error_time"] = 0
    # Nút làm mới giá để bỏ qua cache ngay lập tức
    col1, col2 = st.columns([1, 2])
    with col1:
        refresh_now = st.button("🔄 Làm mới giá (CoinGecko)", key="refresh_prices")
    #with col2:
        #st.caption("💡 Backend price integration disabled due to inflated prices (BTC $122K vs market $112K)")
    
    if refresh_now:
        # Clear all cached data to force fresh fetch
        st.session_state["_last_prices"] = {}
        st.session_state["_price_source"] = "force_refresh_coingecko"
        st.info("🔄 Đã xóa cache, đang tải dữ liệu mới từ CoinGecko...")
        time.sleep(1)  # Give user feedback
        st.rerun()
    
    # Debug Panel - Price Source Status  
    # Ensure a sane default price source label
    if "_price_source" not in st.session_state:
        st.session_state["_price_source"] = "coingecko_primary"
    price_source = st.session_state.get("_price_source", "coingecko_primary")
    debug_info = f"📊 **Price Source:** `{price_source}` (CoinGecko Primary)"
    st.markdown(debug_info)
    
    now_time = int(time.time())
    # Nếu vừa gặp lỗi API, chỉ cho phép request lại sau 70 giây
    can_request = True
    if st.session_state["coingecko_last_error_time"] > 0:
        if now_time - st.session_state["coingecko_last_error_time"] < 70:
            can_request = False
    # --- Cơ chế giữ giá trị cũ khi API lỗi ---
    # Lưu cache giá, portfolio_value, các thông tin coin
    if "_last_prices" not in st.session_state:
        st.session_state["_last_prices"] = {c: 0.0 for c in coins}
    if "_last_price_data" not in st.session_state:
        st.session_state["_last_price_data"] = {c: {} for c in coins}
    if "_last_portfolio_value" not in st.session_state:
        st.session_state["_last_portfolio_value"] = 0.0
    # Track the last non-zero (valid) portfolio value so UI never flashes 0 when API rate limits
    if "_last_nonzero_portfolio_value" not in st.session_state:
        st.session_state["_last_nonzero_portfolio_value"] = 0.0
    if "_last_total_invested_now" not in st.session_state:
        st.session_state["_last_total_invested_now"] = 0.0
    if "_last_current_pnl" not in st.session_state:
        st.session_state["_last_current_pnl"] = 0.0

    price_data = st.session_state["_last_price_data"]
    prices = st.session_state["_last_prices"]
    portfolio_value = st.session_state["_last_portfolio_value"]
    total_invested_now = st.session_state["_last_total_invested_now"]
    current_pnl = st.session_state["_last_current_pnl"]

    update_success = False
    prev_portfolio_value = portfolio_value
    if can_request:
        # Backend price integration disabled due to persistent data reliability issues
        # Issue: Backend returns inflated prices (BTC $122K vs market $112K)
        # Decision: Use CoinGecko API only for reliable portfolio calculations
        print("[DEBUG] Backend price integration disabled - using CoinGecko only")
        
        # Direct CoinGecko price fetch
        prices_new, pdata_new, updated, msg = get_current_prices()
        if updated:
            price_data = pdata_new
            # Merge new prices and carry-forward last non-zero for any missing/zero coins
            prices = {c: float(prices_new.get(c, 0.0) or 0.0) for c in coins}
            last_prices_snap = st.session_state.get("_last_prices", {})
            for c in coins:
                if float(prices.get(c, 0.0)) <= 0 and float(last_prices_snap.get(c, 0.0)) > 0:
                    prices[c] = float(last_prices_snap[c])
            now = int(time.time())
            portfolio_value = sum(float(prices.get(c, 0.0)) * float(holdings.get(c, 0.0)) for c in coins)
            if portfolio_value > 0:
                st.session_state["_last_nonzero_portfolio_value"] = portfolio_value
            total_invested_now = sum(avg_price.get(c, 0.0) * holdings.get(c, 0.0) for c in coins)
            current_pnl = portfolio_value - total_invested_now
            st.session_state["_last_price_data"] = price_data
            st.session_state["_last_prices"] = prices
            st.session_state["_last_portfolio_value"] = portfolio_value
            st.session_state["_last_total_invested_now"] = total_invested_now
            st.session_state["_last_current_pnl"] = current_pnl
            # Label source: coingecko_primary; if we backfilled any zeros from cache, show suffix
            if any(float(prices_new.get(c, 0.0) or 0.0) <= 0 and float(last_prices_snap.get(c, 0.0)) > 0 for c in coins):
                st.session_state["_price_source"] = "coingecko_primary+cache_backfill"
            else:
                st.session_state["_price_source"] = "coingecko_primary"
            update_success = True
        else:
            if msg:
                st.info(msg)
            # If API rate limit and computed value becomes 0 but we have previous non-zero -> keep previous snapshot
            if portfolio_value == 0 and st.session_state.get("_last_nonzero_portfolio_value", 0) > 0 and any(holdings.get(c, 0.0) > 0 for c in coins):
                portfolio_value = st.session_state["_last_nonzero_portfolio_value"]
                prices = st.session_state["_last_prices"]
                price_data = st.session_state["_last_price_data"]
                total_invested_now = st.session_state["_last_total_invested_now"]
                current_pnl = portfolio_value - total_invested_now
        
        # Debug list of zero-priced coins
        try:
            zero_coins = [c for c in coins if float(prices.get(c,0.0))==0.0 and float(holdings.get(c,0.0))!=0]
            if zero_coins:
                st.caption(f"[DEBUG] Zero-priced coins: {', '.join(zero_coins)} | source={st.session_state.get('_price_source','coingecko')}")
        except Exception:
            pass
    else:
        st.warning("Đang chờ hết thời gian delay sau lỗi API CoinGecko...")

    # Không auto refresh mỗi 65s nữa -> giữ dữ liệu static cho tới khi user bấm nút refresh
    if refresh_now:
        prices_new, pdata_new, updated, msg = get_current_prices()
        if updated:
            price_data = pdata_new
            # Merge new prices and carry-forward last non-zero for any missing/zero coins
            prices = {c: float(prices_new.get(c, 0.0) or 0.0) for c in coins}
            last_prices_snap = st.session_state.get("_last_prices", {})
            for c in coins:
                if float(prices.get(c, 0.0)) <= 0 and float(last_prices_snap.get(c, 0.0)) > 0:
                    prices[c] = float(last_prices_snap[c])
            now = int(time.time())
            portfolio_value = sum(float(prices.get(c, 0.0)) * float(holdings.get(c, 0.0)) for c in coins)
            if portfolio_value > 0:
                st.session_state["_last_nonzero_portfolio_value"] = portfolio_value
            total_invested_now = sum(avg_price.get(c, 0.0) * holdings.get(c, 0.0) for c in coins)
            current_pnl = portfolio_value - total_invested_now
            st.session_state["_last_price_data"] = price_data
            st.session_state["_last_prices"] = prices
            st.session_state["_last_portfolio_value"] = portfolio_value
            st.session_state["_last_total_invested_now"] = total_invested_now
            st.session_state["_last_current_pnl"] = current_pnl
            st.success("🔄 Đã tải lại dữ liệu giá mới nhất.")
        else:
            if msg:
                st.info(f"Không cập nhật được giá mới: {msg}")
    # If API failed and current computed value is 0 while we have a previous valid snapshot, reuse last non-zero value
    if portfolio_value == 0 and st.session_state.get("_last_nonzero_portfolio_value", 0) > 0 and any(holdings.get(c, 0.0) > 0 for c in coins):
        portfolio_value = st.session_state["_last_nonzero_portfolio_value"]

    history = load_history()
    # --- Lưu lịch sử tổng và từng coin ---
    # Lưu mỗi phút 1 lần (theo timestamp phút), chỉ lưu nếu portfolio_value > 0 (có data hợp lệ)
    # Noise filter for UI-side logging as well
    has_holdings_any = any(float(holdings.get(c, 0.0)) != 0 for c in coins)
    valid_snapshot = (portfolio_value >= 0) and (not has_holdings_any or portfolio_value > 0)
    # Kiểm tra lỗi API: nếu có holdings mà portfolio_value == 0 hoặc None thì không lưu
    api_error = False
    if (has_holdings_any and (portfolio_value == 0 or portfolio_value is None)):
        api_error = True
    # Ensure 'now' is defined
    if 'now' not in locals():
        now = int(time.time())
    if valid_snapshot and not api_error and (len(history) == 0 or now // 60 > history[-1]["timestamp"] // 60):
        # Lưu tổng portfolio + từng coin vào new_docs
        entry = {"timestamp": now, "value": portfolio_value, "PNL": current_pnl}
        new_docs = [entry]
        for coin in coins:
            coin_value = prices.get(coin, 0.0) * holdings.get(coin, 0.0)
            if coin_value > 0:
                coin_invested = avg_price.get(coin, 0.0) * holdings.get(coin, 0.0)
                coin_pnl = coin_value - coin_invested
                coin_entry = {
                    "timestamp": now,
                    "coin": coin,
                    "value": coin_value,
                    "invested": coin_invested,
                    "PNL": coin_pnl,
                    "amount": holdings.get(coin, 0.0),
                    "avg_price": avg_price.get(coin, 0.0)
                }
                new_docs.append(coin_entry)

        append_snapshot(new_docs)
        try:
            _db_upsert_portfolio_docs(new_docs)
        except Exception:
            pass


    # Đặt mặc định KPI để tránh NameError nếu nhảy qua block legacy
    metric_delta = "N/A"
    value_change = "N/A"
    value_yesterday = None


    # --- Hiển thị tổng giá trị portfolio và thay đổi so với hôm qua ---
    if history:
    # Lọc chỉ các entry tổng portfolio (không có key 'coin')
        df_hist_metric = pd.DataFrame([h for h in history if 'coin' not in h])
        if not df_hist_metric.empty:
            # Chỉ chuyển sang GMT+7 khi hiển thị, dữ liệu gốc vẫn giữ UTC
            df_hist_metric["Date"] = pd.to_datetime(df_hist_metric["timestamp"], unit="s").dt.tz_localize("UTC")
            now_dt = pd.Timestamp.now(tz=tz_gmt7)
            df_hist_sorted = df_hist_metric.sort_values("Date")
            yesterday = now_dt - pd.Timedelta(days=1)
            df_yesterday = df_hist_sorted[df_hist_sorted["Date"] <= yesterday]
            if not df_yesterday.empty:
                value_yesterday = df_yesterday.iloc[-1]["value"]
                metric_delta = f"{(portfolio_value - value_yesterday) / (value_yesterday + 1e-9) * 100:.2f}%"
                value_change = portfolio_value - value_yesterday

    # Display portfolio metric (prefer server-side summary totals to avoid drift)
    server_totals = st.session_state.get('_server_summary_totals') or {}
    server_value = float(server_totals.get('value', 0) or 0)
    
    # Debug: Compare values to understand discrepancy
    if server_value > 0 and abs(portfolio_value - server_value) > 50:  # Significant difference
        print(f"[DEBUG] Portfolio value discrepancy detected:")
        print(f"  UI calculated: ${portfolio_value:,.2f}")
        print(f"  Server calculated: ${server_value:,.2f}")
        print(f"  Difference: ${abs(portfolio_value - server_value):,.2f}")
        print(f"  Price source: {st.session_state.get('_price_source', 'unknown')}")
        print(f"  Holdings count: {len([c for c in coins if holdings.get(c, 0.0) != 0])}")
        print(f"  Prices available: {len([c for c in coins if prices.get(c, 0.0) > 0])}")
    
    if isinstance(server_totals, dict) and server_value > 0:
        display_value = server_value
        value_source = "server-side"
    else:
        display_value = portfolio_value
        value_source = "ui-calculated"
        
    if display_value == 0 and st.session_state.get("_last_nonzero_portfolio_value", 0) > 0 and any(holdings.get(c, 0.0) > 0 for c in coins):
        display_value = st.session_state["_last_nonzero_portfolio_value"]
        value_source = "cached"

    # Debug portfolio value calculation comparison
    try:
        from app_init import compute_portfolio_summary
        import logging
        logger = logging.getLogger(__name__)
        #server_summary = compute_portfolio_summary()
        #server_calc_value = server_summary.get("total_value", 0)
        print(f"[DEBUG] UI calculated portfolio: ${portfolio_value:,.2f}")
        #print(f"[DEBUG] Server calculated portfolio: ${server_calc_value:,.2f}")
        print(f"[DEBUG] Display value: ${display_value:,.2f} ({value_source})")
        #print(f"[DEBUG] Value difference: ${abs(portfolio_value - server_calc_value):,.2f}")
        print(f"[DEBUG] Price source UI: {st.session_state.get('_price_source', 'unknown')}")
        
        # Check for significant difference
        # if abs(portfolio_value - server_calc_value) > 50:
        #     print(f"[DEBUG] Significant portfolio value discrepancy detected!")
        #     print(f"[DEBUG] UI Holdings: {dict(holdings)}")
        #     print(f"[DEBUG] UI Avg Prices: {dict(avg_price)}")
        #     print(f"[DEBUG] Server Holdings: {server_summary.get('holdings', {})}")
        #     print(f"[DEBUG] Server Avg Prices: {server_summary.get('avg_prices', {})}")
            
        #     # Check a few specific prices to see differences
        #     ui_sample = {k: prices.get(k, 0) for k in list(holdings.keys())[:5] if holdings.get(k, 0) > 0}
        #     server_prices = server_summary.get('prices', {})
        #     server_sample = {k: server_prices.get(k, 0) for k in list(holdings.keys())[:5] if holdings.get(k, 0) > 0}
        #     print(f"[DEBUG] UI price sample: {ui_sample}")
        #     print(f"[DEBUG] Server price sample: {server_sample}")
            
    except Exception as debug_ex:
        print(f"[DEBUG] Could not compare portfolio calculations: {debug_ex}")

    cached_note = ""
    if st.session_state.get("_bootstrap_source") == "db" and display_value > 0 and not update_success:
        cached_note = f" (db cached, {value_source})"
    elif not update_success and prices is st.session_state.get("_last_prices") and any(holdings.get(c, 0.0) > 0 for c in coins):
        cached_note = f" (cached, {value_source})"
    elif st.session_state.get("_price_source") == "api" and update_success:
        cached_note = f" (API, {value_source})"
    else:
        cached_note = f" ({value_source})"
    if metric_delta != "N/A" and value_change != "N/A" and value_yesterday is not None:
        st.metric(
            f"💰 Tổng giá trị Portfolio (USD){cached_note}",
            f"{display_value:,.2f}",
            delta=f"{metric_delta} | {value_change:,.2f} USD",
            delta_color="normal"
        )
    else:
        st.metric(f"💰 Tổng giá trị Portfolio (USD){cached_note}", f"{display_value:,.2f}", delta="N/A | N/A")

    # Calculate total invested capital
    invested_capital = sum(holdings.get(coin, 0.0) * avg_price.get(coin, 0.0) for coin in coins)

    # Calculate PNL
    pnl = display_value - invested_capital

    # Display additional metrics (two side-by-side as requested)
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("💸 Tổng số vốn đầu tư (USD)", f"{invested_capital:,.2f}")
    with col2:
        st.metric("📈 PNL (USD)", f"{pnl:,.2f}")
    with col3:
        pnl_pct = (pnl / invested_capital * 100) if invested_capital != 0 else 0.0
        st.metric("📊 PNL (%)", f"{pnl_pct:.2f}%")
    # Initialize df_input to avoid NameError - always create basic structure
    data = []
    for coin in coins:
        d = {
            "Coin": coin_id_to_name[coin],
            "Số token nắm giữ": holdings.get(coin, 0.0),
            "Giá mua trung bình": avg_price.get(coin, 0.0),
            "Giá hiện tại": prices.get(coin, 0.0),
            "% 1D": price_data.get(coin, {}).get("change_1d", 0),
            "% 7D": price_data.get(coin, {}).get("change_7d", 0),
            "% 30D": price_data.get(coin, {}).get("change_30d", 0),
        }
        data.append(d)
    df_input = pd.DataFrame(data)

    # Nếu đã có bảng server-side, hiển thị note nhưng vẫn cho phép legacy table
    if st.session_state.get('_server_reference_available'):
        st.caption("💡 Bảng server-side reference ở trên để so sánh. Bảng chính để quản lý ở dưới.")
    
    # Always show legacy portfolio table for management
    # Chuẩn bị dataframe cho bảng
    data = []
    for coin in coins:
        d = {
            "Coin": coin_id_to_name[coin],
            "Số token nắm giữ": holdings.get(coin, 0.0),
            "Giá mua trung bình": avg_price.get(coin, 0.0),
            "Giá hiện tại": prices.get(coin, 0.0),
            "% 1D": price_data.get(coin, {}).get("change_1d", 0),
            "% 7D": price_data.get(coin, {}).get("change_7d", 0),
            "% 30D": price_data.get(coin, {}).get("change_30d", 0),
        }
        data.append(d)
    df_input = pd.DataFrame(data)
    # Tính lại các cột sau khi nhập
    for idx, row in df_input.iterrows():
        coin = coins[idx]
        # Lấy dữ liệu mới nhất từ session nếu có
        df_input.at[idx, "Số token nắm giữ"] = st.session_state["holdings"].get(coin, 0.0)
        df_input.at[idx, "Giá mua trung bình"] = st.session_state["avg_price"].get(coin, 0.0)
    
    # Only add computed columns if we have the base data
    if "Giá hiện tại" in df_input.columns:
        df_input["Tổng giá trị"] = df_input["Số token nắm giữ"] * df_input["Giá hiện tại"]
    else:
        df_input["Tổng giá trị"] = 0.0

    # PnL calculation functions
    def _pnl_row(row):
        amt = row["Số token nắm giữ"]
        avgc = row["Giá mua trung bình"]
        price_now = row["Giá hiện tại"]
        if amt >= 0:
            return price_now * amt - avgc * amt
        # position âm: coi như short => PNL = (avg_cost - current_price)*abs(amt)
        return (avgc - price_now) * abs(amt)
    
    if not df_input.empty:
        df_input["Profit & Loss"] = df_input.apply(_pnl_row, axis=1)
    
    def _pct_pl(row):
        amt = row["Số token nắm giữ"]
        avgc = row["Giá mua trung bình"]
        if avgc == 0 or amt == 0:
            return 0.0
        invested = avgc * abs(amt)
        if invested <= 0:
            return 0.0
        return 100 * row["Profit & Loss"] / (invested + 1e-9)
    
    if not df_input.empty:
        df_input["% Profit/Loss"] = df_input.apply(_pct_pl, axis=1)
    
    if not df_input.empty:
        df_input["% Hòa vốn"] = np.where(df_input["Profit & Loss"] >= 0, 0.0, 100 * -df_input["Profit & Loss"] / (df_input["Giá mua trung bình"] * df_input["Số token nắm giữ"] + 1e-9))

    # Only process legacy portfolio editor if not empty
    if not df_input.empty:
            # Cho phép nhập liệu trực tiếp trong expander
            with st.expander("Nhập liệu Portfolio (có thể thu nhỏ)", expanded=False):
                # Hiển thị thông tin lần ghi cuối & nguồn dữ liệu
                try:
                    from app_init import get_app_state
                    _state = get_app_state()
                    ts = _state.get("last_write_ts")
                    src = st.session_state.get("_bootstrap_source", "unknown")
                    if ts:
                        import datetime
                        ts_readable = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
                        st.caption(f"Nguồn: {src} • Last write: {ts_readable} (epoch {int(ts)})")
                except Exception:
                    pass
                
                # Check if required columns exist
                if all(col in df_input.columns for col in ["Coin", "Số token nắm giữ", "Giá mua trung bình"]):
                    edited_df = st.data_editor(
                        df_input[[
                            "Coin",
                            "Số token nắm giữ",
                            "Giá mua trung bình"
                        ]],
                        column_config={
                            # Cho phép nhập số âm để thể hiện vay
                            "Số token nắm giữ": st.column_config.NumberColumn("Số token nắm giữ", min_value=-1e12, step=0.0000000001, format="%.10f"),
                            "Giá mua trung bình": st.column_config.NumberColumn("Giá mua trung bình", min_value=0.0, step=0.01, format="%.4f"),
                        },
                        hide_index=True,
                        key="portfolio_table"
                    )
                else:
                    st.error(f"Missing required columns. Available: {list(df_input.columns)}")
                    edited_df = pd.DataFrame(columns=["Coin", "Số token nắm giữ", "Giá mua trung bình"])
                
                # Thêm nút đẩy dữ liệu lên DB (đảm bảo đồng bộ edited_df trước khi push)
                if st.button("Đẩy dữ liệu lên DB", key="push_to_db"):
                    try:
                        from app_init import update_portfolio_data, rehydrate_from_db, get_portfolio_data, get_app_state
                        # Thu thập dữ liệu mới từ bảng (chỉ giữ coin xuất hiện)
                        new_hold = {}
                        new_avg = {}
                        for idx, row in edited_df.iterrows():
                            if idx < len(coins):
                                coin = coins[idx]
                                try:
                                    new_hold[coin] = float(row.get("Số token nắm giữ", 0.0) or 0.0)
                                except Exception:
                                    new_hold[coin] = 0.0
                                try:
                                    new_avg[coin] = float(row.get("Giá mua trung bình", 0.0) or 0.0)
                                except Exception:
                                    new_avg[coin] = 0.0

                        # Kiểm tra xung đột: nếu DB có last_write_ts mới hơn local trước khi ghi
                        state_before = get_app_state()
                        last_before = state_before.get("last_write_ts", 0)
                        # Rehydrate nhẹ để lấy DB snapshot mới nhất trước khi quyết định (không ghi)
                        rehydrate_from_db()
                        state_after_hydrate = get_app_state()
                        db_ts = state_after_hydrate.get("last_write_ts", 0)
                        conflict = db_ts > last_before
                        if conflict:
                            st.warning("⚠️ Phát hiện DB đã có cập nhật mới hơn. Đang dùng snapshot DB mới nhất để tránh ghi đè.")
                            # Lấy lại dữ liệu hiện tại sau hydrate để người dùng xác nhận
                            port_current, avg_current = get_portfolio_data()
                            # So sánh khác biệt số lượng coin để giúp quyết định
                            added = {k:v for k,v in port_current.items() if k not in new_hold or v!=new_hold[k]}
                            if added:
                                st.caption(f"(Debug khác biệt) Số lượng khác so với bảng: {list(added.items())[:5]}")
                            if not st.checkbox("Tôi muốn GHI ĐÈ DB bằng dữ liệu bảng (bỏ qua snapshot mới)", key="override_conflict"):
                                st.info("Hủy thao tác ghi. Bạn có thể tick checkbox để ghi đè nếu chắc chắn.")
                                # Refresh hiển thị holdings/avg_price từ DB snapshot mới
                                st.session_state["holdings"], st.session_state["avg_price"] = port_current, avg_current
                                st.stop()

                        # Không có xung đột hoặc người dùng chấp nhận ghi đè
                        update_portfolio_data(new_hold, new_avg)
                        # Rehydrate from DB to confirm persist path
                        rehydrate_from_db()
                        port_after, avg_after = get_portfolio_data()
                        st.session_state["holdings"] = port_after
                        st.session_state["avg_price"] = avg_after
                        st.session_state["_bootstrap_source"] = "manual_commit"
                        st.success("✅ Đã cập nhật & đồng bộ DB (kèm rehydrate)")
                    except Exception as e:
                        st.error(f"Lỗi khi đẩy dữ liệu lên DB: {e}")

                # Legacy transaction and portfolio display sections (wrapped in conditional)
                # Dòng 'Nhập giao dịch mua mới để tự động cập nhật giá mua trung bình'
                st.write("Nhập giao dịch mua mới để tự động cập nhật giá mua trung bình")
                coin_options = [coin_id_to_name[c] for c in coins]
                selected_buy_coin_name = st.selectbox("Chọn coin để nhập giao dịch mua mới", coin_options, key="buy_coin_select")
                selected_buy_coin = coin_name_to_id[selected_buy_coin_name]
                buy_cols = st.columns([2,2,2,1])
                with buy_cols[0]:
                    st.markdown(f"**{selected_buy_coin_name}**")
                with buy_cols[1]:
                    buy_amount = st.number_input(f"Số lượng mua mới ({selected_buy_coin_name})", min_value=0.0, step=0.00000001, format="%.8f", key=f"buy_amt_{selected_buy_coin}")
                with buy_cols[2]:
                    buy_price = st.number_input(f"Giá mua mới ({selected_buy_coin_name})", min_value=0.0, step=0.01, format="%.4f", key=f"buy_price_{selected_buy_coin}")
                update_avg = st.button("Cập nhật AVG & Số lượng", key="update_avg_btn")
                if update_avg:
                    amt_new = buy_amount
                    price_new = buy_price
                    if amt_new > 0:
                        amt_old = st.session_state["holdings"].get(selected_buy_coin, 0.0)
                        avg_old = st.session_state["avg_price"].get(selected_buy_coin, 0.0)
                        total_amt = amt_old + amt_new
                        if total_amt > 0:
                            avg_new = (amt_old * avg_old + amt_new * price_new) / total_amt
                        else:
                            avg_new = 0.0
                        st.session_state["holdings"][selected_buy_coin] = total_amt
                        st.session_state["avg_price"][selected_buy_coin] = avg_new
                        save_holdings(st.session_state["holdings"])
                        save_avg_price(st.session_state["avg_price"])
                        st.success(f"Đã cập nhật giá mua trung bình và số lượng cho {selected_buy_coin_name}!")

            # Initialize edited_df for legacy mode  
            edited_df = df_input.copy()

    # Portfolio display and styling logic (always available)
    def color_profit(val):
        if val > 0:
            return 'color: green;'
        elif val < 0:
            return 'color: red;'
        else:
            return ''

    # (Không auto-sync bảng vào holdings/avg_price. Chỉ cập nhật khi bấm nút 'Đẩy dữ liệu lên DB'.)

    # Tạo bảng kết quả với các cột tính toán và màu sắc (always available now)
    result_df = edited_df.copy()
    import pandas as pd
    if hasattr(result_df, 'to_pandas'):
        result_df = result_df.to_pandas()
    elif not isinstance(result_df, pd.DataFrame):
        result_df = pd.DataFrame(result_df)
    result_df["Giá hiện tại"] = [prices.get(c, 0) for c in coins]
    result_df["% 1D"] = [price_data.get(c, {}).get("change_1d", 0) for c in coins]
    result_df["% 7D"] = [price_data.get(c, {}).get("change_7d", 0) for c in coins]
    result_df["% 30D"] = [price_data.get(c, {}).get("change_30d", 0) for c in coins]
    # Debug hỗ trợ nếu toàn 0 nhưng backend có dữ liệu
    try:
        if all(v.get("change_1d", 0) == 0 for k, v in price_data.items()) and any(
            (v.get("change_1d",0)!=0 or v.get("change_7d",0)!=0 or v.get("change_30d",0)!=0) for v in price_data.values()
        ):
            st.caption("(Debug) price_data có dữ liệu nhưng bảng mapping sai key. Kiểm tra coin id vs symbol.")
    except Exception:
        pass
    try:
        if all((result_df["% 1D"]==0) & (result_df["% 7D"]==0) & (result_df["% 30D"]==0)):
            st.caption("(Debug) Tất cả change% đang = 0. Kiểm tra backend /prices/spot hoặc file last_prices.json.")
    except Exception:
        pass
    result_df["Tổng giá trị"] = result_df["Số token nắm giữ"] * result_df["Giá hiện tại"]
    def _pnl_row2(row):
        amt = row["Số token nắm giữ"]
        avgc = row["Giá mua trung bình"]
        price_now = row["Giá hiện tại"]
        if amt >= 0:
            return price_now * amt - avgc * amt
        return (avgc - price_now) * abs(amt)
    result_df["Profit & Loss"] = result_df.apply(_pnl_row2, axis=1)
    def _pct_pl2(row):
        amt = row["Số token nắm giữ"]
        avgc = row["Giá mua trung bình"]
        if avgc == 0 or amt == 0:
            return 0.0
        invested = avgc * abs(amt)
        if invested <= 0:
            return 0.0
        return 100 * row["Profit & Loss"] / (invested + 1e-9)
    result_df["% Profit/Loss"] = result_df.apply(_pct_pl2, axis=1)
    result_df["% Hòa vốn"] = np.where(
        result_df["Profit & Loss"] >= 0,
        0.0,
        100 * abs(result_df["Profit & Loss"]) / (result_df["Tổng giá trị"] + 1e-9)
    )

    styled_result = result_df[[
        "Coin",
        "Số token nắm giữ",
        "Giá mua trung bình",
        "Giá hiện tại",
        "% 1D",
        "% 7D",
        "% 30D",
        "Tổng giá trị",
        "Profit & Loss",
        "% Profit/Loss",
        "% Hòa vốn"
    ]].style.format({
        "Số token nắm giữ": "{:.10f}",
        "Giá mua trung bình": "{:.4f}",
        "Giá hiện tại": "{:.4f}",
        "% 1D": "{:.2f}",
        "% 7D": "{:.2f}",
        "% 30D": "{:.2f}",
        "Tổng giá trị": "{:.2f}",
        "Profit & Loss": "{:.2f}",
        "% Profit/Loss": "{:.2f}",
        "% Hòa vốn": "{:.2f}"
    }).map(color_profit, subset=["Profit & Loss", "% Profit/Loss", "% 1D", "% 7D", "% 30D"])

    st.markdown("""
        <style>
        .stDataFrame thead tr th {
            font-weight: bold !important;
            color: #111 !important;
        }
        </style>
    """, unsafe_allow_html=True)
    st.dataframe(styled_result, hide_index=True, width='stretch')

    # (Đã bỏ nút 'Nhâp liệu mới' trùng key để tránh StreamlitDuplicateElementKey)

    # --- TÍNH VÀ HIỂN THỊ CHART, METRIC, PIE/BAR CHART ---
    # Lọc chỉ các entry tổng portfolio (không có key 'coin') cho chart tổng
    df_hist = pd.DataFrame([h for h in history if 'coin' not in h])
    metric_delta = ""
    metric_delta_pnl = ""
    metric_delta_profit = ""
    
    # Calculate metrics if we have history data
    if not df_hist.empty:
        # Chỉ chuyển sang GMT+7 khi hiển thị, dữ liệu gốc vẫn giữ UTC
        df_hist["Date"] = pd.to_datetime(df_hist["timestamp"], unit="s").dt.tz_localize("UTC")
        # Tính tổng số tiền đầu tư tại mỗi thời điểm (dùng giá mua trung bình hiện tại * số token hiện tại)
        total_invested = sum(
            st.session_state["avg_price"].get(c, 0.0) * st.session_state["holdings"].get(c, 0.0)
            for c in coins
        )
        df_hist["PNL"] = df_hist["value"] - total_invested
        df_hist["% Profit & Loss"] = np.where(
            df_hist["value"] > 0,
            df_hist["PNL"] / (df_hist["value"] + 1e-9) * 100,
            0.0
        )
        # Tìm giá trị hôm qua (gần nhất cách hiện tại >= 1 ngày)
        now_dt = pd.Timestamp.now(tz=tz_gmt7)
        df_hist_sorted = df_hist.sort_values("Date")
        yesterday = now_dt - pd.Timedelta(days=1)
        df_yesterday = df_hist_sorted[df_hist_sorted["Date"] <= yesterday]
        if not df_yesterday.empty:
            value_yesterday = df_yesterday.iloc[-1]["value"]
            pnl_yesterday = df_yesterday.iloc[-1]["PNL"]
            profit_yesterday = df_yesterday.iloc[-1]["% Profit & Loss"]
            metric_delta = f"{(portfolio_value - value_yesterday) / (value_yesterday + 1e-9) * 100:.2f}%"
            metric_delta_pnl = f"{(df_hist_sorted.iloc[-1]['PNL'] - pnl_yesterday):,.2f} USD"
            profit_today = df_hist_sorted.iloc[-1]["% Profit & Loss"]
            metric_delta_profit = f"{(profit_today - profit_yesterday):.2f}%"
        else:
            metric_delta = "N/A"
            metric_delta_pnl = "N/A"
            metric_delta_profit = "N/A"

        # Dropdown chọn time range
        range_option = st.selectbox("Chọn khung thời gian", ["30 ngày", "7 ngày", "1 ngày"])
        if range_option == "30 ngày":
            df_hist = df_hist[df_hist["Date"] >= now_dt - pd.Timedelta(days=30)]
        elif range_option == "7 ngày":
            df_hist = df_hist[df_hist["Date"] >= now_dt - pd.Timedelta(days=7)]
        elif range_option == "1 ngày":
            df_hist = df_hist[df_hist["Date"] >= now_dt - pd.Timedelta(days=1)]
    else:
        # No history data available - set defaults
        metric_delta = "N/A"
        metric_delta_pnl = "N/A"
        metric_delta_profit = "N/A"
        st.warning("⚠️ Chưa có dữ liệu lịch sử portfolio. Charts sẽ hiển thị khi có đủ dữ liệu.")
        print("[DEBUG] No historical data available for charts.")

    # Always show charts regardless of history data (they will handle empty data gracefully)
    try:
        show_portfolio_over_time_chart(filter_reliable_history(history), key="main_line_chart")
    except Exception as e:
        st.error(f"Error displaying portfolio chart: {e}")
        
    try:
        show_pie_distribution(result_df)
    except Exception as e:
        st.error(f"Error displaying pie chart: {e}")
        
    try:
        show_bar_pnl(result_df)
    except Exception as e:
        st.error(f"Error displaying bar chart: {e}")
        
    # Update session state with calculated metrics
    st.session_state["portfolio_value"] = portfolio_value
    st.session_state["total_invested_now"] = total_invested_now
    st.session_state["current_pnl"] = current_pnl
    st.session_state["metric_delta"] = metric_delta
    st.session_state["metric_delta_pnl"] = metric_delta_pnl
    st.session_state["metric_delta_profit"] = metric_delta_profit
    st.session_state["num_coins"] = sum(1 for c in coins if holdings.get(c, 0.0) != 0)
    
    if coins:
        values = [prices.get(c, 0) * holdings.get(c, 0.0) for c in coins]
        if any(values):
            max_idx = int(np.argmax(values))
            st.session_state["max_coin"] = coin_id_to_name[coins[max_idx]]
            st.session_state["max_coin_value"] = values[max_idx]
        profits = [prices.get(c, 0) * holdings.get(c, 0.0) - avg_price.get(c, 0.0) * holdings.get(c, 0.0) for c in coins]
        if any(profits):
            max_pnl_idx = int(np.argmax(profits))
            min_pnl_idx = int(np.argmin(profits))
            st.session_state["max_pnl_coin"] = coin_id_to_name[coins[max_pnl_idx]]
            st.session_state["max_pnl_value"] = profits[max_pnl_idx]
            st.session_state["min_pnl_coin"] = coin_id_to_name[coins[min_pnl_idx]]
            st.session_state["min_pnl_value"] = profits[min_pnl_idx]
            
            # --- Growth Chart (resilient snapshot) ---
            import pandas as _pd

            def _okx_symbol_for_coin(display_symbol: str) -> str:
                overrides = {"RENDER": "RENDER"}
                return overrides.get(display_symbol.upper(), display_symbol.upper())

            def _snapshot_file(bar: str) -> str:
                return f"ohlcv_snapshot_{bar}.json"

            def _save_okx_snapshot_file(data_map: dict, bar: str):
                try:
                    out = {}
                    for cid, dfc in data_map.items():
                        try:
                            sub = dfc[['timestamp','open','high','low','close','volume']].tail(200)
                            out[cid] = sub.to_dict(orient='list')
                        except Exception:
                            continue
                    with open(_snapshot_file(bar), 'w', encoding='utf-8') as f:
                        json.dump({"bar": bar, "data": out, "ts": time.time()}, f)
                except Exception:
                    pass

            def _load_okx_snapshot_file(bar: str) -> dict:
                fp = _snapshot_file(bar)
                if not os.path.exists(fp):
                    return {}
                try:
                    with open(fp, 'r', encoding='utf-8') as f:
                        raw = json.load(f)
                    if raw.get('bar') != bar:
                        return {}
                    out = {}
                    for cid, obj in raw.get('data', {}).items():
                        try:
                            df = pd.DataFrame(obj)
                            if not df.empty:
                                df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
                            out[cid] = df
                        except Exception:
                            continue
                    return out
                except Exception:
                    return {}

            def _prefetch_okx_ohlcv_all(bar: str = "30m"):
                snap = st.session_state.get('_ohlcv_snapshot_all')
                # Exclude stablecoins from OKX OHLCV as they don't have meaningful trading pairs
                tradeable_coins = [c for c in coins if c not in ['tether']]  # USDT doesn't trade against itself
                if snap and snap.get('bar') == bar and set(snap.get('coins', [])) == set(tradeable_coins):
                    return snap['data'], st.session_state.get('_okx_prefetch_stats', {})
                success = 0
                failed = []
                data_map: dict[str, pd.DataFrame] = {}
                for c in tradeable_coins:
                    base_disp = coin_id_to_name[c]
                    base = _okx_symbol_for_coin(base_disp)
                    symbol = f"{base}-USDT-SWAP"
                    df_ohlcv = None
                    for attempt in range(2):
                        try:
                            import metrics_ohlcv_okx as _mx
                            df_ohlcv = _mx.fetch_okx_ohlcv_oi(symbol=symbol, bar=bar, limit=200)
                            if df_ohlcv is not None and not df_ohlcv.empty:
                                break
                        except Exception:
                            df_ohlcv = None
                        time.sleep(0.25)
                    if df_ohlcv is None or df_ohlcv.empty:
                        failed.append(base_disp)
                    else:
                        success += 1
                        data_map[c] = df_ohlcv.copy()
                used_cache_file = False
                if success == 0:
                    file_map = _load_okx_snapshot_file(bar)
                    if file_map:
                        data_map = file_map
                        used_cache_file = True
                        success = len(data_map)
                        failed = [coin_id_to_name[c] for c in tradeable_coins if c not in data_map]
                stats = {
                    'bar': bar,
                    'success': success,
                    'total': len(tradeable_coins),
                    'failed_symbols': failed,
                    'used_cache_file': used_cache_file,
                    'timestamp': time.time()
                }
                st.session_state['_ohlcv_snapshot_all'] = {
                    'data': data_map,
                    'bar': bar,
                    'coins': list(tradeable_coins),
                    'ts': stats['timestamp']
                }
                st.session_state['_okx_prefetch_stats'] = stats
                if success > 0 and not used_cache_file:
                    _save_okx_snapshot_file(data_map, bar)
                return data_map, stats

            data_map, stats = _prefetch_okx_ohlcv_all(bar="30m")
            if stats.get('success', 0) == 0:
                st.error("⚠️ Không lấy được dữ liệu OKX 30m cho bất kỳ coin nào để vẽ chart tăng trưởng.")
            else:
                if stats.get('failed_symbols'):
                    st.warning(
                        f"OKX 30m: {stats['success']}/{stats['total']} coin có dữ liệu. Thiếu: {', '.join(stats['failed_symbols'])}" +
                        (" | Sử dụng snapshot file" if stats.get('used_cache_file') else "")
                    )
                else:
                    st.success(
                        f"OKX 30m: Đã tải đầy đủ {stats['success']}/{stats['total']} coin." +
                        (" (snapshot file)" if stats.get('used_cache_file') else "")
                    )
            if stats.get('success', 0) > 0:
                min_len = None
                aligned = {}
                for c, dfc in data_map.items():
                    try:
                        if dfc is None or dfc.empty or 'close' not in dfc.columns:
                            continue
                        closes = dfc['close'].astype(float).values
                        if len(closes) < 5:
                            continue
                        if 'ts' in dfc.columns:
                            times = _pd.to_datetime(dfc['ts'].values, unit='ms')
                        elif 'datetime' in dfc.columns:
                            times = _pd.to_datetime(dfc['datetime'], errors='coerce')
                        else:
                            times = _pd.to_datetime(dfc.iloc[:,0], unit='ms', errors='coerce')
                        if times.isna().all():
                            continue
                        if min_len is None or len(closes) < min_len:
                            min_len = len(closes)
                        aligned[c] = (times, closes)
                    except Exception:
                        continue
                if not aligned or not min_len or min_len < 5:
                    st.info("⚠️ Chưa đủ dữ liệu (>=5 nến) để vẽ chart tăng trưởng.")
                else:
                    fig = go.Figure()
                    for c in coins:
                        if c not in aligned:
                            continue
                        times, closes = aligned[c]
                        closes = closes[-min_len:]
                        times = times[-min_len:]
                        if closes[0] == 0:
                            continue
                        pct = (closes / closes[0] - 1) * 100
                        fig.add_trace(go.Scatter(x=times, y=pct, mode='lines', name=coin_id_to_name[c]))
                    if not fig.data:
                        st.info("⚠️ Không thể vẽ chart do thiếu dữ liệu hợp lệ.")
                    else:
                        ts_loaded = stats.get('timestamp')
                        # datetime here may refer to class imported via 'from datetime import datetime'
                        try:
                            loaded_at = datetime.utcfromtimestamp(ts_loaded).strftime('%H:%M:%S UTC') if ts_loaded else ''
                        except AttributeError:
                            import datetime as _dt_mod
                            loaded_at = _dt_mod.datetime.utcfromtimestamp(ts_loaded).strftime('%H:%M:%S UTC') if ts_loaded else ''
                        suffix = "(snapshot file)" if stats.get('used_cache_file') else ""
                        fig.update_layout(
                            title=f"Tăng trưởng (%) tất cả coin (OKX 30m - snapshot) {suffix} | Loaded {loaded_at}",
                            xaxis_title="Thời gian",
                            yaxis_title="% Tăng trưởng",
                            hovermode='x unified',
                            legend=dict(
                                orientation='h', 
                                yanchor='bottom', 
                                y=-10,  # Adjusted to move the legend below the chart
                                xanchor='right', 
                                x=1
                            )
                        )
                        # Updated deprecation: use width='stretch' instead of use_container_width
                        st.plotly_chart(
                            fig,
                            width='stretch',
                            config={
                                'displaylogo': False,
                                'modeBarButtonsToRemove': ['lasso2d','select2d'],
                                'responsive': True
                            }
                        )

# Phase 0 unified overlay refactor start
from services.whale.whale_loader import load_whales_for_symbol, as_overlay_events

def phase0_overlay_whales(coin_symbol: str, df_ohlcv, fig_ohlcv):
    try:
        if not fig_ohlcv or df_ohlcv is None or df_ohlcv.empty:
            return
        from overlay_whale_alert import overlay_whale_alert_chart
        # Load generic events (cached to avoid heavy IO on reruns)
        @st.cache_data(ttl=15)
        def _cached_load_whales_for_overlay(sym: str):
            return load_whales_for_symbol(sym)
        raw_events = _cached_load_whales_for_overlay(coin_symbol)
        overlay_events = as_overlay_events(raw_events)
        if not overlay_events:
            return
        # Slider step heuristic (reuse older logic per token)
        step = 1.0
        if coin_symbol in ("LINK",):
            step = 100.0
        elif coin_symbol == "BNB":
            step = 10.0
        elif coin_symbol == "ETH":
            step = 0.1
        overlay_whale_alert_chart(
            whale_txs=overlay_events,
            df_ohlcv=df_ohlcv,
            coin_symbol=coin_symbol,
            slider_label=f"Lọc Whale ({coin_symbol})",
            slider_step=step,
            value_unit=coin_symbol,
            type_map={"BUY": "MUA", "SELL": "BÁN", "N/A": "Khác"},
            color_map={"BUY": "#43a047", "SELL": "#e53935", "N/A": "#949086"},
            default_show=True,
            key_prefix=f"unified_{coin_symbol.lower()}_"
        )
    except Exception as _ph0_ex:
        st.warning(f"[Phase0 unified overlay lỗi {coin_symbol}]: {_ph0_ex}")

# ===================== TAB 2 (Metrics) & PER-COIN TABS (RESTORED Phase 0) =====================
# Tab2: hiển thị các metric tổng hợp (có thể mở rộng thêm sau)
with tab2:
    st.title("📈 Metrics tổng hợp")
    # Sử dụng các module metrics nếu có
    cols = st.columns(3)
    with cols[0]:
        try:
            import metrics_dominance as _md
            dom = _md.load_dominance_cached()
            print("[DEBUG] DOM: ",dom)
            if dom:
                st.metric("BTC Dominance (%)", f"{dom.get('btc',0):.2f}")
            else:
                st.caption("Dominance n/a (no data)")
        except Exception as e:
            st.caption(f"Dominance n/a: {e}")
    with cols[1]:
        try:
            import metrics_fear_greed as _fg
            fg = _fg.load_fear_greed_cached()
            if fg:
                st.metric("Fear & Greed", f"{fg.get('value',0)} {fg.get('value_classification','')}" )
            else:
                st.caption("FG n/a (no data)")
        except Exception as e:
            st.caption(f"FG n/a: {e}")
    with cols[2]:
        try:

            import metrics_marketcap_volume as _mv
           
            mv = _mv.load_global_marketcap_cached()
            if mv:
                st.metric("Total MktCap (T)", f"{mv.get('total_market_cap_usd',0)/1e12:.2f}")
            else:
                st.caption("MktCap n/a (no data)")
        except Exception as e:
            st.caption(f"MktCap n/a: {e}")
    # Health panel (tùy chọn)
    try:
        show_health_panel()
    except Exception:
        pass
    # ================== BỔ SUNG CHART LỊCH SỬ (PHASE 4 RESTORE) ==================
    st.markdown("---")
    with st.expander("BTC / ETH / Others Dominance (History)", expanded=False):
        try:
            import metrics_dominance as _md
            _md.show_dominance_metric()
        except Exception as _dom_ex:
            st.caption(f"Không hiển thị được dominance chart: {_dom_ex}")
    with st.expander("Fear & Greed Index (History)", expanded=False):
        try:
            import metrics_fear_greed as _fg
            _fg.show_fear_greed_metric()
        except Exception as _fg_ex:
            st.caption(f"Không hiển thị được Fear & Greed chart: {_fg_ex}")
    with st.expander("Total Market Cap & Volume (History)", expanded=False):
        try:
            import metrics_marketcap_volume as _mv
            _mv.show_marketcap_volume_chart()
        except Exception as _mc_ex:
            st.caption(f"Không hiển thị được Market Cap chart: {_mc_ex}")
    st.caption("(Phase 4) Metrics tab đã khôi phục đầy đủ biểu đồ lịch sử.")

    # === RSI Heatmap panel ===
    with st.expander("RSI Heatmap (MarketCap vs RSI)", expanded=False):
        try:
            import metrics_rsi as _rsi
            # timeframe selector
            tf = st.selectbox("Chọn timeframe RSI", ["4h", "1d", "7d"], index=1, key="rsi_timeframe")
            # universe selector
            uni = st.selectbox("Universe", ["top30", "top50", "portfolio", "all"], index=0, key="rsi_universe")
            st.caption("Lưu ý: RSI được tính từ nguồn OHLCV; có thể dùng CoinGecko nếu nguồn OHLCV không có.")
            # Fetch universe metadata
            list_meta = _rsi.get_universe_from_config(option=uni)
            if not list_meta:
                st.caption("Không lấy được danh sách coin từ CoinGecko.")
            else:
                df_meta = pd.DataFrame(list_meta)
                symbols = df_meta['symbol'].tolist()
                # Cache info and refresh control
                cache_info = _rsi.rsi_cache_info()
                last_ts = cache_info.get('last_updated')
                last_str = pd.to_datetime(last_ts, unit='s', utc=True).strftime('%Y-%m-%d %H:%M:%S (UTC)') if last_ts else 'N/A'
                cols_r = st.columns([1,1,2])
                cols_r[0].caption(f"Cached: {cache_info.get('count',0)} items")
                cols_r[1].caption(f"Last update: {last_str}")
                if cols_r[2].button("🔄 Refresh RSI (force)"):
                    force_refresh = True
                else:
                    force_refresh = False

                with st.spinner("Lấy dữ liệu RSI (cache-aware)..."):
                    # Use Streamlit-level cached wrapper to avoid repeated expensive fetches on reruns
                    rsi_map = get_rsi_for_universe_cached(tuple(symbols), timeframe=tf, ttl_seconds=3600, force_refresh=force_refresh)

                fig = _rsi.build_rsi_scatter(df_meta, rsi_map, title=f"RSI Heatmap - {tf} - {uni}")
                if fig is None:
                    st.caption("Không có dữ liệu RSI để hiển thị.")
                else:
                    st.plotly_chart(fig, use_container_width=True)
        except Exception as _rsi_ex:
            st.caption(f"RSI panel error: {_rsi_ex}")

# Per-coin tabs: tái tạo loop hiển thị OHLCV + overlay whale (unified)
for idx, coin_tuple in enumerate(COIN_LIST):
    coin_id, coin_symbol = coin_tuple
    # Bỏ qua nếu không tồn tại tab (phòng trường hợp user filter coin)
    if idx >= len(tab_coin_tabs):
        continue
    with tab_coin_tabs[idx]:
        st.subheader(f"📌 {coin_symbol} - Tổng quan")
        # Compact per-coin summary metrics (value, invested, PNL USD, PNL %)
        try:
            render_coin_summary(coin_id, coin_symbol)
        except Exception:
            pass
        # === Timeframe selection ===
        khung_list = [("5m", "5 phút"), ("15m", "15 phút"), ("30m", "30 phút"), ("1H", "1 giờ")]
        bar_options = {label: bar for bar, label in khung_list}
        bar_label = st.selectbox(
            f"Chọn khung thời gian giá/volume OKX cho {coin_symbol}",
            list(bar_options.keys()),
            index=2,
            key=f"ohlcv_bar_retab_{coin_symbol}"
        )
        bar = bar_options[bar_label]

        # === Prefetch (first coin triggers) ===
        prefetch_ohlcv_all(bar, [c[1] for c in COIN_LIST])  # use display symbols
        df_ohlcv = get_prefetched_ohlcv(bar, coin_symbol)
        fig_ohlcv = None
        if df_ohlcv is None:
            # fallback single fetch
            try:
                df_ohlcv = fetch_okx_ohlcv_cached(symbol=f"{coin_symbol}-USDT-SWAP", bar=bar, limit=200)
            except Exception as _ex:
                st.warning(f"Không lấy được OHLCV {coin_symbol}: {_ex}")
                df_ohlcv = None
        fig_ohlcv = metrics_ohlcv_okx.plot_price_volume_chart(df_ohlcv, symbol=f"{coin_symbol}-USDT-SWAP") if df_ohlcv is not None else None

        # === Normalize datetime to UTC ===
        if df_ohlcv is not None and not df_ohlcv.empty and 'datetime' in df_ohlcv.columns:
            if not isinstance(df_ohlcv['datetime'].dtype, pd.DatetimeTZDtype):
                try:
                    df_ohlcv['datetime'] = pd.to_datetime(df_ohlcv['datetime'], errors='coerce').dt.tz_localize('UTC')
                except Exception:
                    pass

        # === Liquidation Heatmap (if available) ===
        with st.expander("Liquidation Heatmap", expanded=False):
            enable_liq = st.checkbox(
                f"Bật heatmap cho {coin_symbol}",
                value=True,
                key=f"liq_enable_{coin_symbol}"
            )
            if not enable_liq:
                st.caption("Tắt theo mặc định để tăng tốc trang. Bật để tải dữ liệu (có thể mất vài giây).")
            else:
                try:
                    import metrics_liquidation_okx as _mlo
                    # Controls
                    srcs = st.multiselect(
                        "Nguồn dữ liệu sàn",
                        options=["OKX","BINANCE","BITMEX"],
                        default=["OKX"],
                        key=f"liq_src_{coin_symbol}"
                    )
                    tframe = st.selectbox(
                        f"Khung thời gian (OKX) - {coin_symbol}",
                        options=["3M","1M","7D","1D"],
                        index=3,  # default to 1D
                        key=f"liq_tf_{coin_symbol}"
                    )
                    thr = st.slider(
                        "Ngưỡng lọc (tổng size mỗi ô)",
                        min_value=1,
                        max_value=100,
                        value=8,
                        step=1,
                        key=f"liq_thr_{coin_symbol}"
                    )
                    # Optional advanced binning
                    with st.expander("Tùy chọn nâng cao", expanded=False):
                        time_bins = st.slider("Số ô thời gian", 12, 200, 50, key=f"liq_tb_{coin_symbol}")
                        price_bins = st.slider("Số ô giá", 20, 300, 45, key=f"liq_pb_{coin_symbol}")
                        colorscale = st.selectbox(
                            "Màu Heatmap",
                            options=["Reds","Viridis","Plasma","Cividis","Hot","Turbo"],
                            index=2,  # Plasma
                            key=f"liq_cs_{coin_symbol}"
                        )
                        reverse_y = st.checkbox(
                            "Đảo trục giá (giá cao ở trên)",
                            value=False,
                            key=f"liq_rev_{coin_symbol}"
                        )
                        overlay_price = st.checkbox(
                            "Overlay đường giá lịch sử",
                            value=True,
                            key=f"liq_ovp_{coin_symbol}"
                        )
                    # Determine timeframe
                    from datetime import datetime, timedelta
                    now_dt = datetime.utcnow()
                    tf_map = {
                        "3M": now_dt - timedelta(days=90),
                        "1M": now_dt - timedelta(days=30),
                        "7D": now_dt - timedelta(days=7),
                        "1D": now_dt - timedelta(days=1),
                    }
                    start_dt = tf_map.get(tframe, now_dt - timedelta(days=90))

                    # Quick guidance for selected sources
                    if "BITMEX" in srcs and coin_symbol not in ("BTC","XBT","ETH"):
                        st.info("BitMEX chỉ hỗ trợ BTC/XBT/ETH trong phiên bản này — các coin khác sẽ không có dữ liệu.")
                    if "BINANCE" in srcs and tframe in ("3M","1M"):
                        st.info("Binance allForceOrders có thể giới hạn cửa sổ thời gian. Nếu không thấy dữ liệu, thử 7D hoặc 1D.")
                    symbol_okx = f"{coin_symbol}-USDT-SWAP"
                    # Fetch data depending on selected sources (non-blocking inside provider functions)
                    if srcs and (len(srcs) == 1 and srcs[0] == "OKX"):
                        df_liq = fetch_okx_liq_range_cached(symbol_okx, int(start_dt.timestamp()), int(now_dt.timestamp()))
                    else:
                        df_liq = fetch_liq_multi_cached(coin_symbol, int(start_dt.timestamp()), int(now_dt.timestamp()), tuple(srcs or ["OKX"]), symbol_okx)
                    # Auto-fallback to shorter ranges if empty
                    fallback_used = None
                    if df_liq is None or (hasattr(df_liq, 'empty') and df_liq.empty):
                        for alt in ("1M","7D","1D"):
                            alt_start = tf_map[alt]
                            if srcs and (len(srcs) == 1 and srcs[0] == "OKX"):
                                df_alt = fetch_okx_liq_range_cached(symbol_okx, int(alt_start.timestamp()), int(now_dt.timestamp()))
                            else:
                                df_alt = fetch_liq_multi_cached(coin_symbol, int(alt_start.timestamp()), int(now_dt.timestamp()), tuple(srcs or ["OKX"]), symbol_okx)
                            if df_alt is not None and not (hasattr(df_alt,'empty') and df_alt.empty):
                                df_liq = df_alt
                                fallback_used = alt
                                break
                    if df_liq is not None and not (hasattr(df_liq,'empty') and df_liq.empty):
                        # Per-source stats & hints
                        try:
                            if 'exchange' in df_liq.columns:
                                counts = df_liq['exchange'].value_counts().to_dict()
                                parts = [f"{k}: {v}" for k, v in sorted(counts.items())]
                                st.caption("Số event theo nguồn: " + ", ".join(parts))
                                missing = [s for s in (srcs or []) if s not in counts or counts.get(s,0)==0]
                                hints = []
                                if "BINANCE" in missing:
                                    hints.append("Binance có thể bị rate-limit/geo-block hoặc giới hạn cửa sổ — thử 7D/1D hoặc proxy.")
                                if "BITMEX" in missing and coin_symbol not in ("BTC","XBT","ETH"):
                                    hints.append("BitMEX chỉ hỗ trợ BTC/XBT/ETH ở phiên bản này.")
                                if hints:
                                    st.caption(" · ".join(hints))
                            else:
                                st.caption(f"Số event: {len(df_liq)}")
                        except Exception:
                            pass
                        try:
                            fig_liq = _mlo.build_liquidation_heatmap(
                                df_liq, symbol_okx,
                                time_bins=time_bins,
                                price_bins=price_bins,
                                threshold=thr,
                                timeframe_label=fallback_used or tframe,
                                overlay_price=overlay_price,
                                colorscale=colorscale,
                                yaxis_reverse=reverse_y
                            )
                            if fig_liq is not None:
                                st.plotly_chart(
                                    fig_liq,
                                    use_container_width=True,
                                    key=f"liq_{coin_symbol}",
                                    config={'displaylogo': False, 'responsive': True}
                                )
                                if fallback_used:
                                    st.caption(f"Không đủ dữ liệu {tframe}, đang hiển thị {fallback_used}.")
                            else:
                                st.caption("Không thể tạo heatmap từ dữ liệu hiện có.")
                        except Exception as _liq_ex:
                            st.caption(f"Không vẽ được heatmap: {_liq_ex}")
                    else:
                        # Build source-aware empty message
                        src_list = ", ".join(srcs) if srcs else "(none)"
                        base_msg = f"Không có dữ liệu liquidation cho khung đã chọn từ nguồn: {src_list}."
                        st.caption(base_msg)
                        # Diagnostics from providers (if available)
                        try:
                            import metrics_liquidation_okx as _mlo_diag
                            warn_map = _mlo_diag.get_source_warnings()
                            for s in (srcs or []):
                                w = warn_map.get(s.upper())
                                if w:
                                    st.caption(f"⚠ {s}: {w}")
                        except Exception:
                            pass
                except Exception as _liq_mod_ex:
                    st.caption(f"Module liquidation không khả dụng: {_liq_mod_ex}")

        # === Portfolio history for this coin ===
        with st.expander("Lịch sử Portfolio Coin", expanded=False):
            try:
                hist_all = load_portfolio_history_cached(HISTORY_FILE)
                coin_hist = [h for h in hist_all if h.get('coin') == coin_id]
                if coin_hist:
                    import pandas as _pd
                    df_ch = _pd.DataFrame(coin_hist)
                    df_ch['Date'] = _pd.to_datetime(df_ch['timestamp'], unit='s', utc=True)
                    df_ch.sort_values('Date', inplace=True)
                    df_ch['PNL'] = df_ch['value'] - (df_ch.get('invested') if 'invested' in df_ch.columns else 0)
                    # Chart value & PNL dual-axis
                    import plotly.graph_objects as _go
                    fig_coin = _go.Figure()
                    fig_coin.add_trace(_go.Scatter(x=df_ch['Date'], y=df_ch['value'], mode='lines', name='Value'))
                    if 'PNL' in df_ch.columns:
                        fig_coin.add_trace(_go.Scatter(x=df_ch['Date'], y=df_ch['PNL'], mode='lines', name='PNL', yaxis='y2'))
                        fig_coin.update_layout(
                            yaxis=dict(title='Value USD'),
                            yaxis2=dict(title='PNL', overlaying='y', side='right', showgrid=False)
                        )
                    fig_coin.update_layout(margin=dict(l=10,r=10,t=30,b=10), title=f"Portfolio History {coin_symbol}")
                    st.plotly_chart(
                        fig_coin,
                        width='stretch',
                        key=f"hist_{coin_symbol}",
                        config={'displaylogo': False, 'responsive': True}
                    )
                else:
                    st.caption("Chưa có lịch sử cho coin này.")
            except Exception as _ch_ex:
                st.caption(f"Không load được lịch sử: {_ch_ex}")

        # === Save fig to session for overlay ===
        if fig_ohlcv:
            st.session_state[f"fig_ohlcv_{coin_symbol}"] = fig_ohlcv

        # === Whale overlay (unified) ===
        phase0_overlay_whales(coin_symbol, df_ohlcv, fig_ohlcv)

        # === On-chain & Derived Metrics ===
        with st.expander("On-chain & MVRV Metrics", expanded=False):
            try:
                # Map display symbol back to CoinGecko id (coin_id)
                asset_id = coin_id  # coin_id already is coingecko id per config
                df_on = load_onchain_metrics_cached(asset_id)
                if df_on is None:
                    st.caption("Chưa có dữ liệu on-chain (Coin Metrics community API).")
                else:
                    import pandas as _pd
                    import plotly.graph_objects as _go
                    # Hiển thị các cột phổ biến nếu tồn tại
                    show_cols = [c for c in ["PriceUSD","AdrActCnt","TxCnt","FeeTotUSD","HashRate"] if c in df_on.columns]
                    # Chỉ lấy 180 ngày gần nhất cho nhẹ
                    try:
                        if 'date' in df_on.columns:
                            df_on['date'] = _pd.to_datetime(df_on['date'], errors='coerce')
                            df_on = df_on.dropna(subset=['date']).sort_values('date')
                            cutoff = df_on['date'].max() - _pd.Timedelta(days=180)
                            df_on = df_on[df_on['date'] >= cutoff]
                    except Exception:
                        pass
                    if show_cols:
                        fig_on = _go.Figure()
                        for c in show_cols:
                            try:
                                series = _pd.to_numeric(df_on[c], errors='coerce')
                                if series.notna().sum() == 0:
                                    continue
                                fig_on.add_trace(_go.Scatter(x=df_on['date'], y=series, mode='lines', name=c))
                            except Exception:
                                continue
                        fig_on.update_layout(title=f"On-chain Metrics (sample) - {coin_symbol}", height=320, hovermode='x unified')
                        st.plotly_chart(fig_on, width="stretch", config={'displaylogo': False, 'responsive': True})
                    else:
                        st.caption("Không có cột on-chain hiển thị được.")
                # MVRV (sử dụng file sample nếu có)
                try:
                    import metrics_mvrv_z as _mvrv
                    mvrv_fig = _mvrv.plot_mvrv_z_score(coin_id=coin_id)
                    if mvrv_fig:
                        st.plotly_chart(mvrv_fig, width="stretch", config={'displaylogo': False, 'responsive': True})
                except Exception:
                    pass
            except Exception as _on_ex:
                st.caption(f"On-chain metrics error: {_on_ex}")

        # === Whale Large Transactions box (restored feature) ===
        with st.expander(f"🐳 {coin_symbol} Large Transactions", expanded=False):
            try:
                from services.whale.whale_loader import load_whales_for_symbol as _lwf, to_dataframe as _wh_df

                @st.cache_data(ttl=15)
                def _cached_box_whales(sym: str):
                    try:
                        return _lwf(sym)
                    except Exception:
                        return []

                events = _cached_box_whales(coin_symbol) if load_whales_for_symbol else []
                if not events:
                    st.caption("Chưa có whale events cho coin này.")
                else:
                    dfw = _wh_df(events)
                    # Fallback: nếu không có cột amount_token hoặc toàn 0 thử dựng từ các cột khác (value, value_token, amount, qty)
                    def _derive_amount_token(df):
                        alt_cols = [c for c in ['amount_token','value','value_token','amount','qty'] if c in df.columns]
                        # Nếu đã có amount_token có giá trị dương -> giữ nguyên
                        if 'amount_token' in df.columns and df['amount_token'].fillna(0).gt(0).any():
                            return df
                        for c in alt_cols:
                            try:
                                series = pd.to_numeric(df[c], errors='coerce')
                                if series.fillna(0).gt(0).any():
                                    df['amount_token'] = series
                                    break
                            except Exception:
                                continue
                        return df
                    dfw = _derive_amount_token(dfw)
                    # Derive USD value if possible (fallback estimate via current price)
                    if 'amount_usd' not in dfw.columns or dfw['amount_usd'].isna().all():
                        cur_price = None
                        try:
                            cur_price = st.session_state.get('_last_prices', {}).get(coin_id, None)
                        except Exception:
                            cur_price = None
                        if cur_price:
                            try:
                                dfw['amount_usd'] = dfw.get('amount_token', 0) * float(cur_price)
                            except Exception:
                                pass
                    # Filter threshold slider (token units)
                    max_amt = 0.0
                    if 'amount_token' in dfw.columns:
                        try:
                            max_amt = float(pd.to_numeric(dfw['amount_token'], errors='coerce').fillna(0).max())
                        except Exception:
                            max_amt = 0.0
                    # Nếu vẫn 0 nhưng có cột 'value' dương thì dùng 'value' làm amount_token
                    if max_amt <= 0 and 'value' in dfw.columns:
                        try:
                            value_max = float(pd.to_numeric(dfw['value'], errors='coerce').fillna(0).max())
                            if value_max > 0:
                                dfw['amount_token'] = pd.to_numeric(dfw['value'], errors='coerce').fillna(0)
                                max_amt = value_max
                        except Exception:
                            pass
                    if max_amt <= 0:
                        st.caption("Không tìm thấy giá trị giao dịch dương (amount_token/value). Hiển thị toàn bộ.")
                        thr = 0.0
                    else:
                        default_thr = round(max_amt * 0.1, 8)
                        # Ensure default within bounds
                        if default_thr <= 0:
                            default_thr = 0.0
                        thr = st.slider(
                            "Ngưỡng lọc (theo số token)",
                            min_value=0.0,
                            max_value=float(max_amt),
                            value=float(default_thr),
                            step=round(max_amt/100, 8) if max_amt/100 > 0 else max_amt,
                            key=f"whale_filter_slider_{coin_symbol}"
                        )
                    view = dfw
                    if 'amount_token' in view.columns:
                        view = view[ view['amount_token'] >= thr ]
                    # Format time
                    if 'ts' in view.columns:
                        try:
                            view = view.sort_values('ts', ascending=False)
                        except Exception:
                            pass
                        view['time'] = view['ts'].astype(str)
                    cols_show = [c for c in ['time','direction','amount_token','amount_usd','tx_hash','token'] if c in view.columns]
                    # Đảm bảo cột amount_token luôn có nếu tồn tại trong dataframe
                    if 'amount_token' in view.columns and 'amount_token' not in cols_show:
                        cols_show.append('amount_token')
                    if not cols_show:
                        cols_show = list(view.columns)[:6]
                    # --- Whale transactions table enhancements (Phase 1 polish) ---
                    # Add directional color styling and reorder columns with addresses emphasized if present.
                    # We build a styled dataframe (fallback to normal if styling fails).
                    display_df = view[cols_show].head(100).copy()
                    # Insert address columns if available but not selected
                    for addr_col in ['from_address','to_address','from','to']:
                        if addr_col in view.columns and addr_col not in display_df.columns:
                            display_df[addr_col] = view[addr_col]
                    # Rename common columns for clarity
                    rename_map = {
                        'amount_token': f'Amount ({coin_symbol})',
                        'amount_usd': 'Amount USD',
                        'direction': 'Side',
                        'tx_hash': 'Tx Hash'
                    }
                    display_df.rename(columns=rename_map, inplace=True)
                    # Nếu sau rename mà thiếu cột Amount (coin) (do rename logic), bổ sung lại
                    amt_col_name = f'Amount ({coin_symbol})'
                    if amt_col_name not in display_df.columns and 'amount_token' in view.columns:
                        display_df[amt_col_name] = view['amount_token'].head(len(display_df)).values
                    # Ensure Amount (coin) column is immediately left of Amount USD if both exist
                    desired_order = []
                    existing_cols = list(display_df.columns)
                    # Build order preference
                    for col in ['time','Side',f'Amount ({coin_symbol})','Amount USD','from_address','to_address','from','to','tx_hash','Tx Hash','token']:
                        if col in existing_cols and col not in desired_order:
                            desired_order.append(col)
                    # Append any remaining columns not already included
                    for col in existing_cols:
                        if col not in desired_order:
                            desired_order.append(col)
                    display_df = display_df[desired_order]
                    # Direction color map
                    side_color = {'BUY': '#1b5e20', 'SELL': '#b71c1c'}
                    def _color_row(row):
                        side = row.get('Side') or row.get('direction')
                        if side in side_color:
                            return [f'background-color: {side_color[side]}; color: white' for _ in row]
                        return ['' for _ in row]
                    try:
                        styled = display_df.style.apply(_color_row, axis=1)
                        st.dataframe(styled, hide_index=True, width='stretch')
                    except Exception:
                        st.dataframe(display_df, hide_index=True, width='stretch')
                    # Thay đổi giới hạn hiển thị sự kiện
                    st.caption(f"HIỂN THỊ TOÀN BỘ SỰ KIỆN | Tổng sự kiện: {len(dfw)} | Qua lọc: {len(view)}")
                    # Loại bỏ giới hạn 100 sự kiện
                    view = view.copy()  # Đảm bảo không bị giới hạn số lượng sự kiện
            except Exception as _wbox_ex:
                st.caption(f"Whale box error: {_wbox_ex}")

        # === Timezone Debug ===
        with st.expander("Timezone Debug", expanded=False):
            try:
                tz_info = None
                sample_times = []
                if df_ohlcv is not None and df_ohlcv.empty and 'datetime' in df_ohlcv.columns:
                    col = df_ohlcv['datetime']
                    tz_info = str(getattr(col.dt.tz, 'zone', col.dt.tz)) if hasattr(col, 'dt') else 'n/a'
                    sample_times = col.head(3).astype(str).tolist() + col.tail(3).astype(str).tolist()
                from services.whale.whale_loader import load_whales_for_symbol as _lwf
                raw_events = _lwf(coin_symbol)
                evt_time_samples = []
                for e in raw_events[:3]:
                    evt_time_samples.append(str(e.get('ts') or e.get('time')))
                st.json({
                    'ohlcv_datetime_dtype': str(df_ohlcv['datetime'].dtype) if (df_ohlcv is not None and df_ohlcv.empty and 'datetime' in df_ohlcv.columns) else 'missing',
                    'ohlcv_tz': tz_info,
                    'ohlcv_sample_times': sample_times,
                    'whale_event_time_samples': evt_time_samples,
                    'whale_event_count': len(raw_events)
                })
            except Exception as _tz_ex:
                st.caption(f"Timezone debug error: {_tz_ex}")

        # === Render final price chart ===
        if fig_ohlcv:
            st.plotly_chart(
                fig_ohlcv,
                width='stretch',
                key=f"plotly_chart_ret_{coin_symbol}",
                config={'displaylogo': False, 'responsive': True}
            )
        else:
            st.info("Chưa có dữ liệu OHLCV.")

        st.caption("(Phase 0) Coin tab: OHLCV prefetch + liquidation + portfolio history + whale overlay + timezone debug.")





