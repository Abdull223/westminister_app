"""Westminister Intelligence Suite — entry point.

Run with: streamlit run streamlit_app.py
"""

import pathlib

import streamlit as st

from core import theme
from core.data import make_sample_csv, sheet_names

st.set_page_config(
    page_title="Westminister Intelligence Suite — Kenya",
    page_icon=":material/shield:",
    layout="wide",
)

_ASSET = pathlib.Path(__file__).parent / "assets" / "logo.png"
LOGO_BYTES = _ASSET.read_bytes() if _ASSET.exists() else None
st.session_state.setdefault("logo_bytes", LOGO_BYTES)

theme.inject_theme()
theme.show_splash(LOGO_BYTES)


def _load_sample():
    st.session_state.raw_bytes = make_sample_csv()
    st.session_state.source_name = "sample_kenya_ledger.csv"
    st.session_state.pop("sheet", None)


def _on_upload():
    uploaded = st.session_state.get("ledger_file")
    if uploaded is not None:
        st.session_state.raw_bytes = uploaded.getvalue()
        st.session_state.source_name = uploaded.name
        st.session_state.pop("sheet", None)


def _clear_dataset():
    for key in ("raw_bytes", "source_name", "cert_pdf", "sheet"):
        st.session_state.pop(key, None)


with st.sidebar:
    st.markdown("### Data ingestion")
    st.file_uploader("Excel / CSV ledger", type=["csv", "xlsx"], key="ledger_file", on_change=_on_upload)
    st.button("Load sample Kenya ledger", icon=":material/bolt:", width="stretch", on_click=_load_sample)
    raw = st.session_state.get("raw_bytes")
    if raw is not None:
        sheets = sheet_names(raw, st.session_state["source_name"])
        if len(sheets) > 1:
            if st.session_state.get("sheet") not in sheets:
                st.session_state.sheet = sheets[0]
            st.selectbox("Worksheet to audit", sheets, key="sheet")
            skipped = [s for s in sheets if s != st.session_state.sheet]
            st.warning(f"{len(skipped)} of {len(sheets)} worksheets are outside this audit: {', '.join(skipped[:5])}", icon=":material/folder_off:")
        active = st.session_state["source_name"] + (f" · {st.session_state['sheet']}" if st.session_state.get("sheet") else "")
        st.caption(f"Active: {active}")
        st.button("Clear dataset", icon=":material/delete:", width="stretch", on_click=_clear_dataset)

    st.divider()
    with st.form("cleaning_options"):
        st.markdown("### AI auto-cleaning")
        impute = st.checkbox("Auto-impute missing fields", value=True)
        drop_dupes = st.checkbox("Purge exact duplicates", value=True)
        trim_spaces = st.checkbox("Trim & collapse whitespace", value=True)
        split_merged = st.checkbox("Split merged columns (names, addresses)", value=True)
        cap_outliers = st.checkbox("Cap extreme numeric outliers", value=False)
        if st.form_submit_button("Apply cleaning", icon=":material/auto_fix_high:"):
            st.session_state.clean_opts = {
                "impute": impute,
                "drop_dupes": drop_dupes,
                "trim_spaces": trim_spaces,
                "split_merged": split_merged,
                "cap_outliers": cap_outliers,
            }

page = st.navigation(
    [
        st.Page("app_pages/dashboard.py", title="Dashboard", icon=":material/monitoring:"),
        st.Page("app_pages/pivot.py", title="Pivot & explore", icon=":material/pivot_table_chart:"),
        st.Page("app_pages/findings.py", title="AI findings", icon=":material/fact_check:"),
        st.Page("app_pages/forensics.py", title="Forensics", icon=":material/query_stats:"),
        st.Page("app_pages/quarantine.py", title="Quarantine", icon=":material/shield:"),
        st.Page("app_pages/signoff.py", title="Sign-off & PDF", icon=":material/draw:"),
    ],
    position="top",
)

theme.app_header(LOGO_BYTES, user="Westminister Senior Partner")
page.run()
