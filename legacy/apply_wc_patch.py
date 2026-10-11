"""apply_wc_patch.py - builds west_v2.py from west.py. Your west.py is never changed.

Run from the folder that holds west.py and wc_ui.py:
    python apply_wc_patch.py
Each change reports OK or SKIPPED. The new file is written only if it is valid Python.
"""
import ast
import pathlib
import re
import sys

SRC, OUT = pathlib.Path("west.py"), pathlib.Path("west_v2.py")
if not SRC.exists():
    sys.exit("west.py not found. Run this from the folder that contains west.py.")
if not pathlib.Path("wc_ui.py").exists():
    sys.exit("wc_ui.py not found next to west.py. Add it first.")
t = SRC.read_text(encoding="utf-8")
if "import wc_ui" in t:
    sys.exit("west.py already uses wc_ui. Nothing to do.")
log = []


def rep(name, old, new):
    global t
    if old in t:
        t = t.replace(old, new, 1)
        log.append(("OK     ", name))
    else:
        log.append(("SKIPPED", name + "  (text not found)"))


def cut(name, pattern, new=""):
    global t
    out, n = re.subn(pattern, lambda m: new, t, count=1, flags=re.S)
    if n:
        t = out
        log.append(("OK     ", name))
    else:
        log.append(("SKIPPED", name + "  (text not found)"))


# 1. theme + splash right after page config
m = re.search(r"st\.set_page_config\(.*?\n\)", t, re.S)
if m:
    t = t[:m.end()] + "\nimport wc_ui\nwc_ui.inject_theme()\nwc_ui.show_splash(load_logo(), LOGO_URL)" + t[m.end():]
    log.append(("OK     ", "Theme and new splash screen"))
else:
    log.append(("SKIPPED", "Theme and new splash screen  (st.set_page_config not found)"))

# 2-4. remove old splash, old styles, old header
cut("Remove old splash (sleep + rerun)", r"# 2\. Cinematic Startup Splash Screen.*?(?=# 3\. Main Application Styling)")
cut("Remove old global styles", r"# 3\. Main Application Styling.*?(?=# Header Section)")
cut("Remove old header", r"# Header Section.*?(?=# Sidebar Ingestion)")
rep("New header after sign-in", '_USER = st.session_state.get("user", "guest")\n',
    '_USER = st.session_state.get("user", "guest")\nwc_ui.app_header(st.session_state.logo_bytes or load_logo(), LOGO_URL, _USER)\n')

# 5. data preview into a collapsed section so the tabs sit near the top
s_mark, e_mark = '    st.markdown("## 1. Uploaded Dataset — Full Data")\n', "    st.divider()\n"
s = t.find(s_mark)
e = t.find(e_mark, s) if s >= 0 else -1
if s >= 0 and e >= 0:
    body = t[s + len(s_mark):e].replace('    with st.expander("Dataset details"):', '    if st.checkbox("Show column details", key="wc_show_details"):')
    body = "\n".join(("    " + ln if ln.strip() else ln) for ln in body.split("\n"))
    t = t[:s] + '    with st.expander("Uploaded data (every row, paged)", expanded=False):\n' + body + t[e + len(e_mark):]
    log.append(("OK     ", "Data preview moved into a collapsed section"))
else:
    log.append(("SKIPPED", "Data preview move  (text not found)"))

# 6. dashboard
cut("New executive dashboard", r"    with tab_dash:\n.*?(?=    # --- AUTO-CLEAN STUDIO ---)", r'''    with tab_dash:
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

''')

# 7. honest message before the analysis has been run
rep("Autopilot: no false 'no findings' message",
    """        for it_ in _fr[0][1]:
            st.markdown(f'<div class="insight-box">{it_}</div>', unsafe_allow_html=True)""",
    """        if not AP:
            st.info("The full analysis has not been run yet. Press 'Run full statistical analysis' above to see findings and recommendations.")
        for it_ in (_fr[0][1] if AP else []):
            st.markdown(f'<div class="insight-box">{it_}</div>', unsafe_allow_html=True)""")
rep("Autopilot: recommendations message",
    'st.info("The statistical evidence does not justify any specific action.")',
    'st.info("The statistical evidence does not justify any specific action." if AP else "Recommendations appear after the analysis has been run.")')

# 8. long question list into a collapsed section
rep("Autopilot: question list collapsed",
    """        st.markdown("### Questions the app answers (remove any you do not need)")
        st.multiselect("Questions", _ids, default=_ids, key=_apk, format_func=lambda i: f"[{_th[i]}] {_tt[i]}")""",
    """        with st.expander("Choose which questions to answer (all selected by default)"):
            st.multiselect("Questions", _ids, default=_ids, key=_apk, format_func=lambda i: f"[{_th[i]}] {_tt[i]}")""")

# 9. date-order warning was silently skipped on newer pandas
rep("Fix ambiguous-date note on pandas 3",
    'if kind == "datetime" and df[c].dtype == object:',
    'if kind == "datetime" and (pd.api.types.is_object_dtype(df[c]) or pd.api.types.is_string_dtype(df[c])):')

# 10. honest eTIMS wording
rep("eTIMS wording: format check only", '"Verified eTIMS"', '"Format looks valid (not verified with KRA)"')

# 11. hardcoded verification date
rep("Sign-off date uses today", "October 6, 2026", '""" + datetime.now().strftime("%B %d, %Y") + """')

try:
    ast.parse(t)
except SyntaxError as err:
    print("\n".join(f"{a} {b}" for a, b in log))
    sys.exit(f"\nSTOPPED: the patched file has a syntax error at line {err.lineno}. Nothing was written. Send me this message.")
OUT.write_text(t, encoding="utf-8")
print("\n".join(f"{a} {b}" for a, b in log))
skipped = sum(1 for a, _ in log if a.startswith("SKIPPED"))
print(f"\nCreated {OUT}. {len(log) - skipped} changes applied, {skipped} skipped.")
print("Run it with:  streamlit run west_v2.py")