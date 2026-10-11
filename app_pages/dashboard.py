import numpy as np
import pandas as pd
import streamlit as st

from core import brief
from core import charts
from core import explain
from core import intelligence as intel
from core.state import require_dataset

ds = require_dataset()


def _day_label(ts) -> str:
    return pd.Timestamp(ts).strftime("%d %b %Y")

st.title("Cash-flow dashboard")
st.caption(f"{ds.source} · SHA-256 fingerprint `{ds.hash}`")
explain.page("dashboard")

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
projected = float(forecast["Projected"].iloc[1]) if forecast is not None else None

with st.container(horizontal=True):
    st.metric("Records analysed", f"{len(ds.clean_df):,}", border=True)
    st.metric("Data quality", f"{ds.quality['overall']:.1f}%", border=True)
    st.metric("Integrity checks", f"{checks_ok}/{len(ds.checks)} passed", border=True)
    if metric:
        st.metric(
            "Ledger value",
            explain.money(total_value),
            delta=delta,
            border=True,
            help=f"Exact total of “{metric}” across {len(ds.clean_df):,} records: KES {total_value:,.2f}",
            **({"chart_data": spark, "chart_type": "line"} if spark else {}),
        )
    if forecast is not None:
        last_actual = float(monthly[metric].iloc[-1])
        st.metric(
            "Projected next month",
            explain.money(projected),
            delta=f"{(projected - last_actual) / last_actual * 100:+.1f}% vs latest" if last_actual else None,
            border=True,
            help=f"Unrounded projection: KES {projected:,.2f}",
        )

explain.kpis(ds, monthly, metric, total_value, checks_ok, delta, forecast, projected)

# Published once per run: the decision brief and the certified PDF rebuild from this reading
# rather than recomputing it, so no reader can be shown a different figure than this page showed.
dash = brief.dash_snapshot(ds, monthly, date_col, metric, forecast)
st.session_state.dash_report = dash

with st.form("ledger_search", border=False):
    row = st.container(horizontal=True)
    query = row.text_input("Ask the ledger", placeholder="Search any value, e.g. Nairobi or INV-1002", label_visibility="collapsed")
    row.form_submit_button("Search", icon=":material/search:")
if query:
    text = ds.clean_df.astype(str)
    hit = ds.clean_df[(text.apply(lambda col: col.str.contains(query, case=False, na=False)).any(axis=1))]
    st.dataframe(hit, hide_index=True, height=240)
    st.caption(f"{len(hit):,} of {len(ds.clean_df):,} records match “{query}”.")
    explain.search(hit, len(ds.clean_df), query, metric)
else:
    explain.band([("What this is for",
                   "A whole-file text search, not a filter — it answers 'show me everything touching Nairobi or INV-1002' "
                   "without building a pivot. Matched rows keep their values but are not re-totalled, so use it to find "
                   "documents, not to prove a figure.")], "What this tells you")

st.subheader("Management dashboards")
st.caption(
    "The four readings a management pack is normally built from — liquidity, who the money sits with, "
    "when it moves, and how much of it is unusual — each computed from the same audited ledger."
)
tab_liq, tab_conc, tab_time, tab_risk = st.tabs([
    "Liquidity & cash-flow", "Income & concentration", "Timing & controls", "Value & risk",
])

with tab_liq:
    if monthly is not None and metric:
        with st.container(border=True):
            if forecast is not None:
                st.altair_chart(charts.forecast_trend(monthly, forecast, date_col, metric, "Projected",
                                                     "Monthly cash flow · 3-month projection"))
                st.caption("Dashed line: least-squares fit over the months held. It is a trend, not a budget.")
            else:
                st.altair_chart(charts.area_trend(monthly, date_col, metric, "Monthly cash flow"))
        with st.container(horizontal=True):
            st.metric("Monthly average", explain.money(dash["avg_month"]), border=True)
            if dash["peak"]:
                st.metric(f"Peak · {dash['peak'][0]}", explain.money(dash["peak"][1]), border=True)
            if dash["trough"]:
                st.metric(f"Weakest · {dash['trough'][0]}", explain.money(dash["trough"][1]), border=True)
            if dash["projected"] is not None:
                st.metric("Next month projected", explain.money(dash["projected"]), border=True)
        explain.dash_liquidity(dash)

        var_df = intel.variance_table(monthly, date_col, metric)
        if var_df is not None:
            st.markdown("**Month-over-month variance**")
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
            explain.variance(var_df)
            st.download_button(
                "Download variance schedule (CSV)",
                data=show.to_csv(index=False).encode(),
                file_name="Westminister_Variance_Schedule.csv",
                mime="text/csv",
                icon=":material/download:",
            )
    elif metric:
        st.info("No usable date column, so cash cannot be sequenced over time. The value distribution is on the "
                "Value & risk tab.")
    else:
        st.info("No numeric measure detected in this ledger.")

with tab_conc:
    if ds.schema["dims"] and metric:
        col_a, col_b = st.columns([1.35, 1])
        with col_a:
            with st.container(border=True):
                dim = st.selectbox("Group by", ds.schema["dims"], key="conc_dim")
                kind = st.segmented_control("Chart style", ["Bar", "Donut"], default="Bar", key="conc_kind")
                g = ds.clean_df.groupby(dim, dropna=False)[metric].sum().sort_values(ascending=False).head(10)
                if kind == "Donut":
                    gd = g.rename_axis("label").reset_index(name="value")
                    st.altair_chart(charts.donut(gd, "value", "label", f"Share by {dim}"))
                else:
                    gd = g[::-1].rename_axis("label").reset_index(name="value")
                    st.altair_chart(charts.bar_h(gd, "value", "label", f"Top 10 by {dim}"))
        with col_b:
            for grp in [x for x in dash["groups"] if x["dim"] == dim] or dash["groups"]:
                st.metric(f"Top 3 share of value", f"{grp['top3_share']:.1f}%",
                          delta=f"{grp['rows']:,} distinct {grp['dim']}(s)", delta_color="off", border=True)
                st.dataframe(
                    pd.DataFrame(grp["top"], columns=[grp["dim"], "Value"]).assign(
                        **{"% of ledger": lambda d: (d["Value"] / total_value * 100).round(1) if total_value else 0.0}),
                    hide_index=True,
                    column_config={"Value": st.column_config.NumberColumn(format="KES %,.0f")},
                )
        explain.dash_concentration(dash, dim, g, total_value)
    else:
        st.info("No categorical dimension detected for a breakdown chart.")

with tab_time:
    if metric and date_col:
        d = pd.DataFrame({"d": intel.parse_dates(ds.clean_df[date_col]),
                          "v": pd.to_numeric(ds.clean_df[metric], errors="coerce")}).dropna()
        if len(d):
            d["Month"] = d["d"].dt.strftime("%b %Y")
            d["Weekday"] = d["d"].dt.dayofweek.map(dict(enumerate(brief.WEEKDAYS)))
            hm = d.groupby(["Month", "Weekday"], as_index=False)["v"].sum().rename(columns={"v": "Value"})
            hm["Month"] = pd.Categorical(hm["Month"], categories=list(dict.fromkeys(d["Month"])), ordered=True)
            hm["Weekday"] = pd.Categorical(hm["Weekday"], categories=list(brief.WEEKDAYS), ordered=True)
            with st.container(border=True):
                st.altair_chart(charts.heatmap(hm, "Month", "Weekday", "Value", "When the money moves"))
            busiest = d.groupby("Weekday", as_index=False)["v"].sum().sort_values("v", ascending=False)
            day_end = d.assign(is_end=d["d"].dt.day >= 26).groupby("d")["v"].sum()
            with st.container(horizontal=True):
                st.metric("Weekend share of value", f"{dash['weekend_share']:.1f}%" if dash["weekend_share"] is not None else "—", border=True)
                st.metric("Posted in the last 6 days", f"{dash['month_end_share']:.1f}%" if dash["month_end_share"] is not None else "—", border=True)
                st.metric("Heaviest weekday", f"{busiest.iloc[0]['Weekday']}", delta=explain.money(busiest.iloc[0]["v"]),
                          delta_color="off", border=True)
                st.metric("Busiest single day", _day_label(day_end.idxmax()), delta=explain.money(day_end.max()), delta_color="off", border=True)
            explain.dash_timing(dash, busiest, len(d))
        else:
            st.info("No dates in this ledger parsed, so timing cannot be tested.")
    else:
        st.info("A date column and a measure are required for the timing dashboard.")

with tab_risk:
    if metric:
        anoms = intel.find_anomalies(ds.clean_df, ds.schema)
        with st.container(border=True):
            st.altair_chart(charts.histogram(ds.clean_df, metric, f"Distribution of {metric}"))
        numeric_cols = list(ds.clean_df.select_dtypes(include=[np.number]).columns)
        with st.container(horizontal=True):
            st.metric("Flagged for review", f"{len(anoms):,}", border=True)
            st.metric("Negative postings", f"{dash['negatives']:,}", delta=explain.money(dash["negatives_total"]),
                      delta_color="inverse" if dash["negatives"] else "off", border=True)
            st.metric("Ledger value tested", explain.money(total_value), border=True)
        if len(numeric_cols) >= 2:
            st.markdown("**Correlation explorer**")
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
                explain.correlation(x, y, corr, len(sample))
        explain.dash_value(dash, ds, len(anoms))
    else:
        st.info("No numeric measure detected in this ledger.")

with st.expander("Cleaned ledger data", expanded=False):
    st.dataframe(ds.clean_df, hide_index=True)
