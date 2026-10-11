import datetime
import html

import streamlit as st

from core import charts
from core import intelligence as intel
from core.pdf_report import generate_audit_pdf
from core.signature_pad import signature_pad
from core.state import require_dataset

ds = require_dataset()

st.title("Partner sign-off & certified PDF")
st.caption("Draw the partner signature, then generate the immutable executive audit report.")


def _report_chart_pngs():
    metric = ds.schema["metric"]
    date_col = ds.schema["dates"][0] if ds.schema["dates"] else None
    trend_png = breakdown_png = None
    if metric and date_col is not None:
        d = ds.clean_df[[date_col, metric]].dropna().copy()
        d[date_col] = intel.parse_dates(d[date_col])
        d = d.dropna().set_index(date_col)[metric].resample("MS").sum().reset_index()
        if len(d) >= 2:
            forecast = intel.project_monthly(d, date_col, metric)
            if forecast is not None:
                chart = charts.forecast_trend(d, forecast, date_col, metric, "Projected", "Monthly cash flow · 3-month projection (KES)")
            else:
                chart = charts.area_trend(d, date_col, metric, "Monthly cash flow (KES)")
            trend_png = charts.chart_png(chart)
    if metric and ds.schema["dims"]:
        dim = ds.schema["dims"][0]
        g = ds.clean_df.groupby(dim, dropna=False)[metric].sum().sort_values(ascending=False).head(8)
        if len(g):
            gd = g[::-1].rename_axis("label").reset_index(name="value")
            breakdown_png = charts.chart_png(charts.bar_h(gd, "value", "label", f"Top contributors by {dim} (KES)"))
    return trend_png, breakdown_png


col_left, col_right = st.columns([1.2, 1])

with col_left:
    client_name = st.text_input("Client organization", value="Westminister Consulting Client")
    row = st.columns(2)
    approver_name = row[0].text_input("Signatory partner (types to appear in the report)", value="Abdullahi Abdi Hassan")
    partner_title = row[1].text_input("Partner title", value="Managing Partner")

    st.markdown("**Partner signature**")
    sig_png = signature_pad(key="partner_signature")
    if sig_png:
        st.image(sig_png, caption="Captured signature (embedded in the PDF)", width=220)
    else:
        st.caption("No signature captured yet — the PDF will be issued in 'signature pending' state.")

    if st.button("Generate certified PDF", type="primary", icon=":material/description:"):
        anomalies = intel.find_anomalies(ds.clean_df, ds.schema)
        with st.spinner("Rendering dashboard charts…"):
            trend_png, breakdown_png = _report_chart_pngs()
        st.session_state.cert_pdf = generate_audit_pdf(
            client_name=client_name,
            approver_name=approver_name,
            fingerprint=ds.hash,
            total_records=len(ds.clean_df),
            quality_score=ds.quality["overall"],
            quality_components=ds.quality["components"],
            checks=tuple(ds.checks),
            insights=tuple(ds.insights),
            summary=ds.summary,
            recommendations=tuple(ds.recommendations),
            anomalies=tuple(zip(anomalies.index.tolist(), anomalies["Reasons"].tolist(), strict=True)),
            issues_count=len(ds.issue_log),
            signature_png=sig_png,
            logo_png=st.session_state.get("logo_bytes"),
            timestamp=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"),
            trend_png=trend_png,
            breakdown_png=breakdown_png,
            partner_title=partner_title,
        )

    pdf = st.session_state.get("cert_pdf")
    if pdf:
        safe_name = "".join(c for c in client_name if c.isalnum() or c in " -_").strip().replace(" ", "_") or "Client"
        st.download_button(
            "Download certified audit PDF",
            data=pdf,
            file_name=f"Westminister_Audit_Report_{safe_name}.pdf",
            mime="application/pdf",
            icon=":material/download:",
        )

with col_right:
    checks_ok = sum(1 for _, ok, _ in ds.checks if ok)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
    st.markdown(
        f"""
        <div class="wc-panel" style="padding: 24px; border: 1px solid var(--wc-brass);">
            <h3 style="margin-top: 0;">Westminister Consulting</h3>
            <p style="color: var(--wc-muted); font-size: 0.85rem;">CERTIFICATE OF FINANCIAL AUDIT</p>
            <hr style="border-color: var(--wc-line);">
            <p><b>Client:</b> {html.escape(client_name)}</p>
            <p><b>Signatory:</b> {html.escape(approver_name)} · {html.escape(partner_title)}</p>
            <p><b>Timestamp:</b> {timestamp}</p>
            <p><b>Records processed:</b> {len(ds.clean_df):,}</p>
            <p><b>Data quality:</b> {ds.quality['overall']:.1f}% · {checks_ok}/{len(ds.checks)} integrity checks passed</p>
            <p><b>Cryptographic hash:</b></p>
            <div class="wc-hash">{html.escape(ds.hash)}</div>
            <hr style="border-color: var(--wc-line);">
            <p style="font-size: 0.82rem; color: #5FB38A;">Status: {'✅ CERTIFIED PDF READY FOR DOWNLOAD' if pdf else '⏳ Awaiting PDF generation'}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
