import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from services.whale.whale_loader import load_btc_whales

btc = load_btc_whales()
print('BTC count:', len(btc))
if btc:
    sample = btc[0]
    print('BTC sample keys:', list(sample.keys()))
    print('BTC sample time:', sample.get('time'), type(sample.get('time')))
    print('BTC sample ts:', sample.get('ts'), type(sample.get('ts')))
else:
    print('No BTC events found')
