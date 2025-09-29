import requests
import streamlit as st
import pandas as pd
from datetime import datetime

def fetch_large_eth_transactions(api_key, min_value_eth=100, max_results=20):
    url = "https://api.etherscan.io/api"
    params = {
        "module": "account",
        "action": "txlist",
        "address": "0xde0b295669a9fd93d5f28d9ec85e40f4cb697bae",  # Vitalik's wallet for demo
        "startblock": 0,
        "endblock": 99999999,
        "sort": "desc",
        "apikey": api_key
    }
    r = requests.get(url, params=params, timeout=10)
    data = r.json()
    if data.get("status") != "1":
        return pd.DataFrame()
    df = pd.DataFrame(data["result"])
    df["value"] = df["value"].astype(float) / 1e18  # Convert Wei to ETH
    df = df[df["value"] >= min_value_eth]
    df["time"] = pd.to_datetime(df["timeStamp"].astype(int), unit="s")
    df = df.sort_values("time", ascending=False).head(max_results)
    return df


import os
import json

API_KEY_FILE = "eth_api_key.json"

def save_eth_api_key(key):
    with open(API_KEY_FILE, "w") as f:
        json.dump({"api_key": key}, f)

def load_eth_api_key():
    if os.path.exists(API_KEY_FILE):
        with open(API_KEY_FILE, "r") as f:
            data = json.load(f)
            return data.get("api_key", "")
    return ""

def show_eth_whale_alert_tab(api_key=None):
    # Nếu chưa có key truyền vào, lấy từ file hoặc mặc định
    if not api_key:
        api_key = load_eth_api_key()
    if not api_key:
        api_key = "2I9RJZUQK7CGS6C3G5SPXIUCTCK3VXBRAG"
    # Lưu key nếu khác key mặc định
    if api_key and api_key != load_eth_api_key():
        save_eth_api_key(api_key)
    min_value = st.number_input("Ngưỡng giá trị (ETH) để cảnh báo", min_value=1.0, value=1000.0, step=1.0)
    box_content = ""
    try:
        df = fetch_large_eth_transactions(api_key, min_value_eth=min_value)
        if df.empty:
            box_content += "<div style='color:#888;'>Không có transaction lớn nào được phát hiện gần đây.</div>"
        else:
            for _, row in df.iterrows():
                box_content += f"<div style='margin-bottom:8px;'><span style='color:#1e88e5;font-weight:bold;'>🐳 {row['value']:.2f} ETH</span> | Hash: <code>{row['hash'][:12]}...</code> | Từ: <code>{row['from'][:10]}...</code> → Đến: <code>{row['to'][:10]}...</code> | <span style='color:#888;'>{row['time']}</span></div>"
    except Exception as e:
        box_content += f"<div style='color:#c00;'>Không thể lấy dữ liệu whale alert từ Etherscan: {str(e)}</div>"
    st.markdown(f"<div style='height: 260px; overflow-y: auto; border: 1px solid #ccc; border-radius: 8px; padding: 8px; background: #f9f9f9; margin-top: 16px;'>{box_content}</div>", unsafe_allow_html=True)
