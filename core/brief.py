"""The management decision brief: what a reader has to decide, what it is worth, and by when.

A findings memo tells a client what was wrong. This builds the page that tells them what to *do*:
one verdict, the handful of numbers a decision turns on, and an action schedule where every line
carries an amount, an owner and a date. Everything is derived from the snapshots the pages publish
(dashboard, reconciliation, tax) so the brief can never quote a figure the app did not compute.
"""

from __future__ import annotations

import datetime

import pandas as pd
import streamlit as st

from core import intelligence as intel

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

# What the money column on a decision actually means. Summing "stake" is a cash question;
# summing the others is not, so the brief never lets a reader mix them.
KINDS = {"stake": "Cash at stake", "review": "Value to verify", "depend": "Concentration risk"}


def open_exceptions(ds) -> int:
    """Flagged rows nobody has signed off yet — an unsigned conclusion on every one of them."""
    anomalies = intel.find_anomalies(ds.clean_df, ds.schema)
    overrides = st.session_state.get(f"qc_overrides_{ds.hash}", set())
    return int(len(anomalies[~anomalies.index.isin(overrides)]))


# ---------------------------------------------------------------- snapshot

def dash_snapshot(ds, monthly, date_col, metric, forecast) -> dict:
    """Publish the cash-flow reading the dashboard just computed, in plain data.

    The PDF and the brief rebuild from this rather than re-running the page, so what a partner
    signs is the same reading the screen showed them.
    """
    frame = ds.clean_df
    out: dict = {
        "ledger_hash": ds.hash,
        "source": ds.source,
        "rows": int(len(frame)),
        "metric": metric,
        "total": float(frame[metric].sum()) if metric else 0.0,
        "months": int(len(monthly)) if monthly is not None else 0,
        "span": (str(monthly[date_col].iloc[0].date()), str(monthly[date_col].iloc[-1].date()))
        if monthly is not None and len(monthly) else None,
        "series": [[str(d.date()), float(v)] for d, v in zip(monthly[date_col], monthly[metric], strict=True)]
        if monthly is not None else [],
        "last_month": None, "last_value": 0.0, "avg_month": 0.0, "peak": None, "trough": None,
        "projected": None, "trend_pct": None,
        "negatives": 0, "negatives_total": 0.0,
        "weekend_share": None, "month_end_share": None,
        "groups": [],
    }
    if metric is None or not len(frame):
        return out

    if monthly is not None and len(monthly):
        y = monthly[metric].astype(float)
        out["last_month"] = _month(monthly[date_col].iloc[-1])
        out["last_value"] = float(y.iloc[-1])
        out["avg_month"] = float(y.mean())
        hi, lo = int(y.idxmax()), int(y.idxmin())
        out["peak"] = [_month(monthly.loc[hi, date_col]), float(y.loc[hi])]
        out["trough"] = [_month(monthly.loc[lo, date_col]), float(y.loc[lo])]
        if len(y) >= 2 and y.iloc[-2]:
            out["trend_pct"] = float((y.iloc[-1] - y.iloc[-2]) / abs(y.iloc[-2]) * 100)
    if forecast is not None and len(forecast) > 1:
        out["projected"] = float(forecast["Projected"].iloc[1])

    values = pd.to_numeric(frame[metric], errors="coerce")
    neg = values.lt(0)
    out["negatives"] = int(neg.sum())
    out["negatives_total"] = float(values[neg].abs().sum())

    dated = None
    if date_col:
        d = pd.to_datetime(intel.parse_dates(frame[date_col]), errors="coerce")
        dated = d.notna()
        if dated.any():
            v = values[dated]
            dow = d[dated].dt.dayofweek
            out["weekend_share"] = float(v[dow >= 5].sum() / v.sum() * 100) if v.sum() else None
            dom = d[dated].dt.day
            out["month_end_share"] = float(v[dom >= 26].sum() / v.sum() * 100) if v.sum() else None

    # Concentration: the groups that carry the money, on the two dimensions that read as parties.
    total = float(values.sum())
    for dim in ds.schema["dims"][:2]:
        g = frame.groupby(dim, dropna=False)[metric].sum().sort_values(ascending=False)
        if not len(g):
            continue
        top = g.head(5)
        out["groups"].append({
            "dim": str(dim),
            "rows": int(len(g)),
            "top": [[str(k), float(v)] for k, v in top.items()],
            "top1_share": float(top.iloc[0] / total * 100) if total else 0.0,
            "top3_share": float(top.head(3).sum() / total * 100) if total else 0.0,
        })
    return out


def _month(ts) -> str:
    return pd.Timestamp(ts).strftime("%b %Y")


# ---------------------------------------------------------------- brief

def build(ds, dash: dict | None = None, recon: dict | None = None, tax: dict | None = None,
          open_items: int = 0, today: datetime.date | None = None) -> dict:
    """Assemble the decision brief from whatever evidence the suite currently holds."""
    today = today or datetime.date.today()
    dash = dash if dash and dash.get("ledger_hash") == ds.hash else None
    recon = recon if recon and recon.get("ledger_hash") == ds.hash else None
    tax = tax if tax and tax.get("ledger_hash") == ds.hash else None

    total = float(dash["total"]) if dash else 0.0
    actions: list[dict] = []

    if recon:
        s = recon["stats"]
        if s["duplicate_lines"]:
            actions.append(_action(
                "Recover duplicate payments", s["duplicate_total"],
                f"{s['duplicate_lines']:,} payment(s) appear twice on document or narration evidence.",
                "Finance Manager", today, 7, "stake"))
        if s["bank_only_lines"]:
            actions.append(_action(
                "Book or explain unrecorded bank items", s["bank_only_total"],
                f"{s['bank_only_lines']:,} movement(s) the bank shows and the ledger does not.",
                "Bookkeeper", today, 7, "stake"))
        if s["ledger_only_lines"]:
            actions.append(_action(
                "Chase receipts the ledger claims", s["ledger_only_total"],
                f"{s['ledger_only_lines']:,} booked item(s) with no matching bank movement.",
                "Credit Control", today, 14, "stake"))
        if not s["foots"]:
            actions.append(_action(
                "Close the reconciliation bridge", s["residual"],
                "The value bridge does not foot, so no unqualified certificate can issue.",
                "Engagement Partner", today, 3, "stake"))
    if tax:
        exposure = float(tax["exposure"]["total"])
        if exposure:
            actions.append(_action(
                "Provide for and disclose statutory exposure", exposure,
                f"{tax['vat']['exceptions']:,} VAT exception(s) and {tax['wht']['short_lines']:,} withholding "
                f"shortfall(s) on the schedule configured in the suite.",
                "Tax Lead", today, _days_to_next_filing(today), "stake"))
    if dash:
        if dash["negatives"]:
            actions.append(_action(
                "Review credit notes and negative postings", dash["negatives_total"],
                f"{dash['negatives']:,} line(s) carry a negative value in a ledger otherwise read as income.",
                "Finance Manager", today, 10, "review"))
        for grp in dash["groups"][:1]:
            if grp["top3_share"] >= 50 and len(grp["top"]) >= 3:
                actions.append(_action(
                    f"Reduce dependence on the top three {grp['dim']}",
                    sum(v for _, v in grp["top"][:3]),
                    f"{grp['top3_share']:.0f}% of ledger value sits with three of {grp['rows']:,} {grp['dim']}(s).",
                    "Managing Partner", today, 30, "depend"))
    if open_items:
        actions.append(_action(
            "Clear the exception queue before sign-off", 0.0,
            f"{open_items:,} flagged row(s) still have no named reviewer.",
            "Engagement Manager", today, 5, "review"))

    cash_total = sum(a["amount"] for a in actions if a["kind"] == "stake")
    other_total = sum(a["amount"] for a in actions if a["kind"] != "stake")
    headlines = _headlines(ds, dash, recon, tax)
    balance = f"{_count(len(actions), 'decision')} required, {balance_phrase(cash_total, actions)}."
    return {
        "verdict": _verdict(ds, dash, recon, tax, actions, cash_total),
        "headlines": headlines,
        "actions": actions,
        "cash_total": cash_total,
        "other_total": other_total,
        "balance_line": balance,
        "panel_line": f"{_count(len(actions), 'decision')} · "
                      + (f"KES {cash_total:,.0f} in the balance" if cash_total
                         else "no recoverable cash, checks and exposures only"),
        "watch": _watch(ds, dash, recon, tax, open_items),
        "prepared": today.isoformat(),
        "money": _money_label(dash, recon, tax),
    }


def _count(n: int, word: str) -> str:
    """'3 decisions', not '3 decision(s)' — a partner-facing report pluralises properly."""
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _money_label(dash, recon, tax) -> dict:
    """Where the money in the brief came from, stated once instead of per row."""
    return {
        "ledger": bool(dash),
        "reconciliation": bool(recon),
        "tax": bool(tax),
    }


def _action(decision: str, amount: float, why: str, owner: str, today: datetime.date, days: int,
          kind: str = "stake") -> dict:
    return {
        "decision": decision,
        "amount": float(amount or 0.0),
        "why": why,
        "owner": owner,
        "due": (today + datetime.timedelta(days=days)).isoformat(),
        "days": days,
        "kind": kind,
    }


def _days_to_next_filing(today: datetime.date) -> int:
    """Kenyan VAT returns are due by the 20th of the following month."""
    target = today.replace(day=20)
    if target <= today:
        target = (today.replace(day=28) + datetime.timedelta(days=5)).replace(day=20)
    return max((target - today).days, 1)


def _headlines(ds, dash, recon, tax) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    if dash:
        rows.append(("Ledger value", _fmt(dash["total"]), f"{dash['rows']:,} line(s) · {dash['span'][0] if dash['span'] else 'no dates'} to {dash['span'][1] if dash['span'] else ''}"))
        if dash["last_month"]:
            rows.append((f"Latest month ({dash['last_month']})", _fmt(dash["last_value"]),
                         ("{:+.1f}% vs prior month".format(dash["trend_pct"]) if dash["trend_pct"] is not None else "single month of data")))
        if dash["projected"] is not None:
            rows.append(("Next month projected", _fmt(dash["projected"]), "Straight-line fit over the months held"))
    rows.append(("Data quality", f"{ds.quality['overall']:.1f}%",
                 f"{sum(1 for _, ok, _ in ds.checks if ok)}/{len(ds.checks)} integrity checks passed"))
    if recon:
        s = recon["stats"]
        rows.append(("Bank lines tied", f"{s['match_rate']:.1f}%",
                     f"{s['matched_bank']:,} of {s['bank_lines']:,} · bridge " + ("foots" if s["foots"] else "does not foot")))
    if tax:
        rows.append(("Statutory exposure", _fmt(tax["exposure"]["total"]),
                     f"VAT basis {tax['vat']['basis']} · {tax['vat']['exceptions']:,} VAT / {tax['wht']['short_lines']:,} WHT exception(s)"))
    return rows


def _watch(ds, dash, recon, tax, open_items) -> list[tuple[str, str, str]]:
    """Not decisions — things that would become decisions if they move."""
    rows = [("Composite quality", f"{ds.quality['overall']:.1f}%",
             "clears the 90% certification floor" if ds.quality["overall"] >= 90 else "below the 90% floor — certificate is qualified")]
    if dash and dash["avg_month"]:
        low = dash["trough"][1] if dash["trough"] else 0.0
        rows.append(("Weakest month on record", _fmt(low),
                     f"{low / dash['avg_month'] * 100:.0f}% of the monthly average"))
    if dash and dash["weekend_share"] is not None:
        rows.append(("Value posted at weekends", f"{dash['weekend_share']:.1f}%",
                     "normal for retail and fuel" if dash["weekend_share"] < 15 else "unusually high for a business-hours ledger"))
    if recon:
        rows.append(("Unmatched bank items", f"{recon['stats']['exceptions']:,}",
                     "investigate before the next close"))
    if tax and tax["vat"]["basis"] != "declared":
        rows.append(("VAT basis", tax["vat"]["basis"], "no declared VAT column in the file — returns must be tied to iTax before relying on this"))
    if open_items:
        rows.append(("Exceptions awaiting review", f"{open_items:,}", "each one is an unsigned conclusion"))
    return rows


def balance_phrase(cash_total, actions) -> str:
    """What hangs on the decisions — never 'KES 0.00 in the balance'."""
    other = sum(a["amount"] for a in actions if a["kind"] != "stake")
    if cash_total:
        out = f"with {_fmt(cash_total)} genuinely in the balance"
    else:
        out = "none of them recoverable cash — they are checks and exposures, not receipts"
    if other:
        out += f", and a further {_fmt(other)} on verify and dependence lines that is value to confirm, not cash to recover"
    return out


def _verdict(ds, dash, recon, tax, actions, cash_total) -> str:
    parts = []
    if dash and dash["last_month"] and dash["trend_pct"] is not None:
        direction = "up" if dash["trend_pct"] >= 0 else "down"
        parts.append(f"Cash moved {direction} {abs(dash['trend_pct']):.1f}% in {dash['last_month']}")
    elif dash:
        parts.append(f"{dash['rows']:,} ledger line(s) worth {_fmt(dash['total'])} were re-performed")
    if actions:
        parts.append(f"{_count(len(actions), 'decision')} follow, {balance_phrase(cash_total, actions)}")
    else:
        parts.append("nothing in this ledger requires a decision this cycle")
    if ds.qualified:
        parts.append("the file does not yet support an unqualified certificate")
    elif recon and not recon["stats"]["foots"]:
        parts.append("the bank bridge does not foot, so the certificate is qualified")
    else:
        parts.append("the evidence supports an unqualified certificate")
    return "; ".join(parts) + "."


def render(b: dict) -> None:
    """Draw the brief on screen. The PDF prints the same dict, so screen and report cannot drift."""
    blocked = any("does not foot" in a["why"] for a in b["actions"])
    (st.error if blocked else st.success)(b["verdict"],
                                          icon=":material/assignment:" if blocked else ":material/task_alt:")

    with st.container(horizontal=True):
        for label, value, note in b["headlines"]:
            st.metric(label, value, help=note, border=True)

    st.markdown("**Decisions required**")
    if b["actions"]:
        st.dataframe(
            pd.DataFrame([
                {
                    "Decision": a["decision"],
                    "Amount": a["amount"],
                    "What the amount is": KINDS[a["kind"]],
                    "Why now": a["why"],
                    "Owner": a["owner"],
                    "Due": a["due"],
                }
                for a in b["actions"]
            ]),
            hide_index=True,
            width="stretch",
            column_config={
                "Amount": st.column_config.NumberColumn(format="KES %,.2f", width="medium"),
                "Why now": st.column_config.TextColumn(width="large"),
            },
        )
        st.caption(
            f"{b['balance_line']} Owners and horizons are this suite's convention, not a client instruction — "
            "reassign them before the pack goes out."
        )
    else:
        st.caption("No decision is triggered by this ledger: nothing unreconciled, no statutory exposure on the "
                   "configured schedule, and no unreviewed exceptions.")

    st.markdown("**Watch list**")
    st.caption("Not decisions yet — these become decisions if they move.")
    st.table(pd.DataFrame(b["watch"], columns=["Indicator", "Reading", "What it means"]))


def _fmt(value) -> str:
    v = float(value or 0.0)
    sign = "-" if v < 0 else ""
    a = abs(v)
    if a >= 1_000:
        return f"{sign}KES {a:,.0f}"
    return f"{sign}KES {a:,.2f}"
