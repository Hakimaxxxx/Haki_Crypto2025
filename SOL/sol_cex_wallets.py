import os
from wallet_loader import load_wallet_groups, build_label_sets

# Fallback tối thiểu – để JSON có thể mở rộng ngoài code.
STATIC_EXCHANGE_WALLETS = {
    "Binance": ["8L8pDf3jutdpdr4m3np68CL9ZroLActrqwxi6s9Ah5xU"],
    "OKX": ["is6MTRHEgyFLNTfYcuV4QBWLjrZBfmhVNYR6ccgr8KV"],
}

_JSON_PATH = os.path.join(os.path.dirname(__file__), "sol_cex_wallets.json")
EXCHANGE_WALLETS = load_wallet_groups(_JSON_PATH, STATIC_EXCHANGE_WALLETS)


# Danh sách ví tổ chức/OTC/market maker (không phải sàn CEX/Dex)
ORG_WALLETS = {
    # Wintermute
    "Wintermute": [
        "3ADzk5YDP9sgorvPSs9YPxigJiSqhgddpwHwwPwmEFib"
    ],
    "FireblocksCustody": [
        "GJFXMTxWdT4uWPXon1d9rJmx4U6NWbeaneh8uhVArVfP"
    ],
}

ALL_EXCHANGE_WALLETS, _LABELS_TMP, ALL_EXCHANGE_WALLETS_LC = build_label_sets(EXCHANGE_WALLETS)

# Tập hợp tất cả ví tổ chức/OTC/market maker (không phải sàn)
ALL_ORG_WALLETS = set()
for v in ORG_WALLETS.values():
    ALL_ORG_WALLETS.update(v)

# Tập hợp tất cả ví đặc biệt (sàn + tổ chức/OTC/market maker)
ALL_SPECIAL_WALLETS = ALL_EXCHANGE_WALLETS | ALL_ORG_WALLETS

# Hàm kiểm tra giao dịch giữa các ví sàn (bao gồm ví lưu ký)
def is_internal_exchange_transfer(from_addr, to_addr):
    return from_addr in ALL_EXCHANGE_WALLETS and to_addr in ALL_EXCHANGE_WALLETS

# Hàm kiểm tra ví có phải là ví tổ chức/OTC/market maker không
def is_org_wallet(addr):
    return addr in ALL_ORG_WALLETS

# Hàm kiểm tra ví có phải là ví sàn không (chỉ ví sàn mới tính là mua/bán)
def is_exchange_wallet(addr):
    return (addr or "") in ALL_EXCHANGE_WALLETS
