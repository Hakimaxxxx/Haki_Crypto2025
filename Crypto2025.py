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
    get_cached_data
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

def load_portfolio_holdings():
    """Load portfolio holdings using the new initialization system."""
    try:
        portfolio, avg_prices = get_portfolio_data()
        print(f"[DEBUG] load_portfolio_holdings() called - Portfolio: {len(portfolio)} items, Avg prices: {len(avg_prices)} items")
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
            ts = int(_t.time())
            row = {"timestamp": ts, "btc": btc, "eth": eth, "others": others}
            # Append to CSV
            try:
                if os.path.exists(file):
                    df = pd.read_csv(file)
                else:
                    df = pd.DataFrame(columns=["timestamp","btc","eth","others"])
                df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
                df.to_csv(file, index=False)
            except Exception:
                pass
            _db_upsert_dominance_row(row)
        except Exception:
            pass
        _t.sleep(300)
# để tránh NameError trong các hàm background.
# Đường dẫn file lưu holdings, giá mua trung bình, lịch sử portfolio
# (Đã lấy từ config)


# --- Nền: Ghi nhận Portfolio (Value/PNL/% P&L) theo phút, đồng bộ DB liên tục ---
def _fetch_prices_raw(coins_list: list[str]) -> dict:
    """Fetch current prices for given CoinGecko ids without Streamlit cache (for background thread)."""
    if not coins_list:
        return {}
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "ids": ",".join(coins_list),
        "price_change_percentage": "1h,24h,7d,30d"
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
    except Exception:
        data = []
    prices = {}
    for item in data:
        try:
            prices[item.get("id")] = float(item.get("current_price", 0) or 0)
        except Exception:
            prices[item.get("id")] = 0.0
    return prices


def _load_portfolio_meta_from_local() -> tuple[dict, dict]:
    """Load holdings and avg_price using the new initialization system."""
    holdings, avg_price_local = load_portfolio_holdings()
    
    # Ensure all coin keys exist
    for c in coin_ids:
        holdings.setdefault(c, 0.0)
        avg_price_local.setdefault(c, 0.0)
    
    return holdings, avg_price_local


def portfolio_recorder_background(interval_sec: int = 300):
    """Background loop to record portfolio totals and per-coin PNL every minute and upsert to DB.

    - Reads holdings/avg_price from local files (already synced to DB on edits)
    - Fetches prices from CoinGecko
    - Appends to portfolio_history.json (local) and upserts to MongoDB
    """
    history_file = HISTORY_FILE
    while True:
        try:
            holdings, avg_price_local = _load_portfolio_meta_from_local()
            # Consider coins with non-zero amount or avg to reduce API load
            active_coins = [c for c in coin_ids if (holdings.get(c, 0) != 0 or avg_price_local.get(c, 0) != 0)]
            if not active_coins:
                time.sleep(interval_sec)
                continue
            prices = _fetch_prices_raw(active_coins)
            # Guard: if API failed (no prices), skip this round
            if not prices:
                time.sleep(interval_sec)
                continue
            now = int(time.time())
            minute_ts = (now // 60) * 60

            # Compute totals
            portfolio_value = sum(float(prices.get(c, 0.0)) * float(holdings.get(c, 0.0)) for c in active_coins)
            total_invested = sum(float(avg_price_local.get(c, 0.0)) * float(holdings.get(c, 0.0)) for c in active_coins)
            current_pnl = portfolio_value - total_invested

            # Noise filter: skip invalid snapshots
            # - portfolio_value < 0 (invalid)
            # - portfolio_value == 0 with non-zero holdings indicates price fetch failure
            has_holdings = any(float(holdings.get(c, 0.0)) != 0 for c in active_coins)
            if portfolio_value < 0:
                time.sleep(interval_sec)
                continue
            if has_holdings and portfolio_value == 0:
                time.sleep(interval_sec)
                continue

            # Build docs for DB and local history
            docs = []
            total_entry = {"timestamp": minute_ts, "value": portfolio_value, "PNL": current_pnl}
            docs.append(total_entry)
            for c in active_coins:
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
                    "avg_price": float(avg_price_local.get(c, 0.0))
                }
                docs.append(coin_doc)

            # Local file: append if newer than last minute recorded
            try:
                existing = []
                if os.path.exists(history_file):
                    with open(history_file, "r") as f:
                        existing = json.load(f)
                # Avoid duplicate total record for the same minute
                has_same_minute = any((d.get("timestamp") == minute_ts and "coin" not in d) for d in existing)
                if not has_same_minute:
                    existing.extend(docs)
                    with open(history_file, "w") as f:
                        json.dump(existing, f)
            except Exception:
                pass

            # DB upsert
            try:
                _db_upsert_portfolio_docs(docs)
            except Exception:
                pass
        except Exception:
            pass
        time.sleep(interval_sec)


# Start background portfolio recorder once
if "_portfolio_recorder" not in st.session_state:
    try:
        t = threading.Thread(target=portfolio_recorder_background, kwargs={"interval_sec": 60}, daemon=True)
        t.start()
    except Exception:
        pass
    st.session_state["_portfolio_recorder"] = True



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

@st.cache_data(ttl=90, show_spinner=False)
def fetch_okx_ohlcv_cached(symbol: str, bar: str, limit: int = 200):
    """Cached wrapper around metrics_ohlcv_okx.fetch_okx_ohlcv_oi.
    TTL 90s to reduce network calls when switching tabs / sliders.
    """
    try:
        return metrics_ohlcv_okx.fetch_okx_ohlcv_oi(symbol=symbol, bar=bar, limit=limit)
    except Exception:
        return None

@st.cache_data(ttl=120, show_spinner=False)
def fetch_okx_liq_cached(symbol: str, limit: int = 100):
    try:
        import metrics_liquidation_okx  # local import to reduce initial load
        return metrics_liquidation_okx.fetch_okx_liquidation(symbol=symbol, limit=limit)
    except Exception:
        return None

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

@st.cache_data(ttl=120, show_spinner=False)
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
        col1, col2, col3 = st.columns(3)
        with col1:
            db_status = "🟢 Connected" if app_state["db_available"] else "🔴 Disconnected"
            st.metric("Database", db_status)
        with col2:
            api_status = "🟢 Available" if app_state["api_available"] else "🔴 Unavailable"
            st.metric("API Services", api_status)
        with col3:
            init_status = "✅ Complete" if app_state["init_complete"] else "⏳ In Progress"
            st.metric("Initialization", init_status)
        
        # Sync information
        if app_state["last_db_sync"] > 0:
            last_db = datetime.fromtimestamp(app_state["last_db_sync"]).strftime("%H:%M:%S")
            st.info(f"📊 Last DB sync: {last_db}")
        if app_state["last_api_sync"] > 0:
            last_api = datetime.fromtimestamp(app_state["last_api_sync"]).strftime("%H:%M:%S")
            st.info(f"🔄 Last API sync: {last_api}")
        
        # Background sync status
        sync_status = "🟢 Active" if app_state["background_sync_active"] else "🔴 Inactive"
        st.text(f"Background Sync: {sync_status}")
        
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
        
        # Recent errors
        if app_state["errors"]:
            st.warning("⚠️ Recent errors:")
            for error in app_state["errors"][-5:]:  # Show last 5 errors
                st.text(f"• {error}")

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
    refresh_now = st.button("Làm mới giá (bỏ qua cache)", key="refresh_prices")
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
        backend_ok = False
        # Pilot: thử gọi backend FastAPI /prices/spot trước, nếu lỗi fallback sang logic cũ
        try:
            import httpx
            api_url = st.session_state.get("_backend_price_api", "http://127.0.0.1:8000/prices/spot")
            # Gửi danh sách SYMBOL (BTC, ETH, ...) thay vì coin id (bitcoin, ethereum)
            symbols_param = ",".join([sym for _, sym in COIN_LIST])
            with httpx.Client(timeout=3.5) as client:
                resp = client.get(api_url, params={"symbols": symbols_param})
            if resp.status_code == 200:
                js = resp.json()
                backend_prices_block = js.get("prices") or {}
                prices_new = {}
                pdata_new = {}
                for symbol_key, v in backend_prices_block.items():
                    if not isinstance(v, dict):
                        continue  # backend luôn trả dict PriceSnapshot
                    coin_id_match = v.get("coin_id") or v.get("symbol")
                    if not coin_id_match:
                        continue
                    raw_price = v.get("price") or v.get("last") or v.get("value")
                    c1 = v.get("change_1d", 0)
                    c7 = v.get("change_7d", 0)
                    c30 = v.get("change_30d", 0)
                    try:
                        prices_new[coin_id_match] = float(raw_price)
                    except Exception:
                        prices_new[coin_id_match] = 0.0
                    pdata_new[coin_id_match] = {
                        "change_1d": c1 or 0,
                        "change_7d": c7 or 0,
                        "change_30d": c30 or 0
                    }
                if prices_new:
                    prices = {c: prices_new.get(c, prices.get(c, 0.0)) for c in coins}
                    price_data = {**price_data, **pdata_new}
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
                    st.session_state["_price_source"] = "api"
                    update_success = True
                    backend_ok = True
        except Exception as be:
            st.session_state["_last_backend_error"] = str(be)

        if not backend_ok:  # fallback original function
            prices_new, pdata_new, updated, msg = get_current_prices()
            if updated:
                price_data = pdata_new
                prices = {c: prices_new.get(c, 0.0) for c in coins}
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
                    st.caption(f"[DEBUG] Zero-priced coins (fallback path): {', '.join(zero_coins)} | source={st.session_state.get('_price_source','legacy')} backend_err={st.session_state.get('_last_backend_error')}")
            except Exception:
                pass
    else:
        st.warning("Đang chờ hết thời gian delay sau lỗi API CoinGecko...")

    # Không auto refresh mỗi 65s nữa -> giữ dữ liệu static cho tới khi user bấm nút refresh
    if refresh_now:
        prices_new, pdata_new, updated, msg = get_current_prices()
        if updated:
            price_data = pdata_new
            prices = {c: prices_new.get(c, 0.0) for c in coins}
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


    # --- Hiển thị tổng giá trị portfolio và thay đổi so với hôm qua ---
    metric_delta = "N/A"
    value_change = "N/A"
    value_yesterday = None
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

    # Display portfolio metric (never show 0 if holdings exist and we have prior non-zero)
    display_value = portfolio_value
    if display_value == 0 and st.session_state.get("_last_nonzero_portfolio_value", 0) > 0 and any(holdings.get(c, 0.0) > 0 for c in coins):
        display_value = st.session_state["_last_nonzero_portfolio_value"]

    cached_note = ""
    if st.session_state.get("_bootstrap_source") == "db" and display_value > 0 and not update_success:
        cached_note = " (db cached)"
    elif not update_success and prices is st.session_state.get("_last_prices") and any(holdings.get(c, 0.0) > 0 for c in coins):
        cached_note = " (cached)"
    elif st.session_state.get("_price_source") == "api" and update_success:
        cached_note = " (API)"
    if metric_delta != "N/A" and value_change != "N/A" and value_yesterday is not None:
        st.metric(
            f"💰 Tổng giá trị Portfolio (USD){cached_note}",
            f"{display_value:,.2f}",
            delta=f"{metric_delta} | {value_change:,.2f} USD",
            delta_color="normal"
        )
    else:
        st.metric(f"💰 Tổng giá trị Portfolio (USD){cached_note}", f"{display_value:,.2f}", delta="N/A | N/A")

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
    df = pd.DataFrame(data)

    # Tính lại các cột sau khi nhập
    df_input = df.copy()
    for idx, row in df_input.iterrows():
        coin = coins[idx]
        # Lấy dữ liệu mới nhất từ session nếu có
        df_input.at[idx, "Số token nắm giữ"] = st.session_state["holdings"].get(coin, 0.0)
        df_input.at[idx, "Giá mua trung bình"] = st.session_state["avg_price"].get(coin, 0.0)
    df_input["Tổng giá trị"] = df_input["Số token nắm giữ"] * df_input["Giá hiện tại"]
    def _pnl_row(row):
        amt = row["Số token nắm giữ"]
        avgc = row["Giá mua trung bình"]
        price_now = row["Giá hiện tại"]
        if amt >= 0:
            return price_now * amt - avgc * amt
        # position âm: coi như short => PNL = (avg_cost - current_price)*abs(amt)
        return (avgc - price_now) * abs(amt)
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
    df_input["% Profit/Loss"] = df_input.apply(_pct_pl, axis=1)
    df_input["% Hòa vốn"] = np.where(df_input["Profit & Loss"] >= 0, 0.0, 100 * -df_input["Profit & Loss"] / (df_input["Giá mua trung bình"] * df_input["Số token nắm giữ"] + 1e-9))

    # Chỉ hiển thị 1 bảng duy nhất: nhập liệu và có màu cho các cột tính toán
    def color_profit(val):
        if val > 0:
            return 'color: green;'
        elif val < 0:
            return 'color: red;'
        else:
            return ''

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

    # (Không auto-sync bảng vào holdings/avg_price. Chỉ cập nhật khi bấm nút 'Đẩy dữ liệu lên DB'.)

    # Tạo bảng kết quả với các cột tính toán và màu sắc
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
    st.dataframe(styled_result, hide_index=True)

    # (Đã bỏ nút 'Nhâp liệu mới' trùng key để tránh StreamlitDuplicateElementKey)

    # --- TÍNH VÀ HIỂN THỊ CHART, METRIC, PIE/BAR CHART ---
    # Lọc chỉ các entry tổng portfolio (không có key 'coin') cho chart tổng
    df_hist = pd.DataFrame([h for h in history if 'coin' not in h])
    metric_delta = ""
    metric_delta_pnl = ""
    metric_delta_profit = ""
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

        show_portfolio_over_time_chart(history, key="main_line_chart")
        show_pie_distribution(result_df)
        show_bar_pnl(result_df)
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

    # Lưu các metric tổng hợp vào session_state để tab2 dùng
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
                if snap and snap.get('bar') == bar and set(snap.get('coins', [])) == set(coins):
                    return snap['data'], st.session_state.get('_okx_prefetch_stats', {})
                success = 0
                failed = []
                data_map: dict[str, pd.DataFrame] = {}
                for c in coins:
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
                        failed = [coin_id_to_name[c] for c in coins if c not in data_map]
                stats = {
                    'bar': bar,
                    'success': success,
                    'total': len(coins),
                    'failed_symbols': failed,
                    'used_cache_file': used_cache_file,
                    'timestamp': time.time()
                }
                st.session_state['_ohlcv_snapshot_all'] = {
                    'data': data_map,
                    'bar': bar,
                    'coins': list(coins),
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
                            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1)
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
        # Load generic events
        raw_events = load_whales_for_symbol(coin_symbol)
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

# Per-coin tabs: tái tạo loop hiển thị OHLCV + overlay whale (unified)
for idx, coin_tuple in enumerate(COIN_LIST):
    coin_id, coin_symbol = coin_tuple
    # Bỏ qua nếu không tồn tại tab (phòng trường hợp user filter coin)
    if idx >= len(tab_coin_tabs):
        continue
    with tab_coin_tabs[idx]:
        st.subheader(f"📌 {coin_symbol} - Tổng quan")
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
            try:
                import metrics_liquidation_okx
                df_liq = fetch_okx_liq_cached(symbol=f"{coin_symbol}-USDT-SWAP", limit=120)
                if df_liq is not None and not (hasattr(df_liq, 'empty') and df_liq.empty):
                    try:
                        fig_liq = metrics_liquidation_okx.plot_liquidation_heatmap(df_liq)
                        st.plotly_chart(
                            fig_liq,
                            width='stretch',
                            key=f"liq_{coin_symbol}",
                            config={'displaylogo': False, 'responsive': True}
                        )
                    except Exception as _liq_ex:
                        st.caption(f"Không vẽ được heatmap: {_liq_ex}")
                else:
                    st.caption("Không có dữ liệu liquidation.")
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
                        st.plotly_chart(fig_on, use_container_width=True, config={'displaylogo': False, 'responsive': True})
                    else:
                        st.caption("Không có cột on-chain hiển thị được.")
                # MVRV (sử dụng file sample nếu có)
                try:
                    import metrics_mvrv_z as _mvrv
                    mvrv_fig = _mvrv.plot_mvrv_z_score(coin_id=coin_id)
                    if mvrv_fig:
                        st.plotly_chart(mvrv_fig, use_container_width=True, config={'displaylogo': False, 'responsive': True})
                except Exception:
                    pass
            except Exception as _on_ex:
                st.caption(f"On-chain metrics error: {_on_ex}")

        # === Whale Large Transactions box (restored feature) ===
        with st.expander(f"🐳 {coin_symbol} Large Transactions", expanded=False):
            try:
                from services.whale.whale_loader import load_whales_for_symbol as _lwf, to_dataframe as _wh_df
                events = _lwf(coin_symbol) if load_whales_for_symbol else []
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





