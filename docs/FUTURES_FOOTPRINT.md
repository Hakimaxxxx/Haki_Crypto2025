# 👣 Futures Footprint Chart - Order Flow Analysis

## 📊 Tổng quan

**Footprint Chart** là công cụ phân tích order flow (luồng lệnh) chuyên sâu cho futures trading. Khác với chart giá thông thường chỉ hiển thị OHLC, Footprint Chart cho bạn thấy **WHO is in control** - Buyers hay Sellers đang chiếm ưu thế tại từng mức giá.

### 🎯 Mục đích

Footprint Chart giúp trader nhìn thấy:
- 🟢 **Buy pressure zones** - Vùng mua mạnh (aggressive buying)
- 🔴 **Sell pressure zones** - Vùng bán mạnh (aggressive selling)
- ⚖️ **Volume imbalance (Delta)** - Chênh lệch volume giữa bid/ask
- 🎯 **Absorption zones** - Vùng giá hấp thụ volume lớn nhưng giá ít di chuyển
- 📈 **Trend strength** - Sức mạnh xu hướng qua cumulative delta

---

## 🔧 Features

### 1. **Footprint Heatmap** (Main Chart)
- Color-coded cells showing bid/ask delta at each price level
- 🟢 Green = Buy volume > Sell volume (bullish)
- 🔴 Red = Sell volume > Buy volume (bearish)
- ⚪ White = Balanced (neutral zone)

### 2. **Cumulative Delta Line**
- Running total of (Buy Volume - Sell Volume)
- Rising = Sustained buying pressure → Bullish trend
- Falling = Sustained selling pressure → Bearish trend
- Divergence with price = Warning signal

### 3. **Volume Profile (Horizontal Bars)**
- Shows total volume distribution by price level
- **POC (Point of Control)**: Price level with highest volume
- High Volume Nodes = Acceptance zones (strong S/R)
- Low Volume Nodes = Rejection zones (price moves through quickly)

### 4. **Real-time Metrics**
- Total Buy/Sell Volume
- Net Delta (Buy - Sell)
- Aggression Ratio (Buy/Sell)
- POC Price
- Latest Candle Delta

---

## 📡 Data Sources

### 1. **Binance Futures API** (Primary)
**Endpoint:** `GET /fapi/v1/aggTrades`

**Ưu điểm:**
- ✅ Fast response (<500ms)
- ✅ High limit (1000 trades per request)
- ✅ Accurate side determination (buyer is maker flag)
- ✅ No authentication required
- ✅ Free tier available

**Coverage:** BTC, ETH, SOL, BNB, ARB, OP, AVAX, và hầu hết major coins

### 2. **OKX Futures API** (Backup)
**Endpoint:** `GET /api/v5/market/trades`

**Ưu điểm:**
- ✅ Fast response
- ✅ Clean API design
- ✅ Good for altcoins

**Hạn chế:**
- ⚠️ Max 100 trades per request (lower than Binance)

### 3. **Bybit API** (Future support)
- Planned for additional coverage

---

## 🎨 Chart Types

### Type 1: Footprint Heatmap
```
Time →
Price
  ↓
┌─────┬─────┬─────┬─────┐
│ 🔴  │ 🟢  │ 🟢  │ 🟢  │  High
├─────┼─────┼─────┼─────┤
│ 🔴  │ ⚪  │ 🟢  │ 🟢  │  Mid
├─────┼─────┼─────┼─────┤
│ 🔴  │ 🔴  │ ⚪  │ 🟢  │  Low
└─────┴─────┴─────┴─────┘
 09:00 09:05 09:10 09:15
```

**Cách đọc:**
- Mỗi cell = 1 price level trong 1 candle
- Color intensity = Delta strength
- Dark green = Strong buy pressure
- Dark red = Strong sell pressure

### Type 2: Cumulative Delta
```
Cumulative Δ
     +1000 ━━━━━━━━━━━━━━╱
      +500 ━━━━━━━━╱━━━━━
         0 ━━━━━━
      -500 ━━━╲━━
     -1000     ╲━━━━━━━━━━
           Time →
```

**Cách đọc:**
- Rising = Buyers in control
- Falling = Sellers in control
- Flat = Balanced market

### Type 3: Volume Profile
```
Price
$111k ████████████ (POC)
$110k ███████
$109k ██████████
$108k ████
$107k ██
       Volume →
```

**Cách đọc:**
- Longest bar = POC (strongest S/R)
- High volume = Acceptance zone
- Low volume = Fast move zone

---

## 📈 Trading Applications

### 1. **Trend Confirmation**

**Bullish Trend:**
- ✅ Cumulative delta rising
- ✅ Green zones dominant at highs
- ✅ Large buy volume breaks resistance
- ✅ POC moving higher

**Bearish Trend:**
- ❌ Cumulative delta falling
- ❌ Red zones dominant at lows
- ❌ Large sell volume breaks support
- ❌ POC moving lower

### 2. **Reversal Signals**

**Bullish Reversal:**
- 🔄 Large green delta at lows (buying the dip)
- 🔄 Absorption: Price drops but big buy volume (support)
- 🔄 Cumulative delta rising while price falling (divergence)

**Bearish Reversal:**
- 🔄 Large red delta at highs (selling the rally)
- 🔄 Absorption: Price rises but big sell volume (resistance)
- 🔄 Cumulative delta falling while price rising (divergence)

### 3. **Support/Resistance Identification**

**Strong Support:**
- High volume green zone
- POC at this level
- Multiple absorption events

**Strong Resistance:**
- High volume red zone
- POC at this level
- Repeated rejection

### 4. **Order Flow Patterns**

#### Pattern A: Absorption
```
Price: $100k → $99.5k (small drop)
Volume: 500 BTC bought (large buy)
→ Signal: Strong support, likely reversal
```

#### Pattern B: Exhaustion
```
Price: Rising
Delta: Negative (selling into rally)
→ Signal: Trend weakness, watch for reversal
```

#### Pattern C: Iceberg Order
```
Price: Stuck at $100k
Volume: Repeated large buy orders
→ Signal: Institutional accumulation
```

---

## 🎓 Interpretation Guide

### Metrics Explained

#### 1. **Net Delta**
```
Net Delta = Total Buy Volume - Total Sell Volume

> 0: Bullish (buyers aggressive)
= 0: Neutral (balanced)
< 0: Bearish (sellers aggressive)
```

#### 2. **Aggression Ratio**
```
Aggression Ratio = Buy Volume / Sell Volume

> 1.0: Buyers more aggressive
= 1.0: Balanced
< 1.0: Sellers more aggressive

Example:
- Ratio = 1.5 → 50% more buying
- Ratio = 0.8 → 20% more selling
```

#### 3. **POC (Point of Control)**
```
POC = Price level with highest volume

Use cases:
- Strong S/R level
- Fair value zone
- Magnet for price action
```

#### 4. **Cumulative Delta Slope**
```
Slope > 0: Bullish pressure building
Slope = 0: Balanced, range-bound
Slope < 0: Bearish pressure building

Watch for divergence:
Price ↑ + Delta ↓ = Bearish divergence
Price ↓ + Delta ↑ = Bullish divergence
```

---

## ⚙️ Settings Guide

### Timeframe Selection
- **1min**: Scalping, intraday (very noisy)
- **5min**: Day trading (recommended)
- **15min**: Swing entry/exit
- **30min/1h**: Macro view

### Trade History Limit
- **100 trades**: Quick snapshot (~5-10 minutes of data)
- **500 trades**: Medium view (~30 minutes)
- **1000 trades**: Comprehensive view (~1-2 hours)

**Note:** More trades = More accurate but slower load time

### Price Bins
- Default: 50 bins
- Higher = More granular (see every small price level)
- Lower = Cleaner view (aggregate multiple levels)

---

## 🚨 Common Pitfalls

### ❌ Don't Do This:

1. **Trading footprint alone**
   - Always combine with price action & chart patterns
   - Use as confirmation, not sole signal

2. **Overtrading on noise**
   - 1min charts are very noisy
   - Wait for confluence with higher timeframes

3. **Ignoring market context**
   - Footprint shows current flow, not future direction
   - Check news, events, macro trends

4. **Misreading delta**
   - Positive delta ≠ Price will go up immediately
   - Negative delta ≠ Price will crash
   - Context matters!

5. **Using on illiquid coins**
   - Footprint works best on BTC, ETH (high volume)
   - Small coins = Wash trading distorts readings

### ✅ Best Practices:

1. **Confluence trading**
   ```
   Footprint + Price Action + S/R + Volume = High probability setup
   ```

2. **Focus on key levels**
   - Use footprint at S/R zones
   - Look for absorption/exhaustion at extremes

3. **Watch cumulative delta**
   - More reliable than single candle delta
   - Divergences are powerful signals

4. **Combine timeframes**
   - 15min for trend
   - 5min for entry
   - 1min for precise timing

---

## 🎯 Example Scenarios

### Scenario 1: Long Setup
```
Context: BTC at $108k (support level)
Footprint shows:
- Large green zone at $108k (absorption)
- Cumulative delta rising (+500 BTC)
- POC at $108k
- Latest delta: +50 BTC (buying)

Action: Enter long, stop below $107.5k
```

### Scenario 2: Short Setup
```
Context: ETH at $4,000 (resistance)
Footprint shows:
- Large red zone at $4,000 (rejection)
- Cumulative delta falling (-200 ETH)
- Price rising but delta negative (divergence)
- Latest delta: -30 ETH (selling)

Action: Enter short, stop above $4,020
```

### Scenario 3: Avoid Trade
```
Context: SOL consolidating
Footprint shows:
- Balanced delta (±0)
- Flat cumulative delta
- No clear zones
- Low volume

Action: Wait for breakout + delta confirmation
```

---

## 📚 Technical Details

### Data Structure
```python
{
    'candles': [
        {
            'start_time': datetime,
            'open': float,
            'high': float,
            'low': float,
            'close': float,
            'total_volume': float,
            'buy_volume': float,
            'sell_volume': float,
            'delta': float,
            'price_levels': [
                {
                    'price': float,
                    'buy_vol': float,
                    'sell_vol': float,
                    'delta': float,
                    'total_vol': float
                },
                ...
            ]
        },
        ...
    ]
}
```

### Calculation Method

#### 1. Trade Side Determination (Binance)
```python
# Binance aggTrades
if trade['m'] == False:  # Buyer is taker
    side = 'BUY'
else:  # Buyer is maker
    side = 'SELL'
```

#### 2. Price Binning
```python
bin_size = (high_price - low_price) / num_bins

for i in range(num_bins):
    bin_low = low_price + i * bin_size
    bin_high = bin_low + bin_size
    
    # Aggregate trades in this bin
    bin_trades = trades[(price >= bin_low) & (price < bin_high)]
    bin_buy_vol = bin_trades[side == 'BUY']['qty'].sum()
    bin_sell_vol = bin_trades[side == 'SELL']['qty'].sum()
    bin_delta = bin_buy_vol - bin_sell_vol
```

#### 3. Cumulative Delta
```python
cumulative_delta = []
running_total = 0

for candle in candles:
    running_total += candle['delta']
    cumulative_delta.append(running_total)
```

---

## 🔄 Workflow Integration

### Step 1: Market Analysis
1. Open Futures → Footprint Chart
2. Select coin (BTC/ETH recommended)
3. Choose exchange (Binance for most coins)
4. Set timeframe (5min for day trading)

### Step 2: Identify Zones
1. Look at Volume Profile
2. Note POC and high volume zones
3. Mark as S/R on your trading chart

### Step 3: Wait for Setup
1. Price approaches S/R zone
2. Check footprint for:
   - Absorption (support)
   - Rejection (resistance)
   - Delta divergence

### Step 4: Confirm Entry
1. Footprint shows strong delta
2. Cumulative delta confirms direction
3. Price action breaks/bounces
4. Enter trade with stop loss

### Step 5: Monitor
1. Watch cumulative delta
2. If delta reverses → Consider exit
3. Trail stop as profit grows

---

## 📊 Performance Tips

### Optimization
- **Cache enabled**: 60 second TTL
- **Parallel fetching**: Not needed (single exchange query)
- **Data limit**: Balance between accuracy and speed
  - 100 trades = ~0.5s load time
  - 1000 trades = ~2s load time

### Troubleshooting

**Problem:** No data showing
- ✅ Check coin has futures contract
- ✅ Try different exchange
- ✅ Ensure internet connection

**Problem:** Chart looks noisy
- ✅ Increase timeframe (5min → 15min)
- ✅ Reduce price bins (50 → 30)
- ✅ Fetch more trades for smoothing

**Problem:** Slow loading
- ✅ Reduce trade limit (1000 → 500)
- ✅ Wait for cache (60s TTL)
- ✅ Use Binance (faster than OKX)

---

## 🎉 Version History

### v1.0.0 (2025-10-31)
- ✅ Initial release
- ✅ Binance Futures API integration
- ✅ OKX Futures API backup
- ✅ Footprint heatmap with color-coded delta
- ✅ Cumulative delta line chart
- ✅ Volume profile horizontal bars
- ✅ Real-time metrics (buy/sell volume, delta, aggression ratio, POC)
- ✅ Multi-timeframe support (1m, 5m, 15m, 30m, 1h)
- ✅ 7 major coins supported (BTC, ETH, SOL, BNB, ARB, OP, AVAX)
- ✅ Comprehensive interpretation guide
- ✅ Integration into main Crypto2025.py app

---

## 🚀 Future Enhancements

### High Priority
- [ ] Bybit API integration
- [ ] Kraken Futures support
- [ ] WebSocket for real-time updates
- [ ] Alert system (delta threshold triggers)
- [ ] Export footprint data (CSV/JSON)

### Medium Priority
- [ ] Volume-weighted delta
- [ ] Intrabar analysis (sub-candle delta)
- [ ] Delta heatmap animation (replay)
- [ ] Custom color schemes
- [ ] Responsive POC tracking

### Low Priority
- [ ] Machine learning delta predictions
- [ ] Historical footprint database
- [ ] Multi-coin comparison
- [ ] TradingView integration

---

## 📖 References

### Learning Resources
- **Order Flow Trading** by Al Brooks
- **Footprint Charts Guide** by ATAS
- **Sierra Chart Footprint Documentation**
- **Market Profile** by J. Peter Steidlmayer

### Similar Tools
- **ATAS** (Advanced Time and Sales)
- **Sierra Chart Footprint**
- **Bookmap** (Order flow visualization)
- **TradingView Volume Profile**

---

## ⚠️ Disclaimer

**Risk Warning:**
- Footprint charts are a tool, not a crystal ball
- Past order flow ≠ Future price direction
- Always use stop losses
- Risk management is critical
- Futures trading is high risk

**Data Accuracy:**
- Real-time data from exchange APIs
- Subject to API rate limits
- May have minor delays
- Binance provides most accurate data

---

## 📞 Support

**Issues?**
1. Check this documentation first
2. Verify API connectivity
3. Try different exchange/coin
4. Check Streamlit console for errors
5. Review code in `metrics_futures_footprint.py`

**Feature Requests:**
- Add to GitHub issues
- Tag as `enhancement`
- Provide use case description

---

**Version:** 1.0.0  
**Date:** October 31, 2025  
**Status:** ✅ Production Ready  
**Author:** Crypto2025 Team  
**License:** Private Use
