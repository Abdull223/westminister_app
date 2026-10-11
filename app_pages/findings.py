import io

import pandas as pd
import streamlit as st

from core.state import require_dataset

ds = require_dataset()

st.title("AI executive findings")
st.caption("Insights, narrative and quality scoring derived directly from the ledger — nothing is hard-coded.")

with st.container(horizontal=True):
    st.metric("Overall quality", f"{ds.quality['overall']:.1f}%", border=True)
    for name, score in ds.quality["components"].items():
        st.metric(name, f"{score:.1f}%", border=True)

st.subheader("Executive summary")
with st.container(border=True):
    report_md = (
        f"# Westminister Intelligence Audit — Executive Report\n\n"
        f"**Dataset:** {ds.name}  \n**SHA-256 fingerprint:** `{ds.hash}`  \n"
        f"**Records audited:** {len(ds.clean_df):,}\n\n---\n\n"
        + ds.summary
        + "\n\n## Recommendations\n\n"
        + "\n".join(f"- {r}" for r in ds.recommendations)
    )
    for para in ds.summary.split("\n\n"):
        st.write(para)
    buf = io.BytesIO(report_md.encode("utf-8"))
    st.download_button(
        "Download full report (Markdown)",
        data=buf,
        file_name="Westminister_Executive_Report.md",
        mime="text/markdown",
        icon=":material/download:",
    )

st.subheader("Integrity checks")
checks_df = pd.DataFrame(ds.checks, columns=["Check", "Passed", "Detail"])
st.dataframe(
    checks_df,
    hide_index=True,
    column_config={
        "Passed": st.column_config.CheckboxColumn("Passed", disabled=False),
        "Detail": st.column_config.TextColumn("Detail", width="large"),
    },
)

st.subheader("Synthesized findings")
for insight in ds.insights:
    st.markdown(f"- {insight}")

st.subheader("Recommendations")
for i, rec in enumerate(ds.recommendations, 1):
    st.markdown(f"{i}. {rec}")

with st.expander("AI cleaning & adjustment log", expanded=True):
    if ds.issue_log.empty:
        st.success("No automatic cleaning overrides were required for this dataset.")
    else:
        st.dataframe(ds.issue_log, hide_index=True)
        st.caption(f"{len(ds.issue_log)} adjustment action(s) applied across {ds.stats['rows_raw']:,} raw records.")

with st.expander("Raw vs cleaned comparison"):
    c1, c2 = st.columns(2)
    c1.metric("Raw rows", f"{ds.stats['rows_raw']:,}")
    c1.metric("Missing cells in raw", f"{ds.stats['missing_cells']:,}")
    c2.metric("Cleaned rows", f"{ds.stats['rows_clean']:,}")
    c2.metric("Cells imputed", f"{ds.stats['imputed_cells']:,}")
    st.dataframe(ds.raw_df, hide_index=True, height=240)
