import requests
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

def get_dominance_data():
    # Lấy dữ liệu dominance từ CoinGecko
    url = "https://api.coingecko.com/api/v3/global"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()["data"]["market_cap_percentage"]
        btc = data.get("btc", 0)
        eth = data.get("eth", 0)
        others = 100 - btc - eth
        now = pd.Timestamp.now()
        return pd.DataFrame({
            "timestamp": [now],
            "BTC": [btc],
            "ETH": [eth],
            "Others": [others]
        })
    except Exception as e:
        st.error(f"Không lấy được dữ liệu Dominance: {e}")
        return pd.DataFrame()

import requests
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

def get_marketcap_history(coin_id, days):
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart?vs_currency=usd&days={days}"
    response = requests.get(url, timeout=15)
    data = response.json()
    # data['market_caps'] = [[timestamp, cap], ...]
    df = pd.DataFrame(data['market_caps'], columns=['timestamp', f'{coin_id}_cap'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def get_total_marketcap_history(days):
    url = f"https://api.coingecko.com/api/v3/global/market_cap_chart?vs_currency=usd&days={days}"
    response = requests.get(url, timeout=15)
    data = response.json()
    df = pd.DataFrame(data['market_cap'], columns=['timestamp', 'total_cap'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def get_dominance_history(days=180):
    try:
        btc = get_marketcap_history('bitcoin', days)
        eth = get_marketcap_history('ethereum', days)
        total = get_total_marketcap_history(days)
        # Merge theo timestamp gần nhất
        df = pd.merge_asof(btc.sort_values('timestamp'), eth.sort_values('timestamp'), on='timestamp', direction='nearest')
        df = pd.merge_asof(df, total.sort_values('timestamp'), on='timestamp', direction='nearest')
        df['BTC'] = df['bitcoin_cap'] / df['total_cap'] * 100
        df['ETH'] = df['ethereum_cap'] / df['total_cap'] * 100
        df['Others'] = 100 - df['BTC'] - df['ETH']
        return df[['timestamp', 'BTC', 'ETH', 'Others']]
    except Exception as e:
        st.error(f"Không lấy được dữ liệu Dominance lịch sử tự động: {e}")
        st.info("Bạn có thể tải file CSV Dominance từ TradingView hoặc nguồn khác, đặt tên 'dominance_history.csv' trong thư mục này để hiển thị.")
        return pd.DataFrame()

def show_dominance_metric():
    option = st.radio("Chọn khung thời gian", ["1 ngày", "7 ngày", "1 tháng", "3 tháng", "6 tháng"], horizontal=True)
    days_map = {"1 ngày": 1, "7 ngày": 7, "1 tháng": 30, "3 tháng": 90, "6 tháng": 180}
    days = days_map[option]
    # Ưu tiên đọc file CSV nếu có
    import os
    if os.path.exists("dominance_history.csv"):
        df = pd.read_csv("dominance_history.csv", parse_dates=["timestamp"])
        df["timestamp"] = pd.to_datetime(df["timestamp"])  # Đảm bảo đúng kiểu datetime
        df = df.sort_values("timestamp")
        # Nếu dữ liệu có theo giờ, lọc theo giờ, nếu chỉ có ngày thì vẫn hoạt động bình thường
        min_time = pd.Timestamp.now() - pd.Timedelta(days=days)
        df = df[df["timestamp"] >= min_time]
        # Nếu dữ liệu có nhiều bản ghi trong 1 ngày, vẽ theo từng phút/giờ
        if df["timestamp"].dt.floor('min').nunique() > 24:
            x_title = "Thời gian (phút)"
        elif df["timestamp"].dt.hour.nunique() > 1:
            x_title = "Thời gian (giờ)"
        else:
            x_title = "Ngày"
    else:
        df = get_dominance_history(days)
        x_title = "Ngày"
    if df.empty:
        st.info("Không có dữ liệu Dominance.")
        return
    # Chuẩn hóa để tất cả series bắt đầu từ cùng 1 điểm (gốc = 0, thể hiện thay đổi tương đối)
    df = df.copy()
    for col in ["BTC", "ETH", "Others"]:
        df[col + "_rel"] = df[col] - df[col].iloc[0]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["timestamp"], y=df["BTC_rel"], mode="lines+markers", name="BTC", line=dict(color="#f7931a")))
    fig.add_trace(go.Scatter(x=df["timestamp"], y=df["ETH_rel"], mode="lines+markers", name="ETH", line=dict(color="#627eea")))
    fig.add_trace(go.Scatter(x=df["timestamp"], y=df["Others_rel"], mode="lines+markers", name="Others", line=dict(color="#95a5a6")))
    fig.update_layout(title="Bitcoin/Ethereum/Others Dominance - Relative Change (%)", xaxis_title=x_title, yaxis_title="Δ% Dominance (so với điểm đầu)", height=300, xaxis_tickformat='%d-%m-%Y %H:%M')
    st.plotly_chart(fig, use_container_width=True)