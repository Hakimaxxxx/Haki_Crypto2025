"""
Canonical lists of known CEX/DEX wallets on Bitcoin for basic labeling.
This is a best-effort set; extend or correct as needed. For large-scale precision, consider using a tagging service.
"""

import os
from wallet_loader import load_wallet_groups, build_label_sets

# Fallback tối thiểu (giảm kích thước code — phần đầy đủ nằm ở btc_cex_wallets.json nếu có)
STATIC_CEX_WALLETS = {
    "Binance": [
        "1NDyJtNTjmwk5xPNhjgAMu4HDHigtobu1s",
    ],
    "Coinbase": [
        "3D2oetdNuZUqQHPJmcMDDHYoqkyNVsFk9r",
    ],
}

_JSON_PATH = os.path.join(os.path.dirname(__file__), "btc_cex_wallets.json")
CEX_WALLETS = load_wallet_groups(_JSON_PATH, STATIC_CEX_WALLETS)

DEX_WALLETS = {
    "Bisq": [
        "1Bisq1T1tY8kMxWLbitaG7yT6bPbKChq64",  # placeholder
    ],
}

ALL_CEX_WALLETS, ADDRESS_LABELS_PART, ALL_CEX_WALLETS_LC = build_label_sets(CEX_WALLETS)
ALL_DEX_WALLETS, ADDRESS_LABELS_DEX, ALL_DEX_WALLETS_LC = build_label_sets(DEX_WALLETS)
ADDRESS_LABELS = {**ADDRESS_LABELS_PART, **ADDRESS_LABELS_DEX}

# Lowercased sets for detection
ALL_SPECIAL_WALLETS_LC = ALL_CEX_WALLETS_LC | ALL_DEX_WALLETS_LC

def is_cex_wallet(addr: str) -> bool:
    return (addr or "").lower() in ALL_CEX_WALLETS_LC

def is_dex_wallet(addr: str) -> bool:
    return (addr or "").lower() in ALL_DEX_WALLETS_LC

def is_special_wallet(addr: str) -> bool:
    return (addr or "").lower() in ALL_SPECIAL_WALLETS_LC

def is_internal_cex_transfer(from_addr: str, to_addr: str) -> bool:
    fa, ta = (from_addr or "").lower(), (to_addr or "").lower()
    return fa in ALL_CEX_WALLETS_LC and ta in ALL_CEX_WALLETS_LC

def is_internal_dex_transfer(from_addr: str, to_addr: str) -> bool:
    fa, ta = (from_addr or "").lower(), (to_addr or "").lower()
    return fa in ALL_DEX_WALLETS_LC and ta in ALL_DEX_WALLETS_LC
