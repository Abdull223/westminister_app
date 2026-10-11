"""Shared dataset context used by every page.

All heavy work is cached, so calling `get_dataset()` on each rerun is cheap.
"""

from dataclasses import dataclass

import pandas as pd
import streamlit as st

from core import explain
from core import intelligence as intel
from core.cleaning import smart_clean
from core.data import fingerprint, load_dataset

DEFAULT_OPTS = {"impute": True, "drop_dupes": True, "trim_spaces": True, "cap_outliers": False, "split_merged": True}

# Below either threshold the certificate may only be issued in qualified form.
QUALITY_FLOOR = 90.0


@dataclass
class Dataset:
    name: str
    hash: str
    raw_df: pd.DataFrame
    clean_df: pd.DataFrame
    issue_log: pd.DataFrame
    change_log: pd.DataFrame
    stats: dict
    schema: dict
    quality: dict
    checks: list
    insights: list
    summary: str
    recommendations: list
    sheet: str | None = None

    @property
    def source(self) -> str:
        return f"{self.name} · worksheet “{self.sheet}”" if self.sheet else self.name

    @property
    def qualified(self) -> bool:
        """True when the ledger is too weak for an unqualified certificate."""
        failed = [name for name, ok, _ in self.checks if not ok]
        return self.quality["overall"] < QUALITY_FLOOR or bool(failed)

    @property
    def limitations(self) -> list[str]:
        out = []
        if self.quality["overall"] < QUALITY_FLOOR:
            out.append(f"Composite data quality of {self.quality['overall']:.1f}% is below the {QUALITY_FLOOR:.0f}% floor required for an unqualified opinion.")
        for name, ok, detail in self.checks:
            if not ok:
                out.append(f"Integrity check failed — {name}: {detail}")
        return out


@st.cache_data(ttl="1h", max_entries=4, show_spinner=False)
def analyse(raw_bytes: bytes, filename: str, opts: dict, sheet: str | None) -> dict:
    """Full analysis for one ledger + worksheet + cleaning profile, cached as a unit.

    Cached on the source bytes rather than the frames so a rerun pays a hash
    instead of recomputing ~4s of analytics per widget interaction.
    """
    raw_df = load_dataset(raw_bytes, filename, sheet)
    clean_df, issue_log, changes, stats = smart_clean(raw_df, **opts)
    schema = intel.detect_schema(clean_df)
    quality = intel.quality_report(raw_df, clean_df, stats)
    checks = intel.integrity_checks(clean_df, schema, stats)
    return {
        "raw_df": raw_df,
        "clean_df": clean_df,
        "issue_log": issue_log,
        "change_log": changes,
        "stats": stats,
        "schema": schema,
        "quality": quality,
        "checks": checks,
        "insights": intel.synth_insights(raw_df, clean_df, schema, stats, quality),
        "summary": intel.executive_summary(raw_df, clean_df, schema, stats, quality, checks),
        "recommendations": intel.recommendations(clean_df, schema, stats, quality, checks),
    }


def get_dataset() -> Dataset | None:
    raw_bytes = st.session_state.get("raw_bytes")
    if raw_bytes is None:
        return None
    name = st.session_state["source_name"]
    sheet = st.session_state.get("sheet")
    parts = analyse(raw_bytes, name, {**DEFAULT_OPTS, **st.session_state.get("clean_opts", {})}, sheet)
    if parts["raw_df"].empty:
        st.error(f"{'Worksheet “' + sheet + '”' if sheet else 'This file'} has no rows to analyse. Pick another worksheet or upload a different ledger.")
        st.stop()
    return Dataset(name=name, hash=fingerprint(raw_bytes), sheet=sheet, **parts)


def require_dataset() -> Dataset:
    ds = get_dataset()
    if ds is None:
        st.title("Westminister Intelligence Suite")
        st.markdown("Upload an Excel/CSV ledger in the sidebar, or start from **Load sample Kenya ledger** "
                    "(cash-flow and bank reconciliation) or **Load sample VAT & WHT ledger** (statutory tax "
                    "testing) to open the dashboards, the decision brief and the certified report.")
        c1, c2, c3 = st.columns(3)
        c1.markdown("**Background AI cleaning**")
        c1.caption("Missing fields, duplicates and outliers resolved automatically with a full audit trail.")
        c2.markdown("**Multi-dimensional dashboards**")
        c2.caption("Cash-flow trends, category breakdowns and distribution analytics over your ledger.")
        c3.markdown("**Certified PDF sign-off**")
        c3.caption("Capture the partner signature and issue an immutable, hash-stamped executive report.")
        explain.outputs()
        st.stop()
    return ds
