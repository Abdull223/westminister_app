"""Bank-versus-ledger reconciliation: the tie-out that proves the books agree with the bank."""

import pandas as pd
import streamlit as st

from core import charts
from core import explain
from core import reconciliation as rec
from core.data import make_sample_statement_csv
from core.state import require_dataset

ds = require_dataset()

st.title("Bank reconciliation")
st.caption("Two-way tie-out of the audited ledger against a bank statement — every shilling paired, timed, bundled or proven absent.")
explain.page("reconcile")

stmt_bytes = st.session_state.get("stmt_bytes")
if stmt_bytes is None:
    with st.container(border=True):
        st.subheader("No bank statement loaded")
        st.markdown(
            "Upload the bank statement in the sidebar to reconcile it against **" + ds.source + "**. "
            "The suite reads the export as it arrives — it finds the date column, the money columns "
            "(a single signed amount, or separate withdrawal/deposit legs), and the description and reference text "
            "it will use to tie items together. Title rows above the header and running-balance columns are ignored automatically."
        )
        st.caption(
            "You can correct any column the suite guesses wrong on the reconciliation settings panel, so a badly "
            "labelled export never silently reconciles to the wrong figures."
        )
        if st.button("Load sample bank statement", icon=":material/account_balance:"):
            st.session_state.stmt_bytes = make_sample_statement_csv()
            st.session_state.stmt_name = "sample_bank_statement.csv"
            st.session_state.pop("stmt_sheet", None)
            st.rerun()
    st.stop()

stmt_name = st.session_state["stmt_name"]
stmt_sheet = st.session_state.get("stmt_sheet")
bank_df, detected, header_row = rec.load_statement(stmt_bytes, stmt_name, stmt_sheet)
if bank_df.empty or len(bank_df.columns) < 2:
    st.error("That file has no readable table. Export the statement as CSV or XLSX and upload it again.")
    st.stop()

cols = list(bank_df.columns)
text_default = [c for c in [detected.get("desc_col"), *detected.get("ref_cols", [])] if c in cols]

stmt_id = f"{stmt_name}:{len(stmt_bytes)}:{stmt_sheet}"
if st.session_state.get("recon_cols_id") != stmt_id:
    for key in ("oc_date", "oc_mode", "oc_in", "oc_out", "oc_amt", "oc_text"):
        st.session_state.pop(key, None)
    st.session_state.recon_cols_id = stmt_id

with st.expander("Reconciliation settings", expanded=not detected.get("ready", False)):
    st.markdown(f"**Statement:** `{stmt_name}`" + (f" · worksheet “{stmt_sheet}”" if stmt_sheet else ""))
    st.caption(f"SHA-256 `{rec.fingerprint(stmt_bytes)}` · header row detected at line {header_row + 1}")
    c1, c2 = st.columns(2)
    date_col = c1.selectbox(
        "Transaction date column",
        cols,
        index=max(0, cols.index(detected["date_col"])) if detected.get("date_col") in cols else 0,
        key="oc_date",
        help="The column holding the value or booking date of each movement.",
    )
    mode = c2.radio("Money layout", ["Separate withdrawal / deposit legs", "Single signed amount"], horizontal=True, key="oc_mode")
    if mode == "Separate withdrawal / deposit legs":
        money_cols = [c for c in cols if c != date_col]
        in_col = c1.selectbox(
            "Money-in (deposit / credit) column",
            money_cols,
            index=max(0, money_cols.index(detected["in_col"])) if detected.get("in_col") in money_cols else 0,
            key="oc_in",
        )
        out_col = c2.selectbox(
            "Money-out (withdrawal / debit) column",
            money_cols,
            index=max(0, money_cols.index(detected["out_col"])) if detected.get("out_col") in money_cols else 0,
            key="oc_out",
        )
        amt_col = None
    else:
        money_cols = [c for c in cols if c != date_col]
        amt_col = c1.selectbox(
            "Amount column (signed)",
            money_cols,
            index=max(0, money_cols.index(detected["amount_col"])) if detected.get("amount_col") in money_cols else 0,
            key="oc_amt",
        )
        in_col = out_col = None
    text_cols = st.multiselect(
        "Columns used to tie items by document or counterparty",
        [c for c in cols if c not in (date_col, in_col, out_col, amt_col)],
        default=text_default,
        key="oc_text",
        help="Description, narration and reference numbers. Matching on these catches a payment posted at the wrong value.",
    )
    st.divider()
    f1, f2, f3, f4, f5 = st.columns(5)
    exact_tol = f1.number_input("Exact amount tolerance", value=1.0, min_value=0.0, step=0.5, format="%.2f")
    var_pct = f2.number_input("Value variance allowed %", value=2.0, min_value=0.0, step=0.5, format="%.1f")
    window = f3.slider("Tie-up window (days)", 1, 30, 5)
    timing_window = f4.slider("Timing ceiling (days)", 7, 180, 45, step=5)
    bundle = f5.checkbox("Detect bundled settlements", value=True, help="Match one bank credit against several invoices, or one invoice paid in instalments.")

overrides = {
    "date_col": date_col,
    "amount_col": amt_col,
    "in_col": in_col,
    "out_col": out_col,
    "desc_col": text_cols[0] if text_cols else None,
    "ref_cols": text_cols[1:],
}
ready = date_col is not None and (amt_col is not None or in_col is not None or out_col is not None)
if not ready:
    st.error("Pick the date column and the money column(s) above — nothing can be reconciled until both are set.")
    st.stop()

res = rec.run(
    stmt_bytes,
    stmt_name,
    stmt_sheet,
    st.session_state["raw_bytes"],
    ds.name,
    st.session_state.get("clean_opts", {}),
    ds.sheet,
    float(exact_tol),
    float(var_pct),
    int(window),
    int(timing_window),
    bool(bundle),
    overrides,
)

s = res["stats"]
matched = res["matched"]
bank_only = res["bank_only"]
ledger_only = res["ledger_only"]
dupes = res["duplicates"]

money_layout = f"deposit/withdrawal “{in_col}” / “{out_col}”" if in_col else f"single signed amount “{amt_col}”"
used_cols = f"date “{date_col}” · {money_layout} · text “{', '.join(text_cols) or 'none'}”"

# Snapshot for the certified report: plain data only, so the PDF can be rebuilt without
# re-running the engine, and so the partner signs the numbers they actually looked at.
st.session_state.recon_report = {
    "statement": stmt_name + (f" · {stmt_sheet}" if stmt_sheet else ""),
    "statement_hash": res["stmt_hash"],
    "ledger_hash": ds.hash,
    "ledger_label": ds.source,
    "columns": used_cols,
    "stats": {k: v for k, v in s.items() if k != "bridge"},
    "bridge": [tuple(row) for row in res["bridge"]],
    "findings": tuple(res["findings"]),
    "monthly": tuple(
        (str(m["Month"]), float(m["Ledger value"]), float(m["Bank value"]), float(m["Value paired"]), float(m["Tie-up %"]))
        for _i, m in res["monthly"].tail(12).iterrows()
    ),
    "criteria": {
        "exact_tol": float(exact_tol),
        "var_pct": float(var_pct),
        "window": int(window),
        "timing_window": int(timing_window),
        "bundle": bool(bundle),
    },
    "exceptions": tuple(
        (
            f"Bank row {int(r['Bank row'])}",
            str(r["Date"]),
            str(r["Description"])[:52],
            float(r["Amount"]),
        )
        for _, r in bank_only.reindex(bank_only["Amount"].abs().sort_values(ascending=False).index).head(10).iterrows()
    ),
    "unreceipted": tuple(
        (
            f"Ledger row {int(r['Ledger row'])}",
            str(r["Date"]),
            str(r["Reference"])[:52],
            float(r["Amount"]),
        )
        for _, r in ledger_only.reindex(ledger_only["Amount"].abs().sort_values(ascending=False).index).head(10).iterrows()
    ),
}

with st.container(horizontal=True):
    st.metric("Bank lines tied", f"{s['matched_bank']:,} of {s['bank_lines']:,}", delta=f"{s['match_rate']:.1f}% tie-up", delta_color="off", border=True)
    st.metric("Ledger lines proved", f"{s['matched_ledger']:,} of {s['ledger_lines']:,}", delta=f"{s['ledger_only_lines']:,} unreceived", delta_color="off", border=True)
    st.metric("In bank, not in ledger", f"KES {s['bank_only_total']:,.0f}", delta=f"{s['bank_only_lines']:,} item(s)", delta_color="inverse", border=True)
    st.metric("In ledger, not in bank", f"KES {s['ledger_only_total']:,.0f}", delta=f"{s['ledger_only_lines']:,} item(s)", delta_color="inverse", border=True)
    st.metric("Duplicate payments", f"KES {s['duplicate_total']:,.0f}", delta=f"{s['duplicate_lines']:,} item(s)", delta_color="inverse", border=True)

if s["foots"]:
    st.success(
        f"Value bridge foots: KES {s['ledger_total']:,.0f} of ledger value is fully accounted for against "
        f"KES {s['bank_total']:,.0f} of bank movement. Unexplained difference KES {s['residual']:,.2f}.",
        icon=":material/verified:",
    )
else:
    st.error(
        f"Value bridge does NOT foot — KES {s['residual']:,.2f} is unaccounted for. Widen the tie-up window or correct "
        f"the detected columns; do not sign a reconciliation that does not balance.",
        icon=":material/report:",
    )

explain.bridge(s)

left, right = st.columns([1, 1.3])
with left:
    st.subheader("Reconciliation statement")
    bridge_df = pd.DataFrame(res["bridge"], columns=["Line", "KES"])
    st.dataframe(
        bridge_df,
        hide_index=True,
        width="stretch",
        column_config={"KES": st.column_config.NumberColumn(format="KES %,.2f")},
    )
    st.caption(
        "Every shilling of bank movement is placed in exactly one line above. The final total is the bank's own gross "
        "throughput, computed independently of the pairing — which is what makes the bridge a control rather than a plug."
    )
with right:
    st.subheader("Where the value sits")
    split = pd.DataFrame(
        {
            "Category": ["Paired with a ledger entry", "Ledger value never banked", "Bank movement never booked", "Duplicate bank items", "Value difference on pairs"],
            "Value": [
                max(s["paired_bank_total"], 0.0),
                max(s["ledger_only_total"], 0.0),
                max(s["bank_only_total"], 0.0),
                max(s["duplicate_total"], 0.0),
                abs(s["variance_total"]),
            ],
        }
    )
    split = split[split["Value"] > 0]
    if split.empty:
        st.info("Nothing to plot — no value was classified yet.")
    else:
        st.altair_chart(charts.donut(split, "Value", "Category", "Value by reconciliation outcome"))
    explain.split_donut(s)

st.subheader("Findings")
for finding in res["findings"]:
    st.markdown(f"- {finding}")

st.subheader("Month-by-month tie-out")
st.dataframe(
    res["monthly"],
    hide_index=True,
    width="stretch",
    column_config={
        "Ledger value": st.column_config.NumberColumn(format="KES %,.0f"),
        "Bank value": st.column_config.NumberColumn(format="KES %,.0f"),
        "Value paired": st.column_config.NumberColumn(format="KES %,.0f"),
        "Bank − ledger": st.column_config.NumberColumn(format="KES %,.0f"),
        "Tie-up %": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100),
    },
)
st.caption("A month that ties to 100% with a large bank-minus-ledger gap is a timing backlog, not an error — the gap moves to the next period.")
explain.monthly_tieout(res["monthly"])

tab_pairs, tab_bank, tab_ledger, tab_dupes = st.tabs(
    [f"Paired items ({len(matched):,})", f"In bank, not in ledger ({len(bank_only):,})", f"In ledger, not in bank ({len(ledger_only):,})", f"Duplicate payments ({len(dupes):,})"]
)

with tab_pairs:
    if matched.empty:
        st.info("No bank line could be paired with a ledger entry. Check the columns and tolerances above.")
    else:
        types = sorted(matched["Match type"].unique().tolist())
        chosen = st.multiselect("Match type", types, default=types, key="recon_match_type")
        shown = matched[matched["Match type"].isin(chosen)]
        st.dataframe(
            shown,
            hide_index=True,
            height=460,
            column_config={
                "Bank amount": st.column_config.NumberColumn(format="KES %,.2f"),
                "Ledger amount": st.column_config.NumberColumn(format="KES %,.2f"),
                "Value difference": st.column_config.NumberColumn(format="KES %,.2f"),
                "Confidence": st.column_config.ProgressColumn(format="%.0f", min_value=0, max_value=100),
            },
        )
        st.caption(
            f"{len(shown):,} of {len(matched):,} pair(s) shown. Rows are numbered against the original files "
            "(header = row 1), so an item can be pulled from the statement or the ledger without re-opening either."
        )
        st.download_button(
            "Download paired items (CSV)",
            data=matched.to_csv(index=False).encode("utf-8"),
            file_name="Westminister_Reconciliation_Paired.csv",
            mime="text/csv",
            icon=":material/download:",
        )

with tab_bank:
    if bank_only.empty:
        st.success("Every bank movement has a ledger entry. Nothing is unrecorded.")
    else:
        st.dataframe(
            bank_only,
            hide_index=True,
            height=420,
            column_config={"Amount": st.column_config.NumberColumn(format="KES %,.2f")},
        )
        st.download_button(
            "Download bank-only exceptions (CSV)",
            data=bank_only.to_csv(index=False).encode("utf-8"),
            file_name="Westminister_Bank_Not_In_Ledger.csv",
            mime="text/csv",
            icon=":material/download:",
        )

with tab_ledger:
    if ledger_only.empty:
        st.success("Every ledger entry has reached the bank. Nothing is unreceipted.")
    else:
        st.dataframe(
            ledger_only,
            hide_index=True,
            height=420,
            column_config={"Amount": st.column_config.NumberColumn(format="KES %,.2f")},
        )
        st.download_button(
            "Download ledger-only exceptions (CSV)",
            data=ledger_only.to_csv(index=False).encode("utf-8"),
            file_name="Westminister_Ledger_Not_In_Bank.csv",
            mime="text/csv",
            icon=":material/download:",
        )

with tab_dupes:
    if dupes.empty:
        st.success("No bank item repeats a value and counterparty already settled against the ledger.")
    else:
        st.warning(
            f"{len(dupes)} bank item(s) totalling KES {dupes['Bank amount'].abs().sum():,.0f} repeat a payment already "
            "settled against a ledger line. Recover the funds or reverse the posting before certification.",
            icon=":material/policy:",
        )
        st.dataframe(
            dupes,
            hide_index=True,
            height=420,
            column_config={
                "Bank amount": st.column_config.NumberColumn(format="KES %,.2f"),
                "Ledger amount": st.column_config.NumberColumn(format="KES %,.2f"),
            },
        )

explain.exceptions(bank_only, ledger_only, dupes)
