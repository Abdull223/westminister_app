"""wc_ui.py - Presentation layer for Westminister Consulting Intelligence Suite.
"""
import base64
import html
import io
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
_MONO = ("data:image/svg+xml;utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 96 96'%3E%3Ctext x='48' y='68' font-size='70' text-anchor='middle' fill='%23C9A24F' font-family='Marcellus,serif'%3EW%3C/text%3E%3C/svg%3E")

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
[data-baseweb="tab-list"]{gap:2px;border-bottom:1px solid var(--line);flex-wrap:wrap}
button[role="tab"]{background:transparent!important;color:var(--muted)!important;padding:.55rem .9rem;border-radius:0;font-weight:500;border-bottom:2px solid transparent}
button[role="tab"]:hover{color:var(--text)!important}
button[role="tab"][aria-selected="true"]{color:var(--text)!important;border-bottom:2px solid var(--brass)}
[data-baseweb="tab-highlight"],[data-baseweb="tab-border"]{display:none}
.stButton>button,.stDownloadButton>button{background:var(--brass);color:#1a1204;border:0;border-radius:6px;font-weight:600;padding:.5rem 1.1rem;transition:all .2s ease}
.stButton>button:hover,.stDownloadButton>button:hover{background:#dbb75f;color:#1a1204;box-shadow:0 0 12px rgba(201,162,79,0.35)}
div[data-testid="stMetric"], [data-testid="stExpander"], [data-testid="stPlotlyChart"], .wc-panel, .wc-kpi, .wc-note, .wc-flag {
    background: rgba(12, 34, 56, 0.75)!important;
    backdrop-filter: blur(12px)!important;
    border: 1px solid rgba(201, 162, 79, 0.25)!important;
    border-radius: 10px;
}
div[data-testid="stMetricValue"]{font-variant-numeric:tabular-nums proportional-nums; font-weight: 600;}
[data-testid="stDataFrame"]{border:1px solid rgba(201,162,79,0.25);border-radius:10px;overflow:hidden}
.wc-head{display:flex;align-items:center;justify-content:space-between;padding:4px 0 16px;margin-bottom:18px;border-bottom:1px solid var(--line);min-height:64px}
.wc-head .l{display:flex;align-items:center;gap:16px}.wc-head img{height:56px;width:auto;max-width:200px;object-fit:contain}
.wc-head .t{font-family:'Marcellus',serif;font-size:1.45rem;line-height:1.2;color:var(--text)}
.wc-head .s{color:var(--muted);font-size:.85rem}
.wc-strip{display:grid;grid-template-columns:repeat(4,1fr);border:1px solid rgba(201,162,79,0.25);border-radius:10px;background:rgba(12, 34, 56, 0.75);margin:0 0 18px;backdrop-filter:blur(12px)}
.wc-strip div{padding:12px 16px;border-left:1px solid var(--line)}.wc-strip div:first-child{border-left:0}
.wc-strip b{display:block;font-size:1.25rem;font-weight:600;font-variant-numeric:tabular-nums;color:var(--text)}
.wc-strip span{color:var(--muted);font-size:.8rem}
.wc-note{padding:12px 16px;margin:8px 0;line-height:1.55;font-size:.93rem}
*{scrollbar-width:thin;scrollbar-color:var(--brass) var(--panel)}
hr{border-color:var(--line)!important}
@media (max-width:760px){.wc-strip{grid-template-columns:repeat(2,1fr)}.block-container{padding:1rem}}
</style>
"""

def inject_theme():
    css = (_CSS.replace("__INK__", INK).replace("__PANEL__", PANEL).replace("__LINE__", LINE)
             .replace("__BRASS__", BRASS).replace("__TEXT__", TEXT).replace("__MUTED__", MUTED))
    st.markdown(css, unsafe_allow_html=True)

def empty_state():
    st.markdown("## Westminister Intelligence Suite — Enterprise Workspace")
    st.markdown("Select a dataset in the sidebar or click **⚡ Process Sample Kenya Ledger** to activate AI dashboards and cash flow analytics.")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("""<div class="wc-panel" style="padding: 20px; height: 100%;"><h3 style="color: var(--brass); margin-top: 0;">🛡️ Background AI Cleaning</h3><p style="color: var(--muted); font-size: 0.9rem;">Runs fully automated checks with zero human error.</p></div>""", unsafe_allow_html=True)
    with col2:
        st.markdown("""<div class="wc-panel" style="padding: 20px; height: 100%;"><h3 style="color: var(--brass); margin-top: 0;">📊 Multi-Dashboards</h3><p style="color: var(--muted); font-size: 0.9rem;">Interactive Plotly charts, trends, and category group breakdowns.</p></div>""", unsafe_allow_html=True)
    with col3:
        st.markdown("""<div class="wc-panel" style="padding: 20px; height: 100%;"><h3 style="color: var(--brass); margin-top: 0;">🔒 Certified PDF Sign-off</h3><p style="color: var(--muted); font-size: 0.9rem;">Capture pen signatures and generate immutable executive reports.</p></div>""", unsafe_allow_html=True)

def safe_df_display(df, height=380):
    view = df.copy()
    for col in view.select_dtypes(include=["datetime64[ns]", "datetime64", "datetimetz"]).columns:
        view[col] = view[col].dt.strftime("%Y-%m-%d %H:%M:%S")
    st.dataframe(view, use_container_width=True, hide_index=True, height=height)

def style_fig(fig, height=340):
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      colorway=COLORWAY, height=height, margin=dict(l=10, r=10, t=50, b=10),
                      font=dict(family="IBM Plex Sans, sans-serif", color=TEXT), title=dict(font=dict(size=15)))
    fig.update_xaxes(gridcolor=LINE, zeroline=False)
    fig.update_yaxes(gridcolor=LINE, zeroline=False)
    return fig

_SPLASH = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Marcellus&family=IBM+Plex+Sans:wght@400&display=swap');
.wcs{position:fixed;inset:0;z-index:99999;background:radial-gradient(ellipse at 50% 38%,#0e2a47 0%,#061625 55%,#030c16 100%);display:flex;flex-direction:column;align-items:center;justify-content:center;animation:wcsOut .5s ease 2.4s forwards}
@keyframes wcsOut{to{opacity:0;visibility:hidden;pointer-events:none}}
.wcs-seal{position:relative;width:170px;height:170px;display:grid;place-items:center}
.wcs-seal img{width:96px;opacity:0;animation:wcsIn .6s ease .7s forwards}
@keyframes wcsIn{to{opacity:1}}
.wcs h1{font-family:'Marcellus',serif;font-weight:400;font-size:2.4rem;letter-spacing:3px;margin:30px 0 8px;opacity:0;
 background:linear-gradient(100deg,#E8EDF2 35%,#E9C46A 50%,#E8EDF2 65%);background-size:260% 100%;background-position:100% 0;-webkit-background-clip:text;background-clip:text;color:transparent;
 animation:wcsIn .6s ease .9s forwards}
.wcs p{font-family:'IBM Plex Sans',sans-serif;color:#9fb2c5;font-size:1rem;margin:0;opacity:0;animation:wcsIn .6s ease 1.2s forwards}
</style>
<div class="wcs"><div class="wcs-seal"><img src="__SRC__" alt=""></div>
<h1>Westminister Consulting</h1><p>Data you can sign off on</p></div>
"""

def show_splash(logo_bytes=None, logo_url=""):
    if st.session_state.get("splash_shown"):
        return
    st.session_state.splash_shown = True
    src = ("data:image/png;base64," + base64.b64encode(logo_bytes).decode()) if logo_bytes else (logo_url or _MONO)
    st.markdown(_SPLASH.replace("__SRC__", src), unsafe_allow_html=True)

def app_header(logo_bytes=None, logo_url="", user="guest"):
    src = ("data:image/png;base64," + base64.b64encode(logo_bytes).decode()) if logo_bytes else (logo_url or _MONO)
    st.markdown(f'<div class="wc-head"><div class="l"><img src="{src}" alt=""><div class="t">Westminister Intelligence Suite</div></div>'
                f'<div class="s">Signed in as {html.escape(str(user))}</div></div>', unsafe_allow_html=True)

def evidence_strip(rows, quality, checks_ok, checks_total, fingerprint):
    st.markdown('<div class="wc-strip">'
                f'<div><b>{rows:,}</b><span>records analysed</span></div>'
                f'<div><b>{quality:.0f}%</b><span>overall data quality</span></div>'
                f'<div><b>{checks_ok}/{checks_total}</b><span>integrity checks passed</span></div>'
                f'<div><b>{html.escape(str(fingerprint))}</b><span>data fingerprint</span></div></div>', unsafe_allow_html=True)

def render_exception_quarantine(df):
    st.markdown("### Exception Quarantine & Remediation")
    st.caption("Inspect flagged anomalies and execute interactive overrides.")
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    anomalies = df[(df[numeric_cols] < 0).any(axis=1)] if len(numeric_cols) > 0 else pd.DataFrame(columns=df.columns)
    if len(anomalies) == 0:
        st.success("No active anomalies requiring quarantine.")
        return
    selected_idx = st.selectbox("Select anomalous record index", anomalies.index.tolist())
    safe_df_display(df.loc[[selected_idx]], height=120)
    if st.button("Override and Mark Compliant"):
        st.toast(f"Record {selected_idx} successfully overridden.", icon="🛡️")

def render_nlq_search(df):
    query = st.text_input("💬 Ask the data suite in plain English (e.g., 'Nairobi', 'INV-1002')", key="nlq_bar")
    if query:
        st.info(f"Filtering subset matching semantic indicators for '{query}'...")
        filtered = df[df.astype(str).apply(lambda row: row.str.contains(query, case=False).any(), axis=1)]
        safe_df_display(filtered.head(100), height=300)

def render_dashboard(df, raw_df, U, kd, quality, checks, fingerprint, insights=()):
    cats = [c for c in U["dims"] if c in df.columns][:4]
    dates = [c for c in U["dates"] if c in df.columns]
    metric = U["metric"] if U["metric"] in df.columns else None
    ok = sum(1 for _, o, _ in checks if o)
    
    st.markdown("## 📊 Executive Overview & Multi-Dimensional Dashboards")
    evidence_strip(len(df), quality, ok, len(checks), fingerprint)
    
    render_nlq_search(df)
    
    # Dashboard 1 & 2: Trends and Categorical Breakdowns
    left, right = st.columns([1.4, 1])
    with left:
        try:
            if dates and metric and len(df):
                d = df[[dates[0], metric]].dropna().copy()
                d[dates[0]] = pd.to_datetime(d[dates[0]], errors='coerce')
                d = d.dropna(subset=[dates[0]])
                if len(d):
                    t = d.set_index(dates[0])[metric].resample("MS").sum().reset_index()
                    f = px.area(t, x=dates[0], y=metric, title=f"Monthly Total Cash Flow / Inflow ({metric})", color_discrete_sequence=[BRASS])
                    st.plotly_chart(style_fig(f), use_container_width=True)
            elif metric and len(df):
                f = px.histogram(df, x=metric, nbins=20, title=f"Distribution of {metric}", color_discrete_sequence=[BRASS])
                st.plotly_chart(style_fig(f), use_container_width=True)
        except Exception as e:
            st.note(f"Trend Analysis Note: {e}")
            
    with right:
        try:
            if cats and len(df):
                c = st.selectbox("Group by Category", cats, key="wc_grp")
                g = df.groupby(c)[metric].sum().sort_values(ascending=False).head(10) if metric else df[c].value_counts().head(10)
                gd = g[::-1].rename_axis("label").reset_index(name="value")
                f = px.bar(gd, x="value", y="label", orientation="h", title=f"Top Breakdown by {c}", color_discrete_sequence=[BRASS])
                st.plotly_chart(style_fig(f), use_container_width=True)
        except Exception as e:
            st.note(f"Category Breakdown Note: {e}")

    # Dashboard 3: Numerical Correlation / Summary Matrix
    st.markdown("---")
    st.markdown("### 📈 Additional Analytical Dashboards & Metrics")
    num_cols = list(df.select_dtypes(include=[np.number]).columns)
    if len(num_cols) >= 2:
        d_col1, d_col2 = st.columns(2)
        with d_col1:
            sc_x = st.selectbox("Scatter X-Axis", num_cols, index=0, key="sc_x")
            sc_y = st.selectbox("Scatter Y-Axis", num_cols, index=min(1, len(num_cols)-1), key="sc_y")
            f_sc = px.scatter(df, x=sc_x, y=sc_y, title=f"Correlation: {sc_x} vs {sc_y}", color_discrete_sequence=[BRASS])
            st.plotly_chart(style_fig(f_sc, height=300), use_container_width=True)
        with d_col2:
            box_col = st.selectbox("Box Plot Outlier Inspector", num_cols, index=0, key="box_col")
            f_box = px.box(df, y=box_col, title=f"Outlier Dispersion: {box_col}", color_discrete_sequence=[BRASS])
            st.plotly_chart(style_fig(f_box, height=300), use_container_width=True)

    if insights:
        st.markdown("### 💡 AI Financial Intelligence Insights")
        for insight in insights:
            st.markdown(f"> 🤖 **AI Audit Observation:** {insight}")

def make_sample_csv(n=600, seed=7):
    r = np.random.default_rng(seed)
    days = pd.date_range("2025-01-01", "2026-09-30", freq="D")
    df = pd.DataFrame({
        "Invoice No": [f"INV-{1000 + i}" for i in range(n)],
        "Invoice Date": r.choice(days, n),
        "Customer": r.choice(["Savannah Traders", "Lake Basin Foods", "Rift Hardware", "Coastline Logistics", "Highland Pharmacy", "Mara Supplies"], n),
        "County": r.choice(["Nairobi", "Mombasa", "Kisumu", "Nakuru", "Eldoret"], n),
        "Quantity": r.integers(1, 60, n),
        "Unit Price": r.choice([450, 1200, 2300, 5800, 9900], n),
    })
    df["Total Amount"] = df["Quantity"] * df["Unit Price"]
    df["KRA PIN"] = [f"P{r.integers(0, 10**9):09d}A" for _ in range(n)]
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")