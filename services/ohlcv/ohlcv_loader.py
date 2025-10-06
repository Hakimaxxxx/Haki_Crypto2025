"""OHLCV Loader (Phase 0 Consolidation)

Goal Phase 0:
	- Wrap existing scattered OHLCV fetching (currently in metrics_ohlcv_okx etc.)
	- Provide single function to get OHLCV dataframe for a symbol + timeframe.
	- Do NOT introduce caching layer yet (will add in later phases).
"""

from __future__ import annotations

from typing import Optional
import pandas as pd


def fetch_okx_ohlcv(symbol: str, bar: str = '15m', limit: int = 300) -> Optional[pd.DataFrame]:
	"""Fetch OHLCV via existing metrics module.

	Parameters
	----------
	symbol: e.g. 'BTC-USDT-SWAP'
	bar: timeframe string already accepted by current metrics module
	limit: number of rows
	"""
	try:
		import metrics_ohlcv_okx  # type: ignore
		df = metrics_ohlcv_okx.fetch_okx_ohlcv_cached(symbol=symbol, bar=bar, limit=limit)
		return df
	except Exception:
		return None


def normalize_datetime(df: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
	if df is None or df.empty:
		return df
	if 'datetime' in df.columns and not pd.api.types.is_datetime64_any_dtype(df['datetime']):
		try:
			df['datetime'] = pd.to_datetime(df['datetime'], utc=True, errors='coerce')
		except Exception:
			pass
	return df


def load_ohlcv(symbol: str, bar: str, limit: int = 300) -> Optional[pd.DataFrame]:
	df = fetch_okx_ohlcv(symbol=symbol, bar=bar, limit=limit)
	return normalize_datetime(df)


__all__ = ['load_ohlcv']
