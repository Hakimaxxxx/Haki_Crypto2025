# SUI CEX/DEX wallet classification

# Example wallet lists (to be expanded dynamically)
CEX_WALLETS = [
    "0xac5bceec1b789ff840d7d4e6ce4ce61c90d190a7f8c4f4ddf0bff6ee2413c33c",#Binance
    "0x60dd01bc037e2c1ea2aaf02187701f9f4453ba323338d2f2f521957065b0984d", #Bybit
    "0x443cf42b0da43c230bff7a64e69ce25d24d65f49e7c9db6adecc0bd176dba79a", #Karren
    "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef", #Binance CEX Wallet
]

DEX_WALLETS = [
    "0x789dexwallet1",
    "0xabcdewallet2",
]

def classify_transaction(from_addr: str, to_addr: str) -> str:
    """Classify a transaction based on known wallet addresses."""
    if from_addr in CEX_WALLETS or to_addr in CEX_WALLETS:
        return "CEX"
    elif from_addr in DEX_WALLETS or to_addr in DEX_WALLETS:
        return "DEX"
    return "OTHER"