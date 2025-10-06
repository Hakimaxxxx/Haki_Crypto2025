"""Unified Whale Data Loading Utilities (Phase 0 Refactor)

Purpose (Phase 0):
	- Centralize scattered whale history loading logic from multiple places (BTC, BNB, ERC20, SOL, etc.).
	- No new features; only consolidation + light normalization helpers.
	- Provide a stable import surface for future Phase 1 API extraction.

Do NOT add network fetching logic here yet. Only local file / existing module adapters.
"""

from __future__ import annotations

import json
import os
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime, timezone

import pandas as pd


# ---------- Generic helpers ---------- #

def _safe_read_json(path: str) -> Optional[List[Dict[str, Any]]]:
	if not path or not os.path.exists(path):
		return None
	try:
		with open(path, 'r', encoding='utf-8') as f:
			data = json.load(f)
			if isinstance(data, list):
				return data
			# Some legacy formats might store {"history": [...]} style
			if isinstance(data, dict):
				for k in ("history", "data", "events"):
					if k in data and isinstance(data[k], list):
						return data[k]
	except Exception:
		return None
	return None


def _normalize_event(evt: Dict[str, Any], token: Optional[str] = None) -> Dict[str, Any]:
	"""Best-effort normalization across different whale event sources.

	Normalized keys:
		- token (str)
		- direction (BUY/SELL/TRANSFER/N/A)
		- amount_token (float)
		- amount_usd (float|None)
		- tx_hash (str|None)
		- ts (UTC aware datetime) or 'timestamp' numeric preserved
	"""
	out = dict(evt)  # shallow copy
	if token and 'token' not in out:
		out['token'] = token

	# Direction harmonization
	dir_raw = (out.get('type') or out.get('direction') or out.get('side') or '').upper()
	if dir_raw in ("BUY", "SELL"):
		direction = dir_raw
	elif dir_raw in ("TRANSFER", "MOVE"):
		direction = "TRANSFER"
	else:
		direction = "N/A"
	out['direction'] = direction

	# Amount token (mở rộng thêm 'value' vì nhiều nguồn chỉ có 'value')
	for key_candidate in ["amount_token", "amount", "qty", "value_token", "value"]:
		if key_candidate in out:
			try:
				out['amount_token'] = float(out[key_candidate])
			except Exception:
				pass
			break

	# USD amount (optional)
	for usd_candidate in ["amount_usd", "usd_value", "value_usd"]:
		if usd_candidate in out:
			try:
				out['amount_usd'] = float(out[usd_candidate])
			except Exception:
				pass
			break

	# Standardize timestamp -> prefer numeric epoch
	ts_val = out.get('ts') or out.get('timestamp') or out.get('time')
	if isinstance(ts_val, (int, float)):
		try:
			out['ts'] = datetime.fromtimestamp(float(ts_val), tz=timezone.utc)
		except Exception:
			pass
	elif isinstance(ts_val, str):
		# Try parse ISO or number-in-string
		try:
			if ts_val.isdigit():
				out['ts'] = datetime.fromtimestamp(float(ts_val), tz=timezone.utc)
			else:
				out['ts'] = datetime.fromisoformat(ts_val.replace('Z', '+00:00')).astimezone(timezone.utc)
		except Exception:
			pass

	return out


def normalize_events(events: List[Dict[str, Any]], token: Optional[str] = None) -> List[Dict[str, Any]]:
	return [_normalize_event(e, token) for e in events]


# ---------- Loader Functions Per Domain (adapters) ---------- #

def load_btc_whales() -> List[Dict[str, Any]]:
	try:
		from BTC import metrics_btc_whale_alert_realtime as btc_mod  # type: ignore
		events = btc_mod.load_whale_history()
		return normalize_events(events, token='BTC') if events else []
	except Exception:
		return []


def load_bnb_whales() -> List[Dict[str, Any]]:
	try:
		from BNB import metrics_bnb_whale_alert_realtime as bnb_mod  # type: ignore
		events = bnb_mod.load_whale_history()
		return normalize_events(events, token='BNB') if events else []
	except Exception:
		return []


def load_erc20_whales(token_symbol: str, history_file: Optional[str] = None) -> List[Dict[str, Any]]:
	"""Load ERC20 whale events for a given token symbol.

	Priority:
		1. If ERC20 module provides a recent loader -> use it.
		2. Fallback to local history_file.
	"""
	events: List[Dict[str, Any]] = []
	try:
		from ERC20.metrics_erc20_whale_alert_realtime import (
			load_recent_whale_events, ERC20_TOKENS
		)  # type: ignore

		# Attempt dynamic config resolve if not provided
		if history_file is None:
			for cfg in ERC20_TOKENS:
				if cfg.get('name') == token_symbol:
					history_file = cfg.get('history_file')
					break

		try:
			df_recent = load_recent_whale_events(token_symbol, limit=150)
			if df_recent is not None and not df_recent.empty:
				events = df_recent.to_dict(orient='records')
		except Exception:
			pass

	except Exception:
		# ERC20 module missing or failed → ignore
		pass

	if not events and history_file:
		file_events = _safe_read_json(history_file) or []
		events = file_events

	return normalize_events(events, token=token_symbol)


def load_sol_whales() -> List[Dict[str, Any]]:
	try:
		from SOL import metrics_sol_whale_alert_realtime as sol_mod  # type: ignore
		events = sol_mod.load_whale_history()
		return normalize_events(events, token='SOL') if events else []
	except Exception:
		return []


# ---------- Aggregated / Generic API ---------- #

LOADERS: Dict[str, Callable[[], List[Dict[str, Any]]]] = {
	'BTC': load_btc_whales,
	'BNB': load_bnb_whales,
	'SOL': load_sol_whales,
}


def load_whales_for_symbol(symbol: str) -> List[Dict[str, Any]]:
	sym = symbol.upper()
	if sym in LOADERS:
		return LOADERS[sym]()
	# Assume ERC20 fallback
	return load_erc20_whales(sym)


def to_dataframe(events: List[Dict[str, Any]]) -> pd.DataFrame:
	if not events:
		return pd.DataFrame(columns=["token", "direction", "amount_token", "amount_usd", "ts"])
	df = pd.DataFrame(events)
	# Ensure ts column normalized
	if 'ts' in df.columns:
		if not pd.api.types.is_datetime64_any_dtype(df['ts']):
			try:
				df['ts'] = pd.to_datetime(df['ts'], utc=True, errors='coerce')
			except Exception:
				pass
	return df


__all__ = [
	'load_btc_whales', 'load_bnb_whales', 'load_sol_whales', 'load_erc20_whales',
	'load_whales_for_symbol', 'normalize_events', 'to_dataframe', 'as_overlay_events'
]


def as_overlay_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
	"""Convert normalized whale events into the format expected by overlay_whale_alert_chart.

	overlay_whale_alert_chart expects keys:
		- value (numeric)
		- type  (BUY/SELL/...)
		- time  (ISO string or parseable)
		- hash  (tx hash) optional
		- from, to (addresses)
	"""
	adapted: List[Dict[str, Any]] = []
	for e in events:
		value = e.get('value')
		if value is None:
			for cand in ('amount_token', 'amount', 'qty', 'value_token'):
				if cand in e:
					try:
						value = float(e[cand])
					except Exception:
						value = None
					break
		if value is None:
			continue  # skip unusable
		# Time resolution
		time_val = e.get('time')
		if not time_val:
			ts = e.get('ts')
			if isinstance(ts, datetime):
				time_val = ts.isoformat()
			else:
				time_val = ts
		adapted.append({
			'value': value,
			'type': e.get('direction') or e.get('type') or 'N/A',
			'time': time_val,
			'hash': e.get('tx_hash') or e.get('hash') or e.get('id'),
			'from': e.get('wallet_from') or e.get('from'),
			'to': e.get('wallet_to') or e.get('to')
		})
	return adapted
