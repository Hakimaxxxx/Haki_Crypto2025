# Prompt: Add New Whale Alert Source

You are an AI coding agent working in this repository. Implement or extend whale alert monitoring for a new chain or token.

Inputs to expect
- Chain name and network (e.g., `SUI mainnet`, `SOL mainnet`)
- Provider options and credentials (RPC URL, indexer API keys)
- Token list or filter rules for what constitutes a "whale" transfer

Acceptance criteria
- A background scanner exists or is extended to collect whale events for the target chain
- Events are persisted to local JSON history and (optionally) to MongoDB via retry helpers
- Events are normalized by `services/whale/whale_loader.py`
- Overlay markers render on the per-coin OHLCV chart for affected symbols

Steps
1) Create or extend a scanner
- Location: `<CHAIN>/metrics_<chain>_whale_alert_realtime.py`
- Avoid heavy work at import; guard background startup with a function
- Read credentials from env (do not hardcode)
- Persist to a history file within the chain folder (and log to a `.log` file)

2) Normalize events for overlays
- Update or extend `services/whale/whale_loader.py` to read the chain's history file
- Ensure the output event shape includes timestamp, symbol, size/value, direction/type

3) UI overlay integration
- `Crypto2025.py` calls `phase0_overlay_whales(symbol, df_ohlcv, fig)`
- Confirm the loader returns events for that symbol and markers appear on the chart

4) Resilience & diagnostics
- Handle provider failures gracefully (retry/backoff)
- Provide a short diagnostic helper that prints provider selection and recent errors
- Add local file fallbacks to avoid import-time side effects

Validation checklist
- Run `python -m py_compile <CHAIN>/metrics_<chain>_whale_alert_realtime.py`
- Start Streamlit and toggle whale overlays for a coin linked to the chain
- Check the chain scanner log and history JSON update over time

Deliverables
- A PR adding/updating the scanner file, loader normalization, and optional docs
- Optional: an entry in `CHANGELOG_YYYY-MM-DD.md`
