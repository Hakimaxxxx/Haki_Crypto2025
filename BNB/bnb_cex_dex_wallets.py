"""
Canonical lists of known CEX/DEX wallets on Binance Smart Chain (BSC) for basic labeling.
This is a best-effort set; extend or correct as needed. For large-scale precision, consider using a tagging service.
"""

from .cex_wallets_loader import load_cex_wallets

# Danh sách tĩnh tối thiểu (fallback). Không nên phình to – dữ liệu lớn đặt ở cex_wallets.json.
STATIC_CEX_WALLETS = {
    "Binance": [
        "0x38B661e9df2cc4A7570618AA6645319D6bdf2F46",
        "0xBE0eB53F46cd790Cd13851d5EFf43D12404d33E8",
        "0x5a52E96BAcdaBb82fd05763E25335261B270Efcb",
        "0xF977814e90dA44bFA03b6295A0616a897441aceC",
    ],
    "Kraken": ["0x7DAFbA1d69F6C01AE7567Ffd7b046Ca03B706f83"],
    "KuCoin": ["0xC61b9BB3A7a0767E3179713f3A5c7a9aeDCE193C"],
}

# Load động (nếu có file JSON) rồi merge fallback.
_dynamic = load_cex_wallets()
CEX_WALLETS = {**STATIC_CEX_WALLETS}
for ex, addrs in _dynamic.items():
    base = {a.lower(): a for a in CEX_WALLETS.get(ex, [])}
    for a in addrs:
        if a.lower() not in base:
            CEX_WALLETS.setdefault(ex, []).append(a)

 # (Các sàn Gate / Bybit / Bithumb ... sẽ nạp từ JSON nếu có)

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