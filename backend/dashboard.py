#!/usr/bin/env python3
"""Real-time IoT monitoring dashboard built with Streamlit + Plotly.

Usage:
    streamlit run dashboard.py
"""

import time
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
from influxdb_client import InfluxDBClient

import config

# ──────────────────────────── Page config ─────────────────────
st.set_page_config(
    page_title="IoT Lab 2 — Dashboard",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────── Custom CSS ──────────────────────
st.markdown("""
<style>
/* ── Import Google Font ─────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="st-"] {
    font-family: 'Inter', sans-serif;
}

/* ── Main area ──────────────────────────────────────────── */
.stApp {
    background: linear-gradient(135deg, #0F172A 0%, #1E293B 100%);
}

/* ── Sidebar ────────────────────────────────────────────── */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #1E293B 0%, #0F172A 100%);
    border-right: 1px solid rgba(0, 212, 255, 0.15);
}

/* ── Metric cards ───────────────────────────────────────── */
div[data-testid="stMetric"] {
    background: linear-gradient(135deg, rgba(30,41,59,0.8), rgba(15,23,42,0.9));
    border: 1px solid rgba(0,212,255,0.2);
    border-radius: 12px;
    padding: 16px 20px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.3);
    transition: transform 0.2s, box-shadow 0.2s;
}
div[data-testid="stMetric"]:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 30px rgba(0,212,255,0.15);
}
div[data-testid="stMetric"] label {
    color: #94A3B8 !important;
    font-weight: 500;
    text-transform: uppercase;
    font-size: 0.72rem !important;
    letter-spacing: 0.05em;
}
div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
    color: #F1F5F9 !important;
    font-weight: 700;
}

/* ── Tabs ───────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    gap: 4px;
    background: rgba(30,41,59,0.5);
    border-radius: 12px;
    padding: 4px;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px;
    color: #94A3B8;
    font-weight: 500;
    padding: 8px 20px;
}
.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, #0EA5E9, #7C3AED) !important;
    color: #fff !important;
}

/* ── Headers ────────────────────────────────────────────── */
h1, h2, h3 { color: #F1F5F9 !important; }

/* ── Dataframe ──────────────────────────────────────────── */
.stDataFrame { border-radius: 12px; overflow: hidden; }

/* ── Status pill ────────────────────────────────────────── */
.status-pill {
    display: inline-block;
    padding: 4px 14px;
    border-radius: 20px;
    font-size: 0.8rem;
    font-weight: 600;
}
.status-online  { background: rgba(16,185,129,0.2); color: #10B981; border: 1px solid rgba(16,185,129,0.4); }
.status-offline { background: rgba(239,68,68,0.2);  color: #EF4444; border: 1px solid rgba(239,68,68,0.4);  }
</style>
""", unsafe_allow_html=True)

_PLOTLY_BASE = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(15,23,42,0.6)",
    font=dict(family="Inter", color="#CBD5E1"),
    margin=dict(l=40, r=20, t=40, b=30),
    legend=dict(bgcolor="rgba(0,0,0,0)"),
)

def apply_layout(fig, **overrides):
    """Apply the base dark theme then layer any per-chart overrides."""
    fig.update_layout(**_PLOTLY_BASE)
    if overrides:
        fig.update_layout(**overrides)
    return fig

COLOR_TEMP = "#F97316"       # orange
COLOR_HUMID = "#0EA5E9"      # sky
COLOR_DIST = "#A855F7"       # purple
COLOR_LATENCY = "#10B981"    # emerald
COLOR_RSSI = "#F43F5E"       # rose

NUMERIC_COLS = ["temperature_c", "humidity_pct", "distance_cm"]


# ──────────────────────────── InfluxDB queries ────────────────
@st.cache_resource
def get_influx_client():
    return InfluxDBClient(
        url=config.INFLUXDB_URL,
        token=config.INFLUXDB_TOKEN,
        org=config.INFLUXDB_ORG,
    )


def query_bucket(bucket: str, hours: int, fields: list[str] | None = None) -> pd.DataFrame:
    """Generic Flux query returning a pivoted DataFrame."""
    client = get_influx_client()

    field_filter = ""
    if fields:
        clauses = " or ".join(f'r._field == "{f}"' for f in fields)
        field_filter = f'|> filter(fn: (r) => {clauses})'

    query = f'''
    from(bucket: "{bucket}")
      |> range(start: -{hours}h)
      |> filter(fn: (r) => r._measurement == "telemetry" or r._measurement == "telemetry_processed")
      {field_filter}
      |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
      |> sort(columns: ["_time"])
    '''

    try:
        tables = client.query_api().query_data_frame(query)
    except Exception as exc:
        st.error(f"InfluxDB query error: {exc}")
        return pd.DataFrame()

    if isinstance(tables, list):
        if not tables:
            return pd.DataFrame()
        tables = pd.concat(tables, ignore_index=True)

    if tables.empty:
        return pd.DataFrame()

    df = tables.copy()
    time_col = "_time" if "_time" in df.columns else "time"
    df["time"] = pd.to_datetime(df[time_col], utc=True)
    df = df.set_index("time").sort_index()
    return df


# ──────────────────────────── Sidebar ─────────────────────────
with st.sidebar:
    st.markdown("## 📡 IoT Lab 2")
    st.markdown("**Thu thập & Giám sát dữ liệu**")
    st.markdown("---")

    hours = st.slider("🕐 Khoảng thời gian (giờ)", 1, 48, config.DASHBOARD_DEFAULT_HOURS)
    auto_refresh = st.toggle("🔄 Tự động làm mới", value=True)
    if auto_refresh:
        refresh_sec = st.slider("Chu kỳ (giây)", 3, 30, config.DASHBOARD_REFRESH_SECONDS)

    st.markdown("---")

    # Connection status check
    try:
        c = get_influx_client()
        c.ping()
        st.markdown('<span class="status-pill status-online">● InfluxDB Online</span>', unsafe_allow_html=True)
    except Exception:
        st.markdown('<span class="status-pill status-offline">● InfluxDB Offline</span>', unsafe_allow_html=True)

    st.markdown("---")
    st.caption(f"Cập nhật: {datetime.now().strftime('%H:%M:%S')}")

# ──────────────────────────── Main tabs ───────────────────────
tab_overview, tab_raw, tab_processed, tab_latency = st.tabs([
    "📊 Tổng quan",
    "📈 Dữ liệu thô",
    "🔬 Dữ liệu đã xử lý",
    "⏱ Phân tích độ trễ",
])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━ TAB 1: OVERVIEW ━━━━━━━━━━━━━━━━
with tab_overview:
    st.markdown("### Tổng quan hệ thống")
    raw_df = query_bucket(
        config.INFLUXDB_BUCKET_RAW, hours,
        ["temperature_c", "humidity_pct", "distance_cm", "latency_ms", "rssi_dbm", "sequence"],
    )

    if raw_df.empty:
        st.warning("⚠️ Chưa có dữ liệu. Hãy chạy firmware và mqtt_subscriber trước.")
    else:
        # ── KPI Metrics ──
        latest = raw_df.iloc[-1]
        col1, col2, col3, col4, col5 = st.columns(5)

        def delta_str(col_name):
            if col_name in raw_df.columns and len(raw_df) >= 2:
                d = raw_df[col_name].iloc[-1] - raw_df[col_name].iloc[-2]
                return f"{d:+.1f}"
            return None

        with col1:
            st.metric("🌡 Nhiệt độ",
                       f"{latest.get('temperature_c', 0):.1f} °C",
                       delta_str("temperature_c"))
        with col2:
            st.metric("💧 Độ ẩm",
                       f"{latest.get('humidity_pct', 0):.1f} %",
                       delta_str("humidity_pct"))
        with col3:
            st.metric("📏 Khoảng cách",
                       f"{latest.get('distance_cm', 0):.1f} cm",
                       delta_str("distance_cm"))
        with col4:
            latency_val = latest.get("latency_ms", 0)
            st.metric("⏱ Độ trễ",
                       f"{latency_val:.0f} ms",
                       delta_str("latency_ms"),
                       delta_color="inverse")
        with col5:
            st.metric("📶 RSSI",
                       f"{latest.get('rssi_dbm', 0):.0f} dBm",
                       delta_str("rssi_dbm"))

        st.markdown("")

        # ── Combined real-time chart ──
        fig = go.Figure()

        if "temperature_c" in raw_df.columns:
            fig.add_trace(go.Scatter(
                x=raw_df.index, y=raw_df["temperature_c"],
                name="Nhiệt độ (°C)", line=dict(color=COLOR_TEMP, width=2),
                yaxis="y",
            ))
        if "humidity_pct" in raw_df.columns:
            fig.add_trace(go.Scatter(
                x=raw_df.index, y=raw_df["humidity_pct"],
                name="Độ ẩm (%)", line=dict(color=COLOR_HUMID, width=2),
                yaxis="y2",
            ))
        if "distance_cm" in raw_df.columns:
            fig.add_trace(go.Scatter(
                x=raw_df.index, y=raw_df["distance_cm"],
                name="Khoảng cách (cm)", line=dict(color=COLOR_DIST, width=2),
                yaxis="y3",
            ))

        apply_layout(fig,
            title="Dữ liệu cảm biến real-time",
            height=420,
            yaxis=dict(title=dict(text="°C", font=dict(color=COLOR_TEMP)),
                       tickfont=dict(color=COLOR_TEMP),
                       gridcolor="rgba(148,163,184,0.08)"),
            yaxis2=dict(title=dict(text="%", font=dict(color=COLOR_HUMID)),
                        tickfont=dict(color=COLOR_HUMID),
                        anchor="free", overlaying="y", side="right", position=0.95),
            yaxis3=dict(title=dict(text="cm", font=dict(color=COLOR_DIST)),
                        tickfont=dict(color=COLOR_DIST),
                        anchor="free", overlaying="y", side="right", position=1.0),
            legend=dict(orientation="h", y=1.12),
        )
        st.plotly_chart(fig, width="stretch")

        # ── Stats summary ──
        st.markdown("### 📋 Thống kê tổng hợp")
        stat_cols = [c for c in NUMERIC_COLS if c in raw_df.columns]
        NUMERIC_COLS_OVERVIEW = ["temperature_c", "humidity_pct", "distance_cm"]
        stat_cols = [c for c in NUMERIC_COLS_OVERVIEW if c in raw_df.columns]
        if stat_cols:
            stats_df = raw_df[stat_cols].describe().T
            stats_df.columns = ["Số lượng", "Trung bình", "Độ lệch chuẩn",
                                "Min", "Q1 (25%)", "Median", "Q3 (75%)", "Max"]
            st.dataframe(stats_df.style.format("{:.2f}"), width="stretch")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━ TAB 2: RAW DATA ━━━━━━━━━━━━━━━━
with tab_raw:
    st.markdown("### Dữ liệu thô từ cảm biến")
    raw_df2 = query_bucket(
        config.INFLUXDB_BUCKET_RAW, hours,
        ["temperature_c", "humidity_pct", "distance_cm", "rssi_dbm", "latency_ms", "sequence"],
    )

    if raw_df2.empty:
        st.info("Chưa có dữ liệu thô.")
    else:
        # Individual sensor charts
        for col, label, color, unit in [
            ("temperature_c", "Nhiệt độ", COLOR_TEMP, "°C"),
            ("humidity_pct", "Độ ẩm", COLOR_HUMID, "%"),
            ("distance_cm", "Khoảng cách", COLOR_DIST, "cm"),
        ]:
            if col not in raw_df2.columns:
                continue

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=raw_df2.index, y=raw_df2[col],
                mode="lines+markers",
                name=label,
                line=dict(color=color, width=2),
                marker=dict(size=4, color=color),
                fill="tozeroy",
                fillcolor=color.replace(")", ",0.08)").replace("rgb", "rgba")
                           if color.startswith("rgb") else f"{color}14",
            ))
            apply_layout(fig,
                title=f"{label} ({unit})",
                height=300,
                yaxis_title=unit,
            )
            st.plotly_chart(fig, width="stretch")

        # Raw data table
        with st.expander("📄 Bảng dữ liệu thô (50 bản ghi gần nhất)"):
            display_cols = [c for c in ["sequence", "temperature_c", "humidity_pct",
                                        "distance_cm", "rssi_dbm", "latency_ms"]
                           if c in raw_df2.columns]
            st.dataframe(
                raw_df2[display_cols].tail(50).sort_index(ascending=False),
                width="stretch",
            )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━ TAB 3: PROCESSED ━━━━━━━━━━━━━━━
with tab_processed:
    st.markdown("### Dữ liệu sau tiền xử lý")

    proc_df = query_bucket(config.INFLUXDB_BUCKET_PROCESSED, hours)

    if proc_df.empty:
        st.info("Chưa có dữ liệu đã xử lý. Chạy `python preprocessing.py` trước.")
    else:
        # ── Before / After comparison ──
        st.markdown("#### So sánh trước & sau xử lý")
        raw_cmp = query_bucket(
            config.INFLUXDB_BUCKET_RAW, hours,
            ["temperature_c", "humidity_pct", "distance_cm"],
        )

        for col, label, color in [
            ("temperature_c", "Nhiệt độ", COLOR_TEMP),
            ("humidity_pct", "Độ ẩm", COLOR_HUMID),
            ("distance_cm", "Khoảng cách", COLOR_DIST),
        ]:
            if col not in proc_df.columns:
                continue

            fig = go.Figure()
            if not raw_cmp.empty and col in raw_cmp.columns:
                fig.add_trace(go.Scatter(
                    x=raw_cmp.index, y=raw_cmp[col],
                    name="Dữ liệu thô",
                    mode="lines",
                    line=dict(color="#475569", width=1, dash="dot"),
                    opacity=0.6,
                ))
            fig.add_trace(go.Scatter(
                x=proc_df.index, y=proc_df[col],
                name="Sau xử lý",
                mode="lines",
                line=dict(color=color, width=2.5),
            ))

            # Highlight outliers
            outlier_col = f"{col}_outlier"
            if outlier_col in proc_df.columns:
                outliers = proc_df[proc_df[outlier_col] > 0.5]
                if not outliers.empty and col in outliers.columns:
                    fig.add_trace(go.Scatter(
                        x=outliers.index, y=outliers[col],
                        name="Outlier phát hiện",
                        mode="markers",
                        marker=dict(color="#EF4444", size=10, symbol="x"),
                    ))

            apply_layout(fig, title=f"{label} — Thô vs. Đã xử lý", height=320)
            st.plotly_chart(fig, width="stretch")

        # ── Rolling mean ──
        st.markdown("#### Đặc trưng: Rolling Mean")
        rolling_cols_present = [c for c in proc_df.columns if c.endswith("_rolling_mean")]
        if rolling_cols_present:
            fig_roll = go.Figure()
            colors_map = {
                "temperature_c_rolling_mean": COLOR_TEMP,
                "humidity_pct_rolling_mean": COLOR_HUMID,
                "distance_cm_rolling_mean": COLOR_DIST,
            }
            for rc in rolling_cols_present:
                fig_roll.add_trace(go.Scatter(
                    x=proc_df.index, y=proc_df[rc],
                    name=rc.replace("_rolling_mean", "").replace("_", " ").title(),
                    line=dict(color=colors_map.get(rc, "#94A3B8"), width=2),
                ))
            apply_layout(fig_roll, title="Rolling Mean (window=6)", height=320)
            st.plotly_chart(fig_roll, width="stretch")

        # ── Normalised data ──
        st.markdown("#### Dữ liệu chuẩn hóa (Min-Max)")
        norm_cols = [c for c in proc_df.columns if c.endswith("_norm_minmax")]
        if norm_cols:
            fig_norm = go.Figure()
            norm_colors = {
                "temperature_c_norm_minmax": COLOR_TEMP,
                "humidity_pct_norm_minmax": COLOR_HUMID,
                "distance_cm_norm_minmax": COLOR_DIST,
            }
            for nc in norm_cols:
                fig_norm.add_trace(go.Scatter(
                    x=proc_df.index, y=proc_df[nc],
                    name=nc.replace("_norm_minmax", ""),
                    line=dict(color=norm_colors.get(nc, "#94A3B8"), width=2),
                ))
            apply_layout(fig_norm, title="Chuẩn hóa Min-Max [0, 1]", height=320,
                                    yaxis=dict(range=[-0.05, 1.05]))
            st.plotly_chart(fig_norm, width="stretch")

        # Processed data table
        with st.expander("📄 Bảng dữ liệu đã xử lý"):
            st.dataframe(proc_df.tail(50).sort_index(ascending=False), width="stretch")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━ TAB 4: LATENCY ━━━━━━━━━━━━━━━━━
with tab_latency:
    st.markdown("### Phân tích độ trễ End-to-End")

    lat_df = query_bucket(config.INFLUXDB_BUCKET_RAW, hours, ["latency_ms"])

    if lat_df.empty or "latency_ms" not in lat_df.columns:
        st.info("Chưa có dữ liệu độ trễ.")
    else:
        latency = lat_df["latency_ms"].dropna()

        # KPIs
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Trung bình", f"{latency.mean():.1f} ms")
        with c2:
            st.metric("Median (P50)", f"{latency.median():.1f} ms")
        with c3:
            st.metric("P95", f"{latency.quantile(0.95):.1f} ms")
        with c4:
            st.metric("Max", f"{latency.max():.0f} ms")

        # Latency over time
        fig_lat = go.Figure()
        fig_lat.add_trace(go.Scatter(
            x=latency.index, y=latency,
            mode="lines+markers",
            name="Latency",
            line=dict(color=COLOR_LATENCY, width=2),
            marker=dict(size=4),
        ))
        # Rolling average
        if len(latency) >= 6:
            rolling_lat = latency.rolling(window=6, min_periods=1).mean()
            fig_lat.add_trace(go.Scatter(
                x=rolling_lat.index, y=rolling_lat,
                name="Rolling avg (6)",
                line=dict(color="#F59E0B", width=2, dash="dash"),
            ))
        apply_layout(fig_lat, title="Độ trễ theo thời gian", height=380,
                               yaxis_title="ms")
        st.plotly_chart(fig_lat, width="stretch")

        # Distribution histogram
        col_left, col_right = st.columns(2)
        with col_left:
            fig_hist = go.Figure()
            fig_hist.add_trace(go.Histogram(
                x=latency,
                nbinsx=30,
                marker_color=COLOR_LATENCY,
                opacity=0.8,
            ))
            apply_layout(fig_hist, title="Phân phối độ trễ",
                                    height=350, xaxis_title="ms", yaxis_title="Tần suất")
            st.plotly_chart(fig_hist, width="stretch")

        with col_right:
            fig_box = go.Figure()
            fig_box.add_trace(go.Box(
                y=latency,
                name="Latency",
                marker_color=COLOR_LATENCY,
                boxmean="sd",
            ))
            apply_layout(fig_box, title="Box-plot độ trễ",
                                   height=350, yaxis_title="ms")
            st.plotly_chart(fig_box, width="stretch")

        # Stats table
        with st.expander("📊 Bảng thống kê chi tiết"):
            stats_series = latency.describe()
            stats_series["variance"] = latency.var()
            stats_series["skewness"] = latency.skew()
            stats_series["kurtosis"] = latency.kurtosis()
            st.dataframe(
                pd.DataFrame(stats_series, columns=["Giá trị"]).T,
                width="stretch",
            )

# ──────────────────────────── Auto-refresh ────────────────────
if auto_refresh:
    time.sleep(refresh_sec)
    st.rerun()
