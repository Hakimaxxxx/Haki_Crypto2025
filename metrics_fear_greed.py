import threading
import time
import os
import requests
import pandas as pd
import streamlit as st
from datetime import datetime

def get_fear_greed_index():
    # Đọc cache nếu có
    cache_file = "fear_greed_history.csv"
    if os.path.exists(cache_file):
        try:
            df = pd.read_csv(cache_file)
            df["value"] = df["value"].astype(int)
            # Cast to numeric seconds to avoid pandas FutureWarning when unit used later
            if not pd.api.types.is_numeric_dtype(df["timestamp"]):
                df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce")
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", errors="coerce")
            df = df.sort_values("timestamp")
            return df
        except Exception:
            pass
    # Nếu không có cache, fetch online
    url = "https://api.alternative.me/fng/?limit=400&format=json"
    try:
        response = requests.get(url, timeout=10)
        data = response.json().get("data", [])
        df = pd.DataFrame(data)
        if df.empty:
            return pd.DataFrame()
        df["value"] = pd.to_numeric(df["value"], errors="coerce").fillna(0).astype(int)
        df["timestamp"] = pd.to_datetime(pd.to_numeric(df["timestamp"], errors="coerce"), unit="s", errors="coerce")
        df = df.dropna(subset=["timestamp"]).sort_values("timestamp")
        return df
    except Exception as e:
        st.error(f"Không lấy được dữ liệu Fear & Greed Index: {e}")
        return pd.DataFrame()
# --- TỰ ĐỘNG CRAWL FEAR & GREED INDEX MỖI 5 PHÚT ---
def crawl_fear_greed_background():
    cache_file = "fear_greed_history.csv"
    url = "https://api.alternative.me/fng/?limit=400&format=json"
    while True:
        try:
            response = requests.get(url, timeout=10)
            data = response.json()["data"]
            df = pd.DataFrame(data)
            df["value"] = df["value"].astype(int)
            df["timestamp"] = pd.to_datetime(pd.to_numeric(df["timestamp"], errors="coerce"), unit="s", errors="coerce")
            df = df.sort_values("timestamp")
            df.to_csv(cache_file, index=False)
        except Exception:
            pass
        time.sleep(300)  # 5 phút

# Khởi động thread crawl khi import module (chỉ 1 lần)
if not hasattr(st.session_state, "_fear_greed_crawler"):
    t = threading.Thread(target=crawl_fear_greed_background, daemon=True)
    t.start()
    st.session_state["_fear_greed_crawler"] = True

def show_fear_greed_metric():
    df = get_fear_greed_index()
    if df.empty:
        st.info("Không có dữ liệu Fear & Greed Index.")
        return
    # Chỉ số hiện tại
    current = df.iloc[-1]
    # Xác định màu theo vùng chỉ số
    v = current['value']
    if v >= 75:
        color = "#27ae60"  # Greed - xanh
    elif v <= 30:
        color = "#e74c3c"  # Fear - đỏ
    else:
        color = "#f1c40f"  # Neutral - vàng
    st.markdown(f"<div style='font-size:22px;font-weight:bold;'>Crypto Fear & Greed Index (hiện tại): <span style='color:{color}'>{current['value']} ({current['value_classification']})</span></div>", unsafe_allow_html=True)

    # Option chọn khung thời gian
    option = st.radio("Chọn khung thời gian", ["30 ngày", "1 năm"], horizontal=True)
    if option == "30 ngày":
        df_show = df[df["timestamp"] >= (df["timestamp"].max() - pd.Timedelta(days=30))]
    else:
        df_show = df[df["timestamp"] >= (df["timestamp"].max() - pd.Timedelta(days=365))]

    # Đổi màu line theo giá trị chỉ số (tham lam/sợ hãi)
    import plotly.graph_objects as go
    color_map = []
    for v in df_show["value"]:
        if v >= 75:
            color_map.append("#27ae60")  # Greed - xanh
        elif v <= 30:
            color_map.append("#e74c3c")  # Fear - đỏ
        else:
            color_map.append("#f1c40f")  # Neutral - vàng

    fig = go.Figure()
    # Vẽ từng đoạn line với màu tương ứng
    vals = df_show["value"].values
    # Đảm bảo times là kiểu datetime (không phải numpy object)
    times = pd.to_datetime(pd.to_numeric(df_show["timestamp"], errors="coerce"), unit="s", errors="coerce").to_list()
    for i in range(1, len(vals)):
        fig.add_trace(go.Scatter(
            x=[times[i-1], times[i]],
            y=[vals[i-1], vals[i]],
            mode="lines",
            line=dict(color=color_map[i], width=3),
            showlegend=False
        ))
    # Thêm các điểm value với màu tương ứng
    fig.add_trace(go.Scatter(
        x=times,
        y=vals,
        mode="markers+text",
        marker=dict(color=color_map, size=10),
        text=[str(v) for v in vals],
        textposition="top center",
        showlegend=False
    ))
    fig.update_layout(title="Crypto Fear & Greed Index", xaxis_title="Ngày", yaxis_title="Chỉ số", height=300, xaxis_tickformat='%d-%m-%Y')
    st.plotly_chart(fig, use_container_width=True)
