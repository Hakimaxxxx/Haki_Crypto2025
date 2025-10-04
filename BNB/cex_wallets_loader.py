"""Loader & helper utilities for dynamic CEX wallet lists.

Workflow đề xuất:
1. Ban đầu giữ danh sách tĩnh trong `cex_wallets.json` (có thể commit).
2. Script `update_cex_wallets.py` sẽ cố gắng scrape trang Arkham (best-effort) & merge.
3. Các module whale alert sẽ ưu tiên load động, fallback sang danh sách cứng trong file python.

Chú ý: Trang Arkham render động (client-side). Nếu không lấy đầy đủ bằng requests thường
thì cần dùng manual export hoặc API hợp lệ. Ở đây chỉ cung cấp khung xử lý & regex extract.
"""

from __future__ import annotations
import json
import os
import re
from typing import Dict, List

DEFAULT_JSON_PATH = os.path.join(os.path.dirname(__file__), "cex_wallets.json")


def load_cex_wallets(json_path: str | None = None) -> Dict[str, List[str]]:
    path = json_path or DEFAULT_JSON_PATH
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Chuẩn hóa: bỏ trùng, giữ nguyên thứ tự tương đối
        norm: Dict[str, List[str]] = {}
        for ex, addrs in data.items():
            seen = set()
            cleaned = []
            for a in addrs:
                if not isinstance(a, str):
                    continue
                a_str = a.strip()
                if not a_str:
                    continue
                if a_str.lower() in seen:
                    continue
                seen.add(a_str.lower())
                cleaned.append(a_str)
            norm[ex] = cleaned
        return norm
    except Exception:
        return {}


ETH_ADDRESS_RE = re.compile(r"0x[a-fA-F0-9]{40}")
BTC_ADDRESS_RE = re.compile(r"\b[13][a-km-zA-HJ-NP-Z1-9]{24,42}\b")  # heuristic


def extract_addresses_from_html(html: str) -> list[str]:
    """Best-effort trích xuất địa chỉ từ HTML thô."""
    addrs = set()
    for m in ETH_ADDRESS_RE.findall(html):
        addrs.add(m)
    for m in BTC_ADDRESS_RE.findall(html):
        # tránh nhầm các chuỗi quá dài vô nghĩa
        addrs.add(m)
    return sorted(addrs)


def merge_wallets(existing: dict, newly: dict) -> dict:
    out = {k: list(v) for k, v in existing.items()}
    for ex, addrs in newly.items():
        out.setdefault(ex, [])
        lc = {a.lower() for a in out[ex]}
        for a in addrs:
            if a.lower() not in lc:
                out[ex].append(a)
                lc.add(a.lower())
    return out


def save_cex_wallets(data: dict, json_path: str | None = None) -> None:
    path = json_path or DEFAULT_JSON_PATH
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


if __name__ == "__main__":  # quick manual test
    wallets = load_cex_wallets()
    print("Loaded CEX groups:", list(wallets))
    total = sum(len(v) for v in wallets.values())
    print("Total addresses:", total)
