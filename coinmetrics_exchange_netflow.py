import requests
import pandas as pd

def fetch_coinmetrics_exchange_netflow(asset='btc', start='2022-09-28', end='2025-09-28', api_key=None):
    """
    Lấy dữ liệu exchange netflow (inflow, outflow, netflow) từ CoinMetrics API cho 1 coin.
    - asset: mã coin (btc, eth, sol, ...)
    - start, end: định dạng YYYY-MM-DD
    - api_key: nếu có, truyền vào để tăng quota
    Trả về DataFrame với các cột: date, inflow, outflow, netflow
    """
    url = f"https://api.coinmetrics.io/v4/timeseries/asset-metrics"
    metrics = [
        'TxTfrValInExUSD',   # Inflow USD
        'TxTfrValOutExUSD',  # Outflow USD
    ]
    params = {
        'assets': asset,
        'metrics': ','.join(metrics),
        'frequency': '1d',
        'start_time': start,
        'end_time': end
    }
    headers = {}
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'
    r = requests.get(url, params=params, headers=headers, timeout=20)
    r.raise_for_status()
    data = r.json()
    if 'data' not in data or not data['data']:
        return None
    df = pd.DataFrame(data['data'])
    df['date'] = pd.to_datetime(df['time'])
    df['inflow'] = pd.to_numeric(df['TxTfrValInExUSD'], errors='coerce')
    df['outflow'] = pd.to_numeric(df['TxTfrValOutExUSD'], errors='coerce')
    df['netflow'] = df['inflow'] - df['outflow']
    return df[['date', 'inflow', 'outflow', 'netflow']]

# Ví dụ sử dụng:
if __name__ == "__main__":
    df = fetch_coinmetrics_exchange_netflow('btc', start='2024-09-28', end='2025-09-28')
    print(df.head())
