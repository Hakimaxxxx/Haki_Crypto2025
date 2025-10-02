# Danh sách ví sàn lớn trên Solana (CEX)
# Bạn có thể bổ sung thêm nếu cần
EXCHANGE_WALLETS = {
    # Binance
    "Binance": [
        "4Nd1mY4Q6r5o6Q1r8r1Q1r8r1Q1r8r1Q1r8r1Q1r8r1Q1",  # ví mẫu, thay bằng ví thật
        "8L8pDf3jutdpdr4m3np68CL9ZroLActrqwxi6s9Ah5xU",  # ví thật của Binance
        "5tzFkiKscXHK5ZXCGbXZxdw7gTjjD1mBwuoFbhUvuAi9"  # Binance2
    ],
    # OKX
    "OKX": [
        "6pQe1Q1r8r1Q1r8r1Q1r8r1Q1r8r1Q1r8r1Q1r8r1Q1r8r1Q1",  # ví mẫu
        "is6MTRHEgyFLNTfYcuV4QBWLjrZBfmhVNYR6ccgr8KV"  # OKX thật
    ],
    # Coinbase
    "Coinbase": [
        "FpwQQhQQoEaVu3WU2qZMfF1hx48YyfwsLoRgXG83E99Q"
    ],
    # Kucoin
    "Kucoin": [
        "7Q1r8r1Q1r8r1Q1r8r1Q1r8r1Q1r8r1Q1r8r1Q1r8r1Q1r8r1"  # ví mẫu
    ],
    # Bybit
    "Bybit": [
        "9Q1r8r1Q1r8r1Q1r8r1Q1r8r1Q1r8r1Q1r8r1Q1r8r1Q1r8r1"  # ví mẫu
    ],
    # Gate
    "Gate": [
        "GQ1r8r1Q1r8r1Q1r8r1Q1r8r1Q1r8r1Q1r8r1Q1r8r1Q1r8r1"  # ví mẫu
        "ASTyfSima4LLAdDgoFGkgqoKowG1LZFDr9fAQrg7iaJZ"
    ]
    ,

    # Wintermute (imported from CSV)
    "Exchange": [
        "u6PJ8DtQuPFnfmwHbGFULQ4u4EgjDiyYKjVEsynXq2w",
        "3bwCjRXv4LASkv7DbLRJi7fDXgRRfEZhEstDVoZsjEHR",
        "43DbAvKxhXh1oSxkJSqGosNw3HpBnmsWiak6tB5wpecN",
        "MfDuWeqSHEqTFVYZ7LoexgAK9dxk7cy4DFJWjWMGVWa",
        "9D8xSHWqF9NJWqCtn3rNxYEox63aCbWxYzTMfMur7Cc9",
        "6LY1JzAFVZsP2a2xKrtU6znQMQ5h4i7tocWdgrkZzkzF",
        "FxteHmLwG9nk1eL4pjNve3Eub2goGkkz6g6TbvdmW46a",
        "iGdFcQoyR2MwbXMHQskhmNsqddZ6rinsipHc4TNSdwu",
        "44P5Ct5JkPz76Rs2K6juC65zXMpFRDrHatxcASJ4Dyra",
        "2UL8hbNaoErAYNePqgQYPP9yDCDRZGWbzKW4krLqkhNL",
        "4raqd4tCEnm2yGeUocVqPgN2MPB1W6A3EZfC8LoMChvf",
        "GCRJD52pGwcCSs4oswYxTBCPatxY1P6WpxCC9R9zty6r",
        "H8sMJSCQxfKiFTCfDR3DUMLPwcRbM61LGFJ8N4dK3WjS",
        "BmFdpraQhkiDQE6SnfG5omcA1VwzqfXrwtNYBwWTymy6",
        "81w96XvKAZZFmmuzaohSQUyxtGnAPJmkjwoBFBmtytUj",
        "AobVSwdW9BbpMdJvTqeCN4hPAmh4rHm7vwLnQ5ATSyrS",
        "fr6yQkDmWy6R6pecbUsxXaw6EvRJznZ2HsK5frQgud8",
        "3huamNpghPSPbgQSLX56B18Sj1hq5SE4KGxwTvhwJGnC",
        "9obNtb5GyUegcs3a1CbBkLuc5hEWynWfJC6gjz5uWQkE",
        "GJRs4FwHtemZ5ZE9x3FNvJ8TMwitKTh21yxdRPqn7npE",
        "2bXv6v4g7k3i5cU8m3F6n1Z1J1r8r1Q1r8r1Q1r8r1Q1r8r"  # ví mẫu
    ]
}


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

# Tập hợp tất cả ví sàn (CEX/Dex/lưu ký) để phân loại mua/bán
ALL_EXCHANGE_WALLETS = set()
for v in EXCHANGE_WALLETS.values():
    ALL_EXCHANGE_WALLETS.update(v)

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
    return addr in ALL_EXCHANGE_WALLETS
