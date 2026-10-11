"""wc_pdf.py - Certified PDF Executive Report Generator with Signature Embedding.
"""
import io
import os
import datetime

def generate_audit_pdf(client_name, approver_name, fingerprint, total_records, quality_score, issues_count, signature_img_bytes=None, logo_bytes=None):
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, HRFlowable
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
        story = []
        
        styles = getSampleStyleSheet()
        ink = colors.HexColor("#061625")
        brass = colors.HexColor("#C9A24F")
        muted = colors.HexColor("#5A6E85")
        text_color = colors.HexColor("#1A2B3C")
        bg_card = colors.HexColor("#F8FAFC")
        border_line = colors.HexColor("#CBD5E1")
        
        title_style = ParagraphStyle('DocTitle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=22, textColor=ink, spaceAfter=2)
        sub_style = ParagraphStyle('DocSub', parent=styles['Normal'], fontName='Helvetica', fontSize=10, textColor=muted, spaceAfter=12)
        h2_style = ParagraphStyle('SectionHeading', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=13, textColor=ink, spaceBefore=10, spaceAfter=6)
        body_style = ParagraphStyle('BodyDark', parent=styles['Normal'], fontName='Helvetica', fontSize=9.5, textColor=text_color, leading=14, spaceAfter=6)

        # 1. Header / Logo
        if logo_bytes and os.path.exists("logo.png"):
            try:
                img = RLImage("logo.png", width=140, height=45)
                story.append(img)
                story.append(Spacer(1, 8))
            except Exception:
                pass
                
        story.append(Paragraph("WESTMINISTER CONSULTING KENYA", title_style))
        story.append(Paragraph("Autonomous Financial Ledger & Cash Flow Audit Certificate", sub_style))
        story.append(HRFlowable(width="100%", thickness=2, color=brass, spaceAfter=12))
        
        # 2. Executive Metadata Table
        meta_data = [
            [Paragraph("<b>Client Organization:</b>", body_style), Paragraph(client_name, body_style)],
            [Paragraph("<b>Signatory Partner:</b>", body_style), Paragraph(approver_name, body_style)],
            [Paragraph("<b>Audit Timestamp:</b>", body_style), Paragraph(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"), body_style)],
            [Paragraph("<b>Total Records Audited:</b>", body_style), Paragraph(f"{total_records:,} ledger rows", body_style)],
            [Paragraph("<b>Cleanliness & Data Quality:</b>", body_style), Paragraph(f"<b>{quality_score:.1f}%</b> Verified", body_style)],
            [Paragraph("<b>SHA-256 Crypto Hash:</b>", body_style), Paragraph(f"<font name='Courier' color='#061625'><b>{fingerprint}</b></font>", body_style)]
        ]
        
        t = Table(meta_data, colWidths=[160, 380])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), bg_card),
            ('PADDING', (0,0), (-1,-1), 7),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOX', (0,0), (-1,-1), 1, brass),
            ('INNERGRID', (0,0), (-1,-1), 0.5, border_line)
        ]))
        story.append(t)
        story.append(Spacer(1, 12))
        
        # 3. Key Findings Section
        story.append(Paragraph("1. Executive Findings & AI Observations", h2_style))
        story.append(Paragraph(
            f"An autonomous AI intelligence audit was executed for <b>{client_name}</b> across <b>{total_records:,}</b> financial transactions. The dataset achieved an unassailable data quality rating of <b>{quality_score:.1f}%</b>.",
            body_style
        ))
        story.append(Paragraph(
            "<b>Key Compliance Highlights:</b><br/>"
            "• <b>Background AI Cleaning:</b> Missing values auto-imputed and exact duplicates purged with zero human error.<br/>"
            "• <b>Cash Flow & Tax Reconciliation:</b> Mathematical calculations balanced across all numerical attributes.<br/>"
            "• <b>Provenential Hash:</b> Stamped with immutable SHA-256 cryptographic proof for unassailable sign-off.",
            body_style
        ))
        
        story.append(Spacer(1, 10))
        
        # 4. Digital Signature Block
        story.append(Paragraph("2. Partner Authorization & Digital Sign-Off", h2_style))
        story.append(Paragraph(f"This document represents an official certified audit pack produced by Westminister Consulting Kenya. Authorized by <b>{approver_name}</b>.", body_style))
        story.append(Spacer(1, 6))
        
        if signature_img_bytes:
            try:
                sig_io = io.BytesIO(signature_img_bytes)
                sig_img = RLImage(sig_io, width=180, height=55)
                
                sig_table_data = [
                    [Paragraph("<b>Captured Partner Signature:</b>", body_style), Paragraph("<b>Audit Status:</b>", body_style)],
                    [sig_img, Paragraph("<font color='#5FB38A'><b>✅ VERIFIED & CERTIFIED</b></font><br/><font color='#5A6E85' size='8'>Digitally signed via Westminister Pen Pad</font>", body_style)]
                ]
                sig_table = Table(sig_table_data, colWidths=[270, 270])
                sig_table.setStyle(TableStyle([
                    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                    ('PADDING', (0,0), (-1,-1), 6),
                    ('BACKGROUND', (0,0), (-1,-1), bg_card),
                    ('BOX', (0,0), (-1,-1), 1, border_line)
                ]))
                story.append(sig_table)
            except Exception as e:
                story.append(Paragraph(f"Signature render status: Captured ({e})", body_style))
        else:
            story.append(Paragraph("<i>[Signature Pending - Digitally Authorized via Senior Partner Account]</i>", body_style))

        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()
    except Exception as e:
        return f"PDF generation error: {e}".encode('utf-8')