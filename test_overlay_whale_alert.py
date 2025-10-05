import pandas as pd
from overlay_whale_alert import overlay_whale_alert_chart
import streamlit as st
import plotly.graph_objects as go

# Mock data for whale transactions
whale_txs = [
    {"value": 100, "type": "BUY", "time": "2025-10-05T12:00:00Z", "from": "0x123", "to": "0x456"},
    {"value": 200, "type": "SELL", "time": "2025-10-05T12:05:00Z", "from": "0x789", "to": "0xabc"},
    {"value": 50, "type": "BUY", "time": "2025-10-05T12:10:00Z", "from": "0xdef", "to": "0xghi"}
]

# Mock data for OHLCV DataFrame
data = {
    "datetime": pd.to_datetime([
        "2025-10-05T12:00:00Z",
        "2025-10-05T12:05:00Z",
        "2025-10-05T12:10:00Z",
        "2025-10-05T12:15:00Z"
    ]),
    "close": [1000, 1010, 1020, 1030]
}
df_ohlcv = pd.DataFrame(data)

# Streamlit mock setup
st.set_page_config(layout="wide")
st.title("Test Overlay Whale Alert Chart")

# Mock fig_ohlcv setup
fig = go.Figure()
fig.add_trace(go.Scatter(x=df_ohlcv['datetime'], y=df_ohlcv['close'], mode='lines', name='Price'))
st.session_state[f"fig_ohlcv_ERC20_TEST"] = fig

# Call the function with mock data
overlay_whale_alert_chart(
    whale_txs=whale_txs,
    df_ohlcv=df_ohlcv,
    coin_symbol="ERC20_TEST",
    slider_label="Filter Whale Transactions",
    slider_step=10.0,
    value_unit="TEST",
    type_map={"BUY": "Purchase", "SELL": "Sale"},
    color_map={"BUY": "#43a047", "SELL": "#e53935"},
    default_show=True,
    key_prefix="test_"
)

# Explicitly render the chart
st.plotly_chart(st.session_state[f"fig_ohlcv_ERC20_TEST"], use_container_width=True)