"""fix_wc_smart.py - repairs two bugs in wc_smart.py. Original is saved as wc_smart_backup.py.

Run from the project folder:   python fix_wc_smart.py
  1. Money and count columns with names like Invoice_Amount, Account_Balance, Phone_Usage_Hours
     were being turned into text identifiers. Now a column is an identifier only if its values behave like one.
  2. Category labels in Arabic, Chinese and other non-Latin scripts were all merged into one group.
"""
import ast
import pathlib
import shutil
import sys

P = pathlib.Path("wc_smart.py")
if not P.exists():
    sys.exit("wc_smart.py not found. Run this from the folder that contains it.")
t = P.read_text(encoding="utf-8")
if "_looks_like_id_values" in t:
    sys.exit("Already fixed.")
log = []


def rep(name, old, new):
    global t
    if old in t:
        t = t.replace(old, new, 1)
        log.append(("OK     ", name))
    else:
        log.append(("SKIPPED", name + "  (text not found)"))


rep("Spelling merge: keep non-Latin labels apart",
    'key = lambda x: re.sub(r"[^0-9a-z]", "", x.lower())',
    'key = lambda x: re.sub(r"[\\W_]+", "", x.lower()) or x')

rep("Helper: do the values behave like identifiers?",
    "def _infer(name, s, issues, log):",
    '''def _looks_like_id_values(s):
    x = pd.to_numeric(s.dropna(), errors="coerce").dropna()
    return bool(len(x) and x.mod(1).eq(0).all() and x.nunique() / len(x) > 0.9)


def _infer(name, s, issues, log):''')

rep("Numeric columns: identifier only if values are unique whole numbers",
    "        if id_like:\n            return \"id\", _num_to_idstr(s)",
    "        if id_like and _looks_like_id_values(s):\n            return \"id\", _num_to_idstr(s)")

rep("Text columns: name alone no longer decides",
    '    lead0 = sample.str.match(r"^0\\d+$", na=False).mean() > 0.3\n',
    '    lead0 = sample.str.match(r"^0\\d+$", na=False).mean() > 0.3\n'
    '    id_like = id_like and bool(lead0 or sample.nunique() / n > 0.9 or re.search(r"phone|(^|[_ ])tel($|[_ ])|msisdn|(^|[_ ])pin($|[_ ])|sku", nm))\n')

try:
    ast.parse(t)
except SyntaxError as e:
    print("\n".join(f"{a} {b}" for a, b in log))
    sys.exit(f"STOPPED: syntax error at line {e.lineno}. Nothing was written.")
shutil.copy(P, "wc_smart_backup.py")
P.write_text(t, encoding="utf-8")
print("\n".join(f"{a} {b}" for a, b in log))
print("\nwc_smart.py updated (original saved as wc_smart_backup.py).")