import io

import numpy as np
import pandas as pd
import streamlit as st

from core import charts
from core.state import require_dataset

ds = require_dataset()

st.title("Pivot & explore")
st.caption("Slice the ledger Excel-style: pivot tables, an editable working grid and a per-column profiler.")

df = ds.clean_df
numeric_cols = list(df.select_dtypes(include=[np.number]).columns)
cat_cols = [c for c in df.columns if c not in numeric_cols]
AGGS = {"Sum": "sum", "Mean": "mean", "Count": "count", "Min": "min", "Max": "max", "Median": "median"}

tab_pivot, tab_edit, tab_profile = st.tabs(
    [":material/pivot_table_chart: Pivot table", ":material/grid_on: Edit data", ":material/query_stats: Column profiler"]
)

with tab_pivot:
    with st.container(border=True):
        with st.container(horizontal=True):
            rows = st.multiselect("Rows", df.columns.tolist(), default=[ds.schema["dims"][0]] if ds.schema["dims"] else [])
            cols = st.multiselect("Columns", df.columns.tolist(), max_selections=1)
            vals = st.multiselect("Values", numeric_cols, default=[ds.schema["metric"]] if ds.schema["metric"] else [])
            agg_label = st.selectbox("Aggregation", list(AGGS), index=0, label_visibility="visible")
            show_totals = st.toggle("Totals", value=True)
        with st.container(horizontal=True):
            filters = {}
            for fcol in st.multiselect("Filters", cat_cols, placeholder="Add a category filter"):
                options = sorted(df[fcol].dropna().astype(str).unique())
                chosen = st.multiselect(f"{fcol} =", options, default=options, key=f"pvf_{fcol}")
                filters[fcol] = chosen
    view = df.copy()
    for fcol, chosen in filters.items():
        view = view[view[fcol].astype(str).isin(chosen)]

    if rows and vals:
        agg = AGGS[agg_label]
        try:
            pv = pd.pivot_table(
                view,
                index=rows,
                columns=cols or None,
                values=vals,
                aggfunc=agg,
                margins=show_totals,
                margins_name="Grand Total",
            )
        except Exception as exc:
            st.error(f"Pivot failed: {exc}")
            pv = None
        if pv is not None:
            pv = pv.reset_index()
            st.dataframe(
                pv,
                hide_index=True,
                column_config={
                    c: st.column_config.NumberColumn(format="%.2f")
                    for c in pv.columns
                    if pd.api.types.is_numeric_dtype(pv[c])
                },
            )
            buf = io.BytesIO()
            pv.to_csv(buf, index=False)
            st.download_button(
                "Download pivot CSV",
                data=buf.getvalue(),
                file_name="pivot_table.csv",
                mime="text/csv",
                icon=":material/download:",
            )
            if cols and len(vals) == 1 and view[rows[0]].nunique() <= 40:
                flat = view.pivot_table(index=rows[0], columns=cols[0], values=vals[0], aggfunc=agg).reset_index()
                flat = flat.rename(columns={rows[0]: "row", cols[0]: "col", vals[0]: "value"})
                st.altair_chart(charts.heatmap(flat, "col", "row", "value", f"{agg_label} of {vals[0]}"))
    else:
        st.info("Pick at least one Row and one Value to build a pivot.")

with tab_edit:
    st.caption("Edits live in this browser session only — download to keep them, they do not alter the source file.")
    edited = st.data_editor(
        df,
        hide_index=True,
        height=520,
        key="wc_editor",
        column_config={
            c: st.column_config.NumberColumn(format="%.2f")
            for c in numeric_cols
        },
    )
    with st.container(horizontal=True):
        changed = int((edited.fillna("∅") != df.fillna("∅")).to_numpy().sum())
        st.metric("Edited cells", f"{changed:,}", border=True)
        st.metric("Rows", f"{len(edited):,}", border=True)
        buf = io.BytesIO()
        edited.to_csv(buf, index=False)
        st.download_button(
            "Download edited CSV",
            data=buf.getvalue(),
            file_name="ledger_edited.csv",
            mime="text/csv",
            icon=":material/download:",
            width="content",
        )

with tab_profile:
    col = st.selectbox("Column", df.columns.tolist(), index=0 if not ds.schema["metric"] else df.columns.tolist().index(ds.schema["metric"]))
    s = df[col]
    is_num = pd.api.types.is_numeric_dtype(s)
    with st.container(horizontal=True):
        st.metric("Type", "Numeric" if is_num else "Category", border=True)
        st.metric("Filled", f"{s.notna().mean() * 100:.1f}%", border=True)
        st.metric("Unique", f"{s.nunique():,}", border=True)
        if is_num:
            st.metric("Sum", f"{s.sum():,.0f}", border=True)
    with st.container(border=True):
        if is_num:
            desc = s.describe().to_frame("Value").reset_index(names="Statistic")
            st.dataframe(desc, hide_index=True, width="content")
            st.altair_chart(charts.histogram(s.to_frame(col), col, f"Distribution of {col}"))
        else:
            top = s.value_counts().head(12).rename_axis(col).reset_index(name="Records")
            st.altair_chart(charts.donut(top, "Records", col, f"Share by {col}"))
            st.dataframe(top, hide_index=True, width="content")
