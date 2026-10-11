"""apply_wc_patch3.py - builds west_v4.py from west_v3.py and tunes wc_ui.py.
west_v3.py is never changed. wc_ui.py is backed up once to wc_ui_backup.py first.

Needs in the same folder: west_v3.py, wc_ui.py, wc_smart.py
Run:   python apply_wc_patch3.py
Then:  streamlit run west_v4.py
"""
import ast
import pathlib
import re
import shutil
import sys

SRC, OUT, UI, SMART = pathlib.Path("west_v3.py"), pathlib.Path("west_v4.py"), pathlib.Path("wc_ui.py"), pathlib.Path("wc_smart.py")
for f in (SRC, UI, SMART):
    if not f.exists():
        sys.exit(f"{f} not found. Run patches 1 and 2 first and keep wc_smart.py in this folder.")
t = SRC.read_text(encoding="utf-8")
if "wc_smart.smart_clean" in t:
    sys.exit("west_v3.py already has these changes.")
log = []


def rep(name, old, new, count=1):
    global t
    if old in t:
        t = t.replace(old, new) if count == 0 else t.replace(old, new, count)
        log.append(("OK     ", name))
    else:
        log.append(("SKIPPED", name + "  (text not found)"))


# ---------------------------------------------------------------- west_v3.py
rep("Import the smart engine",
    'warnings.filterwarnings("ignore", category=UserWarning)',
    'warnings.filterwarnings("ignore", category=UserWarning)\nimport wc_smart')

rep("One-touch cleaning replaces auto_clean on upload",
    "    clean, log_df, schema = auto_clean(raw, impute, drop_dupes)",
    "    clean, log_df, schema = wc_smart.smart_clean(raw, impute, drop_dupes)")

rep("Analysis runs automatically after upload (up to 300,000 rows)",
    '            st.session_state._run_autopilot = False\n            audit(_USER, "file loaded"',
    '            st.session_state._run_autopilot = len(_df) <= 300000\n            audit(_USER, "file loaded"')

rep("Analysis runs automatically for the sample file",
    '_pk=("sample",), _run_autopilot=False)',
    '_pk=("sample",), _run_autopilot=True)')

rep("Clean tab: cleaning report with reasons per column",
    '        st.markdown("### Audit trail (what was changed automatically)")',
    '        wc_smart.render_cleaning_report(df, st.session_state.clean_log)\n        st.markdown("### Audit trail (what was changed automatically)")')

# deep-dive dashboard goes straight under the existing executive overview
m = re.search(r"^(?P<ind>[ \t]*)wc_ui\.render_dashboard\(.*\)[ \t]*$", t, re.M)
if m:
    ind = m.group("ind")
    t = t[:m.end()] + f"\n{ind}wc_smart.render_pro_dashboard(df, U, kd, s_insights)" + t[m.end():]
    log.append(("OK     ", "Dashboard: deep-dive section added under the overview"))
else:
    log.append(("SKIPPED", "Dashboard deep dive (wc_ui.render_dashboard call not found). Add this line under it:  wc_smart.render_pro_dashboard(df, U, kd, s_insights)"))

rep("Export tab: verification date is today's date",
    "October 6, 2026",
    '""" + datetime.now().strftime("%B %d, %Y") + """')

n = t.count("Westiminister")
t = t.replace("Westiminister", "Westminister")
log.append(("OK     " if n else "SKIPPED", f"Spelling fix 'Westiminister' ({n} places)"))

try:
    ast.parse(t)
except SyntaxError as err:
    print("\n".join(f"{a} {b}" for a, b in log))
    sys.exit(f"\nSTOPPED: syntax error in west_v4.py at line {err.lineno}. Nothing was written. Send me this message.")

# ---------------------------------------------------------------- wc_ui.py
u = UI.read_text(encoding="utf-8")
ulog = []


def urep(name, old, new, count=1):
    global u
    if old in u:
        u = u.replace(old, new) if count == 0 else u.replace(old, new, count)
        ulog.append(("OK     ", name))
    else:
        ulog.append(("SKIPPED", name + "  (text not found)"))


if "_MONO" not in u:
    urep("Monogram fallback when the logo is missing",
         'COLORWAY = [BRASS, "#4FA3C7", "#7FB77E", "#B58DB6", "#E0A84A", "#E06C6C"]',
         'COLORWAY = [BRASS, "#4FA3C7", "#7FB77E", "#B58DB6", "#E0A84A", "#E06C6C"]\n'
         '_MONO = ("data:image/svg+xml;utf8,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' viewBox=\'0 0 96 96\'%3E%3Ctext x=\'48\' y=\'68\' font-size=\'70\' '
         'text-anchor=\'middle\' fill=\'%23C9A24F\' font-family=\'Marcellus,serif\'%3EW%3C/text%3E%3C/svg%3E")')
    urep("Use the monogram in splash and header", "if logo_bytes else logo_url", "if logo_bytes else (logo_url or _MONO)", 0)
    urep("Old card styles (.metric-card, .insight-box) match the new theme",
         "@media (max-width:760px){.wc-strip",
         ".metric-card{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--brass);border-radius:10px;padding:14px 16px;text-align:center}"
         ".metric-card h2{font-size:1.6rem!important;color:var(--text)!important;margin:0;font-variant-numeric:tabular-nums}"
         ".metric-card p{margin:4px 0 0;color:var(--muted);font-size:.8rem}"
         ".insight-box{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 16px;margin:8px 0;line-height:1.55;font-size:.93rem}\n"
         "@media (max-width:760px){.wc-strip")
    # splash: about 2.9 s in total instead of 4.7 s, no fake progress counter
    urep("Splash timing: fade out earlier", "animation:wcsOut .7s ease 4s forwards", "animation:wcsOut .5s ease 2.4s forwards")
    urep("Splash timing: seal rings", "wcsRing 2s ease .3s forwards", "wcsRing 1.2s ease .1s forwards")
    urep("Splash timing: second ring", "animation-delay:.7s}", "animation-delay:.4s}")
    urep("Splash timing: third ring", "animation-delay:1.1s}", "animation-delay:.6s}")
    urep("Splash timing: logo", "animation:wcsIn .9s ease 1.2s forwards}", "animation:wcsIn .6s ease .7s forwards}")
    urep("Splash timing: title", "animation:wcsIn .9s ease 1.5s forwards,wcsShine 2.2s ease 2.2s forwards", "animation:wcsIn .6s ease .9s forwards,wcsShine 1.1s ease 1.2s forwards")
    urep("Splash timing: tagline", "animation:wcsIn .9s ease 1.9s forwards}", "animation:wcsIn .6s ease 1.2s forwards}")
    urep("Splash: remove the fake progress counter and rotating messages",
         '<div class="wcs-pct"></div>\n<div class="wcs-msg"><i>Opening the audit workspace</i><i>Loading cleaning and checking tools</i><i>Ready for your file</i></div></div>',
         "</div>")
    try:
        ast.parse(u)
    except SyntaxError as err:
        print("\n".join(f"{a} {b}" for a, b in log + ulog))
        sys.exit(f"\nSTOPPED: syntax error in wc_ui.py edit at line {err.lineno}. Nothing was written.")
    if not pathlib.Path("wc_ui_backup.py").exists():
        shutil.copy(UI, "wc_ui_backup.py")
    UI.write_text(u, encoding="utf-8")
else:
    ulog.append(("OK     ", "wc_ui.py already updated"))

OUT.write_text(t, encoding="utf-8")
print("\n".join(f"{a} {b}" for a, b in log + ulog))
print(f"\nCreated {OUT}. wc_ui.py updated (original saved as wc_ui_backup.py).")
print("Run it with:  streamlit run west_v4.py")