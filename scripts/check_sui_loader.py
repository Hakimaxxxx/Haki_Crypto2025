import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from services.whale.whale_loader import load_whales_for_symbol, as_overlay_events

ev = load_whales_for_symbol('SUI')
print('Loaded events count:', len(ev))
if len(ev) > 0:
    print('Sample normalized event keys:', list(ev[0].keys()))
    overlay = as_overlay_events(ev[:5])
    print('Overlay format sample:', overlay[:3])
else:
    print('No SUI events loaded')
