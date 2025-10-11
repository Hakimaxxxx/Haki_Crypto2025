def load_metrics_realtime():
	# Lightweight loader used by top-level app if needed
	from . import metrics_avax_whale_alert_realtime  # type: ignore
	return metrics_avax_whale_alert_realtime

__all__ = ["load_metrics_realtime"]
