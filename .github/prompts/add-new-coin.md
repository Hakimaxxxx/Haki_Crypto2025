# Prompt: Add New Coin

You are an AI coding agent working in this repository. Implement support for a new coin in the Streamlit app.

Inputs to expect
- CoinGecko ID (e.g., `bitcoin`)
- Symbol/ticker (e.g., `BTC`)

Acceptance criteria
- The coin appears as a new tab/expander in the UI automatically after update
- Prices load and aggregate into portfolio totals
- OHLCV and liquidation heatmap render with defaults
- Whale overlays are available if events exist for this symbol

Steps
1) Update `config.py`
- Add `(coingecko_id, symbol)` to `COIN_LIST`
- If needed, add any symbol-specific constants used elsewhere in the UI

2) Verify price fetching
- Ensure the coin is included in CoinGecko requests in `Crypto2025.py`
- Run a quick smoke check: compile `Crypto2025.py`

3) OHLCV and liquidation heatmap
- Ensure `metrics_ohlcv_okx.py` and `metrics_liquidation_okx.py` can fetch for the symbol
- If needed, add symbol-to-exchange mappings (pair names, markets)

4) Whale overlay integration (optional but preferred)
- If the chain has a whale scanner, ensure events are saved under a file the loader recognizes
- Normalize events through `services/whale/whale_loader.py`
- Confirm `phase0_overlay_whales()` renders markers for the symbol

Validation checklist
- Run `python -m py_compile Crypto2025.py`
- Start Streamlit and verify the new coin tab loads and renders price + heatmap
- Confirm no blocking errors if APIs fail (cached fallback works)

Deliverables
- A small PR updating `config.py` and any necessary symbol mapping
- Optional: brief note in `CHANGELOG_YYYY-MM-DD.md`
