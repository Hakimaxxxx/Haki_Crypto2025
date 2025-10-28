# Hướng dẫn cập nhật ETF Flow hàng ngày

## 📊 Nguồn dữ liệu

### 1. Farside Investors (Khuyến nghị - Miễn phí)
- **BTC ETF**: https://farside.co.uk/btc/
- **ETH ETF**: https://farside.co.uk/eth/
- Cập nhật hàng ngày, data rõ ràng theo từng ETF provider
- Dễ copy/paste

### 2. CoinMarketCap (Dễ nhìn)
- **BTC ETF**: https://coinmarketcap.com/currencies/bitcoin/etf/
- **ETH ETF**: https://coinmarketcap.com/currencies/ethereum/etf/
- Có cả Net Flow và Total AUM
- Chart visual đẹp

### 3. CoinShares (Báo cáo tuần)
- https://coinshares.com/research/digital-asset-fund-flows
- Professional reports, data chi tiết
- Update weekly (thường thứ 2)

---

## 🔄 Cách cập nhật

### Bước 1: Lấy data mới nhất
1. Truy cập Farside hoặc CoinMarketCap
2. Xem data ngày hôm nay hoặc ngày gần nhất
3. Ghi lại 4 con số:
   - **BTC Net Flow** (USD)
   - **ETH Net Flow** (USD)
   - **BTC Total AUM** (USD)
   - **ETH Total AUM** (USD)

**Ví dụ từ CoinMarketCap (Oct 24, 2025):**
- BTC: +$91M flow, $149.36B AUM
- ETH: -$94M flow, $22.58B AUM

### Bước 2: Update file CSV
Mở file `etf_flow_history.csv` và thêm dòng mới:

```csv
date,btc_flow_usd,eth_flow_usd,btc_aum_usd,eth_aum_usd
...existing data...
2025-10-27,120000000,-50000000,149480000000,22530000000
```

**Lưu ý format:**
- **date**: YYYY-MM-DD (ví dụ: 2025-10-27)
- **flow**: Số nguyên, dương = inflow, âm = outflow
  - Ví dụ: +$91M → `91000000`
  - Ví dụ: -$94M → `-94000000`
- **aum**: Số nguyên, total assets
  - Ví dụ: $149.36B → `149360000000`

### Bước 3: Reload app
1. Vào trang Metrics → ETF Flow
2. Click nút **"🔄 Refresh"**
3. Kiểm tra data mới hiển thị

---

## 📝 Template nhanh

File `etf_flow_template.csv` có sẵn format mẫu:

```csv
date,btc_flow_usd,eth_flow_usd,btc_aum_usd,eth_aum_usd
2025-10-24,91000000,-94000000,149360000000,22580000000
2025-10-25,150000000,50000000,149510000000,22630000000
```

Copy dòng cuối, sửa ngày và số liệu, paste vào `etf_flow_history.csv`

---

## 💡 Tips

### Tính AUM từ flow
Nếu chỉ có flow, tính AUM:
```
AUM_today = AUM_yesterday + Flow_today
```

Ví dụ:
- Yesterday: BTC AUM = $149.36B
- Today: BTC flow = +$120M
- Today AUM = $149.36B + $0.12B = **$149.48B**

### Bulk update
Nếu update nhiều ngày cùng lúc:
1. Copy data từ Farside (có table theo ngày)
2. Paste vào Excel/Google Sheets
3. Convert format (date, số liệu)
4. Copy vào CSV

### Automation (optional)
Nếu muốn tự động:
- Farside có table HTML, có thể scrape
- CoinMarketCap có API (cần API key)
- Mình có thể tạo script Python scrape Farside

---

## ❓ FAQ

**Q: Phải update mỗi ngày không?**
A: Không bắt buộc. Update khi có thời gian, hoặc 1 tuần 1 lần. Data càng fresh càng tốt.

**Q: Nếu thiếu ngày thì sao?**
A: App vẫn chạy bình thường, chỉ chart bị gap. Có thể bỏ qua ngày cuối tuần (ETF không trade).

**Q: Làm sao biết flow dương hay âm?**
A: 
- Farside/CMC dùng màu: Xanh = inflow (+), Đỏ = outflow (-)
- Có dấu + hoặc - trước số

**Q: AUM có sai số nhỏ được không?**
A: OK, AUM chỉ cần gần đúng. Flow mới quan trọng.

**Q: Có tool nào tự động không?**
A: Chưa có sẵn. Nếu cần, mình làm script scrape Farside. Nhưng update thủ công chỉ mất 2-3 phút/ngày.

---

## 📚 Tham khảo

- [Farside BTC Daily Flows](https://farside.co.uk/btc/)
- [Farside ETH Daily Flows](https://farside.co.uk/eth/)
- [CoinMarketCap ETF Tracker](https://coinmarketcap.com/currencies/bitcoin/etf/)
- [CoinShares Weekly Reports](https://coinshares.com/research/digital-asset-fund-flows)
