# Liquidation Heatmap Improvements - Coinglass Style

## Overview

Upgraded liquidation heatmap with **Coinglass-style visualization** featuring:
1. ✅ **Extended historical data** (30+ days) vs old limit (1 day max)
2. ✅ **Separate Long/Short liquidations** with color coding
3. ✅ **Overlay on price chart** for context
4. ✅ **Clear visual distinction** between bull/bear liquidations

## Problem Statement (Before)

### Issue 1: Insufficient Data
- **OKX limitation**: Only recent liquidations (typically < 24 hours)
- **User complaint**: "Dữ liệu đầu vào từ OKX quá ít (không đủ thời gian tối thiểu 1 tháng)"
- **Impact**: Cannot see liquidation patterns over meaningful timeframes

### Issue 2: Poor Visualization
- **Old style**: Single-color heatmap (all liquidations look the same)
- **User complaint**: "Output không rõ ràng các lệnh kill long short trên heat map"
- **Impact**: Cannot distinguish between:
  - Long liquidations (bulls getting killed)
  - Short liquidations (bears getting killed)

### Issue 3: No Context
- **Old style**: Heatmap alone without price overlay
- **Result**: Hard to correlate liquidations with price movements
- **Coinglass advantage**: Price candles overlaid show WHY liquidations happened

## Solution: Coinglass-Style Heatmap

### Architecture

```
User selects coin detail page
    ↓
Liquidation Heatmap expander
    ↓
Choose style: [Coinglass ✓ | Classic]
    ↓
Select timeframe: [30D | 14D | 7D | 3D]
    ↓
fetch_liquidations_extended (OKX + extended sources)
    ↓
aggregate_liquidations_by_price_time
    ├─> Long Liquidation Matrix (Green zones)
    └─> Short Liquidation Matrix (Red zones)
    ↓
plot_coinglass_style_liquidation
    ├─> Heatmap Layer 1: Long liq (green, transparent → opaque)
    ├─> Heatmap Layer 2: Short liq (red, transparent → opaque)
    └─> Overlay Layer: Price candles (candlestick chart)
    ↓
Display in Streamlit with legends
```

### Key Features

#### 1. Extended Data (30+ Days)

**Implementation**:
```python
def fetch_binance_liquidations_extended(symbol, days=30):
    # Use OKX liquidation API with extended pagination
    from metrics_liquidation_okx import fetch_liquidations_multi
    
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=days)
    
    df = fetch_liquidations_multi(
        asset_symbol=base,
        start_dt=start_dt,
        end_dt=end_dt,
        sources=["OKX", "BINANCE"],  # Multi-source
        max_pages=100,  # Extended pagination
        overall_timeout=30.0  # Allow time for large requests
    )
```

**Result**:
- Before: ~1 day of data
- After: **30 days** (or more)
- Source: OKX extended pagination + fallback sources

#### 2. Long/Short Separation

**Color Coding**:
- 🟢 **Green zones**: Long liquidations (bulls killed)
  - When price drops → long positions liquidated
  - Forced selling pressure
  
- 🔴 **Red zones**: Short liquidations (bears killed)
  - When price pumps → short positions liquidated
  - Forced buying pressure

**Data Processing**:
```python
# Parse OKX posSide field
df['long_liq'] = df.apply(
    lambda x: x['size'] if x.get('posSide') == 'long' else 0,
    axis=1
)
df['short_liq'] = df.apply(
    lambda x: x['size'] if x.get('posSide') == 'short' else 0,
    axis=1
)
```

**Visualization**:
```python
# Two separate heatmap layers
fig.add_trace(go.Heatmap(
    z=long_matrix.values,
    colorscale=[[0, 'rgba(0,0,0,0)'], [1, 'rgba(76,175,80,0.7)']],  # Green
    name="Long Liquidations"
))

fig.add_trace(go.Heatmap(
    z=short_matrix.values,
    colorscale=[[0, 'rgba(0,0,0,0)'], [1, 'rgba(244,67,54,0.7)']],  # Red
    name="Short Liquidations"
))
```

#### 3. Price Overlay

**Integration**:
```python
# Fetch OHLCV data for same timeframe
from ohlcv_multi_source import fetch_binance_ohlcv_extended
df_price = fetch_binance_ohlcv_extended(symbol, interval='1h', days=days)

# Overlay as candlestick chart
fig.add_trace(go.Candlestick(
    x=df_price['datetime'],
    open=df_price['open'],
    high=df_price['high'],
    low=df_price['low'],
    close=df_price['close'],
    increasing_line_color='#26a69a',
    decreasing_line_color='#ef5350',
    opacity=0.8
))
```

**Benefit**:
- See **price context** around liquidations
- Identify liquidation cascades (price drops → more longs liquidated → price drops more)
- Spot support/resistance levels based on liquidation clusters

### UI Implementation

**Streamlit Integration** (`Crypto2025.py` lines ~2989-3185):

```python
# Style selection
heatmap_style = st.radio(
    "Liquidation Style",
    options=["Coinglass (Recommended)", "Classic"],
    index=0
)

# Timeframe selection
tframe = st.selectbox(
    "Khung thời gian",
    options=["30D", "14D", "7D", "3D"],
    index=0  # Default 30 days
)

# Coinglass mode
if heatmap_style == "Coinglass (Recommended)":
    fig_cg = plot_coinglass_style_liquidation(
        symbol=binance_symbol,
        days=days,
        price_bins=100,
        time_bins=72,
        threshold_percentile=50,
        show_price_overlay=True
    )
    st.plotly_chart(fig_cg, use_container_width=True)
    st.caption("🟢 Green: Long liq (bulls killed) | 🔴 Red: Short liq (bears killed)")
```

**Advanced Settings**:
- Price Resolution: 50-150 bins (default 100)
- Time Resolution: 24-96 bins (default 72)
- Threshold %: Only show top X% of liquidations (default 50%)
- Price Overlay: Toggle candlestick chart on/off

## Comparison: Old vs New

| Feature | Old (Classic) | New (Coinglass) |
|---------|--------------|----------------|
| **Data Range** | 1-3 days max | 30+ days ✅ |
| **Long/Short** | Mixed together ❌ | Separated (green/red) ✅ |
| **Price Context** | Optional line | Candlestick overlay ✅ |
| **Visual Clarity** | Single color (confusion) | Dual-color (clear) ✅ |
| **Data Source** | OKX only | OKX + extended sources ✅ |
| **Resembles Coinglass** | No | Yes ✅ |

## Example Use Cases

### 1. Spot Liquidation Cascades

**Scenario**: Price drops from $68K → $65K

**What to look for**:
- 🟢 **Green zones intensifying** as price drops
- Concentration at specific price levels ($67K, $66K, $65K)
- Pattern: Each drop triggers more long liquidations → more selling → price drops further

**Insight**: Identify weak support levels where many long positions clustered

### 2. Short Squeeze Detection

**Scenario**: Price pumps from $65K → $70K

**What to look for**:
- 🔴 **Red zones appearing** as price rises
- Concentration showing where shorts got trapped
- Pattern: Each pump triggers short liquidations → forced buying → price pumps more

**Insight**: Identify resistance levels that shorts failed to defend

### 3. Optimal Entry/Exit Points

**Strategy**: Enter when liquidations clear out weak hands

**Signals**:
- Heavy green zone → Many longs liquidated → Potential bottom
- Heavy red zone → Many shorts liquidated → Potential top
- Mix of both → Consolidation zone

## Technical Implementation

### Files Created

1. **`metrics_liquidation_coinglass_style.py`** (NEW - 300+ lines)
   - `fetch_binance_liquidations_extended()`: Multi-source liquidation fetcher
   - `aggregate_liquidations_by_price_time()`: Bin data into matrix
   - `plot_coinglass_style_liquidation()`: Main visualization function
   - `streamlit_coinglass_liquidation_ui()`: Standalone UI (optional)

2. **`Crypto2025.py`** (MODIFIED - lines 2989-3185)
   - Added style selection radio button
   - Integrated Coinglass option
   - Kept Classic option for backward compatibility
   - Shared timeframe selector

### Data Flow

```
OKX Liquidation API
    ├─> fetch_okx_liquidation_range() [existing]
    ├─> Extended pagination (max_pages=100)
    ├─> Parse posSide field (long/short)
    └─> Returns DataFrame with datetime, price, size, posSide

Aggregation
    ├─> Create price bins (100 levels)
    ├─> Create time bins (72 periods)
    ├─> Group by [price_bin, time_bin]
    ├─> Sum long_liq → long_matrix
    └─> Sum short_liq → short_matrix

Visualization
    ├─> Heatmap 1: long_matrix (green colorscale)
    ├─> Heatmap 2: short_matrix (red colorscale)
    ├─> Candlestick: OHLCV overlay
    ├─> HLine: Current price indicator
    └─> Plotly Dark theme
```

### Performance Optimization

**Caching Strategy** (future enhancement):
```python
@st.cache_data(ttl=300)  # 5-minute cache
def fetch_liquidations_cached(symbol, days):
    return fetch_binance_liquidations_extended(symbol, days)
```

**Benefits**:
- Avoid refetching same data on page refresh
- Reduce API calls to OKX
- Faster rendering

## Troubleshooting

### Issue: No liquidation data available

**Causes**:
1. OKX API rate limited
2. No liquidations occurred in timeframe
3. Symbol mapping error

**Solutions**:
1. Try shorter timeframe (14D → 7D)
2. Check different coin (BTC usually has most data)
3. Verify symbol format (e.g., BTC → BTCUSDT)

### Issue: Only one color showing

**Cause**: All liquidations are same direction (all long OR all short)

**Normal behavior**:
- Strong dump → Mostly green (long liquidations)
- Strong pump → Mostly red (short liquidations)
- Ranging market → Mix of both

### Issue: Heatmap too noisy

**Solution**: Increase threshold percentage
- Default 50% → Shows top half
- Set to 70% → Only top 30% liquidations
- Set to 90% → Only extreme liquidations

## Future Enhancements

1. **Real-time Updates**
   - WebSocket connection to OKX
   - Auto-refresh every 60 seconds
   - Animated liquidation waves

2. **Volume-Weighted Heatmap**
   - Size zones by USD value (price × quantity)
   - Show dollar impact, not just quantity

3. **Multi-Coin Overlay**
   - Compare BTC vs ETH liquidations
   - Correlation analysis

4. **Export Features**
   - Download heatmap as PNG
   - Export data as CSV
   - Share via link

5. **Smart Alerts**
   - Notify when liquidation threshold exceeded
   - Alert on cascade patterns
   - ML-based anomaly detection

## References

- **Coinglass**: https://www.coinglass.com/LiquidationData
- **OKX API Docs**: https://www.okx.com/docs-v5/en/#public-data-rest-api-get-liquidation-orders
- **Plotly Heatmaps**: https://plotly.com/python/heatmaps/

## Changelog

### 2025-10-29
- ✅ Created `metrics_liquidation_coinglass_style.py`
- ✅ Implemented dual-heatmap visualization (long/short separation)
- ✅ Extended data fetch (30+ days vs 1 day)
- ✅ Price candlestick overlay
- ✅ Integrated into Streamlit UI with style selector
- ✅ Added threshold filtering
- ✅ Documentation completed
