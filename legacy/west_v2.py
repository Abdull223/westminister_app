import base64
import io
import os
import re
import time
import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components
import warnings
import urllib.request
import numpy as np
from datetime import datetime

warnings.filterwarnings("ignore", category=UserWarning)

# ===== SMART ENGINE (auto-clean, lookup, PDF) =====
NULL_TOKENS = {"", "na", "n/a", "nan", "null", "none", "nil", "-", "--", "?", "#n/a", "#value!", "#div/0!", "missing", "unknown"}
LOGO_URL = "https://westministerconsulting.com/assets/front/images/WestministerLogo.png"


def read_any(file, sheet=None):
    """Read CSV/Excel efficiently, including large workbooks such as Online Retail.xlsx."""
    name = file.name.lower()
    if name.endswith((".xlsx", ".xlsm", ".xls")):
        # Keep the uploaded bytes reusable across the preview and full read.
        data = file.getvalue() if hasattr(file, "getvalue") else file.read()
        excel_bytes = io.BytesIO(data)
        sheet_name = 0 if sheet is None else sheet
        # The standard UCI Online Retail workbook has its column headers on row 1.
        # Skip the extra preview pass, and prefer the faster calamine engine when installed.
        if "online retail" in name:
            try:
                df = pd.read_excel(io.BytesIO(data), sheet_name=sheet_name, header=0, engine="calamine")
            except Exception:
                df = pd.read_excel(io.BytesIO(data), sheet_name=sheet_name, header=0, engine="openpyxl")
            df = df.dropna(how="all").dropna(axis=1, how="all").reset_index(drop=True)
            df.columns = make_unique([str(c).strip() if pd.notna(c) else f"Column_{j+1}" for j, c in enumerate(df.columns)])
            return df
        # Inspect only the first 15 rows to detect a possible title/header row.
        preview = pd.read_excel(excel_bytes, sheet_name=sheet_name, header=None, nrows=15)
        preview = preview.dropna(axis=1, how="all").reset_index(drop=True)
        hdr = 0
        for i in range(min(15, len(preview))):
            row = preview.iloc[i]
            filled = row.notna().mean()
            vals = row.dropna()
            texty = vals.map(lambda v: isinstance(v, str) and not re.fullmatch(r"[\d.,\-\s]+", v)).mean() if len(vals) else 0
            if filled >= 0.6 and texty >= 0.8:
                hdr = i
                break
        # Read the full sheet with the header applied so pandas can infer types.
        excel_bytes.seek(0)
        df = pd.read_excel(excel_bytes, sheet_name=sheet_name, header=hdr)
        df = df.dropna(how="all").dropna(axis=1, how="all").reset_index(drop=True)
        df.columns = make_unique([str(c).strip() if pd.notna(c) else f"Column_{j+1}" for j, c in enumerate(df.columns)])
        return df

    data = file.getvalue() if hasattr(file, "getvalue") else file.read()
    text = None
    for enc in ("utf-8-sig", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError("Could not decode this CSV. Save it as UTF-8 CSV and upload again.")
    import csv
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        raise ValueError("The uploaded file is empty.")
    # Delimiter whose per-line count is most consistent and highest.
    best, score = ",", -1
    for dl in [",", ";", "\t", "|"]:
        counts = [l.count(dl) for l in lines[:200]]
        if counts:
            mode = max(set(counts), key=counts.count)
            sc = mode * counts.count(mode)
            if mode > 0 and sc > score:
                best, score = dl, sc
    rows = list(csv.reader(lines, delimiter=best))
    width = max(len(r) for r in rows)
    raw = pd.DataFrame([r + [None] * (width - len(r)) for r in rows], dtype=object).replace({"": np.nan})
    raw = raw.dropna(how="all").dropna(axis=1, how="all").reset_index(drop=True)
    hdr = 0
    for i in range(min(15, len(raw))):
        row = raw.iloc[i]
        filled = row.notna().mean()
        vals = row.dropna()
        texty = vals.map(lambda v: isinstance(v, str) and not re.fullmatch(r"[\d.,\-\s]+", v)).mean() if len(vals) else 0
        if filled >= 0.6 and texty >= 0.8:
            hdr = i
            break
    cols = [str(c).strip() if pd.notna(c) else f"Column_{j+1}" for j, c in enumerate(raw.iloc[hdr])]
    df = raw.iloc[hdr + 1:].copy()
    df.columns = make_unique(cols)
    return df.reset_index(drop=True)


class _BytesUpload:
    """Small file-like adapter used by cached upload processing."""
    def __init__(self, data, name):
        self._data = data
        self.name = name
    def getvalue(self):
        return self._data
    def read(self, *args, **kwargs):
        return io.BytesIO(self._data).read(*args, **kwargs)


@st.cache_data(show_spinner=False, max_entries=3)
def _cached_read_any(data: bytes, name: str, sheet=None):
    # Cache by file bytes + sheet so Streamlit reruns don't parse the workbook again.
    return read_any(_BytesUpload(data, name), sheet)


@st.cache_data(show_spinner=False, max_entries=5)
def _cached_sheet_names(data: bytes):
    # Prefer the faster calamine engine when installed; fall back to openpyxl.
    try:
        return pd.ExcelFile(io.BytesIO(data), engine="calamine").sheet_names
    except Exception:
        return pd.ExcelFile(io.BytesIO(data), engine="openpyxl").sheet_names



def make_unique(cols):
    seen, out = {}, []
    for c in cols:
        if c in seen:
            seen[c] += 1
            out.append(f"{c}_{seen[c]}")
        else:
            seen[c] = 0
            out.append(c)
    return out


def _to_number(s):
    """'KES 1,200.50', '(300)', '12%', '5-' -> floats. Returns Series of floats."""
    t = s.astype(str).str.strip()
    neg = t.str.match(r"^\(.*\)$") | t.str.endswith("-") & t.str.len().gt(1)
    t = t.str.replace(r"[A-Za-z$€£₹]|KES|Ksh|USD", "", regex=True).str.replace(r"[,\s()%]", "", regex=True).str.rstrip("-")
    num = pd.to_numeric(t, errors="coerce")
    return num.where(~neg, -num.abs())


def infer_column(s, name=""):
    """Return (kind, converted_series). kind in numeric|integer|datetime|boolean|category|text|id"""
    if s.isna().all():
        return "empty", s
    nn = s.dropna()
    sample = nn.astype(str).str.strip()
    n = len(sample)
    if pd.api.types.is_datetime64_any_dtype(s):
        return "datetime", s
    if pd.api.types.is_bool_dtype(s):
        return "boolean", s
    low = sample.str.lower()
    if low.isin({"yes", "no", "true", "false", "y", "n"}).mean() > 0.95 and low.nunique() <= 4:
        return "boolean", s.astype(str).str.strip().str.lower().map({"yes": True, "y": True, "true": True, "no": False, "n": False, "false": False})
    id_like = re.search(r"(^|_|\b)(id|code|pin|no|number|ref|invoice|phone|tel|account)(\b|_|$)", name.lower()) and not re.search(r"date|time|dob|month|year|period", name.lower())
    num = _to_number(s)
    if num.notna().sum() / max(n, 1) >= 0.9 and not id_like:
        conv = num
        kind = "integer" if (conv.dropna() % 1 == 0).all() else "numeric"
        return kind, conv
    if not id_like and not pd.api.types.is_numeric_dtype(s):
        _dfst, _ = date_order(sample)
        dt = pd.to_datetime(sample, errors="coerce", dayfirst=_dfst)
        if dt.notna().mean() >= 0.9 and sample.str.contains(r"[-/\s]|\d{4}").mean() > 0.9:
            return "datetime", pd.to_datetime(s, errors="coerce", dayfirst=_dfst)
    if id_like or sample.nunique() / n > 0.9:
        return "id", s.astype(str).str.strip().where(s.notna())
    if sample.nunique() <= max(20, 0.05 * n):
        return "category", s
    return "text", s


def auto_clean(df, impute=True, drop_dupes=True):
    """Full automatic cleaning. Returns (clean_df, log_df, schema dict)."""
    log, schema = [], {}
    d = df.copy()
    rows0, cols0 = d.shape

    # 1. column names
    d.columns = make_unique([re.sub(r"\s+", " ", str(c)).strip() for c in d.columns])
    # 2. Trim text & unify null tokens with vectorised operations.
    # Avoid per-cell Python callbacks: they make 500k+ row Excel files appear to hang.
    for c in d.columns:
        if pd.api.types.is_object_dtype(d[c]) or pd.api.types.is_string_dtype(d[c]):
            text_values = d[c].astype("string").str.replace(r"\s+", " ", regex=True).str.strip()
            null_mask = text_values.str.lower().isin(NULL_TOKENS)
            d[c] = text_values.mask(null_mask, pd.NA).astype(object)
    # 3. drop empty rows / columns
    d = d.dropna(how="all")
    empty_cols = [c for c in d.columns if d[c].isna().all()]
    d = d.drop(columns=empty_cols)
    if rows0 - len(d):
        log.append(("Structure", "-", f"Removed {rows0 - len(d)} completely empty rows"))
    for c in empty_cols:
        log.append(("Structure", c, "Removed (column fully empty)"))
    # 4. type inference
    for c in list(d.columns):
        before = d[c].isna().sum()
        kind, conv = infer_column(d[c], c)
        schema[c] = kind
        if kind in ("numeric", "integer", "datetime", "boolean"):
            d[c] = conv
            bad = int(conv.isna().sum() - before)
            if kind == "datetime" and (pd.api.types.is_object_dtype(df[c]) or pd.api.types.is_string_dtype(df[c])):
                _, _note = date_order(df[c].dropna().astype(str).str.strip().head(5000))
                if _note:
                    log.append(("Dates", c, _note))
            msg = f"Converted to {kind}"
            if bad > 0:
                msg += f" ({bad} unreadable values became blank, review them)"
            log.append(("Type", c, msg))
        elif kind == "id":
            d[c] = conv
            log.append(("Type", c, "Kept as text identifier (not converted to number)"))
        elif kind == "category":
            d[c] = d[c].astype("string").str.strip()
            top = d[c].str.lower().value_counts()
            # unify case variants: 'nairobi' / 'NAIROBI' -> most common spelling
            canon = d[c].dropna().groupby(d[c].dropna().str.lower()).agg(lambda x: x.value_counts().index[0])
            fixed = d[c].str.lower().map(canon).where(d[c].notna())
            changed = int((fixed != d[c]).sum())
            d[c] = fixed
            if changed:
                log.append(("Consistency", c, f"Standardised {changed} inconsistent spellings/cases"))
    # 5. duplicates
    if drop_dupes:
        n = d.duplicated().sum()
        if n:
            d = d.drop_duplicates()
            log.append(("Duplicates", "-", f"Removed {n} exact duplicate rows"))
    # 6. missing values (each choice is explained)
    if impute:
        for c, k in schema.items():
            if c not in d.columns:
                continue
            m = int(d[c].isna().sum())
            if not m:
                continue
            pct = m / len(d) * 100
            if k in ("id", "text"):
                stg, why = "Not Provided", "Identifiers and free text can never be estimated; marking them visibly lets you follow up with the source."
            elif k == "datetime":
                stg, why = "Leave blank", "A date cannot be guessed without inventing history. If rows are in time order, use Forward fill or Interpolate in the Auto-Clean Studio."
            else:
                stg, why = strategy_reason(d[c])
            d[c] = fill_series(d[c], stg)
            if k == "integer" and pd.api.types.is_numeric_dtype(d[c]):
                d[c] = d[c].round()
            log.append(("Missing", c, f"{m} blanks ({pct:.1f}%) -> {stg}. Why: {why}"))
    d = d.reset_index(drop=True)
    log.append(("Summary", "-", f"{rows0:,} x {cols0} -> {d.shape[0]:,} x {d.shape[1]}"))
    return d, pd.DataFrame(log, columns=["Step", "Column", "Action taken"]), schema


@st.cache_data(show_spinner=False, max_entries=3)
def _cached_load_and_clean(data: bytes, name: str, sheet, impute: bool, drop_dupes: bool):
    """Cache the expensive read + clean pipeline by uploaded bytes and options."""
    raw = _cached_read_any(data, name, sheet)
    clean, log_df, schema = auto_clean(raw, impute, drop_dupes)
    return raw, clean, log_df, schema


def quality_score(raw, clean_schema):
    miss = raw.isna().mean().mean()
    dup = raw.duplicated().mean()
    return max(0, round(100 * (1 - 0.7 * miss - 1.0 * dup), 1))


def outliers_iqr(s, k=1.5):
    q1, q3 = s.quantile(.25), s.quantile(.75)
    i = q3 - q1
    lo, hi = q1 - k * i, q3 + k * i
    return (s < lo) | (s > hi), lo, hi


def lookup(left, right, lkey, rkey, ret_cols, mode="exact", normalise=True):
    """VLOOKUP/XLOOKUP equivalent. Returns (result, unmatched_count, duplicate_keys_in_lookup)."""
    L, R = left.copy(), right.copy()
    lk, rk = "__lk", "__rk"
    f = (lambda s: s.astype(str).str.strip().str.lower()) if normalise else (lambda s: s)
    if mode == "approximate":
        L[lk] = pd.to_numeric(L[lkey], errors="coerce").astype("float64")
        R[rk] = pd.to_numeric(R[rkey], errors="coerce").astype("float64")
        if L[lk].notna().sum() == 0 or R[rk].notna().sum() == 0:
            raise ValueError("approximate match needs NUMBER columns on both sides")
        L["__ix"] = range(len(L))
        Lv, Ln = L[L[lk].notna()].sort_values(lk), L[L[lk].isna()]
        R = R.dropna(subset=[rk]).sort_values(rk).drop_duplicates(rk)
        out = pd.merge_asof(Lv, R[[rk] + ret_cols], left_on=lk, right_on=rk, direction="backward")
        out = pd.concat([out, Ln]).sort_values("__ix").reset_index(drop=True)
        un = int(out[ret_cols[0]].isna().sum())
        return out.drop(columns=[lk, rk, "__ix"]), un, 0
    L[lk], R[rk] = f(L[lkey]), f(R[rkey])
    dup = int(R[rk].duplicated().sum())
    R1 = R.drop_duplicates(rk)  # Excel returns the FIRST match
    ren = {c: (c if c not in L.columns else f"{c}_lookup") for c in ret_cols}
    out = L.merge(R1[[rk] + ret_cols].rename(columns=ren), left_on=lk, right_on=rk, how="left")
    un = int(out[rk].isna().sum())
    return out.drop(columns=[lk, rk]), un, dup


def _how(m):
    """Money/quantity columns are added up per month; everything else (age, scores, hours) is averaged."""
    return "sum" if re.search(r"amount|total|sales|revenue|cost|price|tax|qty|quantity|income|expense|payment|value|units", str(m).lower()) else "mean"


def monthly(df, dcol, m):
    """Monthly totals (or averages for non-additive columns); works on every pandas version."""
    d = df.dropna(subset=[dcol])
    g = d.groupby(d[dcol].dt.to_period("M"))[m].agg(_how(m))
    g.index = g.index.to_timestamp()
    return g


def auto_insights(df, schema):
    """Plain-English findings written automatically."""
    out = []
    nums = [c for c, k in schema.items() if k in ("numeric", "integer") and c in df]
    cats = [c for c, k in schema.items() if k == "category" and c in df]
    dates = [c for c, k in schema.items() if k == "datetime" and c in df]
    for c in nums[:4]:
        s = df[c]
        flag, lo, hi = outliers_iqr(s)
        out.append(f"{c}: total {s.sum():,.2f}, average {s.mean():,.2f}, median {s.median():,.2f}, range {s.min():,.2f} to {s.max():,.2f}. "
                   f"{int(flag.sum())} unusual values ({flag.mean()*100:.1f}%) fall outside {lo:,.2f} to {hi:,.2f}.")
    if nums and cats:
        m, c = nums[0], cats[0]
        g = df.groupby(c)[m].sum().sort_values(ascending=False)
        if len(g):
            out.append(f"Top {c}: '{g.index[0]}' contributes {g.iloc[0]/g.sum()*100:.1f}% of total {m}. Top 3 together: {g.head(3).sum()/g.sum()*100:.1f}%.")
    if nums and dates:
        m, dcol = nums[0], dates[0]
        t = monthly(df, dcol, m)
        if len(t) >= 2:
            ch = (t.iloc[-1] - t.iloc[-2]) / abs(t.iloc[-2]) * 100 if t.iloc[-2] else np.nan
            out.append(f"Trend: latest month {t.index[-1]:%b %Y} {m} is {t.iloc[-1]:,.2f} ({ch:+.1f}% vs previous month). Peak month: {t.idxmax():%b %Y}.")
    if len(nums) >= 2:
        cm = df[nums].corr().abs().where(~np.eye(len(nums), dtype=bool)).stack().dropna()
        if len(cm):
            (a, b), v = cm.idxmax(), cm.max()
            if v > 0.7:
                out.append(f"Strong relationship: {a} and {b} move together (correlation {df[a].corr(df[b]):+.2f}).")
    return out


KRA_PIN = re.compile(r"^[AP]\d{9}[A-Z]$")


def build_pdf(title, client, kpis, insights, log_df, charts, signer, sig_png, logo_bytes, signed_at="", tables=None, sections=None, tiles=None, meta=None):
    """Executive PDF. Logo top-LEFT of every page; signature block at the end."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import Image as RLImage, PageTemplate, Frame, BaseDocTemplate
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, KeepTogether, PageBreak

    GOLD, NAVY = colors.HexColor("#AA8336"), colors.HexColor("#002043")
    buf = io.BytesIO()
    W, H = A4

    def page(canvas, doc):
        canvas.saveState()
        drawn = False
        if logo_bytes:
            try:
                img = ImageReader(io.BytesIO(logo_bytes))
                iw, ih = img.getSize()
                wd = min(44 * iw / ih, 170)
                canvas.drawImage(img, 36, H - 40 - wd * ih / iw, width=wd, height=wd * ih / iw, mask="auto")  # TOP-LEFT
                drawn = True
            except Exception:
                pass
        if not drawn:
            canvas.setFont("Helvetica-Bold", 16)
            canvas.setFillColor(GOLD)
            canvas.drawString(36, H - 62, "WESTMINISTER")
        canvas.setFont("Helvetica-Bold", 10)
        canvas.setFillColor(NAVY)
        canvas.drawRightString(W - 36, H - 50, "WESTMINISTER CONSULTING")
        canvas.setStrokeColor(GOLD)
        canvas.setLineWidth(1.5)
        canvas.line(36, H - 80, W - 36, H - 80)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.grey)
        canvas.drawString(36, 22, f"Confidential | Generated {datetime.now():%d %b %Y, %H:%M}" + (f" | Report ID {meta['report_id']}" if meta else ""))
        canvas.drawRightString(W - 36, 22, f"Page {doc.page}")
        canvas.restoreState()

    doc = BaseDocTemplate(buf, pagesize=A4, leftMargin=36, rightMargin=36, topMargin=96, bottomMargin=40)
    doc.addPageTemplates([PageTemplate(id="p", frames=[Frame(36, 40, W - 72, H - 136, id="f")], onPage=page)])
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Heading1"], textColor=GOLD, fontSize=16, spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], textColor=NAVY, fontSize=12, spaceBefore=10)
    body = ParagraphStyle("b", parent=ss["Normal"], fontSize=9, leading=13)
    cell = ParagraphStyle("c", parent=body, fontSize=8, leading=10)

    cover = []
    if meta:
        big = ParagraphStyle("big", parent=h1, fontSize=26, leading=30, spaceAfter=12)
        toc = [h_ for h_, _, _ in (sections or [])] + (["Dashboards and Visual Analysis"] if charts else []) + [c_ for c_, _ in (tables or [])] + ["Data Cleaning Audit Trail", "Authorisation Sign-Off"]
        det = Table([["Prepared for", client or "Client"], ["Report ID", meta["report_id"]], ["Generated", f"{datetime.now():%A, %d %B %Y at %H:%M}"], ["Prepared by", meta.get("prepared_by", "")],
                     ["Records analysed", meta.get("records", "")], ["Data fingerprint (SHA-256)", meta["fingerprint"]]], colWidths=[150, 373])
        det.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 9), ("LINEBELOW", (0, 0), (-1, -1), .3, colors.lightgrey), ("TEXTCOLOR", (0, 0), (0, -1), GOLD)]))
        cover = [Spacer(1, 70), Paragraph(title, big), Spacer(1, 14), det, Spacer(1, 22), Paragraph("Contents", h2)] + [Paragraph(f"{i + 1}. {re.sub(r'^\d+\.\s*', '', t_)}", body) for i, t_ in enumerate(toc)] + [
            Spacer(1, 18), Paragraph("<i>The data fingerprint identifies the exact cleaned dataset behind this report; any change to the data changes the fingerprint.</i>", cell), PageBreak()]
    s = cover + [Paragraph(title, h1), Paragraph(f"Prepared for: <b>{client or 'Client'}</b> | Generated: {datetime.now():%d %B %Y, %H:%M}", body), Spacer(1, 8)]
    s.append(Paragraph("Key Figures", h2))
    t = Table([["Metric", "Value"]] + [[k, str(v)] for k, v in kpis], colWidths=[260, 263])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                           ("GRID", (0, 0), (-1, -1), .4, colors.lightgrey), ("FONTSIZE", (0, 0), (-1, -1), 9),
                           ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F6F2E8")])]))
    s.append(t)
    for hd, items, bl in (sections or []):
        s.append(Paragraph(hd, h2))
        for it in items:
            s.append(Paragraph(("&bull; " if bl else "") + str(it).replace("&", "&amp;").replace("<", "&lt;"), body))
            s.append(Spacer(1, 3))
    if insights:
        s.append(Paragraph("Automatic Findings", h2))
    for i in insights:
        s.append(Paragraph("&bull; " + i.replace("&", "&amp;"), body))
        s.append(Spacer(1, 3))
    if charts or tiles:
        s.append(Paragraph("Dashboards and Visual Analysis", h2))
    if tiles:
        tp = [Paragraph(f'<font size="13" color="#AA8336"><b>{v}</b></font><br/><font size="7">{l}</font>', cell) for l, v in tiles]
        while len(tp) % 4:
            tp.append("")
        tg = Table([tp[i:i + 4] for i in range(0, len(tp), 4)], colWidths=[130] * 4)
        tg.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), .5, GOLD), ("INNERGRID", (0, 0), (-1, -1), .5, colors.lightgrey), ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F6F2E8"))]))
        s.append(tg)
        s.append(Spacer(1, 6))
    for item in charts:
        cap, png = item[0], item[1]
        ih_ = 240
        try:
            _w, _h = ImageReader(io.BytesIO(png)).getSize()
            ih_ = 480 * _h / _w
        except Exception:
            pass
        blk = [Paragraph(cap, h2), RLImage(io.BytesIO(png), width=480, height=ih_)]
        if len(item) > 2:
            blk.append(Paragraph("<i>" + item[2] + "</i>", body))
        s.append(KeepTogether(blk))
    for cap, tdf in (tables or []):
        s.append(Paragraph(cap, h2))
        tdf = tdf.head(60)
        lens = [max([len(str(c_))] + [len(str(v)) for v in tdf[c_].tolist()]) for c_ in tdf.columns]
        wts = [min(max(l_, 8), 70) for l_ in lens]
        cw = [523 * w_ / sum(wts) for w_ in wts]
        rw = [[Paragraph("<b>" + str(x) + "</b>", cell) for x in tdf.columns]] + [[Paragraph((f"{v:,.2f}" if isinstance(v, float) else str(v)).replace("&", "&amp;").replace("<", "&lt;"), cell) for v in r] for r in tdf.values.tolist()]
        tt = Table(rw, repeatRows=1, colWidths=cw)
        tt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8DDBF")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                ("GRID", (0, 0), (-1, -1), .3, colors.lightgrey), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F6F2E8")])]))
        s.append(tt)
    s.append(Paragraph("Data Cleaning Audit Trail", h2))
    rows = [["Step", "Column", "Action taken"]] + [[Paragraph(str(a), cell) for a in r] for r in log_df.head(40).values.tolist()]
    lt = Table(rows, colWidths=[70, 110, 343], repeatRows=1)
    lt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                            ("GRID", (0, 0), (-1, -1), .3, colors.lightgrey), ("FONTSIZE", (0, 0), (-1, 0), 8), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    s.append(lt)
    sig = Paragraph("<i>Not yet signed</i>", body)
    if sig_png:
        sig = RLImage(io.BytesIO(sig_png), width=160, height=55)
    block = Table([[Paragraph(f"<b>Approved by:</b><br/>{signer or ''}", body), sig, Paragraph(f"<b>Signed (date & time):</b><br/>{signed_at or 'Not signed'}", body)]],
                  colWidths=[190, 190, 143])
    block.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, 0), 1, GOLD), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 8)]))
    s.append(KeepTogether([Spacer(1, 25), Paragraph("Authorisation Sign-Off", h2), block]))
    doc.build(s)
    return buf.getvalue()


def chart_png(kind, df, x, y):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 4))
    if kind == "bar":
        g = df.groupby(x)[y].sum().sort_values(ascending=False).head(10)
        ax.barh(g.index.astype(str)[::-1], g.values[::-1], color="#AA8336")
    elif kind == "line":
        g = monthly(df, x, y)
        ax.plot(g.index, g.values, color="#002043", marker="o")
    else:
        ax.hist(df[y].dropna(), bins=30, color="#AA8336")
    ax.set_title(f"{y}" + (f" by {x}" if kind != "hist" else " distribution"), color="#002043")
    ax.spines[["top", "right"]].set_visible(False)
    b = io.BytesIO()
    fig.tight_layout()
    fig.savefig(b, format="png", dpi=130)
    plt.close(fig)
    return b.getvalue()


def to_excel(df, log_df, insights, schema):
    from openpyxl.styles import Font, PatternFill
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        df.to_excel(w, sheet_name="Clean Data", index=False)
        log_df.to_excel(w, sheet_name="Cleaning Log", index=False)
        pd.DataFrame({"Findings": insights}).to_excel(w, sheet_name="Insights", index=False)
        pd.DataFrame({"Column": list(schema), "Detected type": list(schema.values())}).to_excel(w, sheet_name="Schema", index=False)
        for ws in w.book.worksheets:
            for c in ws[1]:
                c.font, c.fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="002043")
            ws.freeze_panes = "A2"
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = min(40, max(10, max(len(str(c.value or "")) for c in col[:200]) + 2))
    return out.getvalue()




def col_kind(s):
    if pd.api.types.is_bool_dtype(s): return "boolean"
    if pd.api.types.is_datetime64_any_dtype(s): return "datetime"
    if pd.api.types.is_numeric_dtype(s): return "numeric"
    n = s.nunique(dropna=True)
    if n <= max(20, 0.05 * max(len(s), 1)): return "category"
    return "id" if n / max(s.notna().sum(), 1) > 0.9 else "text"


def kinds(df):
    return {c: col_kind(df[c]) for c in df.columns}


STRATS = ["Auto", "Mean", "Median", "Mode", "Zero", "Forward fill", "Backward fill", "Interpolate", "Not Provided", "Leave blank", "Drop rows"]


METHOD_GUIDE = pd.DataFrame([
    ["Mean (average)", "Numbers that are roughly symmetric with few extremes (e.g. test scores, heights)", "Keeps the column's overall average unchanged and is unbiased when values are evenly spread", "Skewed data or extreme values: one huge value drags the mean and makes the fill unrealistic"],
    ["Median (middle value)", "Skewed numbers or numbers with extremes (income, sales, prices, durations)", "The middle value ignores extremes, so a few giants do not distort the estimate", "Very small samples with no spread"],
    ["Mode (most common)", "Categories and yes/no columns (gender, region, plan type)", "A category has no average; the most frequent group is the most probable value", "No group dominates (top group under 40%): the guess is weak, so 'Not Provided' is used instead"],
    ["Zero", "Counts or amounts where blank truly means none (no sales that day)", "Matches the real-world meaning of 'nothing happened'", "When blank means 'unknown', since zero would understate the real figure"],
    ["Forward / Backward fill", "Ordered records such as daily balances or status that persists until changed", "Carries the last known value forward, which is how such data behaves", "Unordered data: values would be copied from unrelated rows"],
    ["Interpolate", "Smooth time series (temperature, running balances)", "Draws a straight line between known neighbours", "Jumpy data or categories"],
    ["Not Provided", "IDs, names, PINs, free text", "Never invent identifiers; makes gaps visible for follow-up", "Numbers (they must be numeric to calculate)"],
    ["Leave blank", "Dates, or columns more than 60% empty", "Any estimate would be mostly invented; better to recollect or exclude the column", "-"],
    ["Drop rows", "Rows missing a field that is essential (e.g. amount on an invoice)", "A row without its key value cannot be used", "When many rows would be lost and bias the result"],
], columns=["Method", "Best used when", "Why it is the right choice", "Avoid when"])


def strategy_reason(s):
    """Return (strategy, plain-English reason) for a column with blanks."""
    n, m = len(s), int(s.isna().sum())
    if m == 0:
        return "-", "No blanks."
    pct = m / max(n, 1) * 100
    k = col_kind(s)
    if pct > 60:
        return "Leave blank", f"{pct:.0f}% of this column is blank, so any estimate would be mostly invented. Recollect the data or exclude the column from analysis."
    if k == "numeric":
        nn = s.dropna()
        sk = nn.skew() if len(nn) > 2 else 0
        ex = outliers_iqr(nn)[0].mean() if len(nn) > 3 else 0
        if abs(sk) > 1 or ex > .05:
            return "Median", f"Values are skewed (skew {sk:.1f}) or have extremes ({ex*100:.0f}% unusual), so the average would be dragged by them. The median is the typical middle value and stays realistic."
        return "Mean", f"Values are fairly symmetric (skew {sk:.1f}) with few extremes, so the mean is a fair, unbiased estimate and keeps the column's average unchanged."
    if k in ("category", "boolean"):
        vc = s.dropna().astype(str).value_counts(normalize=True)
        if len(vc) and vc.iloc[0] < .4:
            return "Not Provided", f"No group dominates (the largest is only {vc.iloc[0]*100:.0f}%), so guessing the most common would often be wrong. Marked 'Not Provided' instead."
        return "Mode", f"A category has no average; the most common value ('{vc.index[0]}', {vc.iloc[0]*100:.0f}%) is the most probable one." if len(vc) else "Most common value."
    if k == "datetime":
        return "Leave blank", "Dates cannot be guessed without inventing history. Use Forward fill or Interpolate if rows are in time order."
    return "Not Provided", "Identifiers and free text must never be estimated; marking them lets you follow up."


def auto_strategy(s):
    return strategy_reason(s)[0]


def profile(df):
    rows = []
    for c in df.columns:
        s = df[c]
        stg, why = strategy_reason(s) if s.isna().any() else ("-", "No blanks.")
        rows.append({"Column": c, "Type": col_kind(s), "Missing": int(s.isna().sum()), "Missing %": round(s.isna().mean() * 100, 1),
                     "Unique": int(s.nunique()), "Auto Strategy": stg, "Why this strategy": why})
    return pd.DataFrame(rows)


def fill_series(s, strat):
    if strat == "Auto": strat = auto_strategy(s)
    num = pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s)
    if strat == "Mean" and num: return s.fillna(s.mean())
    if strat == "Median" and num: return s.fillna(s.median())
    if strat == "Mode": return s.fillna(s.mode().iat[0]) if not s.mode().empty else s
    if strat == "Zero" and num: return s.fillna(0)
    if strat == "Forward fill": return s.ffill()
    if strat == "Backward fill": return s.bfill()
    if strat == "Interpolate" and (num or pd.api.types.is_datetime64_any_dtype(s)): return s.interpolate(limit_direction="both")
    if strat == "Not Provided" and not num: return s.astype(object).fillna("Not Provided")
    return s


def smart_text_tidy(df):
    d = df.copy(); n = 0
    for c in d.columns:
        if d[c].dtype == object or str(d[c].dtype) in ("string", "str"):
            new = d[c].map(lambda v: re.sub(r"\s+", " ", v).strip() if isinstance(v, str) else v)
            n += int((new.astype(str) != d[c].astype(str)).sum()); d[c] = new
    return d, n



import os


def _script_dir():
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except NameError:
        return os.getcwd()


def load_logo():
    """Logo: local file next to west.py first, then website (with browser-like headers), cached locally."""
    d = _script_dir()
    for n in ("logo.png", "logo.jpg", "WestministerLogo.png"):
        p = os.path.join(d, n)
        if os.path.exists(p):
            return open(p, "rb").read()
    try:
        req = urllib.request.Request(LOGO_URL, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
                                                         "Referer": "https://westministerconsulting.com/"})
        data = urllib.request.urlopen(req, timeout=10).read()
        if data[:8] == b"\x89PNG\r\n\x1a\n" or data[:2] == b"\xff\xd8":
            try:
                open(os.path.join(d, "logo.png"), "wb").write(data)
            except Exception:
                pass
            return data
    except Exception:
        pass
    return None


def _f(x):
    return f"{x:,.2f}".rstrip("0").rstrip(".") if isinstance(x, (int, float, np.floating, np.integer)) else str(x)


def narrative(df, raw, kd, log, prio=()):
    """Rule-based explanation: summary, per-column meaning, findings, risks, recommendations."""
    n, c = df.shape
    nums = _ord([x for x in df.columns if kd[x] == "numeric"], prio)
    cats = _ord([x for x in df.columns if kd[x] == "category"], prio)
    cats = [x for x in cats if not re.search(r"e-?mail|phone|mobile|(^|[_\s])pin($|[_\s])|kra", str(x).lower())]
    dates = _ord([x for x in df.columns if kd[x] == "datetime"], prio)
    blanks0, blanks1 = int(raw.isna().sum().sum()), int(df.isna().sum().sum())
    nd = 0
    for _, col, act in log.values.tolist():
        m = re.match(r"Removed (\d+) exact duplicate", str(act))
        if m:
            nd += int(m.group(1))
    colrows, facts, risks, recs, finds = [], [], [], [], []
    for x in df.columns:
        s, k = df[x], kd[x]
        pre = float(raw[x].isna().mean() * 100) if x in raw else 0.0
        if k == "numeric":
            sk = s.skew() if s.notna().sum() > 2 else 0
            shape = "a few very large values pull the average up" if sk > 1 else "a few very small values pull the average down" if sk < -1 else "values are fairly evenly spread"
            d = f"Average {_f(s.mean())}, median {_f(s.median())}, from {_f(s.min())} to {_f(s.max())}; {shape}."
            fl, lo, hi = outliers_iqr(s.dropna())
            if int(fl.sum()):
                risks.append(f"'{x}' has {int(fl.sum())} unusual values outside {_f(lo)} to {_f(hi)}.")
                recs.append(f"Verify the {int(fl.sum())} unusual values in '{x}' against source documents before relying on its totals or averages.")
        elif k == "category":
            vc = s.astype(str).value_counts(normalize=True)
            d = f"{len(vc)} groups. Largest: '{vc.index[0]}' ({vc.iloc[0]*100:.1f}%); smallest: '{vc.index[-1]}' ({vc.iloc[-1]*100:.1f}%)."
            if vc.iloc[0] > .6 and len(vc) > 2:
                risks.append(f"'{x}' is dominated by '{vc.index[0]}' ({vc.iloc[0]*100:.0f}% of records), so conclusions may not apply to other groups.")
                recs.append(f"Collect more records for the smaller '{x}' groups before drawing conclusions about them.")
        elif k == "datetime":
            d = f"Runs from {s.min():%d %b %Y} to {s.max():%d %b %Y} ({(s.max() - s.min()).days} days)." if s.notna().any() else "No valid dates."
        elif k == "boolean":
            d = f"{s.mean()*100:.1f}% are Yes/True."
        elif k == "id":
            d = f"{s.nunique():,} unique values out of {len(s):,} records (identifier)."
        else:
            d = f"Free text; typical length {s.astype(str).str.len().mean():.0f} characters."
        handled = f"{pre:.1f}% blank in the original; filled automatically" if pre > 0 else "complete"
        if pre >= 5:
            risks.append(f"'{x}' was {pre:.1f}% blank in the original file; filled values are estimates.")
            recs.append(f"Fix data capture for '{x}' at the source (it was {pre:.1f}% blank) so future files need no estimation.")
        colrows.append({"Column": x, "Type": k, "What the data shows": d, "Completeness": handled})
        facts.append(f"{x} [{k}]: {d} ({handled})")
    # group differences (p-values corrected for the number of comparisons made)
    tests = []
    for ct in cats[:3]:
        for nm in nums[:3]:
            g = df.groupby(ct)[nm].agg(["mean", "count"])
            g = g[g["count"] >= 5]
            if len(g) >= 2 and df[nm].mean():
                gap = (g["mean"].max() - g["mean"].min()) / abs(df[nm].mean()) * 100
                pv = None
                try:
                    from scipy import stats
                    grp = [v[nm].dropna().values for _, v in df.groupby(ct) if len(v) >= 5]
                    pv = float(stats.f_oneway(*grp)[1])
                except Exception:
                    pass
                if gap >= 10:
                    tests.append((gap, ct, nm, g, pv))
    m_ = max(len(tests), 1)
    for gap, ct, nm, g, pv in sorted(tests, key=lambda t_: -t_[0])[:5]:
        p, ok = "", True
        if pv is not None:
            pa = min(1.0, pv * m_)
            ok = pa < .05
            p = (f" The difference is statistically significant even after allowing for {m_} comparisons (adjusted p={pa:.3g})." if ok
                 else f" After allowing for {m_} comparisons the difference could be chance (adjusted p={pa:.2g}), so treat it as indicative only.")
        finds.append(f"Average {nm} is highest for {ct} = '{g['mean'].idxmax()}' ({_f(g['mean'].max())}) and lowest for '{g['mean'].idxmin()}' ({_f(g['mean'].min())}), a gap of {gap:.0f}% of the overall average.{p}")
        if ok:
            recs.append(f"Study what '{g['mean'].idxmax()}' does differently in {ct} and test whether it can be applied to '{g['mean'].idxmin()}' to lift {nm}.")
    # correlations
    if len(nums) >= 2:
        cm = df[nums].corr().abs().where(~np.eye(len(nums), dtype=bool)).stack().dropna()
        seen = set()
        for (a, b), v in cm.sort_values(ascending=False).items():
            if v < .4 or len(seen) >= 3 or frozenset((a, b)) in seen:
                continue
            seen.add(frozenset((a, b)))
            r = df[a].corr(df[b])
            st_ = "strong" if v >= .7 else "moderate"
            finds.append(f"{a} and {b} have a {st_} {'positive' if r > 0 else 'negative'} relationship (r={r:+.2f}): when one rises, the other tends to {'rise' if r > 0 else 'fall'}.")
            recs.append(f"Investigate whether {a} influences {b} (or the reverse). Correlation alone does not prove cause, so confirm with a targeted review.")
    # trend
    if dates and nums:
        t = monthly(df, dates[0], nums[0])
        if len(t) >= 3:
            ch = (t.iloc[-1] - t.iloc[0]) / abs(t.iloc[0]) * 100 if t.iloc[0] else 0
            finds.append(f"The monthly {'total' if _how(nums[0]) == 'sum' else 'average'} of {nums[0]} moved from {_f(t.iloc[0])} ({t.index[0]:%b %Y}) to {_f(t.iloc[-1])} ({t.index[-1]:%b %Y}), a change of {ch:+.0f}%. Peak month: {t.idxmax():%b %Y}.")
    if nd:
        risks.append(f"{nd} duplicate records were found and removed.")
        recs.append("Add unique-ID validation at data entry to stop duplicate records at the source.")
    if n < 100:
        risks.append(f"Only {n} records: results may not be reliable.")
    if not finds:
        finds.append("No strong group differences or relationships were detected; the data appears fairly uniform.")
    recs += ["Refresh this analysis on a regular schedule and keep this audit trail as evidence of how the data was prepared.",
             "Have the responsible manager review the flagged items above and confirm them before decisions are taken."]
    recs = list(dict.fromkeys(recs))
    summ = [f"This report analyses {n:,} records across {c} columns ({len(nums)} numeric, {len(cats)} category, {len(dates)} date, {c - len(nums) - len(cats) - len(dates)} other).",
            f"Data quality: the original file contained {blanks0:,} blank cells and {nd} duplicate rows (quality score {quality_score(raw, kd)}%). After automatic cleaning {blanks1:,} blanks remain. Every change is listed in the audit trail at the end of this report."]
    prep = [f"{col}: {act}" for stp, col, act in log.values.tolist() if stp in ("Missing", "Duplicates", "Consistency", "Rows", "Outliers", "Text")]
    prep += ["Method note: the mean (average) is used for evenly spread numbers; the median (middle value) when numbers are skewed or contain extremes; the mode (most common value) for categories; identifiers and text are never estimated; dates are never guessed; columns over 60% blank are left blank."]
    secs = [("1. Executive summary", summ, False), ("2. How the data was prepared, and why", prep, True), ("3. Key findings", finds, True),
            ("4. Risks and data limitations", risks or ["No material data risks were detected."], True),
            ("5. Recommendations", [f"{i+1}. {r}" for i, r in enumerate(recs)], False)]
    return {"sections": secs, "columns": pd.DataFrame(colrows), "facts": "\n".join(facts + finds + risks)}


def report_charts(df, kd, prio=()):
    """Dashboard charts for the PDF; each has a data-driven takeaway."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    nums = _ord([x for x in df.columns if kd[x] == "numeric"], prio)
    cats = _ord([x for x in df.columns if kd[x] == "category"], prio)
    cats = [x for x in cats if not re.search(r"e-?mail|phone|mobile|(^|[_\s])pin($|[_\s])|kra", str(x).lower())]
    dates = _ord([x for x in df.columns if kd[x] == "datetime"], prio)
    out = []

    def png(fig):
        b = io.BytesIO(); fig.tight_layout(); fig.savefig(b, format="png", dpi=120); plt.close(fig); return b.getvalue()
    for cc in cats[:3]:
        vc = df[cc].astype(str).value_counts()
        v = vc.head(10)
        f, ax = plt.subplots(figsize=(8, 3.4)); ax.barh(v.index[::-1], v.values[::-1], color="#AA8336"); ax.spines[["top", "right"]].set_visible(False); ax.set_title(f"Records by {cc}", color="#002043")
        tk = f"Takeaway: '{vc.index[0]}' is the largest {cc} group with {vc.iloc[0]:,} records ({vc.iloc[0]/len(df)*100:.0f}%)" + (f"; the smallest shown is '{vc.index[-1]}' ({vc.iloc[-1]:,})." if len(vc) > 1 else ".")
        if vc.iloc[0] / len(df) > .6:
            tk += " The data is concentrated in one group, so findings mostly describe that group."
        out.append((f"Records by {cc}", png(f), "How to read: each bar is the number of records in a group; longer bars are bigger groups. " + tk))
    if nums:
        k = nums[:4]
        f, axs = plt.subplots(2, 2, figsize=(8, 4.6))
        for ax, nm in zip(axs.ravel(), k):
            ax.hist(df[nm].dropna(), bins=20, color="#AA8336"); ax.set_title(nm, fontsize=9, color="#002043"); ax.spines[["top", "right"]].set_visible(False)
        for ax in axs.ravel()[len(k):]:
            ax.axis("off")
        tk = "; ".join(f"{nm}: average {_f(df[nm].mean())}, median {_f(df[nm].median())}" for nm in k)
        out.append(("Distribution of numeric columns", png(f), "How to read: tall bars are the most common values; isolated bars far from the rest are unusual values. Takeaway: " + tk + ". When average and median differ a lot, a few extreme values are pulling the average."))
    for nm in nums[:2]:
        if cats:
            g = df.groupby(cats[0])[nm].mean().sort_values(ascending=False).head(10)
            f, ax = plt.subplots(figsize=(8, 3.4)); ax.barh(g.index.astype(str)[::-1], g.values[::-1], color="#002043"); ax.spines[["top", "right"]].set_visible(False); ax.set_title(f"Average {nm} by {cats[0]}", color="#002043")
            out.append((f"Average {nm} by {cats[0]}", png(f), f"How to read: compares the average {nm} across {cats[0]} groups. Takeaway: highest is '{g.index[0]}' ({_f(g.iloc[0])}), lowest is '{g.index[-1]}' ({_f(g.iloc[-1])}); large gaps point to groups needing attention or best practice."))
    if len(nums) >= 2:
        cm = df[nums[:8]].corr()
        f, ax = plt.subplots(figsize=(6.2, 4.8)); ax.imshow(cm, cmap="YlOrBr", vmin=-1, vmax=1)
        ax.set_xticks(range(len(cm))); ax.set_xticklabels(cm.columns, rotation=45, ha="right", fontsize=8); ax.set_yticks(range(len(cm))); ax.set_yticklabels(cm.columns, fontsize=8)
        for i in range(len(cm)):
            for j in range(len(cm)):
                ax.text(j, i, f"{cm.iat[i, j]:.2f}", ha="center", va="center", fontsize=7)
        pr = cm.abs().where(~np.eye(len(cm), dtype=bool)).stack().dropna()
        tk = ""
        if len(pr):
            (a, b), v = pr.idxmax(), pr.max()
            tk = f" Takeaway: the strongest link is between {a} and {b} (r={cm.loc[a, b]:+.2f})."
        out.append(("Relationships between numeric columns", png(f), "How to read: values near +1 or -1 mean two columns move together strongly; near 0 means little relationship." + tk))
    if len(cats) >= 2:
        ct = pd.crosstab(df[cats[0]], df[cats[1]]).iloc[:8, :8]
        f, ax = plt.subplots(figsize=(7, 4)); ax.imshow(ct, cmap="YlOrBr")
        ax.set_xticks(range(ct.shape[1])); ax.set_xticklabels(ct.columns, rotation=45, ha="right", fontsize=8); ax.set_yticks(range(ct.shape[0])); ax.set_yticklabels(ct.index, fontsize=8)
        for i in range(ct.shape[0]):
            for j in range(ct.shape[1]):
                ax.text(j, i, str(ct.iat[i, j]), ha="center", va="center", fontsize=7)
        st_ = ct.stack(); (r_, c_) = st_.idxmax()
        out.append((f"{cats[0]} versus {cats[1]}", png(f), f"How to read: each cell counts records with that combination; darker cells are more common. Takeaway: the most common combination is {cats[0]} = '{r_}' with {cats[1]} = '{c_}' ({st_.max():,} records)."))
    if dates and nums:
        t = monthly(df, dates[0], nums[0]); f, ax = plt.subplots(figsize=(8, 3.4)); ax.plot(t.index, t.values, color="#002043", marker="o"); ax.spines[["top", "right"]].set_visible(False); ax.set_title(f"{nums[0]} over time", color="#002043")
        out.append((f"{nums[0]} over time", png(f), f"How to read: each point is one month. Takeaway: peak was {t.idxmax():%b %Y} ({_f(t.max())}) and the lowest {t.idxmin():%b %Y} ({_f(t.min())}); sharp spikes or drops should be explained."))
    return out


def ai_explain(key, facts):
    import json
    body = json.dumps({"model": "claude-sonnet-5-5", "max_tokens": 1500, "messages": [{"role": "user", "content":
        "You are a senior data analyst writing for a firm's partners. Using ONLY these summary facts (no raw data), write a clear plain-English commentary: what the data means, what stands out, and 4-6 practical recommendations. Do not invent numbers. No markdown symbols.\n\n" + facts}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=60).read())
    txt = "".join(b.get("text", "") for b in r["content"])
    return [re.sub(r"[#*_`]", "", p).strip() for p in txt.split("\n\n") if p.strip()]



from collections import Counter
import difflib

EMAIL_RE = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
ROLE_NAME = [
    ("age", r"(^|[_\s])age($|[_\s])"), ("gender", r"gender|(^|[_\s])sex($|[_\s])"),
    ("percentage", r"percent|pct|%|ratio|share"), ("phone", r"phone|mobile|msisdn|(^|[_\s])tel($|[_\s])|contact no"),
    ("email", r"e-?mail"), ("kra_pin", r"(^|[_\s])pin($|[_\s])|kra"),
    ("money", r"amount|total|price|cost|revenue|sales|salary|pay|income|expense|balance|debit|credit|fee|tax|vat|value|budget|profit|wage|gross|net"),
    ("quantity", r"qty|quantity|units|count|pieces|volume|stock"),
    ("location", r"county|city|town|region|country|location|branch|area|address|village|ward"),
    ("identifier", r"(^|[_\s])(id|code|ref|reference|number|no|sku|invoice|receipt|account)($|[_\s])"),
    ("name", r"name|customer|client|supplier|vendor|employee|staff|company|payee|respondent"),
    ("status/type", r"status|state|stage|type|class|grade|category|level|segment|group|platform|app|occupation|chronotype"),
]
DT_KEYWORDS = {
    "Sales / invoice ledger": [r"invoice", r"sales", r"customer", r"receipt", r"vat", r"revenue", r"qty|quantity", r"price"],
    "Payroll / HR records": [r"salary|payroll|wage", r"employee|staff", r"department", r"nssf|nhif|paye|shif", r"gross|net pay", r"leave"],
    "Inventory / stock": [r"sku", r"stock|reorder", r"warehouse", r"item|product", r"qty|quantity", r"unit"],
    "Bank / transaction statement": [r"debit", r"credit", r"balance", r"narration|description", r"transaction", r"reference|ref"],
    "Tax / compliance (KRA)": [r"kra|(^|[_\s])pin($|[_\s])", r"vat|withholding|wht", r"etims|control unit|cu ", r"tax", r"customs|duty"],
    "Survey / behavioural study": [r"survey|respondent", r"score|rating|scale", r"hours|minutes|frequency", r"gender", r"age", r"habit|usage|sleep|stress|screen"],
    "Customer / contact list": [r"email", r"phone|mobile", r"name", r"address", r"county|city"],
}
PLAN = {
    "Sales / invoice ledger": ["Total, average and top customers/products by revenue", "Monthly sales trend and month-on-month change", "Check quantity x price = line total, duplicate invoice numbers, negative amounts", "VAT consistency and KRA PIN validity"],
    "Payroll / HR records": ["Headcount and payroll cost by department", "Salary distribution and unusual salaries", "Duplicate employee IDs and missing statutory numbers (PIN/NSSF/SHIF)", "Gender and grade pay comparison"],
    "Inventory / stock": ["Stock value and quantity by item/category", "Items with negative or zero stock, duplicate SKUs", "Fast and slow movers", "Price outliers"],
    "Bank / transaction statement": ["Total debits vs credits and running balance check", "Duplicate transactions and unusual large items", "Monthly cash-flow trend", "Reconcile against the ledger using VLOOKUP"],
    "Tax / compliance (KRA)": ["Validate every KRA PIN format", "Compute VAT / withholding and compare with declared tax", "Flag duplicate invoices and unusual amounts", "Prepare an exceptions list for follow-up"],
    "Survey / behavioural study": ["Profile of respondents (age, gender, group sizes)", "Compare averages across groups with significance tests", "Strongest relationships between behaviours", "Check impossible ages and out-of-range scores"],
    "Customer / contact list": ["Validate emails and phone numbers", "Find duplicate customers and near-duplicate names", "Completeness by field", "Breakdown by county/city"],
    "General data table": ["Profile every column", "Find duplicates, blanks and unusual values", "Compare groups and look for relationships"],
}


def _ord(lst, prio):
    prio = list(prio or [])
    return sorted(lst, key=lambda c: prio.index(c) if c in prio else 999)


def detect_roles(df, overrides=None):
    roles = {}
    for c in df.columns:
        s, k = df[c], col_kind(df[c])
        samp = s.dropna().astype(str).str.strip().head(3000)
        role, conf, why = None, .5, "from the type of values"
        nm = str(c).lower()
        if len(samp) and k != "datetime":
            if samp.str.match(EMAIL_RE).mean() >= .6:
                role, conf, why = "email", .97, "most values look like email addresses"
            elif samp.str.upper().str.match(KRA_PIN.pattern).mean() >= .6:
                role, conf, why = "kra_pin", .97, "most values match the KRA PIN pattern (A/P + 9 digits + letter)"
            elif (k in ("id", "text") or re.search(r"phone|mobile|msisdn|tel", nm)) and samp.str.replace(r"[\s\-\+\(\)]", "", regex=True).str.match(r"^(254|0)?[17]\d{8}$").mean() >= .6:
                role, conf, why = "phone", .93, "most values look like Kenyan phone numbers"
        if role is None:
            if k == "datetime":
                role, conf, why = "date", .95, "values are dates"
            elif k == "boolean":
                role, conf, why = "boolean", .9, "only yes/no style values"
            else:
                nr = next((r for r, p in ROLE_NAME if re.search(p, nm)), None)
                if nr in ("money", "quantity", "percentage", "age") and k == "numeric":
                    role, conf, why = nr, .9, f"column name suggests {nr} and values are numbers"
                elif nr in ("identifier", "name") and k in ("id", "text", "category"):
                    role, conf, why = nr, .85, f"column name suggests {nr}"
                elif nr == "identifier" and k == "numeric":
                    role, conf, why = "identifier", .7, "name suggests an identifier"
                elif nr in ("gender", "location", "status/type") and k in ("category", "text"):
                    role, conf, why = nr, .88, f"column name suggests {nr} and values repeat in a few groups"
                else:
                    role, conf, why = {"numeric": ("measure", .6, "a general numeric measurement"), "category": ("category", .7, "values repeat in a few groups"),
                                       "id": ("identifier", .7, "nearly every value is unique"), "text": ("text", .6, "free text")}.get(k, ("text", .5, "unclear"))
        if overrides and c in overrides:
            role, conf, why = overrides[c], 1.0, "set by you"
        roles[c] = (role, conf, why)
    return roles


def understand(df, overrides=None):
    roles = detect_roles(df, overrides)
    cnt = Counter(r for r, _, _ in roles.values())
    names = " ".join(map(str, df.columns)).lower()
    score, hits = {}, {}
    for t, kws in DT_KEYWORDS.items():
        h = [k for k in kws if re.search(k, names)]
        hits[t] = h
        score[t] = len(h) * 1.5
    score["Sales / invoice ledger"] += (1.5 if cnt["money"] and cnt["date"] else 0) + (.5 if cnt["identifier"] else 0)
    score["Bank / transaction statement"] += .5 if cnt["money"] and cnt["date"] else 0
    score["Tax / compliance (KRA)"] += 2 if cnt["kra_pin"] else 0
    score["Survey / behavioural study"] += cnt["age"] + cnt["gender"] + (1 if not cnt["money"] else 0) + (1 if cnt["measure"] >= 3 else 0)
    score["Customer / contact list"] += cnt["email"] + cnt["phone"] + (1 if cnt["name"] else 0)
    score["Sales / invoice ledger"] += 2 if any(re.search(k, names) for k in (r"invoice", r"sales", r"receipt")) and cnt["money"] else 0
    score["Customer / contact list"] -= 2 if cnt["money"] else 0
    score["General data table"] = 1.0
    top = sorted(score.items(), key=lambda kv: -kv[1])
    dtype_, sc = top[0]
    conf = int(100 * sc / (sc + top[1][1] + 1))
    ids = [c for c, (r, _, _) in roles.items() if r == "identifier" and df[c].notna().any()]
    grain = "No single identifier column found."
    if ids:
        best = max(ids, key=lambda c: df[c].nunique() / max(len(df), 1))
        ratio = df[best].nunique() / max(len(df), 1)
        grain = f"Each row is one '{best}'." if ratio >= .95 else f"About {1 / max(ratio, 1e-9):.1f} rows per '{best}' (the same {best} appears several times, so rows look like transactions or repeated entries)."
    dates = [c for c, (r, _, _) in roles.items() if r == "date"]
    cover = ""
    if dates and df[dates[0]].notna().any():
        cover = f" Dates in '{dates[0]}' run from {df[dates[0]].min():%d %b %Y} to {df[dates[0]].max():%d %b %Y}."
    # primary choices
    money = [c for c, (r, _, _) in roles.items() if r == "money"]
    pref = [c for c in money if re.search(r"total|amount|revenue|sales|salary|net|value", str(c).lower())]
    measures = [c for c, (r, _, _) in roles.items() if r in ("quantity", "measure")]
    metric = (pref or money or measures or [None])[0]
    dims = [c for r_ in ("status/type", "category", "location", "gender", "name") for c, (r, _, _) in roles.items() if r == r_ and 2 <= df[c].nunique() <= 20]
    prio = [x for x in [metric] + dims[:3] + dates[:1] if x]
    # ---- validation checks ----
    issues, flags, fuzzy = [], [], []

    def add(check, cols, mask, sev, meaning, action):
        try:
            mask = mask.fillna(False)
            n_ = int(mask.sum())
            if n_:
                issues.append({"Check": check, "Columns": cols, "Rows affected": n_, "Severity": sev, "What it means": meaning, "Suggested action": action})
                flags.append((f"{check}: {cols}", df.index[mask.values]))
        except Exception:
            pass
    today = pd.Timestamp.today()
    for c, (r, _, _) in roles.items():
        x = df[c]
        if r == "email":
            add("Invalid email", c, x.notna() & ~x.astype(str).str.match(EMAIL_RE), "Medium", "Values that are not valid email addresses.", "Correct at source or contact the person another way.")
        elif r == "phone":
            add("Invalid phone", c, x.notna() & ~x.astype(str).str.replace(r"[\s\-\+\(\)]", "", regex=True).str.match(r"^(254|0)?[17]\d{8}$"), "Medium", "Numbers that do not fit Kenyan mobile format.", "Confirm numbers; add the 254 or 0 prefix where missing.")
        elif r == "kra_pin":
            add("Invalid KRA PIN", c, x.notna() & ~x.astype(str).str.strip().str.upper().str.match(KRA_PIN.pattern), "High", "PINs that do not match the A/P + 9 digits + letter pattern.", "Verify each PIN on iTax before relying on the record.")
        elif r == "date":
            add("Future date", c, x > today + pd.Timedelta(days=1), "Medium", "Dates later than today.", "Check for typing errors in the year or day/month order.")
            add("Implausibly old date", c, x < pd.Timestamp("1900-01-01"), "Medium", "Dates before 1900.", "Check for default or wrongly typed dates.")
        elif r in ("money", "quantity"):
            add("Negative value", c, x < 0, "Medium", "Negative amounts or quantities; can be genuine refunds or credit notes, or mistakes.", "Confirm each against its credit note or source document.")
        elif r == "age":
            add("Impossible age", c, (x < 0) | (x > 120), "High", "Ages below 0 or above 120.", "Correct from source.")
        elif r == "percentage" and x.max() > 1.5:
            add("Percentage out of range", c, (x < 0) | (x > 100), "Medium", "Percentages outside 0-100.", "Check units (0-1 versus 0-100).")
        elif r == "identifier" and x.notna().any() and x.nunique() / max(len(x), 1) > .5:
            add("Duplicate identifier", c, x.duplicated(keep=False) & x.notna() & (x.astype(str) != "Not Provided"), "High", "The same identifier appears on more than one row.", "Confirm whether these are true duplicates or a reused number.")
        if r in ("money", "measure") and x.notna().sum() > 8:
            q1, q3 = x.quantile(.25), x.quantile(.75)
            i = q3 - q1
            if i > 0:
                add("Extreme value", c, (x < q1 - 3 * i) | (x > q3 + 3 * i), "Medium", "Values far beyond the normal spread (3x IQR).", "Verify against source before totals are relied on.")
        if r in ("status/type", "category", "location", "name", "gender") and 2 <= x.nunique() <= 60:
            vc = x.dropna().astype(str).value_counts()
            u = list(vc.index)
            for a in range(len(u)):
                for b in range(a + 1, len(u)):
                    if u[a].lower() != u[b].lower() and difflib.SequenceMatcher(None, u[a].lower(), u[b].lower()).ratio() >= .85:
                        fuzzy.append({"Column": c, "Keep": u[a], "Merge": u[b], "Rows": int(vc[u[b]])})
        if x.nunique() <= 1 and len(df) > 1:
            issues.append({"Check": "Constant column", "Columns": c, "Rows affected": len(df), "Severity": "Low", "What it means": "Every value is the same, so the column adds no information.", "Suggested action": "Drop it from analysis."})
    if fuzzy:
        fz = pd.DataFrame(fuzzy)
        issues.append({"Check": "Near-duplicate spellings", "Columns": ", ".join(fz["Column"].unique()), "Rows affected": int(fz["Rows"].sum()), "Severity": "Medium", "What it means": "Categories spelled almost the same (e.g. 'Nairobi' and 'Nairobi CBD') split totals.", "Suggested action": "Merge them using the button on the File Understanding tab."})
    qc = [c for c, (r, _, _) in roles.items() if r == "quantity"]
    pc = [c for c in df.columns if re.search(r"price|rate|unit", str(c).lower()) and roles[c][0] == "money"]
    tc = [c for c in df.columns if re.search(r"total|amount|line|gross", str(c).lower()) and roles[c][0] == "money" and c not in pc]
    if qc and pc and tc:
        calc = df[qc[0]] * df[pc[0]]
        add("Quantity x price does not equal total", f"{qc[0]} x {pc[0]} vs {tc[0]}", (calc - df[tc[0]]).abs() > .01 * df[tc[0]].abs().clip(lower=1), "High", "The line total disagrees with quantity multiplied by price.", "Recalculate or confirm discounts/rounding.")
    for c, (r, _, _) in roles.items():
        if r == "money":
            x = df[c].dropna()
            x = x[x > 0]
            if len(x) >= 300 and x.max() / max(x.min(), 1e-9) > 100:
                try:
                    from scipy import stats
                    fd = x.astype(float).map(lambda v: int(f"{v:.6e}"[0]))
                    obs = fd.value_counts().reindex(range(1, 10), fill_value=0).values
                    exp_ = np.log10(1 + 1 / np.arange(1, 10)) * obs.sum()
                    pv = stats.chisquare(obs, exp_)[1]
                    if pv < .001:
                        issues.append({"Check": "Benford's law deviation", "Columns": c, "Rows affected": 0, "Severity": "Medium",
                                       "What it means": f"Leading digits depart from the pattern expected in natural financial data (p={pv:.2g}). Common causes: capped, rounded, fixed-price or hand-entered values; occasionally fabricated figures.",
                                       "Suggested action": "Screening indicator only: review the largest and most repeated amounts."})
                except Exception:
                    pass
    iss = pd.DataFrame(issues, columns=["Check", "Columns", "Rows affected", "Severity", "What it means", "Suggested action"])
    if len(iss):
        iss = iss.assign(_o=iss["Severity"].map({"High": 0, "Medium": 1, "Low": 2})).sort_values(["_o", "Rows affected"], ascending=[True, False]).drop(columns="_o").reset_index(drop=True)
    summary = f"I understand this file as: {dtype_} ({conf}% confident). {len(df):,} records, {df.shape[1]} columns. {grain}{cover}"
    return {"type": dtype_, "conf": conf, "summary": summary, "roles": roles, "metric": metric, "dims": dims, "dates": dates, "prio": prio,
            "issues": iss, "flags": flags, "fuzzy": pd.DataFrame(fuzzy), "plan": PLAN.get(dtype_, PLAN["General data table"]), "hits": hits.get(dtype_, [])}


def about_sections(U, df, q=None):
    paras = [U["summary"], "Column meanings detected: " + "; ".join(f"{c} = {r}" for c, (r, _, _) in list(U["roles"].items())[:14]) + ("; ..." if len(U["roles"]) > 14 else "") + "."]
    if q:
        paras.append(f"Data quality scorecard: completeness {q['Completeness']:.0f}%, uniqueness {q['Uniqueness']:.0f}%, validity {q['Validity']:.0f}%, consistency {q['Consistency']:.0f}%; overall {q['overall']:.0f}%.")
    paras.append("Because of this, the analysis focused on: " + "; ".join(U["plan"][:3]) + ".")
    secs = [("About this file", paras, False)]
    iss = U["issues"]
    if len(iss):
        secs.append(("Validation findings (checks specific to this type of file)", [f"[{r['Severity']}] {r['Check']} in {r['Columns']}: {r['Rows affected']:,} rows. {r['Suggested action']}" for _, r in iss.head(10).iterrows()], True))
    else:
        secs.append(("Validation findings", ["All automatic validation checks passed with no exceptions."], False))
    return secs


def exceptions_xlsx(df, U):
    out = io.BytesIO()
    parts = []
    for reason, idx in U["flags"]:
        parts.append(df.loc[idx].head(5000).assign(Issue=reason))
    ex = pd.concat(parts) if parts else pd.DataFrame({"Issue": ["No exceptions found"]})
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        U["issues"].to_excel(w, sheet_name="Summary", index=False)
        ex.to_excel(w, sheet_name="Flagged rows", index=True)
    return out.getvalue()


def merge_fuzzy(df, fz):
    d, n = df.copy(), 0
    for _, r in fz.iterrows():
        m = d[r["Column"]].astype(str) == r["Merge"]
        n += int(m.sum())
        d.loc[m, r["Column"]] = r["Keep"]
    return d, n


def sheet_overview(data, names):
    rows = []
    for nm in names:
        try:
            class M(io.BytesIO):
                pass
            f = M(data)
            f.name = "x.xlsx"
            raw = read_any(f, nm).head(3000)
            d, _, _ = auto_clean(raw, False, False)
            u = understand(d)
            rows.append({"Sheet": nm, "Rows": len(raw), "Columns": raw.shape[1], "Looks like": u["type"], "Confidence": f"{u['conf']}%", "Validation issues": len(u["issues"])})
        except Exception as e:
            rows.append({"Sheet": nm, "Rows": 0, "Columns": 0, "Looks like": f"unreadable ({e})", "Confidence": "-", "Validation issues": 0})
    return pd.DataFrame(rows)



def _norm_ref(x):
    return x.astype(str).str.lower().str.replace(r"[^a-z0-9]", "", regex=True).where(x.notna(), "")


def _greedy(c):
    return c.sort_values("score").drop_duplicates("ia").drop_duplicates("ib")


def reconcile(A, B, ac, bc, tol=0.0, days=3, thr=0.8, amount_only=False):
    """Match two lists (bank vs ledger, eTIMS vs sales...). ac/bc = {'ref','amt','date','name'} column names (ref/date/name optional).
    Pass 1 reference (+ amount check) -> Pass 2 amount + date window -> Pass 3 amount + similar name. One-to-one."""
    A, B = A.copy().reset_index(drop=True), B.copy().reset_index(drop=True)
    A["__ia"], B["__ib"] = range(len(A)), range(len(B))
    A["__amt"] = pd.to_numeric(A[ac["amt"]], errors="coerce")
    B["__amt"] = pd.to_numeric(B[bc["amt"]], errors="coerce")
    A["__c"], B["__c"] = (A["__amt"].round(2) * 100).round().astype("Int64"), (B["__amt"].round(2) * 100).round().astype("Int64")
    pairs = []
    usedA, usedB = set(), set()

    def take(df_, basis):
        for ia, ib in zip(df_["ia"], df_["ib"]):
            pairs.append((int(ia), int(ib), basis))
            usedA.add(int(ia)); usedB.add(int(ib))
    if ac.get("ref") and bc.get("ref"):
        A["__r"], B["__r"] = _norm_ref(A[ac["ref"]]), _norm_ref(B[bc["ref"]])
        Ar, Br = A[A["__r"] != ""][["__r", "__ia"]].copy(), B[B["__r"] != ""][["__r", "__ib"]].copy()
        Ar["__n"], Br["__n"] = Ar.groupby("__r").cumcount(), Br.groupby("__r").cumcount()
        m = Ar.merge(Br, on=["__r", "__n"]).rename(columns={"__ia": "ia", "__ib": "ib"})
        take(m, "Reference")
    remA = A[~A["__ia"].isin(usedA) & A["__amt"].notna()]
    remB = B[~B["__ib"].isin(usedB) & B["__amt"].notna()]
    if ac.get("date") and bc.get("date") and (len(remA) and len(remB)):
        a_ = remA[["__ia", "__c", ac["date"]]].rename(columns={"__ia": "ia", ac["date"]: "da"})
        b_ = remB[["__ib", "__c", bc["date"]]].rename(columns={"__ib": "ib", bc["date"]: "db"})
        cand = a_.merge(b_, on="__c")
        cand["score"] = (pd.to_datetime(cand["da"], errors="coerce") - pd.to_datetime(cand["db"], errors="coerce")).abs().dt.days
        cand = cand[cand["score"] <= days]
        take(_greedy(cand), "Amount + date")
    elif amount_only and len(remA) and len(remB):
        cand = remA[["__ia", "__c"]].rename(columns={"__ia": "ia"}).merge(remB[["__ib", "__c"]].rename(columns={"__ib": "ib"}), on="__c")
        cand["score"] = 0
        take(_greedy(cand), "Amount only")
    remA = A[~A["__ia"].isin(usedA) & A["__amt"].notna()]
    remB = B[~B["__ib"].isin(usedB) & B["__amt"].notna()]
    if ac.get("name") and bc.get("name") and len(remA) and len(remB):
        a_ = remA[["__ia", "__c", ac["name"]]].rename(columns={"__ia": "ia", ac["name"]: "na"})
        b_ = remB[["__ib", "__c", bc["name"]]].rename(columns={"__ib": "ib", bc["name"]: "nb"})
        cand = a_.merge(b_, on="__c").head(300000)
        cand["sim"] = [difflib.SequenceMatcher(None, str(x).lower(), str(y).lower()).ratio() for x, y in zip(cand["na"], cand["nb"])]
        cand = cand[cand["sim"] >= thr].assign(score=lambda d_: 1 - d_["sim"])
        take(_greedy(cand), "Amount + similar name")
    # ---- build outputs ----
    rows = []
    for ia, ib, how in pairs:
        ra, rb = A.iloc[ia], B.iloc[ib]
        diff = (ra["__amt"] - rb["__amt"]) if pd.notna(ra["__amt"]) and pd.notna(rb["__amt"]) else np.nan
        stat = "Amount difference" if (how == "Reference" and pd.notna(diff) and abs(diff) > tol) else "Matched"
        row = {"Status": stat, "Matched by": how}
        for p, r_, cm in (("A", ra, ac), ("B", rb, bc)):
            for k, lab in (("ref", "Reference"), ("date", "Date"), ("name", "Name")):
                if cm.get(k):
                    row[f"{p} {lab}"] = r_[cm[k]]
            row[f"{p} Amount"] = r_["__amt"]
        row["Difference (A-B)"] = diff
        rows.append(row)
    paired = pd.DataFrame(rows)
    a_only = A[~A["__ia"].isin(usedA)].drop(columns=[c for c in A.columns if c.startswith("__")])
    b_only = B[~B["__ib"].isin(usedB)].drop(columns=[c for c in B.columns if c.startswith("__")])
    ok = paired[paired["Status"] == "Matched"] if len(paired) else paired
    dif = paired[paired["Status"] == "Amount difference"] if len(paired) else paired
    sA, sB = float(A["__amt"].sum()), float(B["__amt"].sum())
    ao, bo = float(pd.to_numeric(A.loc[~A["__ia"].isin(usedA), "__amt"]).sum()), float(pd.to_numeric(B.loc[~B["__ib"].isin(usedB), "__amt"]).sum())
    pd_ = float(paired["Difference (A-B)"].sum()) if len(paired) else 0.0
    stmt = pd.DataFrame([["Total per file A", sA], ["Add/less: paired items whose amounts differ (A minus B)", -pd_], ["Less: items in A with no match in B", -ao],
                         ["Add: items in B with no match in A", bo], ["= Total per file B", sA - pd_ - ao + bo], ["Actual total per file B", sB], ["Unexplained difference", round(sA - pd_ - ao + bo - sB, 2)]],
                        columns=["Reconciliation statement", "Amount"])
    summ = {"pairs": len(paired), "matched": len(ok), "diff": len(dif), "a_only": len(a_only), "b_only": len(b_only), "sA": sA, "sB": sB, "ao": ao, "bo": bo,
            "matched_val": float(ok["A Amount"].sum()) if len(ok) else 0.0, "diff_val": float(dif["Difference (A-B)"].sum()) if len(dif) else 0.0,
            "rate": len(paired) / max(len(A), len(B), 1) * 100}
    return {"paired": paired, "matched": ok, "diff": dif, "a_only": a_only, "b_only": b_only, "stmt": stmt, "sum": summ}


def recon_xlsx(R):
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        R["stmt"].to_excel(w, sheet_name="Statement", index=False)
        R["matched"].to_excel(w, sheet_name="Matched", index=False)
        R["diff"].to_excel(w, sheet_name="Amount differences", index=False)
        R["a_only"].to_excel(w, sheet_name="In A only", index=False)
        R["b_only"].to_excel(w, sheet_name="In B only", index=False)
    return out.getvalue()



import json, hashlib, hmac


def fingerprint(df):
    return hashlib.sha256(pd.util.hash_pandas_object(df, index=False).values.tobytes()).hexdigest()[:16].upper()


def audit(user, action, detail=""):
    """Append-only activity log next to west.py."""
    try:
        import csv
        p = os.path.join(_script_dir(), "audit_log.csv")
        new = not os.path.exists(p)
        with open(p, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["timestamp", "user", "action", "detail"])
            w.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user, action, str(detail)[:300]])
    except Exception:
        pass


def date_order(sample):
    m = sample.str.extract(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.]\d{2,4}")
    if m.isna().all().all():
        return True, None
    a, b = pd.to_numeric(m[0], errors="coerce"), pd.to_numeric(m[1], errors="coerce")
    if (a > 12).any():
        return True, None
    if (b > 12).any():
        return False, "Month-first (US style) dates detected and read accordingly."
    return True, "Every date is ambiguous (day and month both 12 or less). Read as day/month/year (Kenyan style); verify if the source uses month first."


def mask_pii(df, roles):
    d = df.copy()
    for c, (r, _, _) in roles.items():
        if c not in d:
            continue
        x = d[c]
        if r == "email":
            d[c] = x.astype(str).str.replace(r"^(.).*(@.*)$", r"\1***\2", regex=True).where(x.notna())
        elif r == "phone":
            d[c] = x.astype(str).str.replace(r"\D", "", regex=True).map(lambda v: "*" * max(len(v) - 3, 0) + v[-3:]).where(x.notna())
        elif r == "kra_pin":
            d[c] = x.astype(str).str.replace(r"^(.).*(.)$", r"\1*********\2", regex=True).where(x.notna())
        elif r == "name":
            codes, _u = pd.factorize(x)
            d[c] = pd.Series([f"Name {i + 1:03d}" if i >= 0 else None for i in codes], index=d.index)
    return d


def quality_dims(raw, df, U):
    comp = 100 * (1 - raw.isna().mean().mean())
    uniq = 100 * (1 - raw.duplicated().mean())
    flagged = set()
    for _, idx in U["flags"]:
        flagged.update(list(idx))
    valid = 100 * (1 - len(flagged) / max(len(df), 1))
    fz = U["fuzzy"]
    cons = 100 * (1 - min(1, (int(fz["Rows"].sum()) if len(fz) else 0) / max(len(df), 1)))
    return {"Completeness": comp, "Uniqueness": uniq, "Validity": valid, "Consistency": cons, "overall": (comp + uniq + valid + cons) / 4}


def ai_ask(key, question, facts):
    body = json.dumps({"model": "claude-sonnet-5-5", "max_tokens": 900, "messages": [{"role": "user", "content":
        "Answer the question using ONLY these summary facts about a dataset. If the facts are not enough, say exactly what extra analysis is needed. Plain English, no markdown symbols.\n\nFACTS:\n" + facts + "\n\nQUESTION: " + question}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=60).read())
    return re.sub(r"[#*_`]", "", "".join(b.get("text", "") for b in r["content"])).strip()



# ===================== AUTOPILOT ANALYST =====================
def _rl(U, c):
    return U["roles"].get(c, ("measure",))[0]


def _agg_for(U, c):
    return "sum" if _rl(U, c) in ("money", "quantity") else "mean"


def _eta_label(e):
    return "negligible" if e < .01 else "small" if e < .06 else "medium" if e < .14 else "large"


def _V_label(v):
    return "negligible" if v < .1 else "small" if v < .3 else "medium" if v < .5 else "large"


def _spec(kind, data, x, y, title, horizontal=False):
    return {"kind": kind, "data": data, "x": x, "y": y, "title": title, "h": horizontal}


def build_questions(df, U):
    usable = ("money", "quantity", "measure", "age", "percentage")
    nums = _ord([c for c in df.columns if col_kind(df[c]) == "numeric" and _rl(U, c) in usable], U["prio"])
    cats = _ord([c for c in df.columns if col_kind(df[c]) == "category" and _rl(U, c) not in ("email", "phone", "kra_pin", "identifier") and 2 <= df[c].nunique() <= 30], U["prio"])
    qs = []
    for n in nums[:4]:
        for c in cats[:3]:
            w = "total" if _agg_for(U, n) == "sum" else "average"
            qs.append({"id": f"group|{c}|{n}", "theme": "Compare groups", "kind": "group", "cat": c, "num": n, "title": f"Which {c} has the highest and lowest {w} {n}, and is the difference real?"})
    mm = [c for c in nums if _rl(U, c) in ("money", "quantity")]
    for n in mm[:1]:
        for c in cats[:2]:
            qs.append({"id": f"pareto|{c}|{n}", "theme": "Concentration and risk", "kind": "pareto", "cat": c, "num": n, "title": f"How concentrated is {n} across {c}? (80/20 test)"})
    tn = [c for c in nums if _rl(U, c) != "age"]
    for d in U["dates"][:1]:
        for n in tn[:2]:
            if df[d].dt.to_period("M").nunique() >= 4:
                qs.append({"id": f"trend|{d}|{n}", "theme": "Trends over time", "kind": "trend", "date": d, "num": n, "title": f"How is {n} changing over time, and is there seasonality?"})
    for n in tn[:2]:
        if len(nums) >= 2:
            qs.append({"id": f"corr|{n}", "theme": "Relationships and drivers", "kind": "corr", "num": n, "title": f"Which numeric columns move together with {n}?"})
        if len(df) >= 60 and (len(nums) >= 2 or cats):
            qs.append({"id": f"drivers|{n}", "theme": "Relationships and drivers", "kind": "drivers", "num": n, "title": f"What drives {n}? (predictive driver analysis)"})
    pairs = [(a, b) for i, a in enumerate(cats[:4]) for b in cats[:4][i + 1:] if df[a].nunique() <= 12 and df[b].nunique() <= 12][:3]
    for a, b in pairs:
        qs.append({"id": f"assoc|{a}|{b}", "theme": "Relationships and drivers", "kind": "assoc", "a": a, "b": b, "title": f"Is {a} associated with {b}?"})
    if len(nums) >= 3 and len(df) >= 60:
        qs.append({"id": "segments", "theme": "Segments", "kind": "segments", "title": "Are there natural segments (groups of similar records)?"})
    for n in nums[:3]:
        qs.append({"id": f"dist|{n}", "theme": "Data shape and outliers", "kind": "dist", "num": n, "title": f"What is typical for {n}, and how is it spread?"})
    if nums:
        qs.append({"id": "outliers", "theme": "Data shape and outliers", "kind": "outliers", "title": "Which individual records are most unusual?"})
    return qs


def _res(answer, sowhat, table=None, chart=None, score=0.0, recs=None, method=""):
    return {"answer": answer, "sowhat": sowhat, "table": table, "chart": chart, "score": float(score), "recs": recs or [], "method": method}


def _q_group(df, U, q):
    from scipy import stats
    c, n = q["cat"], q["num"]
    agg = _agg_for(U, n)
    d = df[[c, n]].dropna()
    g = d.groupby(c)[n].agg(["count", "mean", "median", "sum"])
    g = g[g["count"] >= 5]
    if len(g) < 2:
        raise ValueError("fewer than two groups with at least 5 records")
    g = g.sort_values(agg, ascending=False)
    arrs = [d.loc[d[c] == k, n].values for k in g.index]
    if len(arrs) == 2:
        p, test = stats.mannwhitneyu(arrs[0], arrs[1]).pvalue, "Mann-Whitney U test"
    else:
        p, test = stats.kruskal(*arrs).pvalue, "Kruskal-Wallis test"
    allv = np.concatenate(arrs)
    gm = allv.mean()
    sst = ((allv - gm) ** 2).sum()
    eta = sum(len(a) * (a.mean() - gm) ** 2 for a in arrs) / sst if sst > 0 else 0.0
    padj = min(1.0, p * q.get("m", 1))
    w = "total" if agg == "sum" else "average"
    top, bot = g.index[0], g.index[-1]
    sig = padj < .05
    ans = (f"{c} = '{top}' has the highest {w} {n} ({_f(g[agg].iloc[0])}) and '{bot}' the lowest ({_f(g[agg].iloc[-1])}). "
           f"Group differences in {n} are {_eta_label(eta)} (eta-squared {eta:.2f}); {test} p={p:.3g}, adjusted for {q.get('m', 1)} comparisons p={padj:.3g}, so the difference is "
           f"{'statistically reliable' if sig else 'not reliably different from chance'}.")
    if agg == "sum":
        ans += " Totals also reflect group size; the test uses per-record values."
    recs = []
    if sig and eta >= .06:
        sw = f"Act on this: the gap is reliable and large enough to matter. Find out what drives '{top}' and whether it can be replicated for '{bot}'."
        recs.append(("High", f"Investigate and replicate what makes {c} = '{top}' different on {n} compared with '{bot}'.", f"{test} adjusted p={padj:.3g}, effect {_eta_label(eta)}"))
    elif sig:
        sw = "The difference is real but small; it should not drive major decisions on its own."
        recs.append(("Low", f"Monitor {n} differences between {c} groups; the effect is small.", f"adjusted p={padj:.3g}, effect {_eta_label(eta)}"))
    else:
        sw = "No evidence of a real difference once chance is allowed for; do not act on this gap."
    t = g.reset_index().rename(columns={c: c, "count": "Records", "mean": "Average", "median": "Median", "sum": "Total"})
    return _res(ans, sw, t, _spec("bar", t, c, "Total" if agg == "sum" else "Average", f"{w.title()} {n} by {c}", True), (2 if sig else 0) + eta * 10, recs, f"{test}; effect size eta-squared; Bonferroni adjustment")


def _q_pareto(df, U, q):
    c, n = q["cat"], q["num"]
    g = df.groupby(c)[n].sum().sort_values(ascending=False)
    tot = g.sum()
    if tot <= 0 or len(g) < 3:
        raise ValueError("not enough positive totals")
    share = g / tot
    k = max(1, int(round(len(g) * .2)))
    t20 = float(share.iloc[:k].sum())
    s1 = float(share.iloc[0])
    ans = f"'{g.index[0]}' contributes {s1*100:.1f}% of total {n}. The top {k} of {len(g)} {c} groups (the top 20%) account for {t20*100:.0f}% of the total."
    recs = []
    if s1 > .3 or t20 > .8:
        sw = "High concentration: results depend heavily on a few groups. Losing one would hit the total, so protect these and build alternatives."
        recs.append(("High" if s1 > .5 else "Medium", f"Reduce dependence on {c} = '{g.index[0]}' ({s1*100:.0f}% of {n}) and protect the top groups.", f"top 20% = {t20*100:.0f}% of total"))
    else:
        sw = "Contribution is spread fairly evenly, so dependence risk is low."
    t = pd.DataFrame({c: g.index[:10], "Total": g.values[:10], "Share %": (share.values[:10] * 100).round(1), "Cumulative %": (share.cumsum().values[:10] * 100).round(1)})
    return _res(ans, sw, t, _spec("bar", t, c, "Total", f"Top {c} by {n}", True), s1 * 3 + t20, recs, "Pareto (80/20) analysis")


def _q_trend(df, U, q):
    from scipy import stats
    dc, n = q["date"], q["num"]
    agg = _agg_for(U, n)
    d = df.dropna(subset=[dc, n])
    t = d.groupby(d[dc].dt.to_period("M"))[n].agg(agg)
    if len(t) < 4:
        raise ValueError("fewer than 4 months of data")
    t.index = t.index.to_timestamp()
    lr = stats.linregress(np.arange(len(t)), t.values)
    ch = (t.iloc[-1] - t.iloc[0]) / abs(t.iloc[0]) * 100 if t.iloc[0] else float("nan")
    pm = lr.slope / abs(t.mean()) * 100 if t.mean() else 0
    sig = lr.pvalue < .05
    w = "monthly total" if agg == "sum" else "monthly average"
    ans = f"The {w} of {n} moved from {_f(t.iloc[0])} ({t.index[0]:%b %Y}) to {_f(t.iloc[-1])} ({t.index[-1]:%b %Y}), {ch:+.0f}% overall. The fitted trend is {'upward' if lr.slope > 0 else 'downward'} by about {abs(pm):.1f}% of the average per month and is {'statistically reliable' if sig else 'not statistically reliable'} (p={lr.pvalue:.3g}). Peak {t.idxmax():%b %Y}, lowest {t.idxmin():%b %Y}."
    if len(t) >= 18:
        moy = t.groupby(t.index.month).mean()
        ans += f" Seasonally, month {moy.idxmax()} is typically strongest and month {moy.idxmin()} weakest."
    if agg == "sum":
        ans += " The first and last months may be partial."
    recs = []
    if sig:
        sw = ("Growth is sustained: plan capacity and targets accordingly." if lr.slope > 0 else "Decline is sustained, not noise: investigate causes and set a recovery plan.")
        recs.append(("High" if lr.slope < 0 else "Medium", f"{'Plan for continued growth' if lr.slope > 0 else 'Investigate and reverse the decline'} in {n} (about {abs(pm):.1f}% per month).", f"trend p={lr.pvalue:.3g}"))
    else:
        sw = "No reliable trend; month-to-month movements look like normal variation."
    tt = t.reset_index()
    tt.columns = [dc, n]
    return _res(ans, sw, tt, _spec("line", tt, dc, n, f"{w.title()} of {n}"), (1.5 if sig else 0) + abs(pm) / 10, recs, "Linear regression of monthly values")


def _numcols(df, U):
    return _ord([c for c in df.columns if col_kind(df[c]) == "numeric" and _rl(U, c) in ("money", "quantity", "measure", "age", "percentage")], U["prio"])


def _q_corr(df, U, q):
    from scipy import stats
    n = q["num"]
    rows = []
    for o in _numcols(df, U):
        if o == n:
            continue
        d = df[[n, o]].dropna()
        if len(d) >= 20 and d[n].nunique() > 1 and d[o].nunique() > 1:
            r, p = stats.spearmanr(d[n], d[o])
            rows.append((o, r, len(d), p))
    if not rows:
        raise ValueError("no comparable numeric columns")
    t = pd.DataFrame(rows, columns=["Column", "Spearman rho", "Records", "p"]).assign(**{"Adjusted p": lambda x: (x["p"] * len(x)).clip(upper=1)}).sort_values("Spearman rho", key=abs, ascending=False)
    top = t.iloc[0]
    st_ = "negligible" if abs(top["Spearman rho"]) < .1 else "weak" if abs(top["Spearman rho"]) < .3 else "moderate" if abs(top["Spearman rho"]) < .5 else "strong"
    sig = top["Adjusted p"] < .05
    ans = f"{n} is most closely related to {top['Column']} (rho {top['Spearman rho']:+.2f}, {st_}, {'statistically reliable' if sig else 'not reliable after adjustment'}). " + "; ".join(f"{r['Column']} {r['Spearman rho']:+.2f}" for _, r in t.head(4).iterrows()) + "."
    recs = []
    if sig and abs(top["Spearman rho"]) >= .3:
        sw = f"{n} and {top['Column']} move {'together' if top['Spearman rho'] > 0 else 'in opposite directions'}. This shows association, not cause; test it before acting."
        recs.append(("Medium", f"Test whether changing {top['Column']} changes {n}; they are {st_}ly linked (rho {top['Spearman rho']:+.2f}).", f"adjusted p={top['Adjusted p']:.3g}"))
    else:
        sw = "No strong linear-style relationship found; other factors are likely at work."
    t2 = t.round(4)
    return _res(ans, sw, t2, _spec("bar", t2, "Column", "Spearman rho", f"Correlation with {n}", True), abs(top["Spearman rho"]) * 3 + (1 if sig else 0), recs, "Spearman rank correlation with Bonferroni adjustment")


def _q_drivers(df, U, q):
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.model_selection import cross_val_score
    n = q["num"]
    d = df.dropna(subset=[n])
    d = d.sample(5000, random_state=0) if len(d) > 5000 else d
    feats, names = [], []
    for c in d.columns:
        if c == n or _rl(U, c) in ("email", "phone", "kra_pin", "identifier", "name", "text"):
            continue
        k = col_kind(d[c])
        if k == "numeric":
            feats.append(d[c].fillna(d[c].median()).astype(float).rename(c)); names.append(c)
        elif k in ("category", "boolean") and 2 <= d[c].nunique() <= 15:
            dm = pd.get_dummies(d[c].astype(str), prefix=c).astype(float)
            for col in dm:
                feats.append(dm[col]); names.append(c)
    if len(set(names)) < 1:
        raise ValueError("no usable predictor columns")
    X = pd.concat(feats, axis=1)
    X.columns = [f"{i}" for i in range(X.shape[1])]
    rf = RandomForestRegressor(n_estimators=120, max_depth=8, min_samples_leaf=5, random_state=0, n_jobs=-1)
    r2 = float(cross_val_score(rf, X, d[n].astype(float), cv=5, scoring="r2").mean())
    rf.fit(X, d[n].astype(float))
    imp = pd.Series(rf.feature_importances_, index=names).groupby(level=0).sum().sort_values(ascending=False)
    t = pd.DataFrame({"Factor": imp.index, "Importance %": (imp.values * 100).round(1)})
    if r2 < .1:
        ans = f"The other columns do not reliably predict {n} (cross-validated R-squared {r2:.2f}). Its main drivers are probably not recorded in this dataset."
        sw = "Do not build decisions on predicting this measure from the available columns; collect more relevant data."
        recs = [("Medium", f"Collect additional data on what influences {n}; existing columns explain little of it.", f"cross-validated R-squared {r2:.2f}")]
    else:
        ans = f"Together the other columns explain about {max(r2, 0)*100:.0f}% of the variation in {n} (cross-validated R-squared {r2:.2f}). Biggest factors: " + "; ".join(f"{a} ({b:.0f}%)" for a, b in zip(t["Factor"].head(4), t["Importance %"].head(4))) + "."
        sw = f"Focus improvement effort on the leading factors ({', '.join(t['Factor'].head(2))}). Importance shows association with {n}, not proven cause."
        recs = [("High" if r2 >= .3 else "Medium", f"Prioritise {', '.join(t['Factor'].head(2))} when trying to influence {n}.", f"model explains {r2*100:.0f}% (cross-validated)")]
    return _res(ans, sw, t, _spec("bar", t.head(10), "Factor", "Importance %", f"What drives {n}", True), max(r2, 0) * 4, recs, "Random Forest, 5-fold cross-validated R-squared, grouped feature importance")


def _q_assoc(df, U, q):
    from scipy import stats
    a, b = q["a"], q["b"]
    ct = pd.crosstab(df[a], df[b])
    if ct.shape[0] < 2 or ct.shape[1] < 2 or ct.values.sum() < 30:
        raise ValueError("too little data for a cross-tabulation test")
    chi, p, _, exp = stats.chi2_contingency(ct)
    n_ = ct.values.sum()
    v = float(np.sqrt(chi / (n_ * (min(ct.shape) - 1))))
    res = (ct - exp) / np.sqrt(exp)
    (ra, cb) = res.stack().idxmax()
    sig = p < .05
    ans = f"{a} and {b} are {'associated' if sig else 'not reliably associated'} (chi-square p={p:.3g}, Cramer's V {v:.2f}, {_V_label(v)}). The most over-represented combination is {a} = '{ra}' with {b} = '{cb}'."
    recs = []
    if sig and v >= .1:
        sw = f"The mix of {b} differs across {a}; tailor actions by {a} rather than treating everyone alike."
        recs.append(("Medium" if v >= .2 else "Low", f"Tailor actions for {a} groups: the {b} mix differs ('{ra}' leans to '{cb}').", f"p={p:.3g}, V={v:.2f}"))
    else:
        sw = "No reliable link; no need to treat these groups differently on this basis."
    t = (ct.div(ct.sum(axis=1), axis=0) * 100).round(1)
    return _res(ans, sw, t.reset_index(), _spec("heat", t, a, b, f"{a} by {b} (% within {a})"), (1 if sig else 0) + v * 5, recs, "Chi-square test of independence; Cramer's V")


def _q_segments(df, U, q):
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score
    cols = _numcols(df, U)[:8]
    d = df[cols].copy()
    d = d.fillna(d.median())
    d = d.sample(20000, random_state=0) if len(d) > 20000 else d
    z = (d - d.mean()) / d.std(ddof=0).replace(0, 1)
    sub = z.sample(min(len(z), 4000), random_state=0)
    best = None
    for k in range(2, 6):
        km = KMeans(n_clusters=k, n_init=5, random_state=0).fit(sub)
        sc = silhouette_score(sub, km.labels_)
        if best is None or sc > best[0]:
            best = (sc, k)
    sc, k = best
    km = KMeans(n_clusters=k, n_init=10, random_state=0).fit(z)
    lab = pd.Series(km.labels_, index=z.index)
    zp = z.groupby(lab).mean()
    sizes = lab.value_counts().sort_index()
    names = []
    for i in zp.index:
        r = zp.loc[i].abs().sort_values(ascending=False).head(2).index
        names.append(f"Segment {i+1}: " + ", ".join(f"{'high' if zp.loc[i, x] > 0 else 'low'} {x}" for x in r))
    tz = zp.copy(); tz.index = names
    prof = d.groupby(lab).mean().round(2); prof.insert(0, "Share %", (sizes / sizes.sum() * 100).round(1)); prof.insert(0, "Segment", names)
    strong = sc >= .25
    ans = f"The records fall into {k} segments (silhouette {sc:.2f}, {'clear' if sc >= .5 else 'moderate' if strong else 'weak'} separation). " + " | ".join(f"{nm} ({sizes[i]/sizes.sum()*100:.0f}%)" for i, nm in zip(sizes.index, names)) + "."
    recs = []
    if strong:
        sw = "The population is not uniform: design different actions per segment instead of one average approach."
        recs.append(("Medium", f"Design differentiated actions for the {k} segments identified ({names[0].split(': ')[1]} etc.).", f"silhouette {sc:.2f}"))
    else:
        sw = "Segments overlap heavily, so treat them as a rough guide only."
    return _res(ans, sw, prof.reset_index(drop=True), _spec("heat", tz.round(2), "Segment", "Variable", "Segment profile (standard deviations from average)"), sc * 3, recs, "K-means clustering on standardised numeric columns; silhouette score picks k")


def _q_dist(df, U, q):
    from scipy import stats
    n = q["num"]
    x = df[n].dropna()
    sk = float(x.skew())
    p = stats.shapiro(x.sample(min(len(x), 5000), random_state=0))[1] if len(x) >= 8 else float("nan")
    q1, q3 = x.quantile(.25), x.quantile(.75)
    fl, lo, hi = outliers_iqr(x)
    shape = "right-skewed (a few very high values)" if sk > 1 else "left-skewed (a few very low values)" if sk < -1 else "roughly symmetric"
    ans = f"Typical {n} is {_f(x.median())} (middle half between {_f(q1)} and {_f(q3)}); the average is {_f(x.mean())}. The distribution is {shape} and {'consistent with a normal curve' if p > .05 else 'not normal'} (Shapiro-Wilk p={p:.2g}). {int(fl.sum())} values ({fl.mean()*100:.1f}%) lie outside {_f(lo)} to {_f(hi)}."
    sw = ("Use the median rather than the average when reporting this measure." if abs(sk) > 1 else "The average is a fair summary of this measure.")
    recs = [("Low", f"Report {n} using the median because the distribution is skewed.", f"skew {sk:.1f}")] if abs(sk) > 1 else []
    return _res(ans, sw, x.describe().round(2).rename("Value").reset_index().rename(columns={"index": "Statistic"}), _spec("hist", x, n, None, f"Distribution of {n}"), abs(sk) / 3, recs, "Descriptive statistics, IQR rule, Shapiro-Wilk test")


def _q_outliers(df, U, q):
    cols = _numcols(df, U)[:8]
    rows = []
    for c in cols:
        x = df[c].dropna()
        med = x.median()
        mad = (x - med).abs().median()
        if mad == 0:
            continue
        mz = 0.6745 * (df[c] - med) / mad
        for i in mz[mz.abs() > 3.5].index:
            rows.append((i, c, df.at[i, c], med, round(float(mz[i]), 1)))
    if not rows:
        return _res("No individual record is extremely unusual on any numeric column (robust z-score above 3.5).", "No records need special review on this basis.", None, None, 0, [], "Modified z-score (median/MAD)")
    t = pd.DataFrame(rows, columns=["Row", "Column", "Value", "Typical (median)", "Robust z"]).assign(a=lambda x: x["Robust z"].abs()).sort_values("a", ascending=False).drop(columns="a").head(15)
    ans = f"{len(set(r[0] for r in rows)):,} records have at least one extremely unusual value (robust z above 3.5). The most extreme: row {t.iloc[0]['Row']} has {t.iloc[0]['Column']} = {_f(t.iloc[0]['Value'])} against a typical {_f(t.iloc[0]['Typical (median)'])}."
    return _res(ans, "Verify these records against source documents before using totals or averages.", t, None, 1.0, [("Medium", f"Verify the {len(set(r[0] for r in rows)):,} extreme records against source documents.", "robust z above 3.5")], "Modified z-score (median/MAD)")


RUN = {"group": _q_group, "pareto": _q_pareto, "trend": _q_trend, "corr": _q_corr, "drivers": _q_drivers, "assoc": _q_assoc, "segments": _q_segments, "dist": _q_dist, "outliers": _q_outliers}


def run_autopilot(df, U, qs):
    out, errs = [], []
    m = max(1, sum(1 for q in qs if q["kind"] == "group"))
    for q in qs:
        try:
            r = RUN[q["kind"]](df, U, dict(q, m=m))
            r.update(id=q["id"], theme=q["theme"], title=q["title"])
            out.append(r)
        except Exception as e:
            errs.append({"Question": q["title"], "Skipped because": str(e)[:160]})
    return out, errs


def integrity(raw, df, log):
    txt = " ".join(log["Action taken"].astype(str)) if len(log) else ""
    cnt = lambda pat: sum(int(x) for x in re.findall(pat, txt))
    rem = cnt(r"Removed (\d+) completely empty rows") + cnt(r"Removed (\d+) exact duplicate rows") + cnt(r"Dropped (\d+) rows") + cnt(r"Removed (\d+) duplicate rows")
    ec = len(re.findall(r"Removed \(column fully empty\)", txt))
    res = [("Row accounting", len(raw) - rem == len(df), f"{len(raw):,} rows read - {rem:,} removed (all logged) = {len(raw) - rem:,}; the app holds {len(df):,}."),
           ("Column accounting", len(df.columns) >= len(raw.columns) - ec, f"{len(raw.columns)} columns read - {ec} empty removed; the app holds {len(df.columns)}."),
           ("No impossible numbers", not any(np.isinf(df[c]).any() for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c])), "No infinite values in any numeric column."),
           ("Every change is logged", len(log) > 0, f"{len(log)} actions in the audit trail.")]
    return res


def decision_sections(AP, errs, integ):
    top = sorted(AP, key=lambda r: -r["score"])[:6]
    first = lambda s_: re.split(r"(?<=[.!?])\s", s_)[0]
    prm = {"High": 0, "Medium": 1, "Low": 2}
    recs, seen = [], set()
    for r in sorted(AP, key=lambda r: -r["score"]):
        for p_, a_, e_ in r["recs"]:
            if a_ not in seen:
                seen.add(a_)
                recs.append((p_, a_, e_))
    recs.sort(key=lambda x: prm[x[0]])
    rt = pd.DataFrame(recs, columns=["Priority", "Recommended action", "Evidence"]) if recs else pd.DataFrame(columns=["Priority", "Recommended action", "Evidence"])
    front = [("Decision summary: what matters most", [f"{r['title']} {first(r['answer'])}" for r in top] or ["No strong findings were detected."], True),
             ("Prioritised recommendations", [f"[{p_}] {a_} (evidence: {e_})" for p_, a_, e_ in recs[:10]] or ["No action is justified by the statistical evidence."], True),
             ("Assurance: integrity checks run on this analysis", [f"{'PASS' if ok else 'REVIEW'}: {c_}. {d_}" for c_, ok, d_ in integ], True)]
    back = [("Analysis by question", [f"{r['title']} {r['answer']} What this means: {r['sowhat']}" for r in AP], True),
            ("Methods and assumptions", sorted({r["method"] for r in AP}) + ["Significance level 5%. Group comparisons are adjusted for the number of comparisons made. Statistical association is not proof of cause."] + ([f"Skipped analyses: {len(errs)} (not enough suitable data)."] if errs else []), True)]
    return front, back, rt


def chart_mpl(spec):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    k, d = spec["kind"], spec["data"]
    f, ax = plt.subplots(figsize=(8, 3.6 if k != "heat" else 4.2))
    if k == "bar":
        d = d.head(12)
        lab = d[spec["x"]].astype(str)
        (ax.barh(lab[::-1], d[spec["y"]].values[::-1], color="#AA8336") if spec["h"] else ax.bar(lab, d[spec["y"]].values, color="#AA8336"))
    elif k == "line":
        ax.plot(d[spec["x"]], d[spec["y"]], color="#002043", marker="o")
    elif k == "hist":
        ax.hist(d.dropna(), bins=25, color="#AA8336")
    elif k == "heat":
        ax.imshow(d.values.astype(float), cmap="YlOrBr", aspect="auto")
        ax.set_xticks(range(d.shape[1])); ax.set_xticklabels([str(c)[:18] for c in d.columns], rotation=40, ha="right", fontsize=7)
        ax.set_yticks(range(d.shape[0])); ax.set_yticklabels([str(c)[:38] for c in d.index], fontsize=7)
        for i in range(d.shape[0]):
            for j in range(d.shape[1]):
                ax.text(j, i, f"{float(d.iat[i, j]):.1f}", ha="center", va="center", fontsize=6)
    if k != "heat":
        ax.spines[["top", "right"]].set_visible(False)
    ax.set_title(spec["title"], color="#002043", fontsize=10)
    b = io.BytesIO()
    f.tight_layout()
    f.savefig(b, format="png", dpi=120)
    plt.close(f)
    return b.getvalue()


def chart_plotly(spec):
    import plotly.express as px
    k, d = spec["kind"], spec["data"]
    cs = ["#16325C", "#AA8336", "#E8C872"]
    if k == "bar":
        d = d.head(12)
        f = px.bar(d, x=spec["y"], y=spec["x"], orientation="h", title=spec["title"], color_discrete_sequence=["#AA8336"]) if spec["h"] else px.bar(d, x=spec["x"], y=spec["y"], title=spec["title"], color_discrete_sequence=["#AA8336"])
        if spec["h"]:
            f.update_layout(yaxis=dict(autorange="reversed"))
    elif k == "line":
        f = px.line(d, x=spec["x"], y=spec["y"], markers=True, title=spec["title"], color_discrete_sequence=["#AA8336"])
    elif k == "hist":
        f = px.histogram(d.to_frame(spec["x"]), x=spec["x"], title=spec["title"], color_discrete_sequence=["#AA8336"])
    else:
        f = px.imshow(d, text_auto=".1f", color_continuous_scale=cs, title=spec["title"], aspect="auto")
    f.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    return f


def pivot_gallery(df, U):
    usable = ("money", "quantity", "measure", "age", "percentage")
    nums = _ord([c for c in df.columns if col_kind(df[c]) == "numeric" and _rl(U, c) in usable], U["prio"])[:4]
    cats = _ord([c for c in df.columns if col_kind(df[c]) in ("category", "boolean") and _rl(U, c) not in ("email", "phone", "kra_pin", "identifier") and 2 <= df[c].nunique() <= 30], U["prio"])[:4]
    out = {}
    for c in cats:
        for n in nums:
            g = df.groupby(c)[n].agg(["count", "mean", "median", "min", "max"])
            if _agg_for(U, n) == "sum":
                g["total"] = df.groupby(c)[n].sum()
            g.columns = [x.title() for x in g.columns]
            g.loc["All records"] = [len(df[n].dropna()), df[n].mean(), df[n].median(), df[n].min(), df[n].max()] + ([df[n].sum()] if "Total" in g.columns else [])
            out[f"{n} by {c}"] = g.sort_values("Mean", ascending=False)
    for i, a in enumerate(cats[:3]):
        for b in cats[:3][i + 1:]:
            out[f"Count of records: {a} x {b}"] = pd.crosstab(df[a], df[b], margins=True, margins_name="All")
    return out


def pivots_xlsx(gal):
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        for i, (k, v) in enumerate(gal.items()):
            v.to_excel(w, sheet_name=f"{i + 1}. {re.sub(r'[^A-Za-z0-9 ]', '', k)}"[:31])
    return out.getvalue()

# ===== END ENGINE =====

# 1. Page Configuration
st.set_page_config(
    page_title="Westminister Consulting | Enterprise Intelligence & Audit Suite",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)
import wc_ui
wc_ui.inject_theme()
wc_ui.show_splash(load_logo(), LOGO_URL)
# Initialize Session State
if "splash_shown" not in st.session_state:
    st.session_state.splash_shown = False
if "df" not in st.session_state:
    st.session_state.df = None
if "df_secondary" not in st.session_state:
    st.session_state.df_secondary = None
for _k, _v in {"raw_df": None, "schema": {}, "clean_log": None, "sig_bytes": None, "sig_time": "", "logo_bytes": None, "lookup_res": None, "pdf": None, "enterprise_pdf_bytes": None, "enterprise_pdf_filename": "Westminister_Enterprise_Audit_Report.pdf", "role_override": {}, "U": None, "prio": []}.items():
    st.session_state.setdefault(_k, _v)
if "signature_image" not in st.session_state:
    st.session_state.signature_image = None
# Sidebar Ingestion
def memo(name, key, fn):
    store = st.session_state.setdefault("_memo", {})
    if store.get(name, (None,))[0] != key:
        store[name] = (key, fn())
    return store[name][1]


def _secret(n):
    try:
        return st.secrets.get(n)
    except Exception:
        return None


_pw = os.environ.get("WEST_PASSWORD") or _secret("WEST_PASSWORD")
if _pw:
    if not st.session_state.get("auth"):
        st.markdown("## Sign in")
        _u = st.text_input("Your name")
        _p = st.text_input("Password", type="password")
        if st.button("Sign in"):
            if _u.strip() and hmac.compare_digest(_p.encode(), str(_pw).encode()):
                st.session_state.auth, st.session_state.user = True, _u.strip()
                audit(_u.strip(), "sign-in")
                st.rerun()
            else:
                st.error("Wrong password or missing name.")
        st.stop()
else:
    st.sidebar.text_input("Your name (recorded in the audit log)", "guest", key="user")
    st.sidebar.caption("No password is set. To require sign-in, set the WEST_PASSWORD environment variable.")
_USER = st.session_state.get("user", "guest")
wc_ui.app_header(st.session_state.logo_bytes or load_logo(), LOGO_URL, _USER)
with st.sidebar.expander("Audit log"):
    try:
        _al = pd.read_csv(os.path.join(_script_dir(), "audit_log.csv"))
        st.dataframe(_al.tail(30), use_container_width=True)
        st.download_button("Download full audit log", _al.to_csv(index=False).encode(), "audit_log.csv", "text/csv", key="al_dl")
    except Exception:
        st.caption("No activity recorded yet.")
st.sidebar.markdown("## Data Ingestion Center")
uploaded_file = st.sidebar.file_uploader(
    "Upload Primary Dataset / Ledger (CSV/XLSX)", type=["csv", "xlsx", "xls"], key="primary"
)
uploaded_file_secondary = st.sidebar.file_uploader(
    "Upload Secondary Dataset (Optional)",
    type=["csv", "xlsx", "xls"],
    key="secondary",
)
_rdir = os.path.join(_script_dir(), "recipes")
try:
    os.makedirs(_rdir, exist_ok=True)
    _saved = sorted(f_[:-5] for f_ in os.listdir(_rdir) if f_.endswith(".json"))
except Exception:
    _saved = []
st.sidebar.markdown("## Client Recipe")
_pick = st.sidebar.selectbox("Load saved recipe", ["(none)"] + _saved)
if _pick != "(none)" and st.session_state.get("_rloaded") != _pick:
    try:
        _rc = json.load(open(os.path.join(_rdir, _pick + ".json"), encoding="utf-8"))
        st.session_state.opt_fill, st.session_state.opt_dupe = _rc.get("opt_fill", True), _rc.get("opt_dupe", True)
        st.session_state.role_override = _rc.get("role_override", {})
        st.session_state.client_in, st.session_state.rep_title, st.session_state.signer_n = _rc.get("client", ""), _rc.get("rep_title", "Data Review & Management Report"), _rc.get("signer", "")
        st.session_state.mask_on = _rc.get("mask_on", False)
        st.session_state._rloaded = _pick
        audit(_USER, "recipe loaded", _pick)
    except Exception as e:
        st.sidebar.error(f"Recipe could not be loaded: {e}")
st.sidebar.markdown("## Smart Cleaning Options")
opt_fill = st.sidebar.checkbox("Auto-fill missing values (per column type)", True, key="opt_fill")
opt_dupe = st.sidebar.checkbox("Remove duplicate rows", True, key="opt_dupe")
st.sidebar.checkbox("Mask personal data (emails, phones, PINs, names) in reports and exceptions", False, key="mask_on")
st.sidebar.text_input("Anthropic API key (optional, for AI commentary and questions)", type="password", key="ai_key")
st.sidebar.markdown("## Report Branding")
client_name = st.sidebar.text_input("Client name", "", key="client_in")
if st.sidebar.button("Save these settings as a client recipe"):
    try:
        json.dump({"opt_fill": opt_fill, "opt_dupe": opt_dupe, "role_override": st.session_state.role_override, "client": client_name, "rep_title": st.session_state.get("rep_title", ""),
                   "signer": st.session_state.get("signer_n", ""), "mask_on": bool(st.session_state.get("mask_on"))},
                  open(os.path.join(_rdir, (re.sub(r"[^A-Za-z0-9_-]", "_", client_name) or "default") + ".json"), "w", encoding="utf-8"))
        st.sidebar.success("Recipe saved. Load it next time from the list above.")
        audit(_USER, "recipe saved", client_name)
    except Exception as e:
        st.sidebar.error(f"Could not save: {e}")
logo_up = st.sidebar.file_uploader("Logo for PDF (optional)", type=["png", "jpg", "jpeg"], key="logo_up")
if logo_up is not None:
    st.session_state.logo_bytes = logo_up.getvalue()
    try:
        open(os.path.join(_script_dir(), "logo.png"), "wb").write(logo_up.getvalue())
    except Exception:
        pass
elif st.session_state.logo_bytes is None:
    st.session_state.logo_bytes = load_logo()
if st.session_state.logo_bytes:
    st.sidebar.success("Logo loaded for PDF reports")
else:
    st.sidebar.warning("Logo not found online. Upload it above once; it is remembered next time.")
_sheets, _sheet = [], None
if uploaded_file is not None and uploaded_file.name.lower().endswith((".xlsx", ".xlsm", ".xls")):
    try:
        _upload_bytes = uploaded_file.getvalue()
        _sheets = _cached_sheet_names(_upload_bytes)
        _sheet = st.sidebar.selectbox("Sheet to analyse", _sheets) if len(_sheets) > 1 else _sheets[0]
    except Exception:
        _sheets, _sheet = [], None
_pk = (getattr(uploaded_file, "name", None), getattr(uploaded_file, "size", None), opt_fill, opt_dupe, _sheet)
if uploaded_file is not None and st.session_state.get("_pk") != _pk:
    try:
        with st.spinner(f"Loading {uploaded_file.name}… first load may take a little time; repeat reruns use cached results."):
            _upload_bytes = uploaded_file.getvalue()
            _raw, _df, _log, _sc = _cached_load_and_clean(
                _upload_bytes, uploaded_file.name, _sheet, opt_fill, opt_dupe
            )
            if _raw.empty:
                raise ValueError("No data rows were found. Check that the selected worksheet contains a header row and data.")
            st.session_state.raw_df, st.session_state.df, st.session_state.clean_log, st.session_state.schema = _raw, _df, _log, _sc
            st.session_state._pk = _pk
            st.session_state._run_autopilot = False
            audit(_USER, "file loaded", f"{uploaded_file.name} | {len(_df):,} rows after cleaning")
        st.sidebar.success(f"Loaded {uploaded_file.name}: {len(_df):,} rows × {len(_df.columns):,} columns.")
    except Exception as e:
        st.sidebar.error(f"Error loading {uploaded_file.name}: {type(e).__name__}: {e}")
        st.sidebar.info("For .xlsx files, ensure openpyxl is installed: python -m pip install openpyxl")
_sk = (getattr(uploaded_file_secondary, "name", None), getattr(uploaded_file_secondary, "size", None))
if uploaded_file_secondary is not None and st.session_state.get("_sk") != _sk:
    try:
        _s2, _, _ = auto_clean(read_any(uploaded_file_secondary), False, False)
        st.session_state.df_secondary = _s2
        st.session_state._sk = _sk
    except Exception as e:
        st.sidebar.error(f"Error loading secondary file: {e}")
# ================= FIRST SCREEN: FULL DATASET VIEW =================
# Show the uploaded dataset before running the deeper analytics modules.
# Large workbooks are paginated so all rows remain accessible without sending
# hundreds of thousands of rows to the browser in one huge table payload.
if st.session_state.get("df") is not None:
    with st.expander("Uploaded data (every row, paged)", expanded=False):
        st.caption(
            "Your dataset is shown here first. Use the page selector to inspect every row; "
            "all columns are retained. Pagination keeps large Excel workbooks responsive."
        )
        _view_options = ["Original uploaded data", "Cleaned data"]
        _view_choice = st.radio(
            "Choose which version to display",
            _view_options,
            horizontal=True,
            key="full_dataset_view_choice",
        )
        _display_df = (
            st.session_state.raw_df
            if _view_choice == "Original uploaded data" and st.session_state.raw_df is not None
            else st.session_state.df
        )
        _total_rows, _total_cols = _display_df.shape
        _m1, _m2, _m3 = st.columns(3)
        _m1.metric("Total rows", f"{_total_rows:,}")
        _m2.metric("Total columns", f"{_total_cols:,}")
        _m3.metric("Current view", "Original" if _view_choice == "Original uploaded data" else "Cleaned")
        _page_size = st.selectbox(
            "Rows per page",
            options=[250, 500, 1000, 2500, 5000],
            index=2,
            key="full_dataset_page_size",
            help="Choose a larger page size to inspect more records at once."
        )
        _page_count = max(1, (_total_rows + _page_size - 1) // _page_size)
        _page_options = list(range(1, _page_count + 1))
        _page_num = st.selectbox(
            f"Page (of {_page_count:,})",
            options=_page_options,
            index=0,
            format_func=lambda n: f"Page {n:,} — rows {(n - 1) * _page_size + 1:,}–{min(n * _page_size, _total_rows):,}",
            key="full_dataset_page_number",
        )
        _start = (_page_num - 1) * _page_size
        _stop = min(_start + _page_size, _total_rows)
        st.dataframe(
            _display_df.iloc[_start:_stop],
            use_container_width=True,
            height=600,
            hide_index=True,
        )
        st.caption(
            f"Displaying rows {_start + 1:,}–{_stop:,} of {_total_rows:,}. "
            "Change the page above to access the rest of the dataset."
        )
        if st.checkbox("Show column details", key="wc_show_details"):
            _details = pd.DataFrame({
                "Column": [str(c) for c in _display_df.columns],
                "Data type": [str(_display_df[c].dtype) for c in _display_df.columns],
                "Non-empty values": [int(_display_df[c].notna().sum()) for c in _display_df.columns],
                "Missing values": [int(_display_df[c].isna().sum()) for c in _display_df.columns],
            })
            st.dataframe(_details, use_container_width=True, hide_index=True)

def get_col_index(cols, keywords):
    for idx, col in enumerate(cols):
        for kw in keywords:
            if kw in str(col).lower():
                return idx
    return 0
# Main Application Tabs
if st.session_state.df is not None:
    df = st.session_state.df
    cols = df.columns.tolist()
    numeric_cols = [c for c in cols if pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c])]
    string_cols = [c for c in cols if not pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_datetime64_any_dtype(df[c])]
    # Cheap dataset identity: do NOT hash every cell on every Streamlit rerun.
    # Online Retail has hundreds of thousands of rows; full-frame hashing made
    # every widget interaction feel like the app was loading again.
    _dk = (st.session_state.get("_pk"), id(df), df.shape, tuple(df.columns), len(st.session_state.clean_log) if st.session_state.clean_log is not None else 0)
    if st.session_state.clean_log is not None:
        st.sidebar.markdown("## Cleaned File")
        st.sidebar.download_button("Download cleaned Excel", memo("xl_sb", (_dk, len(st.session_state.clean_log)), lambda: to_excel(df, st.session_state.clean_log, auto_insights(df, kinds(df)), kinds(df))), "Westminister_Clean_Data.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="sb_x")
        st.sidebar.download_button("Download cleaned CSV", memo("csv_sb", _dk, lambda: df.to_csv(index=False).encode()), "clean_data.csv", "text/csv", key="sb_c")
    
    tab_guide, tab_auto, tab_under, tab_clean, tab_dash, tab_spivot, tab_lookup, tab_mgmt, tab_adv = st.tabs(
        ["Start Here", "Autopilot", "1. Understand", "2. Clean", "3. Dashboard", "4. Pivot", "5. Lookup & Reconcile", "6. Report & Sign-off", "Advanced Tools"]
    )
    with tab_adv:
        st.caption("Specialist and original tools. Most work is done in tabs 1 to 6.")
        tab1, tab2, tab_granular, tab3, tab4, tab_pivot, tab5, tab6, tab7, tab8, tab_etims, tab_customs, tab9 = st.tabs(
            ["Overview & Merge", "Clean & Transform", "Granular Type Sanitation", "Outlier Analysis", "Exploratory Visuals", "Dynamic Pivot Studio",
             "Advanced Statistics", "Predictive ML Studio", "Automated Profiling", "KRA Tax & Compliance", "eTIMS Reconciliation", "Customs & Tariff Simulator", "Export, Reports & Pen Sign"]
        )
    # ================= NEW SMART MODULES =================
    kd = memo("kinds", _dk, lambda: kinds(df))
    raw_df = st.session_state.raw_df if st.session_state.raw_df is not None else df
    s_nums = [c for c in cols if kd.get(c) == "numeric"]
    s_cats = [c for c in cols if kd.get(c) == "category"]
    s_dates = [c for c in cols if kd.get(c) == "datetime"]
    _uk = (st.session_state.get("_pk"), df.shape, tuple(df.columns), str(st.session_state.role_override))
    if st.session_state.get("_uk") != _uk or st.session_state.U is None:
        st.session_state.U = memo("understand", _uk, lambda: understand(df, st.session_state.role_override))
        st.session_state._uk = _uk
    U = st.session_state.U
    PRIO = U["prio"]
    st.session_state.prio = PRIO
    s_nums, s_cats, s_dates = _ord(s_nums, PRIO), _ord(s_cats, PRIO), _ord(s_dates, PRIO)
    s_insights = memo("insights", (_dk, tuple(PRIO)), lambda: auto_insights(df, dict(sorted(kd.items(), key=lambda kv: PRIO.index(kv[0]) if kv[0] in PRIO else 999))))
    _mask = bool(st.session_state.get("mask_on"))
    df_rep = memo("df_rep", (_dk, _mask, str(U["roles"])), lambda: mask_pii(df, U["roles"]) if _mask else df)
    kd_rep = kinds(df_rep) if _mask else kd
    _nar = memo("nar", (_dk, tuple(PRIO), len(st.session_state.clean_log), _mask), lambda: narrative(df_rep, raw_df, kd_rep, st.session_state.clean_log, PRIO))
    QD = memo("qd", (_dk, str(U["roles"])), lambda: quality_dims(raw_df, df, U))
    _adf = df_rep if _mask else df
    try:
        _qs_all = memo("qs_all", (_dk, str(U["roles"])), lambda: build_questions(_adf, U))
    except Exception:
        _qs_all = []
    _ids = [q["id"] for q in _qs_all]
    _apk = "ap_sel_" + str(abs(hash((_dk, tuple(_ids)))) % 10 ** 8)
    _sel = [i for i in (st.session_state.get(_apk) or _ids) if i in _ids]
    # Heavy statistical analysis is opt-in. This keeps the dashboard and its
    # core features responsive immediately after a large file is loaded.
    if st.session_state.get("_run_autopilot", False):
        try:
            AP, APERR = memo("ap", (_dk, tuple(_sel), tuple(PRIO), _mask), lambda: run_autopilot(_adf, U, [q for q in _qs_all if q["id"] in _sel]))
        except Exception as e:
            AP, APERR = [], [{"Question": "All analyses", "Skipped because": str(e)[:160]}]
    else:
        AP, APERR = [], []
    INTEG = memo("integ", (_dk, len(st.session_state.clean_log)), lambda: integrity(raw_df, df, st.session_state.clean_log))

    def kpi(col, val, lab):
        col.markdown(f'<div class="metric-card"><h2>{val}</h2><p>{lab}</p></div>', unsafe_allow_html=True)

    PLOT = dict(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    PAL = ["#AA8336", "#16A3B8", "#E8C872", "#5B8DEF", "#D9534F", "#7FB77E", "#B58DB6", "#F0A35E"]

    # --- AUTOPILOT ---
    with tab_auto:
        st.markdown("## Autopilot: raw file to decision report")
        if not st.session_state.get("_run_autopilot", False):
            st.caption("The file is loaded and the core dashboard is ready. Run the deeper statistical analysis only when you need it; this avoids delaying other features on large workbooks.")
            if st.button("Run full statistical analysis", type="primary", key="run_full_autopilot"):
                st.session_state._run_autopilot = True
                st.rerun()
        else:
            st.caption("Full statistical analysis has been run. Review the results, untick any question you do not need, then build the signed report in tab 6.")
        _ok = sum(1 for _, o_, _ in INTEG if o_)
        k = st.columns(5)
        kpi(k[0], f"{len(df):,}", "Rows read")
        kpi(k[1], U["type"].split(" /")[0], "File understood as")
        kpi(k[2], len(st.session_state.clean_log), "Cleaning actions")
        kpi(k[3], f"{_ok}/{len(INTEG)}", "Integrity checks passed")
        kpi(k[4], len(AP), "Analyses completed")
        with st.expander("Integrity checks (proof the app did not lose or change data silently)"):
            for c_, o_, d_ in INTEG:
                (st.success if o_ else st.error)(f"{c_}: {d_}")
        _fr, _bk, _rt = decision_sections(AP, APERR, INTEG)
        st.markdown("### Decision summary: what matters most")
        if not AP:
            st.info("The full analysis has not been run yet. Press 'Run full statistical analysis' above to see findings and recommendations.")
        for it_ in (_fr[0][1] if AP else []):
            st.markdown(f'<div class="insight-box">{it_}</div>', unsafe_allow_html=True)
        st.markdown("### Prioritised recommendations")
        if len(_rt):
            st.dataframe(_rt, use_container_width=True)
        else:
            st.info("The statistical evidence does not justify any specific action." if AP else "Recommendations appear after the analysis has been run.")
        _tt = {q["id"]: q["title"] for q in _qs_all}
        _th = {q["id"]: q["theme"] for q in _qs_all}
        with st.expander("Choose which questions to answer (all selected by default)"):
            st.multiselect("Questions", _ids, default=_ids, key=_apk, format_func=lambda i: f"[{_th[i]}] {_tt[i]}")
        for th_ in dict.fromkeys(r["theme"] for r in AP):
            st.markdown(f"### {th_}")
            for r in [x for x in AP if x["theme"] == th_]:
                with st.expander(r["title"]):
                    st.markdown(f'<div class="insight-box">{r["answer"]}</div>', unsafe_allow_html=True)
                    st.markdown(f"**What this means:** {r['sowhat']}")
                    if r["chart"] is not None:
                        try:
                            st.plotly_chart(chart_plotly(r["chart"]), use_container_width=True)
                        except Exception:
                            pass
                    if r["table"] is not None:
                        st.dataframe(r["table"], use_container_width=True)
                    st.caption("Method: " + r["method"])
        if APERR:
            st.markdown("### Analyses skipped (not enough suitable data)")
            st.dataframe(pd.DataFrame(APERR), use_container_width=True)
        if AP:
            st.download_button("Download every analysis table (Excel)", memo("ap_x", (_dk, tuple(_sel), _mask), lambda: pivots_xlsx({r["title"]: r["table"] for r in AP if r["table"] is not None})),
                               "Autopilot_Analysis_Tables.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="ap_dl")

    # --- FILE UNDERSTANDING ---
    with tab_under:
        st.markdown("## File Understanding: what the app knows about your file")
        if len(_sheets) > 1:
            st.markdown("### Every sheet in this workbook")
            _ck = (uploaded_file.name, uploaded_file.size)
            if st.session_state.get("_sov_key") != _ck:
                st.session_state._sov = sheet_overview(uploaded_file.getvalue(), _sheets)
                st.session_state._sov_key = _ck
            st.dataframe(st.session_state._sov, use_container_width=True)
            st.caption("Choose which sheet to analyse in the sidebar.")
        c = st.columns(4)
        kpi(c[0], U["type"].split(" /")[0], "File type")
        kpi(c[1], f"{U['conf']}%", "Confidence")
        kpi(c[2], f"{len(df):,}", "Records")
        kpi(c[3], len(U["issues"]), "Checks flagged")
        st.markdown("### Data quality scorecard")
        qc_ = st.columns(5)
        for i_, (k_, v_) in enumerate(QD.items()):
            kpi(qc_[i_], f"{v_:.0f}%", "Overall quality" if k_ == "overall" else k_)
        st.markdown(f'<div class="insight-box">{U["summary"]}</div>', unsafe_allow_html=True)
        st.markdown("### What I will focus on for this type of file")
        for p_ in U["plan"]:
            st.markdown(f"- {p_}")
        if U["metric"]:
            st.info(f"Main measure: **{U['metric']}** | Main groupings: **{', '.join(U['dims'][:3]) or 'none'}** | Main date: **{(U['dates'] or ['none'])[0]}**. Dashboards and the report lead with these.")
        st.markdown("### What each column means (correct me if I am wrong)")
        ROLE_OPTS = ["identifier", "name", "email", "phone", "kra_pin", "date", "money", "quantity", "percentage", "age", "gender", "location", "category", "status/type", "boolean", "measure", "text"]
        rt = pd.DataFrame([{"Column": c_, "Meaning": r_, "Confidence": f"{cf:.0%}", "Why": w_} for c_, (r_, cf, w_) in U["roles"].items()])
        er = st.data_editor(rt, hide_index=True, use_container_width=True, key="role_ed", disabled=["Column", "Confidence", "Why"],
                            column_config={"Meaning": st.column_config.SelectboxColumn("Meaning", options=ROLE_OPTS, required=True)})
        if st.button("Apply my corrections"):
            st.session_state.role_override = {r["Column"]: r["Meaning"] for _, r in er.iterrows() if r["Meaning"] != U["roles"][r["Column"]][0]}
            st.rerun()
        st.markdown("### Checks specific to this file")
        if len(U["issues"]):
            st.dataframe(U["issues"], use_container_width=True)
            st.download_button("Download exceptions workbook (every flagged row with its reason)", memo("exc", (_dk, _mask, len(U["issues"])), lambda: exceptions_xlsx(df_rep, U)), "Exceptions_Report.xlsx",
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="exc_dl")
        else:
            st.success("All validation checks passed.")
        if len(U["fuzzy"]):
            st.markdown("### Near-duplicate spellings found")
            st.dataframe(U["fuzzy"], use_container_width=True)
            if st.button("Merge these into the more common spelling"):
                d2, n_ = merge_fuzzy(df, U["fuzzy"])
                st.session_state.df = d2
                lg_ = st.session_state.clean_log
                st.session_state.clean_log = pd.concat([lg_, pd.DataFrame([("Consistency", "-", f"Merged {n_} near-duplicate spellings")], columns=lg_.columns)], ignore_index=True)
                st.rerun()

    # --- START HERE GUIDE ---
    with tab_guide:
        st.markdown("## How this app works")
        st.markdown("**Follow the numbered tabs:** upload your file (it is cleaned automatically) -> **1. Understand** (what the file is, checks) -> **2. Clean** (review and adjust) -> **3. Dashboard** -> **4. Pivot** -> **5. Lookup & Reconcile** (if you have a second file) -> **6. Report & Sign-off**. The 13 specialist and original tools are all inside **Advanced Tools**. In the sidebar: **Client Recipe** saves your settings for a client, **Mask personal data** hides emails/phones/PINs/names in reports, and the **Audit log** records every action.")
        guide = pd.DataFrame([
            ["Autopilot", "NEW", "Runs the whole analyst workflow automatically: group comparisons with tests, concentration, trends, drivers, segments, outliers; ranks findings; writes recommendations; proves integrity", "Start here for any new file"],
            ["File Understanding", "NEW", "Detects what kind of file it is, what each column means, runs checks specific to that type, lists exceptions", "Always check this first"],
            ["Executive Dashboard", "NEW", "KPI cards, filters, charts, every cleaned record", "First look at any file"],
            ["Auto-Clean Studio", "NEW", "Per-column blank handling with reasons, row rules, duplicates, outlier capping", "Fine-tune cleaning"],
            ["5. Lookup & Reconcile > Reconcile two files", "NEW", "Matches two lists (bank vs ledger, eTIMS vs sales) by reference, then amount+date, then amount+similar name; produces a reconciliation statement and unmatched lists", "Bank, supplier and eTIMS reconciliations"],
            ["VLOOKUP / XLOOKUP", "NEW", "Pull columns from a second file by a matching key; exact or approximate", "Two related files"],
            ["Smart Pivot", "NEW", "Rows, columns, values, totals, heat colours, chart", "Summaries like Excel pivots"],
            ["Management Report & Sign-off", "NEW", "Written explanation, recommendations, dashboards, pen signature with date/time, PDF", "Final deliverable"],
            ["Overview & Merge", "Original", "Size, blanks, preview; join two files on a key", "Quick structure check, joins"],
            ["Clean & Transform", "Original", "Manual duplicate purge, drop blank rows, fill with one constant", "Mostly replaced by Auto-Clean Studio"],
            ["Granular Type Sanitation", "Original", "Force a column to text/integer/decimal/date; text case; rounding", "Fix a column the app mis-typed"],
            ["Outlier Analysis", "Original", "Finds unusual values (IQR rule) and can filter them out", "Spot suspicious amounts"],
            ["Exploratory Visuals", "Original", "Pick any two columns for bar/line/scatter", "Ad-hoc charts"],
            ["Dynamic Pivot Studio", "Original", "Simple pivot (rows and one value)", "Replaced by Smart Pivot"],
            ["Advanced Statistics", "Original", "Correlation heatmap and Shapiro-Wilk normality test", "Statistical checks"],
            ["Predictive ML Studio", "Original", "Random Forest predicts a numeric column and ranks which columns matter most", "Which factors drive a result"],
            ["Automated Profiling", "Original", "Data types, blanks and memory per column", "Data audit"],
            ["KRA Tax & Compliance", "Original", "KRA PIN format check; VAT and withholding calculator", "Kenyan tax reviews"],
            ["eTIMS Reconciliation", "Original", "Flags invoice numbers that do not look like valid control numbers (format check only, not a true match against KRA records)", "Initial eTIMS screening"],
            ["Customs & Tariff Simulator", "Original", "Landed cost: duty, IDF, RDL, excise, VAT; plus a simple question box", "Import costing"],
            ["Export, Reports & Pen Sign", "Original", "Older one-page PDF with pen signature and exports", "Replaced by Management Report"],
        ], columns=["Tab", "Status", "What it does", "Use it for"])
        st.dataframe(guide, use_container_width=True, height=650)
        st.markdown("### This app versus Excel")
        st.dataframe(pd.DataFrame([
            ["Header, types, blanks, duplicates", "Manual, cell by cell, no record", "Automatic, reasoned per column, every change logged"],
            ["VLOOKUP / XLOOKUP", "Formula per column; #N/A errors; spelling mismatches fail", "No formulas; case/space-tolerant keys; unmatched report"],
            ["Pivot tables", "Built by hand each time", "Any pivot, plus a gallery of all sensible pivots; sensible default calculation; totals reconciled"],
            ["Statistical testing", "Needs add-ins and expertise", "Automatic, adjusted for multiple comparisons, effect sizes in plain English"],
            ["Drivers, segments, trends, concentration", "Rarely done", "Automatic, with decisions and priorities"],
            ["Reconciliation", "Manual matching", "Three-pass matching with an accountant's statement"],
            ["Evidence and audit", "None", "Audit log, data fingerprint, integrity checks, signed report"],
            ["Where Excel is still better", "Free-form formulas, custom financial models, bespoke layouts", "Use Excel for those; export the cleaned workbook from here"],
        ], columns=["Task", "Excel", "This app"]), use_container_width=True)
        st.markdown("### How missing values are decided (and why)")
        st.dataframe(METHOD_GUIDE, use_container_width=True)

    # --- EXECUTIVE DASHBOARD ---
    with tab_dash:
        wc_ui.render_dashboard(df, raw_df, U, kd, QD["overall"], INTEG, memo("fp", _dk, lambda: fingerprint(df)), s_insights)
        with st.expander("Ask a question about this data (optional, uses Claude)"):
            st.caption("Claude receives summary figures only, never the raw rows. Add your API key in the sidebar.")
            q_ = st.text_input("Your question", key="ask_q")
            if st.button("Ask", key="wm_ask_dashboard") and q_:
                if not st.session_state.get("ai_key"):
                    st.warning("Enter your Anthropic API key in the sidebar first.")
                else:
                    try:
                        st.write(ai_ask(st.session_state.ai_key, q_, _nar["facts"] + "\n" + U["summary"]))
                    except Exception as e:
                        st.error(f"Could not get an answer: {e}")

    # --- AUTO-CLEAN STUDIO ---
    with tab_clean:
        st.markdown("## Auto-Clean Studio: every column and row, handled by its data type")
        st.write("The app already cleaned your file on upload. Review the audit trail, then fine-tune any column or row rule below.")
        st.markdown("### Audit trail (what was changed automatically)")
        st.dataframe(st.session_state.clean_log, use_container_width=True)
        st.markdown("### Column profile & missing-value strategy")
        with st.expander("Why mean, median, mode...? Read the method guide"):
            st.dataframe(METHOD_GUIDE, use_container_width=True)
        prof = profile(df)
        ed = st.data_editor(prof.assign(Strategy="Auto"), hide_index=True, use_container_width=True, key="strat_ed",
                            disabled=["Column", "Type", "Missing", "Missing %", "Unique", "Auto Strategy", "Why this strategy"],
                            column_config={"Strategy": st.column_config.SelectboxColumn("Your choice", options=STRATS, required=True)})
        r1, r2, r3 = st.columns(3)
        row_thr = r1.slider("Drop rows missing more than X% of their fields", 10, 100, 100, help="100 = off")
        dup_cols = r2.multiselect("Duplicate check columns (empty = whole row)", cols)
        keep = r3.selectbox("When duplicates found keep", ["first", "last", "none (drop all copies)"])
        o1, o2, o3 = st.columns(3)
        do_tidy = o1.checkbox("Trim & collapse extra spaces in text", True)
        do_cap = o2.checkbox("Cap extreme outliers (IQR) on numeric columns", False)
        do_case = o3.checkbox("Title-case text categories", False)
        nd = int(df.duplicated(subset=dup_cols or None, keep=False if keep.startswith("none") else keep).sum())
        st.info(f"Preview: {nd:,} duplicate rows would be removed. {int((df.isna().mean(axis=1) * 100 > row_thr).sum()):,} rows exceed the missing-row limit.")
        if st.button("Apply cleaning rules"):
            d2, notes = df.copy(), []
            if do_tidy:
                d2, n = smart_text_tidy(d2)
                notes.append(("Text", "-", f"Tidied spacing in {n} cells"))
            if row_thr < 100:
                m = d2.isna().mean(axis=1) * 100 > row_thr
                d2 = d2[~m]
                notes.append(("Rows", "-", f"Dropped {int(m.sum())} rows with more than {row_thr}% missing fields"))
            for _, r in ed.iterrows():
                cn, stg = r["Column"], r["Strategy"]
                if cn not in d2 or not d2[cn].isna().any():
                    continue
                if stg == "Drop rows":
                    k = int(d2[cn].isna().sum())
                    d2 = d2[d2[cn].notna()]
                    notes.append(("Missing", cn, f"Dropped {k} rows (blank {cn})"))
                else:
                    k = int(d2[cn].isna().sum())
                    d2[cn] = fill_series(d2[cn], stg)
                    notes.append(("Missing", cn, f"{k} blanks handled with '{stg if stg != 'Auto' else auto_strategy(df[cn]) + ' (auto)'}'"))
            if do_case:
                for cn in [x for x in d2.columns if col_kind(d2[x]) == "category" and not pd.api.types.is_numeric_dtype(d2[x])]:
                    d2[cn] = d2[cn].astype(str).where(d2[cn].notna()).str.title()
                notes.append(("Text", "-", "Title-cased category columns"))
            if do_cap:
                for cn in [x for x in d2.columns if col_kind(d2[x]) == "numeric"]:
                    fl, lo, hi = outliers_iqr(d2[cn].dropna())
                    k = int(((d2[cn] < lo) | (d2[cn] > hi)).sum())
                    if k:
                        d2[cn] = d2[cn].clip(lo, hi)
                        notes.append(("Outliers", cn, f"Capped {k} extreme values to [{lo:,.2f}, {hi:,.2f}]"))
            bef = len(d2)
            d2 = d2.drop_duplicates(subset=dup_cols or None, keep=False if keep.startswith("none") else keep)
            if bef - len(d2):
                notes.append(("Duplicates", ",".join(dup_cols) or "all columns", f"Removed {bef - len(d2)} duplicate rows (kept {keep})"))
            st.session_state.df = d2.reset_index(drop=True)
            lg = st.session_state.clean_log
            st.session_state.clean_log = pd.concat([lg, pd.DataFrame(notes, columns=lg.columns)], ignore_index=True)
            st.success(f"Done. {len(d2):,} rows now. Changes are in the audit trail.")
            audit(_USER, "cleaning rules applied", f"{len(notes)} changes")
            st.rerun()
        if st.button("Reset to original upload (re-clean automatically)"):
            st.session_state._pk = None
            st.rerun()
        flagged_out = []
        for cn in s_nums:
            fl, lo, hi = outliers_iqr(df[cn].dropna())
            if int(fl.sum()):
                flagged_out.append({"Column": cn, "Unusual values": int(fl.sum()), "Normal range": f"{lo:,.2f} to {hi:,.2f}"})
        if flagged_out:
            st.markdown("### Unusual values spotted (review, not auto-deleted)")
            st.dataframe(pd.DataFrame(flagged_out), use_container_width=True)

    # --- VLOOKUP / XLOOKUP ---
    with tab_lookup:
        _lk_tab, _rc_tab = st.tabs(["VLOOKUP / XLOOKUP", "Reconcile two files"])
    with _lk_tab:
        st.markdown("## VLOOKUP / XLOOKUP / Approximate match, no formulas")
        ref = st.session_state.df_secondary
        if ref is None:
            st.info("Upload a Secondary Dataset in the sidebar (the lookup table). Keys are matched ignoring case and extra spaces.")
        else:
            st.dataframe(ref.head(8), use_container_width=True)
            c = st.columns(3)
            lk = c[0].selectbox("Lookup value column (your data)", cols, key="lk_l")
            rk = c[1].selectbox("Match column (lookup table)", ref.columns.tolist(), key="lk_r")
            rc = c[2].multiselect("Columns to return", [x for x in ref.columns if x != rk], key="lk_c")
            md = st.radio("Match type", ["exact", "approximate"], horizontal=True, help="approximate = Excel TRUE: nearest lower value (tax bands, tiers)")
            nf = st.text_input("If not found show", "Not found")
            if st.button("Run lookup") and rc:
                try:
                    res, un, dp = lookup(df, ref, lk, rk, rc, md)
                    for x in rc:
                        xn = x if x in res.columns and x not in df.columns else f"{x}_lookup"
                        if xn in res.columns:
                            res[xn] = res[xn].astype(object).where(res[xn].notna(), nf)
                    st.session_state.lookup_res = res
                    if un == len(res):
                        st.warning("No keys matched at all. These two files may not share a common column; check you picked the right match columns.")
                    else:
                        st.success(f"{len(res) - un:,} matched, {un:,} not found.")
                    if dp:
                        st.warning(f"{dp} duplicate keys in lookup table; first match used, as Excel does.")
                except Exception as e:
                    st.error(f"Lookup could not run: {e}. (Approximate match only works when both columns are numbers.)")
            if st.session_state.lookup_res is not None:
                st.dataframe(st.session_state.lookup_res, use_container_width=True)
                if st.button("Keep looked-up columns in my working data"):
                    st.session_state.df = st.session_state.lookup_res
                    st.session_state.lookup_res = None
                    st.rerun()

    # --- RECONCILE TWO FILES ---
    with _rc_tab:
        st.markdown("## Reconcile two files (bank vs ledger, eTIMS vs sales, supplier statement vs payables)")
        B0 = st.session_state.df_secondary
        if B0 is None:
            st.info("Upload the second file as the Secondary Dataset in the sidebar. File A is your main file; File B is the secondary one.")
        else:
            uB = memo("uB", (B0.shape, tuple(B0.columns)), lambda: understand(B0))
            NONE = "(none)"

            def pick(label, frame, role_list, key, optional=True, rx=None):
                opts = ([NONE] if optional else []) + list(frame.columns)
                dflt = next((c_ for c_, (r_, _, _) in (uB["roles"] if frame is B0 else U["roles"]).items() if r_ in role_list), None)
                if rx and not dflt:
                    dflt = next((c_ for c_ in frame.columns if re.search(rx, str(c_).lower())), None)
                return st.selectbox(label, opts, index=opts.index(dflt) if dflt in opts else 0, key=key)
            ca, cb = st.columns(2)
            with ca:
                st.markdown("**File A (main)**")
                a_ref = pick("Reference / invoice number", df, ["identifier"], "ra_ref")
                a_amt = pick("Amount", df, ["money"], "ra_amt", optional=False)
                a_dt = pick("Date", df, ["date"], "ra_dt")
                a_nm = pick("Name (customer/supplier)", df, ["name"], "ra_nm")
            with cb:
                st.markdown("**File B (secondary)**")
                b_ref = pick("Reference / invoice number", B0, ["identifier"], "rb_ref")
                b_amt = pick("Amount", B0, ["money"], "rb_amt", optional=False)
                b_dt = pick("Date", B0, ["date"], "rb_dt")
                b_nm = pick("Name (customer/supplier)", B0, ["name"], "rb_nm")
            p1, p2, p3 = st.columns(3)
            r_tol = p1.number_input("Amount tolerance for reference matches", 0.0, 1e9, 0.0, help="Differences up to this size still count as matched (rounding)")
            r_days = p2.number_input("Date window (days) for amount+date matching", 0, 60, 3)
            r_thr = p3.slider("Name similarity needed", 0.5, 1.0, 0.8)
            r_ao = st.checkbox("Allow amount-only matching when no dates are available (risky: equal amounts may be unrelated)", False)
            if st.button("Run reconciliation"):
                none = lambda v: None if v == NONE else v
                try:
                    st.session_state.recon = reconcile(df, B0, {"ref": none(a_ref), "amt": a_amt, "date": none(a_dt), "name": none(a_nm)},
                                                       {"ref": none(b_ref), "amt": b_amt, "date": none(b_dt), "name": none(b_nm)}, r_tol, r_days, r_thr, r_ao)
                    st.session_state.recon_sum = st.session_state.recon["sum"]
                    audit(_USER, "reconciliation run", f"{st.session_state.recon_sum['pairs']} pairs")
                except Exception as e:
                    st.error(f"Reconciliation could not run: {e}")
            R = st.session_state.get("recon")
            if R is not None:
                S_ = R["sum"]
                k = st.columns(5)
                kpi(k[0], f"{S_['rate']:.0f}%", "Records matched")
                kpi(k[1], f"{S_['matched']:,}", "Matched exactly")
                kpi(k[2], f"{S_['diff']:,}", "Amount differences")
                kpi(k[3], f"{S_['a_only']:,}", "In A only")
                kpi(k[4], f"{S_['b_only']:,}", "In B only")
                st.markdown("### Reconciliation statement")
                st.dataframe(R["stmt"].style.format({"Amount": "{:,.2f}"}), use_container_width=True)
                if abs(float(R["stmt"].iloc[-1, 1])) > 0.005:
                    st.warning("The statement does not fully balance. Some rows may have blank amounts; check the unmatched lists.")
                else:
                    st.success("The two files are fully reconciled: every difference is explained by the items above.")
                view = st.radio("View", ["Matched", "Amount differences", "In A only", "In B only"], horizontal=True)
                st.dataframe({"Matched": R["matched"], "Amount differences": R["diff"], "In A only": R["a_only"], "In B only": R["b_only"]}[view], use_container_width=True, height=400)
                st.download_button("Download reconciliation workbook", recon_xlsx(R), "Reconciliation.xlsx",
                                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="rc_dl")
                st.caption("Matching order: 1) same reference, 2) same amount within the date window, 3) same amount with a similar name. Each row is used once.")

    # --- SMART PIVOT ---
    with tab_spivot:
        st.markdown("## Smart Pivot Table (rows, columns, values, totals, heat colours)")
        pc = st.columns(4)
        p_rows = pc[0].multiselect("Rows", cols, default=s_cats[:1], key="sp_r")
        p_cols = pc[1].multiselect("Columns", [x for x in cols if x not in p_rows], key="sp_c")
        p_vals = pc[2].multiselect("Values", s_nums + ["Records"], default=s_nums[:1] or ["Records"], key="sp_v")
        _roles_v = [U["roles"].get(v_, ("quantity",))[0] for v_ in p_vals]
        _dagg = "sum" if p_vals and all(r_ in ("money", "quantity") for r_ in _roles_v) else "mean"
        _aopts = ["sum", "mean", "count", "min", "max", "median"]
        p_agg = pc[3].selectbox("Summarise by", _aopts, index=_aopts.index(_dagg), key="sp_a_" + "|".join(p_vals))
        if p_agg == "sum" and any(r_ in ("measure", "age", "percentage") for r_ in _roles_v):
            st.warning("Adding up scores, hours, ages or percentages is rarely meaningful. Use 'mean' or 'median' to see which group is higher.")
        p_pct = st.checkbox("Show as % of grand total", False)
        if p_rows and p_vals:
            pv = pd.pivot_table(df.assign(Records=1), index=p_rows, columns=p_cols or None, values=p_vals, aggfunc=p_agg, margins=True, margins_name="Grand Total", fill_value=0)
            if p_pct:
                pv = pv / pv.loc["Grand Total"].iloc[-1] * 100 if "Grand Total" in pv.index else pv
            try:
                st.dataframe(pv.style.background_gradient(cmap="YlOrBr", axis=None).format("{:,.2f}"), use_container_width=True)
            except Exception:
                st.dataframe(pv, use_container_width=True)
            fl = pv.drop(index="Grand Total", errors="ignore").reset_index()
            fl.columns = [" ".join(map(str, x)).strip() if isinstance(x, tuple) else str(x) for x in fl.columns]
            yc = [x for x in fl.columns if x not in [str(r) for r in p_rows] and "Grand Total" not in x]
            if yc:
                st.plotly_chart(px.bar(fl.head(30), x=fl.columns[0], y=yc[:4], barmode="group", color_discrete_sequence=PAL).update_layout(**PLOT), use_container_width=True)
            st.download_button("Download pivot (CSV)", pv.to_csv().encode(), "pivot.csv", "text/csv", key="sp_dl")
            try:
                if p_agg in ("sum", "count") and not p_pct and len(p_vals) == 1:
                    _c0 = p_vals[0]
                    _exp = df.assign(Records=1)[_c0].sum() if p_agg == "sum" else (len(df) if _c0 == "Records" else df[_c0].count())
                    _got = float(pv.iloc[-1].iloc[-1] if p_cols else pv.iloc[-1].iloc[0])
                    if abs(_got - float(_exp)) <= 1e-6 * max(1.0, abs(float(_exp))):
                        st.success(f"Reconciled: the pivot grand total ({_got:,.2f}) equals the direct total of the column ({float(_exp):,.2f}).")
                    else:
                        st.error("The pivot total does not match the column total. Rows with blanks in the row or column fields are left out of a pivot; check those fields.")
            except Exception:
                pass
            st.session_state.last_pivot = pv.reset_index().head(20)
            st.session_state.last_pivot.columns = [" ".join(map(str, x)).strip() if isinstance(x, tuple) else str(x) for x in st.session_state.last_pivot.columns]

    with tab_spivot:
        st.markdown("---")
        st.markdown("### Pivot Gallery: every sensible pivot, built for you")
        _gal = memo("gal", (_dk, tuple(PRIO)), lambda: pivot_gallery(df, U))
        _gp = st.multiselect("Choose the pivots to show (all selected)", list(_gal.keys()), default=list(_gal.keys()), key="gal_sel")
        for k_ in _gp:
            with st.expander(k_):
                st.dataframe(_gal[k_].style.format("{:,.2f}") if "Count of" not in k_ else _gal[k_], use_container_width=True)
        if _gal:
            st.download_button("Download all pivots (Excel, one sheet each)", memo("gal_x", (_dk, tuple(PRIO)), lambda: pivots_xlsx(_gal)), "Pivot_Gallery.xlsx",
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="gal_dl")

    # --- MANAGEMENT REPORT & SIGN-OFF ---
    with tab_mgmt:
        st.markdown("## Management Report & Digital Sign-Off")
        g1, g2 = st.columns(2)
        rep_title = g1.text_input("Report title", "Data Review & Management Report", key="rep_title")
        signer_n = g2.text_input("Manager / Partner (name & title)", "Hadi Sheikh Abdullahi, Lead Consultant", key="signer_n")
        st.markdown("**Sign below with a pen, finger or mouse** (drag to draw), then press *Capture signature*. The exact date and time are stamped on the report.")
        try:
            from streamlit_drawable_canvas import st_canvas
            cv = st_canvas(stroke_width=3, stroke_color="#002043", background_color="#FFFFFF", height=150, width=450,
                           drawing_mode="freedraw", key="sigpad2", update_streamlit=True, return_image_data=True)
            if cv.image_data is not None and st.button("Capture signature", key="cap2"):
                from PIL import Image as PI
                ar = cv.image_data.astype(np.uint8)
                if (ar[:, :, 3] > 0).sum() < 30:
                    st.error("Please draw your signature first.")
                else:
                    im = PI.fromarray(ar).convert("RGBA")
                    bgm = PI.new("RGBA", im.size, (255, 255, 255, 255))
                    bgm.alpha_composite(im)
                    bb = io.BytesIO()
                    bgm.convert("RGB").save(bb, "PNG")
                    st.session_state.sig_bytes = bb.getvalue()
                    st.session_state.sig_time = datetime.now().strftime("%A, %d %B %Y at %H:%M:%S")
                    audit(_USER, "signature captured", signer_n)
        except Exception as e:
            st.warning(f"Pen pad unavailable ({e}). Upload a signature image instead.")
            up = st.file_uploader("Signature image", type=["png", "jpg", "jpeg"], key="sigup2")
            if up is not None:
                st.session_state.sig_bytes = up.getvalue()
                st.session_state.sig_time = datetime.now().strftime("%A, %d %B %Y at %H:%M:%S")
        if st.session_state.sig_bytes:
            st.image(st.session_state.sig_bytes, width=220, caption=f"Signed {st.session_state.sig_time}")
            if st.button("Clear signature", key="clr2"):
                st.session_state.sig_bytes, st.session_state.sig_time = None, ""
                st.rerun()
        kp = [("Records analysed", f"{len(df):,}"), ("Columns", df.shape[1]), ("Blanks found / left", f"{int(raw_df.isna().sum().sum()):,} / {int(df.isna().sum().sum()):,}"),
              ("Data quality before cleaning", f"{quality_score(raw_df, kd)}%"), ("Cleaning actions logged", len(st.session_state.clean_log))]
        for nc in s_nums[:4]:
            kp.append((f"Average {nc}", f"{df[nc].mean():,.2f}"))
        _fp = memo("fp", _dk, lambda: fingerprint(df))
        _rid = f"WC-{datetime.now():%Y%m%d}-{_fp[:6]}"
        kp += [("Overall data quality score", f"{QD['overall']:.0f}%"), ("Report ID", _rid), ("Data fingerprint (SHA-256)", _fp)]
        st.dataframe(pd.DataFrame(kp, columns=["Metric", "Value"]), use_container_width=True)
        nar = _nar
        st.markdown("### The app explains your data (this text goes into the PDF)")
        with st.expander("Read the full written report", expanded=True):
            for hd_, items_, bl_ in nar["sections"]:
                st.markdown(f"**{hd_}**")
                for it_ in items_:
                    st.markdown(("- " if bl_ else "") + it_)
            st.markdown("**Column-by-column explanation**")
            st.dataframe(nar["columns"], use_container_width=True)
        ai_on = st.checkbox("Add AI-written commentary (optional; only summary numbers are sent, never your rows)")
        ai_key = st.session_state.get("ai_key", "") if ai_on else ""
        extra_note = st.text_area("Your own comments to add to the report (optional)")
        if st.button("Build management report (PDF)"):
            _fr, _bk, _rt = decision_sections(AP, APERR, INTEG)
            secs = about_sections(U, df, QD) + _fr + list(nar["sections"]) + _bk
            if ai_on and ai_key:
                try:
                    secs.append(("6. AI-assisted commentary", ai_explain(ai_key, nar["facts"]), False))
                except Exception as e:
                    st.warning(f"AI commentary skipped: {e}")
            if st.session_state.get("recon_sum"):
                q_ = st.session_state.recon_sum
                secs.append(("Reconciliation results", [f"{q_['pairs']:,} records were paired ({q_['rate']:.0f}% of the larger file): {q_['matched']:,} matched and {q_['diff']:,} paired with an amount difference totalling {q_['diff_val']:,.2f}.",
                                                          f"{q_['a_only']:,} items (value {q_['ao']:,.2f}) appear only in file A and {q_['b_only']:,} items (value {q_['bo']:,.2f}) only in file B.",
                                                          f"Total per file A is {q_['sA']:,.2f} and per file B is {q_['sB']:,.2f}; the reconciliation statement explains the difference of {q_['sA'] - q_['sB']:,.2f}."], True))
            if extra_note.strip():
                secs.append(("Manager\'s comments", [extra_note.strip()], False))
            charts = []
            try:
                charts = report_charts(df_rep, kd_rep, PRIO)
            except Exception as e:
                st.warning(f"Some charts skipped: {e}")
            try:
                charts = [(r["title"], chart_mpl(r["chart"]), r["answer"] + " What this means: " + r["sowhat"]) for r in sorted(AP, key=lambda r_: -r_["score"]) if r["chart"] is not None][:8] + charts
            except Exception:
                pass
            tbls = ([("Prioritised recommendations", _rt)] if len(_rt) else []) + [("Column-by-column explanation", nar["columns"])]
            if len(U["issues"]):
                tbls.append(("Validation checks run on this file", U["issues"][["Check", "Columns", "Rows affected", "Severity", "Suggested action"]]))
            if s_cats:
                tbls.append((f"Records by {s_cats[0]}", df_rep[s_cats[0]].astype(str).value_counts().head(10).rename_axis(s_cats[0]).reset_index(name="Records")))
            if st.session_state.get("last_pivot") is not None:
                tbls.append(("Pivot summary (from Smart Pivot)", st.session_state.last_pivot))
            tiles = [("Records", f"{len(df):,}"), ("Columns", df.shape[1]), ("Blanks fixed", f"{int(raw_df.isna().sum().sum()):,}"), ("Overall data quality", f"{QD['overall']:.0f}%")]
            tiles += [((f"Total {x}", f"{df[x].sum():,.0f}") if U["roles"][x][0] in ("money", "quantity") else (f"Average {x}", f"{df[x].mean():,.1f}")) for x in s_nums[:4]] + [(f"{x} groups", df[x].nunique()) for x in s_cats[:4]]
            st.session_state.pdf = build_pdf(rep_title, client_name, kp, [], st.session_state.clean_log, charts, signer_n,
                                            st.session_state.sig_bytes, st.session_state.logo_bytes, st.session_state.sig_time, tbls, secs, tiles,
                                            {"report_id": _rid, "fingerprint": _fp, "prepared_by": _USER, "records": f"{len(df):,}"})
            audit(_USER, "report built", f"{_rid} | signed: {st.session_state.sig_time or 'no'} | masked: {_mask}")
        if st.session_state.pdf:
            st.download_button("Download management report (PDF)", st.session_state.pdf, "Westminister_Management_Report.pdf", "application/pdf", key="pdf_dl")
        st.download_button("Download full workbook (clean data, log, insights)", memo("xl_mg", (_dk, len(st.session_state.clean_log), tuple(PRIO)), lambda: to_excel(df, st.session_state.clean_log, s_insights, kd)),
                           "Westminister_Full_Pack.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="mg_x")

    # --- TAB 1: OVERVIEW & MERGE ---
    with tab1:
        st.markdown("## Ledger Overview & Structural Integrity")
        st.write("Reviewing dimensional characteristics, schema attributes, and record integrity of the uploaded dataset.")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""<div class="metric-card"><h2>{df.shape[0]:,}</h2><p>Total Records</p></div>""", unsafe_allow_html=True)
        with col2:
            st.markdown(f"""<div class="metric-card"><h2>{df.shape[1]}</h2><p>Data Attributes</p></div>""", unsafe_allow_html=True)
        with col3:
            missing_cells = df.isna().sum().sum()
            st.markdown(f"""<div class="metric-card"><h2>{missing_cells:,}</h2><p>Missing Data Points</p></div>""", unsafe_allow_html=True)
        
        col_names_str = ", ".join([f"<b>{c}</b>" for c in cols])
        st.markdown(
            f"""
            <div class="insight-box">
            <b>Dataset Breakdown:</b> The loaded file contains <b>{df.shape[0]:,} rows</b> and <b>{df.shape[1]} columns</b> ({col_names_str}). 
            A total of <b>{missing_cells:,} missing cells</b> were identified across features. Inspect the preview below.
            </div>
            """,
            unsafe_allow_html=True
        )
        st.markdown("### Ledger Preview")
        st.dataframe(df.head(10), use_container_width=True)
        
        if st.session_state.df_secondary is not None:
            st.markdown("---")
            st.markdown("### Secondary Dataset Relational Merge")
            df_sec = st.session_state.df_secondary
            st.dataframe(df_sec.head(5), use_container_width=True)
            col_m1, col_m2, col_m3 = st.columns(3)
            with col_m1:
                left_key = st.selectbox("Primary Key", cols, key="l_key")
            with col_m2:
                right_key = st.selectbox("Secondary Key", df_sec.columns.tolist(), key="r_key")
            with col_m3:
                join_type = st.selectbox("Join Architecture", ["inner", "left", "right", "outer"])
            if st.button("Execute Data Integration"):
                try:
                    merged_df = pd.merge(df, df_sec, left_on=left_key, right_on=right_key, how=join_type)
                    st.session_state.df = merged_df
                    st.success(f"Datasets merged successfully. New shape: {merged_df.shape}")
                    st.rerun()
                except Exception as e:
                    st.error(f"Merge execution failed: {e}")
    # --- TAB 2: CLEAN & TRANSFORM ---
    with tab2:
        st.markdown("## Automated Data Hygiene & Sanitation")
        st.write("Sanitize dataset records by purging duplicate entries or managing incomplete rows.")
        
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            if st.button("Purge Duplicate Rows"):
                before = len(df)
                df = df.drop_duplicates()
                st.session_state.df = df
                st.success(f"Purged {before - len(df)} duplicate records.")
            if st.button("Drop Rows with Null Values"):
                before = len(df)
                df = df.dropna()
                st.session_state.df = df
                st.success(f"Cleaned incomplete observations. Active rows: {len(df):,}")
        with col_c2:
            fill_val = st.text_input("Impute missing cells with constant value:", value="0")
            if st.button("Apply Statistical Imputation"):
                df = df.fillna(fill_val)
                st.session_state.df = df
                st.success("Missing data successfully imputed.")
        
        st.markdown(
            f"""
            <div class="insight-box">
            <b>Sanitation Status:</b> Active dataset contains <b>{len(df):,} records</b> ready for granular type casting and downstream analysis.
            </div>
            """,
            unsafe_allow_html=True
        )
        st.markdown("### Sanitized Data Sample")
        st.dataframe(df.head(10), use_container_width=True)
    # --- TAB GRANULAR: COLUMN-BY-COLUMN TYPE SANITATION ---
    with tab_granular:
        st.markdown("## Granular Column-by-Column & Row-Level Intelligence")
        st.write("Examine and enforce precise data types (Strings, Integers, Floats, Categorical Classifications, Dates) for every column to surpass standard spreadsheet formatting.")
        
        st.markdown("### Current Column Data Types & Unique Counts")
        type_summary_data = []
        for c in cols:
            col_series = df[c]
            type_summary_data.append({
                "Column Name": c,
                "Detected Type": str(col_series.dtype),
                "Non-Null Count": col_series.notnull().sum(),
                "Unique Values": col_series.nunique()
            })
        st.dataframe(pd.DataFrame(type_summary_data), use_container_width=True)
        
        st.markdown("---")
        st.markdown("### Targeted Type Casting & Sanitation Engine")
        target_col_cast = st.selectbox("Select Column to Transform", cols, key="cast_col")
        target_type = st.selectbox("Target Data Type", ["string (Text / Categorical)", "integer (Whole Number)", "float (Decimal Number)", "datetime (Timestamp)"], key="target_dtype")
        
        col_t_action1, col_t_action2 = st.columns(2)
        with col_t_action1:
            if target_type.startswith("string"):
                string_op = st.selectbox("String Operation", ["None", "Uppercase", "Lowercase", "Title Case", "Strip Whitespace"])
            elif target_type.startswith("integer") or target_type.startswith("float"):
                num_impute = st.selectbox("Missing Value Handling", ["Drop nulls", "Impute with 0", "Impute with Mean", "Impute with Median"])
        with col_t_action2:
            if target_type.startswith("float"):
                round_decimals = st.number_input("Round Decimals", min_value=0, max_value=6, value=2)
        if st.button("Execute Granular Transformation"):
            try:
                if "string" in target_type:
                    df[target_col_cast] = df[target_col_cast].astype(str)
                    if 'Uppercase' in locals().get('string_op', '') and string_op == "Uppercase":
                        df[target_col_cast] = df[target_col_cast].str.upper()
                    elif string_op == "Lowercase":
                        df[target_col_cast] = df[target_col_cast].str.lower()
                    elif string_op == "Title Case":
                        df[target_col_cast] = df[target_col_cast].str.title()
                    elif string_op == "Strip Whitespace":
                        df[target_col_cast] = df[target_col_cast].str.strip()
                elif "integer" in target_type:
                    if num_impute == "Drop nulls":
                        df = df.dropna(subset=[target_col_cast])
                    elif num_impute == "Impute with 0":
                        df[target_col_cast] = df[target_col_cast].fillna(0)
                    elif num_impute == "Impute with Mean":
                        df[target_col_cast] = df[target_col_cast].fillna(df[target_col_cast].mean())
                    elif num_impute == "Impute with Median":
                        df[target_col_cast] = df[target_col_cast].fillna(df[target_col_cast].median())
                    df[target_col_cast] = pd.to_numeric(df[target_col_cast], errors='coerce').astype(int)
                elif "float" in target_type:
                    if num_impute == "Drop nulls":
                        df = df.dropna(subset=[target_col_cast])
                    elif num_impute == "Impute with 0":
                        df[target_col_cast] = df[target_col_cast].fillna(0.0)
                    elif num_impute == "Impute with Mean":
                        df[target_col_cast] = df[target_col_cast].fillna(df[target_col_cast].mean())
                    elif num_impute == "Impute with Median":
                        df[target_col_cast] = df[target_col_cast].fillna(df[target_col_cast].median())
                    df[target_col_cast] = pd.to_numeric(df[target_col_cast], errors='coerce').round(round_decimals)
                elif "datetime" in target_type:
                    df[target_col_cast] = pd.to_datetime(df[target_col_cast], errors='coerce')
                
                st.session_state.df = df
                st.success(f"Successfully cast column '{target_col_cast}' to {target_type}!")
                st.rerun()
            except Exception as e:
                st.error(f"Transformation failed: {e}")
    # --- TAB 3: OUTLIER ANALYSIS ---
    with tab3:
        st.markdown("## Anomaly & Outlier Detection")
        st.write("Detect unusual transaction spikes or billing discrepancies using robust IQR boundaries.")
        if numeric_cols:
            default_num_idx = get_col_index(numeric_cols, ["amount", "total", "cost", "price", "val"])
            selected_num_col = st.selectbox("Select Target Feature for Anomaly Scan", numeric_cols, index=default_num_idx)
            Q1 = df[selected_num_col].quantile(0.25)
            Q3 = df[selected_num_col].quantile(0.75)
            IQR = Q3 - Q1
            lower_bound = Q1 - 1.5 * IQR
            upper_bound = Q3 + 1.5 * IQR
            outliers = df[(df[selected_num_col] < lower_bound) | (df[selected_num_col] > upper_bound)]
            
            col_o1, col_o2 = st.columns(2)
            with col_o1:
                st.markdown(f"""<div class="metric-card"><h2>{len(outliers):,}</h2><p>Anomalous Records</p></div>""", unsafe_allow_html=True)
            with col_o2:
                st.markdown(f"""<div class="metric-card"><h2>{upper_bound:,.2f}</h2><p>Upper Threshold Limit</p></div>""", unsafe_allow_html=True)
            
            st.markdown(
                f"""
                <div class="insight-box">
                <b>Audit Insight:</b> For feature <b>{selected_num_col}</b>, statistical IQR analysis established an upper threshold of <b>{upper_bound:,.2f}</b> and lower limit of <b>{lower_bound:,.2f}</b>. Exactly <b>{len(outliers):,} records ({len(outliers)/len(df)*100:.1f}%)</b> breach these bounds.
                </div>
                """,
                unsafe_allow_html=True
            )
            st.markdown("### Flagged Anomalous Records")
            st.dataframe(outliers, use_container_width=True)
            if st.button("Filter Out Anomalies"):
                df = df[(df[selected_num_col] >= lower_bound) & (df[selected_num_col] <= upper_bound)]
                st.session_state.df = df
                st.success(f"Anomalies filtered. Remaining records: {len(df):,}")
        else:
            st.info("No continuous numeric variables available for outlier detection.")
    # --- TAB 4: EXPLORATORY VISUALS ---
    with tab4:
        st.markdown("## Exploratory Financial Visualization")
        st.write("Inspect distributions, metrics, and transactional totals visually.")
        
        if numeric_cols:
            col_v1, col_v2 = st.columns(2)
            with col_v1:
                default_x = get_col_index(cols, ["invoice", "no", "date", "id", "name", "desc"])
                default_y = get_col_index(numeric_cols, ["amount", "total", "cost", "tax"])
                
                x_col = st.selectbox("Dimension / X-axis Parameter", cols, index=default_x)
                y_col = st.selectbox("Metric / Y-axis Parameter", numeric_cols, index=default_y)
                chart_style = st.radio("Rendering Format", ["Bar Chart", "Line Chart", "Scatter Plot"])
                
                if chart_style == "Bar Chart":
                    fig = px.bar(df, x=x_col, y=y_col, color_discrete_sequence=["#AA8336"])
                elif chart_style == "Line Chart":
                    fig = px.line(df, x=x_col, y=y_col, color_discrete_sequence=["#AA8336"])
                else:
                    fig = px.scatter(df, x=x_col, y=y_col, color_discrete_sequence=["#AA8336"])
                
                fig.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font_color="white")
                st.plotly_chart(fig, use_container_width=True)
                st.markdown(
                    f"""
                    <div class="insight-box">
                    <b>Visual Interpretation:</b> The <b>{chart_style}</b> plots <b>{y_col}</b> against <b>{x_col}</b>, isolating top-tier metrics and trends.
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            with col_v2:
                st.markdown("### Descriptive Financial Summary")
                st.dataframe(df.describe(), use_container_width=True)
                mean_val = df[y_col].mean()
                median_val = df[y_col].median()
                st.markdown(
                    f"""
                    <div class="insight-box">
                    <b>Statistical Overview:</b> For <b>{y_col}</b>, the arithmetic mean is <b>{mean_val:,.2f}</b> while the median is <b>{median_val:,.2f}</b>.
                    </div>
                    """,
                    unsafe_allow_html=True
                )
        else:
            st.warning("Numeric columns required for chart rendering.")
    # --- TAB PIVOT: DYNAMIC PIVOT STUDIO ---
    with tab_pivot:
        st.markdown("## Dynamic Multi-Dimensional Pivot Table Studio")
        st.write("Surpass standard human Excel pivot tables by instantly grouping, aggregating, and analyzing multi-dimensional metrics across large datasets.")
        
        col_piv1, col_piv2, col_piv3 = st.columns(3)
        with col_piv1:
            index_cols = st.multiselect("Row Grouping (Rows)", cols, default=[cols[0]] if cols else [])
        with col_piv2:
            value_col = st.selectbox("Target Value Metric", numeric_cols if numeric_cols else cols, key="piv_val")
        with col_piv3:
            agg_func = st.selectbox("Aggregation Function", ["sum", "mean", "count", "min", "max", "median"])
            
        if index_cols and value_col:
            try:
                pivot_table = pd.pivot_table(
                    df,
                    index=index_cols,
                    values=value_col,
                    aggfunc=agg_func,
                    fill_value=0
                ).reset_index()
                
                st.markdown(f"### Generated Pivot Table ({agg_func.upper()} of {value_col})")
                st.dataframe(pivot_table, use_container_width=True)
                
                st.markdown(
                    f"""
                    <div class="insight-box">
                    <b>Pivot Studio Insight:</b> Successfully aggregated <b>{len(df):,} records</b> across <b>{len(index_cols)} dimension(s)</b>. 
                    This dynamic structure provides instantaneous cross-tabulation without manual formula building.
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            except Exception as e:
                st.error(f"Pivot generation error: {e}")
        else:
            st.info("Please select at least one row grouping and a target value metric.")
    # --- TAB 5: ADVANCED STATISTICS ---
    with tab5:
        st.markdown("## Advanced Statistical Correlation & Normality")
        st.write("Examine collinearity and test distributional normality across numerical features.")
        if len(numeric_cols) >= 2:
            st.markdown("### Pearson Correlation Matrix")
            corr_matrix = df[numeric_cols].corr()
            fig_corr = px.imshow(corr_matrix, text_auto=True, color_continuous_scale="Viridis", title="Feature Correlation Heatmap")
            fig_corr.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font_color="white")
            st.plotly_chart(fig_corr, use_container_width=True)
            st.markdown(
                """
                <div class="insight-box">
                <b>Correlation Review:</b> Evaluates linear dependencies between financial features.
                </div>
                """,
                unsafe_allow_html=True
            )
            st.markdown("### Normality Test (Shapiro-Wilk)")
            default_stat_idx = get_col_index(numeric_cols, ["amount", "total", "tax"])
            selected_stat_col = st.selectbox("Select Numeric Column for Normality Test", numeric_cols, index=default_stat_idx)
            
            if st.button("Run Normality Test"):
                from scipy import stats
                clean_col_data = df[selected_stat_col].dropna()
                stat_val, p_val = stats.shapiro(clean_col_data)
                
                col_s1, col_s2 = st.columns(2)
                with col_s1:
                    st.metric(label="Test Statistic", value=f"{stat_val:.4f}")
                with col_s2:
                    st.metric(label="p-value", value=f"{p_val:.4e}")
                
                if p_val > 0.05:
                    result_text = "The p-value exceeds 0.05, confirming normal distribution."
                else:
                    result_text = "The p-value is below 0.05, indicating departure from normality due to variance."
                
                st.markdown(
                    f"""
                    <div class="insight-box">
                    <b>Test Result Summary:</b> Shapiro-Wilk test yielded statistic <b>{stat_val:.4f}</b> (p-value: <b>{p_val:.4e}</b>). {result_text}
                    </div>
                    """,
                    unsafe_allow_html=True
                )
        else:
            st.info("At least two numeric columns required for advanced statistical testing.")
    # --- TAB 6: PREDICTIVE ML STUDIO ---
    with tab6:
        st.markdown("## Predictive Modeling & Feature Importance Studio")
        st.write("Train supervised Random Forest models to predict financial targets or evaluate feature attribution.")
        
        if len(numeric_cols) >= 2:
            default_target = get_col_index(numeric_cols, ["tax_expected", "amount", "total"])
            target_col = st.selectbox("Dependent Target Variable (Y)", numeric_cols, index=default_target, key="ml_target")
            
            default_features = [c for c in numeric_cols if c != target_col]
            feature_cols = st.multiselect("Independent Explanatory Features (X)", [c for c in numeric_cols if c != target_col], default=default_features, key="ml_features")
            
            if feature_cols and target_col:
                if st.button("Initialize Model Training"):
                    try:
                        from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
                        from sklearn.model_selection import train_test_split
                        model_df = df[feature_cols + [target_col]].dropna()
                        X = model_df[feature_cols]
                        y = model_df[target_col]
                        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
                        
                        if y.nunique() < 20:
                            model = RandomForestClassifier(random_state=42)
                            task_type = "Classification"
                        else:
                            model = RandomForestRegressor(random_state=42)
                            task_type = "Regression"
                        
                        model.fit(X_train, y_train)
                        score = model.score(X_test, y_test)
                        st.success(f"Model successfully trained using {task_type} architecture.")
                        st.metric(label="Validation Score ($R^2$ / Accuracy)", value=f"{score:.4f}")
                        
                        importances = pd.DataFrame({
                            "Feature": feature_cols,
                            "Importance": model.feature_importances_
                        }).sort_values(by="Importance", ascending=False)
                        
                        fig_imp = px.bar(importances, x="Importance", y="Feature", orientation="h", title="Evaluated Feature Importances", color_discrete_sequence=["#AA8336"])
                        fig_imp.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font_color="white")
                        st.plotly_chart(fig_imp, use_container_width=True)
                        
                        top_feature = importances.iloc[0]["Feature"]
                        top_score = importances.iloc[0]["Importance"] * 100
                        st.markdown(
                            f"""
                            <div class="insight-box">
                            <b>Model Attribution:</b> Random Forest <b>{task_type}</b> validation score is <b>{score:.4f}</b>. 
                            Feature <b>{top_feature}</b> exerts the strongest predictive power (<b>{top_score:.1f}%</b> variance explanation).
                            </div>
                            """,
                            unsafe_allow_html=True
                        )
                    except Exception as e:
                        st.error(f"Modeling execution error: {e}")
        else:
            st.info("At least two numeric features are required for predictive modeling.")
    # --- TAB 7: AUTOMATED PROFILING ---
    with tab7:
        st.markdown("## Automated Deep Data Profiling Audit")
        st.write("Instantaneous structural auditing, datatype inspection, and missing value verification.")
        
        buffer = io.StringIO()
        df.info(buf=buffer)
        s = buffer.getvalue()
        
        col_p1, col_p2 = st.columns(2)
        with col_p1:
            st.markdown("### Feature Data Types & Memory Usage")
            dtypes_df = pd.DataFrame({"Column": df.columns, "Type": df.dtypes.astype(str), "Non-Null Count": df.notnull().sum()})
            st.dataframe(dtypes_df, use_container_width=True)
        with col_p2:
            st.markdown("### Missing Value Breakdown")
            missing_df = pd.DataFrame({"Missing Values": df.isnull().sum(), "Percentage (%)": (df.isnull().sum() / len(df)) * 100})
            st.dataframe(missing_df[missing_df["Missing Values"] > 0], use_container_width=True)
        
        st.markdown(
            """
            <div class="insight-box">
            <b>Audit Summary:</b> Verifies type consistency and highlights columns requiring data casting prior to financial reporting.
            </div>
            """,
            unsafe_allow_html=True
        )
        st.markdown("### Console Summary Inspection")
        st.text(s)
    # --- TAB 8: KRA TAX & COMPLIANCE STUDIO ---
    with tab8:
        st.markdown("## Kenya Revenue Authority (KRA) Tax & Compliance Suite")
        st.write("Perform automated local tax audits, compute standard VAT / withholding tax parameters, and verify KRA PIN syntax compliance.")
        
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            st.markdown("### 1. KRA PIN Syntax Audit")
            if string_cols:
                default_pin_idx = get_col_index(string_cols, ["pin", "kra", "tax_pin"])
                pin_col = st.selectbox("Select Column Containing KRA PINs", string_cols, index=default_pin_idx, key="kra_pin_col")
                
                kra_pattern = re.compile(r"^[A-Z]\d{9}[A-Z]$")
                def validate_pin(val):
                    if pd.isna(val):
                        return "Missing"
                    return "Valid" if kra_pattern.match(str(val).strip().upper()) else "Invalid Format"
                
                validation_results = df[pin_col].apply(validate_pin)
                val_counts = validation_results.value_counts()
                st.dataframe(val_counts.reset_index().rename(columns={"index": "Status", pin_col: "Count"}), use_container_width=True)
                
                valid_count = val_counts.get("Valid", 0)
                st.markdown(
                    f"""
                    <div class="insight-box">
                    <b>KRA PIN Verification:</b> Out of {len(df):,} records, <b>{valid_count:,} entries</b> match official KRA alphanumeric syntax.
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            else:
                st.info("No text columns found to verify KRA PIN numbers.")
        
        with col_t2:
            st.markdown("### 2. Corporate VAT & Withholding Tax Simulator")
            if numeric_cols:
                default_tax_col = get_col_index(numeric_cols, ["amount", "total", "cost"])
                tax_base_col = st.selectbox("Select Amount Column for Tax Computation", numeric_cols, index=default_tax_col, key="tax_col")
                
                selected_rate = st.selectbox("Applicable VAT / Tax Regime", ["Standard VAT (16%)", "Zero-Rated / Exempt (0%)", "Withholding Tax (5%)", "Withholding VAT (2%)"])
                total_base = df[tax_base_col].sum()
                discrepancy_text = ""
                
                if "tax_declared" in df.columns and "tax_expected" in df.columns:
                    diff_sum = (df["tax_expected"] - df["tax_declared"]).sum()
                    discrepancy_text = f"<br/><b>Ledger Tax Discrepancy Alert:</b> Total difference between expected and declared tax equals <b>KES {diff_sum:,.2f}</b>."
                
                if "16%" in selected_rate:
                    computed_tax = total_base * 0.16
                    gross_total = total_base + computed_tax
                    tax_label = "Output VAT (16%):"
                elif "5%" in selected_rate:
                    computed_tax = total_base * 0.05
                    gross_total = total_base - computed_tax
                    tax_label = "Withholding Tax (5%):"
                elif "2%" in selected_rate:
                    computed_tax = total_base * 0.02
                    gross_total = total_base - computed_tax
                    tax_label = "Withholding VAT (2%):"
                else:
                    computed_tax = 0.0
                    gross_total = total_base
                    tax_label = "Exempt Tax:"
                
                st.metric(label="Total Cumulative Base Amount", value=f"KES {total_base:,.2f}")
                st.metric(label=tax_label, value=f"KES {computed_tax:,.2f}")
                st.metric(label="Net Financial Settlement Total", value=f"KES {gross_total:,.2f}")
                
                st.markdown(
                    f"""
                    <div class="insight-box">
                    <b>Tax Simulation Breakdown:</b> Applying <b>{selected_rate}</b> yields computed tax liability of <b>KES {computed_tax:,.2f}</b> and net settlement total of <b>KES {gross_total:,.2f}</b>.{discrepancy_text}
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            else:
                st.info("No numeric columns available for tax calculation.")
    # --- TAB ET: eTIMS RECONCILIATION ---
    with tab_etims:
        st.markdown("## eTIMS Ledger Reconciliation & Verification Engine")
        st.write("Cross-examine local transaction ledgers against KRA eTIMS invoice generation logs.")
        
        col_e1, col_e2 = st.columns(2)
        with col_e1:
            etims_id_col = st.selectbox("Select Invoice Number / Control Unit Column", string_cols, key="etims_inv")
        with col_e2:
            etims_amt_col = st.selectbox("Select Total Amount Column", numeric_cols, key="etims_amt")
        
        if st.button("Run eTIMS Matching Audit"):
            df["eTIMS_Status"] = df[etims_id_col].apply(
                lambda x: "Format looks valid (not verified with KRA)" if len(str(x)) >= 6 and str(x).isalnum() else "Flagged / Missing Control Unit"
            )
            
            status_counts = df["eTIMS_Status"].value_counts()
            st.dataframe(status_counts.reset_index().rename(columns={"index": "Compliance Status", "eTIMS_Status": "Record Count"}), use_container_width=True)
            
            flagged_df = df[df["eTIMS_Status"] == "Flagged / Missing Control Unit"]
            st.markdown(f"### Flagged Non-Compliant Records ({len(flagged_df):,})")
            st.dataframe(flagged_df.head(10), use_container_width=True)
            
            st.markdown(
                """
                <div class="insight-box">
                <b>Audit Recommendation:</b> Invoices lacking valid eTIMS control unit signatures must be withheld from corporate VAT input claims.
                </div>
                """,
                unsafe_allow_html=True
            )
    # --- TAB CUSTOMS: EAC CUSTOMS DUTY & TARIFF SIMULATOR ---
    with tab_customs:
        st.markdown("## East African Community (EAC) Customs Duty & Import Tariff Simulator")
        st.write("Simulate total landed costs, import duties, and agency levies for corporate procurement audits.")
        
        col_cd1, col_cd2, col_cd3 = st.columns(3)
        with col_cd1:
            cif_value = st.number_input("CIF Value (KES)", min_value=0.0, value=1500000.0, step=50000.0)
        with col_cd2:
            duty_rate = st.selectbox("Import Duty Rate (EAC CET)", [0.0, 0.10, 0.25], format_func=lambda x: f"{int(x*100)}% (Raw Materials / Capital Goods / Finished Goods)")
        with col_cd3:
            include_excise = st.checkbox("Apply Excise Duty (10%)", value=False)
        
        if st.button("Compute Landed Tax & Duties"):
            import_duty = cif_value * duty_rate
            idf = cif_value * 0.035  # Import Declaration Fee (3.5%)
            rdl = cif_value * 0.02   # Railway Development Levy (2%)
            excise_base = cif_value + import_duty
            excise_duty = excise_base * 0.10 if include_excise else 0.0
            
            vatable_value = cif_value + import_duty + excise_duty + idf + rdl
            vat = vatable_value * 0.16  # VAT 16%
            total_landed_cost = vatable_value + vat
            
            st.markdown(
                f"""
                <div class="metric-card" style="margin-bottom: 15px;">
                    <h2>KES {total_landed_cost:,.2f}</h2>
                    <p>Total Estimated Landed Cost</p>
                </div>
                """,
                unsafe_allow_html=True
            )
            duty_breakdown = pd.DataFrame({
                "Tax / Levy Component": ["CIF Value", "Import Duty", "Import Declaration Fee (IDF 3.5%)", "Railway Development Levy (RDL 2%)", "Excise Duty", "Value Added Tax (VAT 16%)", "Total Landed Cost"],
                "Amount (KES)": [cif_value, import_duty, idf, rdl, excise_duty, vat, total_landed_cost]
            })
            st.dataframe(duty_breakdown, use_container_width=True)
        
        st.markdown("---")
        st.markdown("### Executive AI Financial Copilot (Natural Language Query)")
        user_query = st.text_input("Ask a question about your loaded dataset:", placeholder="e.g., What is the total sum and average of the transaction amounts?")
        if user_query:
            if numeric_cols:
                primary_num = numeric_cols[0]
                total_sum = df[primary_num].sum()
                mean_val = df[primary_num].mean()
                max_val = df[primary_num].max()
                st.success(f"**Copilot Analysis:** Based on your query regarding **{primary_num}**, the cumulative total is **{total_sum:,.2f}**, the average is **{mean_val:,.2f}**, and the maximum recorded entry stands at **{max_val:,.2f}** across **{len(df):,}** total rows.")
            else:
                st.info("Please ensure numeric columns are available to run Copilot analytical queries.")
    # --- TAB 9: EXPORT, REPORTS & DIGITAL PEN SIGNATURE ---
    with tab9:
        st.markdown("## Enterprise Export, Executive Reports & Digital Pen Signature")
        st.write("Review final audit findings, capture a manager or partner's handwritten signature using a digital pen/stylus pad, and export comprehensive workbooks and PDF reports.")
        
        # --- Executive Report Table with Explanations ---
        st.markdown("### Executive Report Summary & Findings Table")
        
        total_records = len(df)
        total_attributes = df.shape[1]
        missing_count = int(df.isna().sum().sum())
        primary_metric_val = f"KES {df[numeric_cols[0]].sum():,.2f}" if numeric_cols else "N/A"
        
        report_table_data = [
            {
                "Metric / Parameter": "Total Dataset Entries",
                "Value / Count": f"{total_records:,}",
                "Explanation & Audit Note": "Total number of transactional records processed in the current enterprise suite."
            },
            {
                "Metric / Parameter": "Active Data Attributes",
                "Value / Count": f"{total_attributes}",
                "Explanation & Audit Note": "Total number of columns evaluated for structural integrity and compliance."
            },
            {
                "Metric / Parameter": "Total Missing Data Points",
                "Value / Count": f"{missing_count:,}",
                "Explanation & Audit Note": "Cumulative null cells identified across all features prior to imputation."
            },
            {
                "Metric / Parameter": "Primary Cumulative Metric",
                "Value / Count": primary_metric_val,
                "Explanation & Audit Note": f"Cumulative sum computed from the primary financial column ({numeric_cols[0] if numeric_cols else 'None'})."
            }
        ]
        
        report_summary_df = pd.DataFrame(report_table_data)
        st.dataframe(report_summary_df, use_container_width=True)
        # --- Interactive Digital Pen / Stylus Signature Pad ---
        st.markdown("---")
        st.markdown("### Manager / Partner Digital Pen Signature Pad")
        st.write("Use a mouse, stylus, or touchscreen to physically sign/draw the approval signature below. This signature will be embedded directly into the generated PDF report.")
        
        try:
            from streamlit_drawable_canvas import st_canvas
            
            col_sig1, col_sig2 = st.columns([2, 1])
            with col_sig1:
                st.markdown("<b>Draw Signature Here (Pen / Stylus):</b>", unsafe_allow_html=True)
                canvas_result = st_canvas(
                    fill_color="rgba(255, 255, 255, 0)",
                    stroke_width=3,
                    stroke_color="#002043",
                    background_color="#FFFFFF",
                    background_image=None,
                    update_streamlit=True,
                    height=150,
                    width=450,
                    drawing_mode="freedraw",
                    key="canvas",
                    return_image_data=True,
                )
            with col_sig2:
                st.markdown("<b>Signature Controls:</b>", unsafe_allow_html=True)
                if canvas_result.image_data is not None:
                    if st.button("Capture & Save Signature"):
                        import numpy as np
                        from PIL import Image as PILImage
                        img_array = canvas_result.image_data.astype(np.uint8)
                        sig_image = PILImage.fromarray(img_array)
                        sig_path = "temp_manager_signature.png"
                        sig_image.save(sig_path)
                        st.session_state.signature_image = sig_path
                        st.success("Signature successfully captured and locked for PDF report generation!")
                if st.session_state.signature_image is not None:
                    st.image(st.session_state.signature_image, width=200, caption="Captured Manager Signature")
        except ImportError:
            st.info("Install `streamlit-drawable-canvas` (`pip install streamlit-drawable-canvas`) to enable the interactive drawing pad. Falling back to signature confirmation toggle.")
            manager_approved = st.checkbox("Approve and Authorize Report as Manager / Partner", value=False)
            if manager_approved:
                st.session_state.signature_image = "approved"
        # --- Lead Consultant & Manager Authorization Box ---
        st.markdown(
            """
            <div class="signature-box">
                <h4 style="margin-top:0; color: #AA8336; font-family: 'Marcellus', serif;">Lead Consultant & Partner Authorization Sign-Off</h4>
                <p style="font-size: 0.9rem; color: #EAE3D2; margin-bottom: 20px;">
                I hereby certify that the granular data sanitation, statistical audits, tax compliance checks, and pivot evaluations detailed in this report have been executed in accordance with Westminister Consulting professional standards.
                </p>
                <div style="display: flex; justify-content: space-between; align-items: flex-end; margin-top: 20px;">
                    <div>
                        <p style="margin: 0; font-size: 0.8rem; color: #8E9EA5; text-transform: uppercase;">Lead Consultant:</p>
                        <p style="margin: 5px 0 0 0; font-weight: 600; color: #FFFFFF; font-size: 0.95rem;">Hadi Sheikh Abdullahi</p>
                        <p style="margin: 0; font-size: 0.75rem; color: #AA8336;">Westminister Consulting</p>
                    </div>
                    <div>
                        <p style="margin: 0; font-size: 0.8rem; color: #8E9EA5; text-transform: uppercase;">Date of Verification:</p>
                        <p style="margin: 5px 0 0 0; font-weight: 600; color: #FFFFFF; font-size: 0.95rem;">""" + datetime.now().strftime("%B %d, %Y") + """</p>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
        
        st.markdown("---")
        csv_data = df.to_csv(index=False).encode("utf-8")
        col_ex1, col_ex2 = st.columns(2)
        with col_ex1:
            st.markdown("### Data & Workbook Exports")
            st.download_button(
                label="Download Cleaned CSV",
                data=csv_data,
                file_name="westminster_cleansed_output.csv",
                mime="text/csv",
            )
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                df.to_excel(writer, sheet_name="Cleansed Ledger", index=False)
                report_summary_df.to_excel(writer, sheet_name="Audit Summary & Explanations", index=False)
                if numeric_cols:
                    desc_df = df.describe()
                    desc_df.to_excel(writer, sheet_name="Statistical Summary")
            excel_data = output.getvalue()
            
            st.download_button(
                label="Download Excel Workbook",
                data=excel_data,
                file_name="westminister_audit_suite.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        
        with col_ex2:
            st.markdown("### Executive PDF Report Generator")
            st.caption("Generate the PDF first. The download button will remain available after Streamlit reruns.")

            if st.button("Generate PDF Executive Report", key="generate_enterprise_pdf"):
                try:
                    from reportlab.lib import colors
                    from reportlab.lib.pagesizes import letter
                    from reportlab.lib.utils import ImageReader
                    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, Image as RLImage
                    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

                    pdf_buffer = io.BytesIO()
                    doc = SimpleDocTemplate(
                        pdf_buffer,
                        pagesize=letter,
                        rightMargin=36,
                        leftMargin=36,
                        topMargin=36,
                        bottomMargin=36,
                    )
                    story = []
                    styles = getSampleStyleSheet()
                    title_style = ParagraphStyle(
                        "WestminsterTitleStyle",
                        parent=styles["Heading1"],
                        fontName="Helvetica-Bold",
                        fontSize=15,
                        textColor=colors.HexColor("#AA8336"),
                        spaceAfter=2,
                    )
                    normal_style = styles["Normal"]

                    # Use the uploaded logo in memory; do not rely on a temporary file.
                    logo_img = None
                    logo_bytes = st.session_state.get("logo_bytes")
                    if logo_bytes:
                        try:
                            logo_stream = io.BytesIO(logo_bytes)
                            logo_reader = ImageReader(logo_stream)
                            logo_w, logo_h = logo_reader.getSize()
                            logo_stream.seek(0)
                            logo_img = RLImage(logo_stream, width=130, height=130 * logo_h / logo_w)
                        except Exception:
                            logo_img = None

                    header_data = [[
                        logo_img if logo_img else Paragraph("<b>WESTMINISTER</b>", title_style),
                        Paragraph("<b>WESTMINISTER CONSULTING</b><br/>Enterprise Granular Audit &amp; Financial Report", title_style),
                    ]]
                    header_table = Table(header_data, colWidths=[130, 410])
                    header_table.setStyle(TableStyle([
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                        ("LINEBELOW", (0, 0), (-1, -1), 1.5, colors.HexColor("#AA8336")),
                    ]))
                    story.extend([header_table, Spacer(1, 15)])
                    story.append(Paragraph("<b>Executive Summary &amp; Granular Audit Scope</b>", title_style))
                    summary_text = (
                        f"This report summarises the records processed by Westminister Consulting. "
                        f"A total of <b>{total_records:,}</b> records with <b>{total_attributes}</b> "
                        "attributes were evaluated for structural integrity, data quality, and potential anomalies."
                    )
                    story.extend([Paragraph(summary_text, normal_style), Spacer(1, 10)])

                    pdf_table_data = [["Metric / Parameter", "Value / Count", "Audit Note"]]
                    for row in report_table_data:
                        pdf_table_data.append([
                            str(row.get("Metric / Parameter", "")),
                            str(row.get("Value / Count", "")),
                            str(row.get("Explanation & Audit Note", "")),
                        ])
                    summary_table = Table(pdf_table_data, colWidths=[140, 90, 310], repeatRows=1)
                    summary_table.setStyle(TableStyle([
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#002043")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 8),
                        ("BOTTOMPADDING", (0, 0), (-1, 0), 7),
                        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#F9F9F9")),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]))
                    story.extend([summary_table, Spacer(1, 15)])

                    # Embed the captured signature when available.
                    sig_element = Paragraph("<b>Status:</b> Signature/approval status not supplied", normal_style)
                    signature_image = st.session_state.get("signature_image")
                    if signature_image == "approved":
                        sig_element = Paragraph("<b>Status:</b> Approved by the user", normal_style)
                    elif signature_image and isinstance(signature_image, str) and os.path.exists(signature_image):
                        try:
                            sig_element = RLImage(signature_image, width=150, height=50)
                        except Exception:
                            pass
                    signoff_table = Table([[
                        Paragraph("<b>Lead Consultant:</b><br/>Hadi Sheikh Abdullahi<br/>Westminister Consulting", normal_style),
                        sig_element,
                    ]], colWidths=[270, 270])
                    signoff_table.setStyle(TableStyle([
                        ("LINEABOVE", (0, 0), (-1, 0), 1, colors.HexColor("#AA8336")),
                        ("TOPPADDING", (0, 0), (-1, -1), 8),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ]))
                    story.append(signoff_table)

                    doc.build(story)
                    pdf_bytes = pdf_buffer.getvalue()
                    if not pdf_bytes.startswith(b"%PDF"):
                        raise ValueError("The report generator did not produce a valid PDF file.")

                    st.session_state.enterprise_pdf_bytes = pdf_bytes
                    st.session_state.enterprise_pdf_filename = "Westminister_Enterprise_Audit_Report.pdf"
                    st.success(f"PDF report generated successfully ({len(pdf_bytes):,} bytes). Use the download button below.")
                except Exception as e:
                    st.session_state.enterprise_pdf_bytes = None
                    st.error(f"PDF generation failed: {type(e).__name__}: {e}")

            # Keep this button OUTSIDE the generation-button condition so it survives reruns.
            enterprise_pdf = st.session_state.get("enterprise_pdf_bytes")
            if enterprise_pdf:
                st.download_button(
                    label="Download PDF Executive Report",
                    data=enterprise_pdf,
                    file_name=st.session_state.get("enterprise_pdf_filename", "Westminister_Enterprise_Audit_Report.pdf"),
                    mime="application/pdf",
                    key="download_enterprise_pdf",
                    help="Downloads the generated executive audit report as a PDF file.",
                )
                st.caption("If the download does not start, right-click the button or check your browser's downloads list.")

