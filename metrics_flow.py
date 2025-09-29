import requests
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

def get_cryptoquant_flow(symbol, days=30):
    """
    Lấy dữ liệu inflow, outflow, netflow từ CryptoQuant public API (dạng CSV download)
    symbol: 'btc' hoặc 'eth'
    days: số ngày gần nhất
    """
    # CryptoQuant không có API public miễn phí, nhưng có thể lấy CSV từ web
    # Ví dụ: https://cryptoquant.com/asset/btc/flow
    # Hướng dẫn: User tải file CSV từ CryptoQuant, đặt tên btc_flow.csv hoặc eth_flow.csv
    file = f"{symbol}_flow.csv"
    try:
        df = pd.read_csv(file)
        # Giả định cột: date, inflow, outflow, netflow
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        df = df[df['date'] >= pd.Timestamp.now() - pd.Timedelta(days=days)]
        return df
    except Exception as e:
        st.error(f"Không đọc được file {file}: {e}")
        return pd.DataFrame()

def show_flow_metric(symbol, name):
    st.subheader(f"{name} Exchange Inflow/Outflow/Netflow")
    df = get_cryptoquant_flow(symbol)
    if df.empty:
        st.info(f"Hãy tải file {symbol}_flow.csv từ CryptoQuant và đặt vào thư mục này.")
        return
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df['date'], y=df['inflow'], mode='lines', name='Inflow', line=dict(color='#3498db')))
    fig.add_trace(go.Scatter(x=df['date'], y=df['outflow'], mode='lines', name='Outflow', line=dict(color='#e67e22')))
    fig.add_trace(go.Bar(x=df['date'], y=df['netflow'], name='Netflow', marker_color='#2ecc71'))
    fig.update_layout(title=f"{name} Exchange Inflow/Outflow/Netflow", xaxis_title="Ngày", yaxis_title="Số lượng coin", height=350)
    st.plotly_chart(fig, use_container_width=True)
