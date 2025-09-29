import requests
import pandas as pd
import plotly.express as px

def fetch_okx_liquidation(symbol="BTC-USDT-SWAP", limit=100):
    """
    Lấy danh sách liquidation gần nhất từ OKX public API.
    symbol: mã hợp đồng, ví dụ BTC-USDT-SWAP, ETH-USDT-SWAP
    limit: số lượng liquidation lấy về (tối đa 100)
    """
    # symbol ví dụ: BTC-USDT-SWAP, ETH-USDT-SWAP, SOL-USDT-SWAP
    base = symbol.split('-')[0]
    url = f"https://www.okx.com/api/v5/public/liquidation-orders?instType=SWAP&uly={base}-USDT&instId={symbol}&state=filled&limit={limit}"
    resp = requests.get(url, timeout=10)
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

def plot_liquidation_heatmap(df, symbol="BTC-USDT-SWAP"):
    """
    Vẽ heatmap liquidation theo vùng giá và khối lượng.
    """
    if df.empty:
        return None
    # Check for required columns
    import streamlit as st
    if "bkPx" not in df.columns or "sz" not in df.columns:
        st.warning("Không có dữ liệu liquidation hợp lệ từ OKX (thiếu trường 'bkPx' hoặc 'sz').")
        return None
    # Chuyển price và sz sang float, loại bỏ giá trị lỗi
    df = df.copy()
    try:
        df["price"] = pd.to_numeric(df["bkPx"], errors="coerce")
        df["size"] = pd.to_numeric(df["sz"], errors="coerce")
    except Exception as e:
        st.warning(f"Lỗi chuyển đổi dữ liệu: {e}")
        return None
    df = df.dropna(subset=["price", "size"])
    if df.empty:
        st.warning("Không có dữ liệu liquidation hợp lệ sau khi xử lý số liệu.")
        return None
    # Gom nhóm theo price (làm tròn về vùng giá, ví dụ 100 USD)
    # Tự động chọn bước giá phù hợp từng coin
    if symbol.startswith("BTC"):
        price_step = 100
    elif symbol.startswith("ETH"):
        price_step = 10
    elif symbol.startswith("SOL"):
        price_step = 1
    else:
        price_step = 5
    df["price_bin"] = (df["price"] // price_step) * price_step
    heatmap = df.groupby("price_bin")["size"].sum().reset_index()
    if heatmap.empty:
        st.warning("Không có dữ liệu liquidation sau khi nhóm theo vùng giá.")
        return None
    import plotly.express as px
    fig = px.density_heatmap(heatmap, y="price_bin", x="size", nbinsy=30, color_continuous_scale="Reds",
                            labels={"price_bin": "Vùng giá", "size": "Khối lượng thanh lý"},
                            title=f"Liquidation Heatmap ({symbol})")

    # Lấy giá hiện tại từ OKX public API
    try:
        inst_id = symbol
        url = f"https://www.okx.com/api/v5/market/ticker?instId={inst_id}"
        resp = requests.get(url, timeout=5)
        data = resp.json()
        px_now = float(data["data"][0]["last"])
        fig.add_shape(
            type="line",
            x0=0, x1=heatmap["size"].max(),
            y0=px_now, y1=px_now,
            line=dict(color="blue", width=2, dash="dash"),
            name="Giá hiện tại"
        )
        fig.add_annotation(x=heatmap["size"].max(), y=px_now, text=f"Giá hiện tại: {px_now:,.0f}",
                          showarrow=False, font=dict(color="blue"), bgcolor="white")
    except Exception as e:
        pass
    return fig
