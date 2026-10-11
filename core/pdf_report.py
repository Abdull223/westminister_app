"""Certified executive audit report generation (ReportLab)."""

import datetime
import html
import io
import itertools
import struct

import streamlit as st

# Helvetica carries no glyph for these, so they are given words instead of boxes.
_PDF_GLYPHS = {"⚠": "WARNING — ", "✓": "pass", "✗": "fail"}


def _esc(s) -> str:
    text = str(s)
    for glyph, word in _PDF_GLYPHS.items():
        text = text.replace(glyph, word)
    return html.escape(text.encode("cp1252", "replace").decode("cp1252"))


def _png_size(png: bytes) -> tuple[int, int]:
    """Read width/height from a PNG IHDR chunk without needing PIL."""
    if len(png) >= 24 and png[:8] == b"\x89PNG\r\n\x1a\n":
        w, h = struct.unpack(">II", png[16:24])
        return int(w), int(h)
    return 620, 300


@st.cache_data(ttl="1h", max_entries=16, show_spinner="Rendering certified report…")
def generate_audit_pdf(
    client_name: str,
    approver_name: str,
    fingerprint: str,
    total_records: int,
    quality_score: float,
    quality_components: dict,
    checks: tuple,
    insights: tuple,
    summary: str,
    recommendations: tuple,
    anomalies: tuple,
    issues_count: int,
    signature_png: bytes | None,
    logo_png: bytes | None,
    timestamp: str,
    trend_png: bytes | None = None,
    breakdown_png: bytes | None = None,
    partner_title: str = "Senior Partner",
    source_label: str = "",
    qualified: bool = False,
    limitations: tuple = (),
    changes: tuple = (),
    changes_truncated: bool = False,
    recon: dict | None = None,
) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import HRFlowable, Image as RLImage
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=42, leftMargin=42, topMargin=40, bottomMargin=40)
    story = []

    styles = getSampleStyleSheet()
    ink = colors.HexColor("#061625")
    brass = colors.HexColor("#C9A24F")
    muted = colors.HexColor("#5A6E85")
    body_color = colors.HexColor("#1A2B3C")
    bg_card = colors.HexColor("#F8FAFC")
    border_line = colors.HexColor("#CBD5E1")
    pass_green = colors.HexColor("#1E7A46")
    fail_red = colors.HexColor("#B3382C")

    title_style = ParagraphStyle("DocTitle", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=21, textColor=ink, spaceAfter=2)
    sub_style = ParagraphStyle("DocSub", parent=styles["Normal"], fontName="Helvetica", fontSize=10, textColor=muted, spaceAfter=12)
    h2_style = ParagraphStyle("SectionHeading", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=13, textColor=ink, spaceBefore=12, spaceAfter=6)
    h3_style = ParagraphStyle("SubHeading", parent=styles["Heading3"], fontName="Helvetica-Bold", fontSize=11, textColor=colors.HexColor("#0C2238"), spaceBefore=8, spaceAfter=4)
    body_style = ParagraphStyle("Body", parent=styles["Normal"], fontName="Helvetica", fontSize=9.5, textColor=body_color, leading=14, spaceAfter=6, alignment=TA_LEFT)
    _section = itertools.count(1)

    def h2(title: str) -> Paragraph:
        """Numbered section heading — keeps numbering correct when sections are conditional."""
        return Paragraph(f"{next(_section)}. {title}", h2_style)

    def card_table(rows, col_widths):
        t = Table(rows, colWidths=col_widths)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), bg_card),
            ("PADDING", (0, 0), (-1, -1), 7),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOX", (0, 0), (-1, -1), 1, brass),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, border_line),
        ]))
        return t

    # ---- Cover header ----
    if logo_png:
        try:
            story.append(RLImage(io.BytesIO(logo_png), width=140, height=45))
            story.append(Spacer(1, 8))
        except Exception:
            pass
    story.append(Paragraph("WESTMINISTER CONSULTING KENYA", title_style))
    story.append(Paragraph(
        f"Autonomous Financial Ledger &amp; Cash Flow Audit — {'Qualified Report' if qualified else 'Certified Report'}",
        sub_style,
    ))
    story.append(HRFlowable(width="100%", thickness=2, color=brass, spaceAfter=12))
    if qualified:
        banner = Table(
            [[Paragraph(
                "<b>QUALIFIED REPORT.</b> This ledger failed one or more acceptance gates, so the report is issued with the "
                "scope limitations listed in the next section. It must not be relied upon as an unqualified certification.",
                body_style)]],
            colWidths=[540],
        )
        banner.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FDF0EE")),
            ("BOX", (0, 0), (-1, -1), 1, fail_red),
            ("PADDING", (0, 0), (-1, -1), 9),
        ]))
        story.append(banner)
        story.append(Spacer(1, 10))

    meta_rows = [
        ("Client organization", _esc(client_name)),
    ]
    if source_label:
        meta_rows.append(("Source audited", _esc(source_label)))
    if recon:
        meta_rows.append(("Bank statement tied", _esc(recon["statement"])))
    meta_rows += [
        ("Signatory partner", _esc(approver_name)),
        ("Audit timestamp", _esc(timestamp)),
        ("Records audited", f"{total_records:,} ledger rows"),
        ("Composite data quality", f"<b>{quality_score:.1f}%</b>"),
        ("Cleaning adjustments", f"{issues_count} logged action(s)"),
        ("SHA-256 fingerprint", f"<font name='Courier'><b>{_esc(fingerprint)}</b></font>"),
    ]
    story.append(card_table(
        [[Paragraph(f"<b>{k}:</b>", body_style), Paragraph(v, body_style)] for k, v in meta_rows],
        [160, 380],
    ))
    story.append(Spacer(1, 12))

    # ---- Scope limitations (qualified reports only) ----
    if qualified:
        story.append(h2("Scope limitations"))
        for limitation in limitations:
            story.append(Paragraph(f"• {_esc(limitation)}", body_style))
        story.append(Paragraph(
            "These matters fall below the acceptance floor the suite applies before certification. The report is issued "
            "in qualified form on the explicit acknowledgement of the signatory partner and does not constitute an "
            "unqualified assurance over the ledger.",
            body_style,
        ))
        story.append(Spacer(1, 6))

    # ---- Executive summary (narrative) ----
    story.append(h2("Executive summary"))
    for para in summary.split("\n\n"):
        story.append(Paragraph(_esc(para), body_style))

    # ---- 2. Data quality profile with bars ----
    story.append(h2("Data quality profile"))
    from reportlab.graphics.shapes import Drawing, Rect, String

    bar_rows = []
    for name, score in quality_components.items():
        d = Drawing(400, 16)
        d.add(String(0, 4, name, fontName="Helvetica", fontSize=8.5, fillColor=body_color))
        d.add(Rect(120, 6, 240, 6, fillColor=colors.HexColor("#E2E8F0"), strokeColor=None))
        d.add(Rect(120, 6, 240 * score / 100.0, 6, fillColor=brass if score >= 95 else (colors.HexColor("#E0A84A") if score >= 85 else fail_red), strokeColor=None))
        d.add(String(370, 4, f"{score:.1f}%", fontName="Helvetica-Bold", fontSize=8.5, fillColor=ink))
        bar_rows.append([d])
    bar_rows.insert(0, [_overall_drawing(quality_score)])
    story.append(Table(bar_rows, colWidths=[400], style=TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ])))
    story.append(Spacer(1, 10))

    # ---- 3. Dashboard analytics ----
    if trend_png or breakdown_png:
        story.append(h2("Cash-flow dashboard"))
        story.append(Paragraph("Charts below are rendered live from the audited ledger at signing time.", body_style))
        for png, caption in ((trend_png, "Monthly cash-flow trend"), (breakdown_png, "Value concentration by segment")):
            if not png:
                continue
            w, h = _png_size(png)
            disp_w = 430.0
            img = RLImage(io.BytesIO(png), width=disp_w, height=disp_w * h / max(w, 1))
            frame = Table([[img], [Paragraph(f"<font color='#5A6E85'><i>{_esc(caption)}</i></font>", body_style)]], colWidths=[460])
            frame.setStyle(TableStyle([
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("BOX", (0, 0), (-1, -1), 1, border_line),
                ("PADDING", (0, 0), (-1, -1), 6),
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
            ]))
            story.append(frame)
            story.append(Spacer(1, 10))

    # ---- 4. Integrity checks ----
    story.append(h2("Integrity checks"))
    th = ParagraphStyle("th", parent=body_style, textColor=colors.white)
    check_rows = [[Paragraph(f"<b>{h}</b>", th) for h in ("Check", "Result", "Detail")]]
    for name, passed, detail in checks:
        verdict = f"<font color='#1E7A46'><b>PASS</b></font>" if passed else f"<font color='#B3382C'><b>FAIL</b></font>"
        check_rows.append([Paragraph(_esc(name), body_style), Paragraph(verdict, body_style), Paragraph(_esc(detail), body_style)])
    ct = Table(check_rows, colWidths=[150, 55, 335])
    ct.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0C2238")),
        ("PADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, border_line),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, bg_card]),
    ]))
    story.append(ct)
    story.append(Spacer(1, 10))

    # ---- Bank reconciliation ----
    if recon:
        rs, crit = recon["stats"], recon["criteria"]

        def rtable(header, rows, widths, right=()):
            data = [[Paragraph(f"<b>{h}</b>", th) for h in header]]
            for r in rows:
                data.append([Paragraph(_esc(v), body_style) for v in r])
            t = Table(data, colWidths=widths)
            style = [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0C2238")),
                ("PADDING", (0, 0), (-1, -1), 5),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.5, border_line),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, bg_card]),
            ]
            for col in right:
                style.append(("ALIGN", (col, 1), (col, -1), "RIGHT"))
            t.setStyle(TableStyle(style))
            return t

        story.append(h2("Bank reconciliation"))
        stmt_hash = _esc(recon["statement_hash"]).removeprefix("SHA256:")
        story.append(Paragraph(
            f"Every ledger line was tested against the bank statement <b>{_esc(recon['statement'])}</b> "
            f"(SHA-256 <font name='Courier' size='7'>{stmt_hash}</font>), reading {_esc(recon['columns'])}. "
            f"Pairing criteria: exact tolerance KES {crit['exact_tol']:,.2f}, variance {crit['var_pct']:g}%, tie-up window "
            f"{crit['window']} day(s), timing ceiling {crit['timing_window']} day(s), bundled-settlement search "
            f"{'on' if crit['bundle'] else 'off'}.",
            body_style,
        ))
        footing = (
            "<font color='#1E7A46'><b>FOOTS — no unexplained difference</b></font>"
            if rs["foots"]
            else f"<font color='#B3382C'><b>DOES NOT FOOT — KES {rs['residual']:,.2f} unexplained</b></font>"
        )
        story.append(card_table(
            [
                [Paragraph(f"<b>{k}:</b>", body_style), Paragraph(v, body_style)]
                for k, v in (
                    ("Bank lines reconciled", f"{rs['matched_bank']:,} of {rs['bank_lines']:,} ({rs['match_rate']:.1f}%)"),
                    ("Ledger lines proved against the bank", f"{rs['matched_ledger']:,} of {rs['ledger_lines']:,}"),
                    ("Bank movement with no ledger entry", f"{rs['bank_only_lines']:,} item(s) · KES {rs['bank_only_total']:,.2f}"),
                    ("Ledger value never received by the bank", f"{rs['ledger_only_lines']:,} item(s) · KES {rs['ledger_only_total']:,.2f}"),
                    ("Duplicate payments identified", f"{rs['duplicate_lines']:,} item(s) · KES {rs['duplicate_total']:,.2f}"),
                    ("Value bridge", footing),
                )
            ],
            [240, 280],
        ))
        story.append(Spacer(1, 10))

        story.append(Paragraph("Value bridge — how ledger value becomes bank value", h3_style))
        story.append(rtable(
            ("Bridge line", "KES"),
            [(label, f"{value:,.2f}") for label, value in recon["bridge"]],
            [400, 110],
            right=(1,),
        ))
        story.append(Paragraph(
            "The closing line is the bank's own gross throughput, computed independently of the pairing above. "
            "Because the bridge is derived from the same population it reconciles, a non-zero residual cannot be hidden.",
            body_style,
        ))

        if recon["monthly"]:
            story.append(Paragraph("Month-by-month tie-out", h3_style))
            story.append(rtable(
                ("Month", "Ledger value", "Bank value", "Value paired", "Tie-up"),
                [(m, f"{lv:,.0f}", f"{bv:,.0f}", f"{pv:,.0f}", f"{tie:.1f}%") for m, lv, bv, pv, tie in recon["monthly"]],
                [80, 110, 110, 110, 70],
                right=(1, 2, 3, 4),
            ))

        for title, rows in (
            ("Largest bank movements with no ledger entry", recon["exceptions"]),
            ("Largest ledger entries never received by the bank", recon["unreceipted"]),
        ):
            if rows:
                story.append(Paragraph(title, h3_style))
                story.append(rtable(
                    ("Source", "Date", "Narration", "KES"),
                    [(src, dt, narr, f"{amt:,.2f}") for src, dt, narr, amt in rows],
                    [90, 70, 250, 100],
                    right=(3,),
                ))

        story.append(Paragraph("Reconciliation findings", h3_style))
        for finding in recon["findings"]:
            story.append(Paragraph(f"• {_esc(finding)}", body_style))
        story.append(Spacer(1, 10))

    # ---- 5. Key observations ----
    story.append(h2("Key observations"))
    for insight in insights:
        story.append(Paragraph(f"• {_esc(insight)}", body_style))

    # ---- 6. Recommendations ----
    story.append(h2("Recommendations"))
    for i, rec in enumerate(recommendations, 1):
        story.append(Paragraph(f"{i}. {_esc(rec)}", body_style))

    # ---- 7. Exception appendix ----
    if anomalies:
        story.append(h2("Exception quarantine appendix"))
        story.append(Paragraph(f"{len(anomalies)} record(s) were flagged for partner review. Items below remain quarantined unless marked compliant.", body_style))
        an_rows = [[Paragraph(f"<b>{h}</b>", th) for h in ("Row", "Reason")]]
        for idx, reason in anomalies[:25]:
            an_rows.append([Paragraph(str(idx), body_style), Paragraph(_esc(reason), body_style)])
        at = Table(an_rows, colWidths=[50, 435])
        at.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0C2238")),
            ("PADDING", (0, 0), (-1, -1), 5),
            ("GRID", (0, 0), (-1, -1), 0.5, border_line),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, bg_card]),
        ]))
        story.append(at)
        if len(anomalies) > 25:
            story.append(Paragraph(f"… and {len(anomalies) - 25} further quarantined row(s).", body_style))

    # ---- Cleaning change register (cell-level evidence) ----
    if changes:
        story.append(h2("Cleaning change register"))
        story.append(Paragraph(
            f"Every individual adjustment the cleaning engine made is listed below — {len(changes):,} entr(ies), "
            "referenced by spreadsheet row (row 1 holds the column headers). A reviewer can re-perform any entry against "
            "the raw file identified by the fingerprint on page 1.",
            body_style,
        ))
        ch_rows = [[Paragraph(f"<b>{h}</b>", th) for h in ("Row", "Field", "Before", "After", "Action")]]
        for row_no, field, before, after, action in changes[:20]:
            ch_rows.append([
                Paragraph(f"<font name='Courier'>{_esc(row_no)}</font>", body_style),
                Paragraph(_esc(field), body_style),
                Paragraph(_esc(before), body_style),
                Paragraph(_esc(after), body_style),
                Paragraph(_esc(action), body_style),
            ])
        cht = Table(ch_rows, colWidths=[32, 86, 128, 128, 106])
        cht.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0C2238")),
            ("PADDING", (0, 0), (-1, -1), 5),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.5, border_line),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, bg_card]),
        ]))
        story.append(cht)
        if changes_truncated:
            story.append(Paragraph(
                f"The register is capped at the first {len(changes):,} changes; the complete set is available as a CSV export from the suite.",
                body_style,
            ))
        elif len(changes) > 20:
            story.append(Paragraph(f"… and {len(changes) - 20} further entr(ies) in the downloadable register.", body_style))

    # ---- Partner sign-off ----
    story.append(h2("Partner authorization &amp; digital sign-off"))
    story.append(Paragraph(
        f"This document is an official certified audit report produced by Westminister Consulting Kenya, "
        f"reviewed and authorized for release by the signatory partner named below.",
        body_style,
    ))
    story.append(Spacer(1, 10))

    partner_style = ParagraphStyle("PartnerName", parent=body_style, fontName="Helvetica-Bold", fontSize=15, textColor=ink, spaceAfter=0)
    role_style = ParagraphStyle("PartnerRole", parent=body_style, fontName="Helvetica-Oblique", fontSize=9, textColor=muted, spaceAfter=0)

    sig_cell = [Paragraph("<font color='#5A6E85' size='8'><b>Wet signature</b></font>", body_style)]
    if signature_png:
        sw, sh = _png_size(signature_png)
        sig_cell.insert(0, RLImage(io.BytesIO(signature_png), width=170, height=170 * sh / max(sw, 1)))
    else:
        sig_cell.insert(0, Spacer(1, 34))

    sign_block = Table(
        [
            [sig_cell, ""],
            [HRFlowable(width=170, thickness=1, color=ink, spaceAfter=0), HRFlowable(width=170, thickness=1, color=ink, spaceAfter=0)],
            [Paragraph(_esc(approver_name) or "—", partner_style), Paragraph(f"Date of certification<br/><font color='#5A6E85'>{_esc(timestamp)}</font>", role_style)],
            [Paragraph(_esc(partner_title), role_style), Paragraph("", body_style)],
        ],
        colWidths=[230, 230],
        rowHeights=[None, 8, None, None],
    )
    sign_block.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("VALIGN", (0, 1), (-1, 1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BACKGROUND", (0, 0), (-1, -1), bg_card),
        ("BOX", (0, 0), (-1, -1), 1, brass),
    ]))
    story.append(sign_block)
    story.append(Spacer(1, 8))
    if signature_png and qualified:
        story.append(Paragraph("<font color='#B3382C'><b>SIGNED UNDER QUALIFICATION</b></font> — the limitations section above governs the reliance that may be placed on this report.", body_style))
    elif signature_png:
        story.append(Paragraph("<font color='#1E7A46'><b>VERIFIED &amp; CERTIFIED</b></font> — digitally signed via the Westminister pen pad and bound to the SHA-256 fingerprint above.", body_style))
    else:
        story.append(Paragraph("<i>Signature pending — this report is provisionally authorized by the senior partner account and becomes certified once wet-signed in the suite.</i>", body_style))

    footer = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
    story.append(Spacer(1, 18))
    story.append(HRFlowable(width="100%", thickness=1, color=border_line, spaceAfter=4))
    story.append(Paragraph(f"Generated by Westminister Intelligence Suite · {footer} · {_esc(fingerprint)}", sub_style))

    def _decorate(canvas, _doc):
        if not qualified:
            return
        canvas.saveState()
        canvas.setFont("Helvetica-Bold", 76)
        canvas.setFillColor(colors.Color(0.70, 0.22, 0.17, alpha=0.07))
        canvas.translate(letter[0] / 2.0, letter[1] / 2.0)
        canvas.rotate(38)
        canvas.drawCentredString(0, 0, "QUALIFIED")
        canvas.restoreState()

    doc.build(story, onFirstPage=_decorate, onLaterPages=_decorate)
    buffer.seek(0)
    return buffer.getvalue()


def _overall_drawing(quality_score: float):
    from reportlab.graphics.shapes import Drawing, String
    d = Drawing(400, 22)
    d.add(String(0, 6, "COMPOSITE", fontName="Helvetica-Bold", fontSize=9, fillColor=colors_ink()))
    d.add(String(120, 6, f"{quality_score:.1f}%", fontName="Helvetica-Bold", fontSize=9, fillColor=colors_ink()))
    return d


def colors_ink():
    from reportlab.lib import colors
    return colors.HexColor("#061625")
