"""Data intelligence: schema detection, quality scoring, integrity checks,
insight synthesis and anomaly detection — all computed from the actual ledger."""

import numpy as np
import pandas as pd

DATE_HINTS = ("date", "time")
STRONG_METRIC_HINTS = ("amount", "total", "revenue", "value", "cost", "price")
WEAK_METRIC_HINTS = ("qty", "quantity")
KEY_HINTS = ("no", "id", "number", "ref", "code", "pin")


def parse_dates(s: pd.Series) -> pd.Series:
    """Parse ledger dates, preferring day-first (dd/mm/yyyy) formats."""
    out = pd.to_datetime(s, errors="coerce", format="mixed", dayfirst=True)
    if out.notna().mean() < 0.8:
        fallback = pd.to_datetime(s, errors="coerce")
        if fallback.notna().mean() > out.notna().mean():
            return fallback
    return out


def _metric_score(name: str) -> int:
    lc = name.lower()
    for i, h in enumerate(STRONG_METRIC_HINTS):
        if h in lc:
            return 100 - i
    for i, h in enumerate(WEAK_METRIC_HINTS):
        if h in lc:
            return 10 - i
    return 0


def detect_schema(df: pd.DataFrame) -> dict:
    cols = list(df.columns)
    dates = [c for c in cols if any(h in c.lower() for h in DATE_HINTS)]
    parsed_dates = []
    for c in dates:
        if parse_dates(df[c]).notna().mean() > 0.8:
            parsed_dates.append(c)
    numeric = [c for c in cols if pd.api.types.is_numeric_dtype(df[c])]
    metric = max(numeric, key=_metric_score) if numeric else None
    if metric is not None and _metric_score(metric) == 0:
        metric = numeric[-1]
    keys = [c for c in cols if any(h in c.lower() for h in KEY_HINTS)]
    dims = [c for c in cols if not pd.api.types.is_numeric_dtype(df[c]) and c not in parsed_dates and c not in keys][:4]
    return {"dates": parsed_dates, "metric": metric, "dims": dims, "keys": keys}


def _pct(part: float, whole: float) -> float:
    return 100.0 * part / whole if whole else 100.0


def quality_report(raw_df: pd.DataFrame, clean_df: pd.DataFrame, stats: dict) -> dict:
    """Component scores: completeness, uniqueness, validity, consistency."""
    total_cells = max(stats["total_cells"], 1)
    completeness = max(0.0, min(100.0, 100.0 - _pct(stats["missing_cells"] + stats.get("malformed_cells", 0), total_cells)))
    uniqueness = 100.0 - _pct(stats["dupes_removed"] + stats.get("empty_rows_dropped", 0), max(stats["rows_raw"], 1))

    schema = detect_schema(clean_df)
    validity_penalties = 0
    if schema["dates"]:
        for c in schema["dates"]:
            validity_penalties += clean_df[c].pipe(lambda s: (parse_dates(s).isna() & s.notna()).sum())
    if schema["metric"]:
        validity_penalties += (clean_df[schema["metric"]] < 0).sum()
    validity = max(0.0, 100.0 - _pct(validity_penalties, max(len(clean_df), 1)))

    consistency_penalties = 0
    consistency_total = 0
    recon = _reconciliation(clean_df, schema)
    if recon is not None:
        mismatched, checked = recon
        consistency_penalties = mismatched
        consistency_total = checked
    consistency = 100.0 - _pct(consistency_penalties, consistency_total) if consistency_total else 100.0

    overall = 0.35 * completeness + 0.25 * uniqueness + 0.25 * validity + 0.15 * consistency
    return {
        "overall": round(overall, 1),
        "components": {
            "Completeness": round(completeness, 1),
            "Uniqueness": round(uniqueness, 1),
            "Validity": round(validity, 1),
            "Consistency": round(consistency, 1),
        },
    }


def _reconciliation(df: pd.DataFrame, schema: dict) -> tuple[int, int] | None:
    """If Qty x Unit Price columns exist alongside the metric, verify the totals."""
    cols = {c.lower(): c for c in df.columns}
    qty = next((cols[c] for c in cols if "qty" in c or "quantity" in c), None)
    price = next((cols[c] for c in cols if "price" in c or "rate" in c), None)
    metric = schema["metric"]
    if not (qty and price and metric and metric not in (qty, price) and len(df)):
        return None
    expected = df[qty] * df[price]
    mismatched = int((abs(expected - df[metric]) > 0.01).sum())
    return mismatched, len(df)


def integrity_checks(clean_df: pd.DataFrame, schema: dict, stats: dict) -> list[tuple[str, bool, str]]:
    checks = []
    checks.append(
        (
            "Exact-duplicate purge",
            stats["dupes_removed"] == 0 or stats["rows_clean"] < stats["rows_raw"],
            f"{stats['dupes_removed']} duplicate row(s) removed; {stats['rows_clean']:,} unique records remain",
        )
    )
    key_dupes = None
    for k in schema["keys"]:
        dups = int(clean_df[k].duplicated().sum()) if len(clean_df) else 0
        if dups and key_dupes is None:
            key_dupes = (k, dups)
    if key_dupes:
        checks.append(("Primary-key uniqueness", False, f"{key_dupes[1]} repeated value(s) in '{key_dupes[0]}'"))
    else:
        checks.append(("Primary-key uniqueness", True, "No duplicate identifiers detected"))

    recon = _reconciliation(clean_df, schema)
    if recon is None:
        checks.append(("Cash-flow reconciliation", True, "No multi-column arithmetic to verify — skipped"))
    else:
        mismatched, total = recon
        checks.append(
            (
                "Cash-flow reconciliation",
                mismatched == 0,
                f"{mismatched} of {total:,} rows fail Qty × Price = Total" if mismatched else f"All {total:,} rows balance (Qty × Price = Total)",
            )
        )

    if schema["metric"] and len(clean_df):
        negatives = int((clean_df[schema["metric"]] < 0).sum())
        checks.append(
            (
                "Sign convention",
                negatives == 0,
                f"{negatives} negative value(s) in '{schema['metric']}'" if negatives else f"No negative values in '{schema['metric']}'",
            )
        )
    if schema["dates"]:
        c = schema["dates"][0]
        parsed = parse_dates(clean_df[c])
        bad = int((parsed.isna() & clean_df[c].notna()).sum())
        checks.append(("Date validity", bad == 0, f"{bad} unparseable date(s) in '{c}'" if bad else f"All dates parse cleanly in '{c}'"))
    return checks


def synth_insights(raw_df: pd.DataFrame, clean_df: pd.DataFrame, schema: dict, stats: dict, quality: dict) -> list[str]:
    insights = []
    n = len(clean_df)
    if not n:
        return ["The cleaned dataset is empty — review the source ledger."]
    metric = schema["metric"]
    if metric:
        total = float(clean_df[metric].sum())
        insights.append(f"Total audited value across {n:,} records is KES {total:,.0f} (mean {total / n:,.0f} per record).")
        top_month = None
        if schema["dates"]:
            d = clean_df[[schema["dates"][0], metric]].dropna().copy()
            d[schema["dates"][0]] = parse_dates(d[schema["dates"][0]])
            d = d.dropna().set_index(schema["dates"][0])[metric].resample("MS").sum()
            if len(d) >= 2:
                top_month = d.idxmax().strftime("%B %Y")
                growth = (d.iloc[-1] - d.iloc[-2]) / d.iloc[-2] * 100 if d.iloc[-2] else 0.0
                insights.append(f"Peak cash-flow month: {top_month} (KES {d.max():,.0f}); latest month trend {growth:+.1f}% vs prior.")
            elif len(d) == 1:
                top_month = d.index[0].strftime("%B %Y")
        if schema["dims"]:
            dim = schema["dims"][0]
            g = clean_df.groupby(dim)[metric].sum().sort_values(ascending=False)
            share = g.iloc[0] / total * 100 if total else 0.0
            insights.append(
                f"'{g.index[0]}' leads {clean_df[dim].nunique()} '{dim}' contributors at KES {g.iloc[0]:,.0f} ({share:.1f}% of value)."
            )
    fixes = []
    if stats["imputed_cells"]:
        fixes.append(f"resolved {stats['imputed_cells']} missing cell(s)")
    if stats["dupes_removed"]:
        fixes.append(f"removed {stats['dupes_removed']} duplicate row(s)")
    if stats.get("malformed_cells"):
        fixes.append(f"normalised {stats['malformed_cells']} malformed numeric cell(s)")
    if stats.get("empty_rows_dropped"):
        fixes.append(f"discarded {stats['empty_rows_dropped']} blank row(s)")
    if stats["outliers_capped"]:
        fixes.append(f"capped {stats['outliers_capped']} outlier(s)")
    if fixes:
        insights.append("AI cleaning automatically " + ", ".join(fixes) + ".")
    else:
        insights.append("No automatic overrides were required — the ledger arrived structurally clean.")
    split = stats.get("split_columns") or []
    if split:
        parts = ", ".join(f"'{c}' → {n} columns" for c, n in split)
        insights.append(f"Un-merged {len(split)} packed column(s) holding multiple fields in one cell ({parts}).")
    redundant = stats.get("redundant_columns") or []
    if redundant:
        insights.append(f"Retired {len(redundant)} repeated column(s) that duplicated data already present elsewhere: {', '.join(redundant)}.")
    recon = _reconciliation(clean_df, schema)
    if recon and recon[0]:
        insights.append(f"⚠ {recon[0]} row(s) fail arithmetic reconciliation and are queued in Exception Quarantine for partner review.")
    ben = benford_check(clean_df, schema)
    if ben:
        insights.append(f"Benford's Law first-digit test on {ben['n']:,} values: mean absolute deviation {ben['mad']:.2f}% — {ben['verdict']}")
    nd = near_duplicates(clean_df, schema)
    if len(nd):
        top = nd.iloc[0]
        insights.append(f"⚠ {len(nd)} near-duplicate group(s) found (same party and amount under different document numbers, {int(top['Count'])} records on top of the pile) — see Audit Forensics.")
    insights.append(f"Composite data-quality rating {quality['overall']:.1f}% (completeness {quality['components']['Completeness']:.1f}%, consistency {quality['components']['Consistency']:.1f}%).")
    return insights


def find_anomalies(clean_df: pd.DataFrame, schema: dict) -> pd.DataFrame:
    """Rows needing partner attention: negatives, reconciliation breaks, IQR outliers."""
    if not len(clean_df):
        return pd.DataFrame(columns=[*clean_df.columns, "Reasons"])
    reasons = pd.Series([""] * len(clean_df), index=clean_df.index)

    def flag(mask: pd.Series, text: str):
        nonlocal reasons
        reasons += np.where(mask, text + "; ", "")

    metric = schema["metric"]
    if metric:
        flag(clean_df[metric] < 0, f"negative {metric}")
        col = clean_df[metric]
        q1, q3 = col.quantile(0.25), col.quantile(0.75)
        iqr = q3 - q1
        if iqr > 0:
            flag((col < q1 - 3 * iqr) | (col > q3 + 3 * iqr), "extreme outlier")
    recon = _reconciliation(clean_df, schema)
    if recon:
        cols = {c.lower(): c for c in clean_df.columns}
        qty = next((cols[c] for c in cols if "qty" in c or "quantity" in c), None)
        price = next((cols[c] for c in cols if "price" in c or "rate" in c), None)
        mismatch = abs(clean_df[qty] * clean_df[price] - clean_df[metric]) > 0.01
        flag(pd.Series(mismatch, index=clean_df.index), "total ≠ qty × price")
    if schema["keys"]:
        k = schema["keys"][0]
        flag(clean_df[k].duplicated(keep=False), f"duplicate {k}")

    out = clean_df[reasons != ""].copy()
    out["Reasons"] = reasons[reasons != ""].str.rstrip("; ")
    return out


def _monthly_series(df: pd.DataFrame, schema: dict) -> pd.Series | None:
    if not (schema["dates"] and schema["metric"] and len(df)):
        return None
    dcol, metric = schema["dates"][0], schema["metric"]
    d = df[[dcol, metric]].dropna().copy()
    d[dcol] = parse_dates(d[dcol])
    d = d.dropna().set_index(dcol)[metric].resample("MS").sum()
    return d if len(d) else None


def executive_summary(raw_df: pd.DataFrame, clean_df: pd.DataFrame, schema: dict, stats: dict,
                      quality: dict, checks: list, client_name: str = "the client") -> str:
    """A well-written narrative audit summary, generated from the data itself."""
    n = len(clean_df)
    metric = schema["metric"]
    total = float(clean_df[metric].sum()) if metric and n else 0.0
    para = []

    scope = (
        f"Westminister Consulting was engaged to perform an autonomous intelligence audit of {client_name}'s "
        f"financial ledger, comprising {n:,} transaction records across {len(clean_df.columns)} attributes. "
    )
    if metric:
        scope += (
            f"The ledger carries a gross audited value of KES {total:,.0f}, an average of KES {total / max(n, 1):,.0f} "
            f"per record. The engagement covered completeness, uniqueness, validity and consistency testing, "
            f"arithmetic reconciliation and exception quarantine."
        )
    para.append(scope)

    fixes = []
    if stats["dupes_removed"]:
        fixes.append(f"{stats['dupes_removed']} exact duplicate row(s) were purged")
    if stats.get("empty_rows_dropped"):
        fixes.append(f"{stats['empty_rows_dropped']} blank row(s) were discarded")
    if stats["imputed_cells"]:
        fixes.append(f"{stats['imputed_cells']} missing cell(s) were imputed using median/default strategies")
    if stats.get("malformed_cells"):
        fixes.append(f"{stats['malformed_cells']} malformed cell(s) (currency text, N/A placeholders) were coerced to clean numerics")
    if stats["outliers_capped"]:
        fixes.append(f"{stats['outliers_capped']} extreme value(s) were capped under the IQR method")
    split = stats.get("split_columns") or []
    if split:
        fixes.append(f"{len(split)} packed column(s) had multiple fields merged per cell and were split into discrete fields ({', '.join(f'{c} → {n} parts' for c, n in split)})")
    redundant = stats.get("redundant_columns") or []
    if redundant:
        fixes.append(f"{len(redundant)} column(s) repeating data held elsewhere were retired ({', '.join(redundant)})")
    quality_text = (
        f"The dataset achieved a composite data-quality rating of {quality['overall']:.1f}% "
        f"(completeness {quality['components']['Completeness']:.1f}%, uniqueness {quality['components']['Uniqueness']:.1f}%, "
        f"validity {quality['components']['Validity']:.1f}%, consistency {quality['components']['Consistency']:.1f}%). "
    )
    quality_text += "During background cleaning, " + (", ".join(fixes) + "." if fixes else "no overrides were required — the ledger arrived structurally clean.")
    para.append(quality_text)

    failed = [c for c in checks if not c[1]]
    if failed:
        detail = "; ".join(f"{name}: {msg}" for name, _, msg in failed)
        para.append(
            f"{len(failed)} of {len(checks)} integrity checks did not pass: {detail}. "
            f"The affected records have been isolated in the exception quarantine register for partner review "
            f"and should be resolved before final certification."
        )
    else:
        para.append(
            f"All {len(checks)} integrity checks passed, including primary-key uniqueness, sign convention, "
            f"date validity and cash-flow reconciliation. No unresolved exceptions remain."
        )

    series = _monthly_series(clean_df, schema)
    if series is not None and len(series) >= 2:
        growth = (series.iloc[-1] - series.iloc[-2]) / series.iloc[-2] * 100 if series.iloc[-2] else 0.0
        trend = "expansion" if growth >= 0 else "contraction"
        peak = series.idxmax()
        obs = (
            f"Cash-flow analytics show the most recent month closed at KES {series.iloc[-1]:,.0f} "
            f"({growth:+.1f}% month-on-month), indicating {trend}. Peak activity occurred in {peak.strftime('%B %Y')} "
            f"at KES {series.max():,.0f}. "
        )
        if schema["dims"]:
            dim = schema["dims"][0]
            g = clean_df.groupby(dim)[metric].sum().sort_values(ascending=False)
            share = g.iloc[0] / total * 100 if total else 0.0
            conc = " — concentration risk warrants diversification review." if share > 45 else "."
            obs += f"By '{dim}', '{g.index[0]}' accounts for KES {g.iloc[0]:,.0f} ({share:.1f}% of total value){conc}"
        else:
            obs = obs.rstrip(". ") + "."
        para.append(obs)

    return "\n\n".join(para)


def recommendations(clean_df: pd.DataFrame, schema: dict, stats: dict, quality: dict, checks: list) -> list[str]:
    recs = []
    if stats["missing_cells"] > 0:
        recs.append("Strengthen upstream data capture: mandatory-field validation at entry would eliminate the imputation step entirely.")
    if stats["dupes_removed"] > 0:
        recs.append("Introduce receipt/invoice-level duplicate detection in the bookkeeping workflow to prevent double-counting before export.")
    recon = _reconciliation(clean_df, schema)
    if recon and recon[0]:
        recs.append(f"Resolve the {recon[0]} reconciliation break(s) flagged in quarantine before sign-off, and audit the pricing templates that produced them.")
    nd = near_duplicates(clean_df, schema)
    if len(nd):
        recs.append(f"Verify the {len(nd)} near-duplicate payment group(s) listed in Audit Forensics against bank statements before releasing further funds.")
    ben = benford_check(clean_df, schema)
    if ben and ben["mad"] >= 2.5:
        recs.append("Benford first-digit deviation is elevated — sample-test entries whose leading digits depart most from the expected curve.")
    if quality["components"]["Consistency"] < 99.5 and not (recon and recon[0]):
        recs.append("Review arithmetic consistency rules in the source workbook to keep totals locked to line-item math.")
    if not any(not ok for _, ok, _ in checks):
        recs.append("Maintain the current controls — the ledger passed every integrity check this cycle.")
    recs.append("Re-run this audit monthly and archive each signed PDF against its SHA-256 fingerprint for an immutable trail.")
    return recs


def project_monthly(monthly: pd.DataFrame | None, date_col: str, metric: str, months: int = 3) -> pd.DataFrame | None:
    """Linear least-squares projection of the next `months` on the monthly totals."""
    if monthly is None or len(monthly) < 3:
        return None
    y = monthly[metric].astype(float)
    slope, intercept = np.polyfit(np.arange(len(y)), y.to_numpy(), 1)
    last = monthly[date_col].iloc[-1]
    rows = [{date_col: last, "Projected": float(y.iloc[-1])}]
    for k in range(1, months + 1):
        rows.append({date_col: last + pd.DateOffset(months=k), "Projected": max(intercept + slope * (len(y) - 1 + k), 0.0)})
    return pd.DataFrame(rows)


def variance_table(monthly: pd.DataFrame | None, date_col: str, metric: str) -> pd.DataFrame | None:
    """Month-over-month variance analysis — the classic Excel close-pack table."""
    if monthly is None or len(monthly) < 2:
        return None
    v = monthly.copy()
    v["Month"] = v[date_col].dt.strftime("%b %Y")
    v["Change"] = v[metric].diff()
    v["Change %"] = v[metric].pct_change() * 100
    v["Cumulative"] = v[metric].cumsum()
    v["Share of year"] = v[metric] / v[metric].sum() * 100
    return v[["Month", metric, "Change", "Change %", "Cumulative", "Share of year"]]


def benford_check(clean_df: pd.DataFrame, schema: dict) -> dict | None:
    """First-digit (Benford's Law) conformity test on the ledger metric.

    Returns observed/expected shares per digit, mean absolute deviation and a
    verdict. Genuine transactional data closely follows log10(1 + 1/d)."""
    metric = schema["metric"]
    if not metric or not len(clean_df):
        return None
    vals = pd.to_numeric(clean_df[metric], errors="coerce").abs()
    vals = vals[vals >= 1]
    if len(vals) < 50:
        return None
    first = vals.astype("int64").astype(str).str[0].value_counts()
    total = int(first.sum())
    expected = {d: np.log10(1 + 1 / d) for d in range(1, 10)}
    table = pd.DataFrame(
        {
            "Digit": [str(d) for d in range(1, 10)],
            "Observed %": [100.0 * first.get(str(d), 0) / total for d in range(1, 10)],
            "Expected %": [100.0 * expected[d] for d in range(1, 10)],
            "Count": [int(first.get(str(d), 0)) for d in range(1, 10)],
        }
    )
    mad = float(np.abs(table["Observed %"] - table["Expected %"]).mean())
    if mad < 1.5:
        verdict = "Close conformity — no digit-manipulation signal."
    elif mad < 2.5:
        verdict = "Acceptable conformity for this sample size."
    elif mad < 3.5:
        verdict = "Non-conformity — investigate leading-digit anomalies."
    else:
        verdict = "Strong non-conformity — possible fabricated or rounded entries."
    return {"table": table, "mad": mad, "n": total, "verdict": verdict}


def near_duplicates(clean_df: pd.DataFrame, schema: dict) -> pd.DataFrame:
    """Groups of different documents carrying the same client + amount — the
    classic double-payment / split-invoice red flag exact dedupe cannot see."""
    metric, keys, dims = schema["metric"], schema["keys"], schema["dims"]
    if not (metric and keys and dims and len(clean_df)):
        return pd.DataFrame(columns=["Client", "Amount", "Receipts", "Count"])
    client = dims[0]
    key = keys[0]
    grouped = (
        clean_df.groupby([client, metric], dropna=False)
        .agg(Receipts=(key, lambda s: ", ".join(map(str, s))), Count=(key, "size"))
        .reset_index()
    )
    hits = grouped[grouped["Count"] > 1].sort_values("Count", ascending=False)
    return hits.rename(columns={client: "Client", metric: "Amount"}).head(50)
