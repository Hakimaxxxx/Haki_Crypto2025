from redis_cache import safe_json_load
for f in [
    'portfolio_history.json',
    'ohlcv_cache.json',
    'btc_whale_alert_history.json',
    'eth_whale_alert_history.json'
]:
    import os
    if os.path.exists(f):
        ok, data, err = safe_json_load(f)
        if not ok:
            print(f, 'BROKEN:', err[:400])
        else:
            print(f, 'OK type:', type(data), 'len:', (len(data) if hasattr(data,'__len__') else 'n/a'))