"""wc_smart.py - one-touch cleaning, imputation tournament and deep-dive dashboard
for the Westminister Consulting Intelligence Suite.

Put this file next to west.py. Needs pandas and numpy. Uses scikit-learn, plotly and
streamlit when they are installed (they already are for the app).

Design rules
  * One call does everything: smart_clean(raw) -> (clean, log, schema).
  * Never fatal: every column is handled in its own guard. A failure is written to the
    log and the column is kept as it was. The function itself cannot raise.
  * Never silent: every change is in the log; every estimated cell is listed
    (clean.attrs["wc_imputed"]); every odd value is listed (clean.attrs["wc_formats"]).
  * Deterministic: fixed random seed, so the same file gives the same data fingerprint.
  * The log keeps the exact phrases west.py's integrity() check reads
    ("Removed N completely empty rows", "Removed N exact duplicate rows",
    "Removed (column fully empty)").

Fixes in this version
  1. A numeric column is an identifier only if its values behave like one (unique whole
     numbers). Names such as Invoice_Amount, Account_Balance or Phone_Usage_Hours no longer
     turn money or count columns into text.
  2. Category labels in non-Latin scripts (Arabic, Chinese...) are no longer merged into one.
"""
import difflib
import re
import unicodedata
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

LOG_COLS = ["Step", "Column", "Action taken"]
ISS_COLS = ["Column", "Record #", "Original value", "Problem", "Action"]
NULLS = {"", "na", "n/a", "n.a", "n.a.", "nan", "null", "none", "nil", "nill", "-", "--", "---", "?", "??", "#n/a", "#value!", "#div/0!",
         "#ref!", "#name?", "#null!", "missing", "unknown", "undefined", "tbc", "tbd", "xxx", "not available", "not applicable", "(blank)", "blank"}
ID_NAME = re.compile(r"(^|_|\b)(id|code|pin|no|number|ref|invoice|phone|tel|account|sku|receipt|msisdn)(\b|_|$)")
DATE_NAME = re.compile(r"date|time|dob|month|year|period|day")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
KRA = re.compile(r"^[AP]\d{9}[A-Z]$")
KE_PHONE = re.compile(r"^(254|0)?[17]\d{8}$")
CUR = re.compile(r"(?i)\b(kes|ksh|kshs|usd|eur|gbp|sh|shs)\b\.?|[$€£₹]|/=")
ZW = re.compile(r"[\u200b-\u200f\u2060\ufeff]")
CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
DATE_FORMATS = ["%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%m-%y", "%d %b %Y", "%d %B %Y", "%d-%b-%Y",
                "%d-%b-%y", "%b %d, %Y", "%B %d, %Y", "%b %d %Y", "%Y%m%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M",
                "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d-%m-%Y %H:%M"]


def _n(x):
    try:
        return f"{float(x):,.2f}".rstrip("0").rstrip(".")
    except Exception:
        return str(x)


def _unique(cols):
    seen, out = {}, []
    for c in cols:
        if c in seen:
            seen[c] += 1
            out.append(f"{c}_{seen[c]}")
        else:
            seen[c] = 0
            out.append(c)
    return out


# ------------------------------------------------------------------ text repair
def _fix_moji(v):
    try:
        return v.encode("latin-1").decode("utf-8")
    except Exception:
        return v


def _normalise(s):
    """Unicode tidy, hidden characters, broken accents, spacing, null words. Returns (series, cells_repaired, null_words)."""
    raw = s.astype("string")
    t = raw
    touched = False
    if t.str.contains(r"[^\x00-\x7f]", regex=True, na=False).any():
        try:
            t = t.str.normalize("NFKC")
        except Exception:
            pass
        t = t.str.replace(ZW, "", regex=True)
        moji = t.str.contains("Ã|â€", na=False, regex=True)
        if moji.any():
            t = t.mask(moji, t.map(_fix_moji).astype("string"))
        touched = True
    if touched or t.str.contains(r"^\s|\s$|\s{2}|[\x00-\x08\x0b-\x1f\x7f]", regex=True, na=False).any():
        t = t.str.replace(CTRL, " ", regex=True).str.replace(r"\s+", " ", regex=True).str.strip()
        touched = True
    changed = int((t.fillna("") != raw.fillna("")).sum()) if touched else 0
    nm = t.str.lower().isin(NULLS).fillna(False).astype(bool)
    n_null = int((nm & (t.fillna("") != "")).sum())
    return (t.mask(nm, pd.NA) if nm.any() else t), changed, n_null


# ------------------------------------------------------------------ numbers
def _parse_numbers(s):
    """'KES 1,200.50', '(300)', '5-', '1.234,56', '1E5' -> floats. Returns (floats, cleaned_text, european_flag)."""
    t = s.astype("string").str.strip().str.replace(CUR, "", regex=True).str.strip()
    neg = t.str.match(r"^\(.*\)$", na=False).astype(bool) | (t.str.endswith("-").fillna(False).astype(bool) & (t.str.len().fillna(0) > 1).astype(bool))
    t = t.str.replace(r"[()%\s]", "", regex=True).str.rstrip("-")
    sample = t.dropna()
    us = int(sample.str.match(r"^-?\d{1,3}(,\d{3})+(\.\d+)?$", na=False).sum())
    eu = int(sample.str.match(r"^-?\d{1,3}(\.\d{3})+,\d+$", na=False).sum()) + int(sample.str.match(r"^-?\d+,\d{1,2}$", na=False).sum())
    european = eu > us
    t = t.str.replace(".", "", regex=False).str.replace(",", ".", regex=False) if european else t.str.replace(",", "", regex=False)
    num = pd.to_numeric(t.astype(object).where(t.notna(), np.nan), errors="coerce").astype("float64")
    return num.where(~neg, -num.abs()), t, european


def _ocr_repair(num, t):
    """Letters typed instead of digits (O for 0, l or I for 1) in a column that is clearly numeric."""
    bad = num.isna() & t.notna()
    if not bad.any():
        return num, []
    fixed = t[bad].str.replace(r"[Oo]", "0", regex=True).str.replace(r"[lI]", "1", regex=True)
    n2 = pd.to_numeric(fixed.astype(object), errors="coerce").astype("float64")
    ok = n2.notna()
    out = num.copy()
    out.loc[ok[ok].index] = n2[ok]
    return out, list(ok[ok].index)


# ------------------------------------------------------------------ dates
def _date_order(sample):
    m = sample.str.extract(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.]\d{2,4}")
    if m.isna().all().all():
        return True, None, False
    a, b = pd.to_numeric(m[0], errors="coerce"), pd.to_numeric(m[1], errors="coerce")
    ha, hb = bool((a > 12).any()), bool((b > 12).any())
    if ha and hb:
        return True, "Dates are written both day-first and month-first in this column; each was read by the only order that is valid for it.", True
    if ha:
        return True, None, False
    if hb:
        return False, "Month-first (US style) dates detected and read accordingly.", False
    return True, "Every date is ambiguous (day and month both 12 or less). Read as day/month/year (Kenyan style); verify if the source uses month first.", False


def _swap(f):
    return f.replace("%d/%m", "%m/%d").replace("%d-%m-", "%m-%d-").replace("%d.%m", "%m.%d")


def _month_first(fmts):
    return [_swap(f) for f in fmts if _swap(f) != f]


def _parse_dates(s):
    """Mixed formats row by row. Returns (datetimes, note, minority_format_count)."""
    t = s.astype("string").str.strip()
    nn = t.dropna()
    dayfirst, note, mixed = _date_order(nn.head(5000))
    if dayfirst:
        fams = DATE_FORMATS + (_month_first(DATE_FORMATS) if mixed else [])
    else:
        fams = _month_first(DATE_FORMATS) + [f for f in DATE_FORMATS if _swap(f) == f]
    src = nn.sample(3000, random_state=0) if len(nn) > 3000 else nn
    cover = {}
    for f in dict.fromkeys(fams):
        try:
            cover[f] = int(pd.to_datetime(src, format=f, errors="coerce").notna().sum())
        except Exception:
            cover[f] = 0
    out = pd.to_datetime(pd.Series(pd.NaT, index=t.index))
    n_first = 0
    for k, f in enumerate([f for f in sorted(cover, key=lambda q: -cover[q]) if cover[f] > 0]):
        todo = out.isna() & t.notna()
        if not todo.any():
            break
        p = pd.to_datetime(t[todo], format=f, errors="coerce")
        if k == 0:
            n_first = int(p.notna().sum())
        out = out.fillna(p)
    rest = out.isna() & t.notna()
    if rest.any():
        try:
            p = pd.to_datetime(t[rest], errors="coerce", dayfirst=dayfirst, format="mixed")
        except Exception:
            p = pd.to_datetime(t[rest], errors="coerce", dayfirst=dayfirst)
        out = out.fillna(p)
    minority = int(out.notna().sum() - n_first)
    return out, note, max(minority, 0)


# ------------------------------------------------------------------ categories
def _unify(s):
    """Merge spelling, case, spacing and punctuation variants; fix rare near-miss typos. Returns (series, merges)."""
    v = s.dropna().astype(str)
    if v.empty:
        return s, []
    vc = v.value_counts()
    # FIX 2: unicode-aware key, and a value with no letters or digits keeps itself as its key
    key = lambda x: re.sub(r"[\W_]+", "", x.lower()) or x
    groups = {}
    for val, cnt in vc.items():
        groups.setdefault(key(val), []).append((val, int(cnt)))
    canon, merges, reps = {}, [], {}
    for items in groups.values():
        best = items[0][0]
        reps[best] = sum(c for _, c in items)
        for val, cnt in items[1:]:
            canon[val] = best
            merges.append((val, best, cnt))
    names = sorted(reps, key=lambda r: -reps[r])
    if len(names) <= 150:
        for i, small in enumerate(names):
            if len(small) < 5 or small in canon:
                continue
            best, br = None, 0.9
            for big in names[:i]:
                if reps[small] > 0.1 * reps[big] or abs(len(big) - len(small)) > 2 or big in canon:
                    continue
                if re.findall(r"\d+", big) != re.findall(r"\d+", small):
                    continue
                r = difflib.SequenceMatcher(None, small.lower(), big.lower()).ratio()
                if r >= br:
                    best, br = big, r
            if best:
                canon[small] = best
                merges.append((small, best, reps[small]))
    for k in list(canon):
        while canon[k] in canon and canon[canon[k]] != canon[k]:
            canon[k] = canon[canon[k]]
    if not canon:
        return s, []
    return s.astype(object).map(lambda x: canon.get(x, x)), merges


def _sig(t):
    return t.str.replace(r"\d", "9", regex=True).str.replace(r"[A-Z]", "A", regex=True).str.replace(r"[a-z]", "a", regex=True)


# ------------------------------------------------------------------ column typing
def _num_to_idstr(s):
    x = pd.to_numeric(s, errors="coerce")
    if x.dropna().mod(1).eq(0).all():
        return x.round().astype("Int64").astype("string").astype(object).where(s.notna(), pd.NA)
    return s.astype("string").astype(object)


def _looks_like_id_values(s):
    """FIX 1: identifiers are unique whole numbers. Amounts, balances and counts repeat or have decimals."""
    x = pd.to_numeric(s.dropna(), errors="coerce").dropna()
    return bool(len(x) and x.mod(1).eq(0).all() and x.nunique() / len(x) > 0.9)


def _infer(name, s, issues, log):
    """Decide the kind of a column and convert it. Returns (kind, converted)."""
    nm = name.lower()
    id_like = bool(ID_NAME.search(nm)) and not DATE_NAME.search(nm)
    if s.isna().all():
        return "empty", s
    if pd.api.types.is_datetime64_any_dtype(s):
        return "datetime", s
    if pd.api.types.is_bool_dtype(s):
        return "boolean", s
    if pd.api.types.is_numeric_dtype(s):
        if id_like and _looks_like_id_values(s):
            return "id", _num_to_idstr(s)
        x = s.astype("float64")
        if DATE_NAME.search(nm) and 20000 <= x.median() <= 60000 and x.dropna().mod(1).eq(0).all():
            log.append(("Dates", name, "Excel serial numbers converted to real dates"))
            return "datetime", pd.to_datetime(x, unit="D", origin="1899-12-30", errors="coerce")
        return ("integer" if x.dropna().mod(1).eq(0).all() else "numeric"), x
    t = s.astype("string")
    sample = t.dropna()
    n = max(len(sample), 1)
    low = sample.str.lower()
    if low.isin({"yes", "no", "true", "false", "y", "n"}).mean() > 0.95 and low.nunique() <= 4:
        return "boolean", t.str.lower().map({"yes": True, "y": True, "true": True, "no": False, "n": False, "false": False}).astype(object)
    lead0 = sample.str.match(r"^0\d+$", na=False).mean() > 0.3
    # FIX 1: for text columns the name alone does not decide; the values must also look like identifiers
    id_like = id_like and bool(lead0 or sample.nunique() / n > 0.9 or re.search(r"phone|(^|[_ ])tel($|[_ ])|msisdn|(^|[_ ])pin($|[_ ])|sku", nm))
    samp = sample.sample(5000, random_state=0) if len(sample) > 5000 else sample
    looks_num = _parse_numbers(samp)[0].notna().mean() >= 0.9 and not id_like and not lead0
    if looks_num:
        num, tt, european = _parse_numbers(t)
    if looks_num and num.notna().sum() / n >= 0.9:
        before = num.isna()
        num, fixed_idx = _ocr_repair(num, tt)
        for i in fixed_idx[:50]:
            issues.append((name, int(i) + 1 if isinstance(i, (int, np.integer)) else i, str(t.get(i)), "Letter typed instead of a digit", f"Read as {_n(num.get(i))}"))
        if fixed_idx:
            log.append(("Format", name, f"{len(fixed_idx)} values had letters typed instead of digits (O for 0, l or I for 1) and were repaired"))
        if european:
            log.append(("Format", name, "Numbers written with comma decimals and dot thousands (1.234,56) were read correctly"))
        if t.str.contains("%", na=False).any():
            log.append(("Format", name, "Percent signs removed; values kept as written (12% becomes 12)"))
        if t.str.contains(CUR.pattern, na=False, regex=True).any():
            log.append(("Format", name, "Currency symbols and words removed from amounts"))
        unread = (t.notna() & num.isna())
        for i in unread[unread].index[:200]:
            issues.append((name, int(i) + 1, str(t[i]), "Not readable as a number", "Became blank, then estimated"))
        return ("integer" if num.dropna().mod(1).eq(0).all() else "numeric"), num
    if not id_like and not lead0 and not (sample.str.fullmatch(r"\d{1,4}").mean() > 0.5):
        has_sep = samp.str.contains(r"[-/.:\s]", regex=True).mean() > 0.9 or DATE_NAME.search(nm)
        if has_sep and _parse_dates(samp)[0].notna().mean() >= 0.9:
            dt, note, minority = _parse_dates(t)
        else:
            dt, note, minority, has_sep = None, None, 0, False
        if has_sep and dt.notna().sum() / n >= 0.9:
            if note:
                log.append(("Dates", name, note))
            if minority:
                log.append(("Dates", name, f"{minority} dates were written in a different format from the rest and were standardised"))
            bad = t.notna() & dt.isna()
            for i in bad[bad].index[:200]:
                issues.append((name, int(i) + 1, str(t[i]), "Not readable as a date", "Left blank"))
            return "datetime", dt
    if id_like or sample.nunique() / n > 0.9:
        return "id", t.astype(object)
    if sample.nunique() <= max(20, 0.05 * n):
        return "category", t.astype(object)
    return "text", t.astype(object)


def _role_fix(name, s, kind, issues, log):
    """Emails, Kenyan phone numbers and KRA PINs: standardise the way they are written, flag the rest."""
    if kind not in ("id", "text", "category"):
        return s
    t = s.astype("string")
    sample = t.dropna()
    if sample.empty:
        return s
    if len(sample) > 3000:
        sample = sample.sample(3000, random_state=0)
    nm = name.lower()
    if sample.str.contains("@", regex=False).mean() >= 0.6:
        new = t.str.replace(r"\s+", "", regex=True).str.lower()
        ch = int((new.fillna("") != t.fillna("")).sum())
        if ch:
            log.append(("Format", name, f"{ch} email addresses standardised (lower case, no spaces)"))
        bad = new.notna() & ~new.str.match(EMAIL.pattern, na=False).astype(bool)
        for i in bad[bad].index[:200]:
            issues.append((name, int(i) + 1, str(new[i]), "Not a valid email address", "Left as written; verify at source"))
        return new.astype(object)
    digits = sample.str.replace(r"\D", "", regex=True)
    if (re.search(r"phone|mobile|msisdn|(^|[_\s])tel($|[_\s])|contact", nm) or digits.str.len().between(9, 13).mean() > 0.9) and digits.str.match(KE_PHONE.pattern, na=False).mean() >= 0.6:
        def ph(v):
            if pd.isna(v):
                return v
            d = re.sub(r"\D", "", str(v))
            if len(d) == 9 and d[0] in "17":
                return "254" + d
            if len(d) == 10 and d[0] == "0" and d[1] in "17":
                return "254" + d[1:]
            return d if len(d) == 12 and d.startswith("254") and d[3] in "17" else v
        new = t.astype(object).map(ph)
        ch = int((new.astype("string").fillna("") != t.fillna("")).sum())
        if ch:
            log.append(("Format", name, f"{ch} phone numbers written in the Kenyan 254XXXXXXXXX format"))
        bad = new.notna() & ~new.astype("string").str.match(r"^254[17]\d{8}$", na=False).astype(bool)
        for i in bad[bad].index[:200]:
            issues.append((name, int(i) + 1, str(new[i]), "Not a valid Kenyan mobile number", "Left as written; confirm with the person"))
        return new
    if sample.str.upper().str.replace(r"[\s\-]", "", regex=True).str.match(KRA.pattern, na=False).mean() >= 0.6:
        up = t.str.upper().str.replace(r"[\s\-]", "", regex=True)

        def pin(v):
            if pd.isna(v) or KRA.match(v) or len(v) != 11 or v[0] not in "AP" or not v[-1].isalpha():
                return v
            return v[0] + v[1:10].translate(str.maketrans("OIL", "011")) + v[-1]
        new = up.astype(object).map(pin)
        ch = int((new.astype("string").fillna("") != t.fillna("")).sum())
        if ch:
            log.append(("Format", name, f"{ch} KRA PINs standardised (upper case, no spaces or dashes, O/I mistyped for digits repaired)"))
        bad = new.notna() & ~new.astype("string").str.match(KRA.pattern, na=False).astype(bool)
        for i in bad[bad].index[:200]:
            issues.append((name, int(i) + 1, str(new[i]), "Not a valid KRA PIN (A or P + 9 digits + letter)", "Left as written; verify on iTax"))
        return new
    return s


def _pattern_audit(name, s, issues):
    """Row-by-row check: values that do not follow the column's usual shape (letters, digits, separators, length)."""
    t = s.astype("string")
    t = t[t.notna() & (t != "Not Provided")]
    if len(t) < 20:
        return 0
    vc = _sig(t.sample(5000, random_state=0) if len(t) > 5000 else t).value_counts()
    if len(vc) < 2 or len(vc) > 12 or vc.iloc[0] / vc.sum() < 0.8:
        return 0
    sg = _sig(t)
    vc = sg.value_counts()
    if len(vc) < 2 or len(vc) > 12 or vc.iloc[0] / len(t) < 0.8:
        return 0
    usual = vc.index[0]
    odd = sg[sg != usual]
    for i in odd.index[:100]:
        issues.append((name, int(i) + 1, str(t[i]), f"Does not follow this column's usual format ({usual})", "Check the source record"))
    return len(odd)


# ------------------------------------------------------------------ missing values
def _arith_holds(d, q, p, t):
    Q, P, T = d[q], d[p], d[t]
    full = Q.notna() & P.notna() & T.notna()
    if full.sum() < 20:
        return 0.0
    return float(((Q * P - T).abs() <= 0.01 * T.abs().clip(lower=1))[full].mean())


def _arith_repair(d, schema, imputed, log, rec):
    """Quantity x price = total: find the three columns for which the rule really holds, then fill a missing one of them exactly."""
    nums = [c for c, k in schema.items() if k in ("numeric", "integer") and c in d.columns]
    find = lambda rx: [c for c in nums if re.search(rx, c.lower())]
    qs, ps, ts = find(r"qty|quantity|units|pieces")[:3], find(r"price|rate|unit.?cost")[:3], find(r"total|amount|line|gross|value")[:5]
    chosen = None
    for q in qs:
        for p in ps:
            for t in ts:
                if len({q, p, t}) == 3:
                    h = _arith_holds(d, q, p, t)
                    if h >= 0.98:
                        chosen = (q, p, t, h)
                        break
            if chosen:
                break
        if chosen:
            break
    if not chosen:
        return
    q, p, t, holds = chosen
    Q, P, T = d[q], d[p], d[t]
    for tgt, expr, label in ((t, lambda: Q * P, f"{q} x {p}"), (q, lambda: T / P.where(P != 0), f"{t} / {p}"), (p, lambda: T / Q.where(Q != 0), f"{t} / {q}")):
        d_t = d[tgt]
        calc = expr()
        m = d_t.isna() & calc.notna()
        if tgt == q and schema[q] == "integer":
            calc = calc.round()
        if m.any():
            d.loc[m, tgt] = calc[m]
            imputed[tgt] = imputed[tgt] | m
            for i in m[m].index:
                rec.append((int(i) + 1, tgt, float(d.at[i, tgt]), "Exact calculation"))
            log.append(("Missing", tgt, f"{int(m.sum())} blanks computed exactly as {label}. Why: this relationship holds in {holds:.1%} of complete rows, so the value is arithmetic, not an estimate."))


def _best_groupers(d, yv, known, cats, k=3):
    out = []
    for p in cats:
        g = pd.DataFrame({"g": d[p].astype(object).where(d[p].notna(), "__NA__").to_numpy()[known], "y": yv[known]})
        mean, sst = g["y"].mean(), ((g["y"] - g["y"].mean()) ** 2).sum()
        if sst > 0:
            grp = g.groupby("g")["y"]
            out.append(((grp.count() * (grp.mean() - mean) ** 2).sum() / sst, p))
    return [p for _, p in sorted(out, reverse=True)[:k]]


def _codes(s):
    c = pd.factorize(s)[0].astype(float)
    c[c < 0] = np.nan
    return c


def _num_tournament(d, c, cats, nums, dates, rng):
    """Hide 15% of the known values, let every method try to recover them, keep the most accurate method."""
    yv = d[c].to_numpy(dtype=float)
    known = ~np.isnan(yv)
    kpos, miss = np.flatnonzero(known), np.flatnonzero(~known)
    if len(kpos) < 40 or len(miss) == 0:
        return None
    lo, hi = float(np.min(yv[known])), float(np.max(yv[known]))
    cands = {"Median": lambda fit, pos: np.full(len(pos), np.median(yv[fit])), "Mean": lambda fit, pos: np.full(len(pos), np.mean(yv[fit]))}

    def grp(p):
        codes = d[p].astype(object).where(d[p].notna(), "__NA__").to_numpy()

        def f(fit, pos):
            g = pd.DataFrame({"g": codes[fit], "y": yv[fit]}).groupby("g")["y"].agg(["median", "count"])
            m = g.loc[g["count"] >= 3, "median"]
            return pd.Series(codes[pos]).map(m).fillna(np.median(yv[fit])).to_numpy(dtype=float)
        return f
    for p in _best_groupers(d, yv, known, [x for x in cats if x != c]):
        cands[f"Group median by {p}"] = grp(p)
    dc = next((x for x in dates if d[x].notna().mean() >= 0.9), None)
    if dc:
        key = (d[dc] - pd.Timestamp("1970-01-01")).dt.total_seconds().fillna(np.inf).to_numpy()
        order = np.argsort(key, kind="stable")

        def interp(fit, pos):
            arr = pd.Series(np.where(fit, yv, np.nan)[order]).interpolate(limit_direction="both").to_numpy()
            out = np.empty(len(yv))
            out[order] = arr
            return out[pos]
        cands["Interpolate in date order"] = interp
    feats = [d[x].to_numpy(dtype=float) for x in nums if x != c][:10]
    feats += [_codes(d[x]) for x in cats if x != c][:4]
    if dc:
        feats.append(((d[dc] - pd.Timestamp("1970-01-01")).dt.days).to_numpy(dtype=float))
    if feats and len(kpos) >= 60:
        try:
            from sklearn.ensemble import HistGradientBoostingRegressor
            X = np.column_stack(feats)

            def model(fit, pos):
                idx = np.flatnonzero(fit)
                if len(idx) > 20000:
                    idx = rng.choice(idx, 20000, replace=False)
                m = HistGradientBoostingRegressor(max_iter=80, max_depth=4, random_state=0).fit(X[idx], yv[idx])
                return m.predict(X[pos])
            cands["Model on related columns"] = model
        except Exception:
            pass
    test = rng.choice(kpos, size=int(min(max(len(kpos) * 0.15, 10), 2000)), replace=False)
    fit = known.copy()
    fit[test] = False
    truth, scores = yv[test], {}
    for name, fn in cands.items():
        try:
            e = float(np.nanmean(np.abs(np.clip(np.asarray(fn(fit, test), float), lo, hi) - truth)))
            if np.isfinite(e):
                scores[name] = e
        except Exception:
            pass
    if not scores:
        return None
    simple = "Median" if scores.get("Median", np.inf) <= scores.get("Mean", np.inf) else "Mean"
    best = min(scores, key=scores.get)
    if scores[best] > 0.95 * scores[simple]:
        best = simple
    pr = np.clip(np.asarray(cands[best](known, miss), float), lo, hi)
    pr = np.where(np.isnan(pr), np.median(yv[known]), pr)
    return best, scores, len(test), miss, pr


def _cat_tournament(d, c, cats, rng):
    v = d[c].astype(object).to_numpy()
    known = pd.notna(v)
    kpos, miss = np.flatnonzero(known), np.flatnonzero(~known)
    if len(miss) == 0 or len(kpos) == 0:
        return None
    mode = lambda fit: pd.Series(v[fit]).value_counts().index[0]
    share = pd.Series(v[known]).value_counts(normalize=True).iloc[0]
    cands = {"Most common value": lambda fit, pos: np.array([mode(fit)] * len(pos), dtype=object)}

    def grp(p):
        codes = d[p].astype(object).where(d[p].notna(), "__NA__").to_numpy()

        def f(fit, pos):
            g = pd.DataFrame({"g": codes[fit], "v": v[fit]}).groupby("g")["v"].agg(lambda x: x.value_counts().index[0])
            return pd.Series(codes[pos]).map(g).fillna(mode(fit)).to_numpy(dtype=object)
        return f
    for p in [x for x in cats if x != c and 2 <= d[x].nunique() <= 30][:3]:
        cands[f"Most common value within {p}"] = grp(p)
    if len(kpos) < 40:
        return ("Most common value", {"Most common value": share}, 0, miss, cands["Most common value"](known, miss)) if share >= 0.4 else ("Not Provided", {}, 0, miss, np.array(["Not Provided"] * len(miss), dtype=object))
    test = rng.choice(kpos, size=int(min(max(len(kpos) * 0.15, 10), 2000)), replace=False)
    fit = known.copy()
    fit[test] = False
    truth, scores = v[test], {}
    for name, fn in cands.items():
        try:
            scores[name] = float(np.mean(np.asarray(fn(fit, test), dtype=object) == truth))
        except Exception:
            pass
    best = max(scores, key=scores.get)
    if best != "Most common value" and scores[best] < scores.get("Most common value", 0) + 0.02:
        best = "Most common value"
    if scores[best] < 0.4:
        return "Not Provided", scores, len(test), miss, np.array(["Not Provided"] * len(miss), dtype=object)
    return best, scores, len(test), miss, np.asarray(cands[best](known, miss), dtype=object)


def _impute(d, schema, imputed, log, rec):
    rng = np.random.default_rng(0)
    cats = [c for c, k in schema.items() if k == "category" and c in d.columns and 2 <= d[c].nunique() <= 30]
    nums = [c for c, k in schema.items() if k in ("numeric", "integer") and c in d.columns]
    dates = [c for c, k in schema.items() if k == "datetime" and c in d.columns]
    for c in list(d.columns):
        try:
            k = schema.get(c)
            na = d[c].isna()
            m = int(na.sum())
            if not m:
                continue
            pct = m / len(d) * 100
            if pct > 60:
                log.append(("Missing", c, f"{m} blanks ({pct:.1f}%) -> Leave blank. Why: {pct:.0f}% of this column is blank, so any estimate would be mostly invented. Recollect the data or exclude the column."))
                continue
            how, why, method = None, "", ""
            if k in ("numeric", "integer"):
                res = _num_tournament(d, c, cats, nums, dates, rng)
                if res:
                    method, sc, nt, pos, pr = res
                    if k == "integer":
                        pr = np.round(pr)
                    d.iloc[pos, d.columns.get_loc(c)] = pr
                    top = "; ".join(f"{a} {_n(b)}" for a, b in sorted(sc.items(), key=lambda kv: kv[1])[:4])
                    why = f"tested {len(sc)} methods by hiding {nt} known values at random; average error per method: {top}. The most accurate was kept (a fancier method is used only if it beats the median by 5% or more)."
                else:
                    x = d[c].dropna()
                    sk = x.skew() if len(x) > 2 else 0
                    method = "Median" if abs(sk) > 1 else "Mean"
                    d[c] = d[c].fillna(x.median() if method == "Median" else x.mean())
                    if k == "integer":
                        d[c] = d[c].round()
                    why = f"fewer than 40 known values, too few to test methods; chose by shape (skew {sk:.1f})."
                    pos = np.flatnonzero(na.to_numpy())
                if pct > 20:
                    why += f" Caution: {pct:.0f}% of this column is estimated, so treat its totals as indicative."
            elif k in ("category", "boolean"):
                if k == "boolean":
                    vc = d[c].dropna().astype(str).value_counts(normalize=True)
                    if len(vc) and vc.iloc[0] >= 0.6:
                        arr = d[c].astype(object).to_numpy(copy=True)
                        pos = np.flatnonzero(na.to_numpy())
                        arr[pos] = d[c].dropna().mode().iat[0]
                        d[c] = arr
                        method, why = "Most common value", f"'{vc.index[0]}' is {vc.iloc[0]*100:.0f}% of known answers."
                    else:
                        log.append(("Missing", c, f"{m} blanks ({pct:.1f}%) -> Leave blank. Why: no answer dominates, so a guess would often be wrong."))
                        continue
                else:
                    res = _cat_tournament(d, c, cats, rng)
                    if not res:
                        continue
                    method, sc, nt, pos, pr = res
                    arr = d[c].astype(object).to_numpy(copy=True)
                    arr[pos] = pr
                    d[c] = arr
                    why = (f"tested {len(sc)} methods by hiding {nt} known values; hit rate: " + "; ".join(f"{a} {b*100:.0f}%" for a, b in sorted(sc.items(), key=lambda kv: -kv[1])[:3]) + ".") if sc else "simple rule."
                    if method == "Not Provided":
                        why += " No method guessed right at least 40% of the time, so the gap is marked 'Not Provided' rather than guessed."
            elif k == "datetime":
                x = d[c]
                if x.notna().sum() > 2 and x.dropna().is_monotonic_increasing and pct <= 5:
                    ns = (x - pd.Timestamp("1970-01-01")).dt.total_seconds()
                    d[c] = pd.to_datetime(ns.interpolate(limit_area="inside").round(), unit="s")
                    method, why = "Interpolate between neighbours", "the dates are in time order, so a missing date lies between its neighbours."
                    pos = np.flatnonzero(na.to_numpy() & d[c].notna().to_numpy())
                else:
                    log.append(("Missing", c, f"{m} blanks ({pct:.1f}%) -> Leave blank. Why: a date cannot be guessed without inventing history."))
                    continue
            else:
                d[c] = d[c].astype(object).where(d[c].notna(), "Not Provided")
                method, why = "Not Provided", "identifiers and free text can never be estimated; marking them lets you follow up with the source."
                pos = np.flatnonzero(na.to_numpy())
            filled = na & d[c].notna()
            imputed[c] = imputed[c] | filled
            for i in np.asarray(pos)[:50000]:
                rec.append((int(i) + 1, c, d.iat[int(i), d.columns.get_loc(c)], method))
            log.append(("Missing", c, f"{m} blanks ({pct:.1f}%) -> {method}. Why: {why}"))
        except Exception as e:
            log.append(("Missing", c, f"Skipped ({type(e).__name__}: {str(e)[:80]}); blanks left as they were"))


# ------------------------------------------------------------------ main entry
def _smart_clean(df, impute, drop_dupes):
    log, issues, rec = [], [], []
    d = df.copy()
    rows0, cols0 = d.shape
    d.columns = _unique([re.sub(r"\s+", " ", str(c)).strip() or f"Column_{i + 1}" for i, c in enumerate(d.columns)])
    for c in list(d.columns):
        s = d[c]
        if pd.api.types.is_object_dtype(s) or pd.api.types.is_string_dtype(s):
            try:
                t, ch, nn = _normalise(s)
                d[c] = t
                if ch:
                    log.append(("Text", c, f"Repaired {ch} cells (extra spaces, hidden characters, broken accents)"))
                if nn:
                    log.append(("Text", c, f"{nn} placeholder words (N/A, -, unknown, TBC...) treated as blank"))
            except Exception as e:
                log.append(("Text", c, f"Text repair skipped ({type(e).__name__})"))
    d = d.dropna(how="all")
    empty = [c for c in d.columns if d[c].isna().all()]
    d = d.drop(columns=empty)
    if rows0 - len(d):
        log.append(("Structure", "-", f"Removed {rows0 - len(d)} completely empty rows"))
    for c in empty:
        log.append(("Structure", c, "Removed (column fully empty)"))
    schema = {}
    for c in list(d.columns):
        try:
            kind, conv = _infer(c, d[c], issues, log)
            if kind in ("numeric", "integer", "datetime", "boolean"):
                log.append(("Type", c, f"Converted to {kind}"))
            elif kind == "id":
                log.append(("Type", c, "Kept as text identifier (not converted to number)"))
            conv = _role_fix(c, conv, kind, issues, log)
            if kind == "category":
                conv, merges = _unify(conv)
                if merges:
                    ex = "; ".join(f"'{a}' to '{b}'" for a, b, _ in merges[:4])
                    log.append(("Consistency", c, f"Standardised {sum(x[2] for x in merges)} inconsistent spellings/cases/typos ({len(merges)} variants, e.g. {ex})"))
            elif kind == "id":
                _pattern_audit(c, conv, issues)
            d[c] = conv
            schema[c] = kind
        except Exception as e:
            schema[c] = "text"
            log.append(("Type", c, f"Left as it was ({type(e).__name__}: {str(e)[:80]})"))
    if drop_dupes:
        n = int(d.duplicated().sum())
        if n:
            d = d.drop_duplicates()
            log.append(("Duplicates", "-", f"Removed {n} exact duplicate rows"))
    d = d.reset_index(drop=True)
    imputed = pd.DataFrame(False, index=d.index, columns=d.columns)
    if impute:
        _arith_repair(d, schema, imputed, log, rec)
        _impute(d, schema, imputed, log, rec)
    for c, k in schema.items():
        if k == "integer" and c in d and pd.api.types.is_numeric_dtype(d[c]):
            d[c] = d[c].round()
    log.append(("Summary", "-", f"{rows0:,} x {cols0} -> {d.shape[0]:,} x {d.shape[1]}"))
    d.attrs["wc_formats"] = pd.DataFrame(issues[:20000], columns=ISS_COLS)
    d.attrs["wc_imputed"] = pd.DataFrame(rec[:200000], columns=["Row", "Column", "Filled value", "Method"]).astype({"Filled value": "string"})
    d.attrs["wc_imputed_counts"] = {c: int(imputed[c].sum()) for c in d.columns if imputed[c].any()}
    return d, pd.DataFrame(log, columns=LOG_COLS), schema


def smart_clean(df, impute=True, drop_dupes=True):
    """Same return shape as west.py's auto_clean: (clean_df, log_df, schema). Cannot raise."""
    try:
        return _smart_clean(df, impute, drop_dupes)
    except Exception as e:
        out = df.copy()
        out.attrs["wc_formats"] = pd.DataFrame(columns=ISS_COLS)
        out.attrs["wc_imputed"] = pd.DataFrame(columns=["Row", "Column", "Filled value", "Method"])
        out.attrs["wc_imputed_counts"] = {}
        log = pd.DataFrame([("Summary", "-", f"Smart cleaning could not finish ({type(e).__name__}: {str(e)[:120]}). The original data was kept unchanged.")], columns=LOG_COLS)
        return out, log, {c: "text" for c in out.columns}


# ------------------------------------------------------------------ streamlit: cleaning report
def render_cleaning_report(df, log):
    import streamlit as st
    fm = df.attrs.get("wc_formats", pd.DataFrame(columns=ISS_COLS))
    im = df.attrs.get("wc_imputed", pd.DataFrame(columns=["Row", "Column", "Filled value", "Method"]))
    cnt = df.attrs.get("wc_imputed_counts", {})
    st.markdown("### One-touch cleaning report")
    steps = log["Step"].value_counts() if log is not None and len(log) else pd.Series(dtype=int)
    c = st.columns(4)
    c[0].metric("Cells estimated", f"{sum(cnt.values()):,}")
    c[1].metric("Format repairs logged", f"{int(steps.get('Format', 0) + steps.get('Dates', 0) + steps.get('Text', 0)):,}")
    c[2].metric("Spelling groups merged", f"{int(steps.get('Consistency', 0)):,}")
    c[3].metric("Odd values to review", f"{len(fm):,}")
    with st.expander("Missing values: what was done to each column, and why", expanded=True):
        m = log[log["Step"] == "Missing"] if log is not None and len(log) else pd.DataFrame()
        if len(m):
            st.dataframe(m, width="stretch", hide_index=True)
        else:
            st.success("There were no blanks to fill.")
    with st.expander(f"Wrong or unusual formats found ({len(fm):,})"):
        if len(fm):
            st.dataframe(fm.head(2000), width="stretch", hide_index=True)
            st.download_button("Download format findings (CSV)", fm.to_csv(index=False).encode(), "format_findings.csv", "text/csv", key="wc_fm_dl")
        else:
            st.success("Every value follows the usual format of its column.")
    with st.expander(f"Every estimated cell ({len(im):,})"):
        if len(im):
            st.caption("Estimated cells are flagged here so no figure in the report can pass as original data.")
            st.dataframe(im.head(2000), width="stretch", hide_index=True)
            st.download_button("Download estimated cells (CSV)", im.to_csv(index=False).encode(), "estimated_cells.csv", "text/csv", key="wc_im_dl")
        else:
            st.caption("No cells were estimated.")


# ------------------------------------------------------------------ streamlit: deep-dive dashboard
INK, PANEL, LINE, BRASS, TEXT, MUTED = "#061625", "#0C2238", "#1E3A57", "#C9A24F", "#E8EDF2", "#8FA3B8"
SEQ = [[0, "#0C2238"], [1, BRASS]]


def _style(fig, h=340):
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=h, margin=dict(l=10, r=10, t=50, b=10),
                      font=dict(family="IBM Plex Sans, sans-serif", color=TEXT), title=dict(font=dict(size=15)), colorway=[BRASS, "#4FA3C7", "#7FB77E", "#B58DB6", "#E0A84A", "#E06C6C"])
    fig.update_xaxes(gridcolor=LINE, zeroline=False)
    fig.update_yaxes(gridcolor=LINE, zeroline=False)
    return fig


def render_pro_dashboard(df, U, kd=None, insights=()):
    """Interactive deep dive. Every panel is guarded: one failing panel never breaks the page."""
    import plotly.express as px
    import plotly.graph_objects as go
    import streamlit as st

    def safe(title, fn):
        try:
            fn()
        except Exception as e:
            st.caption(f"{title}: not available for this file ({type(e).__name__}).")
    roles = U["roles"]
    nums = [c for c, (r, _, _) in roles.items() if r in ("money", "quantity", "measure", "age", "percentage") and c in df and pd.api.types.is_numeric_dtype(df[c])]
    dates = [c for c in U["dates"] if c in df]
    cats = [c for c in U["dims"] if c in df and df[c].nunique() <= 60][:6]
    st.markdown("## Deep dive")
    if not nums:
        st.info("This file has no numeric measure, so only record counts can be analysed.")
    flt = df
    with st.expander("Focus the analysis (filters)"):
        cols = st.columns(3)
        for i, c in enumerate(cats[:3]):
            pick = cols[i].multiselect(c, sorted(df[c].dropna().astype(str).unique())[:100], key=f"wcp_f_{c}")
            if pick:
                flt = flt[flt[c].astype(str).isin(pick)]
        if dates:
            lo, hi = df[dates[0]].min(), df[dates[0]].max()
            if pd.notna(lo) and lo < hi:
                rng = st.date_input("Period", (lo.date(), hi.date()), key="wcp_range")
                if isinstance(rng, (tuple, list)) and len(rng) == 2:
                    flt = flt[(flt[dates[0]] >= pd.Timestamp(rng[0])) & (flt[dates[0]] <= pd.Timestamp(rng[1]) + pd.Timedelta(days=1))]
    c1, c2, c3, c4 = st.columns(4)
    measure = c1.selectbox("Measure", nums or ["Records"], index=nums.index(U["metric"]) if U.get("metric") in nums else 0, key="wcp_m")
    dcol = c2.selectbox("Date", dates, key="wcp_d") if dates else None
    gran = c3.selectbox("Period", ["Month", "Week", "Quarter", "Day"], key="wcp_g")
    gcol = c4.selectbox("Group by", cats, key="wcp_c") if cats else None
    additive = measure != "Records" and roles.get(measure, ("measure",))[0] in ("money", "quantity")
    how = "sum" if additive or measure == "Records" else "mean"
    if len(flt) == 0:
        st.warning("No records match these filters.")
        return
    y = flt[measure] if measure in flt else pd.Series(1, index=flt.index)
    ser = None
    if dcol:
        tmp = pd.DataFrame({"d": flt[dcol], "y": y}).dropna()
        if len(tmp):
            ser = tmp.set_index("d")["y"].resample({"Day": "D", "Week": "W-MON", "Month": "MS", "Quarter": "QS"}[gran]).agg(how)
    tot = float(y.sum()) if how == "sum" else float(y.mean())
    kp = [("Records", f"{len(flt):,}", f"of {len(df):,}"), (("Total " if how == "sum" else "Average ") + measure, f"{tot:,.0f}", None),
          ("Median " + measure, f"{float(y.median()):,.0f}", None)]
    if ser is not None and len(ser) >= 2 and ser.iloc[-2]:
        kp.append((f"Latest {gran.lower()} vs previous", f"{(ser.iloc[-1] / ser.iloc[-2] - 1) * 100:+.1f}%", "latest period may be partial"))
    try:
        import wc_ui
        wc_ui.kpi_row(kp)
    except Exception:
        for col, (a, b, _) in zip(st.columns(len(kp)), kp):
            col.metric(a, b)

    def trend():
        if ser is None or len(ser) < 2:
            st.caption("A trend needs a date column with at least two periods.")
            return
        f = go.Figure()
        f.add_bar(x=ser.index, y=ser.values, name=measure, marker_color="rgba(201,162,79,.55)")
        f.add_scatter(x=ser.index, y=ser.rolling(3, min_periods=1).mean(), name="3-period average", line=dict(color="#E8EDF2", width=2))
        f.add_scatter(x=[ser.idxmax()], y=[ser.max()], mode="markers+text", text=["peak"], textposition="top center", marker=dict(size=10, color="#E06C6C"), showlegend=False)
        f.update_layout(title=f"{measure} by {gran.lower()}", legend=dict(orientation="h", y=1.12))
        st.plotly_chart(_style(f), width="stretch")

    def groups():
        if not gcol:
            return
        g = (flt.groupby(gcol)[measure].agg(how) if measure in flt else flt[gcol].value_counts()).sort_values(ascending=False)
        top = g.head(10)[::-1]
        share = top / g.sum() * 100 if g.sum() else top * 0
        f = go.Figure(go.Bar(x=top.values, y=top.index.astype(str), orientation="h", marker_color=BRASS, text=[f"{s:.0f}%" for s in share], textposition="outside"))
        f.update_layout(title=f"Top {gcol} by {measure} (share of total)")
        st.plotly_chart(_style(f), width="stretch")
    a, b = st.columns([1.4, 1])
    with a:
        safe("Trend", trend)
    with b:
        safe("Groups", groups)

    def dist():
        x = y.dropna()
        f = px.histogram(x, nbins=40, title=f"Distribution of {measure}")
        f.add_vline(x=float(x.median()), line_color="#E8EDF2", annotation_text="median")
        f.update_layout(showlegend=False, xaxis_title=None, yaxis_title=None)
        st.plotly_chart(_style(f), width="stretch")

    def box():
        if not gcol or measure not in flt:
            return
        keep = flt[gcol].value_counts().head(8).index
        f = px.box(flt[flt[gcol].isin(keep)], x=gcol, y=measure, title=f"Spread of {measure} by {gcol}", points=False)
        f.update_layout(showlegend=False, xaxis_title=None, yaxis_title=None)
        st.plotly_chart(_style(f), width="stretch")
    a, b = st.columns(2)
    with a:
        safe("Distribution", dist)
    with b:
        safe("Spread", box)

    def season():
        if not dcol or measure not in flt:
            return
        t = flt[[dcol, measure]].dropna()
        if t[dcol].dt.to_period("M").nunique() < 13:
            st.caption("The seasonality map appears once the file covers more than 12 months.")
            return
        pv = t.assign(Year=t[dcol].dt.year, Month=t[dcol].dt.month).pivot_table(index="Year", columns="Month", values=measure, aggfunc=how)
        f = px.imshow(pv, color_continuous_scale=SEQ, aspect="auto", title=f"Seasonality of {measure} (year by month)", labels=dict(color=measure))
        st.plotly_chart(_style(f, 300), width="stretch")

    def corr():
        use = [c for c in nums if flt[c].nunique() > 2][:8]
        if len(use) < 3:
            return
        cm = flt[use].corr(method="spearman")
        f = px.imshow(cm, text_auto=".2f", zmin=-1, zmax=1, color_continuous_scale=[[0, "#4FA3C7"], [.5, PANEL], [1, BRASS]], title="How the numeric columns move together (Spearman)", aspect="auto")
        st.plotly_chart(_style(f, 300), width="stretch")
    a, b = st.columns(2)
    with a:
        safe("Seasonality", season)
    with b:
        safe("Relationships", corr)

    def unusual():
        if measure not in flt:
            return
        x = flt[measure].dropna()
        med = x.median()
        mad = (x - med).abs().median()
        if not mad:
            return
        z = (0.6745 * (flt[measure] - med) / mad)
        top = flt.loc[z.abs().sort_values(ascending=False).index[:10]].assign(**{"Robust z": z.round(1)})
        top = top[top["Robust z"].abs() > 3.5]
        st.markdown(f"#### Most unusual records by {measure}")
        if len(top):
            st.dataframe(top.head(10), width="stretch", hide_index=True)
            st.caption("Review indicators only. Check the source documents before treating any record as an error.")
        else:
            st.caption("No record is extremely unusual on this measure.")
    safe("Unusual records", unusual)

    def trust():
        cnt = df.attrs.get("wc_imputed_counts", {})
        st.markdown("#### How much of this data is estimated?")
        if not cnt:
            st.success("Every figure on this page comes from original values. Nothing was estimated.")
            return
        s = pd.Series(cnt).sort_values()
        pct = (s / len(df) * 100).round(1)
        f = go.Figure(go.Bar(x=pct.values, y=pct.index, orientation="h", marker_color="#E0A84A", text=[f"{v}%" for v in pct.values], textposition="outside"))
        f.update_layout(title="Share of each column that was estimated", xaxis_title=None, yaxis_title=None)
        st.plotly_chart(_style(f, 80 + 28 * len(s)), width="stretch")
    safe("Estimated share", trust)
    if insights:
        st.markdown("#### What the data says")
        for s_ in list(insights)[:4]:
            st.markdown(f'<div class="wc-note">{s_}</div>', unsafe_allow_html=True)