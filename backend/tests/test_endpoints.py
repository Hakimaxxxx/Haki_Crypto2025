import os, json
from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)

# Ensure price cache exists for test
if not os.path.exists('last_prices.json'):
    with open('last_prices.json', 'w', encoding='utf-8') as f:
        json.dump({"BTC": {"price": 50000}}, f)


def test_health():
    r = client.get('/health/')
    assert r.status_code == 200
    assert r.json()['status'] == 'ok'


def test_prices_spot():
    r = client.get('/prices/spot?symbols=BTC')
    assert r.status_code == 200
    data = r.json()
    assert 'prices' in data and 'BTC' in data['prices']


def test_ohlcv_endpoint():
    # This depends on local metrics_ohlcv_okx fetch; allow 404 if not present
    r = client.get('/ohlcv/BTC?bar=15m&limit=20')
    assert r.status_code in (200, 404)


def test_whales_endpoint():
    r = client.get('/whales/BTC?limit=20')
    assert r.status_code in (200, 404)
