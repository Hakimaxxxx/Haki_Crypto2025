import requests
import pandas as pd
import os

def fetch_btc_onchain_coinmetrics(days=365, save_path="coin_data/btc_onchain_coinmetrics.csv", api_key=None):
    """
    Lấy dữ liệu lịch sử Realized Cap, Market Cap, Supply của BTC từ Coin Metrics (community API),
    lưu vào file CSV để dùng cho chart và phân tích.
    """
    base_url = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
    metrics = ["CapRealizedUSD", "CapMrktCurUSD", "SplyCur"]
    params = {
        "assets": "btc",
        "metrics": ",".join(metrics),
        "frequency": "1d",
        "page_size": 10000,
        "pretty": "false"
    }
    if api_key:
        params["api_key"] = api_key
    resp = requests.get(base_url, params=params, timeout=30)
    data = resp.json()
    if "data" not in data:
        raise Exception(f"Không lấy được dữ liệu từ Coin Metrics: {data}")
    df = pd.DataFrame(data["data"])
    # Đổi tên cột cho dễ đọc
    df = df.rename(columns={
        "time": "date",
        "CapRealizedUSD": "realized_cap",
        "CapMrktCurUSD": "market_cap",
        "SplyCur": "supply"
    })
    # Tính thêm realized_price và MVRV
    df["realized_price"] = df["realized_cap"].astype(float) / df["supply"].astype(float)
    df["mvrv"] = df["market_cap"].astype(float) / df["realized_cap"].astype(float)
    # Lưu file
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    df.to_csv(save_path, index=False)
    return save_path
