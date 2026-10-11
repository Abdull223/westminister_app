"""Brand theme, animated background, splash and chrome for the Westminister Intelligence Suite."""

import base64
import html

import streamlit as st

INK = "#061625"
PANEL = "#0C2238"
LINE = "#1E3A57"
BRASS = "#C9A24F"
TEXT = "#E8EDF2"
MUTED = "#8FA3B8"
OK = "#5FB38A"
WARN = "#E0A84A"
BAD = "#E06C6C"
COLORWAY = [BRASS, "#4FA3C7", "#7FB77E", "#B58DB6", "#E0A84A", "#E06C6C"]

_MONO = (
    "data:image/svg+xml;utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 96 96'%3E"
    "%3Ctext x='48' y='68' font-size='70' text-anchor='middle' fill='%23C9A24F' "
    "font-family='Marcellus,serif'%3EW%3C/text%3E%3C/svg%3E"
)

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Marcellus&family=IBM+Plex+Sans:wght@400;500;600&display=swap');
:root{--wc-ink:__INK__;--wc-panel:__PANEL__;--wc-line:__LINE__;--wc-brass:__BRASS__;--wc-text:__TEXT__;--wc-muted:__MUTED__}

/* ---------- animated aurora background ---------- */
.stApp{background:var(--wc-ink);color:var(--wc-text);font-family:'IBM Plex Sans',sans-serif}
.stApp::before{content:"";position:fixed;inset:-30%;z-index:0;pointer-events:none;opacity:.55;
  background:
    radial-gradient(38% 30% at 18% 22%, rgba(201,162,79,.14), transparent 70%),
    radial-gradient(42% 34% at 82% 18%, rgba(79,163,199,.13), transparent 70%),
    radial-gradient(46% 38% at 55% 88%, rgba(12,34,56,.9), transparent 70%),
    radial-gradient(30% 26% at 8% 82%, rgba(181,141,182,.08), transparent 70%);
  animation:wcDrift 26s ease-in-out infinite alternate}
@keyframes wcDrift{
  0%{transform:translate3d(0,0,0) scale(1)}
  50%{transform:translate3d(2.5%, -2%, 0) scale(1.06)}
  100%{transform:translate3d(-2%, 2.5%, 0) scale(1.03)}}
/* fine grain overlay for depth */
.stApp::after{content:"";position:fixed;inset:0;z-index:0;pointer-events:none;opacity:.035;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='140' height='140'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2'/%3E%3C/filter%3E%3Crect width='140' height='140' filter='url(%23n)'/%3E%3C/svg%3E")}
header[data-testid="stHeader"],[data-testid="stToolbar"]{background:transparent}
.block-container{position:relative;z-index:1;max-width:1320px;padding:4.6rem 2rem 3rem}
[data-testid="stSidebar"]{background:linear-gradient(180deg,#04111e 0%,#061625 100%);border-right:1px solid var(--wc-line)}

/* ---------- typography ---------- */
h1,h2,h3,h4{font-family:'Marcellus',serif!important;font-weight:400!important;letter-spacing:.2px}
h3{color:var(--wc-brass)!important}
div[data-testid="stMetricValue"]{font-variant-numeric:tabular-nums}
*{scrollbar-width:thin;scrollbar-color:var(--wc-brass) var(--wc-panel)}

/* ---------- entrance animations (staggered fade-up) ---------- */
@keyframes wcFadeUp{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:translateY(0)}}
@keyframes wcFadeIn{from{opacity:0}to{opacity:1}}
div[data-testid="stVerticalBlock"]>div[data-testid="stElementContainer"],
div[data-testid="stVerticalBlock"]>div[data-testid="stLayoutWrapper"]{
  animation:wcFadeUp .55s cubic-bezier(.22,.61,.36,1) both}
div[data-testid="stVerticalBlock"]>div:nth-child(1)>*{animation-delay:.03s}
div[data-testid="stVerticalBlock"]>div:nth-child(2)>*{animation-delay:.09s}
div[data-testid="stVerticalBlock"]>div:nth-child(3)>*{animation-delay:.15s}
div[data-testid="stVerticalBlock"]>div:nth-child(4)>*{animation-delay:.21s}
div[data-testid="stVerticalBlock"]>div:nth-child(5)>*{animation-delay:.27s}
div[data-testid="stVerticalBlock"]>div:nth-child(6)>*{animation-delay:.33s}
div[data-testid="stVerticalBlock"]>div:nth-child(n+7)>*{animation-delay:.39s}
/* A transformed ancestor captures position:fixed — exempt the splash overlay's container
   so the intro still covers the viewport instead of collapsing into a zero-height box. */
div[data-testid="stElementContainer"]:has(#wcs-overlay){animation:none}
@media (prefers-reduced-motion: reduce){
  .stApp::before{animation:none}
  div[data-testid="stVerticalBlock"]>div[data-testid="stElementContainer"]{animation:none}}

/* ---------- panels & metrics ---------- */
.wc-panel{background:rgba(12,34,56,.75);backdrop-filter:blur(10px);
  border:1px solid rgba(201,162,79,.25);border-radius:12px;transition:border-color .25s ease, box-shadow .25s ease}
.wc-panel:hover{border-color:rgba(201,162,79,.55);box-shadow:0 6px 28px rgba(201,162,79,.08)}
div[data-testid="stMetric"],div[data-testid="stExpander"],div[data-testid="stDataFrame"],
div[data-testid="stAlert"]{background:rgba(12,34,56,.72)!important;backdrop-filter:blur(10px);
  border:1px solid rgba(201,162,79,.22)!important;border-radius:12px;
  transition:border-color .25s ease, transform .25s ease}
div[data-testid="stMetric"]:hover,div[data-testid="stDataFrame"]:hover{
  border-color:rgba(201,162,79,.5)!important;transform:translateY(-2px)}
/* gold sweep across metric values on load */
@keyframes wcShimmer{0%{background-position:130% 0}100%{background-position:-30% 0}}
div[data-testid="stMetricValue"]{background:linear-gradient(100deg,var(--wc-text) 40%,#E9C46A 50%,var(--wc-text) 60%);
  background-size:250% 100%;-webkit-background-clip:text;background-clip:text;color:transparent;
  animation:wcShimmer 2.6s ease .35s 1 both}

/* ---------- header ---------- */
.wc-head{display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;
  padding:4px 0 16px;margin-bottom:18px;border-bottom:1px solid var(--wc-line);animation:wcFadeIn .8s ease both}
.wc-head .l{display:flex;align-items:center;gap:16px}
.wc-head img{height:56px;width:auto;max-width:200px;object-fit:contain}
.wc-head .t{font-family:'Marcellus',serif;font-size:1.45rem;line-height:1.2;color:var(--wc-text)}
.wc-head .s{color:var(--wc-muted);font-size:.85rem}
.wc-hash{background:#04111e;padding:10px;border-radius:6px;font-family:monospace;
  color:var(--wc-brass);font-size:.82rem;word-break:break-all}
hr{border-color:var(--wc-line)!important}
</style>
"""

_SPLASH = """
<div class="wcs" id="wcs-overlay">
  <style>
  .wcs{position:fixed;inset:0;z-index:99999;display:flex;flex-direction:column;align-items:center;
    justify-content:center;padding:0 18px;pointer-events:none;overflow:hidden;
    background:radial-gradient(ellipse 70% 55% at 50% 40%,#10304f 0%,#061625 55%,#020a12 100%);
    animation:wcsOut .8s cubic-bezier(.4,0,.2,1) 3.9s forwards}
  @keyframes wcsOut{to{opacity:0;visibility:hidden;transform:scale(1.05)}}
  .wcs::before{content:"";position:absolute;width:130vmax;height:130vmax;opacity:.07;filter:blur(2px);
    background:conic-gradient(from 0deg,transparent 0 12%,rgba(201,162,79,.7) 13% 14%,transparent 15% 37%,
      rgba(201,162,79,.5) 38% 39%,transparent 40% 62%,rgba(201,162,79,.7) 63% 64%,transparent 65% 87%,
      rgba(201,162,79,.5) 88% 89%,transparent 90%);
    animation:wcsSpin 14s linear infinite}
  @keyframes wcsSpin{to{transform:rotate(360deg)}}
  .wcs i.pt{position:absolute;width:4px;height:4px;border-radius:50%;background:rgba(233,196,106,.9);
    box-shadow:0 0 8px 2px rgba(201,162,79,.45);opacity:0;animation:wcsFloat 3.4s ease-in-out infinite}
  @keyframes wcsFloat{0%{opacity:0;transform:translateY(24px) scale(.6)}
    25%{opacity:.9}70%{opacity:.5}100%{opacity:0;transform:translateY(-70px) scale(1.1)}}
  .wcs-seal{position:relative;width:220px;height:220px;display:grid;place-items:center}
  .wcs-halo{position:absolute;inset:12px;border-radius:50%;
    background:radial-gradient(circle,rgba(201,162,79,.28) 0%,transparent 65%);
    opacity:0;animation:wcsIn .8s ease .9s forwards, wcsBreath 2.6s ease-in-out 1.7s infinite}
  @keyframes wcsBreath{0%,100%{transform:scale(1);opacity:.85}50%{transform:scale(1.12);opacity:1}}
  .wcs-seal img{width:150px;position:relative;opacity:0;transform:scale(.65);
    filter:drop-shadow(0 0 0 rgba(201,162,79,0));
    animation:wcsPop .8s cubic-bezier(.34,1.56,.64,1) .6s forwards,
      wcsGlow 2.8s ease-in-out 1.4s infinite}
  @keyframes wcsPop{to{opacity:1;transform:scale(1)}}
  @keyframes wcsGlow{0%,100%{filter:drop-shadow(0 0 6px rgba(201,162,79,.35))}
    50%{filter:drop-shadow(0 0 22px rgba(233,196,106,.75))}}
  .wcs-ring{position:absolute;inset:0;transform:rotate(-90deg)}
  .wcs-ring circle{fill:none;stroke:url(#wcsGrad);stroke-width:2;stroke-linecap:round;
    stroke-dasharray:653;stroke-dashoffset:653;animation:wcsDraw 1.7s ease .15s forwards}
  @keyframes wcsDraw{to{stroke-dashoffset:0}}
  .wcs-ring2 circle{stroke:rgba(201,162,79,.3);stroke-width:1;stroke-dasharray:578;
    stroke-dashoffset:578;animation:wcsDraw 2s ease .35s forwards}
  .wcs-ring3{animation:wcsSpinSlow 22s linear infinite}
  @keyframes wcsSpinSlow{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}
  .wcs-ring3 circle{fill:none;stroke:rgba(201,162,79,.4);stroke-width:1;stroke-dasharray:3 14}
  .wcs h1{font-family:'Marcellus',serif;font-weight:400;font-size:clamp(1.45rem,4.3vw,2.6rem);
    letter-spacing:clamp(2px,.55vw,5px);white-space:nowrap;text-align:center;margin:30px 0 8px;
    position:relative;opacity:0;background:linear-gradient(100deg,#E8EDF2 35%,#E9C46A 50%,#E8EDF2 65%);
    background-size:260% 100%;-webkit-background-clip:text;background-clip:text;color:transparent;
    animation:wcsIn .8s ease 1.25s forwards, wcsShine 2.6s linear 1.8s 2}
  @keyframes wcsIn{to{opacity:1}}
  @keyframes wcsShine{to{background-position:160% 0}}
  .wcs-rule{width:0;height:1px;margin:2px 0 14px;opacity:0;
    background:linear-gradient(90deg,transparent,#C9A24F,transparent);
    animation:wcsLine 1s ease 1.7s forwards}
  @keyframes wcsLine{to{width:min(340px,76vw);opacity:1}}
  .wcs p{font-family:'IBM Plex Sans',sans-serif;color:#a8bccf;font-size:clamp(.72rem,1.5vw,1rem);
    letter-spacing:clamp(1.5px,.45vw,3.5px);margin:0;text-align:center;white-space:nowrap;
    text-transform:uppercase;opacity:0;animation:wcsIn .7s ease 1.75s forwards}
  .wcs .sub{color:#5f7891;letter-spacing:clamp(1px,.32vw,2px);margin-top:8px;animation-delay:2.05s}
  .wcs-bar{width:230px;height:2px;background:rgba(201,162,79,.18);border-radius:2px;margin-top:24px;
    opacity:0;animation:wcsIn .5s ease 2.15s forwards;overflow:hidden}
  .wcs-bar i.blk{display:block;height:100%;width:0;border-radius:2px;
    background:linear-gradient(90deg,#8a6c33,#C9A24F,#E9C46A);
    animation:wcsLoad 1.45s cubic-bezier(.6,0,.2,1) 2.25s forwards}
  @keyframes wcsLoad{to{width:100%}}
  /* keep the whole composition inside short viewports */
  @media (max-height:820px){
    .wcs-seal{width:170px;height:170px}
    .wcs-seal img{width:118px}
    .wcs h1{margin:22px 0 6px}
    .wcs-bar{margin-top:18px}
  }
  @media (max-height:620px){
    .wcs-seal{width:128px;height:128px}
    .wcs-seal img{width:90px}
    .wcs h1{margin:14px 0 4px;font-size:1.2rem}
    .wcs-rule{margin:2px 0 9px}
    .wcs .sub{display:none}
    .wcs-bar{margin-top:14px}
  }
  @media (prefers-reduced-motion: reduce){
    .wcs::before,.wcs i.pt,.wcs-halo,.wcs-seal img,.wcs-ring3{animation-iteration-count:1}
  }
  </style>
  <i class="pt" style="left:32%;top:64%;animation-delay:.8s"></i>
  <i class="pt" style="left:63%;top:58%;animation-delay:1.6s"></i>
  <i class="pt" style="left:47%;top:72%;animation-delay:2.3s"></i>
  <i class="pt" style="left:71%;top:70%;animation-delay:1.1s"></i>
  <i class="pt" style="left:26%;top:52%;animation-delay:2.8s"></i>
  <div class="wcs-seal">
    <div class="wcs-halo"></div>
    <svg class="wcs-ring" viewBox="0 0 220 220"><defs>
      <linearGradient id="wcsGrad" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="#C9A24F"/><stop offset="55%" stop-color="#E9C46A"/><stop offset="100%" stop-color="#8a6c33"/>
      </linearGradient></defs>
      <circle cx="110" cy="110" r="104"/>
    </svg>
    <svg class="wcs-ring wcs-ring2" viewBox="0 0 220 220"><circle cx="110" cy="110" r="92"/></svg>
    <svg class="wcs-ring wcs-ring3" viewBox="0 0 230 230" style="inset:-5px"><circle cx="115" cy="115" r="112"/></svg>
    <img src="__SRC__" alt="">
  </div>
  <h1>Westminister Consulting</h1>
  <div class="wcs-rule"></div>
  <p>Data you can sign off on</p>
  <p class="sub">Autonomous Ledger Intelligence · Nairobi, Kenya</p>
  <div class="wcs-bar"><i class="blk"></i></div>
</div>
"""


def inject_theme() -> None:
    css = (
        _CSS.replace("__INK__", INK)
        .replace("__PANEL__", PANEL)
        .replace("__LINE__", LINE)
        .replace("__BRASS__", BRASS)
        .replace("__TEXT__", TEXT)
        .replace("__MUTED__", MUTED)
    )
    st.markdown(css, unsafe_allow_html=True)


def logo_src(logo_bytes: bytes | None) -> str:
    if logo_bytes:
        return "data:image/png;base64," + base64.b64encode(logo_bytes).decode()
    return _MONO


def show_splash(logo_bytes: bytes | None = None) -> None:
    if st.session_state.get("splash_shown"):
        return
    st.session_state.splash_shown = True
    st.markdown(_SPLASH.replace("__SRC__", logo_src(logo_bytes)), unsafe_allow_html=True)


def app_header(logo_bytes: bytes | None, user: str) -> None:
    st.markdown(
        f'<div class="wc-head"><div class="l"><img src="{logo_src(logo_bytes)}" alt="">'
        f'<div class="t">Westminister Intelligence Suite</div></div>'
        f'<div class="s">Signed in as {html.escape(user)}</div></div>',
        unsafe_allow_html=True,
    )
