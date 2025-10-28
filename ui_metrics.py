import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import streamlit as st
import pytz
from typing import Dict, List
from portfolio_history import filter_portfolio_totals, filter_coin_history


def show_portfolio_over_time_chart(history, tz_display="Asia/Bangkok", key="main_line_chart"):
    if not history:
        st.info("Chưa có dữ liệu lịch sử portfolio.")
        return
    tz = pytz.timezone(tz_display)
    df_totals = pd.DataFrame(filter_portfolio_totals(history))
    if df_totals.empty:
        st.info("Không có bản ghi tổng Portfolio.")
        return
    df_totals["Date"] = pd.to_datetime(df_totals["timestamp"], unit="s").dt.tz_localize("UTC").dt.tz_convert(tz)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_totals["Date"], y=df_totals["value"], name="Portfolio Value", yaxis="y1", line=dict(color="royalblue")))
    if "PNL" in df_totals.columns:
        fig.add_trace(go.Scatter(x=df_totals["Date"], y=df_totals["PNL"], name="PNL", yaxis="y1", line=dict(color="orange"), visible="legendonly"))
    fig.update_layout(
        title="Portfolio Value & PNL Over Time",
        xaxis=dict(title="Date"),
        yaxis=dict(title="Value / PNL (USD)", side="left"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig, use_container_width=True, key=key, config={'displaylogo': False, 'responsive': True})


def show_pie_distribution(df_result):
    pie_df = df_result[["Coin", "Tổng giá trị"]].copy()
    pie_df = pie_df[pie_df["Tổng giá trị"] > 0]
    if pie_df.empty:
        return
    fig = px.pie(pie_df, names="Coin", values="Tổng giá trị", title="Tỉ lệ từng coin trong Portfolio", hole=0.3)
    st.plotly_chart(fig, use_container_width=True, config={'displaylogo': False, 'responsive': True})


def show_bar_pnl(df_result):
    bar_df = df_result[["Coin", "Profit & Loss", "% Profit/Loss"]].copy()
    if bar_df.empty:
        return
    fig_bar = px.bar(bar_df, x="Coin", y=["Profit & Loss", "% Profit/Loss"], barmode="group",
                     title="PNL và % Profit/Loss theo coin",
                     labels={"value": "Giá trị", "variable": "Chỉ số"})
    st.plotly_chart(fig_bar, use_container_width=True, config={'displaylogo': False, 'responsive': True})


def show_health_panel(db, queue_length: int, last_price_ts: int, last_price_update_message: str = ""):
    st.subheader("⚙️ System Health")
    
    # First row: DB, Queue, Price Update
    cols = st.columns(4)
    with cols[0]:
        st.metric("DB Available", "Yes" if db.available() else "No")
    with cols[1]:
        st.metric("Queue Pending", queue_length)
    with cols[2]:
        if last_price_ts:
            st.metric("Last Price Update", last_price_ts)
        else:
            st.metric("Last Price Update", "N/A")
    with cols[3]:
        st.write(last_price_update_message or "")
    
    # Second row: RSI Sync Status
    try:
        import rsi_sync
        sync_status = rsi_sync.get_sync_status()
        
        st.markdown("---")
        st.markdown("#### 📊 RSI Background Sync")
        
        cols2 = st.columns(4)
        with cols2[0]:
            status_icon = "✅" if sync_status['running'] else "❌"
            st.metric("Sync Status", f"{status_icon} {'Running' if sync_status['running'] else 'Stopped'}")
        with cols2[1]:
            st.metric("Interval", f"{sync_status['interval_minutes']:.0f} min")
        with cols2[2]:
            # Count how many timeframes have been synced
            synced_count = len([t for t in sync_status['last_sync'] if sync_status['last_sync'][t] != 'Never'])
            total_count = len(sync_status['timeframes'])
            st.metric("Timeframes Synced", f"{synced_count}/{total_count}")
        with cols2[3]:
            error_count = len(sync_status.get('errors', []))
            st.metric("Recent Errors", error_count)
        
        # Show last sync times
        if sync_status['last_sync']:
            st.caption("**Last Sync Times:**")
            sync_info = []
            for tf in sync_status['timeframes']:
                last = sync_status['last_sync'].get(tf, 'Never')
                if last != 'Never':
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(last.replace('Z', '+00:00'))
                        mins_ago = (datetime.now(dt.tzinfo) - dt).total_seconds() / 60
                        last = f"{mins_ago:.0f}m ago"
                    except:
                        pass
                sync_info.append(f"{tf}: {last}")
            st.caption(" | ".join(sync_info))
        
        # Show recent errors if any
        if error_count > 0:
            with st.expander(f"⚠️ Recent Errors ({error_count})"):
                for err in sync_status['errors'][-5:]:  # Last 5 errors
                    st.code(f"{err['timestamp']}: {err['message']}")
    
    except Exception as e:
        st.caption(f"RSI sync status unavailable: {e}")

