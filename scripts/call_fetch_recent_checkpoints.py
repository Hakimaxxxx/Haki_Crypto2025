import sys
sys.path.append(r'd:\Crypto')
from SUI import metrics_sui_whale_alert_realtime as mod
import importlib
mod = importlib.reload(mod)
print('Calling fetch_recent_checkpoints(limit=20)')
print(mod.fetch_recent_checkpoints(20)[:20])
