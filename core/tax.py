"""Kenya statutory exception testing — the tax health check engine.

Three rules govern everything here.

1. Rates are *configuration*, never assertions of law. `DEFAULT_SCHEDULE` is a dated,
   user-editable table; every figure this module produces is only as correct as that table,
   and the page says so. Nothing in here is legal advice.
2. A derived number is always labelled derived. Where the ledger has no declared VAT or WHT
   column, the engine reports what the tax *would* be and stamps `basis="derived"` on it, so a
   computed estimate can never be read as a figure the client actually filed with KRA.
3. Every check returns a table of exceptions plus a summary, sorted by materiality, because a
   tax health check is sold on "here is what KRA would find first".
"""

import re

import numpy as np
import pandas as pd

# --- configured schedule ---------------------------------------------------------------
# (tax, head, rate_pct, effective_from, effective_to, note)
DEFAULT_SCHEDULE = [
    ("VAT", "Standard rated", 16.0, "2022-07-01", None, "Kenya standard VAT rate for periods on or after 1 July 2022."),
    ("VAT", "Standard rated", 14.0, None, "2022-06-30", "Prior standard rate; applies to invoices raised before 1 July 2022."),
    ("VAT", "Zero rated", 0.0, None, None, "Exports and the scheduled zero-rated goods; VATable at 0%, still a VATable supply."),
    ("VAT", "Exempt", 0.0, None, None, "Exempt supplies; input VAT attaching to these is not deductible."),
    ("WHT", "Professional & consultancy fees", 5.0, None, None, "Resident payee. Verify the rate for non-residents and the DTA position."),
    ("WHT", "Management & director's fees", 8.0, None, None, "Verify against the schedule in force for the year of payment."),
    ("WHT", "Rent", 8.0, None, None, "Commercial rent to a resident corporate lessor. Individual lessors differ."),
    ("WHT", "Other services", 5.0, None, None, "Default head where the narration indicates a service but no named head applies."),
    ("Penalty", "Late filing", 5.0, None, None, "Percentage of the tax understated or late, with a minimum fixed amount below."),
    ("Penalty", "Late filing minimum", 0.0, None, None, "Set this to the fixed KES floor you apply per return period."),
    ("Penalty", "Late payment", 10.0, None, None, "Percentage of unpaid tax."),
    ("Interest", "Monthly interest", 1.0, None, None, "Per cent per month on unpaid tax, applied to whole months outstanding."),
]

SCHEDULE_COLUMNS = ["Tax", "Head", "Rate %", "From", "To", "Note"]

# Keyword → schedule head, used to classify a service expense from its narration. Word boundaries are
# load-bearing: without them "maintenance" reads as a tenant and every repair bill becomes rent.
WHT_HEADS = (
    ("Professional & consultancy fees", r"\bconsult\w*|\bprofessional\b|\blegal\b|\badvoca\w*|\baudit\w*|tax service|\badvisory\b|agency fee"),
    ("Management & director's fees", r"\bmanage\w*|\bdirector\w*|\bboard fee|\bretainer"),
    ("Rent", r"\brent\w*|\blease\w*|\btenant\w*"),
    ("Other services", r"\bservice\w*|\bmaintenance\b|\brepair\w*|\bcleaning\b|\bsecurity\b|\btraining\b|\blicen[cs]e\b|\bfee\b|\bfees\b"),
)

# The shape KRA issues: a leading letter, eight or nine digits, then a check character. The digit
# count is left loose because both lengths are live in the register — the check digit itself is not
# recomputed here, so a well-formed PIN only earns the right to be looked up.
PIN_SHAPE = r"^[A-Z][0-9]{8,9}[A-Z]$"

_VAT_HINT = re.compile(r"\bvat\b|\btax\b|\bitax\b", re.I)
_NET_HINT = re.compile(r"\bnet\b|excl|before tax|base amount", re.I)
_GROSS_HINT = re.compile(r"\bgross\b|incl|total|amount|value|charge|paid", re.I)
_CODE_HINT = re.compile(r"tax\s*code|vat\s*(code|type|category)|supply|classification|exempt|zer|rate\s*type", re.I)
_WHT_HINT = re.compile(r"\bwht\b|withhold", re.I)
_PAYEE_HINT = re.compile(r"customer|client|supplier|vendor|party|payee|account name|narration|description|particulars", re.I)
_PIN_HINT = re.compile(r"\bpin\b|\bkra\b|taxpayer|tax\s*payer", re.I)
_DOC_HINT = re.compile(r"invoice|receipt|voucher|document|\bno\b|number|ref|bill", re.I)
_EXPENSE_HINT = re.compile(r"expense|purchase|cost|payment out|debit|supplier|vendor|billed to us", re.I)
_INCOME_HINT = re.compile(r"income|sale|revenue|receipt|credit|customer|invoice to", re.I)
_TYPE_HINT = re.compile(r"\btype\b|class|direction|\bflow\b|category", re.I)


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def _text(df: pd.DataFrame, col) -> pd.Series:
    """Column as text with blanks for the holes — astype(str) would write "nan" into a name field."""
    return df[col].fillna("").astype(str)


def _dates(df: pd.DataFrame, col) -> pd.Series:
    """One parsed date column, ISO-aware.

    Mixed formats are the norm in bank and ERP exports, so an unparseable column must not stop a tax
    check. dayfirst=True is applied only to what is demonstrably not ISO: handed an ISO string it reads
    the month as a day, which silently moves a line across a rate-change boundary.
    """
    if not col:
        return pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns]")
    raw = df[col]
    if pd.api.types.is_datetime64_any_dtype(raw):
        return raw
    s = _text(df, col).str.strip().str.slice(0, 10)
    out = pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns]")
    iso = s.str.match(r"^\d{4}[-/.]\d{1,2}[-/.]\d{1,2}", na=False)
    for mask, dayfirst in ((iso, False), ((~iso) & s.ne(""), True)):
        if not mask.any():
            continue
        try:
            out[mask] = pd.to_datetime(s[mask], errors="coerce", dayfirst=dayfirst, format="mixed")
        except (TypeError, ValueError):
            out[mask] = pd.to_datetime(s[mask], errors="coerce", dayfirst=dayfirst)
    return out


def _is_placeholder(pin) -> bool:
    """A PIN whose digit run is a single repeated character — a typed-in filler, not a registration."""
    digits = re.sub(r"[^0-9]", "", str(pin or ""))
    return bool(digits) and len(set(digits)) == 1


def detect_columns(df: pd.DataFrame) -> dict:
    """Best-effort column map. Reported to the page so a wrong guess is visible, never silent."""
    names = list(df.columns)
    lower = {c: str(c).lower() for c in names}

    def hits(hint, exclude=()):
        return [c for c in names if hint.search(lower[c]) and c not in exclude]

    def pick(hint, exclude=()):
        found = hits(hint, exclude)
        return found[0] if found else None

    # A "Tax Code"/"VAT category" column describes the supply; it is not an amount of tax.
    code = pick(_CODE_HINT)
    vat = pick(_VAT_HINT, exclude={code})
    wht = pick(_WHT_HINT, exclude={vat})
    net = pick(_NET_HINT, exclude={vat, wht, code})
    gross = pick(_GROSS_HINT, exclude={vat, wht, net, code})
    pin = pick(_PIN_HINT, exclude={vat})
    # A payee is a name. "Payee KRA PIN" carries the word payee but holds an identifier, and feeding it
    # into narration matching turns digit runs into fake expense heads.
    payees = [c for c in hits(_PAYEE_HINT) if c != pin]
    return {
        "date": next((c for c in names if pd.api.types.is_datetime64_any_dtype(df[c])), None) or pick(
            re.compile(r"date|time|period")),
        "vat": vat,
        "wht": wht,
        "net": net,
        "gross": gross,
        "code": code,
        "pin": pin,
        "doc": pick(_DOC_HINT),
        "payees": (payees or [None])[0],
        "payee_candidates": payees,
    }


def schedule_frame(rows=DEFAULT_SCHEDULE) -> pd.DataFrame:
    return pd.DataFrame([list(r) for r in rows], columns=SCHEDULE_COLUMNS)


def _bound(v) -> str | None:
    """A schedule date bound as clean text, or None meaning "no boundary in that direction"."""
    if v is None:
        return None
    if isinstance(v, str):
        return v.strip()[:10] or None
    if pd.isna(v):
        return None
    return str(v).strip()[:10] or None


def schedule_from_editor(edited: pd.DataFrame) -> pd.DataFrame:
    """Normalise the page's rate table back into the engine's schedule.

    The editor is the user's, so it arrives with blank rows, text dates, and rates typed as strings.
    Nothing here second-guesses their values — it only makes them usable and drops rows that carry no tax name.
    """
    rows = []
    for _, r in edited.iterrows():
        name = str(r.get("Tax") or "").strip()
        if not name or name.lower() in ("nan", "none"):
            continue
        head = str(r.get("Head") or "").strip() or "Standard rated"
        rate = pd.to_numeric(pd.Series([r.get("Rate %")]), errors="coerce").iloc[0]
        rows.append([name, head, 0.0 if pd.isna(rate) else float(rate),
                     _bound(r.get("From")), _bound(r.get("To")), str(r.get("Note") or "").strip()[:160]])
    return pd.DataFrame(rows, columns=SCHEDULE_COLUMNS)


def _rate_on(day, sched: pd.DataFrame, tax: str, head: str = "Standard rated") -> float | None:
    """The rate that was in force on `day` for a tax/head, or None if the schedule says nothing."""
    rows = sched[(sched["Tax"] == tax) & (sched["Head"] == head)]
    ts = pd.Timestamp(day) if day is not None and not pd.isna(day) else None
    for _, r in rows.iterrows():
        lo, hi = r.get("From"), r.get("To")
        if ts is not None and pd.notna(lo) and str(lo) not in ("", "None") and ts < pd.Timestamp(str(lo)):
            continue
        if ts is not None and pd.notna(hi) and str(hi) not in ("", "None") and ts > pd.Timestamp(str(hi)):
            continue
        return float(r["Rate %"])
    first = rows.head(1)
    return float(first["Rate %"].iloc[0]) if len(first) else None


def classify_head(text) -> str | None:
    s = str(text or "").lower()
    for head, pattern in WHT_HEADS:
        if re.search(pattern, s):
            return head
    return None


# --- 1. VAT ----------------------------------------------------------------------------------

def vat_checks(df: pd.DataFrame, cols: dict, sched: pd.DataFrame) -> dict:
    out = {"rows_tested": 0, "exceptions": 0, "basis": "none", "under_declared": 0.0, "over_declared": 0.0,
           "table": pd.DataFrame(columns=["Source row", "Date", "Payee", "Issue", "Net", "Rate %",
                                          "VAT declared", "VAT expected", "Difference"]),
           "note": "No VAT or tax column exists in this ledger, so declared VAT cannot be tested."}
    if not len(df):
        return out

    gross_col = cols["gross"] or cols["net"]
    has_vat = cols["vat"] is not None
    out["rows_tested"] = len(df)

    if not has_vat:
        # Derived: the only honest statement is what the tax would be if every line were standard-rated.
        d = _num(df[gross_col]) if gross_col else pd.Series(dtype="float64")
        if d.dropna().empty:
            return out
        dates = _dates(df, cols["date"])
        if not len(dates.dropna()):
            return out
        rate = _rate_on(dates.dropna().iloc[-1], sched, "VAT")
        if rate is None:
            return out
        net = d / (1 + rate / 100.0)
        out.update({
            "basis": "derived",
            "note": (
                f"This ledger carries no VAT column. Output VAT below is *derived* by treating every "
                f"{gross_col} figure as VAT-inclusive at {rate:.0f}% — an assumption about the whole file, not a "
                "figure anyone declared. Treat the total as an order-of-magnitude exposure test, and confirm against "
                "the returns before discussing it with a client."
            ),
            "gross_inclusive": float(d.sum(skipna=True)),
            "net_derived": float(net.sum(skipna=True)),
            "vat_derived": float((d - net).sum(skipna=True)),
        })
        return out

    g = _num(df[gross_col]) if gross_col else None
    n = _num(df[cols["net"]]) if cols["net"] else None
    v = _num(df[cols["vat"]])
    dates = _dates(df, cols["date"])
    codes = _text(df, cols["code"]) if cols["code"] else pd.Series([""] * len(df), index=df.index)
    payee = _text(df, cols["payees"]) if cols["payees"] else pd.Series([""] * len(df), index=df.index)

    day_arr = dates.to_numpy(dtype="datetime64[s]", na_value="NaT")
    net_arr = n.to_numpy(dtype="float64") if n is not None else np.full(len(df), np.nan)
    vat_arr = v.to_numpy(dtype="float64")
    gross_arr = g.to_numpy(dtype="float64") if g is not None else np.full(len(df), np.nan)
    code_vals = codes.to_numpy()
    payee_vals = payee.to_numpy()
    date_str = dates.dt.strftime("%Y-%m-%d").fillna("").to_numpy()
    rate_cache: dict = {}
    # Net + VAT can only be footed to gross when they are genuinely two different columns.
    footing = bool(cols["gross"]) and cols["gross"] != cols["net"]

    issues = []
    for i in range(len(df)):
        vv, nn, gg = vat_arr[i], net_arr[i], gross_arr[i]
        if np.isnan(vv) and np.isnan(nn) and np.isnan(gg):
            continue
        declared_vat = 0.0 if np.isnan(vv) else float(vv)
        if np.isnan(nn):
            if np.isnan(gg) or np.isnan(vv):
                continue
            nn = gg - vv
        base = float(nn)
        code = str(code_vals[i])
        zeroish = bool(re.search(r"zero|exempt|0%|export", code, re.I))
        head = "Zero rated" if zeroish else "Standard rated"
        key = (date_str[i], head)
        if key not in rate_cache:
            rate_cache[key] = _rate_on(None if date_str[i] == "" else pd.Timestamp(day_arr[i]), sched, "VAT", head)
        expected_rate = rate_cache[key]
        if expected_rate is None:
            continue

        expected_vat = round(base * expected_rate / 100.0, 2)
        implied = round(declared_vat / base * 100.0, 3) if base else np.nan

        if declared_vat < 0:
            issue = "Negative VAT entry — confirm it is a credit note, not an error"
        elif expected_rate > 0 and declared_vat == 0 and abs(base) > 0.005:
            issue = "No VAT charged on a standard-rated supply"
        elif expected_rate == 0 and declared_vat != 0:
            issue = "VAT charged on a zero-rated or exempt supply"
        elif not np.isnan(implied) and abs(implied - expected_rate) > 0.15:
            issue = f"Wrong VAT rate applied ({implied:.2f}% instead of {expected_rate:.0f}%)"
        elif abs(declared_vat - expected_vat) > 0.5:
            issue = "VAT does not agree with net x rate"
        elif footing and not np.isnan(gg) and abs((base + declared_vat) - gg) > 0.5:
            issue = "Net + VAT does not equal the gross total"
        else:
            continue

        diff = round(expected_vat - declared_vat, 2)
        issues.append({
            "Source row": i + 2, "Date": date_str[i], "Payee": str(payee_vals[i])[:34],
            "Issue": issue, "Net": round(base, 2), "Rate %": expected_rate,
            "VAT declared": round(declared_vat, 2), "VAT expected": expected_vat, "Difference": diff,
        })

    table = pd.DataFrame(issues, columns=list(out["table"].columns))
    if len(table):
        table = table.reindex(table["Difference"].abs().sort_values(ascending=False).index).reset_index(drop=True)
    out.update({
        "basis": "declared",
        "exceptions": len(table),
        "table": table,
        "under_declared": float(table["Difference"].clip(lower=0).sum()) if len(table) else 0.0,
        "over_declared": float(-table["Difference"].clip(upper=0).sum()) if len(table) else 0.0,
        "note": "Every line with a declared VAT amount was recomputed against the rate in force on its date.",
    })
    return out


def control_account(df: pd.DataFrame, cols: dict, sched: pd.DataFrame) -> dict:
    """Monthly output/input VAT position, and how the split was decided (it may be undecidable)."""
    empty = {"table": pd.DataFrame(), "basis": "none", "months": 0, "gap_months": [], "net_total": 0.0,
             "derived": False, "note": "Nothing to account."}
    if not len(df) or not cols["date"]:
        empty["note"] = "No date column, so VAT cannot be aged into return periods."
        return empty

    d = _dates(df, cols["date"])
    derived = cols["vat"] is None
    if derived:
        amount = _num(df[cols["gross"] or cols["net"]]) if (cols["gross"] or cols["net"]) else pd.Series(dtype="float64")
        # Treat the amount as VAT-inclusive and back the tax out at the rate in force that day.
        rate_by_month = {str(m): (_rate_on(m.to_timestamp(how="end"), sched, "VAT") or 0.0)
                         for m in d.dt.to_period("M").dropna().unique()}
        pct = d.dt.to_period("M").map(lambda m: rate_by_month.get(str(m), 0.0) if pd.notna(m) else 0.0) / 100.0
        money = (amount * pct / (1.0 + pct)).round(2)
    else:
        money = _num(df[cols["vat"]])
    if money.dropna().empty:
        return empty

    # Direction of each line: an explicit type column beats a sign convention beats a guess.
    basis = None
    for c in df.columns:
        if not _TYPE_HINT.search(str(c).lower()):
            continue
        guess = _text(df, c).str.contains(_EXPENSE_HINT, na=False)
        if guess.any() and guess.sum() < len(df):
            direction = np.where(guess, "Input", "Output")
            basis = f"column “{c}”"
            break
    if basis is None:
        base_money = _num(df[cols["gross"] or cols["net"]]) if (cols["gross"] or cols["net"]) else money
        if base_money.lt(0).any() and base_money.gt(0).any():
            direction = np.where(base_money < 0, "Input", "Output")
            basis = "the sign of the amount"
        elif cols["payees"] and _text(df, cols["payees"]).str.contains(_EXPENSE_HINT, na=False).any():
            mask = _text(df, cols["payees"]).str.contains(_EXPENSE_HINT, na=False)
            direction = np.where(mask, "Input", "Output")
            basis = f"a narration match on “{cols['payees']}”"
        else:
            direction = np.full(len(df), "Output", dtype=object)
            basis = "the assumption that every line is a taxable output supply (single-sided ledger)"

    frame = pd.DataFrame({"Month": d.dt.to_period("M"), "Side": direction, "VAT": money.values}).dropna(subset=["Month"])
    if frame.empty:
        return empty
    pivot = frame.pivot_table(index="Month", columns="Side", values="VAT", aggfunc="sum").fillna(0.0)
    for col in ("Output", "Input"):
        if col not in pivot.columns:
            pivot[col] = 0.0
    pivot["Input"] = pivot["Input"].abs()
    pivot["Net payable"] = pivot["Output"] - pivot["Input"]
    full = pd.period_range(pivot.index.min(), pivot.index.max(), freq="M")
    table = pivot.reset_index().rename_axis(None, axis=1)
    table["Month"] = table["Month"].astype(str)
    table = table.round(2)
    return {
        "table": table,
        "months": int(pivot.index.nunique()),
        "basis": basis,
        "derived": derived,
        "gap_months": [str(m) for m in full if m not in set(pivot.index)][:12],
        "net_total": float(pivot["Net payable"].sum()),
        "note": (
            ("No VAT column exists in this ledger, so the monthly figures below are derived by backing tax out of the "
             "amount at the configured rate — they are an exposure shape, not a control account anyone posted to. "
             if derived else
             "Output and input VAT were taken from the declared VAT column, so these are the client's own figures, "
             "restated by period. ")
            + f"Output and input were separated using {basis}. Where that rule is a guess rather than a column in "
              "the file, the net position is indicative only — the filed return, not this ledger, is the authority."
        ),
    }


# --- 2. Withholding tax -----------------------------------------------------------------------

def wht_checks(df: pd.DataFrame, cols: dict, sched: pd.DataFrame) -> dict:
    res = {"table": pd.DataFrame(), "register": pd.DataFrame(), "expense_lines": 0, "wht_heads": 0,
           "unwithheld": 0.0, "declared_total": 0.0, "basis": "none", "note": ""}
    base_col = cols["net"] or cols["gross"]
    if not len(df) or not base_col:
        res["note"] = "No amount column to test withholding against."
        return res

    narr = pd.Series("", index=df.index, dtype=object)
    text_cols = [c for c in dict.fromkeys([*cols["payee_candidates"], cols["doc"], cols["code"]]) if c]
    text_cols += [c for c in df.columns if c not in text_cols and _TYPE_HINT.search(str(c).lower())]
    for c in text_cols:
        narr = narr + " " + _text(df, c)
    heads = narr.map(classify_head)
    # An expense line is one the file itself says is a purchase, or one booked as a negative amount.
    expense = narr.str.contains(_EXPENSE_HINT, na=False)
    if cols["gross"]:
        expense = expense | (_num(df[cols["gross"]]) < 0)

    money = _num(df[base_col]).abs()
    cand = heads.notna() & expense & money.gt(0)
    res["expense_lines"] = int(expense.sum())
    res["wht_heads"] = int(cand.sum())

    dates = _dates(df, cols["date"])
    date_str = dates.dt.strftime("%Y-%m-%d").fillna("").to_numpy()
    declared = _num(df[cols["wht"]]).abs() if cols["wht"] else pd.Series(0.0, index=df.index)
    res["basis"] = "declared" if cols["wht"] else "absent"

    head_vals = heads.to_numpy()
    money_vals = money.to_numpy(dtype="float64")
    declared_vals = declared.to_numpy(dtype="float64")
    payee_vals = _text(df, cols["payees"]).to_numpy() if cols["payees"] else np.full(len(df), "", dtype=object)
    rate_cache: dict = {}

    rows = []
    for i in np.flatnonzero(cand.to_numpy()):
        head = head_vals[i]
        day = None if date_str[i] == "" else pd.Timestamp(date_str[i])
        key = (date_str[i], head)
        if key not in rate_cache:
            rate_cache[key] = _rate_on(day, sched, "WHT", head)
        rate = rate_cache[key]
        if not rate:
            continue
        expected = round(float(money_vals[i]) * rate / 100.0, 2)
        got = 0.0 if np.isnan(declared_vals[i]) else float(declared_vals[i])
        short = round(expected - got, 2)
        if abs(short) < 0.5:
            continue
        rows.append({
            "Source row": i + 2, "Date": date_str[i], "Payee": str(payee_vals[i])[:34],
            "Head": head, "Base": round(float(money_vals[i]), 2), "Rate %": rate,
            "WHT expected": expected, "WHT deducted": round(got, 2), "Short": short,
        })
    columns = ["Source row", "Date", "Payee", "Head", "Base", "Rate %", "WHT expected", "WHT deducted", "Short"]
    table = pd.DataFrame(rows, columns=columns)
    if len(table):
        table = table.reindex(table["Short"].abs().sort_values(ascending=False).index).reset_index(drop=True)
        res["unwithheld"] = float(table["Short"].clip(lower=0).sum())
    res["declared_total"] = float(declared.sum(skipna=True))
    res["table"] = table

    # Certificate register: the filing obligation exists whether or not anyone withheld.
    reg = table.loc[table["Short"] > 0, ["Date", "Payee", "Head", "Base", "Rate %", "WHT expected"]].copy()
    if len(reg) and cols["date"]:
        d = pd.to_datetime(reg["Date"], errors="coerce", format="mixed")
        reg["Due (20th of following month)"] = (d + pd.offsets.MonthEnd(1) + pd.Timedelta(days=19)).dt.strftime("%Y-%m-%d")
        reg["Certificate no."] = [f"WHT-{i + 1:04d}" for i in range(len(reg))]
    res["register"] = reg
    res["note"] = (
        "Withholding was tested on expense lines whose narration matches a service head. "
        + ("The ledger carries a withholding column, so shortfalls are declared-versus-expected. "
           if cols["wht"] else
           "The ledger carries no withholding column at all, which means either nobody withheld or the withholding "
           "lives in a separate file. The exposure below assumes nobody withheld and must be confirmed. ")
        + "An expense suffered without the required withholding may be disallowed as a deduction, so the real cost is "
          "the tax on the grossed-up amount as well as the withheld sum."
    )
    return res


# --- 3. Supplier identity ---------------------------------------------------------------------

def pin_checks(df: pd.DataFrame, cols: dict) -> dict:
    res = {"table": pd.DataFrame(), "populated": 0, "malformed": 0, "shared": 0, "placeholders": 0,
           "coverage": 0.0, "shared_table": pd.DataFrame(columns=["PIN", "Distinct payees", "Payees seen"]),
           "pin_per_payee": pd.DataFrame(columns=["Payee", "Distinct PINs"]), "note": ""}
    if not cols["pin"]:
        res["note"] = "No taxpayer PIN column in this ledger, so supplier identity cannot be tested."
        return res
    pin = _text(df, cols["pin"]).str.upper().str.replace(r"[^A-Z0-9]", "", regex=True)
    payee = _text(df, cols["payees"]).str.strip().str.upper() if cols["payees"] else pd.Series("", index=df.index, dtype=object)
    filled = pin != ""
    res["populated"] = int(filled.sum())

    bad = filled & ~pin.str.match(PIN_SHAPE, na=False)
    ph = filled & pin.map(_is_placeholder)
    res["malformed"] = int((bad & ~ph).sum())
    res["placeholders"] = int(ph.sum())

    body = pin[filled]
    dupes = body[body.duplicated(keep=False)] if len(body) else pd.Series(dtype=object)
    one_pin_many = (
        pd.DataFrame({"PIN": dupes, "Payee": payee[dupes.index]})
        .groupby("PIN", as_index=False, dropna=False)
        .agg(**{"Distinct payees": ("Payee", "nunique"),
                "Payees seen": ("Payee", lambda s: ", ".join(sorted(set(s))[:3]))})
    ) if len(dupes) else pd.DataFrame(columns=["PIN", "Distinct payees", "Payees seen"])
    one_pin_many = one_pin_many[one_pin_many["Distinct payees"] > 1].sort_values("Distinct payees", ascending=False)
    res["shared"] = len(one_pin_many)
    res["shared_table"] = one_pin_many.head(100)

    rows = []
    for i in np.flatnonzero((bad | ph).to_numpy()):
        rows.append({
            "Source row": i + 2, "PIN": pin.iloc[i],
            "Payee": payee.iloc[i][:34],
            "Issue": "Placeholder PIN" if ph.iloc[i] else "PIN is not in the expected shape",
        })
    table = pd.DataFrame(rows, columns=["Source row", "PIN", "Payee", "Issue"]).head(200)
    res["table"] = table
    res["pin_per_payee"] = (
        pd.DataFrame({"PIN": body, "Payee": payee[filled]})
        .groupby("Payee")["PIN"].nunique().sort_values(ascending=False).head(10).reset_index(name="Distinct PINs")
        if len(body) else pd.DataFrame(columns=["Payee", "Distinct PINs"])
    )
    res["coverage"] = round(res["populated"] / max(len(df), 1) * 100, 1)
    res["note"] = (
        "The PIN shape tested here is one capital letter, eight or nine digits and one check character, which is the "
        "format KRA issues — but this module cannot compute the check character, so a well-formed PIN is not proof of "
        "a registered taxpayer. Anything flagged needs a lookup against the KRA portal before it becomes a finding."
    )
    return res


# --- 4. Document sequence ---------------------------------------------------------------------

def sequence_checks(df: pd.DataFrame, cols: dict) -> dict:
    res = {"table": pd.DataFrame(), "groups": 0, "gaps": 0, "repeats": 0, "inversions": 0, "note": "",
           "coverage": None, "read_by": None}
    if not cols["doc"]:
        res["note"] = "No document or invoice number column, so sequence integrity cannot be tested."
        return res
    doc = _text(df, cols["doc"]).str.strip()
    dated = _dates(df, cols["date"])
    party = _text(df, cols["payees"]).str.strip() if cols["payees"] else pd.Series("All lines", index=df.index, dtype=object)

    def serial(s: str):
        m = re.search(r"(\d+)(?!.*\d)", s)
        return int(m.group(1)) if m else None

    def prefix(s: str):
        m = re.match(r"^[^0-9]*", s)
        return (m.group(0).strip("-/ ") or "DOC") if m else "DOC"

    frame = pd.DataFrame({
        "Party": party, "Doc": doc, "Serial": doc.map(serial), "Prefix": doc.map(prefix),
        "Date": dated.values, "Row": np.arange(2, len(df) + 2),
    }).dropna(subset=["Serial"])
    if frame.empty:
        res["note"] = "Document numbers carry no numeric component, so no sequence can be read."
        return res

    def gap_events(keys) -> int:
        n = 0
        for _, g in frame.groupby(keys, dropna=False):
            s = np.sort(g["Serial"].to_numpy(dtype="int64"))
            if len(s) > 1:
                n += int((np.diff(s) > 1).sum())
        return n

    # Read the numbering the way the file means it. One letter prefix normally carries one series, but when
    # several issuers each run their own numbers under the same prefix, grouping by prefix alone invents gaps.
    keys, by_party = ["Prefix"], False
    if party.nunique() > 1 and gap_events(["Party", "Prefix"]) < gap_events(["Prefix"]):
        keys, by_party = ["Party", "Prefix"], True
    res["read_by"] = "each party within each prefix" if by_party else "each document prefix as one series"

    rows = []
    groups = 0
    for name, g in frame.groupby(keys, dropna=False):
        groups += 1
        g = g.sort_values("Serial")
        who = str(g["Party"].iloc[0])[:30] if g["Party"].nunique() == 1 else f"{g['Party'].nunique()} parties"
        series = str(g["Prefix"].iloc[0])
        ser = g["Serial"].to_numpy(dtype="int64")
        missing = int((np.diff(ser) > 1).sum()) if len(ser) > 1 else 0
        dupes = int(pd.Series(ser).duplicated().sum())
        if missing:
            jumps = np.where(np.diff(ser) > 1)[0]
            for j in jumps[:12]:
                rows.append({
                    "Series": series, "Issuers": who, "Type": "Number gap",
                    "Detail": f"{ser[j]} → {ser[j + 1]} ({ser[j + 1] - ser[j] - 1} missing)",
                    "From row": int(g["Row"].iloc[j]), "Count": int(ser[j + 1] - ser[j] - 1),
                })
            res["gaps"] += missing
        if dupes:
            res["repeats"] += dupes
            first_dupe = int(g["Row"].iloc[int(pd.Series(ser).duplicated().values.argmax())])
            rows.append({"Series": series, "Issuers": who, "Type": "Repeated number",
                         "Detail": f"{dupes} use(s) of a number already issued", "From row": first_dupe, "Count": dupes})
        if cols["date"]:
            d = pd.to_datetime(g["Date"], errors="coerce").dropna()
            if len(d) > 2:
                vals = d.to_numpy(dtype="datetime64[ns]").astype("int64")
                steps = np.diff(vals)
                inv = int((steps < 0).sum())
                if inv:
                    res["inversions"] += inv
                    at = int(np.where(steps < 0)[0][0])
                    earlier = pd.Timestamp(vals[at + 1]).strftime("%Y-%m-%d")
                    later = pd.Timestamp(vals[at]).strftime("%Y-%m-%d")
                    rows.append({"Series": series, "Issuers": who, "Type": "Date out of sequence",
                                 "Detail": f"No. {ser[at + 1]} dated {earlier} sits before No. {ser[at]} dated {later} "
                                           f"({inv} such step(s) back) — the backdating signature",
                                 "From row": int(g["Row"].iloc[at]), "Count": inv})
    res["groups"] = groups
    table = pd.DataFrame(rows, columns=["Series", "Issuers", "Type", "Detail", "From row", "Count"])
    res["table"] = table.sort_values("Count", ascending=False, ignore_index=True)
    res["coverage"] = round(len(frame) / max(len(df), 1) * 100, 1)
    res["note"] = (
        f"Sequences were read as {res['read_by']}, because a company running two number series is not gapping and "
        "suppliers each number their own documents. A gap is not proof of anything on its own — cancelled documents, a "
        "number block reserved for a branch and a re-coded system all create them — but under e-TIMS every issued "
        "invoice must transmit, so a gap is a question that needs a document as the answer."
    )
    return res


# --- 5. Exposure ---------------------------------------------------------------------------------

def exposure(vat: dict, wht: dict, sched: pd.DataFrame, months_outstanding: float = 6.0) -> dict:
    """Tax at risk plus the configured penalty and interest assumptions. All three numbers are assumptions."""
    tax = max(vat.get("under_declared", 0.0) if vat.get("basis") == "declared" else 0.0, 0.0) + max(wht.get("unwithheld", 0.0), 0.0)
    filing_rate = _rate_on(None, sched, "Penalty", "Late filing") or 0.0
    filing_min = _rate_on(None, sched, "Penalty", "Late filing minimum") or 0.0
    pay_rate = _rate_on(None, sched, "Penalty", "Late payment") or 0.0
    interest = _rate_on(None, sched, "Interest", "Monthly interest") or 0.0
    if not tax:
        return {"tax": 0.0, "penalty": 0.0, "interest": 0.0, "total": 0.0, "months": months_outstanding}
    penalty = max(tax * filing_rate / 100.0, filing_min if filing_min else 0.0) + tax * pay_rate / 100.0
    charge = tax * interest / 100.0 * months_outstanding
    return {
        "tax": round(tax, 2), "penalty": round(penalty, 2), "interest": round(charge, 2),
        "total": round(tax + penalty + charge, 2), "months": months_outstanding,
        "rates": {"filing_pct": filing_rate, "filing_min": filing_min, "payment_pct": pay_rate, "interest_pm": interest},
    }


# --- orchestration ------------------------------------------------------------------------------

_SLOT_KEYS = ("date", "vat", "wht", "net", "gross", "code", "pin", "doc")


def run(df: pd.DataFrame, opts: dict | None = None) -> dict:
    """One pass of the tax health check. `opts` carries the column overrides and the rate schedule."""
    opts = opts or {}
    cols = detect_columns(df)
    # An override only counts if it names a column that is actually in this file — a picklist left over
    # from another upload must fall back to detection rather than silently blanking a test.
    for k in _SLOT_KEYS:
        v = opts.get(k)
        if isinstance(v, str) and v in df.columns:
            cols[k] = v
    payee = opts.get("payees")
    if isinstance(payee, str) and payee in df.columns:
        cols["payees"] = payee
    elif cols["payees"] not in cols["payee_candidates"]:
        cols["payees"] = (cols["payee_candidates"] or [None])[0]

    sched = opts.get("schedule")
    sched = schedule_frame() if sched is None else (sched if isinstance(sched, pd.DataFrame) else pd.DataFrame(sched, columns=SCHEDULE_COLUMNS))

    vat = vat_checks(df, cols, sched)
    wht = wht_checks(df, cols, sched)
    pins = pin_checks(df, cols)
    seq = sequence_checks(df, cols)
    control = control_account(df, cols, sched)
    exposure_ = exposure(vat, wht, sched, months_outstanding=float(opts.get("months", 6)))

    fdates = _dates(df, cols["date"])
    span = (str(fdates.min().date()), str(fdates.max().date())) if fdates.notna().any() else None
    rate_first = _rate_on(fdates.min() if span else None, sched, "VAT")
    rate_last = _rate_on(fdates.max() if span else None, sched, "VAT")
    raw_dates = _text(df, cols["date"]).str.strip() if cols["date"] else pd.Series("", index=df.index, dtype=object)
    unparsed = int((raw_dates.ne("") & fdates.isna()).sum())

    findings = []
    if vat["basis"] == "declared":
        if vat["exceptions"]:
            findings.append(
                f"{vat['exceptions']} VAT line exception(s): VAT understated by KES {vat['under_declared']:,.2f} and "
                f"overstated by KES {vat['over_declared']:,.2f} against the rate in force on each date."
            )
        else:
            findings.append(f"No VAT exceptions across {vat['rows_tested']:,} line(s) carrying declared VAT.")
    elif vat["basis"] == "derived":
        findings.append(
            f"No declared VAT column exists. If every line were a standard-rated taxable supply the ledger implies "
            f"KES {vat['vat_derived']:,.2f} of output VAT on a derived net of KES {vat['net_derived']:,.2f} — an "
            "assumption to be confirmed, not a filed figure."
        )
    else:
        findings.append("VAT could not be tested on this file — no amount column recognised.")

    if wht["wht_heads"]:
        findings.append(
            f"{wht['wht_heads']} service-expense line(s) attract withholding; {len(wht['table'])} fall short by "
            f"KES {wht['unwithheld']:,.2f}. {('The ledger shows no withholding column at all.' if wht['basis'] == 'absent' else 'Declared withholding was compared line by line.')}"
        )
    else:
        findings.append("No expense narration matched a withholding-tax service head, so withholding was not applicable on this reading.")

    if pins["table"] is not None and len(pins["table"]):
        findings.append(
            f"{len(pins['table'])} supplier PIN(s) fail the expected shape or look like placeholders "
            f"({pins['coverage']}% of lines carry a PIN). Verify each against the KRA register before it becomes a finding."
        )
    if pins["shared"]:
        findings.append(f"{pins['shared']} tax PIN(s) are used by more than one payee name — one of these is wrong.")

    if seq["gaps"]:
        findings.append(
            f"Document sequence: {seq['gaps']} gap(s) and {seq['repeats']} repeated number(s) across {seq['groups']} "
            f"series, with {seq['inversions']} date-order inversion(s)."
        )
    elif seq.get("coverage"):
        findings.append(f"Document sequences run unbroken across {seq['groups']} series ({seq['coverage']}% of lines numbered).")

    if control.get("gap_months"):
        findings.append(
            f"{len(control['gap_months'])} month(s) in the file's date span carry no VATable activity at all: "
            f"{', '.join(control['gap_months'][:6])}. A nil return is a filing event; silence in the ledger is not."
        )

    if span and rate_first != rate_last:
        findings.append(
            f"The rate schedule you configured moves inside this file's period: {rate_first:.0f}% at {span[0]} and "
            f"{rate_last:.0f}% by {span[1]}. Each line was tested against the rate on its own date, so any flat-rate "
            "assumption in the books will show up as exceptions at the boundary."
        )

    if unparsed > max(5, 0.05 * len(df)):
        findings.append(
            f"{unparsed} of {len(df):,} lines carry a value in {cols['date']} that will not parse as a date at all. "
            "Those lines were tested at the schedule's default rate rather than the rate on their own date, which is "
            "the weakest evidence on this page — fix the date column and re-run before quoting any figure derived "
            "from it."
        )

    return {
        "cols": cols, "schedule": sched, "vat": vat, "wht": wht, "pins": pins, "seq": seq,
        "control": control, "exposure": exposure_, "findings": tuple(findings), "rows": len(df),
        "span": span, "date_col": cols["date"], "rate_first": rate_first, "rate_last": rate_last,
        "unparsed_dates": unparsed,
    }
