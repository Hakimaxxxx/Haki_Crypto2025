# Development Guide

This guide helps developers set up the project locally, understand key workflows, and contribute safely.

## Prerequisites
- Python 3.10+ (dev container already includes Python and pip)
- Streamlit (installed via `requirements.txt`)
- MongoDB Atlas connection string (optional for read/write DB features)
- Optional chain provider keys: `BLOCKBERRY_API_KEY`, `SUI_RPC_URL`, and others per chain

## Environment setup
1. Create a virtual environment (optional when using the dev container).
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Configure environment variables (put in `.env` or Codespaces secrets):
- `MONGO_URI` — MongoDB Atlas connection string
- `CLOUD_DB_NAME` — database name
- Chain providers (as available):
  - `BLOCKBERRY_API_KEY` — SUI BlockBerry indexer key
  - `SUI_RPC_URL` — SUI RPC endpoint
  - Add other chain keys as needed (SOL, ETH, etc.)

## Running the app
```bash
streamlit run Crypto2025.py
```

If running outside the dev container, add flags to relax CORS/XSFR locally:
```bash
streamlit run Crypto2025.py --server.enableCORS false --server.enableXsrfProtection false
```

## Project structure (high level)
- `Crypto2025.py` — main Streamlit UI and orchestration
- `app_init.py` — initialization and data bootstrap (DB → API → local)
- `cloud_db.py` — DB client factory and reconnection helper
- `db_utils.py` — retry queue and safe DB write helpers
- `portfolio_history.py` — local caching and history management
- `metrics_*` — metrics modules for OHLCV, dominance, liquidation, etc.
- `overlay_whale_alert.py` — render whale markers on OHLCV charts
- `SUI/`, `SOL/`, `BTC/`, `BNB/` — chain-specific scanners and wallet lists
- `services/` — shared loaders (whales, ohlcv) and utilities

## Common workflows
### Add a new coin
1. Update `COIN_LIST` in `config.py` with `(coingecko_id, symbol)`
2. If the coin needs a new whale scanner, follow the whale alert workflow below
3. Restart the app to include the coin in UI and price fetching

### Add a new whale alert source
1. Add a `metrics_<CHAIN>_whale_alert_realtime.py` in the chain folder or update existing
2. Ensure safe import: avoid long network calls at import-time; start background thread lazily
3. Persist events to local JSON (history) and optionally DB via `db_utils`
4. Normalize events via `services/whale/whale_loader.py` for overlays
5. Render markers with `overlay_whale_alert.py`

### Database operations (safe pattern)
- Use `db_utils.db_upsert_portfolio_docs_with_retry(db, docs)` for writes
- Periodically call `db_utils.db_retry_queue(db)` to flush queued operations

## Conventions and tips
- Use caching decorators in `Crypto2025.py` for heavy network calls
- Prefer `app_init` helpers to read/write portfolio state over direct file I/O
- Avoid starting background threads at module import — use a guard or function
- Keep chain keys in environment; don’t hardcode secrets

## Quick checks
- Syntax check a file:
```bash
python -m py_compile Crypto2025.py
```
- Tail SUI scanner logs:
```bash
tail -n 200 SUI/sui_whale_scanner.log
```
- Inspect last prices cache:
```bash
cat last_prices.json | head
```

## Troubleshooting
- API rate limits: rely on cached data; verify `ohlcv_cache.json` and `last_prices.json`
- DB unavailable: app should continue with local JSON; check `MONGO_URI` and network
- Whale overlays missing: ensure OHLCV/figure context exists and events are loaded via `whale_loader`

## Contribution
- Keep PRs small and focused
- Add or update small unit scripts for loaders/scanners when making changes
- Follow retry/caching patterns to avoid UI blocking
