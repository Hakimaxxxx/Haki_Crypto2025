# Architecture Overview

This document explains the high-level architecture, data flow, and key modules of the Crypto2025 application.

## System components
- Front-end UI: Streamlit app in `Crypto2025.py`
- Data sources:
  - MongoDB Atlas (primary persistence)
  - Public APIs (CoinGecko, OKX)
  - Local JSON/CSV caches (fallback and history)
- Background services:
  - Chain whale scanners (e.g., `SUI/metrics_sui_whale_alert_realtime.py`)
  - Periodic data recorders (portfolio snapshots, market metrics)
- Services layer:
  - `services/whale/whale_loader.py` — unify whale events for overlays
  - `services/ohlcv/ohlcv_loader.py` — candle loaders (if present)

## Data flow
1. Initialization (`app_init.initialize_app`):
   - Try MongoDB → if unavailable, use API → else use local files
   - Merge and reconcile data, populate session cache and local caches
2. UI render (`Crypto2025.py`):
   - Prefetch OHLCV for coins, render per-coin tabs
   - Build liquidation heatmap and overlays
   - Display portfolio metrics and health panel
3. Background updates:
   - Every ~60s, refresh prices and write portfolio history
   - Whale scanners append events to local JSON and (optionally) DB
   - Retry queue flushes DB writes when connectivity resumes

## Modules and responsibilities
- `Crypto2025.py`
  - Orchestrates the UI, calls cached fetchers, renders charts
  - Hosts controls for timeframe, bins, thresholds, color scales
  - Invokes whale overlay helpers and shows health status
- `app_init.py`
  - Bootstrap logic with source priority (DB → API → local)
  - Provides getters/setters for portfolio state
  - Exposes diagnostics (app state, cached data)
- `cloud_db.py`
  - DB client and reconnection policies
  - Thin layer used by `db_utils` for resilience
- `db_utils.py`
  - Retry queue, backoff, and safe upsert helpers
  - Common entry points for writes from UI and background
- `metrics_*`
  - Fetch and compute specific metrics (liquidation, OHLCV, dominance, etc.)
- Chain scanners (`SUI/`, `SOL/`, `BTC/`, `BNB/`)
  - Real-time whale detection per chain
  - Write to local history and (optionally) DB
  - Avoid heavy work at import; start via guarded functions
- `overlay_whale_alert.py`
  - Convert normalized whale events into Plotly markers
  - Integrate with OHLCV charts to visualize event timing

## Caching and resilience
- Streamlit cache applied to heavy network calls
- Local JSON caches used when APIs fail
- DB writes queued with retry to avoid data loss
- UI guards to avoid blocking when sources are down

## Extensibility
- Adding a coin: edit `config.COINE_LIST` (tuple `(coingecko_id, symbol)`), UI loops auto-include
- Adding a whale source: implement/extend chain scanner, normalize via `whale_loader`, overlay via `overlay_whale_alert`
- Adding metrics: create `metrics_*.py` and plug into the UI

## Security & secrets
- All keys via environment variables: `MONGO_URI`, `CLOUD_DB_NAME`, chain RPC/indexer keys
- Never commit secrets to the repo; avoid hardcoding API keys in code

## Known considerations
- Some modules may start threads at import; prefer lazy init
- API limits require caching to maintain performance
- Filesystem paths should resolve within repo root; ensure directories exist before writing
