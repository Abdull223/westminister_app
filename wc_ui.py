"""wc_ui.py - presentation layer for the Westminister Consulting Intelligence Suite.

Put this file next to west.py, then see the wiring notes at the bottom.
Design: ink-navy surfaces, one brass accent, flat panels (no shadows, no animated
background), tabular numerals for figures. The splash is the single piece of motion.
"""
import base64
import html
import io
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

INK, PANEL, LINE = "#061625", "#0C2238", "#1E3A57"
BRASS, BRASS_FILL = "#C9A24F", "#AA8336"
TEXT, MUTED = "#E8EDF2", "#8FA3B8"
OK, WARN, BAD = "#5FB38A", "#E0A84A", "#E06C6C"
COLORWAY = [BRASS, "#4FA3C7", "#7FB77E", "#B58DB6", "#E0A84A", "#E06C6C"]


# ---------------------------------------------------------------- theme
_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Marcellus&family=IBM+Plex+Sans:wght@400;500;600&display=swap');
:root{--ink:__INK__;--panel:__PANEL__;--line:__LINE__;--brass:__BRASS__;--text:__TEXT__;--muted:__MUTED__}
.stApp{background:var(--ink);color:var(--text);font-family:'IBM Plex Sans',sans-serif}
[data-testid="stHeader"]{background:transparent}
.block-container{max-width:1280px;padding:4.6rem 2rem 3rem}
h1,h2,h3,h4{font-family:'Marcellus',serif!important;color:var(--text)!important;font-weight:400!important;letter-spacing:.2px}
h2{font-size:1.55rem!important}h3{font-size:1.2rem!important;color:var(--brass)!important}
p,li,label,.stMarkdown{color:var(--text)}
.stCaption,[data-testid="stCaptionContainer"]{color:var(--muted)!important}
[data-testid="stSidebar"]{background:#04111e;border-right:1px solid var(--line)}
[data-testid="stSidebar"] h2{font-size:1.05rem!important;color:var(--brass)!important}
/* tabs: underline style */
[data-baseweb="tab-list"]{gap:2px;border-bottom:1px solid var(--line);flex-wrap:wrap}
button[role="tab"]{background:transparent!important;color:var(--muted)!important;padding:.55rem .9rem;border-radius:0;font-weight:500;border-bottom:2px solid transparent}
button[role="tab"]:hover{color:var(--text)!important}
button[role="tab"][aria-selected="true"]{color:var(--text)!important;border-bottom:2px solid var(--brass)}
[data-baseweb="tab-highlight"],[data-baseweb="tab-border"]{display:none}
/* buttons */
.stButton>button,.stDownloadButton>button{background:var(--brass);color:#1a1204;border:0;border-radius:6px;font-weight:600;padding:.5rem 1.1rem}
.stButton>button:hover,.stDownloadButton>button:hover{background:#dbb75f;color:#1a1204}
.stButton>button:focus-visible,.stDownloadButton>button:focus-visible,button[role="tab"]:focus-visible{outline:2px solid #fff;outline-offset:2px}
/* inputs, tables, expanders */
[data-testid="stExpander"]{background:var(--panel);border:1px solid var(--line);border-radius:10px}
[data-testid="stDataFrame"]{border:1px solid var(--line);border-radius:10px;overflow:hidden}
div[data-testid="stMetric"]{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:.8rem 1rem}
div[data-testid="stMetricValue"]{font-variant-numeric:tabular-nums}
[data-testid="stPlotlyChart"]{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:6px}
/* components */
.wc-head{display:flex;align-items:center;justify-content:space-between;padding:4px 0 16px;margin-bottom:18px;border-bottom:1px solid var(--line);min-height:64px}
.wc-head .l{display:flex;align-items:center;gap:16px}.wc-head img{height:56px;width:auto;max-width:200px;object-fit:contain}
.wc-head .t{font-family:'Marcellus',serif;font-size:1.45rem;line-height:1.2;color:var(--text)}
.wc-head .s{color:var(--muted);font-size:.85rem}
.wc-strip{display:grid;grid-template-columns:repeat(4,1fr);border:1px solid var(--line);border-radius:10px;background:var(--panel);margin:0 0 18px}
.wc-strip div{padding:12px 16px;border-left:1px solid var(--line)}.wc-strip div:first-child{border-left:0}
.wc-strip b{display:block;font-size:1.25rem;font-weight:600;font-variant-numeric:tabular-nums;color:var(--text)}
.wc-strip span{color:var(--muted);font-size:.8rem}
.wc-kpi{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--brass);border-radius:10px;padding:14px 16px}
.wc-kpi b{display:block;font-size:1.7rem;font-weight:600;font-variant-numeric:tabular-nums;line-height:1.15}
.wc-kpi span{color:var(--muted);font-size:.82rem}.wc-kpi i{font-style:normal;color:var(--brass);font-size:.8rem;display:block;margin-top:2px}
.wc-note{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 16px;margin:8px 0;line-height:1.55;font-size:.93rem}
.wc-flag{display:flex;gap:12px;align-items:flex-start;padding:10px 14px;border:1px solid var(--line);border-radius:10px;background:var(--panel);margin:6px 0}
.wc-flag .dot{flex:0 0 10px;height:10px;border-radius:50%;margin-top:6px}
.wc-flag small{color:var(--muted)}
@media (max-width:760px){.wc-strip{grid-template-columns:repeat(2,1fr)}.block-container{padding:1rem}}
</style>
"""


def inject_theme():
    css = (_CSS.replace("__INK__", INK).replace("__PANEL__", PANEL).replace("__LINE__", LINE)
           .replace("__BRASS__", BRASS).replace("__TEXT__", TEXT).replace("__MUTED__", MUTED))
    st.markdown(css, unsafe_allow_html=True)


def style_fig(fig, height=340):
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      colorway=COLORWAY, height=height, margin=dict(l=10, r=10, t=50, b=10),
                      font=dict(family="IBM Plex Sans, sans-serif", color=TEXT), title=dict(font=dict(size=15)))
    fig.update_xaxes(gridcolor=LINE, zeroline=False)
    fig.update_yaxes(gridcolor=LINE, zeroline=False)
    return fig


# ---------------------------------------------------------------- splash
_SPLASH = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Marcellus&family=IBM+Plex+Sans:wght@400&display=swap');
@property --p{syntax:'<integer>';inherits:false;initial-value:0}
.wcs{position:fixed;inset:0;z-index:99999;background:radial-gradient(ellipse at 50% 38%,#0e2a47 0%,#061625 55%,#030c16 100%);display:flex;flex-direction:column;align-items:center;justify-content:center;animation:wcsOut .7s ease 4s forwards}
@keyframes wcsOut{to{opacity:0;visibility:hidden;pointer-events:none}}
.wcs-rules{position:absolute;inset:0;background:repeating-linear-gradient(to bottom,transparent 0 47px,rgba(201,162,79,.08) 47px 48px);clip-path:inset(0 100% 0 0);animation:wcsDraw 1.8s ease .1s forwards}
@keyframes wcsDraw{to{clip-path:inset(0 0 0 0)}}
.wcs-glow{position:absolute;width:520px;height:520px;border-radius:50%;background:radial-gradient(circle,rgba(201,162,79,.18),transparent 65%);opacity:0;animation:wcsGlow 2.4s ease .8s forwards}
@keyframes wcsGlow{to{opacity:1}}
.wcs-seal{position:relative;width:170px;height:170px;display:grid;place-items:center}
.wcs-seal svg{position:absolute;inset:0}
.wcs-seal circle{fill:none;stroke:#C9A24F;stroke-width:1.6;stroke-dasharray:380;stroke-dashoffset:380;animation:wcsRing 2s ease .3s forwards}
.wcs-seal circle+circle{stroke:rgba(201,162,79,.4);stroke-dasharray:440;stroke-dashoffset:440;animation-delay:.7s}
.wcs-seal circle+circle+circle{stroke:rgba(232,237,242,.18);stroke-dasharray:500;stroke-dashoffset:500;animation-delay:1.1s}
@keyframes wcsRing{to{stroke-dashoffset:0}}
.wcs-seal img{width:96px;opacity:0;animation:wcsIn .9s ease 1.2s forwards}
@keyframes wcsIn{to{opacity:1}}
.wcs h1{font-family:'Marcellus',serif;font-weight:400;font-size:2.4rem;letter-spacing:3px;margin:30px 0 8px;opacity:0;
 background:linear-gradient(100deg,#E8EDF2 35%,#E9C46A 50%,#E8EDF2 65%);background-size:260% 100%;background-position:100% 0;-webkit-background-clip:text;background-clip:text;color:transparent;
 animation:wcsIn .9s ease 1.5s forwards,wcsShine 2.2s ease 2.2s forwards}
@keyframes wcsShine{to{background-position:0 0}}
.wcs p{font-family:'IBM Plex Sans',sans-serif;color:#9fb2c5;font-size:1rem;margin:0;opacity:0;animation:wcsIn .9s ease 1.9s forwards}
.wcs-pct{--p:0;counter-reset:p var(--p);margin-top:34px;font:500 .95rem 'IBM Plex Sans',sans-serif;color:#C9A24F;font-variant-numeric:tabular-nums;animation:wcsCount 3.4s cubic-bezier(.45,0,.2,1) .3s forwards}
.wcs-pct::after{content:counter(p) "%"}
@keyframes wcsCount{to{--p:100}}
.wcs-msg{position:relative;height:18px;width:340px;margin-top:10px;text-align:center;font:400 .82rem 'IBM Plex Sans',sans-serif;color:#8FA3B8}
.wcs-msg i{position:absolute;left:0;right:0;opacity:0;font-style:normal;animation:wcsMsg 3.6s ease forwards}
.wcs-msg i:nth-child(2){animation-delay:1.2s}.wcs-msg i:nth-child(3){animation-delay:2.4s}
@keyframes wcsMsg{0%{opacity:0}15%,40%{opacity:1}55%,100%{opacity:0}}
@media (prefers-reduced-motion:reduce){.wcs{animation-delay:.8s}.wcs *{animation-duration:.01s!important;animation-delay:0s!important}}
</style>
<div class="wcs"><div class="wcs-rules"></div><div class="wcs-glow"></div>
<div class="wcs-seal"><svg viewBox="0 0 170 170"><circle cx="85" cy="85" r="60"/><circle cx="85" cy="85" r="69"/><circle cx="85" cy="85" r="78"/></svg><img src="__SRC__" alt=""></div>
<h1>Westminister Consulting</h1><p>Data you can sign off on</p>
<div class="wcs-pct"></div>
<div class="wcs-msg"><i>Opening the audit workspace</i><i>Loading cleaning and checking tools</i><i>Ready for your file</i></div></div>
"""


def show_splash(logo_bytes=None, logo_url=""):
    """Call once, early. No sleep, no rerun: the overlay fades itself out in CSS."""
    if st.session_state.get("splash_shown"):
        return
    st.session_state.splash_shown = True
    src = ("data:image/png;base64," + base64.b64encode(logo_bytes).decode()) if logo_bytes else logo_url
    st.markdown(_SPLASH.replace("__SRC__", src), unsafe_allow_html=True)


# ---------------------------------------------------------------- components
def app_header(logo_bytes=None, logo_url="", user="guest"):
    src = ("data:image/png;base64," + base64.b64encode(logo_bytes).decode()) if logo_bytes else logo_url
    st.markdown(f'<div class="wc-head"><div class="l"><img src="{src}" alt=""><div class="t">Westminister Intelligence Suite</div></div>'
                f'<div class="s">Signed in as {html.escape(str(user))}</div></div>', unsafe_allow_html=True)


def kpi_row(items):
    """items: [(label, value, note_or_None), ...]"""
    cols = st.columns(len(items))
    for c, (lab, val, note) in zip(cols, items):
        c.markdown(f'<div class="wc-kpi"><b>{html.escape(str(val))}</b><span>{html.escape(str(lab))}</span>'
                   + (f'<i>{html.escape(str(note))}</i>' if note else "") + "</div>", unsafe_allow_html=True)


def note(text):
    st.markdown(f'<div class="wc-note">{html.escape(str(text))}</div>', unsafe_allow_html=True)


def evidence_strip(rows, quality, checks_ok, checks_total, fingerprint):
    """One line of proof that the numbers can be trusted."""
    st.markdown('<div class="wc-strip">'
                f'<div><b>{rows:,}</b><span>records analysed</span></div>'
                f'<div><b>{quality:.0f}%</b><span>overall data quality</span></div>'
                f'<div><b>{checks_ok}/{checks_total}</b><span>integrity checks passed</span></div>'
                f'<div><b>{html.escape(str(fingerprint))}</b><span>data fingerprint</span></div></div>', unsafe_allow_html=True)


def review_items(issues, limit=6):
    if issues is None or not len(issues):
        st.success("The checks found nothing that needs review.")
        return
    colour = {"High": BAD, "Medium": WARN, "Low": MUTED}
    for _, r in issues.head(limit).iterrows():
        st.markdown(
            f'<div class="wc-flag"><span class="dot" style="background:{colour.get(r["Severity"], MUTED)}"></span><div>'
            f'<b>{html.escape(str(r["Check"]))}</b> in {html.escape(str(r["Columns"]))}: {int(r["Rows affected"]):,} rows<br>'
            f'<small>{html.escape(str(r["Suggested action"]))}</small></div></div>', unsafe_allow_html=True)
    st.caption("These are review indicators, not findings of error. Check the source records first.")


def briefing(U, quality, rows, analysis_ready):
    """The first thing a partner sees: how healthy is this file, what matters, what to do next."""
    iss = U["issues"]
    high = int((iss["Severity"] == "High").sum()) if len(iss) else 0
    g, t = st.columns([1, 1.7])
    with g:
        f = go.Figure(go.Indicator(mode="gauge+number", value=round(quality), number=dict(suffix="%", font=dict(size=44, color=TEXT)),
                      title=dict(text="Data health", font=dict(size=14, color=MUTED)),
                      gauge=dict(axis=dict(range=[0, 100], tickcolor=LINE), bar=dict(color=BRASS, thickness=.28), bgcolor=PANEL, borderwidth=0,
                                 steps=[dict(range=[0, 60], color="#3a2327"), dict(range=[60, 85], color="#33301f"), dict(range=[85, 100], color="#1d3329")])))
        st.plotly_chart(style_fig(f, 230), width="stretch")
    with t:
        worst = (f"{iss.iloc[0]['Check']} in {iss.iloc[0]['Columns']} ({int(iss.iloc[0]['Rows affected']):,} rows)") if len(iss) else "nothing needs review"
        if high:
            nxt = f"Review the {high} high-severity item{'s' if high != 1 else ''} below before relying on any totals."
        elif not analysis_ready:
            nxt = "Open the Autopilot tab and run the full analysis, then build the signed report in tab 6."
        else:
            nxt = "Build the signed management report in tab 6."
        st.markdown("### 30-second briefing")
        note(f"This looks like {U['type'].lower()}: {rows:,} records, read with {U['conf']}% confidence.")
        note(f"Biggest thing to know: {worst}.")
        note(f"Do next: {nxt}")


# ---------------------------------------------------------------- executive dashboard
def render_dashboard(df, raw_df, U, kd, quality, checks, fingerprint, insights=()):
    """Replace the body of `with tab_dash:` with:
        render_dashboard(df, raw_df, U, kd, QD["overall"], INTEG, _fp, s_insights)
    checks = INTEG list of (name, ok, detail); _fp = fingerprint(df)."""
    cats = [c for c in U["dims"] if c in df.columns][:4]
    dates = [c for c in U["dates"] if c in df.columns]
    metric = U["metric"] if U["metric"] in df.columns else None
    ok = sum(1 for _, o, _ in checks if o)
    st.markdown("## Executive overview")
    briefing(U, quality, len(df), bool(st.session_state.get("_run_autopilot")))
    evidence_strip(len(df), quality, ok, len(checks), fingerprint)

    flt = df
    with st.expander("Filters"):
        fc = st.columns(2)
        for i, c in enumerate(cats):
            vals = sorted(df[c].dropna().astype(str).unique())[:100]
            pick = fc[i % 2].multiselect(c, vals, key=f"wcf_{c}")
            if pick:
                flt = flt[flt[c].astype(str).isin(pick)]
    st.caption(f"Showing {len(flt):,} of {len(df):,} records")

    raw_blank, now_blank = int(raw_df.isna().sum().sum()), int(df.isna().sum().sum())
    items = [("Records", f"{len(flt):,}", None)]
    if metric:
        tot = pd.to_numeric(flt[metric], errors="coerce")
        items += [(f"Total {metric}" if U["roles"][metric][0] in ("money", "quantity") else f"Average {metric}",
                   f"{(tot.sum() if U['roles'][metric][0] in ('money', 'quantity') else tot.mean()):,.0f}", None)]
    items += [("Blank cells fixed", f"{raw_blank - now_blank:,}", f"{raw_blank:,} before"),
              ("Items to review", f"{len(U['issues']):,}", "see below")]
    kpi_row(items)

    left, right = st.columns([1.4, 1])
    with left:
      try:
        if dates and metric and len(flt):
            d = flt[[dates[0], metric]].dropna()
            if len(d):
                how = "sum" if U["roles"][metric][0] in ("money", "quantity") else "mean"
                t = d.set_index(dates[0])[metric].resample("MS").agg(how).reset_index()
                f = px.area(t, x=dates[0], y=metric, title=f"{'Monthly total' if how == 'sum' else 'Monthly average'} of {metric}")
                f.update_traces(line=dict(width=2.5), fillcolor="rgba(201,162,79,.14)")
                st.plotly_chart(style_fig(f), width="stretch")
        else:
            note("A trend chart appears when the file has a date column and a numeric measure.")
      except Exception as e:
        note(f"The trend chart could not be drawn for this file: {e}")
    with right:
      try:
        if cats and len(flt):
            c = st.selectbox("Group by", cats, key="wc_grp")
            if metric:
                g = flt.groupby(c)[metric].sum().sort_values(ascending=False).head(10)
                title = f"Top {c} by {metric}"
            else:
                g = flt[c].value_counts().head(10)
                title = f"Top {c} by records"
            gd = g[::-1].rename_axis("label").reset_index(name="value")
            gd["label"] = gd["label"].astype(str)
            f = px.bar(gd, x="value", y="label", orientation="h", title=title)
            f.update_layout(showlegend=False, xaxis_title=None, yaxis_title=None)
            st.plotly_chart(style_fig(f), width="stretch")
      except Exception as e:
        note(f"The group chart could not be drawn for this file: {e}")

    st.markdown("### Needs review")
    review_items(U["issues"])
    if insights:
        st.markdown("### What the data says")
        for s in list(insights)[:4]:
            note(s)
    with st.expander("Search the cleaned records"):
        q = st.text_input("Search text columns", key="wc_search")
        txt = [c for c in df.columns if kd.get(c) in ("category", "text", "id")]
        view = df
        if q and txt:
            m = np.zeros(len(df), dtype=bool)
            for c in txt:
                m |= df[c].astype(str).str.contains(q, case=False, na=False, regex=False).values
            view = df[m]
        st.caption(f"{len(view):,} matching records")
        st.dataframe(view.head(2000), width="stretch", hide_index=True, height=380)


# ---------------------------------------------------------------- start page, empty state, report pre-flight
def _dot(state):
    return {"done": OK, "attention": WARN, "todo": MUTED}[state]


def _checklist(rows):
    for state, title, detail in rows:
        st.markdown(f'<div class="wc-flag"><span class="dot" style="background:{_dot(state)}"></span><div>'
                    f'<b>{html.escape(title)}</b><br><small>{html.escape(detail)}</small></div></div>', unsafe_allow_html=True)


def render_start(rows, issues, n_clean, analysed, signed, built):
    """Where you are in the job, and what to do next."""
    high = int((issues["Severity"] == "High").sum()) if len(issues) else 0
    st.markdown("## Where you are")
    steps = [
        ("done", "1. File loaded and cleaned", f"{rows:,} records; {n_clean} cleaning actions are logged in tab 2."),
        ("attention" if high else "done", "2. Review what the checks found",
         f"{high} high-severity item(s) need a look in tab 1." if high else (f"{len(issues)} lower-priority item(s) listed in tab 1." if len(issues) else "Nothing flagged.")),
        ("done" if analysed else "todo", "3. Run the full analysis", "Done." if analysed else "Open the Autopilot tab and press Run full statistical analysis."),
        ("done" if (signed and built) else "todo", "4. Sign and download the report",
         "Report built and signed." if (signed and built) else "Tab 6: draw your signature, then build the PDF."),
    ]
    _checklist(steps)
    nxt = next((t for st_, t, _ in steps if st_ != "done"), None)
    note("Next: " + nxt[3:] + "." if nxt else "Everything is done. Download the report from tab 6.")


def report_preflight(client, signer, signed, issues, analysed, integ):
    """Shown above the Build button: what the report will and will not contain."""
    high = int((issues["Severity"] == "High").sum()) if len(issues) else 0
    ok_all = all(o for _, o, _ in integ)
    rows = [
        ("done" if str(client).strip() else "attention", "Client name", str(client).strip() or "Empty. Enter it in the sidebar so the cover page names the client."),
        ("done" if str(signer).strip() else "attention", "Approver", str(signer).strip() or "Empty."),
        ("done" if signed else "attention", "Signature", "Captured." if signed else "Not signed yet. The report will say 'Not signed'."),
        ("done" if analysed else "attention", "Full analysis", "Included." if analysed else "Not run. The report will have no analysis section."),
        ("done" if ok_all else "attention", "Integrity checks", "All passed." if ok_all else "At least one check needs review (see Autopilot tab)."),
        ("done" if not high else "attention", "High-severity items", "None." if not high else f"{high} still listed in the report as open."),
    ]
    st.markdown("### Before you build")
    _checklist(rows)


def empty_state():
    """First screen, before any file is loaded."""
    st.markdown("## Bring in a file")
    note("Upload a CSV or Excel file in the sidebar. The app finds what it is, cleans it, checks it, analyses it and writes a signed report. Every change is logged.")
    _checklist([("todo", "1. Upload", "Use the Data Ingestion Center in the sidebar."),
                ("todo", "2. Review", "See what was found and fixed, and the items that need a decision."),
                ("todo", "3. Sign and download", "Draw your signature and download the PDF and Excel pack.")])
    st.caption("Files are processed on this computer. Only summary numbers leave it, and only if you switch on AI commentary.")


# ---------------------------------------------------------------- sample data
def make_sample_csv(n=600, seed=7):
    """A realistic sales ledger with planted problems, so first-time users see the checks work."""
    r = np.random.default_rng(seed)
    days = pd.date_range("2025-01-01", "2026-09-30", freq="D")
    df = pd.DataFrame({
        "Invoice No": [f"INV-{1000 + i}" for i in range(n)],
        "Invoice Date": r.choice(days, n),
        "Customer": r.choice(["Savannah Traders", "Lake Basin Foods", "Rift Hardware", "Coastline Logistics", "Highland Pharmacy", "Mara Supplies"], n),
        "County": r.choice(["Nairobi", "Mombasa", "Kisumu", "Nakuru", "Eldoret"], n, p=[.38, .22, .15, .15, .10]),
        "Quantity": r.integers(1, 60, n),
        "Unit Price": r.choice([450, 1200, 2300, 5800, 9900], n),
    })
    df["Total Amount"] = df["Quantity"] * df["Unit Price"]
    df["KRA PIN"] = [f"{r.choice(['A', 'P'])}{r.integers(0, 10**9):09d}{r.choice(list('ABCDEFGH'))}" for _ in range(n)]
    df.loc[5, "KRA PIN"] = "12345"
    df.loc[17, "Total Amount"] = -abs(df.loc[17, "Total Amount"])
    df.loc[40, "Total Amount"] = df.loc[40, "Total Amount"] * 25
    df.loc[::37, "County"] = np.nan
    df.loc[3, "County"] = "nairobi"
    df = pd.concat([df, df.sample(6, random_state=1)], ignore_index=True)
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


# ---------------------------------------------------------------- wiring notes
# 1. west.py, right after st.set_page_config(...):
#        import wc_ui
#        wc_ui.inject_theme()
#        wc_ui.show_splash(load_logo(), LOGO_URL)
#    and delete the old splash block (time.sleep + st.rerun) and the big global <style> blocks.
# 2. Replace the old header markdown with:
#        wc_ui.app_header(st.session_state.logo_bytes, LOGO_URL, _USER)   # after _USER is set
# 3. Dashboard tab:   with tab_dash:
#        wc_ui.render_dashboard(df, raw_df, U, kd, QD["overall"], INTEG, _fp_dash, s_insights)
#    where  _fp_dash = memo("fp", _dk, lambda: fingerprint(df))
# 4. Sidebar sample button (after the file uploaders):
#        if st.sidebar.button("Try with sample data"):
#            b = wc_ui.make_sample_csv()
#            raw, clean, log, sc = _cached_load_and_clean(b, "sample_sales_ledger.csv", None, opt_fill, opt_dupe)
#            st.session_state.update(raw_df=raw, df=clean, clean_log=log, schema=sc, _pk=("sample",), _run_autopilot=False)
#            st.rerun()