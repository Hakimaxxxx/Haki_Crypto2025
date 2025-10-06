# Phase 2 Plan (Architecture Expansion)

Date: 2025-10-06
Status: Draft
Owner: Migration Initiative

## Vision
Evolve from a monolithic Streamlit + thin backend bridge into a layered architecture with clear contracts, enabling future automation (alerts, ingestion pipelines) and scaling (API consumers beyond UI).

## Guiding Principles
1. Single Source of Truth: Database-backed canonical data (prices snapshots, whale events, portfolio history).
2. Explicit Contracts: All API responses validated via Pydantic schemas.
3. Separation of Concerns: UI ↔ Service ↔ Repository layers.
4. Observability: Structured logging + health & metrics endpoints.
5. Resilience: Retry, backoff, circuit-breaker patterns around external APIs.

## Target Architecture Layers
- Schemas (Pydantic): request/response/domain DTOs (`backend/app/schemas/*`).
- Services: business logic orchestration (aggregation, derivations, caching strategies).
- Repositories: persistence + external API adapters (MongoDB, OKX, CoinGecko).
- Tasks: background scheduled jobs (ingest, refresh, cleanup) with a lightweight runner.
- API Routers: thin (validation + delegation to services).

## Phase 2 Iteration Outline
| Iter | Scope | Key Artifacts |
|------|-------|--------------|
| 2.1 | Schema foundation | Base models for Price, WhaleEvent, PortfolioMeta, OHLCVBar |
| 2.2 | Service layer extraction | prices_service, whales_service, portfolio_service |
| 2.3 | Repository adapters | okx_repo, coingecko_repo, mongo_repo |
| 2.4 | Task scheduler | periodic refresh (prices, whales), retry queue integration |
| 2.5 | DB canonical data | Persist normalized snapshots + query by time window |
| 2.6 | Observability | /metrics (Prometheus-style), structured logs, error surfaces |
| 2.7 | Test coverage uplift | Unit + integration tests for services & repos |
| 2.8 | UI refactor | Streamlit consumes only backend contracts (remove file fallbacks) |

## Data Models (Initial Draft)
```text
PriceSnapshot: symbol, price, change_1d, change_7d, change_30d, ts
WhaleEvent: symbol, ts, direction, amount_token, amount_usd, tx_hash, from_address, to_address, chain
OHLCVBar: symbol, ts_open, open, high, low, close, volume, timeframe
PortfolioPosition: symbol, holding, avg_cost, value, pnl_abs, pnl_pct
PortfolioMeta: generated_at, positions[], total_value, total_pnl_abs, total_pnl_pct
```

## Caching Strategy (Planned)
- In-memory (short TTL) for hot endpoints.
- Optional Redis/Mongo query caching layer (future if needed).
- Cache key versioning tied to schema version to prevent stale shape usage.

## Task Scheduler Proposal
Lightweight internal loop registry (no heavy Celery):
```python
register_task(name, interval_seconds, fn, jitter=0.1)
run_tasks_forever()
```
Supports backoff + disabled-after-N-failures semantics.

## Migration Steps
1. Introduce schemas without changing existing responses (dual path).
2. Refactor routes to emit schema instances (serialize via .model_dump()).
3. Extract existing inline logic from routes into service functions.
4. Add repository abstractions and gradually redirect data access.
5. Turn on DB persistence for price snapshots + whale events.
6. Remove direct file reads from frontend (Streamlit uses only backend/meta endpoints).
7. Add tests to lock behavior before final cleanup phase.

## Risks & Mitigations
| Risk | Mitigation |
|------|-----------|
| Schema churn breaks frontend | Introduce versioned endpoints or response_version field |
| Background task race conditions | Per-task async lock + last-run timestamp guard |
| Increased complexity overhead | Keep services thin; iterate incrementally per domain |
| Data inconsistency (file vs DB) | Cutover flag: read-from-DB-once-has >X records |

## Success Criteria
- 100% of UI data sourced via backend endpoints (no direct file I/O in Streamlit).
- All endpoints backed by Pydantic schemas & test coverage >70% lines for service layer.
- Background tasks stable (<1% failure rate over 24h test window).
- Deprecation warnings eliminated; zero blocked migrations for Phase 3 (alerting/webhooks).

## Out of Scope (Phase 2)
- Real-time websocket push (deferred to Phase 3).
- Advanced analytics (MVRV, on-chain heuristics enrichment) beyond existing metrics.

---
Draft prepared to anchor implementation sequencing. Iterate as code evolves.
