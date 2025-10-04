# Crypto Portfolio & Whale Alert System - AI Agent Guide

## Architecture Overview

This is a **Streamlit-based cryptocurrency portfolio tracker** with **real-time whale alert monitoring** across multiple blockchains. The system integrates MongoDB Atlas for cloud persistence with local JSON fallbacks and features a **robust initialization system** with graceful degradation.

### Core Components

- **`Crypto2025.py`**: Main Streamlit application with portfolio tracking and metrics dashboard
- **`app_init.py`**: **NEW** - Robust initialization system with multi-source data loading and conflict resolution
- **`cloud_db.py`**: MongoDB Atlas abstraction with automatic reconnection and fallback handling
- **`db_utils.py`**: Database operations with retry queuing and failure recovery mechanisms
- **`config.py`**: Central configuration for supported coins and file paths
- **`portfolio_history.py`**: Local caching and history management with TTL-based invalidation

### Blockchain-Specific Modules

Each blockchain has its own directory (`BTC/`, `SOL/`, `ERC20/`, `BNB/`) containing:
- `metrics_*_whale_alert_realtime.py`: Real-time whale transaction monitoring
- `*_cex_dex_wallets.py`: Known exchange and DEX wallet classifications
- Chain-specific utilities and on-chain data fetchers

## Initialization & Data Flow

### App Init Process
```python
# Initialize with robust error handling and fallbacks
from app_init import initialize_app, get_portfolio_data, get_price_data

success, message = initialize_app()
# Loads data in priority: DB → API → Local Files
```

### Data Source Priority
1. **MongoDB Atlas** (primary source of truth)
2. **CoinGecko/OKX APIs** (live price data)
3. **Local JSON files** (fallback/cache)

### Background Sync System
- Continuous 60-second sync cycles for both DB and API
- Automatic reconnection and exponential backoff on failures
- Thread-safe data access with mutex locks
- Error queue management (keeps last 10 errors)

## Development Patterns

### Database Operations
Always use the retry-enabled patterns from `db_utils.py`:
```python
# Pattern for database writes with fallback queuing
db_upsert_portfolio_docs_with_retry(db, docs)
db_retry_queue(db)  # Call periodically to process failed writes
```

### Portfolio Data Access
Use the new init system instead of direct file I/O:
```python
# OLD: Direct file access
with open("data.json", "r") as f: data = json.load(f)

# NEW: Robust data access with fallbacks
holdings, avg_prices = get_portfolio_data()
update_portfolio_data(new_holdings, new_avg_prices)
```

### Price Data Fetching
```python
# Get current prices with fallback handling
prices, price_changes = get_price_data()
```

### Error Handling Patterns
- **Database failures**: Automatic queuing and exponential backoff retry
- **API rate limits**: Graceful degradation with cached data
- **Import errors**: Safe fallback stubs for missing modules
- **Initialization failures**: Partial functionality with available data sources

## Health Monitoring

### System Status Panel
The app includes a health panel showing:
- Database connection status
- API service availability  
- Background sync activity
- Recent error messages
- Last sync timestamps

### Diagnostics Functions
```python
from app_init import get_app_state, get_cached_data

# Monitor system health
state = get_app_state()
print(f"DB Available: {state['db_available']}")
print(f"Errors: {state['errors']}")
```

## Common Operations

### Running the Application
```bash
streamlit run Crypto2025.py
```

### Database Cleanup
```bash
python cleanup_zero_values.py --uri "mongodb+srv://..." --db Crypto2025 --collection portfolio_history
```

### Adding New Coins
1. Update `COIN_LIST` in `config.py` with `(coingecko_id, symbol)` tuple
2. Restart app to automatically include in init system

### Testing & Debugging

Monitor the health panel for:
- Initialization status and data source availability
- Background sync activity and error patterns
- Database connection health and retry queue status

The new init system provides resilient operation even when individual services fail, ensuring the app remains functional with available data sources.