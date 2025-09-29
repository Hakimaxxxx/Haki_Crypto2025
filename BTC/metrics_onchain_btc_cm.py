import requests
import pandas as pd
import os

def fetch_btc_onchain_metrics_cm(save_path="coin_data/btc_onchain_metrics_cm.csv", days=365):
    """
    Lấy dữ liệu on-chain phổ biến của BTC từ Coin Metrics community API.
    """
    base_url = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
    metrics = [
        "PriceUSD",        # Giá BTC
        "AdrActCnt",      # Địa chỉ active
        "TxCnt",          # Số giao dịch
        "FeeTotUSD",      # Tổng phí giao dịch (USD)
        "IssTotUSD",      # Giá trị coin mới phát hành (USD)
        "BlkCnt",         # Số block mỗi ngày
        "HashRate",       # Hashrate
        "DiffMean"        # Độ khó trung bình
    ]
    params = {
        "assets": "btc",
        "metrics": ",".join(metrics),
        "frequency": "1d",
        "page_size": 10000,
        "pretty": "false"
    }
    resp = requests.get(base_url, params=params, timeout=30)
    data = resp.json()
    if "data" not in data:
        raise Exception(f"Không lấy được dữ liệu từ Coin Metrics: {data}")
    df = pd.DataFrame(data["data"])
    df = df.rename(columns={"time": "date"})
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    df.to_csv(save_path, index=False)
    return save_path
