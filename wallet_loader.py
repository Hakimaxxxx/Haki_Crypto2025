"""Generic wallet loader utilities.

Mục tiêu:
 - Chuẩn hóa cách load danh sách ví CEX / DEX / tổ chức từ file JSON động.
 - Cho phép fallback sang danh sách tĩnh trong code nếu file chưa tồn tại.
 - Hạn chế trùng lặp logic giữa các chain (BTC / BNB / SOL / ERC20 ...).

JSON format gợi ý:
{
  "Binance": ["addr1", "addr2"],
  "Kraken": ["addr3"],
  "Gate": []
}

Dùng:
    from wallet_loader import load_wallet_groups
    CEX_WALLETS = load_wallet_groups(json_path, fallback_dict)
"""
from __future__ import annotations
import json
import os
from typing import Dict, List

def _dedupe(seq):
    out = []
    seen = set()
    for x in seq:
        if not isinstance(x, str):
            continue
        xx = x.strip()
        if not xx:
            continue
        key = xx.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(xx)
    return out

def load_wallet_groups(json_path: str, fallback: Dict[str, List[str]] | None = None) -> Dict[str, List[str]]:
    """Load groups từ json_path và merge fallback.

    - Nếu file không tồn tại: trả về fallback (hoặc {}).
    - Nếu tồn tại: merge (JSON ưu tiên, nhưng vẫn giữ fallback address nếu chưa có).
    - Loại bỏ địa chỉ trùng và chuỗi rỗng.
    """
    fallback = fallback or {}
    data: Dict[str, List[str]] = {}
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                for k, v in raw.items():
                    if isinstance(v, list):
                        data[k] = _dedupe(v)
        except Exception:
            data = {}
    # merge fallback
    for k, v in (fallback or {}).items():
        base = {a.lower(): a for a in data.get(k, [])}
        for a in v:
            if isinstance(a, str) and a.strip() and a.lower() not in base:
                data.setdefault(k, []).append(a.strip())
    return data

def build_label_sets(groups: Dict[str, List[str]]):
    """Trả về (ALL_SET, LABEL_MAP, LOWERCASE_SET) phục vụ phân loại.
    Không can thiệp định dạng gốc ngoài việc tạo bản lower-case để so sánh.
    """
    all_set = set()
    label_map = {}
    for label, addrs in groups.items():
        for a in addrs:
            all_set.add(a)
            label_map[a.lower()] = label
    all_lc = {a.lower() for a in all_set}
    return all_set, label_map, all_lc
