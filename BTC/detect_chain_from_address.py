def detect_chain(address: str) -> str:
    """
    Nhận diện chain của địa chỉ ví dựa vào định dạng.
    Trả về: 'BTC', 'ETH', 'EVM', hoặc 'Unknown'
    """
    address = address.strip()
    # Địa chỉ Bitcoin (Legacy, SegWit, Bech32)
    if address.startswith('1') or address.startswith('3'):
        if 26 <= len(address) <= 35:
            return 'BTC'
    if address.startswith('bc1'):
        if 42 <= len(address) <= 62:
            return 'BTC'
    # Địa chỉ Ethereum/EVM (ETH, LINK, ETHFI, ENA, EIGEN, WLD, ONDO, RENDER, BNB)
    if address.startswith('0x') and len(address) == 42:
        return 'ETH/EVM'
    # Địa chỉ Solana (SOL)
    if len(address) == 44 and address.isalnum():
        return 'Solana'
    # Địa chỉ Near (NEAR)
    if address.endswith('.near') and len(address) > 5:
        return 'Near'
    # Địa chỉ Avalanche (AVAX)
    if address.startswith('X-') or address.startswith('P-') or address.startswith('C-'):
        return 'Avalanche'
    # Địa chỉ Sui (SUI)
    if address.startswith('0x') and len(address) == 66:
        return 'Sui'
    # Địa chỉ Aptos (APT)
    if address.startswith('0x') and len(address) == 66:
        return 'Aptos'
    # Địa chỉ BNB Chain (BNB)
    if address.startswith('bnb') and len(address) == 42:
        return 'BNB Chain'
    # Địa chỉ Tether (USDT) - đa chain, cần xác định qua chain cụ thể
    # Địa chỉ khác
    return 'Unknown'

if __name__ == "__main__":
    # Ví dụ test
    test_addresses = [
        "1NDyJtNTjmwk5xPNhjgAMu4HDHigtobu1s",  # BTC
        "3Cbq7aT1tY8kMxWLbitaG7yT6bPbKChq64",  # BTC
        "bc1qr4dl5wa7kl8yu792dceg9z5knl2gkn220lk7a9",  # BTC
        "0xA023f08c70A23aBc7EdFc5B6b5E171d78dFc947e",  # ETH
        "147sPaNaqeyQp8GS2oAUajhb9d4PZ9xAv9",  # BTC
        "8L8pDf3jutdpdr4m3np68CL9ZroLActrqwxi6s9Ah5xU",  # Solana
        "randomaddress1234567890"
    ]
    for addr in test_addresses:
        print(f"{addr}: {detect_chain(addr)}")
