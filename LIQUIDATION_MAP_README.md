# 🔥 Liquidation Map - Quick Start

## Truy cập trong App

**Option 1: Trong Crypto2025 App**
```bash
streamlit run Crypto2025.py
```
→ Sidebar: **Futures** → Metric: **Liquidation Map**

**Option 2: Standalone Test**
```bash
streamlit run tests/test_streamlit_liqmap.py
```

## Features

✅ **Multi-Exchange**: Binance + Bybit + OKX (beta)  
✅ **Real-time OI**: Long/Short ratio live  
✅ **Coinglass Style**: Professional visualization  
✅ **Customizable**: Leverage levels, price range  
✅ **Tiếng Việt**: Full Vietnamese guide  

## Quick Example

```python
from metrics_liquidation_map import plot_liquidation_map

fig = plot_liquidation_map(
    symbol='BTC',
    exchange='total',  # All exchanges combined
    leverage_levels=[10, 25, 50, 100],
    price_range_pct=10.0
)

fig.show()
```

## Cách đọc

- 🔴 **Left (Red)**: Long liquidations khi giá GIẢM ↓
- 🟢 **Right (Green)**: Short liquidations khi giá TĂNG ↑
- ⚪ **Middle (White line)**: Current price
- **Bar height**: Liquidation amount

## Docs

📖 Full documentation: `docs/LIQUIDATION_MAP.md`  
✅ Completion report: `docs/LIQUIDATION_MAP_COMPLETION.md`

## Test Results

```
✅ Binance: Working
✅ Bybit: Working  
⚠️ OKX: Minor API issue (non-critical)
✅ Chart Generation: Success
✅ Streamlit UI: Ready
```

App is live at: http://localhost:8501
