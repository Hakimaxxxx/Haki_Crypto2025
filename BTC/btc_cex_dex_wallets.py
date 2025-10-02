"""
Canonical lists of known CEX/DEX wallets on Bitcoin for basic labeling.
This is a best-effort set; extend or correct as needed. For large-scale precision, consider using a tagging service.
"""

# Known exchange clusters (sample + commonly referenced addresses). Edit safely.
CEX_WALLETS = {
    "Binance": [
        "1NDyJtNTjmwk5xPNhjgAMu4HDHigtobu1s",  # Binance hot wallet
        "3LDsS579y7bG9k2zGwZkE2wTqd9yT2Q7y",  # sample/placeholder
    ],
    "Coinbase": [
        "3D2oetdNuZUqQHPJmcMDDHYoqkyNVsFk9r",
        "3Cbq7aT1tY8kMxWLbitaG7yT6bPbKChq64",
        "147sPaNaqeyQp8GS2oAUajhb9d4PZ9xAv9",
    ],
    "Crypto.com": [
        "bc1qr4dl5wa7kl8yu792dceg9z5knl2gkn220lk7a9",
        "32hK628jM4j1xLRQzJuvLsBhmBxKeVSdgN",
        "bc1q7cyrfmck2ffu2ud3rn5l5a8yv6f0chkp0zpemf",
    ],
    "Bitfinex": [
        "3D2oetdNuZUqQHPJmcMDDHYoqkyNVsFk9r",  # placeholder if unknown
    ],
    "OKX": [
        "1OKX1T1tY8kMxWLbitaG7yT6bPbKChq64",  # placeholder
    ],
}

DEX_WALLETS = {
    "Bisq": [
        "1Bisq1T1tY8kMxWLbitaG7yT6bPbKChq64",  # placeholder
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
