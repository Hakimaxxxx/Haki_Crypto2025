import streamlit as st
import pandas as pd
import numpy as np
import os
import json

def show_mvrv_z_metric(coin_id, coin_name):
    """
    Hiển thị metric MVRV-Z score cho từng coin (ETH, BTC,...)
    Dữ liệu lấy từ coin_data/{coin_id}_onchain_sample.json
    """
    file_path = f"coin_data/{coin_id}_onchain_sample.json"
    if not os.path.exists(file_path):
        st.info(f"Chưa có dữ liệu on-chain cho {coin_name}.")
        return
    with open(file_path, "r") as f:
        data = json.load(f)
    df = pd.DataFrame({
        "date": [x[0] for x in data["market_cap"]],
        "market_cap": [x[1] for x in data["market_cap"]],
        "realized_cap": [x[1] for x in data["realized_cap"]]
    })
    # Tính MVRV-Z score
    std_mcap = np.std(df["market_cap"])
    df["mvrv_z"] = (df["market_cap"] - df["realized_cap"]) / (std_mcap if std_mcap > 0 else 1)
    st.subheader(f"MVRV-Z Score ({coin_name})")
    st.line_chart(df.set_index("date")["mvrv_z"], use_container_width=True)
    st.caption("MVRV-Z = (Market Cap - Realized Cap) / Std(Market Cap). Giá trị cao: thị trường có thể đang bị định giá quá cao. Giá trị thấp: có thể bị định giá thấp.")
