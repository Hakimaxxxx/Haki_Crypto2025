"""
Canonical lists of known CEX/DEX wallets on Binance Smart Chain (BSC) for basic labeling.
This is a best-effort set; extend or correct as needed. For large-scale precision, consider using a tagging service.
"""

# Known exchange clusters (sample + commonly referenced addresses). Edit safely.
CEX_WALLETS = {
    "Binance": [
        "0x123...",  # Binance hot wallet
        "0x456...",  # sample/placeholder
    ],
    "KuCoin": [
        "0x789...",  # KuCoin wallet
        "0xabc...",  # sample/placeholder
    ],
    "Crypto.com": [
        "0xdef...",  # Crypto.com wallet
    ],
}

DEX_WALLETS = {
    "PancakeSwap": [
        "0x111...",  # PancakeSwap router
        "0x222...",  # sample/placeholder
    ],
    "Uniswap": [
        "0x333...",  # Uniswap router
    ],
}

# Build sets and label map (lowercased keys for case-insensitive matching)
ALL_CEX_WALLETS = set()
ALL_DEX_WALLETS = set()
ADDRESS_LABELS = {}

for label, addrs in CEX_WALLETS.items():
    for a in addrs:
        ALL_CEX_WALLETS.add(a)
        ADDRESS_LABELS[a.lower()] = label
for label, addrs in DEX_WALLETS.items():
    for a in addrs:
        ALL_DEX_WALLETS.add(a)
        ADDRESS_LABELS[a.lower()] = label

# Lowercased sets for detection
ALL_CEX_WALLETS_LC = {a.lower() for a in ALL_CEX_WALLETS}
ALL_DEX_WALLETS_LC = {a.lower() for a in ALL_DEX_WALLETS}
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

def classify_transaction(from_addr: str, to_addr: str) -> str:
    """
    Classify a transaction as BUY, SELL, or N/A based on wallet addresses.
    """
    if is_cex_wallet(from_addr):
        return "SELL"
    if is_cex_wallet(to_addr):
        return "BUY"
    return "N/A"