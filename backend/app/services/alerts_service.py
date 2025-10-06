from __future__ import annotations
import time, threading
from typing import List, Dict, Callable, Optional
from collections import deque

# Simple in-memory ring buffers
_price_events = deque(maxlen=500)
_whale_events = deque(maxlen=500)
_alerts = deque(maxlen=300)

_rules: List[Dict] = []  # to be loaded from yaml / json later
_listeners: List[Callable[[Dict], None]] = []  # callbacks for new alert

_lock = threading.Lock()


def push_price(snapshot: Dict):
    with _lock:
        _price_events.append(snapshot)


def push_whale(event: Dict):
    with _lock:
        _whale_events.append(event)


def register_alert_listener(fn: Callable[[Dict], None]):
    _listeners.append(fn)


def load_rules(rules: List[Dict]):
    global _rules
    _rules = rules


def _emit(alert: Dict):
    _alerts.append(alert)
    for fn in _listeners:
        try:
            fn(alert)
        except Exception:
            pass


def evaluate_rules():
    now = int(time.time())
    # Very naive rule evaluation placeholder
    for rule in _rules:
        rtype = rule.get('type')
        symbol = rule.get('symbol')
        if rtype == 'whale_large':
            min_amt = float(rule.get('min_amount_usd', 0))
            window = int(rule.get('window_sec', 600))
            since = now - window
            total_large = 0.0
            count = 0
            for evt in list(_whale_events):
                if evt.get('symbol') == symbol and evt.get('ts_epoch', now) >= since:
                    amt_usd = evt.get('amount_usd') or 0
                    if amt_usd >= min_amt:
                        total_large += amt_usd
                        count += 1
            if count > 0:
                alert = {
                    'ts': now,
                    'type': 'whale_large',
                    'symbol': symbol,
                    'rule_id': rule.get('id'),
                    'count': count,
                    'total_amount_usd': total_large,
                    'severity': 'info'
                }
                _emit(alert)
        elif rtype == 'price_move':
            pct_move = float(rule.get('pct_move', 0))
            window = int(rule.get('window_sec', 900))
            since = now - window
            # simplistic: compare first vs last in window
            recent = [s for s in list(_price_events) if s.get('symbol') == symbol and s.get('ts', now) >= since]
            if len(recent) >= 2:
                first = recent[0]['price']
                last = recent[-1]['price']
                if first:
                    move_pct = (last/first - 1)*100
                    if abs(move_pct) >= pct_move:
                        alert = {
                            'ts': now,
                            'type': 'price_move',
                            'symbol': symbol,
                            'rule_id': rule.get('id'),
                            'move_pct': move_pct,
                            'severity': 'warning' if abs(move_pct) >= pct_move*2 else 'info'
                        }
                        _emit(alert)


def list_alerts(limit: int = 100) -> List[Dict]:
    return list(_alerts)[-limit:]
