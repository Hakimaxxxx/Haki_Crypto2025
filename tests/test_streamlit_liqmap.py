"""
Quick test of Liquidation Map in Streamlit
Run: streamlit run tests/test_streamlit_liqmap.py
"""

import streamlit as st
import sys
import os

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

st.set_page_config(page_title="Liquidation Map Test", page_icon="🔥", layout="wide")

st.title("🔥 Liquidation Map - Test Page")

# Import and run the UI
try:
    from metrics_liquidation_map import show_liquidation_map_ui
    show_liquidation_map_ui()
except Exception as e:
    st.error(f"Error: {e}")
    import traceback
    st.code(traceback.format_exc())
