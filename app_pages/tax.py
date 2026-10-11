"""Tax health check: the statutory exceptions a KRA audit would find inside this ledger."""

import pandas as pd
import streamlit as st

from core import charts
from core import explain
from core import tax
from core.data import make_sample_tax_csv
from core.state import require_dataset

ds = require_dataset()

st.title("Tax health check")
st.caption(
    "VAT and withholding re-performed at the rate in force on each line's own date — the exceptions a KRA audit "
    "would find, found first."
)
explain.page("tax")

# Tested as recorded, not as cleaned: an exception table has to point at a row in the client's own file.
frame = ds.raw_df
if frame.empty:
    st.error("This worksheet has no rows to test.")
    st.stop()

col_names = list(frame.columns)
det = tax.detect_columns(frame)

if st.session_state.get("tax_cols_id") != "|".join(str(c) for c in col_names):
    for key in ("tc_date", "tc_net", "tc_gross", "tc_vat", "tc_wht", "tc_code", "tc_pin", "tc_doc", "tc_payee", "tc_sched"):
        st.session_state.pop(key, None)
    st.session_state.tax_cols_id = "|".join(str(c) for c in col_names)

if not any(det[k] for k in ("vat", "net", "gross")):
    with st.container(border=True):
        st.subheader("No amount columns recognised")
        st.markdown(
            f"The engine looked in `{', '.join(str(c) for c in col_names[:8]) or 'nothing'}` for a net, gross, VAT or "
            "withholding amount and found none it trusted. Name the columns yourself in the settings below — a badly "
            "labelled export should be corrected, never guessed at. To see the check working on a file that carries "
            "VAT, withholding, tax codes and PINs, load the demonstration ledger."
        )
        if st.button("Load sample VAT & WHT ledger", icon=":material/receipt_long:"):
            st.session_state.raw_bytes = make_sample_tax_csv()
            st.session_state.source_name = "sample_tax_ledger.csv"
            st.session_state.pop("sheet", None)
            st.rerun()
    st.stop()


def _pick(label, options, chosen, help=None, key=None):
    """Selectbox over a nullable slot, defaulting to the engine's own detection."""
    index = max(0, options.index(chosen)) if chosen in options else 0
    return st.selectbox(label, options, index=index, key=key, help=help)


with st.expander("Check settings — column mapping and rate schedule", expanded=not det["vat"]):
    st.warning(
        "The rates below are **your configuration, used as a working assumption**. They are not legal advice and are "
        "not kept current with the Finance Act: check the rate in force for the period you are working, edit it here, "
        "and cite the law yourself. Every figure on this page is only as correct as this table.",
        icon=":material/gavel:",
    )
    st.markdown(f"**Ledger under test:** {ds.source} · {len(frame):,} line(s) as uploaded · SHA-256 `{ds.hash[:16]}…`")
    st.caption(
        "The tests run against the file as it arrived, not the cleaned copy, so every row number below points at a "
        "real line in the client's spreadsheet."
    )
    plain = [None, *col_names]
    c1, c2, c3 = st.columns(3)
    with c1:
        date_col = _pick("Transaction date", col_names, det["date"], key="tc_date",
                         help="Each line is tested at the rate in force on this date.")
        vat_col = _pick("Declared VAT amount", plain, det["vat"], key="tc_vat",
                        help="Leave blank if the file carries no VAT column: the page then reports a derived figure and labels it derived.")
    with c2:
        net_col = _pick("Net of tax", col_names, det["net"], key="tc_net")
        wht_col = _pick("Withholding deducted", plain, det["wht"], key="tc_wht")
    with c3:
        gross_col = _pick("Gross / total", col_names, det["gross"], key="tc_gross")
        code_col = _pick("Tax code / supply type", plain, det["code"], key="tc_code",
                         help="Identifies zero-rated and exempt supplies so they are tested at 0% rather than the standard rate.")
    c4, c5, c6, c7 = st.columns(4)
    with c4:
        pin_col = _pick("Payee KRA PIN", plain, det["pin"], key="tc_pin")
    with c5:
        doc_col = _pick("Invoice / document number", plain, det["doc"], key="tc_doc")
    with c6:
        payee_col = _pick("Payee name", [None, *det["payee_candidates"]], det["payees"], key="tc_payee",
                          help="Used for supplier identity, withholding head matching and counterparty.")
    with c7:
        months = st.slider("Months outstanding", 1, 36, 6, key="tc_months",
                           help="Drives the interest line in the exposure summary only.")
    if not det["vat"]:
        st.info(
            "No VAT column was detected, so VAT is reported as a derived figure. If the VAT amounts live in another "
            "worksheet or file, load that as the ledger — a health check built on derived tax sizes the exposure, it "
            "does not prove one.",
            icon=":material/info:",
        )

    st.markdown("**Rate schedule** — edit, add or delete rows. `From` / `To` are `YYYY-MM-DD`; blank means open-ended.")
    base = tax.schedule_frame()
    for edge in ("From", "To"):
        base[edge] = base[edge].map(lambda v: "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)[:10])
    edited = st.data_editor(
        base,
        key="tc_sched",
        hide_index=True,
        num_rows="dynamic",
        width="stretch",
        column_config={
            "Tax": st.column_config.TextColumn("Tax", help="VAT, WHT, Penalty or Interest."),
            "Head": st.column_config.TextColumn("Head", help="The schedule head, e.g. Standard rated, Rent."),
            "Rate %": st.column_config.NumberColumn("Rate %", format="%.2f", min_value=0.0, step=0.5),
            "From": st.column_config.TextColumn("From", help="YYYY-MM-DD, or blank for open-ended."),
            "To": st.column_config.TextColumn("To", help="YYYY-MM-DD, or blank for open-ended."),
            "Note": st.column_config.TextColumn("Note", width="large"),
        },
    )
    if st.button("Restore default schedule", icon=":material/restore:"):
        st.session_state.pop("tc_sched", None)
        st.rerun()
    sched = tax.schedule_from_editor(edited)
    if sched.empty:
        st.error("The rate schedule has no usable rows, so nothing can be recomputed. Restore the default above.")
        st.stop()

res = tax.run(
    frame,
    {
        "date": date_col, "net": net_col, "gross": gross_col, "vat": vat_col, "wht": wht_col,
        "code": code_col, "pin": pin_col, "doc": doc_col, "payees": payee_col,
        "schedule": sched, "months": float(months),
    },
)
used = res["cols"]
vat, wht, pins, seq, control, exp = res["vat"], res["wht"], res["pins"], res["seq"], res["control"], res["exposure"]

# Snapshot for the certified report: plain values only, so the PDF rebuilds without the engine and the
# partner signs the numbers this page actually showed them.
st.session_state.tax_report = {
    "ledger": ds.source,
    "ledger_hash": ds.hash,
    "rows": res["rows"],
    "span": res["span"],
    "value_tested": float(pd.to_numeric(frame[used["gross"] or used["net"]], errors="coerce").sum(skipna=True)),
    "columns": {k: v for k, v in used.items() if k != "payee_candidates" and v},
    "rate_span": (res["rate_first"], res["rate_last"]),
    "unparsed_dates": int(res["unparsed_dates"]),
    "vat": {
        "basis": vat["basis"],
        "tested": int(vat["rows_tested"]),
        "exceptions": int(vat["exceptions"]),
        "under_declared": float(vat.get("under_declared", 0.0)),
        "over_declared": float(vat.get("over_declared", 0.0)),
        "vat_derived": float(vat.get("vat_derived", 0.0)),
        "top": tuple(
            (int(r["Source row"]), str(r["Date"]), str(r["Issue"])[:44], float(r["Net"]), float(r["Rate %"]), float(r["Difference"]))
            for _i, r in vat["table"].head(10).iterrows()
        ) if vat["exceptions"] else (),
    },
    "control": {
        "months": int(control["months"]),
        "net_total": float(control["net_total"]),
        "derived": bool(control["derived"]),
        "basis": control["basis"],
        "gap_months": tuple(control["gap_months"]),
        "profile": tuple(
            (str(m), float(o), float(i))
            for m, o, i in zip(control["table"]["Month"], control["table"]["Output"], control["table"]["Input"])
        ) if control["months"] else (),
    },
    "wht": {
        "basis": wht["basis"],
        "expense_lines": int(wht["expense_lines"]),
        "heads": int(wht["wht_heads"]),
        "short_lines": int(len(wht["table"])),
        "unwithheld": float(wht["unwithheld"]),
        "certificates": int(len(wht["register"])),
        "top": tuple(
            (int(r["Source row"]), str(r["Date"]), str(r["Payee"])[:26], str(r["Head"]), float(r["Base"]), float(r["Rate %"]), float(r["Short"]))
            for _i, r in wht["table"].head(10).iterrows()
        ) if len(wht["table"]) else (),
    },
    "pins": {
        "coverage": float(pins["coverage"]),
        "populated": int(pins["populated"]),
        "malformed": int(pins["malformed"]),
        "placeholders": int(pins["placeholders"]),
        "shared": int(pins["shared"]),
        "flagged": int(len(pins["table"])),
    },
    "sequence": {
        "groups": int(seq["groups"]),
        "gaps": int(seq["gaps"]),
        "repeats": int(seq["repeats"]),
        "inversions": int(seq["inversions"]),
        "read_by": seq["read_by"],
    },
    "exposure": {k: (float(v) if isinstance(v, (int, float)) else v) for k, v in exp.items() if k != "rates"},
    "rates": {k: float(v) for k, v in (exp.get("rates") or {}).items()},
    "schedule": tuple(
        (str(r["Tax"]), str(r["Head"]), float(r["Rate %"]), str(r["From"] or "—"), str(r["To"] or "—"))
        for _i, r in sched.iterrows()
    ),
    "findings": tuple(res["findings"]),
}

if vat["basis"] == "declared":
    vat_delta = (f"KES {vat['under_declared']:,.0f} short" if vat["under_declared"] else "nothing short")
elif vat["basis"] == "derived":
    vat_delta = "derived, not filed"
else:
    vat_delta = "no VAT column"

with st.container(horizontal=True):
    st.metric("Lines tested", f"{res['rows']:,}", delta=(f"{res['span'][0]} → {res['span'][1]}" if res["span"] else "no dates read"), delta_color="off", border=True)
    st.metric("VAT exceptions", f"{vat['exceptions']:,}" if vat["basis"] == "declared" else vat["basis"], delta=vat_delta, delta_color="inverse" if vat.get("under_declared") else "off", border=True)
    st.metric("Withholding shortfall", f"KES {wht['unwithheld']:,.0f}", delta=f"{len(wht['table']):,} of {wht['wht_heads']:,} service line(s)", delta_color="inverse" if wht["unwithheld"] else "off", border=True)
    st.metric("PIN exceptions", f"{len(pins['table']) + pins['shared']:,}", delta=f"{pins['coverage']}% of lines carry a PIN", delta_color="inverse" if len(pins["table"]) or pins["shared"] else "off", border=True)
    st.metric("Sequence breaks", f"{seq['gaps'] + seq['repeats'] + seq['inversions']:,}", delta=f"{seq['groups']} series read", delta_color="inverse" if seq["gaps"] or seq["repeats"] else "off", border=True)
    st.metric("Estimated exposure", f"KES {exp['total']:,.0f}", delta=f"tax + penalty + {exp['months']:g} mo interest", delta_color="inverse" if exp["total"] else "off", border=True)

if res["span"] and res["rate_first"] is not None and res["rate_last"] is not None and res["rate_first"] != res["rate_last"]:
    st.warning(
        f"The configured VAT rate changes inside this file's period ({res['rate_first']:.0f}% at {res['span'][0]} → "
        f"{res['rate_last']:.0f}% by {res['span'][1]}). Lines were tested on their own dates, so a book that applied "
        "one flat rate through the boundary shows a cluster of exceptions at the changeover.",
        icon=":material/calendar_month:",
    )

with st.container(border=True):
    st.subheader("What this run found")
    for finding in res["findings"]:
        st.markdown(f"- {finding}")
explain.tax_setup(res)

tab_vat, tab_control, tab_wht, tab_pins, tab_seq, tab_exp = st.tabs(
    [
        f"VAT re-perform ({vat['exceptions']:,})" if vat["basis"] == "declared" else "VAT (no declared column)",
        f"VAT control account ({control['months']} mo)",
        f"Withholding ({len(wht['table']):,})",
        f"Supplier PINs ({len(pins['table']) + pins['shared']:,})",
        f"Sequence ({seq['gaps'] + seq['repeats']:,})",
        "Exposure summary",
    ]
)

with tab_vat:
    if vat["basis"] == "none":
        st.info(vat["note"], icon=":material/info:")
    elif vat["basis"] == "derived":
        st.info(vat["note"], icon=":material/science:")
        derived = pd.DataFrame(
            {
                "Measure": [
                    f"Gross value read from “{used['gross'] or used['net']}”",
                    "Net of tax, derived at the schedule rate",
                    "Output VAT implied if every line were standard-rated",
                ],
                "KES": [vat["gross_inclusive"], vat["net_derived"], vat["vat_derived"]],
            }
        )
        st.dataframe(derived, hide_index=True, width="stretch", column_config={"KES": st.column_config.NumberColumn(format="KES %,.2f")})
    elif not vat["exceptions"]:
        st.success(f"All {vat['rows_tested']:,} lines carrying declared VAT recompute to the schedule on their own dates.", icon=":material/verified:")
    else:
        left, right = st.columns([1.15, 1])
        with left:
            st.dataframe(
                vat["table"],
                hide_index=True,
                height=460,
                column_config={
                    "Net": st.column_config.NumberColumn(format="KES %,.2f"),
                    "Rate %": st.column_config.NumberColumn(format="%.2f%%"),
                    "VAT declared": st.column_config.NumberColumn(format="KES %,.2f"),
                    "VAT expected": st.column_config.NumberColumn(format="KES %,.2f"),
                    "Difference": st.column_config.NumberColumn(
                        format="KES %,.2f", help="Positive = VAT short on this line; negative = VAT booked above what the rate supports."
                    ),
                },
            )
            st.caption(
                f"{vat['exceptions']:,} exception(s), largest value difference first. “Source row” is the row number "
                "in the uploaded file, header counted as row 1."
            )
        with right:
            mix = (
                vat["table"]
                .groupby("Issue", as_index=False)
                .agg(**{"Lines": ("Source row", "size"), "KES": ("Difference", lambda s: s.abs().sum())})
                .sort_values("KES", ascending=False)
            )
            st.altair_chart(charts.bar_h(mix, "KES", "Issue", "VAT value at risk by issue type"))
            st.download_button(
                "Download VAT exceptions (CSV)",
                data=vat["table"].to_csv(index=False).encode("utf-8"),
                file_name="Westminister_TAX_VAT_Exceptions.csv",
                mime="text/csv",
                icon=":material/download:",
            )
    explain.tax_vat(vat)

with tab_control:
    if not control["months"]:
        st.info(control["note"], icon=":material/info:")
    else:
        if control["derived"]:
            st.info(
                "Derived: this ledger has no VAT column, so each month's tax was backed out of the amounts at the "
                "configured rate. Read the shape of the profile, not the totals.",
                icon=":material/science:",
            )
        t = control["table"]
        long = t.melt(id_vars=["Month"], value_vars=["Output", "Input"], var_name="Side", value_name="KES")
        st.altair_chart(charts.grouped_bars(long, "Month", "KES", "Side", "Output and input VAT by return period", order=t["Month"].tolist()))
        st.dataframe(
            t,
            hide_index=True,
            width="stretch",
            column_config={
                "Output": st.column_config.NumberColumn(format="KES %,.2f"),
                "Input": st.column_config.NumberColumn(format="KES %,.2f"),
                "Net payable": st.column_config.NumberColumn(format="KES %,.2f", help="Output less input — the figure that must agree with the filed return."),
            },
        )
        st.caption(
            f"Net across the file: KES {control['net_total']:,.2f}. Separated using {control['basis']}. The filed "
            "return, not this ledger, is the authority — this schedule exists to show which period to go and check."
        )
        st.download_button(
            "Download VAT control account (CSV)",
            data=t.to_csv(index=False).encode("utf-8"),
            file_name="Westminister_TAX_VAT_Control.csv",
            mime="text/csv",
            icon=":material/download:",
        )
    explain.tax_control(control)

with tab_wht:
    if not wht["wht_heads"]:
        st.info(wht["note"], icon=":material/info:")
    else:
        st.markdown(
            f"{wht['wht_heads']:,} expense line(s) out of {wht['expense_lines']:,} carry a withholding service head. "
            + (
                f"Declared withholding in “{used['wht']}” was compared line by line."
                if wht["basis"] == "declared"
                else "This ledger carries no withholding column, so the figures below assume nobody withheld."
            )
        )
        if wht["table"].empty:
            st.success("No line falls short of the configured withholding schedule.", icon=":material/verified:")
        else:
            st.dataframe(
                wht["table"],
                hide_index=True,
                height=380,
                column_config={
                    "Base": st.column_config.NumberColumn(format="KES %,.2f"),
                    "Rate %": st.column_config.NumberColumn(format="%.2f%%"),
                    "WHT expected": st.column_config.NumberColumn(format="KES %,.2f"),
                    "WHT deducted": st.column_config.NumberColumn(format="KES %,.2f"),
                    "Short": st.column_config.NumberColumn(format="KES %,.2f", help="Positive = withholding short on this line; negative = more withheld than the head requires."),
                },
            )
            st.download_button(
                "Download withholding shortfalls (CSV)",
                data=wht["table"].to_csv(index=False).encode("utf-8"),
                file_name="Westminister_TAX_WHT_Shortfalls.csv",
                mime="text/csv",
                icon=":material/download:",
            )
        if len(wht["register"]):
            st.markdown("**Withholding certificate register**")
            st.caption(
                "One certificate per payee, per payment — and the remittance due date is the filing obligation "
                "whether or not the tax was ever deducted, so this doubles as the overdue-filing list."
            )
            st.dataframe(
                wht["register"],
                hide_index=True,
                height=320,
                column_config={
                    "Base": st.column_config.NumberColumn(format="KES %,.2f"),
                    "Rate %": st.column_config.NumberColumn(format="%.2f%%"),
                    "WHT expected": st.column_config.NumberColumn(format="KES %,.2f"),
                },
            )
            st.download_button(
                "Download certificate register (CSV)",
                data=wht["register"].to_csv(index=False).encode("utf-8"),
                file_name="Westminister_TAX_WHT_Certificates.csv",
                mime="text/csv",
                icon=":material/download:",
            )
    explain.tax_wht(wht)

with tab_pins:
    if not pins["populated"] and pins["table"].empty:
        st.info(pins["note"], icon=":material/info:")
    else:
        with st.container(horizontal=True):
            st.metric("Lines carrying a PIN", f"{pins['coverage']}%", delta=f"{pins['populated']:,} of {res['rows']:,}", delta_color="off", border=True)
            st.metric("Malformed", f"{pins['malformed']:,}", delta_color="inverse" if pins["malformed"] else "off", border=True)
            st.metric("Placeholders", f"{pins['placeholders']:,}", delta_color="inverse" if pins["placeholders"] else "off", border=True)
            st.metric("Shared across payees", f"{pins['shared']:,}", delta_color="inverse" if pins["shared"] else "off", border=True)
        st.caption(pins["note"])
        if len(pins["table"]):
            st.markdown("**PINs that fail the shape test**")
            st.dataframe(pins["table"], hide_index=True, height=280)
            st.download_button(
                "Download PIN exceptions (CSV)",
                data=pins["table"].to_csv(index=False).encode("utf-8"),
                file_name="Westminister_TAX_PIN_Exceptions.csv",
                mime="text/csv",
                icon=":material/download:",
            )
        if len(pins["shared_table"]):
            st.markdown("**One PIN, several payee names**")
            st.dataframe(pins["shared_table"], hide_index=True, width="stretch")
        if len(pins["pin_per_payee"]) and int(pins["pin_per_payee"]["Distinct PINs"].max()) > 1:
            st.markdown("**Payees appearing under several PINs**")
            st.dataframe(pins["pin_per_payee"], hide_index=True, width="stretch")
    explain.tax_pins(pins)

with tab_seq:
    if not seq["groups"]:
        st.info(seq["note"], icon=":material/info:")
    else:
        with st.container(horizontal=True):
            st.metric("Series read", seq["groups"], delta=seq["read_by"], delta_color="off", border=True)
            st.metric("Number gaps", seq["gaps"], delta=f"{seq['coverage']}% of lines numbered", delta_color="inverse" if seq["gaps"] else "off", border=True)
            st.metric("Repeated numbers", seq["repeats"], delta_color="inverse" if seq["repeats"] else "off", border=True)
            st.metric("Date inversions", seq["inversions"], delta_color="inverse" if seq["inversions"] else "off", border=True)
        st.caption(seq["note"])
        if len(seq["table"]):
            st.dataframe(seq["table"], hide_index=True, height=420, column_config={"Count": st.column_config.NumberColumn("Breaks")})
            st.download_button(
                "Download sequence exceptions (CSV)",
                data=seq["table"].to_csv(index=False).encode("utf-8"),
                file_name="Westminister_TAX_Sequence_Exceptions.csv",
                mime="text/csv",
                icon=":material/download:",
            )
        else:
            st.success("Every series runs unbroken and in date order.", icon=":material/verified:")
    explain.tax_sequence(seq)

with tab_exp:
    if not exp["total"]:
        st.info(
            "No under-declared VAT and no unwithheld tax were found on this basis, so there is nothing to provision "
            "against. Read the VAT and withholding tabs for what was estimated rather than tested.",
            icon=":material/task_alt:",
        )
    else:
        rates = exp.get("rates") or {}
        filing_pct = float(rates.get("filing_pct", 0.0))
        filing_min = float(rates.get("filing_min", 0.0) or 0.0)
        payment_pct = float(rates.get("payment_pct", 0.0))
        interest_pm = float(rates.get("interest_pm", 0.0))
        comp = pd.DataFrame(
            {
                "Component": [
                    "VAT under-declared (re-performed on this file)",
                    "Withholding not deducted",
                    f"Late-filing penalty at {filing_pct:g}%" + (f" (minimum KES {filing_min:,.0f})" if filing_min else ""),
                    f"Late-payment penalty at {payment_pct:g}%",
                    f"Interest at {interest_pm:g}% per month for {exp['months']:g} month(s)",
                ],
                "KES": [
                    vat.get("under_declared", 0.0),
                    wht["unwithheld"],
                    max(exp["tax"] * filing_pct / 100.0, filing_min),
                    exp["tax"] * payment_pct / 100.0,
                    exp["interest"],
                ],
            }
        )
        comp = comp[comp["KES"] > 0.005].reset_index(drop=True)
        st.dataframe(comp, hide_index=True, width="stretch", column_config={"KES": st.column_config.NumberColumn(format="KES %,.2f")})
        st.metric("Total exposure on these assumptions", f"KES {exp['total']:,.2f}", border=True)
        st.caption(
            "The two penalty lines are shown apart on purpose: the late-filing charge is the part a disclosure before "
            "assessment can still negotiate away, the interest is not."
        )
        st.download_button(
            "Download exposure summary (CSV)",
            data=pd.DataFrame(
                {"Component": [*comp["Component"], "TOTAL ON THESE ASSUMPTIONS"], "KES": [*comp["KES"].round(2), exp["total"]]}
            ).to_csv(index=False).encode("utf-8"),
            file_name="Westminister_TAX_Exposure.csv",
            mime="text/csv",
            icon=":material/download:",
        )
    explain.tax_exposure(exp, vat, wht)

st.divider()
st.subheader("Turn this into a deliverable")
rate_from = f"{res['rate_first']:.0f}%" if res["rate_first"] is not None else "unset"
rate_to = f"{res['rate_last']:.0f}%" if res["rate_last"] is not None else "unset"
st.markdown(
    "Each exception table above downloads as a CSV, which is the working paper. The schedule that was actually applied "
    f"is the one in the settings panel — **{len(sched)} rate row(s), VAT {rate_from} at the start of the period and "
    f"{rate_to} at the end** — and it is stored with "
    "the figures when the certified report is issued, so the PDF quotes the assumptions these numbers were built on. "
    "Capture the partner signature on the sign-off page to make the exception schedule part of the deliverable."
)
