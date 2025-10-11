"""AVAX chain shared utilities

- Chain: Avalanche C-Chain (EVM)
- Chain ID: 43114
- Decimal: 18
"""
from __future__ import annotations

AVAX_CHAIN_ID = 43114
AVAX_DECIMALS = 18

# Local filenames (kept at repo root for consistency with other chains)
USER_SEEN_BLOCK_FILE = "avax_whale_user_seen_block.json"
HISTORY_FILE = "avax_whale_alert_history.json"
BLOCK_FILE = "avax_whale_last_block.json"
LOG_FILE = "avax_whale_scanner.log"
CSV_FILE = "avax_whale_alert_history.csv"

__all__ = [
	"AVAX_CHAIN_ID",
	"AVAX_DECIMALS",
	"USER_SEEN_BLOCK_FILE",
	"HISTORY_FILE",
	"BLOCK_FILE",
	"LOG_FILE",
	"CSV_FILE",
]
