"""Westminister Intelligence Suite — entry point.

Run with: streamlit run streamlit_app.py
"""

import pathlib

import streamlit as st

from core import theme
from core.data import make_sample_csv

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


def _on_upload():
    uploaded = st.session_state.get("ledger_file")
    if uploaded is not None:
        st.session_state.raw_bytes = uploaded.getvalue()
        st.session_state.source_name = uploaded.name


def _clear_dataset():
    st.session_state.pop("raw_bytes", None)
    st.session_state.pop("source_name", None)
    st.session_state.pop("cert_pdf", None)


with st.sidebar:
    st.markdown("### Data ingestion")
    st.file_uploader("Excel / CSV ledger", type=["csv", "xlsx"], key="ledger_file", on_change=_on_upload)
    st.button("Load sample Kenya ledger", icon=":material/bolt:", width="stretch", on_click=_load_sample)
    if st.session_state.get("raw_bytes") is not None:
        st.caption(f"Active: {st.session_state['source_name']}")
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
