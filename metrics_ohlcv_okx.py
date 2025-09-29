import streamlit as st

def get_with_proxy_popup(url, **kwargs):
    import requests
    session = requests.Session()
    try:
        resp = session.get(url, **kwargs)
        return resp
    except requests.exceptions.ProxyError as e:
        # Nếu lỗi proxy mới hiện popup, còn nếu không thì không hỏi proxy
        st.warning("Proxy yêu cầu xác thực. Vui lòng nhập username và password proxy để tiếp tục.")
        proxy_host = "rb-proxy-de.bosch.com"
        proxy_port = 8080
        with st.form("proxy_auth_form"):
            proxy_user = st.text_input("Proxy Username", type="default")
            proxy_pass = st.text_input("Proxy Password", type="password")
            submitted = st.form_submit_button("Xác thực proxy")
        if submitted and proxy_user and proxy_pass:
            proxies = {
                "http": f"http://{proxy_user}:{proxy_pass}@{proxy_host}:{proxy_port}",
                "https": f"http://{proxy_user}:{proxy_pass}@{proxy_host}:{proxy_port}"
            }
            try:
                resp = session.get(url, proxies=proxies, **kwargs)
                import sys
                print(f"[Proxy] Đã xác thực proxy thành công với user: {proxy_user}", file=sys.stderr)
                print(f"[Proxy] Đang truy cập: {url}", file=sys.stderr)
                return resp
            except Exception as e2:
                import sys
                print(f"[Proxy] Lỗi proxy: {e2}", file=sys.stderr)
                st.error(f"Lỗi proxy: {e2}")
                st.stop()
        else:
            st.stop()
    except Exception as e:
        st.error(f"Lỗi kết nối: {e}")
        st.stop()
import requests
import pandas as pd

def fetch_okx_ohlcv_oi(symbol="BTC-USDT-SWAP", bar="1h", limit=200):
    # Bỏ qua các cặp không hợp lệ như USDT-USDT-SWAP
    if symbol.upper().startswith("USDT-USDT"):
        st.warning(f"Cặp giao dịch {symbol} không hợp lệ trên OKX, sẽ bỏ qua.")
        return pd.DataFrame()
    """
    Lấy dữ liệu nến (OHLCV), volume, open interest từ OKX cho symbol và khung thời gian bar.
    symbol: ví dụ BTC-USDT-SWAP
    bar: '1m','5m','15m','1h','4h','1d',...
    limit: số lượng nến (tối đa 200)
    """
    url_main = f"https://www.okx.com/api/v5/market/history-candles?instId={symbol}&bar={bar}&limit={limit}"
    url_sg = f"https://www.okx.com/en-sg/api/v5/market/history-candles?instId={symbol}&bar={bar}&limit={limit}"
    resp = get_with_proxy_popup(url_main, timeout=10)
    data = resp.json()
    if data.get("code") == "0" and "data" in data:
        pass
    else:
        # Thử lại với endpoint Singapore nếu lỗi hoặc không có data
        resp = get_with_proxy_popup(url_sg, timeout=10)
        data = resp.json()
        if data.get("code") != "0" or "data" not in data:
            return pd.DataFrame()
    # OKX trả về: [[ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm], ...] (9 trường)
    columns = [
        "timestamp", "open", "high", "low", "close", "volume", "volCcy", "volCcyQuote", "confirm"
    ]
    df = pd.DataFrame(data["data"], columns=columns)
    df = df.astype({
        "timestamp": "int64", "open": "float", "high": "float", "low": "float", "close": "float",
        "volume": "float"
    })
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.sort_values("datetime")
    return df

def plot_price_volume_chart(df, symbol="BTC-USDT-SWAP"):
    import plotly.graph_objects as go
    if df is None or df.empty:
        return None
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["datetime"], y=df["close"], name="Giá đóng cửa", line=dict(color="blue")))
    fig.add_trace(go.Bar(x=df["datetime"], y=df["volume"], name="Volume", yaxis="y2", marker_color="orange", opacity=0.4))
    fig.update_layout(
        title=f"Giá & Volume ({symbol})",
        xaxis=dict(title="Thời gian"),
        yaxis=dict(title="Giá đóng cửa", side="left"),
        yaxis2=dict(title="Volume", overlaying="y", side="right", showgrid=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    return fig
