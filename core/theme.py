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
div[data-testid="stMetricValue"]{font-variant-numeric:tabular-nums;white-space:normal;overflow:visible;
  text-overflow:clip;font-size:clamp(1.05rem,1.3vw,1.5rem);line-height:1.2}
div[data-testid="stMetricLabel"]{overflow:visible;text-overflow:clip}
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
/* A transformed ancestor captures position:fixed — exempt any animated wrapper holding the
   splash so the intro covers the viewport instead of collapsing into a zero-height box. */
div[data-testid="stVerticalBlock"]>div:has(#wcs-overlay){animation:none}
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

/* ---------- explainer bands ---------- */
.wc-note{background:linear-gradient(92deg,rgba(201,162,79,.10),rgba(12,34,56,.66) 46%);
  border:1px solid rgba(201,162,79,.26);border-left:3px solid var(--wc-brass);border-radius:12px;
  padding:14px 18px 12px;margin:2px 0 18px;backdrop-filter:blur(8px)}
.wc-note b.hd{display:block;font-family:'Marcellus',serif;font-weight:400;color:var(--wc-brass);
  font-size:.95rem;letter-spacing:.4px;margin:0 0 9px}
.wc-note .r{display:grid;grid-template-columns:190px minmax(0,1fr);gap:14px;padding:7px 0;
  border-top:1px solid rgba(30,58,87,.5)}
.wc-note .r:first-of-type{border-top:0;padding-top:0}
.wc-note .k{color:#D4AF63;font-size:.79rem;font-weight:600;line-height:1.5;padding-top:1px}
.wc-note .v{color:#DCE6EF;font-size:.885rem;line-height:1.62}
@media (max-width:760px){.wc-note .r{grid-template-columns:minmax(0,1fr);gap:3px}}

/* ---------- buttons ---------- */
[data-testid^="stBaseButton"]{border-radius:9px;font-weight:500;letter-spacing:.2px;
  transition:transform .16s ease, box-shadow .16s ease, border-color .16s ease, filter .16s ease}
[data-testid="stBaseButton-primary"],[data-testid="stBaseButton-formSubmitButton"]{
  background:linear-gradient(180deg,#DDB869,var(--wc-brass))!important;color:#08192a!important;
  border:1px solid #E9C46A!important;box-shadow:0 4px 18px rgba(201,162,79,.2)}
[data-testid^="stBaseButton-secondary"],[data-testid="stSidebar"] [data-testid^="stBaseButton"]{
  background:rgba(12,34,56,.72)!important;color:var(--wc-text)!important;border:1px solid var(--wc-line)!important}
[data-testid^="stBaseButton"]:hover{transform:translateY(-1px);filter:brightness(1.07)}
[data-testid^="stBaseButton"]:disabled{opacity:.42;filter:grayscale(.5);transform:none}

/* ---------- tabs ---------- */
button[data-baseweb="tab"]{color:var(--wc-muted)!important;font-weight:500;padding:0 14px}
button[data-baseweb="tab"]:hover{color:var(--wc-text)!important}
button[data-baseweb="tab"][aria-selected="true"]{color:var(--wc-brass)!important}
div[data-baseweb="tab-highlight"]{background:var(--wc-brass)!important}
div[data-baseweb="tab-border"],[data-testid="stTabs"] [role="tablist"]{background:transparent!important;
  border-bottom:1px solid var(--wc-line)!important}

/* ---------- inputs, selects, dates ---------- */
[data-testid="stTextInput"] input,[data-testid="stNumberInput"] input,
[data-baseweb="select"]>div,[data-testid="stDateInput"] input{background:#04111e!important;
  color:var(--wc-text)!important;border:1px solid var(--wc-line)!important;border-radius:8px}
[data-testid="stTextInput"]:hover input,[data-testid="stNumberInput"]:hover input,
[data-baseweb="select"]:hover>div{border-color:rgba(201,162,79,.55)!important}
[data-testid="stTextInput"]:focus-within input,[data-testid="stNumberInput"]:focus-within input{
  border-color:var(--wc-brass)!important;box-shadow:0 0 0 2px rgba(201,162,79,.16)!important}
[data-testid="stSelectbox"] label p,[data-testid="stMultiSelect"] label p,[data-testid="stTextInput"] label p,
[data-testid="stNumberInput"] label p{color:var(--wc-muted)!important;font-size:.79rem;font-weight:600}
ul[data-baseweb="select"]{background:#04111e!important;border:1px solid var(--wc-line)!important}

/* ---------- sidebar, captions, links ---------- */
[data-testid="stSidebar"] h1,[data-testid="stSidebar"] h2,[data-testid="stSidebar"] h3{color:var(--wc-brass)!important}
[data-testid="stCaption"],figcaption{color:var(--wc-muted)!important}
.stMarkdown a,.stCaption a{color:var(--wc-brass)}
.stMarkdown a:hover{color:#E9C46A}
[data-testid="stExpander"] details summary p{color:var(--wc-text)}
[data-testid="stDataFrame"] [role="columnheader"]{background:#04111e!important}

/* ---------- keyboard focus, for a live demo ---------- */
:focus-visible{outline:2px solid var(--wc-brass)!important;outline-offset:2px}

/* ---------- scrollbars (WebKit) ---------- */
::-webkit-scrollbar{width:10px;height:10px}
::-webkit-scrollbar-track{background:#04111e}
::-webkit-scrollbar-thumb{background:var(--wc-line);border-radius:8px}
::-webkit-scrollbar-thumb:hover{background:var(--wc-brass)}
</style>
"""

_BOOT = """
<style>
/* The intro itself is a 40 KB message; the frame that flashes up while it is still in flight is
   the app the intro exists to replace. This 400-byte cover lands first and hands over the moment
   the intro appears — and clears itself after six seconds if the intro never does. */
#wcs-boot{position:fixed;inset:0;z-index:99998;background:__INK__;
  animation:wcsBootFade 6s steps(1,end) forwards}
@keyframes wcsBootFade{from{opacity:1}to{opacity:0;visibility:hidden}}
div[data-testid="stVerticalBlock"]>div:has(#wcs-boot){animation:none!important;transform:none!important}
body:has(#wcs-overlay) #wcs-boot{display:none}
</style>
<div id="wcs-boot"></div>
"""

_SPLASH = """
<div class="wcs" id="wcs-overlay">
  <style>
  @import url('https://fonts.googleapis.com/css2?family=Marcellus&family=IBM+Plex+Sans:wght@400;500;600&display=swap');
  body{--wcs-out:.6s}
  /* The intro carries its own fonts and its own exemption from the app's staggered entrance,
     so no later stylesheet can lift it out of the viewport or queue it behind the frame. */
  div[data-testid="stVerticalBlock"]>div:has(#wcs-overlay),
  div[data-testid="stElementContainer"]:has(#wcs-overlay){animation:none!important;transform:none!important}
  .wcs{position:fixed;inset:0;z-index:99999;display:flex;flex-direction:column;align-items:center;
    justify-content:center;padding:0 18px;overflow:hidden;
    background:radial-gradient(ellipse 70% 55% at 50% 40%,#10304f 0%,#061625 58%,#04111e 100%)}
  @keyframes wcsOut{to{opacity:0;visibility:hidden;transform:scale(1.05)}}
  /* The intro owns the screen until Enter now is clicked: the app behind it stays unseen.
     Both selector shapes are needed because the splash container may sit directly in the
     block or inside a layout wrapper — either way nothing else may stay lit. */
  body:has(#wcs-overlay):not(:has(#wcs-skip:checked)) [data-testid="stSidebar"],
  body:has(#wcs-overlay):not(:has(#wcs-skip:checked)) header[data-testid="stHeader"],
  body:has(#wcs-overlay):not(:has(#wcs-skip:checked)) div[data-testid="stElementContainer"]:has(#wcs-overlay) ~ *,
  body:has(#wcs-overlay):not(:has(#wcs-skip:checked)) div[data-testid="stVerticalBlock"]:has(#wcs-overlay)>*:not(:has(#wcs-overlay)){
    opacity:0}
  /* Streamlit strips inline JS and on* handlers from markdown, so Enter now is a styled
     checkbox: checking it fades the intro out and the app in, entirely in the browser. */
  #wcs-overlay:has(#wcs-skip:checked){pointer-events:none;
    animation:wcsOut var(--wcs-out) cubic-bezier(.4,0,.2,1) forwards}
  body:has(#wcs-overlay):has(#wcs-skip:checked) [data-testid="stSidebar"],
  body:has(#wcs-overlay):has(#wcs-skip:checked) header[data-testid="stHeader"],
  body:has(#wcs-overlay):has(#wcs-skip:checked) div[data-testid="stElementContainer"]:has(#wcs-overlay) ~ *,
  body:has(#wcs-overlay):has(#wcs-skip:checked) div[data-testid="stVerticalBlock"]:has(#wcs-overlay)>*:not(:has(#wcs-overlay)){
    animation:wcsReveal var(--wcs-out) ease both}
  @keyframes wcsReveal{from{opacity:0}to{opacity:1}}
  /* Reduced-motion viewers get the same door, just without the travel. */
  @media (prefers-reduced-motion: reduce){body{--wcs-out:.08s}}
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
  /* The wordmark rises out of a clipped band rather than fading — a mask reveal reads as
     craft, a fade reads as a loading screen. */
  .wcs-wm{overflow:hidden;padding-top:4px}
  .wcs h1{font-family:'Marcellus',serif;font-weight:400;font-size:clamp(1.45rem,4.3vw,2.6rem);
    letter-spacing:clamp(2px,.55vw,5px);white-space:nowrap;text-align:center;margin:26px 0 8px;
    position:relative;transform:translateY(115%);background:linear-gradient(100deg,#E8EDF2 35%,#E9C46A 50%,#E8EDF2 65%);
    background-size:260% 100%;-webkit-background-clip:text;background-clip:text;color:transparent;
    animation:wcsRise 1s cubic-bezier(.22,.61,.36,1) 1.2s forwards, wcsShine 2.6s linear 2.2s 2}
  @keyframes wcsRise{to{transform:translateY(0)}}
  @keyframes wcsIn{to{opacity:1}}
  @keyframes wcsShine{to{background-position:160% 0}}
  .wcs-rule{width:0;height:1px;margin:2px 0 14px;opacity:0;
    background:linear-gradient(90deg,transparent,#C9A24F,transparent);
    animation:wcsLine 1s ease 1.7s forwards}
  @keyframes wcsLine{to{width:min(340px,76vw);opacity:1}}
  .wcs p{font-family:'IBM Plex Sans',sans-serif;color:#a8bccf;font-size:clamp(.72rem,1.5vw,1rem);
    letter-spacing:clamp(1.5px,.45vw,3.5px);margin:0;text-align:center;white-space:nowrap;
    text-transform:uppercase;opacity:0;animation:wcsIn .7s ease 2s forwards}
  .wcs .sub{color:#5f7891;letter-spacing:clamp(1px,.32vw,2px);margin-top:8px;animation-delay:2.3s}
  .wcs-bar{width:230px;height:2px;background:rgba(201,162,79,.18);border-radius:2px;margin-top:24px;
    opacity:0;animation:wcsIn .5s ease 2.5s forwards;overflow:hidden}
  .wcs-bar i.blk{display:block;height:100%;width:0;border-radius:2px;
    background:linear-gradient(90deg,#8a6c33,#C9A24F,#E9C46A);
    animation:wcsLoad 1.45s cubic-bezier(.6,0,.2,1) 2.6s forwards}
  @keyframes wcsLoad{to{width:100%}}
  /* The intro waits on the viewer, so these four lines keep cycling for as long as it is up. */
  .wcs-steps{position:relative;height:15px;width:min(430px,86vw);margin-top:13px}
  .wcs-steps span{position:absolute;inset:0;text-align:center;opacity:0;
    font-family:'IBM Plex Sans',sans-serif;font-size:.66rem;font-weight:500;line-height:15px;
    letter-spacing:1.9px;text-transform:uppercase;color:#6d87a0;
    animation:wcsStep 3.8s ease infinite}
  .wcs-steps span:nth-child(1){animation-delay:.6s}
  .wcs-steps span:nth-child(2){animation-delay:1.55s}
  .wcs-steps span:nth-child(3){animation-delay:2.5s}
  .wcs-steps span:nth-child(4){animation-delay:3.45s}
  @keyframes wcsStep{0%{opacity:0;transform:translateY(6px)}
    5%,18%{opacity:1;transform:translateY(0)}25%,100%{opacity:0;transform:translateY(-4px)}}
  .wcs-skip{margin-top:16px;opacity:0;font-family:'IBM Plex Sans',sans-serif;font-size:.58rem;
    letter-spacing:2.6px;text-transform:uppercase;color:#45657f;animation:wcsIn .6s ease 2.2s forwards}
  .wcs-skip input{position:absolute;width:1px;height:1px;opacity:0}
  .wcs-skip label{display:inline-block;cursor:pointer;padding:6px 16px;border-radius:999px;
    border:1px solid rgba(201,162,79,.42);color:#C9A24F;letter-spacing:2.4px;font-size:.58rem;
    transition:border-color .2s ease, background .2s ease, transform .2s ease;
    animation:wcsTap 2.6s ease-out 3s infinite}
  @keyframes wcsTap{0%,100%{box-shadow:0 0 0 0 rgba(201,162,79,.3)}
    55%{box-shadow:0 0 0 8px rgba(201,162,79,0)}}
  .wcs-skip label:hover{background:rgba(201,162,79,.13);border-color:#E9C46A;transform:translateY(-1px)}
  .wcs-skip input:focus-visible+label{outline:2px solid #C9A24F;outline-offset:3px}
  /* Six miniature dashboards cycle in behind the seal. The intro no longer lifts on a timer, so
     this is a loop rather than a race: 3.4s per rotation, staggered by a sixth of it, so three
     screens are lit at any instant and a viewer who lingers still sees all six in turn. */
  .wcs-dash{--wcs-cycle:3.4s;position:absolute;inset:-2%;z-index:0;overflow:hidden;pointer-events:none;
    -webkit-mask-image:radial-gradient(ellipse 58% 52% at 50% 44%,transparent 24%,#000 74%);
    mask-image:radial-gradient(ellipse 58% 52% at 50% 44%,transparent 24%,#000 74%);
    animation:wcsWall 19s ease-in-out infinite alternate}
  @keyframes wcsWall{from{transform:translate3d(-9px,5px,0) scale(1.03)}
    to{transform:translate3d(9px,-5px,0) scale(1.03)}}
  .wcs-seal,.wcs-wm,.wcs-rule,.wcs p,.wcs-bar,.wcs-steps,.wcs-skip{position:relative;z-index:2}
  .wcs-tile{position:absolute;width:min(232px,19vw);aspect-ratio:20/11;padding:9px 11px 8px;
    border:1px solid rgba(201,162,79,.24);border-radius:11px;opacity:0;
    background:linear-gradient(158deg,rgba(16,44,72,.72),rgba(6,20,34,.44));
    box-shadow:0 16px 44px rgba(2,10,18,.5),0 0 26px rgba(201,162,79,.07),
      inset 0 1px 0 rgba(233,196,106,.16);
    animation-name:wcsTile;animation-duration:var(--wcs-cycle);animation-timing-function:cubic-bezier(.4,0,.2,1);
    animation-iteration-count:infinite;animation-delay:var(--d,0s)}
  @keyframes wcsTile{0%{opacity:0;transform:translateY(15px) scale(.955)}
    12%,44%{opacity:.82;transform:none}
    64%,100%{opacity:0;transform:translateY(-13px) scale(1.03)}}
  .wcs-tile .hd{display:flex;align-items:baseline;justify-content:space-between;gap:7px;margin:0 0 6px}
  .wcs-tile b{font-family:'IBM Plex Sans',sans-serif;font-weight:600;font-size:.5rem;line-height:1.1;
    letter-spacing:1.6px;text-transform:uppercase;color:#8ba3ba;white-space:nowrap;overflow:hidden;
    text-overflow:ellipsis}
  .wcs-tile i{font-style:normal;font-family:'IBM Plex Sans',sans-serif;font-weight:600;font-size:.66rem;
    line-height:1.1;letter-spacing:.3px;color:#D9B45F;white-space:nowrap}
  .wcs-tile i em{font-style:normal;font-size:.46rem;font-weight:600;letter-spacing:.7px;margin-left:5px;
    color:#5FB38A;vertical-align:1px}
  .wcs-tile i em.dn{color:#E06C6C}
  .wcs-tile svg{display:block;width:100%;height:calc(100% - 26px);overflow:visible}
  .wcs-tile .gl{stroke:rgba(143,163,184,.13);stroke-width:1}
  .wcs-tile .ax{stroke:rgba(143,163,184,.3);stroke-width:1.2}
  .wcs-tile .ln{fill:none;stroke:#E9C46A;stroke-width:2.6;stroke-linecap:round;stroke-linejoin:round;
    stroke-dasharray:var(--len);stroke-dashoffset:var(--len);
    filter:drop-shadow(0 0 5px rgba(201,162,79,.4))}
  .wcs-tile .rg{fill:none;stroke-width:9;stroke-dasharray:var(--len) 100;stroke-dashoffset:var(--len)}
  .wcs-tile .ln,.wcs-tile .rg{animation-name:wcsDash;animation-duration:var(--wcs-cycle);
    animation-timing-function:cubic-bezier(.2,.7,.3,1);animation-iteration-count:infinite;
    animation-delay:calc(var(--d,0s) + var(--o,0s))}
  @keyframes wcsDash{0%,6%{stroke-dashoffset:var(--len)}40%,100%{stroke-dashoffset:0}}
  .wcs-tile .ar{fill:rgba(201,162,79,.14);stroke:none}
  .wcs-tile .bar{transform-box:fill-box;transform-origin:50% 100%;fill:rgba(201,162,79,.46);
    animation-name:wcsGrow;animation-duration:var(--wcs-cycle);animation-timing-function:cubic-bezier(.3,.7,.3,1);
    animation-iteration-count:infinite;animation-delay:calc(var(--d,0s) + var(--o,0s))}
  .wcs-tile .bar.pb{fill:rgba(79,163,199,.4)}
  @keyframes wcsGrow{0%,6%{transform:scaleY(.05)}42%,100%{transform:scaleY(1)}}
  .wcs-tile .trk{fill:rgba(143,163,184,.18)}
  .wcs-tile .val{fill:#C9A24F;transform-box:fill-box;transform-origin:0 50%;
    animation-name:wcsBar;animation-duration:var(--wcs-cycle);animation-timing-function:cubic-bezier(.3,.7,.3,1);
    animation-iteration-count:infinite;animation-delay:calc(var(--d,0s) + var(--o,0s))}
  .wcs-tile .val.cb{fill:#4FA3C7}
  @keyframes wcsBar{0%,6%{transform:scaleX(.02)}42%,100%{transform:scaleX(var(--w,1))}}
  .wcs-tile .cell,.wcs-tile .dot{fill:#C9A24F;opacity:.08;
    animation-name:wcsHeat;animation-duration:var(--wcs-cycle);animation-timing-function:ease-in-out;
    animation-iteration-count:infinite;animation-delay:calc(var(--d,0s) + var(--o,0s))}
  .wcs-tile .dot{fill:#E9C46A}
  @keyframes wcsHeat{0%,6%{opacity:.05}36%,52%{opacity:.6}72%,100%{opacity:.16}}
  .wcs-tile .sk{fill:rgba(143,163,184,.24)}
  @media (max-width:1240px),(max-height:700px){.wcs-tile.t5,.wcs-tile.t6{display:none}}
  @media (max-width:960px),(max-height:560px){.wcs-dash{display:none}}
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
    .wcs-dash{display:none}
    .wcs h1{transform:none}
  }
  </style>
  <div class="wcs-dash">__TILES__</div>
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
  <div class="wcs-wm"><h1>Westminister Consulting</h1></div>
  <div class="wcs-rule"></div>
  <p>Evidence, not assurances.</p>
  <p class="sub">Re-performed ledgers · bank reconciliation · tax health checks · certified sign-off</p>
  <div class="wcs-bar"><i class="blk"></i></div>
  <div class="wcs-steps">
    <span>Re-performing the ledger</span>
    <span>Matching bank lines</span>
    <span>Testing VAT &amp; WHT</span>
    <span>Sealing the certificate</span>
  </div>
  <div class="wcs-skip"><input type="checkbox" id="wcs-skip"><label for="wcs-skip">Enter now</label></div>
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


def _tile(inner: str) -> str:
    return f'<svg viewBox="0 0 200 110" aria-hidden="true">{inner}</svg>'


_DASH_CYCLE = 3.4  # seconds; the one number the stylesheet's --wcs-cycle must match

_GRID = "".join(f'<line class="gl" x1="0" y1="{y}" x2="200" y2="{y}"/>' for y in (28, 62, 96))
_RUN = "0,88 24,72 48,78 72,54 96,62 120,38 144,46 168,24 192,32 200,10"

# Sparkline, receipts against payments, tax split, reconciliation ladder, anomaly density,
# coverage steps — one motif per screen the suite actually delivers, each quoting the figure
# that screen really reports so the wall previews the engagement rather than decorating it.
_T_RUNWAY = _tile(
    _GRID
    + f'<polygon class="ar" points="{_RUN} 200,108 0,108"/>'
    + f'<polyline class="ln" style="--len:340" points="{_RUN}"/>'
    + '<line class="ax" x1="0" y1="108" x2="200" y2="108"/>'
)

_T_RECEIPTS = _tile(
    _GRID
    + "".join(
        f'<rect class="bar pb" x="{group * 40 + 2}" y="{108 - spent}" width="14" height="{spent}" rx="2"/>'
        f'<rect class="bar" x="{group * 40 + 18}" y="{108 - earned}" width="14" height="{earned}" rx="2" '
        f'style="--o:{0.05 * group:.2f}s"/>'
        for group, (spent, earned) in enumerate(((58, 76), (40, 58), (66, 84), (30, 52), (48, 70)))
    )
    + '<line class="ax" x1="0" y1="108" x2="200" y2="108"/>'
)

_T_TAX = _tile(
    '<circle class="tk" cx="52" cy="56" r="30" pathLength="100"/>'
    '<circle class="rg" cx="52" cy="56" r="30" pathLength="100" stroke="#C9A24F" '
    'style="--len:58" transform="rotate(-90 52 56)"/>'
    '<circle class="rg" cx="52" cy="56" r="30" pathLength="100" stroke="#4FA3C7" '
    'style="--len:26;--o:.14s" transform="rotate(119 52 56)"/>'
    '<rect x="100" y="28" width="9" height="9" rx="2" fill="#C9A24F" opacity=".55"/>'
    '<rect class="sk" x="116" y="30" width="58" height="5" rx="2.5"/>'
    '<rect x="100" y="50" width="9" height="9" rx="2" fill="#4FA3C7" opacity=".55"/>'
    '<rect class="sk" x="116" y="52" width="42" height="5" rx="2.5"/>'
    '<rect x="100" y="72" width="9" height="9" rx="2" fill="#E0A84A" opacity=".55"/>'
    '<rect class="sk" x="116" y="74" width="50" height="5" rx="2.5"/>'
)

_T_RECON = _tile(
    "".join(
        f'<rect class="sk" x="0" y="{y - 9}" width="46" height="4" rx="2"/>'
        f'<rect class="trk" x="0" y="{y}" width="200" height="7" rx="3.5"/>'
        f'<rect class="val{" cb" if i == 1 else ""}" x="0" y="{y}" width="200" height="7" rx="3.5" '
        f'style="--w:{ratio};--o:{0.08 * i:.2f}s"/>'
        for i, (y, ratio) in enumerate(((18, ".88"), (54, ".61"), (90, ".95")))
    )
)

_T_HEAT = _tile(
    "".join(
        f'<rect class="cell" x="{col * 28}" y="{row * 34}" width="25" height="30" rx="3" '
        f'style="--o:{((col * 3 + row * 5) % 7) * 0.04:.2f}s"/>'
        for row in range(3)
        for col in range(7)
    )
    + '<line class="ax" x1="0" y1="108" x2="200" y2="108"/>'
)

_T_COVER = _tile(
    _GRID
    + '<path class="ln" style="--len:470" d="M2 96H34V74H66V56H98V38H130V46H162V20H198"/>'
    + '<circle class="dot" cx="66" cy="56" r="4" style="--o:.12s"/>'
    '<circle class="dot" cx="98" cy="38" r="4" style="--o:.2s"/>'
    '<circle class="dot" cx="162" cy="20" r="4" style="--o:.28s"/>'
    + '<line class="ax" x1="0" y1="108" x2="200" y2="108"/>'
)

# Label, headline figure and movement — the same readings the pages report after an audit.
_DASH_TILES = (
    ("t1", "left:4%;top:10%", "Cash runway", "14.2 mo", "+8.2%", "", _T_RUNWAY),
    ("t2", "right:4.5%;top:8%", "Receipts vs payments", "212.5M", "-3.1%", "dn", _T_RECEIPTS),
    ("t3", "left:2.5%;top:43%", "VAT &amp; WHT exposure", "1.19M", "89 lines", "dn", _T_TAX),
    ("t4", "right:3%;top:45%", "Bank reconciliation", "99.1%", "41 open", "dn", _T_RECON),
    ("t5", "left:18%;bottom:6%", "Anomalies by month", "37 flags", "+12", "dn", _T_HEAT),
    ("t6", "right:17%;bottom:7%", "Ledger coverage", "96.4%", "clean", "", _T_COVER),
)


def _splash_dashboards() -> str:
    """Negative delays put three screens lit at every instant and all six on the wall inside the
    one rotation the intro has time to show."""
    step = _DASH_CYCLE / len(_DASH_TILES)
    return "".join(
        f'<div class="wcs-tile {cls}" style="{place};--d:-{index * step:.2f}s">'
        f'<div class="hd"><b>{label}</b><i>{figure}<em class="{tone}">{delta}</em></i></div>{chart}</div>'
        for index, (cls, place, label, figure, delta, tone, chart) in enumerate(_DASH_TILES)
    )


def show_splash(logo_bytes: bytes | None = None) -> None:
    if st.session_state.get("splash_shown"):
        return
    st.session_state.splash_shown = True
    st.markdown(_BOOT.replace("__INK__", INK), unsafe_allow_html=True)
    html_splash = _SPLASH.replace("__SRC__", logo_src(logo_bytes)).replace("__TILES__", _splash_dashboards())
    st.markdown(html_splash, unsafe_allow_html=True)


def note(rows, title: str = "What this tells you") -> None:
    """A brass-edged explainer band: labelled plain-English lines under a result block.

    Text is escaped because the labels carry user-supplied column and counterparty names.
    """
    body = "".join(
        f'<div class="r"><span class="k">{html.escape(str(k))}</span>'
        f'<span class="v">{html.escape(str(v))}</span></div>'
        for k, v in rows
    )
    head = f'<b class="hd">{html.escape(title)}</b>' if title else ""
    st.markdown(f'<div class="wc-note">{head}{body}</div>', unsafe_allow_html=True)


def app_header(logo_bytes: bytes | None, user: str) -> None:
    st.markdown(
        f'<div class="wc-head"><div class="l"><img src="{logo_src(logo_bytes)}" alt="">'
        f'<div class="t">Westminister Intelligence Suite</div></div>'
        f'<div class="s">Signed in as {html.escape(user)}</div></div>',
        unsafe_allow_html=True,
    )
