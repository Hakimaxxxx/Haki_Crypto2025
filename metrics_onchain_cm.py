import requests
import pandas as pd
import os

COINGECKO_TO_CM_ASSET = {
    "bitcoin": "btc",
    "ethereum": "eth",
    "solana": "sol",
    "chainlink": "link",
    "near": "near",
    "avalanche-2": "avax",
    "sui": "sui",
    "binancecoin": "bnb",
    "aptos": "apt",
    "ethena": "ena",
    "eigenlayer": "eigen",
    "worldcoin-wld": "wld",
    "ondo-finance": "ondo",
    "render-token": "render",
    "tether": "usdt"
}

def fetch_onchain_metrics_cm(asset, save_path, days=365):
    # Map CoinGecko id sang asset id của Coin Metrics nếu có
    asset_cm = COINGECKO_TO_CM_ASSET.get(asset, asset)
    """
    Lấy dữ liệu on-chain phổ biến của 1 coin từ Coin Metrics community API.
    """
    base_url = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
    metrics = [
        "PriceUSD",        # Giá
        "AdrActCnt",      # Địa chỉ active
        "TxCnt",          # Số giao dịch
        "FeeTotUSD",      # Tổng phí giao dịch (USD)
        "IssTotUSD",      # Giá trị coin mới phát hành (USD)
        "BlkCnt",         # Số block mỗi ngày
        "HashRate",       # Hashrate
        "DiffMean"        # Độ khó trung bình
    ]
    params = {
        "assets": asset_cm,
        "metrics": ",".join(metrics),
        "frequency": "1d",
        "page_size": 10000,
        "pretty": "false"
    }
    try:
        resp = requests.get(base_url, params=params, timeout=30)
        data = resp.json()
        if "data" not in data:
            return None
        df = pd.DataFrame(data["data"])
        df = df.rename(columns={"time": "date"})
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        df.to_csv(save_path, index=False)
        return save_path
    except Exception:
        return None

def load_onchain_metrics(asset, days=365):
    """
    Tải dữ liệu on-chain từ file hoặc crawl nếu chưa có.
    """
    save_path = f"coin_data/{asset}_onchain_metrics_cm.csv"
    if not os.path.exists(save_path):
        result = fetch_onchain_metrics_cm(asset, save_path, days)
        if result is None:
            return None
    try:
        df = pd.read_csv(save_path)
        return df
    except Exception:
        return None
