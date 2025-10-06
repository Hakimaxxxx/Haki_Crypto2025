# Phase 3 Plan (Realtime Alerts & Advanced Persistence)
Date: 2025-10-06
Status: Draft

## Vision
Kích hoạt hệ thống cảnh báo (whale + biến động giá) thời gian gần thực, lưu snapshot chuẩn hoá vào DB để phục vụ phân tích lịch sử, và mở cổng websocket/SSE cho UI / client khác.

## Core Pillars
1. Alert & Rule Engine.
2. Realtime Delivery (WebSocket / optional SSE fallback).
3. Persistent Snapshot Store (prices + whales + portfolio summaries).
4. Observability & Metrics.
5. Extensible Outputs (Telegram / Discord / Email hooks - optional wave 2).

## Iteration Breakdown
| Iter | Scope | Output |
|------|-------|--------|
| 3.1 | Snapshot persistence | collections: price_snapshots, whale_events (schema), indices |
| 3.2 | WebSocket gateway | `/ws/stream` multiplex (channels: prices, whales, alerts) |
| 3.3 | Rule engine (baseline) | YAML/JSON rule parser + evaluator loop + alert queue |
| 3.4 | Alert delivery adapters | console + in-app panel + (stub webhook) |
| 3.5 | Metrics & logging | structured logs + /metrics (Prometheus) |
| 3.6 | Backfill & query endpoints | `/analytics/price_range`, `/analytics/whales` |
| 3.7 | UI integration | Live ticker + alert panel + subscription UI |
| 3.8 | Hardening & tests | load tests + rule engine unit tests |

## Data Schemas (Draft)
price_snapshots:
- ts (epoch sec, index)
- coin_id, symbol
- price, change_1h, change_1d, change_7d, change_30d
- source

whale_events:
- ts, symbol, coin_id, direction, amount_token, amount_usd, tx_hash, chain, from, to
- normalized_flag, ingestion_ts

alerts:
- ts, type (price_move|whale_large|custom)
- symbol, coin_id
- rule_id, payload, severity
- delivered_channels

## Rule Engine (Baseline)
Structure example:
```yaml
rules:
  - id: large_whale_eth
    type: whale_large
    symbol: ETH
    min_amount_usd: 250000
    window_sec: 600
  - id: price_spike_eigen
    type: price_move
    symbol: EIGEN
    pct_move: 3
    window_sec: 900
```
Evaluator loop:
1. Pull recent events from in-memory ring buffer (populated by periodic fetcher / future stream).
2. Aggregate by symbol & time window.
3. Match against rule conditions.
4. Emit alert object -> broadcast queue -> delivery adapters.

## WebSocket Channels (JSON frames)
```json
{"channel":"prices","data":{...snapshot...}}
{"channel":"whales","data":{...event...}}
{"channel":"alerts","data":{...alert...}}
```
Handshake query params: `?channels=prices,whales,alerts`.

## Caching & Buffers
- In-memory ring buffers per channel (size bound, e.g. 500 events).
- Async queue for alert dispatch.

## Metrics (/metrics)
- tasks_running, last_price_snapshot_ts, whale_events_ingested_total, alerts_emitted_total, rule_eval_duration_ms (histogram).

## Risks
| Risk | Mitigation |
|------|------------|
| Burst whale events gây nghẽn | Bounded ring buffer + drop oldest |
| Rule chạy chậm | Pre-aggregation + incremental windows |
| WS disconnect nhiều | Heartbeat frame + client backoff |

## Success Criteria
- WebSocket phát được stream giá & ít nhất 1 kênh alert.
- Tốc độ rule eval < 300ms / chu kỳ (1000 events test).
- Không mất hơn 5% events trong điều kiện burst giả lập.
- UI hiển thị alert mới < 2s từ khi phát hiện.

---
Draft ready for execution.
