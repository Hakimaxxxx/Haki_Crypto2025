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
    st.plotly_chart(fig, use_container_width=True, key=key)


def show_pie_distribution(df_result):
    pie_df = df_result[["Coin", "Tổng giá trị"]].copy()
    pie_df = pie_df[pie_df["Tổng giá trị"] > 0]
    if pie_df.empty:
        return
    fig = px.pie(pie_df, names="Coin", values="Tổng giá trị", title="Tỉ lệ từng coin trong Portfolio", hole=0.3)
    st.plotly_chart(fig, use_container_width=True)


def show_bar_pnl(df_result):
    bar_df = df_result[["Coin", "Profit & Loss", "% Profit/Loss"]].copy()
    if bar_df.empty:
        return
    fig_bar = px.bar(bar_df, x="Coin", y=["Profit & Loss", "% Profit/Loss"], barmode="group",
                     title="PNL và % Profit/Loss theo coin",
                     labels={"value": "Giá trị", "variable": "Chỉ số"})
    st.plotly_chart(fig_bar, use_container_width=True)


def show_health_panel(db, queue_length: int, last_price_ts: int, last_price_update_message: str = ""):
    st.subheader("⚙️ System Health")
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
