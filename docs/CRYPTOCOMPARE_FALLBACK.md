# CryptoCompare Fallback Implementation

## Overview
Thêm CryptoCompare API làm backup khi CoinGecko bị rate limit (429 Too Many Requests).

## Changes Made

### 1. Altcoin Season Index
**File:** `metrics_altcoin_season.py`, `altcoin_season_cryptocompare.py`

#### Primary Source: CoinGecko
- Historical prices (90 days)
- Top 100 coins by market cap
- Rate limit: ~3 phút (50 coins × 3.2s aggressive throttling)

#### Fallback Source: CryptoCompare
- Historical daily OHLC data (90 days)
- Top list endpoint (no CoinGecko dependency)
- Rate limit: ~30 giây (50 coins × 0.5s)
- Free tier: 100,000 calls/month

#### Auto-Fallback Flow:
```python
fetch_altcoin_season_index():
    1. Try CoinGecko (primary)
    2. On 429/error → Try CryptoCompare
    3. On both fail → Return index=50 (neutral)
```

#### UI Enhancements:
- 5-column metrics display
- Data source indicator: 🦎 CoinGecko / 📊 CryptoCompare
- Updated documentation in interpretation section

### 2. RSI Universe Fetching
**File:** `metrics_rsi.py`

#### Primary Source: CoinGecko
- `/coins/markets` endpoint
- Top 250 coins by market cap
- Filtered by top30/top50/portfolio/all

#### Fallback Source: CryptoCompare
- `/data/top/mktcapfull` endpoint
- Top 100 coins by market cap
- Auto-fallback on 429 rate limit

#### Function: `get_universe_from_config()`
```python
Before:
- Only CoinGecko
- Silent failure on rate limit
- Return empty list []

After:
- Try CoinGecko first
- Auto-fallback to CryptoCompare on 429
- Console logging for debugging
- Returns: [{'symbol': str, 'market_cap_usd': float}, ...]
```

## API Comparison

| Feature | CoinGecko | CryptoCompare |
|---------|-----------|---------------|
| Free tier | 10-50 calls/min | 100K calls/month |
| Historical data | 90 days | Unlimited |
| Rate limiting | Aggressive (429) | Generous |
| API key required | No | No |
| Top coins list | ✅ Markets endpoint | ✅ Top mktcap endpoint |
| Response time | Fast | Fast |

## Files Modified

1. **`metrics_altcoin_season.py`**
   - Added `fetch_altcoin_season_index()` wrapper
   - Renamed `calculate_altcoin_season_index()` → `_fetch_from_coingecko()`
   - Auto-fallback logic
   - UI: 5-column metrics with data source

2. **`altcoin_season_cryptocompare.py`** (renamed from `altcoin_season_coinpaprika.py`)
   - CryptoCompare API implementation
   - `/data/v2/histoday` for historical prices
   - `/data/top/mktcapfull` for top coins list
   - 90-day performance calculation

3. **`metrics_rsi.py`**
   - Added `from pathlib import Path`
   - Enhanced `get_universe_from_config()` with fallback
   - Console logging for debugging
   - Handles both CoinGecko and CryptoCompare response formats

## Testing

### Test Files Created:
1. **`test_altcoin_season.py`** - Test CoinGecko primary source
2. **`test_coinpaprika.py`** - Test CryptoCompare fallback
3. **`test_rsi_universe.py`** - Test RSI universe with fallback

### Test Results:
```bash
# RSI Universe Test
python test_rsi_universe.py

Output:
- top30: ✓ CoinGecko (30 coins)
- top50: ✓ CoinGecko (50 coins)  
- all: ✓ CryptoCompare fallback (98 coins) - CoinGecko 429
```

## Usage

### Automatic (No code changes needed)
The fallback is transparent - just use existing functions:

```python
# Altcoin Season Index
from metrics_altcoin_season import fetch_altcoin_season_index
index, data, success = fetch_altcoin_season_index()
print(f"Data source: {data.get('data_source')}")  # 'CoinGecko' or 'CryptoCompare'

# RSI Universe
from metrics_rsi import get_universe_from_config
coins = get_universe_from_config('top50')
# Automatically tries CryptoCompare if CoinGecko fails
```

### Monitoring
Check console logs for source being used:
```
[RSI Universe] ✓ Fetched from CoinGecko
[RSI Universe] CoinGecko rate limited (429), trying CryptoCompare fallback...
[RSI Universe] ✓ Fetched 100 coins from CryptoCompare
```

## Benefits

1. **Resilience**: App continues working when CoinGecko rate limited
2. **Performance**: CryptoCompare often faster (0.5s vs 3.2s per call)
3. **Transparency**: UI shows which source was used
4. **Zero config**: Auto-fallback with no user intervention
5. **Debugging**: Console logs show source switching

## Rate Limit Mitigation

### CoinGecko (Primary):
- Aggressive throttling: 3.2s per call
- Still hits 429 after ~10-15 calls
- Best for: Light usage, cached data

### CryptoCompare (Fallback):
- Conservative throttling: 0.5s per call
- 100K calls/month = ~3,300 calls/day
- Best for: Heavy usage, real-time updates

## Future Improvements

1. Add user preference to choose source manually
2. Implement smart caching across both sources
3. Add retry logic with exponential backoff
4. Monitor API usage metrics
5. Consider paid tier for CoinGecko if needed

## Deployment Notes

- No API keys required (both free tier)
- No environment variables needed
- Works immediately after deployment
- Cache still effective (1 hour TTL)
- Logs visible in console for debugging
