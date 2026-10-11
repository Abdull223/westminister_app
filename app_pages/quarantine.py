import streamlit as st

from core import intelligence as intel
from core.state import require_dataset

ds = require_dataset()

st.title("Exception quarantine")
st.caption("Rows flagged for negative values, arithmetic breaks, duplicate keys or extreme outliers. Mark rows compliant to exclude them from audit counts.")

anomalies = intel.find_anomalies(ds.clean_df, ds.schema)

override_key = f"qc_overrides_{ds.hash}"
overrides = st.session_state.setdefault(override_key, set())
open_items = anomalies[~anomalies.index.isin(overrides)]

with st.container(horizontal=True):
    st.metric("Flagged rows", f"{len(anomalies):,}", border=True)
    st.metric("Awaiting review", f"{len(open_items):,}", border=True)
    st.metric("Marked compliant", f"{len(overrides):,}", border=True)

if open_items.empty:
    st.success("Quarantine clear — no exceptions require partner review.")
    if not anomalies.empty:
        with st.expander("Previously overridden rows"):
            st.dataframe(anomalies[anomalies.index.isin(overrides)], hide_index=True)
    st.stop()

with st.form("qc_review", border=False):
    idx = st.selectbox(
        "Select an exception",
        list(open_items.index),
        format_func=lambda i: f"Row {i} — {open_items.loc[i, 'Reasons']}",
    )
    st.dataframe(open_items.loc[[idx]].drop(columns=["Reasons"]), hide_index=True, height=120)
    st.caption(f"Reason: {open_items.loc[idx, 'Reasons']}")
    submitted = st.form_submit_button("Mark compliant & release", icon=":material/shield:")
if submitted:
    overrides.add(idx)
    st.toast(f"Row {idx} marked compliant.", icon=":material/shield:")
    st.rerun()

with st.expander("All flagged rows", expanded=True):
    view = anomalies.copy()
    view["Status"] = ["Released" if i in overrides else "Quarantined" for i in view.index]
    st.dataframe(view, hide_index=True)
