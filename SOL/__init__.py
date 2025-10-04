"""SOL package initializer.

Provides a safe lazy import function for whale alert realtime module to avoid
KeyError issues in constrained deployment environments where partial module
loading or packaging race conditions occur.
"""

def load_metrics_realtime():
	try:
		from . import metrics_sol_whale_alert_realtime  # type: ignore
		return metrics_sol_whale_alert_realtime
	except Exception:
		return None

__all__ = ["load_metrics_realtime"]
