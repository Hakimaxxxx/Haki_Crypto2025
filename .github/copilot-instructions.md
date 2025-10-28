# Crypto Portfolio & Whale Alert System - AI Agent Guide

This is a Streamlit-based cryptocurrency portfolio tracker with real-time whale alert monitoring across multiple blockchains. It integrates MongoDB Atlas for cloud persistence, falls back to local JSON files, and features a robust initialization system with graceful degradation.

Key docs for humans and agents
- Development guide: see `docs/Development.md` for local setup, environment variables, and workflows.
- Architecture overview: see `docs/Architecture.md` for the system architecture, data flow, and module map.
- Issue resolution history: see `docs/ISSUE_RESOLUTION_2025-10-04.md` and other docs in `docs/` folder.
- Prompt templates for automation: see `.github/prompts` for guided prompts to add coins or whale alerts.

Core components
- `Crypto2025.py` — Main Streamlit application with portfolio tracking, liquidation heatmaps, and whale overlays.
- `app_init.py` — Initialization with multi-source loading (DB → API → local) and conflict resolution.
- `cloud_db.py` — MongoDB Atlas abstraction with automatic reconnection and fallback handling.
- `db_utils.py` — Database operations with retry queuing and failure recovery.
- `config.py` — Central configuration (supported coins via `COIN_LIST`, file paths).
- `portfolio_history.py` — Local caching and history management with TTL-based invalidation.
- Metrics & data modules — e.g., `metrics_liquidation_okx.py`, `metrics_ohlcv_okx.py`, `overlay_whale_alert.py`.
- Chain scanners — folders like `SUI/`, `SOL/`, `BTC/`, `BNB/` contain `metrics_*_whale_alert_realtime.py` and wallet classifiers.

Initialization & data flow
- App init pattern:
	```python
	from app_init import initialize_app, get_portfolio_data, get_price_data
	success, message = initialize_app()  # Loads in priority: DB → API → Local files
	```
- Data source priority:
	1) MongoDB Atlas
	2) CoinGecko / OKX APIs
	3) Local JSON files (fallback/cache)
- Background sync: 60-second cycles, exponential backoff, thread-safe data access, error queue keeps last 10 errors.

Development patterns & conventions
- Use `db_utils` retry helpers for DB writes (e.g., `db_upsert_portfolio_docs_with_retry`) and run `db_retry_queue` periodically.
- Prefer `app_init.get_portfolio_data()` over direct file I/O; update via `update_portfolio_data()`.
- Fetch current prices via `get_price_data()`; OHLCV via cached helpers in `Crypto2025.py` (e.g., `fetch_okx_ohlcv_cached`).
- Avoid import-time side effects: some scanner modules spin up threads or probe network at import. Use lazy imports or simple JSON reads for fallbacks.

Health monitoring
- The app has a health panel exposing DB connection, API availability, background sync status, recent errors, and last sync timestamps.
- Diagnostics helpers:
	```python
	from app_init import get_app_state, get_cached_data
	state = get_app_state()
	print("DB Available:", state.get("db_available"))
	print("Errors:", state.get("errors"))
	```

Common operations
- Run the app:
	```bash
	streamlit run Crypto2025.py
	```
- Cleanup DB zeros:
	```bash
	python cleanup_zero_values.py --uri "mongodb+srv://..." --db Crypto2025 --collection portfolio_history
	```
- Add a new coin:
	1) Update `COIN_LIST` in `config.py` with `(coingecko_id, symbol)`
	2) Restart app (init system auto-includes)

Testing & debugging
- Use the health panel and logs to spot initialization status, retries, and API/DB issues.
- Streamlit caching reduces API pressure; when APIs fail, the app uses cached/local data for resilience.

Notes
- Secrets via env vars (e.g., `MONGO_URI`, `CLOUD_DB_NAME`, chain indexer keys like `BLOCKBERRY_API_KEY`, `SUI_RPC_URL`).
- For advanced developer setup and architecture diagrams, see `Development.md` and `Architecture.md`.