"""apply_wc_patch2.py - builds west_v3.py from west_v2.py. west_v2.py is never changed.

Run from the same folder:   python apply_wc_patch2.py
"""
import ast
import pathlib
import sys

SRC, OUT = pathlib.Path("west_v2.py"), pathlib.Path("west_v3.py")
if not SRC.exists():
    sys.exit("west_v2.py not found. Run apply_wc_patch.py first.")
t = SRC.read_text(encoding="utf-8")
if "wc_ui.render_start" in t:
    sys.exit("west_v2.py already has these changes.")
log = []


def rep(name, old, new):
    global t
    if old in t:
        t = t.replace(old, new, 1)
        log.append(("OK     ", name))
    else:
        log.append(("SKIPPED", name + "  (text not found)"))


# 1. first screen before any file is loaded, with a sample-data button
rep("Welcome screen and sample-data button",
    "def get_col_index(cols, keywords):",
    '''if st.session_state.get("df") is None:
    wc_ui.empty_state()
    if st.button("Try it with sample data", type="primary", key="wc_sample"):
        _b = wc_ui.make_sample_csv()
        _raw, _df, _log, _sc = _cached_load_and_clean(_b, "sample_sales_ledger.csv", None, opt_fill, opt_dupe)
        st.session_state.update(raw_df=_raw, df=_df, clean_log=_log, schema=_sc, _pk=("sample",), _run_autopilot=False)
        st.rerun()


def get_col_index(cols, keywords):''')

# 2. Start Here tab shows progress and the next step
rep("Start Here: progress and next step",
    '        st.markdown("## How this app works")\n',
    '''        wc_ui.render_start(len(df), U["issues"], len(st.session_state.clean_log), bool(st.session_state.get("_run_autopilot")),
                           bool(st.session_state.sig_bytes), bool(st.session_state.pdf))
        st.markdown("### Reference: every tool, and how this app compares with Excel")
''')

# 3. what the report will contain, shown before the Build button
rep("Report: pre-flight checklist",
    '        if st.button("Build management report (PDF)"):',
    '''        wc_ui.report_preflight(client_name, signer_n, bool(st.session_state.sig_bytes), U["issues"], bool(st.session_state.get("_run_autopilot")), INTEG)
        if st.button("Build management report (PDF)"):''')

# 4. warn before changing real values
rep("Clean: outlier capping warning",
    'do_cap = o2.checkbox("Cap extreme outliers (IQR) on numeric columns", False)',
    'do_cap = o2.checkbox("Cap extreme outliers (IQR) on numeric columns", False, help="Changes real values. Leave off for audit work unless you will document the change.")')
rep("Clean: title-case warning",
    'do_case = o3.checkbox("Title-case text categories", False)',
    'do_case = o3.checkbox("Title-case text categories", False, help="Rewrites the text in your data. Leave off unless the client agrees.")')

# 5. new Streamlit wording for full-width elements (removes the warnings)
n = t.count("use_container_width=True")
t = t.replace("use_container_width=True", 'width="stretch"')
log.append(("OK     " if n else "SKIPPED", f"Streamlit warning fix ({n} places)"))

try:
    ast.parse(t)
except SyntaxError as err:
    print("\n".join(f"{a} {b}" for a, b in log))
    sys.exit(f"\nSTOPPED: syntax error at line {err.lineno}. Nothing was written. Send me this message.")
OUT.write_text(t, encoding="utf-8")
print("\n".join(f"{a} {b}" for a, b in log))
print(f"\nCreated {OUT}.")
print("Run it with:  streamlit run west_v3.py")