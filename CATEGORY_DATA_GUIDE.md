# Hướng Dẫn Load REAL Cryptocurrency Data

## 🎯 Vấn Đề Hiện Tại
- Cache cũ có **fake data** (Fet Token 1, 2, 3...)
- Cần fetch **REAL coins** từ CoinGecko API (Bitcoin, Ethereum, Solana, etc.)

## ✅ Giải Pháp

### Option 1: Tự động fetch khi mở Streamlit (Khuyến nghị)
```bash
streamlit run Crypto2025.py
```
- Vào **Metrics** → **Category Performance**
- Lần đầu sẽ hiển thị: "⏳ First load: Fetching REAL coins..."
- Đợi ~40 giây để fetch 19 categories × 50 coins
- Sau đó data được cache 3 giờ

⚠️ **Lưu ý:** Nếu gặp rate limit, đợi 5-10 phút rồi click 🔄 Refresh

### Option 2: Pre-fetch data trước (Tránh đợi trong UI)
```bash
python fetch_real_categories.py
```
- Script sẽ fetch tất cả 19 categories
- Progress hiển thị realtime: `[1/19] OK layer-1: 50 coins`
- Hoàn thành: cache file được tạo
- Mở Streamlit → data load ngay lập tức

## 📊 Kết Quả Mong Đợi

### Treemap sẽ hiển thị:
- **19 categories** (L1, L2, DeFi, AI, Meme, Gaming, etc.)
- **Size**: Volatility-based (abs % change) → highlight hot sectors
- **Color**: Direction (+/- %)

### Drill-down sẽ có REAL coins:
- **Layer 1**: Bitcoin (BTC), Ethereum (ETH), Solana (SOL), Cardano (ADA), ...
- **DeFi**: Uniswap (UNI), Aave (AAVE), Maker (MKR), Curve (CRV), ...
- **Meme**: Dogecoin (DOGE), Shiba Inu (SHIB), Pepe (PEPE), ...
- **AI**: Fetch.ai (FET), Render (RNDR), The Graph (GRT), ...

## 🔧 Troubleshooting

### "Failed to load category data"
→ CoinGecko rate limit (50 calls/min)
→ Đợi 5-10 phút, click 🔄 Refresh

### "Only 3 categories loading"
→ Rate limit hit giữa chừng
→ Delete cache: `category_treemap_cache.json`
→ Đợi 10 phút, chạy lại

### Cache bị stuck với fake data
```bash
# Windows PowerShell
Remove-Item d:\Crypto\category_treemap_cache.json
python fetch_real_categories.py
```

## 📝 Technical Notes

- **API Endpoint**: CoinGecko `/coins/markets?category=...`
- **Rate Limit**: 50 calls/min (free tier)
- **Delay**: 2 seconds between requests
- **Cache TTL**: 3 hours
- **Coins per category**: Top 50 by market cap
