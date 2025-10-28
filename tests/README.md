# Tests Directory

This directory contains all test scripts for the Crypto Portfolio & Whale Alert System.

## 🧪 Test Categories

### Initialization & Core
- **test_init.py** - App initialization and bootstrap tests
- **test_final_verification.py** - End-to-end verification tests

### Portfolio & Data
- **test_portfolio_form.py** - Portfolio form UX tests
- **test_price_mapping.py** - Price data mapping tests
- **test_missing_coins.py** - Missing coin detection tests

### Metrics & Analytics
- **test_metrics_dominance.py** - BTC dominance metric tests
- **test_fear_greed.py** - Fear & Greed index tests
- **test_category_treemap.py** - Category performance tests
- **test_etf_auto_update.py** - ETF flow auto-update tests
- **test_coin_metrics.py** - Coin metrics API tests

### Futures & Trading
- **test_funding_rate.py** - Funding rate metric tests
- **test_open_interest.py** - Open interest metric tests
- **test_liquidations.py** - Liquidations metric tests
- **test_ada_futures.py** - ADA futures specific tests

### Technical Indicators
- **test_rsi_sync.py** - RSI background sync tests
- **test_ohlcv_fixed.py** - OHLCV data fetching tests
- **test_timeframe.py** - Timeframe handling tests

### Whale Alerts
- **test_overlay_whale_alert.py** - Whale alert overlay tests
- **test_whale_overlay_fix.py** - Whale overlay bug fixes
- **test_whale_ohlcv.py** - Whale alert OHLCV integration
- **test_sol_whale_scanner.py** - Solana whale scanner tests
- **test_fetch_block_369810960.py** - Specific block fetch test

### Backend & Infrastructure
- **test_backend_validation.py** - Backend API validation
- **test_background_crawlers.py** - Background crawler tests
- **test_redis_whalealert.py** - Redis whale alert tests
- **test_overlay.py** - Overlay module tests

## 🚀 Running Tests

### Run a single test:
```bash
# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Run specific test
python tests/test_rsi_sync.py
```

### Run all tests in a category:
```bash
# Example: Run all whale alert tests
python tests/test_overlay_whale_alert.py
python tests/test_whale_overlay_fix.py
python tests/test_whale_ohlcv.py
```

### Run with pytest (if installed):
```bash
pytest tests/
pytest tests/test_rsi_sync.py -v
```

## 📝 Adding New Tests

When creating new test files:

1. **Naming convention**: `test_<feature_name>.py`
2. **Location**: Place in this `tests/` directory
3. **Structure**: Follow existing test patterns
4. **Documentation**: Add entry to this README

### Example test template:
```python
"""
Test for [Feature Name]

Tests:
- Feature behavior A
- Feature behavior B
- Edge cases
"""

def test_feature_basic():
    # Test basic functionality
    pass

def test_feature_edge_cases():
    # Test edge cases
    pass

if __name__ == "__main__":
    test_feature_basic()
    test_feature_edge_cases()
    print("All tests passed!")
```

## 🔍 Test Coverage

Tests cover:
- ✅ Core initialization and data loading
- ✅ Portfolio management and forms
- ✅ Price data and metrics
- ✅ Futures trading indicators
- ✅ Technical analysis (RSI, OHLCV)
- ✅ Whale alert detection and overlay
- ✅ Backend API integration
- ✅ Background sync processes

## 📊 Test Results

Run `test_final_verification.py` for comprehensive system check.

## 🐛 Debugging Failed Tests

1. Check error messages in console
2. Verify environment variables (MONGO_URI, API keys)
3. Ensure dependencies installed: `pip install -r requirements.txt`
4. Check MongoDB connection
5. Review recent code changes

## 🔗 Related Documentation

- [Development Guide](../docs/Development.md)
- [Architecture](../docs/Architecture.md)
- [Issue Resolution](../docs/ISSUE_RESOLUTION_2025-10-04.md)
