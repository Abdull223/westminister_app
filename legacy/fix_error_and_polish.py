"""fix_error_and_polish.py - fixes the "truth value of a DataFrame is ambiguous" crash and polishes the look.

Run from the project folder:   python fix_error_and_polish.py
Needs wc_smart.py and wc_ui.py in the same folder. Originals are saved as *_backup2.py.

Cause of the crash: wc_smart stored whole tables inside df.attrs. When pandas joins pieces of that
table (pd.concat in the exceptions workbook) it compares the attrs, and comparing tables raises the error.
It also made pandas copy those big tables on every filter. Now the tables live in a small store,
and df.attrs only holds a short text token.
"""
import ast
import pathlib
import shutil
import sys

log = []


def patch(path, edits, backup):
    p = pathlib.Path(path)
    if not p.exists():
        sys.exit(f"{path} not found. Run this from the folder that contains it.")
    t = p.read_text(encoding="utf-8")
    new = t
    for name, old, rep in edits:
        if old in new:
            new = new.replace(old, rep, 1)
            log.append(("OK     ", f"{path}: {name}"))
        else:
            log.append(("SKIPPED", f"{path}: {name}  (text not found)"))
    if new != t:
        try:
            ast.parse(new)
        except SyntaxError as e:
            print("\n".join(f"{a} {b}" for a, b in log))
            sys.exit(f"STOPPED: syntax error in {path} at line {e.lineno}. Nothing was written.")
        shutil.copy(p, backup)
        p.write_text(new, encoding="utf-8")


EMPTY = 'pd.DataFrame(columns=["Row", "Column", "Filled value", "Method"])'

smart = pathlib.Path("wc_smart.py")
if smart.exists() and "_stash(" in smart.read_text(encoding="utf-8"):
    log.append(("OK     ", "wc_smart.py: crash fix already applied"))
else:
    patch("wc_smart.py", [
        ("small store for the cleaning tables",
         "import numpy as np\nimport pandas as pd\n",
         '''import uuid
from collections import OrderedDict

import numpy as np
import pandas as pd

_STORE = OrderedDict()
_LAST = [None]


def _stash(d, formats, imputed, counts):
    """Keep the big tables outside df.attrs (pandas compares and copies attrs on many operations)."""
    tok = uuid.uuid4().hex
    _STORE[tok] = {"formats": formats, "imputed": imputed, "counts": counts}
    while len(_STORE) > 3:
        _STORE.popitem(last=False)
    _LAST[0] = tok
    d.attrs.clear()
    d.attrs["wc_token"] = tok


def _meta(df):
    m = _STORE.get(df.attrs.get("wc_token") or _LAST[0], {})
    return (m.get("formats", pd.DataFrame(columns=ISS_COLS)),
            m.get("imputed", pd.DataFrame(columns=["Row", "Column", "Filled value", "Method"])),
            m.get("counts", {}))

'''),
        ("store results after cleaning",
         '''    d.attrs["wc_formats"] = pd.DataFrame(issues[:20000], columns=ISS_COLS)
    d.attrs["wc_imputed"] = pd.DataFrame(rec[:200000], columns=["Row", "Column", "Filled value", "Method"]).astype({"Filled value": "string"})
    d.attrs["wc_imputed_counts"] = {c: int(imputed[c].sum()) for c in d.columns if imputed[c].any()}
''',
         '''    _stash(d, pd.DataFrame(issues[:20000], columns=ISS_COLS),
           pd.DataFrame(rec[:200000], columns=["Row", "Column", "Filled value", "Method"]).astype({"Filled value": "string"}),
           {c: int(imputed[c].sum()) for c in d.columns if imputed[c].any()})
'''),
        ("store results in the fallback path",
         '''        out.attrs["wc_formats"] = pd.DataFrame(columns=ISS_COLS)
        out.attrs["wc_imputed"] = pd.DataFrame(columns=["Row", "Column", "Filled value", "Method"])
        out.attrs["wc_imputed_counts"] = {}
''',
         '''        _stash(out, pd.DataFrame(columns=ISS_COLS), pd.DataFrame(columns=["Row", "Column", "Filled value", "Method"]), {})
'''),
        ("cleaning report reads the store",
         '''    fm = df.attrs.get("wc_formats", pd.DataFrame(columns=ISS_COLS))
    im = df.attrs.get("wc_imputed", pd.DataFrame(columns=["Row", "Column", "Filled value", "Method"]))
    cnt = df.attrs.get("wc_imputed_counts", {})
''',
         "    fm, im, cnt = _meta(df)\n"),
        ("dashboard reads the store",
         '        cnt = df.attrs.get("wc_imputed_counts", {})\n',
         "        cnt = _meta(df)[2]\n"),
    ], "wc_smart_backup2.py")

POLISH = '''@keyframes wcFade{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
[data-baseweb="tab-panel"]{animation:wcFade .35s ease}
[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"]{border:1px dashed rgba(201,162,79,.55);background:rgba(201,162,79,.05);border-radius:10px}
[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"]:hover{border-color:var(--brass);background:rgba(201,162,79,.1)}
[data-testid="stSidebar"] .stMarkdown h2{margin-top:1.2rem;padding-top:.9rem;border-top:1px solid var(--line)}
[data-testid="stSidebar"] .stMarkdown h2:first-child{border-top:0;padding-top:0}
*{scrollbar-width:thin;scrollbar-color:#2a4a6b transparent}
hr{border-color:var(--line)!important}
[data-testid="stAlert"]{border-radius:10px;border:1px solid var(--line)}
.wc-polish{display:none}
'''
ui = pathlib.Path("wc_ui.py")
if ui.exists() and ".wc-polish" in ui.read_text(encoding="utf-8"):
    log.append(("OK     ", "wc_ui.py: polish already applied"))
else:
    patch("wc_ui.py", [("look polish (fade-in tabs, upload box, sidebar sections)",
                        "@media (max-width:760px){.wc-strip", POLISH + "@media (max-width:760px){.wc-strip")], "wc_ui_backup2.py")

cfg = pathlib.Path(".streamlit/config.toml")
if cfg.exists():
    c = cfg.read_text(encoding="utf-8")
    if "toolbarMode" not in c:
        cfg.write_text(c.rstrip() + '\n\n[client]\ntoolbarMode = "minimal"\n', encoding="utf-8")
        log.append(("OK     ", "config.toml: hides the Deploy button"))
    else:
        log.append(("OK     ", "config.toml: already set"))
else:
    log.append(("SKIPPED", "config.toml not found"))

print("\n".join(f"{a} {b}" for a, b in log))
print("\nNow stop the app (Ctrl+C in its terminal) and start it again so Streamlit forgets the old cached tables.")