"""Two-way bank-versus-ledger reconciliation.

This is the control a spreadsheet cannot enforce: every ledger line is paired with a
bank movement (or its absence is proven), the value bridge is forced to foot to zero,
and anything that cannot be explained is escalated instead of quietly rounded away.
"""

import itertools
import re

import numpy as np
import pandas as pd
import streamlit as st

from core import intelligence as intel
from core.data import fingerprint

DATE_TOKENS = ("transaction date", "value date", "txn date", "booking date", "date", "time")
DESC_TOKENS = ("description", "narrative", "particular", "detail", "remark", "memo", "comment")
REF_TOKENS = ("ref", "receipt", "invoice", "cheque", "slip", "voucher", "code")
IN_TOKENS = ("deposit", "credit", "pay in", "payin", "inflow", "amount in", "receipt", "cr", "in")
OUT_TOKENS = ("withdrawal", "debit", "payment made", "outflow", "amount out", "cheque issued", "dr", "out")
BALANCE_TOKENS = ("balance", "b/f", "c/f")

MATCH_EXACT = "Exact match"
MATCH_TIMING = "Timing difference"
MATCH_VARIANCE = "Value variance"
MATCH_REFERENCE = "Identified by reference"
MATCH_BUNDLE = "Bundled settlement"
MATCH_BUNDLE_OUT = "Instalments received"
MATCH_DUPLICATE = "Duplicate bank item"

FEE_WORDS = ("charge", "fee", "commission", "duty", "levy", "stamp", "interest", "reversal", "vat")

STOP_WORDS = frozenset(
    {"the", "and", "for", "pay", "payment", "bank", "transfer", "rtgs", "mpesa", "txn", "transaction",
     "deposit", "withdrawal", "debit", "credit", "amount", "ref", "reference", "narration", "account",
     "internal", "system", "auto", "reversal", "charges"}
)


def _hit(name: str, token: str) -> bool:
    """Word-boundary aware column-name match so 'Cr' cannot match 'Credential'."""
    if len(token) <= 3:
        return re.search(rf"(?<![a-z]){re.escape(token)}(?![a-z])", name) is not None
    return token in name


def _to_money(s: pd.Series) -> pd.Series:
    """Coerce bank-export money columns: currency symbols, thousand separators,
    (parenthesised) and trailing-minus negatives. Cells that still contain a
    letter after the currency word is removed are document references, not money."""
    out = pd.to_numeric(s, errors="coerce").astype(float)
    if out.notna().mean() >= 0.7 or s.notna().sum() == 0:
        return out
    txt = s.astype("string").fillna("").str.strip()
    txt = txt.str.replace(r"(?i)\b(kes|ksh|shilling|shillings|ugx|tz|usd|ez|sh)\b\.?", "", regex=True).str.strip()
    is_number = (~txt.str.contains(r"[a-z]", regex=True) & txt.str.contains(r"\d", regex=True)).fillna(False)
    body = txt.str.replace(r"[^\d.,()\-+]", "", regex=True)
    comma_decimal = int((is_number & body.str.contains(",", regex=False) & ~body.str.contains(".", regex=False)).sum()) > int(
        (is_number & body.str.contains(".", regex=False)).sum()
    )
    if comma_decimal:
        body = body.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    else:
        body = body.str.replace(",", "", regex=False)
    neg = (
        body.str.contains(r"^\s*\((.*)\)\s*$", regex=True, na=False)
        | body.str.contains(r"-\s*$", regex=True, na=False)
        | body.str.contains(r"^-\s*", regex=True, na=False)
    )
    val = pd.to_numeric(body.str.replace(r"[()\-\+,]", "", regex=True), errors="coerce")
    val = val.where(is_number, np.nan).astype(float)
    return np.where(neg, -val.abs(), val).astype(float)


def _tokens(s: pd.Series) -> list[set[str]]:
    out = []
    for v in s.astype("string").fillna("").tolist():
        toks = {t for t in re.findall(r"[a-z0-9][a-z0-9\-/]*", str(v).lower()) if len(t) > 3 and t not in STOP_WORDS}
        out.append(toks)
    return out


def detect_statement_schema(df: pd.DataFrame) -> dict:
    """Find the date, money and text columns of an unattended bank export."""
    cols = list(df.columns)
    low = {c: str(c).lower().strip() for c in cols}

    date_col = None
    for c in cols:
        if any(_hit(low[c], t) for t in DATE_TOKENS) and len(df) and intel.parse_dates(df[c]).notna().mean() > 0.6:
            date_col = c
            break
    if date_col is None and len(df):
        for c in cols:
            if not pd.api.types.is_numeric_dtype(df[c]) and intel.parse_dates(df[c]).notna().mean() > 0.85:
                date_col = c
                break

    named = (*REF_TOKENS, *DESC_TOKENS, *DATE_TOKENS)
    candidates = [c for c in cols if c != date_col and not any(_hit(low[c], t) for t in BALANCE_TOKENS)]
    unlabelled = [c for c in candidates if not any(_hit(low[c], t) for t in named)]
    money: dict = {}
    for group in (unlabelled, [c for c in candidates if c not in unlabelled]):
        for c in group:
            v = _to_money(df[c])
            if len(df) and float(v.notna().mean()) > 0.6 and float(v.abs().sum()) > 0:
                money[c] = v
        if money:
            break

    in_col = next((c for c in money if any(_hit(low[c], t) for t in IN_TOKENS)), None)
    out_col = next((c for c in money if c != in_col and any(_hit(low[c], t) for t in OUT_TOKENS)), None)
    amount_col = None
    if in_col is None and out_col is None and money:
        amount_col = max(money, key=lambda c: intel._metric_score(str(c)))
        if amount_col is None or intel._metric_score(str(amount_col)) == 0:
            amount_col = list(money)[-1]

    desc_col = next((c for c in cols if c != date_col and any(_hit(low[c], t) for t in DESC_TOKENS)), None)
    if desc_col is None:
        texts = [c for c in cols if c not in money and c != date_col and not pd.api.types.is_numeric_dtype(df[c])]
        desc_col = texts[0] if texts else None
    ref_cols = [c for c in cols if c not in money and c != date_col and c != desc_col and any(_hit(low[c], t) for t in REF_TOKENS)]

    return {
        "date_col": date_col,
        "amount_col": amount_col,
        "in_col": in_col,
        "out_col": out_col,
        "desc_col": desc_col,
        "ref_cols": ref_cols,
        "money_cols": list(money),
        "money": money,
        "ready": date_col is not None and (amount_col is not None or in_col is not None or out_col is not None),
    }


@st.cache_data(ttl="1h", max_entries=8, show_spinner=False)
def load_statement(raw_bytes: bytes, filename: str, sheet: str | None = None) -> tuple[pd.DataFrame, dict, int]:
    """Read a statement, skipping past title/banner rows until the header is found."""
    from core.data import load_dataset

    for header in range(6):
        try:
            df = load_dataset_offset(raw_bytes, filename, sheet, header)
        except Exception:
            break
        if df.empty or len(df.columns) < 2:
            continue
        schema = detect_statement_schema(df)
        if schema["ready"]:
            return df, schema, header
    df = load_dataset_offset(raw_bytes, filename, sheet, 0)
    return df, detect_statement_schema(df), 0


def load_dataset_offset(raw_bytes: bytes, filename: str, sheet: str | None, header: int) -> pd.DataFrame:
    import io

    buf = io.BytesIO(raw_bytes)
    if filename.lower().endswith(".csv"):
        return pd.read_csv(buf, skiprows=header)
    return pd.read_excel(buf, sheet_name=sheet if sheet is not None else 0, skiprows=header)


def _text_of(df: pd.DataFrame, cols: list) -> pd.Series:
    parts = [df[c].astype("string").fillna("") for c in cols if c is not None and c in df.columns]
    if not parts:
        return pd.Series([""] * len(df), index=df.index)
    t = parts[0]
    for p in parts[1:]:
        t = t + " | " + p
    return t


def bank_frame(df: pd.DataFrame, schema: dict, header_row: int) -> pd.DataFrame:
    """Normalise a statement into (row, date, signed amount, abs amount, text)."""
    n = len(df)
    date = pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns]")
    if schema["date_col"] is not None:
        date = intel.parse_dates(df[schema["date_col"]])
    money = schema["money"]
    if schema["in_col"] is not None or schema["out_col"] is not None:
        ins = money.get(schema["in_col"], pd.Series(0.0, index=df.index)).fillna(0.0)
        outs = money.get(schema["out_col"], pd.Series(0.0, index=df.index)).fillna(0.0)
        amount = ins - outs
    elif schema["amount_col"] is not None:
        amount = money[schema["amount_col"]].astype(float)
    else:
        amount = pd.Series(np.nan, index=df.index, dtype=float)
    return pd.DataFrame(
        {
            "row": np.arange(n) + header_row + 2,
            "date": date.to_numpy(),
            "amount": amount.to_numpy(dtype=float),
            "text": _text_of(df, [schema["desc_col"], *schema["ref_cols"]]).to_numpy(),
        }
    )


def ledger_frame(clean_df: pd.DataFrame, schema: dict) -> pd.DataFrame:
    metric = schema["metric"]
    if metric is None or clean_df.empty:
        return pd.DataFrame(columns=["row", "date", "amount", "text"])
    date = (
        intel.parse_dates(clean_df[schema["dates"][0]])
        if schema["dates"]
        else pd.Series(pd.NaT, index=clean_df.index, dtype="datetime64[ns]")
    )
    text_cols = list(schema.get("keys", []))[:2]
    if schema.get("dims"):
        text_cols.append(schema["dims"][0])
    return pd.DataFrame(
        {
            "row": np.arange(len(clean_df)) + 2,
            "date": date.to_numpy(dtype="datetime64[ns]"),
            "amount": pd.to_numeric(clean_df[metric], errors="coerce").astype(float).to_numpy(),
            "text": _text_of(clean_df, text_cols).to_numpy(),
        }
    )


def _overlap(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def _doc_link(a: set[str], b: set[str]) -> bool:
    """A shared document-style token (invoice, cheque or receipt number) is the only
    evidence strong enough to accuse a payment of being a duplicate."""
    return any(len(t) >= 5 and any(c.isdigit() for c in t) for t in a & b)


def _days(x, y) -> float:
    if pd.isna(x) or pd.isna(y):
        return -1.0
    return abs((pd.Timestamp(x) - pd.Timestamp(y)).days)


def _ordinals(dates) -> np.ndarray:
    """Day numbers for vectorised gap maths; NaN where the date is missing."""
    s = pd.to_datetime(pd.Series(list(dates)), errors="coerce")
    return (s - pd.Timestamp("1970-01-01")).dt.days.astype("float64").to_numpy()


def reconcile(
    bank: pd.DataFrame,
    led: pd.DataFrame,
    *,
    exact_tol: float = 1.0,
    var_pct: float = 2.0,
    window: int = 5,
    timing_window: int = 45,
    bundle: bool = True,
) -> dict:
    """Pair every bank movement with ledger entries, escalating what cannot be paired."""
    b_amt = bank["amount"].to_numpy(dtype=float)
    l_amt = led["amount"].to_numpy(dtype=float)
    b_abs = np.abs(b_amt)
    l_abs = np.abs(l_amt)
    b_txt = _tokens(bank["text"])
    l_txt = _tokens(led["text"])
    dated_bank = bank["date"].tolist()
    dated_led = led["date"].tolist()
    b_row = bank["row"].to_numpy()
    l_row = led["row"].to_numpy()
    b_text_str = bank["text"].astype(str).tolist()
    l_text_str = led["text"].astype(str).tolist()
    b_dstr = _date_strs(dated_bank)
    l_dstr = _date_strs(dated_led)
    ledger_signed = bool(np.nan_to_num(l_amt, nan=0.0).min() < 0) if len(l_amt) else False

    used_b = np.zeros(len(bank), dtype=bool)
    used_l = np.zeros(len(led), dtype=bool)
    pairs: list[tuple[int, int, int, float, str]] = []  # (bank i, ledger j, tier, score, match type)
    direct: list[tuple[int, int, str, float]] = []

    order = np.argsort(l_abs)
    sorted_abs = l_abs[order]
    b_ord = _ordinals(dated_bank)
    l_ord = _ordinals(dated_led)
    TIER_TYPE = {1: MATCH_EXACT, 2: MATCH_TIMING, 3: MATCH_VARIANCE}

    # Vectorised pre-pass: the common case is a bank line with exactly one ledger line at
    # the same amount inside the date window. Resolving those without per-line numpy work
    # is what keeps a 25k-line statement from taking minutes.
    lo_all = np.searchsorted(sorted_abs, b_abs - exact_tol, side="left")
    hi_all = np.searchsorted(sorted_abs, b_abs + exact_tol, side="right")
    solo = np.nonzero((hi_all - lo_all == 1) & ~np.isnan(b_abs))[0]
    if solo.size:
        solo_j = order[lo_all[solo]]
        solo_gap = np.abs(b_ord[solo] - l_ord[solo_j])
        solo_ok = np.nonzero(solo_gap <= window)[0]
        for k in solo_ok:
            i, j = int(solo[k]), int(solo_j[k])
            if used_b[i] or used_l[j]:
                continue
            used_b[i] = used_l[j] = True
            direct.append((i, j, MATCH_EXACT, 90.0))

    def scan(i: int, band: float) -> None:
        """Collect candidate pairs for one bank line within an absolute amount band."""
        var_tol = max(exact_tol, band)
        hi = int(np.searchsorted(sorted_abs, b_abs[i] + var_tol, side="right"))
        lo = int(np.searchsorted(sorted_abs, b_abs[i] - var_tol, side="left"))
        js = order[lo:hi]
        if js.size == 0:
            return
        adiff = np.abs(l_abs[js] - b_abs[i])
        gap = np.abs(b_ord[i] - l_ord[js])
        if js.size > 300:
            trim = np.lexsort((np.where(np.isnan(gap), 1e9, gap), adiff))[:300]
            js, adiff, gap = js[trim], adiff[trim], gap[trim]
        known = ~np.isnan(gap)
        in_window = known & (gap <= window)
        in_timing = known & (gap <= timing_window)
        exact_amt = adiff <= exact_tol
        tier = np.full(js.size, 9, dtype=np.int8)
        tier[exact_amt & in_window] = 1
        tier[exact_amt & ~in_window & (in_timing | ~known)] = 2
        tier[~exact_amt & in_window] = 3
        keep = np.nonzero(tier != 9)[0]
        if keep.size == 0:
            return
        if keep.size == 1 and tier[keep[0]] == 1:
            j = int(js[keep[0]])
            if not used_l[j]:
                used_b[i] = used_l[j] = True
                direct.append((i, j, MATCH_EXACT, 90.0))
                return
        t = tier[keep]
        g = gap[keep]
        prov = 100.0 - t * 10.0
        prov -= np.where(np.isnan(g), 0.0, np.minimum(20.0, 20.0 * g / max(timing_window, 1)))
        prov -= np.minimum(15.0, 15.0 * adiff[keep] / max(var_tol, 1e-9))
        if ledger_signed:
            prov -= np.where(np.sign(b_amt[i]) != np.sign(l_amt[js[keep]]), 40.0, 0.0)
        for pos in np.argsort(-prov)[:12]:
            j = int(js[keep[pos]])
            if used_l[j]:
                continue
            score = float(prov[pos]) + 18.0 * _overlap(b_txt[i], l_txt[j])
            tier_of = int(tier[keep[pos]])
            pairs.append((i, j, tier_of, score, TIER_TYPE[tier_of]))

    # Tight pass first: it is cheap, and an exact tie should never lose to a near miss.
    for i in range(len(bank)):
        if not used_b[i] and not np.isnan(b_abs[i]):
            scan(i, exact_tol)

    # Settle the exact tier before widening. A bank line that already has an exact,
    # in-window twin would drop its wider candidates at assignment time anyway, so
    # scanning the 2% band for it buys nothing but time.
    matches = list(direct)
    exact_pairs = [p for p in pairs if p[2] == 1]
    exact_pairs.sort(key=lambda p: (-p[3], p[0]))
    for i, j, _tier, score, label in exact_pairs:
        if used_b[i] or used_l[j]:
            continue
        used_b[i] = used_l[j] = True
        matches.append((i, j, label, score))
    pairs = [p for p in pairs if p[2] != 1]

    # Only the leftovers need the wider variance band.
    for i in range(len(bank)):
        if not used_b[i] and not np.isnan(b_abs[i]) and var_pct > 0:
            scan(i, b_abs[i] * var_pct / 100.0)

    # Reference-led pass: same document or counterparty, different amount — the posting-error case.
    idx: dict[str, list[int]] = {}
    for j, toks in enumerate(l_txt):
        for t in toks:
            idx.setdefault(t, []).append(j)
    for i in range(len(bank)):
        if used_b[i] or np.isnan(b_amt[i]) or not b_txt[i]:
            continue
        cand: set[int] = set()
        for t in b_txt[i]:
            hits = idx.get(t, ())
            if len(hits) <= 60:
                cand.update(hits)
        cand = {j for j in cand if not used_l[j]}
        if not cand:
            continue
        jl = np.fromiter(cand, dtype=np.int64, count=len(cand))
        gaps = np.abs(b_ord[i] - l_ord[jl])
        near = jl[np.isnan(gaps) | (gaps <= timing_window)]
        if not len(near):
            continue
        scored = []
        for j in near:
            ov = _overlap(b_txt[i], l_txt[j])
            if not (ov >= 0.4 or _doc_link(b_txt[i], l_txt[j])):
                continue
            scored.append((52.0 + 30.0 * ov, int(j)))
        for score, j in sorted(scored, key=lambda t: -t[0])[:6]:
            pairs.append((i, j, 4, score, MATCH_REFERENCE))

    pairs.sort(key=lambda p: (p[2], -p[3], p[0]))
    for i, j, tier, score, label in pairs:
        if used_b[i] or used_l[j]:
            continue
        used_b[i] = used_l[j] = True
        matches.append((i, j, label, score))

    bundle_skipped = False
    if bundle:
        free_b, free_l = int((~used_b).sum()), int((~used_l).sum())
        if free_b > 4000 or free_l > 20_000:
            bundle_skipped = True
        else:
            matches.extend(
                _bundle_pass(bank, led, used_b, used_l, dated_bank, dated_led, max(window, timing_window), exact_tol)
            )

    dupes = _duplicate_pass(bank, used_b, matches, b_abs, exact_tol, dated_bank, b_txt, l_txt, window)

    rows = []
    for i, j, label, score in matches + dupes:
        gap = -1.0 if (np.isnan(b_ord[i]) or np.isnan(l_ord[j])) else abs(float(b_ord[i] - l_ord[j]))
        rows.append(
            {
                "Bank row": int(b_row[i]),
                "Bank date": b_dstr[i],
                "Bank description": b_text_str[i][:60],
                "Bank amount": float(b_amt[i]),
                "Ledger row": int(l_row[j]),
                "Ledger date": l_dstr[j],
                "Ledger amount": float(l_amt[j]),
                "Ledger reference": l_text_str[j][:60],
                "Value difference": round(float(b_amt[i] - l_amt[j]), 2),
                "Day gap": None if gap == -1 else int(gap),
                "Match type": label,
                "Confidence": int(max(1, min(100, round(score)))),
            }
        )
    matched = pd.DataFrame(
        rows,
        columns=[
            "Bank row", "Bank date", "Bank description", "Bank amount", "Ledger row", "Ledger date",
            "Ledger amount", "Ledger reference", "Value difference", "Day gap", "Match type", "Confidence",
        ],
    )
    bank_only_pos = np.nonzero(~used_b)[0]
    bank_only_out = pd.DataFrame(
        {
            "Bank row": b_row[bank_only_pos],
            "Date": [b_dstr[k] for k in bank_only_pos],
            "Description": [b_text_str[k][:70] for k in bank_only_pos],
            "Amount": b_amt[bank_only_pos],
        }
    )
    ledger_only_pos = np.nonzero(~used_l)[0]
    ledger_only_out = pd.DataFrame(
        {
            "Ledger row": l_row[ledger_only_pos],
            "Date": [l_dstr[k] for k in ledger_only_pos],
            "Reference": [l_text_str[k][:70] for k in ledger_only_pos],
            "Amount": l_amt[ledger_only_pos],
        }
    )

    stats = _bridge(bank, led, used_b, used_l, {i for i, _j, _l, _s in dupes}, matched)
    monthly = _monthly(bank, led, matches, dupes)
    findings = _findings(stats, matched, bank_only_out, ledger_only_out, dupes, window, bundle_skipped)
    return {
        "matched": matched,
        "bank_only": bank_only_out,
        "ledger_only": ledger_only_out,
        "bridge": stats["bridge"],
        "stats": stats,
        "monthly": monthly,
        "findings": findings,
        "duplicates": matched[matched["Match type"] == MATCH_DUPLICATE] if len(matched) else matched,
    }


def _bundle_pass(bank, led, used_b, used_l, dated_bank, dated_led, window, tol) -> list:
    """One bank line settling several invoices, or one invoice paid in instalments."""
    out = []
    l_abs = np.abs(led["amount"].to_numpy(dtype=float))
    b_abs = np.abs(bank["amount"].to_numpy(dtype=float))
    l_ord = _ordinals(dated_led)
    b_ord = _ordinals(dated_bank)
    ledger_days = _day_index(l_ord, used_l)
    bank_days = _day_index(b_ord, used_b)
    budget = 250_000
    if not ledger_days or not bank_days:
        return out

    for i in range(len(bank)):
        if used_b[i] or np.isnan(b_abs[i]) or np.isnan(b_ord[i]) or budget <= 0:
            continue
        target = b_abs[i]
        cand = _windowed(ledger_days, b_ord[i], window, target, l_abs, tol)
        if len(cand) < 2:
            continue
        cand = cand[:24]
        budget -= len(cand) ** 3
        hit = _find_subset(cand, l_abs, target, tol)
        if hit:
            for j in hit:
                used_l[j] = True
            used_b[i] = True
            out.extend((i, j, MATCH_BUNDLE, 60.0) for j in hit)

    bank_days = _day_index(b_ord, used_b)
    if not bank_days:
        return out
    for j in range(len(led)):
        if used_l[j] or np.isnan(l_abs[j]) or np.isnan(l_ord[j]) or budget <= 0:
            continue
        target = l_abs[j]
        cand = _windowed(bank_days, l_ord[j], window, target, b_abs, tol)
        if len(cand) < 2:
            continue
        cand = cand[:24]
        budget -= len(cand) ** 3
        hit = _find_subset(cand, b_abs, target, tol)
        if hit:
            for i in hit:
                used_b[i] = True
            used_l[j] = True
            out.extend((i, j, MATCH_BUNDLE_OUT, 58.0) for i in hit)
    return out


def _day_index(ordinals: np.ndarray, used: np.ndarray) -> dict:
    days: dict = {}
    for k, d in enumerate(ordinals):
        if used[k] or np.isnan(d):
            continue
        days.setdefault(int(d), []).append(k)
    return days


def _windowed(days: dict, centre: float, window: int, target: float, values: np.ndarray, tol: float) -> list[int]:
    cand = []
    for d in range(int(centre) - window, int(centre) + window + 1):
        for k in days.get(d, ()):
            if values[k] < target - tol:
                cand.append(k)
    cand.sort(key=lambda k: -values[k])
    return cand


def _find_subset(cand, values, target, tol) -> list[int] | None:
    arr = np.array([values[c] for c in cand], dtype=float)
    for size in (2, 3):
        if len(cand) < size:
            return None
        for combo in itertools.combinations(range(len(cand)), size):
            if abs(arr[list(combo)].sum() - target) <= tol:
                return [cand[k] for k in combo]
    return None


def _duplicate_pass(bank, used_b, matches, b_abs, tol, dated_bank, b_txt, l_txt, window) -> list:
    """A second bank item that ties to an already-settled ledger line — double payment.

    Only claimed when a document number or an identical narration backs it up, so
    recurring payments of the same size to the same party are not mislabelled."""
    out = []
    buckets: dict[int, list] = {}
    for (bi, lj, label, _s) in matches:
        if np.isnan(b_abs[bi]):
            continue
        buckets.setdefault(int(round(float(b_abs[bi]))), []).append((bi, lj))
    span = min(50, max(1, int(np.ceil(tol))))
    b_ord = _ordinals(dated_bank)
    for i in range(len(bank)):
        if used_b[i] or np.isnan(b_abs[i]):
            continue
        base = int(round(float(b_abs[i])))
        hit = None
        for k in range(base - span, base + span + 1):
            for (bi, lj) in buckets.get(k, ()):
                if abs(b_abs[bi] - b_abs[i]) > tol:
                    continue
                gap = -1.0 if np.isnan(b_ord[i]) or np.isnan(b_ord[bi]) else abs(b_ord[i] - b_ord[bi])
                if gap != -1 and gap > window:
                    continue
                if _doc_link(b_txt[i], l_txt[lj]) or (b_txt[i] and b_txt[i] == b_txt[bi]):
                    hit = (bi, lj)
                    break
            if hit:
                break
        if hit:
            used_b[i] = True
            out.append((i, hit[1], MATCH_DUPLICATE, 55.0))
    return out


def _date_strs(dates) -> list[str]:
    s = pd.to_datetime(pd.Series(list(dates)), errors="coerce")
    return s.dt.strftime("%Y-%m-%d").fillna("").tolist()


def _fmt_date(d) -> str:
    return "" if pd.isna(d) else pd.Timestamp(d).strftime("%Y-%m-%d")


def _bridge(bank, led, used_b, used_l, dup_rows, matched) -> dict:
    """The value bridge, forced to foot. A non-zero residual means the pairing is incomplete.

    Totals come from the used-masks rather than the match table, because a bundled
    settlement legitimately shows one bank line against several ledger lines.
    """
    b_amt = np.abs(bank["amount"].to_numpy(dtype=float))
    l_amt = np.abs(led["amount"].to_numpy(dtype=float))
    dup_mask = np.zeros(len(bank), dtype=bool)
    dup_mask[sorted(dup_rows)] = True

    ledger_total = float(np.nansum(l_amt))
    bank_total = float(np.nansum(b_amt))
    paired_ledger = float(np.nansum(l_amt[used_l]))
    paired_bank = float(np.nansum(np.where(used_b & ~dup_mask, b_amt, 0.0)))
    duplicate_total = float(np.nansum(np.where(dup_mask, b_amt, 0.0)))
    bank_only_total = float(np.nansum(np.where(~used_b & ~dup_mask, b_amt, 0.0)))
    ledger_only_total = float(np.nansum(l_amt[~used_l]))
    variance = paired_bank - paired_ledger
    residual = bank_total - (ledger_total - ledger_only_total + bank_only_total + duplicate_total + variance)

    n_matched = int(used_b.sum()) - len(dup_rows)
    return {
        "ledger_lines": int(len(led)),
        "bank_lines": int(len(bank)),
        "matched_bank": n_matched,
        "matched_ledger": int(used_l.sum()),
        "match_rate": round(100.0 * n_matched / max(len(bank), 1), 1),
        "ledger_only_lines": int((~used_l).sum()),
        "bank_only_lines": int((~used_b & ~dup_mask).sum()),
        "duplicate_lines": int(len(dup_rows)),
        "ledger_total": ledger_total,
        "bank_total": bank_total,
        "paired_ledger_total": paired_ledger,
        "paired_bank_total": paired_bank,
        "bank_only_total": bank_only_total,
        "ledger_only_total": ledger_only_total,
        "duplicate_total": duplicate_total,
        "variance_total": variance,
        "residual": residual,
        "foots": abs(residual) <= 0.05,
        "exceptions": int((~used_l).sum() + (~used_b & ~dup_mask).sum() + len(dup_rows)),
        "bridge": [
            ("Gross value booked in the ledger", ledger_total),
            ("Less: ledger value never seen on the bank", -ledger_only_total),
            ("Add: bank movements with no ledger entry", bank_only_total),
            ("Add: duplicate bank items against settled lines", duplicate_total),
            ("Add/(less): value difference on paired lines", variance),
            ("Gross value moved through the bank", bank_total),
        ],
    }


def _monthly(bank, led, matches, dupes) -> pd.DataFrame:
    """Month-by-month tie-out so timing backlogs are visible instead of averaged away."""
    b = bank.copy()
    b["m"] = pd.to_datetime(b["date"], errors="coerce").dt.to_period("M").astype(str)
    l = led.copy()
    l["m"] = pd.to_datetime(l["date"], errors="coerce").dt.to_period("M").astype(str)
    matched_rows = sorted({i for i, _j, _l, _s in matches} | {i for i, _j, _l, _s in dupes})
    paired_bank = b.iloc[matched_rows] if matched_rows else b.iloc[[]]

    lg = l.groupby("m")["amount"].agg(lines="count", value=lambda s: np.nansum(np.abs(s)))
    bg = b.groupby("m")["amount"].agg(lines="count", value=lambda s: np.nansum(np.abs(s)))
    pg = paired_bank.groupby("m")["amount"].agg(lambda s: np.nansum(np.abs(s)))

    months = sorted(m for m in (set(lg.index) | set(bg.index)) if m and m != "NaT")
    out = pd.DataFrame(index=months)
    out["Ledger lines"] = lg["lines"].reindex(out.index).fillna(0).astype(int)
    out["Ledger value"] = lg["value"].reindex(out.index).fillna(0.0).round(2)
    out["Bank lines"] = bg["lines"].reindex(out.index).fillna(0).astype(int)
    out["Bank value"] = bg["value"].reindex(out.index).fillna(0.0).round(2)
    out["Value paired"] = pg.reindex(out.index).fillna(0.0).round(2) if len(pg) else 0.0
    out["Bank − ledger"] = (out["Bank value"] - out["Ledger value"]).round(2)
    out["Tie-up %"] = (100.0 * out["Value paired"] / out["Bank value"].replace(0, np.nan)).fillna(0.0).round(1)
    out.index.name = "Month"
    return out.reset_index()


def _findings(stats, matched, bank_only, ledger_only, dupes, window, bundle_skipped=False) -> list[str]:
    f = []
    if stats["bank_lines"] == 0:
        return ["The statement contains no readable transactions."]
    f.append(
        f"{stats['match_rate']:.1f}% of bank lines ({stats['matched_bank']:,} of {stats['bank_lines']:,}) were tied "
        f"to ledger entries; {stats['bank_only_lines']:,} bank movement(s) and {stats['ledger_only_lines']:,} "
        f"ledger entry(s) remain unreconciled."
    )
    if stats["bank_only_lines"]:
        top = bank_only.reindex(bank_only["Amount"].abs().sort_values(ascending=False).index).head(3)
        names = ", ".join(f"{r['Description'][:34]} ({r['Amount']:,.0f})" for _i, r in top.iterrows())
        fee_lines = bank_only[bank_only["Description"].str.lower().str.contains("|".join(FEE_WORDS), na=False)]
        why = (
            f" {len(fee_lines)} of them read as bank charges or statutory deductions, which belong in the ledger as expenses, "
            f"not as differences."
            if len(fee_lines)
            else ""
        )
        f.append(
            f"KES {stats['bank_only_total']:,.0f} moved through the bank with no ledger entry — largest items: {names}.{why}"
        )
    if stats["ledger_only_lines"]:
        f.append(
            f"KES {stats['ledger_only_total']:,.0f} is booked in the ledger but never reached the bank. Until these "
            "entries are either receipted or written off they are unrecovered value, and a persistent pile is the "
            "classic falsified-revenue pattern."
        )
    if dupes:
        amt = float(np.nansum(np.abs(matched.loc[matched["Match type"] == MATCH_DUPLICATE, "Bank amount"])))
        f.append(
            f"⚠ {len(dupes)} bank item(s) totalling KES {amt:,.0f} repeat an amount, date window and counterparty already "
            "settled against a ledger line. These are candidate duplicate payments and should be recovered or reversed."
        )
    var = matched[matched["Match type"] == MATCH_VARIANCE] if len(matched) else matched
    if len(var):
        worst = var.reindex(var["Value difference"].abs().sort_values(ascending=False).index).iloc[0]
        f.append(
            f"{len(var)} pair(s) match on date and counterparty but not on amount. The largest break is "
            f"KES {worst['Value difference']:,.2f} between bank row {int(worst['Bank row'])} and ledger row {int(worst['Ledger row'])} — "
            "post the difference, do not plug it."
        )
    bundles = matched[matched["Match type"].isin([MATCH_BUNDLE, MATCH_BUNDLE_OUT])] if len(matched) else matched
    if len(bundles):
        f.append(
            f"{len(bundles)} ledger line(s) settled in bundles (a single bank credit clearing several invoices, or an "
            "invoice received in instalments). Bundle the allocation back to the document numbers before month-end."
        )
    elif bundle_skipped:
        f.append(
            "Bundled-settlement search was skipped: too many items remain unmatched for a subset search to stay "
            "interactive. Reconcile a shorter period, or clear the obvious one-sided items first."
        )
    timing = matched[matched["Match type"] == MATCH_TIMING] if len(matched) else matched
    if len(timing):
        med = float(pd.to_numeric(timing["Day gap"], errors="coerce").median() or 0.0)
        f.append(
            f"{len(timing)} pair(s) cleared outside the {window}-day window (median gap {med:.0f} days) — genuine timing, "
            "but a long tail of stale items usually means deposits in transit at period end."
        )
    refd = matched[matched["Match type"] == MATCH_REFERENCE] if len(matched) else matched
    if len(refd):
        f.append(
            f"{len(refd)} pair(s) were identified by document reference or counterparty only, with values that do not agree. "
            "These are the postings most likely to be keying errors."
        )
    f.append(
        "Value bridge "
        + ("foots exactly — every shilling of ledger value is either paired, proven absent, or classified."
           if stats["foots"]
           else f"does NOT foot (residual KES {stats['residual']:,.2f}) — the pairing is incomplete and the result must not be signed.")
    )
    return f


@st.cache_data(ttl="1h", max_entries=4, show_spinner="Reconciling the ledger against the bank statement…")
def run(
    stmt_bytes: bytes,
    stmt_name: str,
    stmt_sheet: str | None,
    raw_bytes: bytes,
    ledger_name: str,
    opts: dict,
    ledger_sheet: str | None,
    exact_tol: float,
    var_pct: float,
    window: int,
    timing_window: int,
    bundle: bool,
    overrides: dict | None = None,
) -> dict:
    from core.state import DEFAULT_OPTS, analyse

    bank_df, bank_schema, header_row = load_statement(stmt_bytes, stmt_name, stmt_sheet)
    bank_schema = apply_overrides(bank_df, bank_schema, overrides or {})
    parts = analyse(raw_bytes, ledger_name, {**DEFAULT_OPTS, **opts}, ledger_sheet)
    led = ledger_frame(parts["clean_df"], parts["schema"])
    bank = bank_frame(bank_df, bank_schema, header_row)
    bank = bank[bank["amount"].notna()]
    result = reconcile(
        bank,
        led,
        exact_tol=exact_tol,
        var_pct=var_pct,
        window=window,
        timing_window=timing_window,
        bundle=bundle,
    )
    result["stmt_schema"] = {k: v for k, v in bank_schema.items() if k != "money"}
    result["stmt_name"] = stmt_name
    result["stmt_sheet"] = stmt_sheet
    result["stmt_hash"] = fingerprint(stmt_bytes)
    result["header_row"] = header_row
    result["bank_raw"] = bank_df
    return result


def apply_overrides(df: pd.DataFrame, schema: dict, overrides: dict) -> dict:
    """Let the user correct an autodetected column — a silent mis-read is worse than no read."""
    out = dict(schema)
    for key in ("date_col", "amount_col", "in_col", "out_col", "desc_col"):
        col = overrides.get(key)
        if col is not None and col in df.columns:
            out[key] = col
    refs = overrides.get("ref_cols")
    if refs is not None:
        out["ref_cols"] = [c for c in refs if c in df.columns]
    for key in ("in_col", "out_col", "amount_col"):
        if out.get(key) is not None:
            col = out[key]
            if col not in out["money"]:
                out["money"] = {**out["money"], col: _to_money(df[col])}
    out["ready"] = out["date_col"] is not None and (
        out["amount_col"] is not None or out["in_col"] is not None or out["out_col"] is not None
    )
    return out
