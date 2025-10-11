"""
Canonical lists of known CEX/DEX wallets on Avalanche C-Chain for basic labeling.
Best-effort starter set. Extend via JSON sources later if needed.
"""
from __future__ import annotations

# Try to load from JSON, fallback to empty dict if not available
def load_cex_wallets():
	try:
		import json
		import os
		cex_file = os.path.join(os.path.dirname(__file__), "cex_wallets.json")
		if os.path.exists(cex_file):
			with open(cex_file, "r") as f:
				return json.load(f)
	except Exception:
		pass
	return {}

# Minimal seed lists (placeholders). Replace/extend with verified addresses when available.
CEX_WALLETS = {
	"Binance": [
		"0x564286362092D8e7936f0549571a803B203aAceD",  # sample (illustrative)
	],
	"Kraken": [
		"0x0A869d79a7052C7f1b55a8EbAbbEa3420F0D1E13",  # sample (illustrative)
	],
}

DEX_WALLETS = {
	"TraderJoe": [
		"0xB31f66AA3C1e785363F0875A1B74E27b85FD66c7",  # AVAX token (placeholder for routing contracts)
	],
}

# Load dynamic wallets from JSON and merge with static wallets
_dynamic = load_cex_wallets()
for ex, addrs in _dynamic.items():
    base = {a.lower(): a for a in CEX_WALLETS.get(ex, [])}
    for a in addrs:
        if a.lower() not in base:
            CEX_WALLETS.setdefault(ex, []).append(a)

# Build label sets
ALL_CEX_WALLETS_LC = {a.lower() for addrs in CEX_WALLETS.values() for a in addrs}
ALL_DEX_WALLETS_LC = {a.lower() for addrs in DEX_WALLETS.values() for a in addrs}

ADDRESS_LABELS = {a.lower(): ex for ex, addrs in CEX_WALLETS.items() for a in addrs}
ADDRESS_LABELS.update({a.lower(): dex for dex, addrs in DEX_WALLETS.items() for a in addrs})


def is_cex_wallet(addr: str) -> bool:
	return (addr or "").lower() in ALL_CEX_WALLETS_LC


def is_dex_wallet(addr: str) -> bool:
	return (addr or "").lower() in ALL_DEX_WALLETS_LC


def classify_transaction(from_addr: str, to_addr: str) -> str:
	"""Basic BUY/SELL labeling by CEX direction like other chains.
	- from CEX -> SELL
	- to CEX -> BUY
	Else N/A
	"""
	fa, ta = (from_addr or "").lower(), (to_addr or "").lower()
	if fa in ALL_CEX_WALLETS_LC:
		return "SELL"
	if ta in ALL_CEX_WALLETS_LC:
		return "BUY"
	return "N/A"
