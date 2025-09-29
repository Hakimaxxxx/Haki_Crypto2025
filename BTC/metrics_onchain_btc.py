import requests
import pandas as pd
import os
import json

def fetch_btc_onchain_data(days=90, save_path="coin_data/btc_onchain.json"):
    """
    Crawl market cap và realized cap của Bitcoin từ CoinGecko, lưu vào file json.
    """
    # Market cap history
    url_chart = f"https://api.coingecko.com/api/v3/coins/bitcoin/market_chart?vs_currency=usd&days={days}"
    r = requests.get(url_chart, timeout=15)
    data = r.json()
    df_mcap = pd.DataFrame(data['market_caps'], columns=['timestamp', 'market_cap'])
    df_mcap['date'] = pd.to_datetime(df_mcap['timestamp'], unit='ms').dt.strftime('%Y-%m-%d')
    df_mcap = df_mcap.groupby('date').last().reset_index()

    # Realized cap (current value, not history)
    url_info = "https://api.coingecko.com/api/v3/coins/bitcoin?localization=false"
    r2 = requests.get(url_info, timeout=15)
    data2 = r2.json()
    realized_cap = None
    if 'market_data' in data2 and 'realized_market_cap' in data2['market_data']:
        realized_cap = data2['market_data']['realized_market_cap'].get('usd')
    if realized_cap is None:
        # fallback: dùng market cap hiện tại nếu không có realized cap
        realized_cap = data2['market_data']['market_cap'].get('usd') if 'market_data' in data2 and 'market_cap' in data2['market_data'] else None
    if realized_cap is None:
        realized_cap = 0
    # Gán realized cap hiện tại cho tất cả ngày (do API không có lịch sử realized cap)
    df_mcap['realized_cap'] = realized_cap

    # Lưu file
    out = {
        "market_cap": df_mcap[['date', 'market_cap']].values.tolist(),
        "realized_cap": df_mcap[['date', 'realized_cap']].values.tolist()
    }
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    with open(save_path, "w") as f:
        json.dump(out, f)
    return save_path

def get_btc_onchain_df():
    file_path = "coin_data/btc_onchain.json"
    if not os.path.exists(file_path):
        fetch_btc_onchain_data()
    with open(file_path, "r") as f:
        data = json.load(f)
    df = pd.DataFrame({
        "date": [x[0] for x in data["market_cap"]],
        "market_cap": [x[1] for x in data["market_cap"]],
        "realized_cap": [x[1] for x in data["realized_cap"]]
    })
    return df

def get_btc_realized_price():
    df = get_btc_onchain_df()
    # Realized price = realized cap / supply
    url_info = "https://api.coingecko.com/api/v3/coins/bitcoin?localization=false"
    r = requests.get(url_info, timeout=15)
    data = r.json()
    supply = data['market_data'].get('circulating_supply') if 'market_data' in data else None
    realized_cap = None
    if 'market_data' in data and 'realized_market_cap' in data['market_data']:
        realized_cap = data['market_data']['realized_market_cap'].get('usd')
    if realized_cap is None:
        realized_cap = data['market_data']['market_cap'].get('usd') if 'market_data' in data and 'market_cap' in data['market_data'] else None
    if realized_cap is None or not supply:
        return None
    realized_price = realized_cap / supply if supply > 0 else None
    return realized_price

# Returns (realized_price, mvrv) for BTC using CoinGecko API (live)
def get_btc_mvrv():
    url_info = "https://api.coingecko.com/api/v3/coins/bitcoin?localization=false"
    try:
        r = requests.get(url_info, timeout=15)
        data = r.json()
        market_cap = data['market_data']['market_cap'].get('usd') if 'market_data' in data and 'market_cap' in data['market_data'] else None
        realized_cap = data['market_data']['realized_market_cap'].get('usd') if 'market_data' in data and 'realized_market_cap' in data['market_data'] else None
        supply = data['market_data'].get('circulating_supply') if 'market_data' in data else None
        if realized_cap is None:
            realized_cap = market_cap
        realized_price = realized_cap / supply if realized_cap and supply and supply > 0 else None
        mvrv = market_cap / realized_cap if market_cap and realized_cap and realized_cap > 0 else None
        return realized_price, mvrv
    except Exception:
        return None, None
