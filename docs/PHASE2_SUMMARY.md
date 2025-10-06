# Phase 2 Summary (Completed 2025-10-06)

## Goal
Chuẩn hoá lớp backend thành kiến trúc nhiều lớp (schemas + services + scheduler) và tách logic khỏi route inline / Streamlit, chuẩn bị tiền đề cho Phase 3 (alerting realtime + persistence nâng cao).

## Completed Deliverables
- Pydantic Schemas: `PriceSnapshot (thêm coin_id)`, `WhaleEvent`, `OHLCVBar`, `PortfolioPosition`, `PortfolioMeta`, `PortfolioMetaResponse`.
- Service Layer: `prices_service`, `whales_service`, `portfolio_service`.
- Scheduler nhẹ: warm cache cho giá (`warm_prices`).
- Routes refactor: `/prices/spot`, `/whales/*`, `/portfolio/meta` dùng service & schema.
- Whale Large Transactions panel: filter threshold, màu BUY/SELL, bổ sung cột Amount (coin) fallback.
- Fix mapping symbol ↔ coin_id (đã đồng nhất price_data keys = coin_id).
- PNL logic xử lý vị thế âm (short/borrow) hợp lệ.
- Migration caption whale box theo feedback người dùng.

## Key Changes vs Phase 1
| Hạng mục | Phase 1 | Phase 2 |
|----------|---------|---------|
| Giá & % change | File parsing trực tiếp | Service + schema + coin_id mapping |
| Whale events cache | TTL inline trong route | Service layer TTL, overlay adapter |
| Portfolio meta | Dict raw | Schema object + tổng hợp P&L chuẩn hoá |
| Scheduler | Chưa có | Skeleton `register_task` + warm_prices |
| UI Whale Box | Chỉ filter cơ bản | Styling, amount fallback, caption tùy biến |
| PNL âm | Sai với holdings âm | Công thức short đã điều chỉnh |

## Technical Debt Remaining
- Chưa có repository layer tách Mongo / File I/O rõ ràng.
- Chưa có task ingest whale / price snapshot DB định kỳ.
- Chưa có cảnh báo / rule engine.
- Chưa version hóa API responses.
- Thiếu test coverage (services & edge cases negative holdings, missing amounts).
- Chưa có metrics Prometheus hoặc structured logging middleware.

## Ready for Phase 3
Phase 2 tạo nền để mở rộng:
1. Alert / rule engine (whale spike, %move, volume).  
2. Realtime push (websocket / SSE).  
3. Snapshot persistence & query by time window (câu truy vấn analytics).  
4. Observability (tracing, /metrics).  
5. Rule config & subscription (Telegram / Discord hooks).  

---
Generated: 2025-10-06
