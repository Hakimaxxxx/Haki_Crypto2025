"""
Test Portfolio Form Behavior

This script demonstrates the fixed behavior where:
1. User can edit multiple cells in data_editor without page reload
2. Page only reloads when user clicks "Đẩy dữ liệu lên DB" or "Cập nhật AVG"
"""

import streamlit as st
import pandas as pd

st.title("Portfolio Form Test")

st.info("""
✅ **Fixed Issues:**
- Before: Page reloaded on every cell edit → Annoying!
- After: Page only reloads when you click submit buttons → Smooth!

**Test Steps:**
1. Edit multiple cells in the table below
2. Notice the page does NOT reload while editing
3. Click "Submit Changes" to save
4. Page reloads only after submit
""")

# Sample data
if "test_data" not in st.session_state:
    st.session_state.test_data = pd.DataFrame({
        "Coin": ["BTC", "ETH", "SOL"],
        "Holdings": [1.5, 10.0, 100.0],
        "Avg Price": [50000.0, 3000.0, 150.0]
    })

# Form wrapping the data_editor
with st.form(key="test_form"):
    st.write("### Edit Portfolio Data")
    
    edited = st.data_editor(
        st.session_state.test_data,
        column_config={
            "Holdings": st.column_config.NumberColumn("Holdings", min_value=0.0, format="%.8f"),
            "Avg Price": st.column_config.NumberColumn("Avg Price", min_value=0.0, format="%.2f")
        },
        hide_index=True,
        key="data_table"
    )
    
    # Store in session_state for access after submission
    st.session_state._temp_edited = edited
    
    submit = st.form_submit_button("💾 Submit Changes", type="primary")

# Handle submission
if submit:
    st.session_state.test_data = st.session_state._temp_edited
    st.success("✅ Data saved successfully!")
    st.balloons()

# Display current data
st.write("### Current Saved Data")
st.dataframe(st.session_state.test_data, use_container_width=True)

st.markdown("---")
st.caption("🎯 This is how Portfolio tab now works - no more annoying reloads during editing!")
