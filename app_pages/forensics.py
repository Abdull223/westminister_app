"""Forensic analytics beyond Excel: Benford's Law digit tests and near-duplicate payment detection."""

import streamlit as st

from core import charts
from core import intelligence as intel
from core.state import require_dataset

ds = require_dataset()

st.title("Audit forensics")
st.caption("Fraud-oriented tests that go beyond Excel — digit-frequency forensics and double-payment detection.")

ben = intel.benford_check(ds.clean_df, ds.schema)
near = intel.near_duplicates(ds.clean_df, ds.schema)

left, right = st.columns([1.3, 1])

with left:
    with st.container(border=True):
        st.subheader("Benford's Law first-digit test")
        if ben is None:
            st.info("At least 50 numeric ledger values are required for meaningful digit analysis. The current ledger is too small — results would be noise.")
        else:
            st.altair_chart(charts.benford_chart(ben["table"]))
            ok = ben["mad"] < 2.5
            st.metric("Mean absolute deviation", f"{ben['mad']:.2f}%", delta=f"{ben['n']:,} values tested", delta_color="off", border=True)
            (st.success if ok else st.warning)(f"Verdict: {ben['verdict']}")
            st.caption(
                "Genuine transactional data follows log10(1 + 1/d): digit 1 leads ~30.1% of the time, "
                "digit 9 only ~4.6%. Large deviations often indicate fabricated, altered or heavily rounded entries."
            )

with right:
    with st.container(border=True):
        st.subheader("Near-duplicate payments")
        st.caption("Different document numbers, same party and same amount — the classic double-payment and split-invoice red flag exact dedupe cannot see.")
        if not len(near):
            st.success("No near-duplicate client + amount combinations detected.")
        else:
            flagged = int(near["Count"].sum())
            st.metric("Suspicious groups", f"{len(near)}", delta=f"{flagged} records involved", delta_color="off", border=True)
            st.dataframe(
                near,
                hide_index=True,
                height=380,
                column_config={
                    "Amount": st.column_config.NumberColumn(format="KES %,.0f"),
                    "Count": st.column_config.NumberColumn("Same amount"),
                },
            )
            st.download_button(
                "Download near-duplicate register (CSV)",
                data=near.to_csv(index=False).encode(),
                file_name="Westminister_Near_Duplicates.csv",
                mime="text/csv",
                icon=":material/download:",
            )
