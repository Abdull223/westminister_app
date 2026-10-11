"""Autonomous ledger cleaning with a full audit trail of every adjustment.

Handles: empty/bad rows, malformed numerics ("N/A" in an amount column),
merged columns (name + address in one cell), repeated columns (same data in
two columns), duplicates, missing values and outliers.
"""

import re

import numpy as np
import pandas as pd
import streamlit as st

ISSUE_COLS = ["Check / action", "Severity", "Target field", "Records affected", "Resolution method"]
CHANGE_COLS = ["Row", "Field", "Before", "After", "Action", "Severity"]

# A reviewer samples this register; cap it so a huge ledger stays renderable.
MAX_CHANGES = 20000

NUM_LIKE = re.compile(r"^\s*(KES|Ksh|Sh|USD|\$)?\s*-?[\d,]+(\.\d+)?\s*$")
DELIERS = [", ", "; ", " - ", " | ", ",", ";", "|"]


def _issue(action, severity, field, count, method):
    return (action, severity, field, int(count), method)


def _norm(s: pd.Series) -> pd.Series:
    return s.astype("string").fillna("(blank)")


def _diff(changes: list, before: pd.DataFrame, after: pd.DataFrame, action: str, severity: str) -> None:
    """Record every cell this step actually altered, keyed to the spreadsheet row."""
    idx = after.index
    src = before.loc[idx]
    for col in after.columns:
        if col not in src.columns or len(changes) >= MAX_CHANGES:
            continue
        old, new = _norm(src[col]), _norm(after[col])
        changed = old != new
        if not changed.any():
            continue
        # Reformatting the same number (450 -> 450.0) is not an adjustment.
        onum, nnum = pd.to_numeric(old, errors="coerce"), pd.to_numeric(new, errors="coerce")
        same = onum.notna() & nnum.notna() & np.isclose(onum.fillna(-1.0), nnum.fillna(-1.0), rtol=1e-12, atol=1e-9)
        for pos in np.flatnonzero((changed & ~same).to_numpy()):
            if len(changes) >= MAX_CHANGES:
                break
            changes.append((int(idx[pos]) + 2, str(col), old.iloc[pos], new.iloc[pos], action, severity))


def _row_events(changes: list, removed: pd.DataFrame, action: str, severity: str) -> None:
    for i, row in removed.iterrows():
        if len(changes) >= MAX_CHANGES:
            return
        preview = "; ".join(f"{c}={v}" for c, v in row.items() if pd.notna(v) and str(v).strip())
        changes.append((int(i) + 2, "(entire row)", preview[:160], "(removed)", action, severity))


def _split_merged(d: pd.DataFrame, issues: list, changes: list) -> list[tuple[str, int]]:
    """Split text columns where most values pack 2-3 fields behind a common delimiter."""
    split_info = []
    for col in list(d.select_dtypes(include=["object", "string"]).columns):
        s = d[col].dropna().astype(str)
        if len(s) < 5:
            continue
        for delim in DELIERS:
            parts = s.str.split(delim, regex=False)
            counts = parts.str.len()
            share = (counts >= 2).mean()
            if share < 0.75:
                continue
            n_parts = int(counts.mode().iloc[0])
            if n_parts < 2 or n_parts > 3:
                continue
            # consistency: at least 75% of splitting rows have exactly n_parts
            if (counts == n_parts).mean() < 0.75:
                continue
            # don't split if the parts are just one short token each (noise)
            avg_tokens = parts.explode().str.strip().str.len().mean()
            if avg_tokens < 2:
                continue
            new_cols = {}
            for i in range(n_parts):
                new_cols[f"{col} · part {i + 1}"] = d[col].astype("string").str.split(delim, n=n_parts - 1, regex=False).str[i].astype("string").str.strip()
            k = min(len(d), MAX_CHANGES - len(changes))
            if k > 0:
                extracted = pd.concat([s.iloc[:k] for s in new_cols.values()], axis=1).fillna("(blank)").astype("string")
                packed = d[col].iloc[:k].astype("string").fillna("(blank)")
                for pos in range(k):
                    changes.append((int(d.index[pos]) + 2, col, packed.iloc[pos], " ⟶ ".join(extracted.iloc[pos]), "Merged cell split", "Medium"))
            d.drop(columns=[col], inplace=True)
            for name, series in new_cols.items():
                d[name] = series
            issues.append(_issue("Merged column split", "Medium", col, len(d), f"Values packed {n_parts} fields per cell (delimiter '{delim.strip()}') — split into {n_parts} columns"))
            split_info.append((col, n_parts))
            break
    return split_info


def _coerce_numerics(d: pd.DataFrame, issues: list) -> int:
    """Convert numeric-looking text columns to real numbers; count values that failed."""
    coerced_total = 0
    for col in list(d.select_dtypes(include=["object", "string"]).columns):
        s = d[col].astype("string")
        non_null = s.notna()
        if not non_null.any():
            continue
        looks_numeric = s.str.strip().str.match(NUM_LIKE, na=False)
        if looks_numeric[non_null].mean() < 0.7:
            continue
        cleaned = s.str.replace(r"^(KES|Ksh|Sh|USD|\$)", "", regex=True).str.replace(",", "", regex=False)
        numeric = pd.to_numeric(cleaned, errors="coerce")
        bad = (numeric.isna() & non_null).sum()
        plain = s.str.match(r"^\s*-?\d+(\.\d+)?\s*$", na=False)
        normalised = int((looks_numeric & ~plain & non_null).sum())
        d[col] = numeric
        coerced_total += int(bad) + normalised
        if bad or normalised:
            issues.append(_issue("Malformed numeric normalised", "High", col, int(bad) + normalised, f"{normalised} currency/comma-formatted value(s) coerced to pure numerics; {int(bad)} unparseable entry(ies) blanked and queued for imputation"))
    return coerced_total


def _drop_redundant_columns(d: pd.DataFrame, issues: list) -> list[str]:
    """Remove later columns whose values repeat an earlier column almost exactly."""
    dropped = []
    cols = list(d.columns)
    str_view = {c: d[c].astype(str) for c in cols}
    for i, a in enumerate(cols):
        if a in dropped:
            continue
        for b in cols[i + 1:]:
            if b in dropped:
                continue
            match = (str_view[a] == str_view[b]).mean()
            if match >= 0.99:
                d.drop(columns=[b], inplace=True)
                dropped.append(b)
                issues.append(_issue("Repeated column removed", "Medium", b, len(d), f"'{b}' duplicated '{a}' in {match * 100:.0f}% of rows — redundant column dropped"))
            elif match >= 0.85:
                issues.append(_issue("Similar columns flagged", "Low", f"{a} / {b}", len(d), f"{match * 100:.0f}% identical values — review whether both are needed"))
    return dropped


@st.cache_data(ttl="1h", max_entries=16, show_spinner="Running AI cleaning…")
def smart_clean(
    raw_df: pd.DataFrame,
    impute: bool = True,
    drop_dupes: bool = True,
    trim_spaces: bool = True,
    cap_outliers: bool = False,
    split_merged: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    """Clean the ledger and return (clean_df, issue_log, change_log, stats).

    `change_log` records every individual adjustment — one row per edited cell
    or removed record — so a reviewer can re-perform the work instead of taking
    the aggregate counts on trust. Row numbers are spreadsheet rows (header = 1).
    """
    d = raw_df.copy()
    issues: list[tuple] = []
    changes: list[tuple] = []
    stats = {
        "rows_raw": len(d),
        "rows_clean": len(d),
        "missing_cells": int(raw_df.isna().sum().sum()),
        "total_cells": int(raw_df.size),
        "dupes_removed": 0,
        "imputed_cells": 0,
        "outliers_capped": 0,
        "empty_rows_dropped": 0,
        "malformed_cells": 0,
        "split_columns": [],
        "redundant_columns": [],
    }

    # 0. Drop fully-empty rows
    empty_mask = d.isna().all(axis=1) | (d.astype(str).apply(lambda c: c.str.strip()).eq("").all(axis=1))
    if empty_mask.any():
        stats["empty_rows_dropped"] = int(empty_mask.sum())
        _row_events(changes, d[empty_mask], "Empty row removed", "Medium")
        d = d[~empty_mask]

    # 1. Split merged columns (names/addresses packed together)
    if split_merged:
        stats["split_columns"] = _split_merged(d, issues, changes)

    # 2. Trim & collapse whitespace
    if trim_spaces:
        pre = d.copy()
        text_cols = list(d.select_dtypes(include=["object", "string"]).columns)
        for col in text_cols:
            d[col] = (
                d[col]
                .astype("string")
                .str.strip()
                .str.replace(r"\s+", " ", regex=True)
                .replace({"nan": pd.NA, "None": pd.NA, "": pd.NA})
            )
        if text_cols:
            issues.append(_issue("Whitespace normalisation", "Low", ", ".join(text_cols[:3]), len(d), "Trimmed and collapsed whitespace in text fields"))
        _diff(changes, pre, d, "Whitespace trimmed", "Low")

    # 3. Coerce malformed numerics (currency strings, "N/A" in number columns)
    pre = d.copy()
    stats["malformed_cells"] = _coerce_numerics(d, issues)
    _diff(changes, pre, d, "Numeric format normalised", "High")

    # 4. Repeated columns
    stats["redundant_columns"] = _drop_redundant_columns(d, issues)

    # 5. Duplicate purge
    if drop_dupes:
        pre = d
        d = d.drop_duplicates()
        stats["dupes_removed"] = len(pre) - len(d)
        if stats["dupes_removed"]:
            _row_events(changes, pre.loc[pre.index.difference(d.index)], "Duplicate row purged", "Medium")
            issues.append(_issue("Duplicate purge", "Medium", "Full row", stats["dupes_removed"], "Removed exact duplicate transactions"))

    # 6. Missing value imputation (covers original gaps + blanked malformed cells)
    if impute:
        pre = d.copy()
        for col in d.columns:
            missing = int(d[col].isna().sum())
            if not missing:
                continue
            if pd.api.types.is_numeric_dtype(d[col]):
                fill = d[col].median()
                if pd.isna(fill):
                    continue
                d[col] = d[col].fillna(fill)
                method = "Median imputation"
            else:
                d[col] = d[col].fillna("Not provided")
                method = "Default label"
            stats["imputed_cells"] += missing
            issues.append(_issue("Missing field auto-fill", "Low", col, missing, method))
        _diff(changes, pre, d, "Missing value imputed", "Low")

    # 7. Outlier capping
    if cap_outliers:
        pre = d.copy()
        for col in d.select_dtypes(include=[np.number]).columns:
            q1, q3 = d[col].quantile(0.25), d[col].quantile(0.75)
            iqr = q3 - q1
            if iqr <= 0:
                continue
            lo, hi = q1 - 3 * iqr, q3 + 3 * iqr
            flagged = (d[col] < lo) | (d[col] > hi)
            if flagged.any():
                if pd.api.types.is_integer_dtype(d[col].dtype):
                    d[col] = d[col].astype("Float64")
                d[col] = d[col].clip(lower=lo, upper=hi)
                stats["outliers_capped"] += int(flagged.sum())
                issues.append(_issue("Outlier capping", "Medium", col, flagged.sum(), f"Clipped values outside [{lo:,.0f}, {hi:,.0f}] (IQR method)"))
        _diff(changes, pre, d, "Outlier capped", "Medium")

    stats["rows_clean"] = len(d)
    stats["cell_changes"] = len(changes)
    stats["changes_truncated"] = len(changes) >= MAX_CHANGES
    log_df = pd.DataFrame(issues, columns=ISSUE_COLS)
    return d.reset_index(drop=True), log_df, pd.DataFrame(changes, columns=CHANGE_COLS), stats
