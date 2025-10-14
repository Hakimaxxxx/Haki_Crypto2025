import os

# Lấy thư mục chứa file script hiện tại (ví dụ: Crypto/)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Đường dẫn tới thư mục SUI (BASE_DIR is already the SUI package directory)
SUI_DIR = BASE_DIR

# Ensure the directory exists (safe no-op if present)
try:
	os.makedirs(SUI_DIR, exist_ok=True)
except Exception:
	pass

# Chain identification constant (used by scanner and external callers)
SUI_CHAIN_ID = "sui:mainnet"

# Ghép đường dẫn file cần lưu vào thư mục SUI
USER_SEEN_BLOCK_FILE = os.path.join(SUI_DIR, "sui_whale_user_seen_block.json")
HISTORY_FILE = os.path.join(SUI_DIR, "sui_whale_alert_history.json")
BLOCK_FILE = os.path.join(SUI_DIR, "sui_whale_last_block.json")
LOG_FILE = os.path.join(SUI_DIR, "sui_whale_scanner.log")
CSV_FILE = os.path.join(SUI_DIR, "sui_whale_alert_history.csv")