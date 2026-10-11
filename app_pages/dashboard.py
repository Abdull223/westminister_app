import numpy as np
import pandas as pd
import streamlit as st

from core import charts
from core import intelligence as intel
from core.state import require_dataset

ds = require_dataset()

st.title("Cash-flow dashboard")
st.caption(f"{ds.name} · SHA-256 fingerprint `{ds.hash}`")

metric = ds.schema["metric"]
date_col = ds.schema["dates"][0] if ds.schema["dates"] else None
total_value = float(ds.clean_df[metric].sum()) if metric and len(ds.clean_df) else 0.0
checks_ok = sum(1 for _, ok, _ in ds.checks if ok)

# Monthly series powers both the trend chart and the KPI sparklines.
monthly = None
if metric and date_col is not None:
    d = ds.clean_df[[date_col, metric]].dropna().copy()
    d[date_col] = intel.parse_dates(d[date_col])
    monthly = d.dropna().set_index(date_col)[metric].resample("MS").sum().reset_index()
    if not len(monthly):
        monthly = None

spark = charts.spark_values(monthly, date_col, metric) if monthly is not None else None
forecast = intel.project_monthly(monthly, date_col, metric) if monthly is not None else None
delta = None
if monthly is not None and len(monthly) >= 2 and monthly[metric].iloc[-2]:
    growth = (monthly[metric].iloc[-1] - monthly[metric].iloc[-2]) / monthly[metric].iloc[-2] * 100
    delta = f"{growth:+.1f}% MoM"

with st.container(horizontal=True):
    st.metric("Records analysed", f"{len(ds.clean_df):,}", border=True)
    st.metric("Data quality", f"{ds.quality['overall']:.1f}%", border=True)
    st.metric("Integrity checks", f"{checks_ok}/{len(ds.checks)} passed", border=True)
    if metric:
        st.metric(
            "Ledger value",
            f"KES {total_value:,.0f}",
            delta=delta,
            border=True,
            **({"chart_data": spark, "chart_type": "line"} if spark else {}),
        )
    if forecast is not None:
        nxt = float(forecast["Projected"].iloc[1])
        last_actual = float(monthly[metric].iloc[-1])
        st.metric(
            "Projected next month",
            f"KES {nxt:,.0f}",
            delta=f"{(nxt - last_actual) / last_actual * 100:+.1f}% vs latest" if last_actual else None,
            border=True,
        )

with st.form("ledger_search", border=False):
    row = st.container(horizontal=True)
    query = row.text_input("Ask the ledger", placeholder="Search any value, e.g. Nairobi or INV-1002", label_visibility="collapsed")
    row.form_submit_button("Search", icon=":material/search:")
if query:
    text = ds.clean_df.astype(str)
    hit = ds.clean_df[(text.apply(lambda col: col.str.contains(query, case=False, na=False)).any(axis=1))]
    st.dataframe(hit, hide_index=True, height=240)
    st.caption(f"{len(hit):,} of {len(ds.clean_df):,} records match “{query}”.")

left, right = st.columns([1.4, 1])
with left:
    with st.container(border=True):
        if metric and monthly is not None:
            if forecast is not None:
                st.altair_chart(charts.forecast_trend(monthly, forecast, date_col, metric, "Projected", "Monthly cash flow · 3-month projection"))
                st.caption("Dashed line: least-squares linear projection over the last months of actual ledger activity.")
            else:
                st.altair_chart(charts.area_trend(monthly, date_col, metric, "Monthly cash flow"))
        elif metric:
            st.altair_chart(charts.histogram(ds.clean_df, metric, f"Distribution of {metric}"))
        else:
            st.info("No numeric measure detected in this ledger.")
with right:
    with st.container(border=True):
        if ds.schema["dims"] and metric:
            dim = st.selectbox("Group by", ds.schema["dims"])
            kind = st.segmented_control("Chart style", ["Bar", "Donut"], default="Bar")
            g = ds.clean_df.groupby(dim, dropna=False)[metric].sum().sort_values(ascending=False).head(10)
            if kind == "Donut":
                gd = g.rename_axis("label").reset_index(name="value")
                st.altair_chart(charts.donut(gd, "value", "label", f"Share by {dim}"))
            else:
                gd = g[::-1].rename_axis("label").reset_index(name="value")
                st.altair_chart(charts.bar_h(gd, "value", "label", f"Top 10 by {dim}"))
        else:
            st.info("No categorical dimension detected for a breakdown chart.")

st.subheader("Correlation explorer")
numeric_cols = list(ds.clean_df.select_dtypes(include=[np.number]).columns)
if len(numeric_cols) >= 2 and metric:
    c1, c2 = st.columns(2)
    with c1:
        x = st.selectbox("X axis", numeric_cols, index=numeric_cols.index(metric), key="sc_x")
    with c2:
        default_y = next((c for c in numeric_cols if c != x), x)
        y = st.selectbox("Y axis", numeric_cols, index=numeric_cols.index(default_y), key="sc_y")
    if x == y:
        st.info("Pick two different numeric columns to compare.")
    else:
        sample = ds.clean_df[[x, y]].dropna()
        if len(sample) > 5000:
            sample = sample.sample(5000, random_state=0)
        st.altair_chart(charts.scatter(sample, x, y, f"{y} vs {x}"))
        corr = sample[x].corr(sample[y]) if sample[x].std() and sample[y].std() else 0.0
        st.caption(f"Pearson correlation: {corr:+.2f} across {len(sample):,} rows.")
else:
    st.info("At least two numeric columns are required for the correlation explorer.")

var_df = intel.variance_table(monthly, date_col, metric) if monthly is not None else None
if var_df is not None:
    st.subheader("Month-over-month variance")
    st.caption("The close-pack variance schedule you would rebuild by hand in Excel — generated live from the ledger.")
    show = var_df.copy()
    show.columns = ["Month", "Total", "Change", "Change %", "Cumulative", "Share %"]
    st.dataframe(
        show,
        hide_index=True,
        column_config={
            "Total": st.column_config.NumberColumn(format="KES %,.0f"),
            "Change": st.column_config.NumberColumn(format="KES %,.0f"),
            "Change %": st.column_config.NumberColumn(format="%+.1f%%"),
            "Cumulative": st.column_config.NumberColumn(format="KES %,.0f"),
            "Share %": st.column_config.NumberColumn(format="%.1f%%"),
        },
    )
    st.download_button(
        "Download variance schedule (CSV)",
        data=show.to_csv(index=False).encode(),
        file_name="Westminister_Variance_Schedule.csv",
        mime="text/csv",
        icon=":material/download:",
    )

with st.expander("Cleaned ledger data", expanded=False):
    st.dataframe(ds.clean_df, hide_index=True)
