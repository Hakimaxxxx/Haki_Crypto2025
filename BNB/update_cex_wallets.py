"""Script bán tự động để cập nhật danh sách ví CEX từ trang Arkham Tags.

Do trang hoạt động client-side, requests đơn thuần có thể không lấy đủ.
Các bước gợi ý:
1. Chạy script này thử fetch HTML.
2. Nếu kết quả ít, mở trang trong browser, copy toàn bộ HTML (hoặc JSON devtools) dán vào file tạm.
3. Truyền đường dẫn file tạm qua --html-file để script parse regex địa chỉ & merge.

Usage (PowerShell):
  python BNB/update_cex_wallets.py --fetch
  python BNB/update_cex_wallets.py --html-file raw.html --exchange Kraken

Bạn có thể chạy nhiều lần với các exchange khác nhau để gán nhóm chính xác.
Nếu không chỉ định --exchange, script sẽ bỏ tất cả vào nhóm "Unclassified" để xử lý sau.
"""

from __future__ import annotations
import argparse
import requests
from pathlib import Path
from cex_wallets_loader import (
    load_cex_wallets,
    save_cex_wallets,
    extract_addresses_from_html,
    merge_wallets,
)

ARKHAM_TAGS_URL = "https://intel.arkm.com/tags/cex"


def fetch_html(url: str = ARKHAM_TAGS_URL, timeout: int = 15) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Cache-Control": "no-cache",
    }
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def main():
    ap = argparse.ArgumentParser(description="Update CEX wallet list (best-effort)")
    ap.add_argument("--fetch", action="store_true", help="Fetch HTML trực tiếp từ Arkham")
    ap.add_argument("--html-file", help="Đường dẫn file HTML thủ công")
    ap.add_argument("--exchange", help="Tên sàn áp nhãn cho tất cả địa chỉ mới (vd Kraken)")
    args = ap.parse_args()

    if not args.fetch and not args.html_file:
        ap.error("Cần --fetch hoặc --html-file")

    html_parts = []
    if args.fetch:
        try:
            print("[INFO] Fetching HTML từ Arkham...")
            html_parts.append(fetch_html())
        except Exception as e:
            print(f"[WARN] Fetch lỗi: {e}")
    if args.html_file:
        p = Path(args.html_file)
        if p.exists():
            html_parts.append(p.read_text(encoding="utf-8", errors="ignore"))
        else:
            print(f"[WARN] File {p} không tồn tại")

    if not html_parts:
        print("[ERROR] Không có HTML để parse")
        return

    combined_html = "\n".join(html_parts)
    found = extract_addresses_from_html(combined_html)
    print(f"[INFO] Tìm thấy {len(found)} địa chỉ (unique)")

    if not found:
        return

    existing = load_cex_wallets()
    new_block = {}
    label = args.exchange or "Unclassified"
    new_block[label] = found
    merged = merge_wallets(existing, new_block)
    save_cex_wallets(merged)
    total = sum(len(v) for v in merged.values())
    print(f"[OK] Đã merge & lưu. Tổng địa chỉ: {total}")


if __name__ == "__main__":
    main()
