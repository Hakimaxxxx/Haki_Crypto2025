
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
        if not db.available():
            return
        if holdings is not None:
            db.set_kv("portfolio_meta", "holdings", holdings)
        if avg_price is not None:
            db.set_kv("portfolio_meta", "avg_price", avg_price)
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
                    with st.spinner("Reconnecting to database..."):
                        success = db.force_reconnect()
                        if success:
                            st.success("✅ Database reconnected successfully!")
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
                # Do not change invested/current_pnl; recompute with preserved prices
                prices = st.session_state["_last_prices"]
                price_data = st.session_state["_last_price_data"]
                total_invested_now = st.session_state["_last_total_invested_now"]
                current_pnl = portfolio_value - total_invested_now
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
    df_input["Profit & Loss"] = df_input["Tổng giá trị"] - df_input["Giá mua trung bình"] * df_input["Số token nắm giữ"]
    df_input["% Profit/Loss"] = np.where(
        df_input["Giá mua trung bình"] > 0,
        100 * df_input["Profit & Loss"] / (df_input["Giá mua trung bình"] * df_input["Số token nắm giữ"] + 1e-9),
        0.0
    )
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

        st.markdown("#### Nhập giao dịch mua mới để tự động cập nhật giá mua trung bình")
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

    # Tính toán lại các cột sau khi nhập
    for idx, row in edited_df.iterrows():
        coin = coins[idx]
        holdings[coin] = row["Số token nắm giữ"]
        avg_price[coin] = row["Giá mua trung bình"]
    # Debounce saving: only persist if changed checksum
    import json, hashlib
    def _checksum(obj):
        try:
            return hashlib.md5(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()
        except Exception:
            return str(obj)
    new_holdings_sum = _checksum(holdings)
    new_avg_sum = _checksum(avg_price)
    prev_holdings_sum = st.session_state.get("_holdings_checksum")
    prev_avg_sum = st.session_state.get("_avg_price_checksum")
    st.session_state["holdings"] = holdings
    st.session_state["avg_price"] = avg_price
    if new_holdings_sum != prev_holdings_sum:
        save_holdings(holdings)
        st.session_state["_holdings_checksum"] = new_holdings_sum
    if new_avg_sum != prev_avg_sum:
        save_avg_price(avg_price)
        st.session_state["_avg_price_checksum"] = new_avg_sum

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
    result_df["Tổng giá trị"] = result_df["Số token nắm giữ"] * result_df["Giá hiện tại"]
    result_df["Profit & Loss"] = result_df["Tổng giá trị"] - result_df["Giá mua trung bình"] * result_df["Số token nắm giữ"]
    result_df["% Profit/Loss"] = np.where(
        result_df["Giá mua trung bình"] > 0,
        100 * result_df["Profit & Loss"] / (result_df["Giá mua trung bình"] * result_df["Số token nắm giữ"] + 1e-9),
        0.0
    )
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
                        loaded_at = datetime.utcfromtimestamp(ts_loaded).strftime('%H:%M:%S UTC') if ts_loaded else ''
                        suffix = "(snapshot file)" if stats.get('used_cache_file') else ""
                        fig.update_layout(
                            title=f"Tăng trưởng (%) tất cả coin (OKX 30m - snapshot) {suffix} | Loaded {loaded_at}",
                            xaxis_title="Thời gian",
                            yaxis_title="% Tăng trưởng",
                            hovermode='x unified',
                            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1)
                        )
                        st.plotly_chart(fig, use_container_width=True)

    # --- Health Panel ---
    # Lấy độ dài queue DB (thông qua biến trong db_utils - tạm không public nên dùng try) và timestamp cập nhật giá gần nhất
    try:
        from db_utils import get_db_queue_info  # type: ignore
        qinfo = get_db_queue_info()
        queue_len = qinfo["queue_length"]
    except Exception:
        queue_len = 0
        qinfo = {"queue_length":0, "consecutive_failures":0, "retry_interval":0, "next_retry_in":0}
    # Giá trị cập nhật cuối cùng đã lưu trong session
    last_price_ts = int(st.session_state.get("_last_portfolio_value_ts", 0)) if "_last_portfolio_value" in st.session_state else 0
    # Thử flush queue DB thường xuyên hơn nếu đã có kết nối trở lại
    if db.available():
        try:
            db_retry_queue(db)
        except Exception:
            pass
    db_status_msg = "Price cache active"
    if not db.available():
        last_err = getattr(db, 'last_error', lambda: None)()
        db_status_msg = "DB unavailable – auto retry 30s" + (f" | {last_err}" if last_err else "")
    elif queue_len > 0:
        db_status_msg = (
            f"Queue: {queue_len} | next retry in {qinfo['next_retry_in']}s | fail x{qinfo['consecutive_failures']}"
        )
    show_health_panel(db, queue_len, last_price_ts, last_price_update_message=db_status_msg)

with tab2:
    st.title("📈 Metric")
    st.info("Các metric thị trường tổng quan:")
    # Metric 1: Crypto Fear & Greed Index
    import metrics_fear_greed
    metrics_fear_greed.show_fear_greed_metric()
    import metrics_dominance
    metrics_dominance.show_dominance_metric()

    # --- Market Cap & Volume Chart ---
    import metrics_marketcap_volume
    metrics_marketcap_volume.show_marketcap_volume_chart(key_suffix="_main")
    for idx, coin in enumerate(COIN_LIST):
        with tab_coin_tabs[idx]:
            # Lấy link logo từ CoinGecko
            logo_url = price_data.get(coin[0], {}).get('image', '')
            current_price = prices.get(coin[0], 0.0)
            price_str = f"<span style='font-size:1.2rem;font-weight:normal;color:#3df78a;'>${current_price:,.2f}</span>" if current_price else ""
            # Luôn dùng markdown để tránh hiển thị thô chuỗi HTML (tránh lỗi thấy <span ...> xuất hiện)
            if not logo_url:
                # Fallback logo đơn giản (data URI hình tròn xám) để đồng bộ layout
                logo_url = "https://via.placeholder.com/36/cccccc/000000?text=?"
            try:
                st.markdown(
                    (
                        "<div style='display:flex;align-items:center;gap:10px;'>"
                        f"<img src='{logo_url}' width='36' style='vertical-align:middle;border-radius:50%;border:1px solid #ccc;'/>"
                        f" <span style='font-size:2rem;font-weight:bold'>{coin[1]} ({coin[0].capitalize()}) {price_str}</span>"
                        "</div>"
                    ),
                    unsafe_allow_html=True,
                )
            except Exception:
                # Fallback cuối cùng: hiển thị plain text (không HTML) nếu có lỗi render
                st.header(f"{coin[1]} ({coin[0].capitalize()}) - ${current_price:,.2f}")

            # --- Hiển thị tổng giá trị và PNL từng coin (format đẹp) ---
            coin_id = coin[0]
            coin_name = coin[1]
            amount = holdings.get(coin_id, 0.0)
            price = prices.get(coin_id, 0.0)
            avg = avg_price.get(coin_id, 0.0)
            total = amount * price
            invested = amount * avg
            pnl = total - invested
            pnl_pct = (pnl / invested * 100) if invested > 0 else 0
            st.markdown(f"<div style='font-size:2rem;font-weight:bold;text-transform:uppercase;'>TOTAL: {total:,.2f} USD</div>", unsafe_allow_html=True)
            pnl_color = 'green' if pnl >= 0 else 'red'
            st.markdown(f"<div style='font-size:1.2rem;font-weight:bold;color:{pnl_color};'>PNL: {'+' if pnl >= 0 else ''}{pnl:,.2f} ({'+' if pnl_pct >= 0 else ''}{pnl_pct:.2f}%)</div>", unsafe_allow_html=True)
            st.info(f"Tab này dành riêng cho các metric, biểu đồ, thông tin liên quan đến {coin[1]}.")

            # Hiển thị metric MVRV-Z cho ETH và Realized Price cho BTC
            import metrics_mvrv_z
            if coin[1] == "ETH":
                metrics_mvrv_z.show_mvrv_z_metric("ethereum", "ETH")
            # --- On-chain metrics (Lazy load qua expander) ---
            import pandas as pd
            import plotly.graph_objects as go
            # def _render_onchain(asset, asset_name, days=365):
            #     df = load_onchain_metrics_cached(asset, days)
            #     if df is None or df.empty:
            #         st.info(f"Không có dữ liệu on-chain cho {asset_name}.")
            #         return
            #     last = df.iloc[-1]
            #     cols = st.columns(4)
            #     def safe_metric(val, fmt, default="N/A"):
            #         try:
            #             if pd.isna(val):
            #                 return default
            #             return fmt.format(val)
            #         except Exception:
            #             return default
            #     with cols[0]:
            #         st.markdown(f"<div style='font-size:13px;'>Giá {asset_name} (USD)<br><b>{safe_metric(last.get('PriceUSD'), '${:,.2f}')}</b></div>", unsafe_allow_html=True)
            #         st.markdown(f"<div style='font-size:13px;'>Địa chỉ active<br><b>{safe_metric(last.get('AdrActCnt'), '{:,.0f}')}</b></div>", unsafe_allow_html=True)
            #     with cols[1]:
            #         st.markdown(f"<div style='font-size:13px;'>Số giao dịch<br><b>{safe_metric(last.get('TxCnt'), '{:,.0f}')}</b></div>", unsafe_allow_html=True)
            #         st.markdown(f"<div style='font-size:13px;'>Tổng phí giao dịch<br><b>{safe_metric(last.get('FeeTotUSD'), '${:,.2f}')}</b></div>", unsafe_allow_html=True)
            #     with cols[2]:
            #         st.markdown(f"<div style='font-size:13px;'>Coin mới phát hành<br><b>{safe_metric(last.get('IssTotUSD'), '${:,.2f}')}</b></div>", unsafe_allow_html=True)
            #         st.markdown(f"<div style='font-size:13px;'>Số block/ngày<br><b>{safe_metric(last.get('BlkCnt'), '{:,.0f}')}</b></div>", unsafe_allow_html=True)
            #     with cols[3]:
            #         st.markdown(f"<div style='font-size:13px;'>Hashrate TB<br><b>{safe_metric(last.get('HashRate'), '{:,.2f}')}</b></div>", unsafe_allow_html=True)
            #         st.markdown(f"<div style='font-size:13px;'>Độ khó TB<br><b>{safe_metric(last.get('DiffMean'), '{:,.2f}')}</b></div>", unsafe_allow_html=True)
            #     fig = go.Figure()
            #     if 'PriceUSD' in df.columns:
            #         fig.add_trace(go.Scatter(x=df['date'], y=df['PriceUSD'], name=f'Giá {asset_name} (USD)', line=dict(color='blue')))
            #     if 'AdrActCnt' in df.columns:
            #         fig.add_trace(go.Scatter(x=df['date'], y=df['AdrActCnt'], name='Địa chỉ active', line=dict(color='orange')))
            #     if 'TxCnt' in df.columns:
            #         fig.add_trace(go.Scatter(x=df['date'], y=df['TxCnt'], name='Số giao dịch', line=dict(color='green')))
            #     if 'FeeTotUSD' in df.columns:
            #         fig.add_trace(go.Scatter(x=df['date'], y=df['FeeTotUSD'], name='Tổng phí giao dịch', line=dict(color='red')))
            #     fig.update_layout(
            #         title=f"{asset_name} On-chain Metrics (Community API)",
            #         xaxis=dict(title="Date"),
            #         yaxis=dict(title="Giá trị / Số lượng", side="left"),
            #         legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            #     )
            #     st.plotly_chart(fig, use_container_width=True)

            # perf_mode = st.session_state.get("_perf_mode", True)
            # with st.expander("🔗 On-chain Metrics (nhấn để tải)", expanded=False):
            #     if perf_mode:
            #         # Performance mode: user phải nhấn nút để tránh load tự động nhiều coin
            #         if st.button("Tải dữ liệu on-chain", key=f"btn_onchain_{coin[0]}"):
            #             _render_onchain(coin[0], coin[1])
            #     else:
            #         # Non-performance: tự động render khi mở expander
            #         _render_onchain(coin[0], coin[1])

            # --- Hiển thị heatmap liquidation OKX cho mọi coin ---
            symbol = f"{coin[1]}-USDT-SWAP"
            st.subheader(f"Heatmap Liquidation OKX ({symbol})")
            df_liq = fetch_okx_liq_cached(symbol=symbol, limit=100)
            try:
                import metrics_liquidation_okx
                fig_liq = metrics_liquidation_okx.plot_liquidation_heatmap(df_liq, symbol=symbol)
            except Exception:
                fig_liq = None
            if fig_liq:
                st.plotly_chart(fig_liq, use_container_width=True)
            else:
                st.info("Không có dữ liệu liquidation từ OKX.")

            # --- Chart Portfolio Value, PNL & % Profit & Loss Over Time cho từng coin ---
            import plotly.graph_objects as go
            import numpy as np
            import pytz
            tz_gmt7 = pytz.timezone("Asia/Bangkok")
            # Đọc lịch sử portfolio
            HISTORY_FILE = "portfolio_history.json"
            # Cached portfolio history load
            history = load_portfolio_history_cached(HISTORY_FILE)
            # Lọc lịch sử cho coin này
            df_hist = pd.DataFrame([h for h in history if h.get("coin") == coin[0]])
            if not df_hist.empty:
                df_hist["Date"] = pd.to_datetime(df_hist["timestamp"], unit="s").dt.tz_localize("UTC").dt.tz_convert(tz_gmt7)
                df_hist = df_hist.sort_values("Date")
                # Tính toán các chỉ số
                df_hist["PNL"] = df_hist["value"] - df_hist["invested"]
                df_hist["% Profit & Loss"] = np.where(
                    df_hist["value"] > 0,
                    df_hist["PNL"] / (df_hist["value"] + 1e-9) * 100,
                    0.0
                )
                # Option enable/disable từng dòng trên chart
                chart_options = st.multiselect(
                    "Chọn dòng muốn hiển thị trên chart:",
                    ["Portfolio Value", "PNL", "% Profit & Loss"],
                    default=["Portfolio Value", "PNL", "% Profit & Loss"],
                    key=f"chart_lines_{coin[0]}"
                )
                fig = go.Figure()
                if "Portfolio Value" in chart_options:
                    # Chuyển sang GMT+7 khi hiển thị
                    x_gmt7 = df_hist["Date"].dt.tz_convert(tz_gmt7)
                    fig.add_trace(go.Scatter(x=x_gmt7, y=df_hist["value"], name="Portfolio Value", yaxis="y1", line=dict(color="royalblue"), visible=True))
                    if "PNL" in chart_options:
                        fig.add_trace(go.Scatter(x=x_gmt7, y=df_hist["PNL"], name="PNL", yaxis="y1", line=dict(color="orange"), visible=True))
                    if "% Profit & Loss" in chart_options:
                        fig.add_trace(go.Scatter(x=x_gmt7, y=df_hist["% Profit & Loss"], name="% Profit & Loss", yaxis="y2", line=dict(color="green"), visible=True))
                fig.update_layout(
                    title=f"{coin[1]} Portfolio Value, PNL & % Profit & Loss Over Time (GMT+7)",
                    xaxis=dict(title="Date (GMT+7)"),
                    yaxis=dict(title="Portfolio Value / PNL (USD)", side="left"),
                    yaxis2=dict(title="% Profit & Loss", overlaying="y", side="right", showgrid=False),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                )
                st.plotly_chart(fig, use_container_width=True, key=f"line_chart_{coin[0]}")
            else:
                st.info("Chưa có lịch sử portfolio cho coin này.")
            # --- Hiển thị chart giá & volume OKX với lựa chọn timeframe ---
            import metrics_ohlcv_okx
            khung_list = [
                ("5m", "5 phút"),
                ("15m", "15 phút"),
                ("30m", "30 phút"),
                ("1H", "1 giờ")
            ]
            bar_options = {label: bar for bar, label in khung_list}
            bar_label = st.selectbox(
                f"Chọn khung thời gian giá/volume OKX cho {coin[1]}",
                list(bar_options.keys()),
                index=2,  # mặc định 30 phút
                key=f"ohlcv_bar_{coin[1]}"
            )
            bar = bar_options[bar_label]

            st.subheader(f"Giá & Volume OKX ({coin[1]}-USDT-SWAP, {bar_label})")

            try:
                df_ohlcv = fetch_okx_ohlcv_cached(symbol=f"{coin[1]}-USDT-SWAP", bar=bar, limit=200)
            except Exception as e:
                import requests
                if isinstance(e, requests.exceptions.ProxyError):
                    st.warning(f"Không thể lấy dữ liệu OKX cho {coin[1]}-USDT-SWAP do lỗi proxy: {e}")
                    df_ohlcv = None
                else:
                    st.warning(f"Lỗi lấy dữ liệu OKX cho {coin[1]}-USDT-SWAP: {e}")
                    df_ohlcv = None
            fig_ohlcv = metrics_ohlcv_okx.plot_price_volume_chart(df_ohlcv, symbol=f"{coin[1]}-USDT-SWAP")

            # Chuẩn hóa cột thời gian của df_ohlcv sang UTC nếu chưa có tz
            if df_ohlcv is not None and not df_ohlcv.empty and "datetime" in df_ohlcv.columns:
                if not isinstance(df_ohlcv["datetime"].dtype, pd.DatetimeTZDtype):
                    df_ohlcv["datetime"] = pd.to_datetime(df_ohlcv["datetime"]).dt.tz_localize("UTC")
            fig_to_show = fig_ohlcv
            # Whale Alert cho ETH: overlay vào fig_ohlcv nếu là ETH
            if coin[1] == "ETH" and fig_ohlcv and not df_ohlcv.empty:
                from overlay_whale_alert import overlay_whale_alert_chart
                from ERC20.metrics_erc20_whale_alert_realtime import ERC20_TOKENS, show_erc20_whale_alert_realtime
                eth_token = [t for t in ERC20_TOKENS if t['name'] == 'ETH'][0]
                whale_txs = []
                try:
                    import json
                    with open(eth_token['history_file'], 'r') as f:
                        whale_txs = json.load(f)
                except:
                    pass
                st.session_state[f"fig_ohlcv_ETH"] = fig_ohlcv
                overlay_whale_alert_chart(
                    whale_txs=whale_txs,
                    df_ohlcv=df_ohlcv,
                    coin_symbol="ETH",
                    slider_label="Lọc theo độ lớn giao dịch Whale (ETH)",
                    slider_step=0.1,
                    value_unit="ETH",
                    type_map={"BUY": "MUA", "SELL": "BÁN", "N/A": "Khác"},
                        color_map={"BUY": "#43a047", "SELL": "#e53935", "N/A": "#fbc02d"},
                    default_show=True,
                    key_prefix="eth_"
                )
            if coin[1] == "ETH":
                from ERC20.metrics_erc20_whale_alert_realtime import ERC20_TOKENS, show_erc20_whale_alert_realtime
                eth_token = [t for t in ERC20_TOKENS if t['name'] == 'ETH'][0]
                show_erc20_whale_alert_realtime(eth_token)
            
            # Whale Alert cho SOL
            if coin[1] == "SOL":
                from overlay_whale_alert import overlay_whale_alert_chart
                from SOL import metrics_sol_whale_alert_realtime
                if metrics_sol_whale_alert_realtime:
                    metrics_sol_whale_alert_realtime.mark_sol_whale_alert_seen()
                    whale_txs = metrics_sol_whale_alert_realtime.load_whale_history()
                else:
                    whale_txs = []
                # Chuẩn hóa cột thời gian của df_ohlcv sang UTC nếu chưa có tz
                if df_ohlcv is not None and not df_ohlcv.empty and "datetime" in df_ohlcv.columns:
                    if not isinstance(df_ohlcv["datetime"].dtype, pd.DatetimeTZDtype):
                        df_ohlcv["datetime"] = pd.to_datetime(df_ohlcv["datetime"]).dt.tz_localize("UTC")
                # Kiểm tra dữ liệu df_ohlcv và whale_txs cho SOL
                error_msgs = []
                if df_ohlcv is None or df_ohlcv.empty:
                    error_msgs.append("❌ df_ohlcv cho SOL bị thiếu hoặc rỗng!")
                elif "datetime" not in df_ohlcv.columns or "close" not in df_ohlcv.columns:
                    error_msgs.append("❌ df_ohlcv cho SOL thiếu cột 'datetime' hoặc 'close'!")
                if not whale_txs:
                    error_msgs.append("❌ whale_txs cho SOL bị rỗng!")
                else:
                    # Kiểm tra định dạng time
                    for tx in whale_txs:
                        if "time" not in tx:
                            error_msgs.append("❌ Một số whale_txs thiếu trường 'time'!")
                            break
                if error_msgs:
                    st.warning("\n".join(error_msgs))
                st.session_state[f"fig_ohlcv_SOL"] = fig_ohlcv
                overlay_whale_alert_chart(
                    whale_txs=whale_txs,
                    df_ohlcv=df_ohlcv,
                    coin_symbol="SOL",
                    slider_label="Lọc theo độ lớn giao dịch Whale (SOL)",
                    slider_step=1.0,
                    value_unit="SOL",
                    type_map={"BUY": "MUA", "SELL": "BÁN", "N/A": "Khác"},
                    color_map={"BUY": "#43a047", "SELL": "#e53935", "N/A": "#fbc02d"},
                    default_show=True,
                    key_prefix="sol_"
                )
            # Whale Alert cho BTC: overlay bóng Whale lên chart nếu có whale_txs
            if coin[1] == "BTC" and fig_ohlcv and not df_ohlcv.empty:
                from overlay_whale_alert import overlay_whale_alert_chart
                from BTC import metrics_btc_whale_alert_realtime
                whale_txs = metrics_btc_whale_alert_realtime.load_whale_history()
                # Chuẩn hóa cột thời gian của df_ohlcv sang GMT+7 nếu chưa có tz
                if df_ohlcv is not None and not df_ohlcv.empty and "datetime" in df_ohlcv.columns:
                    if not isinstance(df_ohlcv["datetime"].dtype, pd.DatetimeTZDtype):
                        df_ohlcv["datetime"] = pd.to_datetime(df_ohlcv["datetime"]).dt.tz_localize("UTC").dt.tz_convert(tz_gmt7)
                st.session_state[f"fig_ohlcv_BTC"] = fig_ohlcv
                overlay_whale_alert_chart(
                    whale_txs=whale_txs,
                    df_ohlcv=df_ohlcv,
                    coin_symbol="BTC",
                    slider_label="Lọc theo độ lớn giao dịch Whale (BTC)",
                    slider_step=1.0,
                    value_unit="BTC",
                    type_map={"BUY": "MUA", "SELL": "BÁN", "N/A": "Khác"},
                    color_map={"BUY": "#43a047", "SELL": "#e53935", "N/A": "#fbc02d"},
                    default_show=True,
                    key_prefix="btc_"
                )
            # Whale Alert cho BNB: overlay markers (giống LINK/SOL/BTC)
            if coin[1] == "BNB" and fig_ohlcv and not df_ohlcv.empty:
                from overlay_whale_alert import overlay_whale_alert_chart
                from BNB import metrics_bnb_whale_alert_realtime
                whale_txs = metrics_bnb_whale_alert_realtime.load_whale_history()
                # Chuẩn hóa cột thời gian df_ohlcv sang UTC nếu chưa có tz
                if df_ohlcv is not None and not df_ohlcv.empty and "datetime" in df_ohlcv.columns:
                    if not isinstance(df_ohlcv["datetime"].dtype, pd.DatetimeTZDtype):
                        df_ohlcv["datetime"] = pd.to_datetime(df_ohlcv["datetime"]).dt.tz_localize("UTC")
                st.session_state[f"fig_ohlcv_BNB"] = fig_ohlcv
                overlay_whale_alert_chart(
                    whale_txs=whale_txs,
                    df_ohlcv=df_ohlcv,
                    coin_symbol="BNB",
                    slider_label="Lọc theo độ lớn giao dịch Whale (BNB)",
                    slider_step=10.0,
                    value_unit="BNB",
                    type_map={"BUY": "MUA", "SELL": "BÁN", "N/A": "Khác"},
                    color_map={"BUY": "#43a047", "SELL": "#e53935", "N/A": "#fbc02d"},
                    default_show=True,
                    key_prefix="bnb_"
                )
            # Hiển thị box Whale Alert BTC
            if coin[1] == "BTC":
                from BTC import metrics_btc_whale_alert_realtime
                metrics_btc_whale_alert_realtime.show_btc_whale_alert_realtime()
            if coin[1] == "SOL" and metrics_sol_whale_alert_realtime:
                metrics_sol_whale_alert_realtime.show_sol_whale_alert_realtime()
            # Whale Alert cho LINK: overlay markers, slider, box (thực hiện TRƯỚC khi vẽ chart)
            if coin[1] == "LINK" and fig_ohlcv and not df_ohlcv.empty:
                from overlay_whale_alert import overlay_whale_alert_chart
                from ERC20.metrics_erc20_whale_alert_realtime import ERC20_TOKENS, show_erc20_whale_alert_realtime
                link_token = [t for t in ERC20_TOKENS if t['name'] == 'LINK'][0]
                whale_txs = []
                try:
                    import json
                    with open(link_token['history_file'], 'r') as f:
                        whale_txs = json.load(f)
                except:
                    pass
                # Chuẩn hóa cột thời gian của df_ohlcv sang UTC nếu chưa có tz
                if df_ohlcv is not None and not df_ohlcv.empty and "datetime" in df_ohlcv.columns:
                    if not isinstance(df_ohlcv["datetime"].dtype, pd.DatetimeTZDtype):
                        df_ohlcv["datetime"] = pd.to_datetime(df_ohlcv["datetime"]).dt.tz_localize("UTC")
                st.session_state[f"fig_ohlcv_LINK"] = fig_ohlcv
                overlay_whale_alert_chart(
                    whale_txs=whale_txs,
                    df_ohlcv=df_ohlcv,
                    coin_symbol="LINK",
                    slider_label="Lọc theo độ lớn giao dịch Whale (LINK)",
                    slider_step=100.0,
                    value_unit="LINK",
                    type_map={"BUY": "MUA", "SELL": "BÁN", "N/A": "Khác"},
                    color_map={"BUY": "#43a047", "SELL": "#e53935", "N/A": "#fbc02d"},
                    default_show=True,
                    key_prefix="link_"
                )
            if coin[1] == "LINK":
                from ERC20.metrics_erc20_whale_alert_realtime import ERC20_TOKENS, show_erc20_whale_alert_realtime
                link_token = [t for t in ERC20_TOKENS if t['name'] == 'LINK'][0]
                show_erc20_whale_alert_realtime(link_token)
            # Hiển thị box Whale Alert BNB
            if coin[1] == "BNB":
                from BNB import metrics_bnb_whale_alert_realtime
                metrics_bnb_whale_alert_realtime.show_bnb_whale_alert_realtime()
            # Vẽ chart SAU khi đã overlay để đảm bảo marker hiển thị
            if fig_ohlcv:
                st.plotly_chart(fig_ohlcv, use_container_width=True, key=f"plotly_chart_{coin[1]}")
            else:
                st.info(f"Không có dữ liệu giá/volume từ OKX cho khung {bar_label}.")


# Tự động refresh mỗi 60 giây
st.experimental_rerun = getattr(st, "experimental_rerun", None)  # compatibility
st_autorefresh = getattr(st, "autorefresh", None)
if st_autorefresh:
    st_autorefresh(interval=60 * 1000, key="refresh")  # 1 phút

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
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump(history, f)
    except Exception as e:
        st.warning(f"Không thể lưu lịch sử portfolio: {e}")

# Hàm load holdings từ file
def load_holdings():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                data = json.load(f)
            for c in coin_ids:
                if c not in data:
                    data[c] = 0.0
            return data
        except Exception:
            pass
    return {c: 0.0 for c in coin_ids}

# Hàm load giá mua trung bình từ file
def load_avg_price():
    if os.path.exists(AVG_PRICE_FILE):
        try:
            with open(AVG_PRICE_FILE, "r") as f:
                data = json.load(f)
            for c in coin_ids:
                if c not in data:
                    data[c] = 0.0
            return data
        except Exception:
            pass
    return {c: 0.0 for c in coin_ids}

# Hàm lưu giá mua trung bình vào file
def save_avg_price(avg_price):
    try:
        with open(AVG_PRICE_FILE, "w") as f:
            json.dump(avg_price, f)
        _db_set_portfolio_meta(avg_price=avg_price)
    except Exception as e:
        st.warning(f"Không thể lưu giá mua trung bình: {e}")

# Hàm lưu holdings vào file
def save_holdings(holdings):
    try:
        with open(DATA_FILE, "w") as f:
            json.dump(holdings, f)
        _db_set_portfolio_meta(holdings=holdings)
    except Exception as e:
        st.warning(f"Không thể lưu dữ liệu: {e}")











    # --- BẢNG NHẬP DỮ LIỆU KIỂU EXCEL ---
    st.subheader("Bảng quản lý Portfolio")

    # Load dữ liệu holdings và giá mua trung bình
    if "holdings" not in st.session_state:
        st.session_state["holdings"] = load_holdings()
    if "avg_price" not in st.session_state:
        st.session_state["avg_price"] = load_avg_price()
    holdings = st.session_state["holdings"]
    avg_price = st.session_state["avg_price"]

    # Lấy giá và % thay đổi (cache 60s)
    if "coingecko_429" not in st.session_state:
        st.session_state["coingecko_429"] = False
    price_data = get_prices_and_changes(coins)
    if st.session_state["coingecko_429"]:
        st.warning("Bạn đã gửi quá nhiều yêu cầu tới CoinGecko. Vui lòng thử lại sau 1 phút hoặc giảm tần suất làm mới trang.")
        st.session_state["coingecko_429"] = False
    prices = {c: price_data.get(c, {}).get("price", 0) for c in coins}

    # --- Lưu lịch sử giá trị portfolio và PNL mỗi phút ---
    now = int(time.time())
    portfolio_value = sum(prices[c] * st.session_state["holdings"].get(c, 0.0) for c in coins)
    total_invested_now = sum(st.session_state["avg_price"].get(c, 0.0) * st.session_state["holdings"].get(c, 0.0) for c in coins)
    current_pnl = portfolio_value - total_invested_now
    history = load_portfolio_history()
    # Lưu mỗi phút 1 lần (theo timestamp phút)
    if len(history) == 0 or now // 60 > history[-1]["timestamp"] // 60:
        # Nếu đã có PNL trong dict thì giữ, nếu chưa thì thêm
        entry = {"timestamp": now, "value": portfolio_value, "PNL": current_pnl}
        history.append(entry)
        save_portfolio_history(history)

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
    df_input["Profit & Loss"] = df_input["Tổng giá trị"] - df_input["Giá mua trung bình"] * df_input["Số token nắm giữ"]
    df_input["% Profit/Loss"] = np.where(
        df_input["Giá mua trung bình"] > 0,
        100 * df_input["Profit & Loss"] / (df_input["Giá mua trung bình"] * df_input["Số token nắm giữ"] + 1e-9),
        0.0
    )
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

        st.markdown("#### Nhập giao dịch mua mới để tự động cập nhật giá mua trung bình")
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

    # Tính toán lại các cột sau khi nhập
    for idx, row in edited_df.iterrows():
        coin = coins[idx]
        holdings[coin] = row["Số token nắm giữ"]
        avg_price[coin] = row["Giá mua trung bình"]
    st.session_state["holdings"] = holdings
    st.session_state["avg_price"] = avg_price
    save_holdings(holdings)
    save_avg_price(avg_price)

    # Tạo bảng kết quả với các cột tính toán và màu sắc
    result_df = edited_df.copy()
    result_df["Giá hiện tại"] = [prices.get(c, 0) for c in coins]
    result_df["% 1D"] = [price_data.get(c, {}).get("change_1d", 0) for c in coins]
    result_df["% 7D"] = [price_data.get(c, {}).get("change_7d", 0) for c in coins]
    result_df["% 30D"] = [price_data.get(c, {}).get("change_30d", 0) for c in coins]
    result_df["Tổng giá trị"] = result_df["Số token nắm giữ"] * result_df["Giá hiện tại"]
    result_df["Profit & Loss"] = result_df["Tổng giá trị"] - result_df["Giá mua trung bình"] * result_df["Số token nắm giữ"]
    result_df["% Profit/Loss"] = np.where(
        result_df["Giá mua trung bình"] > 0,
        100 * result_df["Profit & Loss"] / (result_df["Giá mua trung bình"] * result_df["Số token nắm giữ"] + 1e-9),
        0.0
    )
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

    st.dataframe(styled_result, hide_index=True)
    if coins:
        profits = [prices.get(c, 0) * holdings.get(c, 0.0) - avg_price.get(c, 0.0) * holdings.get(c, 0.0) for c in coins]
        if any(profits):
            max_pnl_idx = int(np.argmax(profits))
            min_pnl_idx = int(np.argmin(profits))
            st.metric("Coin lãi nhiều nhất", f"{coin_id_to_name[coins[max_pnl_idx]]} ({profits[max_pnl_idx]:,.2f} USD)")
            st.metric("Coin lỗ nhiều nhất", f"{coin_id_to_name[coins[min_pnl_idx]]} ({profits[min_pnl_idx]:,.2f} USD)")





