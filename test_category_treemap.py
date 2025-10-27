"""Quick test for Category Performance Treemap"""
import sys
import os
os.chdir(r'd:\Crypto')
sys.path.insert(0, r'd:\Crypto')

from metrics_category_treemap import show_category_performance_metric

print("=" * 60)
print("CATEGORY PERFORMANCE TREEMAP TEST")
print("=" * 60)

# Mock Streamlit environment
class MockExpander:
    def __init__(self, title, **kwargs): print(f"\n[EXPANDER] {title}")
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def markdown(self, msg): print(f"  {msg}")

class MockSpinner:
    def __init__(self, msg): print(f"[LOADING] {msg}")
    def __enter__(self): return self
    def __exit__(self, *args): pass

class MockCol:
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def plotly_chart(self, fig, use_container_width=True):
        print(f"    [CHART] {fig.data[0].type}")
    def markdown(self, msg): print(f"    {msg}")
    def info(self, msg): print(f"    [INFO] {msg}")
    def dataframe(self, df, use_container_width=True):
        print(f"    [TABLE] {len(df)} rows")

class MockStreamlit:
    def info(self, msg): print(f"[INFO] {msg}")
    def warning(self, msg): print(f"[WARN] {msg}")
    def error(self, msg): print(f"[ERROR] {msg}")
    def success(self, msg): print(f"[OK] {msg}")
    def subheader(self, msg): print(f"\n## {msg}")
    def markdown(self, msg): print(msg)
    def caption(self, msg): print(f"  {msg}")
    def selectbox(self, label, options, **kwargs): return options[0] if options else None
    def button(self, label, **kwargs): return False
    def spinner(self, msg): return MockSpinner(msg)
    def expander(self, title, **kwargs): return MockExpander(title, **kwargs)
    def plotly_chart(self, fig, **kwargs):
        print(f"[CHART] Plotly chart ({fig.data[0].type})")
    def dataframe(self, df, **kwargs):
        try:
            rows = len(df.data) if hasattr(df, 'data') else len(df)
        except:
            rows = "?"
        print(f"[TABLE] DataFrame ({rows} rows)")
    def columns(self, spec): return [MockCol() for _ in (spec if isinstance(spec, list) else range(spec))]

import metrics_category_treemap
metrics_category_treemap.st = MockStreamlit()

# Run the metric
try:
    show_category_performance_metric()
    print("\n" + "=" * 60)
    print("TEST PASSED ✓")
    print("=" * 60)
except Exception as e:
    print("\n" + "=" * 60)
    print(f"TEST FAILED: {e}")
    import traceback
    traceback.print_exc()
    print("=" * 60)
