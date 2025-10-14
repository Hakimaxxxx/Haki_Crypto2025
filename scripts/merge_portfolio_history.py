import json, os, glob, time
from pathlib import Path

# Lấy thư mục chứa file script hiện tại
ROOT = Path(__file__).parent.resolve()
MAIN = ROOT / "portfolio_history.json"

# Gather candidate files: main + backups/corrupt variants
candidates = [MAIN]
candidates += sorted(ROOT.glob("portfolio_history.json.backup"))
candidates += sorted(ROOT.glob("portfolio_history.json.corrupt_*"))

records = []
seen = set()
contrib = {}

for p in candidates:
    if not p.exists():
        continue
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            # some files may have {'history': [...]} shape
            data = data.get('history') or []
        if not isinstance(data, list):
            continue
    except Exception:
        # try to recover line-delimited JSON or partial arrays
        try:
            lines = [ln.strip() for ln in p.read_text(encoding="utf-8", errors="ignore").splitlines() if ln.strip()]
            data = []
            for ln in lines:
                try:
                    data.append(json.loads(ln))
                except Exception:
                    continue
        except Exception:
            continue
    added = 0
    for d in data:
        if not isinstance(d, dict):
            continue
        # Use a reasonable key for dedup: (timestamp, coin) else fallback to tuple(sorted items))
        ts = d.get('timestamp')
        coin = d.get('coin')
        if ts is not None:
            key = (ts, coin)
        else:
            try:
                key = tuple(sorted(d.items()))
            except Exception:
                key = None
        if key is None or key in seen:
            continue
        seen.add(key)
        records.append(d)
        added += 1
    contrib[str(p.name)] = added

# Sort by timestamp if present
records.sort(key=lambda x: (x.get('timestamp') is None, x.get('timestamp', 0)))

# Write atomically: create a temp then replace
from portfolio_history import _atomic_write_json

if records:
    _atomic_write_json(records, str(MAIN))
    print(f"Merged {len(records)} records into {MAIN}")
else:
    print("No records to merge")

print("Contributions:")
for k, v in contrib.items():
    print(f"  {k}: {v}")
