import time
import math
import os
from datetime import datetime, timedelta
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def fetch_okx_liquidation(symbol="BTC-USDT-SWAP", limit=100):
    """Compatibility wrapper: fetch most recent liquidation orders (single page).

    Returns a DataFrame with parsed 'time' -> ms timestamp converted to datetime in 'datetime' column.
    """
    base = symbol.split('-')[0]
    url = f"https://www.okx.com/api/v5/public/liquidation-orders?instType=SWAP&uly={base}-USDT&instId={symbol}&state=filled&limit={limit}"
    resp = requests.get(url, timeout=10, headers=_PUBLIC_GET_HEADERS)
    data = resp.json()
    if data.get("code") != "0" or "data" not in data:
        return pd.DataFrame()
    all_details = []
    for liq in data["data"]:
        details = liq.get("details", [])
        for d in details:
            all_details.append(d)
    if not all_details:
        return pd.DataFrame()
    df = pd.DataFrame(all_details)
    df["datetime"] = pd.to_datetime(df["time"], unit="ms")
    return df


def fetch_okx_liquidation_range(symbol, start_dt, end_dt, page_limit=100, max_pages=50, sleep=0.15, overall_timeout: float | None = 8.0):
    """Fetch liquidation details from OKX paginating backwards until start_dt.

    Args:
      symbol: instId like 'BTC-USDT-SWAP'
      start_dt, end_dt: python datetimes in UTC. We'll fetch pages until the earliest record is older than start_dt or max_pages reached.
      page_limit: per-request limit (<=100)
      max_pages: safety limit to avoid infinite loops
      sleep: seconds between requests (respectful throttling)

    Returns: DataFrame with 'datetime', 'price' (bkPx), 'size' (sz), 'side' (posSide or side if available), and raw fields.
    """
    assert page_limit <= 100
    collected = []
    base = symbol.split('-')[0]
    params = {
        "instId": symbol,
        "instType": "SWAP",
        "uly": f"{base}-USDT",
        "state": "filled",
        "limit": page_limit,
    }

    # OKX liquidation-orders returns pages sorted newest -> oldest. We'll iterate until time < start_dt.
    pages = 0
    earliest_ms_seen = None
    deadline = (time.time() + float(overall_timeout)) if overall_timeout else None
    while pages < max_pages:
        # Stop if time budget exceeded
        if deadline is not None and time.time() >= deadline:
            break
        url = f"https://www.okx.com/api/v5/public/liquidation-orders"
        try:
            # Fit request timeout into remaining overall budget
            remaining = (deadline - time.time()) if deadline is not None else None
            req_to = 7 if remaining is None else max(1.5, min(7.0, remaining - 0.2))
            resp = requests.get(url, params=params, timeout=req_to, headers=_PUBLIC_GET_HEADERS)
            data = resp.json()
        except Exception:
            break
        if data.get("code") != "0" or "data" not in data:
            break
        page_has_data = False
        page_earliest = None
        for liq in data["data"]:
            details = liq.get("details", [])
            for d in details:
                ts = int(d.get("time", 0))
                dt = datetime.utcfromtimestamp(ts / 1000.0)
                if dt < start_dt:
                    # stop condition: this detail older than requested start
                    # still track earliest to paginate
                    if (page_earliest is None) or (ts < page_earliest):
                        page_earliest = ts
                    continue
                if dt > end_dt:
                    # skip future (shouldn't happen)
                    continue
                page_has_data = True
                collected.append(d)
                if (page_earliest is None) or (ts < page_earliest):
                    page_earliest = ts
        pages += 1
        # Pagination using 'before' based on earliest time seen
        if page_earliest is not None:
            earliest_ms_seen = page_earliest if earliest_ms_seen is None else min(earliest_ms_seen, page_earliest)
            params["before"] = str(int(earliest_ms_seen))
        # If no data at all and no pagination possible, stop
        if not page_has_data and page_earliest is None:
            break
        # Respectful throttling but don't exceed remaining budget
        if deadline is not None:
            remaining_after = deadline - time.time()
            if remaining_after <= 0:
                break
            time.sleep(min(sleep, max(0, remaining_after)))
        else:
            time.sleep(sleep)

    if not collected:
        return pd.DataFrame()
    df = pd.DataFrame(collected)
    # normalize
    df["datetime"] = pd.to_datetime(df["time"], unit="ms")
    df["price"] = pd.to_numeric(df.get("bkPx"), errors="coerce")
    df["size"] = pd.to_numeric(df.get("sz"), errors="coerce")
    # side: OKX returns 'side' or 'posSide' depending on API; normalize
    df["side"] = df.get("side").fillna(df.get("posSide")) if "side" in df.columns or "posSide" in df.columns else None
    df = df.dropna(subset=["price", "size", "datetime"]).reset_index(drop=True)
    return df


def _map_bar_for_duration(days: float) -> str:
    """Choose an OKX bar string from time window length."""
    if days >= 60:
        return "1D"
    if days >= 14:
        return "4H"
    if days > 1.25:
        return "1H"
    return "15m"


def fetch_okx_candles_range(symbol: str, start_dt: datetime, end_dt: datetime, bar: str | None = None,
                             limit_per: int = 300, max_pages: int = 50, sleep: float = 0.15, overall_timeout: float | None = 6.0) -> pd.DataFrame:
    """Fetch OKX candles for instId between start_dt..end_dt with pagination.

    Returns DataFrame with columns [ts, open, high, low, close, volume, datetime].
    """
    if bar is None:
        days = max(1.0, (end_dt - start_dt).total_seconds() / 86400)
        bar = _map_bar_for_duration(days)
    params = {
        "instId": symbol,
        "bar": bar,
        "limit": limit_per,
    }
    url = "https://www.okx.com/api/v5/market/candles"
    pages = 0
    rows = []
    before = None
    deadline = (time.time() + float(overall_timeout)) if overall_timeout else None
    while pages < max_pages:
        # Time budget check
        if deadline is not None and time.time() >= deadline:
            break
        q = dict(params)
        if before is not None:
            q["before"] = str(int(before))
        try:
            remaining = (deadline - time.time()) if deadline is not None else None
            req_to = 6 if remaining is None else max(1.5, min(6.0, remaining - 0.2))
            r = requests.get(url, params=q, timeout=req_to, headers=_PUBLIC_GET_HEADERS)
            js = r.json()
        except Exception:
            break
        if js.get("code") != "0" or not js.get("data"):
            break
        # OKX returns newest->oldest rows per page
        page_data = js["data"]
        page_min_ts = None
        for row in page_data:
            # [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
            try:
                ts = int(row[0])
                dt = datetime.utcfromtimestamp(ts / 1000.0)
                if dt < start_dt:
                    page_min_ts = ts if (page_min_ts is None or ts < page_min_ts) else page_min_ts
                    continue
                if dt > end_dt:
                    # newer than end, skip
                    continue
                o, h, l, c = map(float, row[1:5])
                vol = float(row[5]) if len(row) > 5 else 0.0
                rows.append({
                    "ts": ts,
                    "open": o,
                    "high": h,
                    "low": l,
                    "close": c,
                    "volume": vol,
                    "datetime": dt,
                })
                page_min_ts = ts if (page_min_ts is None or ts < page_min_ts) else page_min_ts
            except Exception:
                continue
        pages += 1
        if page_min_ts is None:
            break
        before = page_min_ts
        if deadline is not None:
            remaining_after = deadline - time.time()
            if remaining_after <= 0:
                break
            time.sleep(min(sleep, max(0, remaining_after)))
        else:
            time.sleep(sleep)
    if not rows:
        return pd.DataFrame()
    cdf = pd.DataFrame(rows).sort_values("datetime").reset_index(drop=True)
    return cdf


# ==================== Additional Exchange Providers (Optional) ==================== #
def _safe_to_float(x, default=None):
    try:
        return float(x)
    except Exception:
        return default

# Generic headers to reduce 403 from CDNs for public endpoints
_PUBLIC_GET_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 HakiCrypto/1.0"
}

# Allow overriding API base URLs via environment variables (for proxy/relay use cases)
BINANCE_API_BASE = os.getenv("BINANCE_API_BASE", "https://fapi.binance.com")
BITMEX_API_BASE = os.getenv("BITMEX_API_BASE", "https://www.bitmex.com")

# Lightweight diagnostics to surface fetch issues to the UI
_LAST_SOURCE_WARNINGS: dict[str, str] = {}

def _set_source_warning(source: str, message: str):
    try:
        _LAST_SOURCE_WARNINGS[source.upper()] = (message or "").strip()[:300]
    except Exception:
        pass

def get_source_warnings() -> dict:
    """Return a shallow copy of last known warnings per source (for UI diagnostics)."""
    try:
        return dict(_LAST_SOURCE_WARNINGS)
    except Exception:
        return {}


def fetch_binance_liquidation_range(symbol: str, start_dt: datetime, end_dt: datetime,
                                    limit: int = 1000, max_pages: int = 10, overall_timeout: float | None = 8.0) -> pd.DataFrame:
    """Fetch Binance Futures forced liquidation orders (if accessible).

    Endpoint (public market data): GET https://fapi.binance.com/fapi/v1/allForceOrders
    Params: symbol (e.g., BTCUSDT), startTime, endTime (ms), limit (<= 1000)
    Note: Some deployments may face restrictions; function fails fast and returns empty DataFrame if blocked.
    """
    base_url = f"{BINANCE_API_BASE.rstrip('/')}/fapi/v1/allForceOrders"
    rows = []
    deadline = (time.time() + float(overall_timeout)) if overall_timeout else None
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)
    current_start = start_ms
    pages = 0
    while pages < max_pages and current_start < end_ms:
        if deadline is not None and time.time() >= deadline:
            break
        params = {
            "symbol": symbol,
            "startTime": current_start,
            "endTime": end_ms,
            "limit": min(1000, limit),
        }
        try:
            remaining = (deadline - time.time()) if deadline is not None else None
            req_to = 6 if remaining is None else max(1.2, min(6.0, remaining - 0.2))
            r = requests.get(base_url, params=params, timeout=req_to, headers=_PUBLIC_GET_HEADERS)
            if r.status_code != 200:
                _set_source_warning("BINANCE", f"HTTP {r.status_code} from Binance allForceOrders")
                break
            data = r.json()
            # Handle geo-restricted or unexpected payloads
            if isinstance(data, dict):
                msg = (data or {}).get("msg", "")
                if msg:
                    _set_source_warning("BINANCE", msg)
                break
            if not isinstance(data, list) or not data:
                _set_source_warning("BINANCE", "Empty or non-list response from allForceOrders")
                break
            # Records typically sorted ascending by time
            for d in data:
                ts = int(d.get("time") or d.get("updatedTime") or 0)
                dt = datetime.utcfromtimestamp(ts / 1000.0)
                if dt < start_dt or dt > end_dt:
                    continue
                price = _safe_to_float(d.get("price") or d.get("avgPrice"))
                qty = _safe_to_float(d.get("qty") or d.get("executedQty"))
                if price is None or qty is None:
                    continue
                rows.append({
                    "datetime": dt,
                    "price": price,
                    "size": qty,
                    "exchange": "BINANCE"
                })
            # Advance start to last ts + 1 ms to avoid duplicates
            last_ts = int(data[-1].get("time") or data[-1].get("updatedTime") or current_start)
            if last_ts <= current_start:
                break
            current_start = last_ts + 1
            pages += 1
        except Exception:
            break
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def fetch_bitmex_liquidation_range(symbol: str, start_dt: datetime, end_dt: datetime,
                                   count: int = 1000, max_pages: int = 10, overall_timeout: float | None = 8.0) -> pd.DataFrame:
    """Fetch BitMEX liquidation events (public endpoint).

    Endpoint: GET https://www.bitmex.com/api/v1/liquidation
    Params: symbol, count, reverse=false, startTime, endTime
    """
    base_url = f"{BITMEX_API_BASE.rstrip('/')}/api/v1/liquidation"
    rows = []
    deadline = (time.time() + float(overall_timeout)) if overall_timeout else None
    # BitMEX supports ISO8601 times
    cur_start = start_dt
    pages = 0
    while pages < max_pages and cur_start < end_dt:
        if deadline is not None and time.time() >= deadline:
            break
        params = {
            "symbol": symbol,
            "count": count,
            "reverse": "false",
            "startTime": cur_start.strftime('%Y-%m-%dT%H:%M:%S.000Z'),
            "endTime": end_dt.strftime('%Y-%m-%dT%H:%M:%S.000Z'),
        }
        try:
            remaining = (deadline - time.time()) if deadline is not None else None
            req_to = 6 if remaining is None else max(1.2, min(6.0, remaining - 0.2))
            r = requests.get(base_url, params=params, timeout=req_to, headers=_PUBLIC_GET_HEADERS)
            if r.status_code != 200:
                _set_source_warning("BITMEX", f"HTTP {r.status_code} from BitMEX liquidation")
                break
            data = r.json()
            if not isinstance(data, list) or not data:
                _set_source_warning("BITMEX", "Empty or non-list response from liquidation")
                break
            for d in data:
                try:
                    ts = d.get("timestamp")
                    dt = datetime.fromisoformat(ts.replace('Z', '+00:00')).replace(tzinfo=None)
                    price = _safe_to_float(d.get("price"))
                    qty = _safe_to_float(d.get("qty"))
                    if price is None or qty is None:
                        continue
                    rows.append({
                        "datetime": dt,
                        "price": price,
                        "size": qty,
                        "exchange": "BITMEX"
                    })
                except Exception:
                    continue
            last_time = rows[-1]["datetime"] if rows else cur_start
            if last_time <= cur_start:
                break
            cur_start = last_time
            pages += 1
        except Exception:
            break
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def fetch_liquidations_multi(asset_symbol: str, start_dt: datetime, end_dt: datetime,
                             sources: list[str], okx_inst: str | None = None) -> pd.DataFrame:
    """Aggregate liquidation events from multiple exchanges into a unified DataFrame.

    sources: any of ["OKX","BINANCE","BITMEX"]
    asset_symbol: e.g., "BTC", "ETH" (used to map exchange symbols)
    okx_inst: explicit OKX instId if available (e.g., BTC-USDT-SWAP)
    """
    frames = []
    sym = asset_symbol.upper()
    # OKX
    if "OKX" in sources:
        inst = okx_inst or f"{sym}-USDT-SWAP"
        try:
            df_okx = fetch_okx_liquidation_range(inst, start_dt, end_dt, overall_timeout=6.5)
            if df_okx is not None and not df_okx.empty:
                df2 = df_okx[["datetime","price","size"]].copy()
                df2["exchange"] = "OKX"
                frames.append(df2)
        except Exception:
            pass
    # Binance
    if "BINANCE" in sources:
        # Map asset to Binance symbol
        b_symbol = f"{sym}USDT"
        try:
            df_bi = fetch_binance_liquidation_range(b_symbol, start_dt, end_dt, overall_timeout=6.5)
            if df_bi is not None and not df_bi.empty:
                frames.append(df_bi[["datetime","price","size","exchange"]])
        except Exception:
            pass
    # BitMEX
    if "BITMEX" in sources and sym in ("BTC","XBT","ETH"):
        mx_sym = "XBTUSD" if sym in ("BTC","XBT") else "ETHUSD"
        try:
            df_mx = fetch_bitmex_liquidation_range(mx_sym, start_dt, end_dt, overall_timeout=6.0)
            if df_mx is not None and not df_mx.empty:
                frames.append(df_mx[["datetime","price","size","exchange"]])
        except Exception:
            pass
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df.sort_values("datetime", inplace=True)
    return df


def build_liquidation_heatmap(
    df,
    symbol,
    time_bins=72,
    price_bins=80,
    price_step=None,
    threshold=1,
    timeframe_label="3M",
    overlay_price=True,
    colorscale: str = "Reds",
    yaxis_reverse: bool = True,
):
    """Build a 2D heatmap (time × price) aggregated by size.

    Args:
      df: DataFrame with 'datetime', 'price', 'size'
      time_bins: number of time buckets (vertical axis will be price, horizontal time or vice-versa)
      price_bins: number of price buckets
      price_step: optional fixed price step; if None, infer from price span
      threshold: minimum aggregated liquidation size to show (in same units as size)
      timeframe_label: string for title/annotation

    Returns: plotly.graph_objects.Figure
    """
    if df.empty:
        return None
    df = df.copy()
    df = df.sort_values("datetime")
    start = df["datetime"].min()
    end = df["datetime"].max()
    # time bins
    df["time_bin"] = pd.cut(df["datetime"].astype('int64') // 10**9, bins=time_bins, labels=False)
    # price bins
    pmin = df["price"].min()
    pmax = df["price"].max()
    if price_step is None:
        # choose reasonable step: divide range into price_bins
        if pmax <= pmin:
            price_step = 1
        else:
            price_step = max((pmax - pmin) / price_bins, 1e-6)
    # compute price_bin as floor((price - pmin)/price_step)
    df["price_bin_idx"] = ((df["price"] - pmin) // price_step).astype(int)
    # aggregate
    agg = df.groupby(["price_bin_idx", "time_bin"]) ["size"].sum().reset_index()
    # apply threshold
    agg["size_clipped"] = agg["size"].where(agg["size"] >= threshold, 0)
    # build matrix for heatmap
    time_range = range(0, df["time_bin"].max() + 1)
    price_range = range(0, df["price_bin_idx"].max() + 1)
    matrix = pd.DataFrame(0.0, index=price_range, columns=time_range)
    for _, row in agg.iterrows():
        i = int(row["price_bin_idx"])
        j = int(row["time_bin"])
        matrix.at[i, j] = row["size_clipped"]

    # y labels: price for each price bin
    y_prices = [pmin + (i + 0.5) * price_step for i in matrix.index]
    x_times = []
    # compute representative time per time_bin (center)
    tmins = df.groupby("time_bin")["datetime"].min()
    tmaxs = df.groupby("time_bin")["datetime"].max()
    for tb in matrix.columns:
        if tb in tmins.index:
            x_times.append(pd.to_datetime((tmins.loc[tb].value + tmaxs.loc[tb].value) // 2))
        else:
            x_times.append(start + (end - start) * (tb / max(1, matrix.shape[1] - 1)))

    z = matrix.values
    # build figure
    fig = go.Figure()
    fig.add_trace(go.Heatmap(
        z=z,
        x=x_times,
        y=y_prices,
        colorscale=colorscale,
        colorbar=dict(title="Liquidation size"),
        showscale=True,
        zsmooth=False,
        hovertemplate="Time: %{x}<br>Price: %{y:.2f}<br>Size: %{z}<extra></extra>",
        opacity=0.9
    ))

    # overlay price path (close) across the same window
    if overlay_price:
        try:
            # Choose bar based on df window to match timeframe granularity
            days = max(1.0, (end - start).total_seconds() / 86400)
            bar = _map_bar_for_duration(days)
            # Keep price overlay non-blocking with a small time budget
            cdf = fetch_okx_candles_range(symbol, start, end, bar=bar, overall_timeout=4.0)
            if cdf is not None and not cdf.empty:
                fig.add_trace(go.Scatter(
                    x=cdf["datetime"],
                    y=cdf["close"],
                    mode="lines",
                    name=f"Price ({bar})",
                    line=dict(color="#1f77b4", width=1.8)
                ))
        except Exception:
            pass

    # add current price line
    try:
        inst_id = symbol
        url = f"https://www.okx.com/api/v5/market/ticker?instId={inst_id}"
        resp = requests.get(url, timeout=5, headers=_PUBLIC_GET_HEADERS)
        data = resp.json()
        px_now = float(data["data"][0]["last"])
        fig.add_hline(y=px_now, line_dash="dash", line_color="#00bcd4", annotation_text=f"Now: {px_now:,.2f}", annotation_position="top right")
    except Exception:
        pass

    fig.update_layout(
        title=f"Liquidation Heatmap {symbol} ({timeframe_label})",
        xaxis_title="Time",
        yaxis_title="Price",
        yaxis_autorange='reversed' if yaxis_reverse else True,
        template='plotly_dark',
        hovermode='x unified'
    )
    return fig


def streamlit_liquidation_heatmap_ui():
    """Simple Streamlit UI entrypoint for interactive heatmap with timeframe and threshold controls.

    Use in Streamlit: `import metrics_liquidation_okx as mlo; mlo.streamlit_liquidation_heatmap_ui()`
    """
    import streamlit as st

    st.header("OKX Liquidation Heatmap")
    symbol = st.text_input("Symbol (instId)", value="BTC-USDT-SWAP")
    timeframe = st.selectbox("Timeframe", options=["3M", "1M", "7D", "1D"], index=3)
    threshold = st.slider("Threshold (min aggregated size)", min_value=1, max_value=1000000, value=8, step=1)
    price_bins = st.slider("Price bins", 20, 300, 45)
    time_bins = st.slider("Time bins", 8, 200, 50)

    now = datetime.utcnow()
    if timeframe == "3M":
        start = now - timedelta(days=90)
    elif timeframe == "1M":
        start = now - timedelta(days=30)
    elif timeframe == "7D":
        start = now - timedelta(days=7)
    else:
        start = now - timedelta(days=1)

    with st.spinner("Fetching liquidation data from OKX..."):
        df = fetch_okx_liquidation_range(symbol, start, now)

    if df.empty:
        st.warning("Không có dữ liệu liquidation trong khoảng thời gian đã chọn.")
        return

    fig = build_liquidation_heatmap(df, symbol, time_bins=time_bins, price_bins=price_bins, threshold=threshold, timeframe_label=timeframe, overlay_price=True, colorscale="Plasma", yaxis_reverse=False)
    if fig is None:
        st.warning("Không thể tạo heatmap với dữ liệu hiện tại.")
        return
    st.plotly_chart(fig, use_container_width=True)

