"""Plain-English management commentary for every screen.

Two jobs. First, name the document each page produces, because most readers do
not know that a dashboard is a management cash-flow summary or that a
reconciliation is the proof of cash. Second, turn computed figures into
sentences a manager can act on.

Every number quoted here is re-derived from the frame or stats dict handed over
by the page, so an explainer can never state something the page did not compute.
"""

import pandas as pd

from core import theme

# What each screen is, how to read it, and which management report it becomes.
PAGES = {
    "dashboard": {
        "What this screen is":
            "The monthly management cash-flow summary — the pack a finance manager presents after close. "
            "It answers the three questions every review asks: how much money moved, whether it is moving the "
            "right way, and whether the figures are trustworthy enough to quote.",
        "How to read it":
            "The tiles at the top are the headlines; the charts below explain why they moved. Nothing is typed in "
            "by hand — every figure is computed from the ledger in the sidebar, so two readers always get the same answer.",
        "What it becomes":
            "Section 3 of the certified report (cash-flow dashboard, printed with the charts) and the source of the "
            "quality and record counts quoted on the cover.",
    },
    "findings": {
        "What this screen is":
            "The audit findings memo — the written opinion on the quality of the ledger, in the form a board, a lender "
            "or a tax authority expects to see.",
        "How to read it":
            "Start with the four quality tiles. They score the ledger on completeness, uniqueness, validity and "
            "consistency; the overall figure must clear 90% before an unqualified certificate can be issued. "
            "Then read the integrity checks: a failed check is not cosmetic, it is disclosed on the face of the report.",
        "What it becomes":
            "The executive summary, integrity table, findings and recommendations in the certified PDF — the pages "
            "a client actually reads after the fieldwork is done.",
    },
    "forensics": {
        "What this screen is":
            "The fraud-risk screening note. Two tests Excel cannot do: whether the ledger's numbers behave like "
            "genuine transaction data, and whether the same payment was made twice under different document numbers.",
        "How to read it":
            "These are screening tests, not proof. A clean result means no statistical smell of manipulation — not "
            "that no fraud exists. A flagged result means pull these specific documents and check them by hand.",
        "What it becomes":
            "Supports the integrity opinion. A non-conforming result should be disclosed as a scope limitation, and "
            "the flagged register becomes the sample list for detailed testing.",
    },
    "quarantine": {
        "What this screen is":
            "The exception review schedule — the working paper where every unusual row gets a named human decision "
            "instead of being quietly left in or quietly deleted.",
        "How to read it":
            "Each row states the rule that caught it. 'Awaiting review' means nobody has accepted responsibility for "
            "that row yet. Releasing a row is an audit decision and is recorded against this file's fingerprint.",
        "What it becomes":
            "The exception count in the certificate. Unreviewed exceptions are why reports get qualified.",
    },
    "pivot": {
        "What this screen is":
            "Ad-hoc management information — the slicing, filtering and cross-tabbing you would otherwise rebuild by "
            "hand in Excel, run on the cleaned ledger rather than the raw one.",
        "How to read it":
            "The pivot answers 'how much per what'. The profiler tells you whether a column is safe to group by: a "
            "column that is half empty or full of one value will produce a misleading pivot. Edits in the grid are "
            "session-only and never change the source file or its fingerprint.",
        "What it becomes":
            "Nothing automatically. This page is for analysis you quote in a management discussion; the report is "
            "built from the other screens.",
    },
    "reconcile": {
        "What this screen is":
            "The bank reconciliation statement — the proof of cash. It shows the books agree with the bank's own "
            "record of what actually happened to the money, item by item rather than in total.",
        "How to read it":
            "Anything paired is proved twice: once by your ledger, once by the bank. Anything left on one side is an "
            "exception somebody must explain. The value bridge at the bottom is the control — it must land on zero.",
        "What it becomes":
            "Section 4 of the certified PDF: the bridge, the month-by-month tie-out, the ten largest exceptions on "
            "each side and the matching criteria used.",
    },
    "tax": {
        "What this screen is":
            "The tax health check working paper — a re-performance of the client's own VAT and withholding figures at "
            "the rates on their own dates, before a KRA audit finds the differences. It is the domestic tax and "
            "compliance engagement in software form: tax health check across VAT and withholding, iTax mismatch "
            "cleanup, and an exposure estimate to argue from.",
        "How to read it":
            "Two things must be true before any number here means anything. First, the rate table in the settings "
            "panel is the user's configuration, not a statement of law — check the rates for the period you are "
            "working in and edit them. Second, the column mapping must name the right columns. Where the ledger has "
            "no declared VAT or withholding column the screen labels the figure 'derived', which means "
            "'this is what the tax would be', never 'this is what the client filed'.",
        "What it becomes":
            "The tax exceptions schedule and exposure summary in the certified PDF, and the supporting schedule for "
            "a VAT re-adjustment, an amended return, a withholding registration or a self-assessment disclosure.",
    },
    "signoff": {
        "What this screen is":
            "The signed report — the certificate a third party relies on, and the only output of this suite that "
            "leaves the building.",
        "How to read it":
            "An unqualified opinion means the evidence supported the figures without reservation. A qualified opinion "
            "means a limitation exists, it is listed on the face of the report, and the partner accepts it in writing "
            "before anything issues.",
        "What it becomes":
            "One immutable PDF: cover, scope and methodology, dashboard charts, bank reconciliation, findings, "
            "exception register, limitations, signature block and the SHA-256 fingerprint that locks it to this file.",
    },
}


def page(key: str) -> None:
    """The standing explainer under a page title: what the screen is, how to read it, what it becomes."""
    theme.note(list(PAGES[key].items()), title="How to use this page")


TITLES = {
    "dashboard": "Cash-flow dashboard",
    "findings": "AI executive findings",
    "forensics": "Audit forensics",
    "quarantine": "Exception quarantine",
    "pivot": "Pivot & explore",
    "reconcile": "Bank reconciliation",
    "tax": "Tax health check",
    "signoff": "Partner sign-off",
}

# Order a client actually walks through them, landing page only.
WORKFLOW = ("dashboard", "reconcile", "tax", "forensics", "quarantine", "findings", "signoff")


def outputs() -> None:
    """The landing-screen answer to 'what kind of report does this produce?'."""
    theme.note(
        [(TITLES[k], PAGES[k]["What it becomes"]) for k in WORKFLOW],
        title="The management reports this suite produces",
    )


# ---------- helpers ----------

def _money(value) -> str:
    v = float(value or 0.0)
    a = abs(v)
    sign = "-" if v < 0 else ""
    if a >= 1_000_000_000:
        return f"{sign}KES {a / 1_000_000_000:.2f}bn"
    if a >= 1_000_000:
        return f"{sign}KES {a / 1_000_000:.2f}m"
    if a >= 1_000:
        return f"{sign}KES {a:,.0f}"
    return f"{sign}KES {a:,.2f}"


def _month(value) -> str:
    try:
        return pd.Timestamp(value).strftime("%b %Y")
    except Exception:
        return str(value)


def band(rows: list[tuple[str, str]], title: str = "What this tells you") -> None:
    if rows:
        theme.note(rows, title)


# ---------- dashboard ----------

def kpis(ds, monthly, metric, total_value: float, checks_ok: int, delta, forecast, projected) -> None:
    rows = []
    n = len(ds.clean_df)
    if metric:
        avg = total_value / n if n else 0.0
        rows.append((
            "The headline",
            f"{n:,} records carrying {_money(total_value)} of value — about {_money(avg)} per transaction. "
            "That average is the useful part: if it drifts month to month, the mix of business changed rather than the volume."))
    score = ds.quality["overall"]
    tone = (
        "high enough to quote to a lender or a board" if score >= 90 else
        "below the 90% floor, so the certificate can only be issued qualified — fix the data before you present it"
    )
    rows.append(("How much to trust it",
                 f"Data quality scores {score:.1f}%, which is {tone}. "
                 f"{checks_ok} of {len(ds.checks)} integrity checks passed."))
    if delta:
        rows.append(("Direction of travel",
                     f"The latest month moved {delta.replace('% MoM', '%')} against the month before it. "
                     "One month is noise, three in the same direction is a trend."))
    if forecast is not None and projected is not None and monthly is not None and len(monthly):
        last = float(monthly[metric].iloc[-1])
        basis = "above" if projected > last else "below"
        rows.append(("The projection",
                     f"The straight-line fit points at {_money(projected)} next month, {basis} the most recent actual. "
                     "It extends the average slope of the history you have — treat it as a planning range, not a forecast to commit."))
    band(rows, "What the headline tiles tell you")


def trend(monthly, date_col, metric, forecast) -> None:
    if monthly is None or not len(monthly):
        return
    rows = []
    y = monthly[metric].astype(float)
    first, last = float(y.iloc[0]), float(y.iloc[-1])
    hi, lo = int(y.idxmax()), int(y.idxmin())
    span = f"{_month(monthly[date_col].iloc[0])} to {_month(monthly[date_col].iloc[-1])}"
    if len(monthly) == 1:
        rows.append(("Too short for a trend",
                     "Only one month of dated activity was found, so this is a snapshot rather than a trend. "
                     "Any month-over-month or projection claim would be unsupported."))
    else:
        rows.append((
            "Shape of the year",
            f"{len(monthly)} months of activity ({span}). Peak {_month(monthly[date_col].iloc[hi])} at {_money(y.iloc[hi])}, "
            f"trough {_month(monthly[date_col].iloc[lo])} at {_money(y.iloc[lo])} — a "
            f"{abs(y.iloc[hi] - y.iloc[lo]) / max(abs(y.mean()), 1) * 100:.0f}% swing around the average, which is what "
            "a cash planner has to fund."))
        if first:
            move = (last - first) / abs(first) * 100
            rows.append((
                "Start to finish",
                f"The latest month is {move:+.1f}% against the first. "
                + ("Growth of this size usually needs a facility or a collections push, not just optimism."
                   if move > 15 else
                   "Broadly flat — the business is repeating itself, so cost control is where the improvement has to come from."
                   if -15 <= move <= 15 else
                   "Value is falling. The next conversation should be with whoever owns the revenue lines, not with the spreadsheet.")))
    if forecast is not None and len(monthly) < 6:
        rows.append(("Reliability caveat",
                     "Fewer than six months of history means the fitted line has almost nothing behind it. "
                     "Read the dashed section as arithmetic, not as insight."))
    band(rows, "What the trend chart tells you")


def breakdown(dim, g, total) -> None:
    if g is None or not len(g) or not total:
        return
    top_name, top_val = str(g.index[0]), float(g.iloc[0])
    share = top_val / total * 100
    top3 = float(g.head(3).sum()) / total * 100
    rows = [(
        "Where the value concentrates",
        f"By {dim.lower()}, the largest group is “{top_name}” at {_money(top_val)} — {share:.1f}% of the ledger. "
        f"The top three together are {top3:.1f}% of everything.")]
    if share >= 40:
        rows.append(("Why it matters",
                     "One name carrying four in every ten shillings is concentration risk. If that is a customer, their "
                     "payment behaviour is now your cash-flow behaviour; if it is a cost head, it is the first place a "
                     "saving is actually available."))
    elif share >= 20:
        rows.append(("Why it matters",
                     "Noticeable but not dangerous. Keep the top group in the monthly pack and watch whether its share creeps up."))
    else:
        rows.append(("Why it matters",
                     "Well spread — no single counterparty or category can move the whole result on its own, which is the "
                     "safer position to be in."))
    rows.append(("What to do with it",
                 "Switch to Donut when presenting the split, Bar when the names matter more than the share, and take it "
                 "to Pivot & explore when you need the same cut by a second dimension."))
    band(rows, "What the split tells you")


def correlation(x, y, corr, n) -> None:
    if x == y:
        return
    a = abs(float(corr or 0.0))
    if a >= 0.7:
        strength, what = "strong", "one moves with the other almost lockstep"
    elif a >= 0.4:
        strength, what = "moderate", "they tend to move together, with a lot of slack"
    elif a >= 0.2:
        strength, what = "weak", "there is a hint of a relationship, but most of the movement is unexplained"
    else:
        strength, what = "negligible", "for practical purposes these two columns are unrelated"
    rows = [(
        "Reading it",
        f"{x} against {y}: {strength} {'positive' if corr >= 0 else 'inverse'} relationship (r = {float(corr or 0):+.2f} "
        f"over {n:,} rows) — {what}.")]
    rows.append(("The trap",
                 "Correlation is not causation, and a ledger is full of pairs that move together for an obvious reason "
                 "(both scale with volume) or no reason at all. Use this to decide what to investigate, never to justify "
                 "a claim in a report."))
    if n < 30:
        rows.append(("Sample warning", f"Only {n:,} usable rows — treat the number as unproven."))
    band(rows, "What the scatter tells you")


def search(hit, total: int, query: str, metric) -> None:
    n = len(hit)
    if n == 0:
        band([("Nothing matched",
               f"No record contains “{query}”. Before concluding it never happened, try a shorter fragment: the cleaner "
               "trims stray spaces and splits merged columns, so a full phrase typed from a paper invoice can miss while "
               "half of it hits.")])
        return
    value = float(pd.to_numeric(hit[metric], errors="coerce").sum()) if metric and metric in hit.columns else 0.0
    rows = [(
        "What matched",
        f"{n:,} of {total:,} records ({n / max(total, 1) * 100:.1f}%) contain “{query}”, carrying {_money(value)} of "
        "value. Quote the value, not the row count — the count only says how wide the search was.")]
    if n == total:
        rows.append(("Careful", "Every record matched, so this term discriminates nothing. Narrow it."))
    band(rows, "What the search matched")


def variance(var_df) -> None:
    if var_df is None or not len(var_df):
        return
    v = var_df.dropna(subset=["Change"]) if "Change" in var_df.columns else var_df
    rows = []
    if len(v):
        up = v.loc[v["Change"].idxmax()]
        down = v.loc[v["Change"].idxmin()]
        rows.append((
            "What the board asks",
            f"The largest month-on-month jump was {_money(up['Change'])} in {up['Month']}; the deepest fall was "
            f"{_money(down['Change'])} in {down['Month']}. Those two months are where the explanation is owed."))
        swing = pd.to_numeric(v["Change %"], errors="coerce").abs().max()
        if pd.notna(swing):
            rows.append((
                "How to use it",
                f"Percentage swings run up to {swing:.1f}%. A variance schedule like this is normally read with a "
                "budget column beside it — on its own it shows movement, not whether the movement was allowed."))
    band(rows, "What this schedule tells you")


# ---------- findings ----------

def quality(ds) -> None:
    rows = []
    labels = {
        "Completeness": ("How much of the ledger is filled in", "A low score means the file has holes, and any total "
                         "quoted from it silently assumes the blanks are zero."),
        "Uniqueness": ("How much of it is the same thing twice", "Duplicates inflate every total and make the record "
                       "count a fiction. This is the score that double-payment findings live in."),
        "Validity": ("Whether the values are possible", "Bad dates and negative money land here. Invalid data cannot "
                     "be aged, reconciled or filed, no matter how complete it looks."),
        "Consistency": ("Whether the arithmetic agrees with itself", "Quantity times unit price should equal the "
                        "recorded total. When it does not, someone changed a figure without changing the others."),
    }
    for name, score in ds.quality["components"].items():
        why = labels.get(name, (name, ""))[1]
        flag = "healthy" if score >= 95 else "watch" if score >= 90 else "weak"
        rows.append((f"{name} · {score:.1f}% ({flag})", why))
    overall = ds.quality["overall"]
    rows.append(("The 90% floor",
                 f"Composite score is {overall:.1f}%. At or above 90 the report can be signed unqualified; below it, "
                 "the certificate carries a written limitation, because a weak ledger cannot support a clean opinion no "
                 "matter how good the charts look."))
    band(rows, "What the quality score means")


def integrity(ds) -> None:
    failed = [name for name, ok, _ in ds.checks if not ok]
    rows = [(
        "What these are",
        f"{len(ds.checks)} pass/fail tests on the structure of the ledger: duplicates purged, identifier uniqueness, "
        "arithmetic balancing, sign convention and date validity. They are the checks a reviewer would re-perform by hand.") ]
    if failed:
        rows.append(("Consequence",
                     f"Failed: {', '.join(failed)}. Each one is copied verbatim into the limitations section of the "
                     "certificate, so the reader sees exactly what could not be proved."))
    else:
        rows.append(("Consequence",
                     "All passed, which is what allows the report to be issued without a written limitation."))
    band(rows)


def insights(n_insights: int, n_recs: int, n_changes: int) -> None:
    band([
        ("Synthesized findings",
         f"{n_insights} observations the engine raised itself from the numbers — not a template list. Each one is a "
         "sentence you can put in front of a client as written."),
        ("Recommendations",
         f"{n_recs} actions, generated from what actually failed or drifted in this ledger. Treat them as the 'so what' "
         "page of the pack: findings without a recommendation are just news."),
        ("Change register",
         f"{n_changes:,} individual cell-level adjustments were recorded. This is the difference between 'the software "
         "cleaned it' and 'here is every change, re-performable row by row'."),
    ])


# ---------- forensics ----------

def benford(ben) -> None:
    if ben is None:
        band([("Why nothing is shown",
               "Digit testing needs at least 50 values before the pattern means anything. Below that, random noise looks "
               "identical to manipulation, so the test is withheld rather than misread.")], "What this tells you")
        return
    mad = float(ben["mad"])
    ok = mad < 2.5
    rows = [(
        "The idea in one line",
        "Real transaction amounts start with 1 about 30% of the time and with 9 about 5%. People inventing numbers do not "
        "reproduce that skew, so the first digit acts as a lie detector on the arithmetic.")]
    if ok:
        rows.append((
            "This ledger",
            f"Mean absolute deviation {mad:.2f}% across {ben['n']:,} values — inside the range genuine data produces. "
            "No evidence of hand-made or systematically rounded figures. That is an absence of a signal, not a clean bill "
            "of health: Benford cannot see a single large fabricated invoice."))
    else:
        rows.append((
            "This ledger",
            f"Mean absolute deviation {mad:.2f}% across {ben['n']:,} values, which is outside normal behaviour. This does "
            "not prove fraud — round-number pricing, a fixed fee schedule or a heavily refunded account all distort the "
            "first digit legitimately. It does mean the digit pattern needs a documented explanation before sign-off."))
    rows.append(("What to do",
                 "Filter the ledger to the digits that deviate most in the table above and sample those documents. A "
                 "non-conforming result is disclosed as a limitation, not quietly deleted."))
    band(rows)


def near_dupes(near) -> None:
    if not len(near):
        band([("Nothing flagged",
               "No counterparty was paid the same amount on two different documents. This is the duplicate that exact "
               "dedupe cannot catch, because the receipt numbers differ — only the payer and the amount match.")])
        return
    groups = len(near)
    records = int(near["Count"].sum())
    value = float(near["Amount"].abs().sum())
    band([
        ("What you are looking at",
         f"{groups} group(s) covering {records} records and {_money(value)}, where the same party received the same "
         "amount more than once under separate document numbers."),
        ("Why it is a red flag",
         "Paying an invoice twice is the most common real cash loss in a payables process, and splitting one purchase "
         "into several documents is the most common way an approval limit is evaded. Both leave this footprint."),
        ("Before you accuse anyone",
         "Legitimate causes exist: instalments on one contract, two jobs quoted the same day, a subscription billed "
         "monthly at a flat rate. The output is a work list for document checks, not a conclusion."),
    ])


# ---------- quarantine ----------

def quarantine(anomalies, overrides, total_rows: int) -> None:
    open_items = len(anomalies) - len(overrides)
    if not len(anomalies):
        band([
            ("Nothing was flagged",
             f"No record out of {total_rows:,} broke any rule: no negative amounts, no extreme outliers, no arithmetic "
             "that fails to balance, no repeated identifiers. The exception population is empty, so there is nothing for "
             "a partner to decide."),
            ("What that is worth",
             "An empty quarantine is a result, not an absence of work — the rules ran over every row. It is also the "
             "condition that lets the certificate quote a record count without a carve-out."),
            ("When to distrust it",
             "If the ledger is small, or the money column was detected as something other than the real one, the rules "
             "had nothing to bite on. Check the detected schema on the dashboard before treating this as clean."),
        ])
        return
    rows = [(
        "What this population is",
        f"{len(anomalies):,} of {total_rows:,} records ({len(anomalies) / max(total_rows, 1) * 100:.1f}%) broke at least "
        "one rule: a negative amount, an extreme outlier, arithmetic that does not balance, or a repeated identifier. "
        "They are still inside the ledger — they are flagged, not removed.") ]
    rows.append((
        "Why a human has to touch these",
        "An outlier can be a genuine large payment or a fat-fingered decimal, and the statistics cannot tell them apart. "
        "Only the source document can. Marking a row compliant is the audit trail for that judgement."))
    if open_items:
        rows.append((
            "Effect on the report",
            f"{open_items:,} row(s) still await a decision. Until they are cleared or explained, the exception count in "
            "the certificate carries them, and a large unreviewed population is a classic reason for a qualified opinion."))
    else:
        rows.append(("Effect on the report",
                     "Every flagged row has a recorded decision, so the exception population is closed."))
    band(rows)


# ---------- pivot ----------

def pivot(df, pv, rows_cols, val_cols, agg_label: str) -> None:
    lines = [(
        "What this is",
        "A cross-tabulation — the same total, cut by what it belongs to. It is the single table a management pack "
        "usually needs most, and it is built on the cleaned ledger so it agrees with the dashboard by construction.")]
    if pv is not None and len(rows_cols) and len(val_cols):
        body = pv[~pv.astype(str).apply(lambda r: r.str.contains("Grand Total", na=False)).any(axis=1)] if len(pv) else pv
        lines.append((
            "This cut",
            f"{agg_label} of {', '.join(val_cols)} by {', '.join(rows_cols)} — {len(pv):,} groups built from "
            f"{len(df):,} records."))
        if len(rows_cols) == 1 and len(val_cols) == 1 and agg_label in {"Sum", "Mean"} and len(body):
            num = pd.to_numeric(body[val_cols[0]], errors="coerce")
            if num.notna().any():
                if agg_label == "Sum":
                    share = float(num.max()) / float(num.sum()) * 100 if num.sum() else 0.0
                    lines.append((
                        "How to read the spread",
                        f"The biggest group holds {share:.1f}% of the total. Anything under about 5% is worth grouping "
                        "into 'Other' before you show it to anyone — a long tail makes a management table unreadable."))
                else:
                    lines.append((
                        "How to read the spread",
                        f"Group averages run from {num.min():,.0f} to {num.max():,.0f}. With a mean, always check how "
                        "many records sit behind each group — three large invoices can look like a healthy average."))
    else:
        lines.append(("Nothing to interpret yet",
                      "Choose at least one Row and one Value. Count answers 'how many', Sum answers 'how much', and "
                      "Mean answers 'how typical' — picking the wrong one is the most common reporting error there is."))
    band(lines, "What this pivot tells you")


def profiler(col, s, is_num: bool) -> None:
    filled = float(s.notna().mean() * 100)
    unique = int(s.nunique())
    if is_num:
        band([
            ("What you are checking",
             f"“{col}” is numeric: {filled:.1f}% filled, {unique:,} distinct values, sum {s.sum():,.0f}. Use this page "
             "to decide whether a column is safe to add up."),
            ("The test before you trust a total",
             "If the minimum is negative, the column mixes money going out with money coming in and a plain sum is "
             "meaningless. If the mean sits far from the median, a few extreme values are dragging it — quote the "
             "median instead."),
        ])
    else:
        band([
            ("What you are checking",
             f"“{col}” is a category: {filled:.1f}% filled and {unique:,} distinct values."),
            ("The test before you group by it",
             "One value covering almost everything, or hundreds of near-duplicate spellings, will shred any pivot. "
             "Both are visible in this donut before they embarrass a report."),
        ])


# ---------- reconciliation ----------

def bridge(s) -> None:
    rows = [(
        "The one number that matters",
        f"{s['match_rate']:.1f}% of bank movements found a matching ledger entry ({s['matched_bank']:,} of "
        f"{s['bank_lines']:,} lines). Paired items are proved twice — by your books and by the bank — so the rest of "
        "this page is about the ones that were not.")]
    bank_only, ledger_only = float(s["bank_only_total"]), float(s["ledger_only_total"])
    if bank_only:
        rows.append((
            "In the bank, not in the ledger",
            f"{s['bank_only_lines']:,} item(s) worth {_money(bank_only)} of real money moved that the books do not "
            "mention. This is the serious direction of miss: it is understated turnover, it is what a tax authority "
            "finds first, and every line needs either a booking or an explanation."))
    else:
        rows.append(("In the bank, not in the ledger",
                     "Nothing. Every movement on the bank statement is recorded in the books."))
    if ledger_only:
        rows.append((
            "In the ledger, not in the bank",
            f"{s['ledger_only_lines']:,} item(s) worth {_money(ledger_only)} the books claim but the bank never saw. "
            "Either it is still outstanding — which makes it a collection problem and a receivable — or it was recorded "
            "against a payment that never happened."))
    else:
        rows.append(("In the ledger, not in the bank",
                     "Nothing. Every booked item has reached the bank."))
    if s["duplicate_lines"]:
        rows.append((
            "Duplicate bank items",
            f"{s['duplicate_lines']:,} bank item(s) repeating a payment already settled, worth "
            f"{_money(s['duplicate_total'])}. This is recoverable cash and the fastest win on the page."))
    if s["foots"]:
        rows.append((
            "The bridge",
            f"Starting from ledger value {_money(s['ledger_total'])} and walking it to the bank's own movement of "
            f"{_money(s['bank_total'])} leaves {_money(s['residual'])} unexplained. Every shilling sits in exactly one "
            "line of that bridge, which is what makes it a control rather than a plug — and it is the condition the "
            "certificate depends on."))
    else:
        rows.append((
            "The bridge",
            f"{_money(s['residual'])} of value cannot be placed. Until it can, this reconciliation is not evidence of "
            "anything and no report built on it can be signed unqualified."))
    band(rows)


def split_donut(s) -> None:
    bank_total = abs(float(s["bank_total"]))
    if not bank_total:
        return
    paired = float(s["paired_bank_total"])
    ledger_total = abs(float(s["ledger_total"]))
    proved_ledger = (ledger_total - float(s["ledger_only_total"])) / ledger_total * 100 if ledger_total else 0.0
    band([
        (
            "What this picture shows",
            f"Every shilling of bank movement sorted into exactly one bucket, so the ring is the whole statement and not "
            f"a sample. {paired / bank_total * 100:.1f}% of the bank's money is paired with a ledger entry, which is the "
            "part that is proved twice. This ring counts value, not lines — the tile above can report 99% of lines "
            "matched while 100% of value is paired, because the items that failed to match were the small ones."),
        (
            "Why the two percentages differ",
            f"On the bank side {paired / bank_total * 100:.1f}% is proved; on the ledger side {proved_ledger:.1f}% is. "
            "They can differ because the two records do not contain the same items — money that moved without being "
            "booked raises the bank's total, and booked items that never banked raise the ledger's. Read the difference "
            "as the size of the explaining job, not as an error in the chart."),
        (
            "How to read the ring",
            "A thin slice is worth more attention than a fat one when it is the slice nobody has accounted for. Paired "
            "value needs no action; everything else on this ring has a line, an amount and somebody's name attached to it."),
    ], "What the value split tells you")


def monthly_tieout(monthly_df) -> None:
    if monthly_df is None or not len(monthly_df):
        return
    m = monthly_df.copy()
    if "Tie-up %" not in m.columns or not len(m):
        return
    worst = m.loc[m["Tie-up %"].idxmin()]
    best = m.loc[m["Tie-up %"].idxmax()]
    rows = [(
        "Why it is on the page",
        "A total that ties can hide two large errors cancelling out. Month by month, they cannot. This is where a "
        "reviewer stops trusting an aggregate and starts asking about periods.") ]
    rows.append((
        "This ledger",
        f"Best month {_month(best['Month'])} at {float(best['Tie-up %']):.1f}%, weakest {_month(worst['Month'])} at "
        f"{float(worst['Tie-up %']):.1f}%. Start with the weak month: read its Bank − ledger column before its tie-up "
        "percentage, because a large gap paired with a high tie-up rate is simply money that moved after the cut-off."))
    rows.append(("Timing versus error",
                 "Timing gaps move to the next period on their own and need no correcting — they are explained, not "
                 "booked. Anything that stays unmatched in both directions across months is an error, and it stays with you."))
    band(rows, "What the tie-out tells you")


def exceptions(bank_only, ledger_only, dupes) -> None:
    rows = [(
        "How to work these tabs",
        "Paired items are the evidence — take them to the file and check a sample. The other three tabs are the "
        "action list, and they are ordered by amount on purpose: the top of each list is where the value is.")]
    if len(bank_only):
        rows.append((
            "In bank, not in ledger",
            f"{len(bank_only):,} line(s). Ask the bank for the narration or the payment reference on the largest ones; "
            "unrecorded receipts are booked first, explained second."))
    if len(ledger_only):
        rows.append((
            "In ledger, not in bank",
            f"{len(ledger_only):,} line(s). Confirm whether the cash ever arrived. If it did not, the entry comes out "
            "or the customer gets chased — leaving it in flatters the results."))
    if len(dupes):
        rows.append((
            "Duplicate payments",
            f"{len(dupes)} item(s). Recover or reverse before sign-off; a known duplicate that is left in the books is "
            "a finding you have already accepted."))
    if not any(len(x) for x in (bank_only, ledger_only, dupes)):
        rows.append(("Nothing to work",
                     "Both sides are fully accounted for, which is the result the reconciliation page exists to produce."))
    band(rows)


# ---------- tax health check ----------

_SLOT_LABELS = {
    "date": "date", "vat": "declared VAT", "wht": "withholding", "net": "net of tax", "gross": "gross",
    "code": "tax code", "pin": "taxpayer PIN", "doc": "document number", "payees": "payee name",
}


def tax_setup(res) -> None:
    cols = res["cols"]
    named = [f"{_SLOT_LABELS[k]} → “{cols[k]}”" for k in _SLOT_LABELS if cols.get(k)]
    missing = [label for key, label in _SLOT_LABELS.items() if not cols.get(key)]
    rows = [(
        "What the engine was actually handed",
        (", ".join(named) if named else "nothing recognisable") + ". Every exception on this page is computed from "
        "those columns and the rate table, which is why the mapping is shown rather than assumed. If one of them "
        "names the wrong column, change it above and the whole page re-computes — nothing here is cached against a "
        "guess.",
    )]
    if missing:
        rows.append((
            "What it therefore cannot test",
            "No column was found for " + ", ".join(missing) + ". The corresponding check reports that honestly "
            "instead of inventing a figure: a tax screen that quietly fills its own gaps is worse than no screen, "
            "because it gets quoted.",
        ))
    if res["unparsed_dates"]:
        rows.append((
            f"{res['unparsed_dates']:,} date(s) the engine could not read",
            "Those lines were still tested, but against the schedule's default rate rather than the rate on their "
            "own date. If the rate moved inside your period that is the one place this page can be wrong, and it is "
            "fixable by cleaning the date column.",
        ))
    band(rows, "What this run was working from")


def tax_vat(vat) -> None:
    basis = vat["basis"]
    if basis == "none":
        band([("VAT was not tested", vat["note"])], "What the VAT test tells you")
        return
    if basis == "derived":
        band([
            ("A shape, not a return",
             f"Output VAT of {_money(vat['vat_derived'])} here is a derived figure: the ledger has no VAT column, so the "
             f"engine took {_money(vat['gross_inclusive'])} of gross value across {vat['rows_tested']:,} lines and "
             "backed tax out of all of it at the configured rate. That is a legitimate scoping number — it says what "
             "the order of magnitude is if everything was standard-rated — and it is not a figure anybody filed, so "
             "it must not appear in an objection or a refund claim as though it did."),
            ("What to do with it",
             "Take the filed returns and the supplier invoices labelled with their tax codes, load them as the VAT "
             "column, and this same test becomes a re-performance instead of an estimate. Until then the honest "
             "sentence to the client is: we have sized the exposure, we have not proved it."),
            ("The finding inside the gap",
             "A purchase ledger with no VAT column is itself worth reporting. Either the tax sits in a separate "
             "return file the ledger cannot be tied to, or the business is not separating VAT at all — and the "
             "second is the one that becomes an assessment."),
        ], "What the VAT test tells you")
        return

    rows = [(
        "The headline",
        f"{vat['exceptions']:,} of {vat['rows_tested']:,} line(s) fail recomputation against the rate in force on "
        "their own date. This is the useful framing for a client conversation: not 'is the VAT total roughly right' "
        "but 'which documents would be pulled first, and what does each one cost'."),
    ]
    if vat["exceptions"]:
        mix = vat["table"]["Issue"].value_counts().head(3)
        rows.append((
            "What the exceptions are made of",
            "; ".join(f"{int(n)} × {issue}" for issue, n in mix.items())
            + ". A handful of recurring issue types is a systems or training problem and fixes in one pass; a table "
              "of fifteen unrelated problems is a bookkeeping problem and takes longer.",
        ))
        if vat["under_declared"]:
            rows.append((
                "Under-declared — the direction KRA assesses",
                f"{_money(vat['under_declared'])} of VAT was charged as less than the rate required, or not charged "
                "where it should have been. This is the number that grows penalties and interest, and it is the "
                "number a self-assessment disclosure has to cover."),
            )
        if vat["over_declared"]:
            rows.append((
                "Over-declared — the direction nobody chases",
                f"{_money(vat['over_declared'])} of VAT was booked above what the rate supports. That is not a "
                "penalty risk, it is cash: output VAT charged to customers and never properly owed, or input VAT "
                "understated on a line that should have carried more. Fixing the schedule should recover it, and a "
                "health check that only reported the first direction would be an argument for the tax authority."),
            )
    else:
        rows.append((
            "A clean result, and its limit",
            f"All {vat['rows_tested']:,} lines with declared VAT foot to the rate table on their own dates. That is "
            "arithmetic, not absolution: the test cannot know whether a supply was *correctly classified* as "
            "standard or zero-rated, nor whether a return was filed on time. Those need the contract terms and the "
            "iTax ledger, not this file.",
        ))
    band(rows, "What the VAT test tells you")


def tax_control(control) -> None:
    if not control["months"]:
        band([("The control account could not be built", control["note"])], "What the VAT control account tells you")
        return
    rows = [(
        "Why this schedule exists",
        f"The VAT control account is the monthly position — output VAT less input VAT, restated from the ledger into "
        f"return periods. Summed over {control['months']} month(s) it comes to {_money(control['net_total'])}, "
        + ("a net payable: VAT collected and owed." if control["net_total"] >= 0 else "net recoverable: VAT paid and "
           "never claimed back.") + " This is the figure a filed return has to agree with. If it does not, the "
        "difference is either a posting error in the ledger or a return made on something else."),
    ]
    rows.append((
        "How output and input were separated",
        f"Using {control['basis']}. "
        + ("That is a rule the file itself states, so the split is evidence. " if control["basis"].startswith("column")
           else "That rule is the engine's reading of the file rather than a column the client maintains, so treat "
                "the split as indicative: the total VAT may still be right while its allocation between output and "
                "input is not. Ask for the VAT control account from the general ledger and this becomes a "
                "reconciliation instead of an inference."),
    ))
    if control["derived"]:
        rows.append((
            "Labelled derived",
            "There is no VAT column in this ledger, so each month's tax was computed from the amounts at the "
            "configured rate. The shape of the profile — which months were busy, where the activity stops — is real; "
            "the shilling figures are estimates and are printed as such.",
        ))
    if control["gap_months"]:
        rows.append((
            f"{len(control['gap_months'])} silent month(s): " + ", ".join(_month(m) for m in control["gap_months"][:6]),
            "No VATable line at all in those periods inside a span that is otherwise active. Two explanations and "
            "both are findings: activity happened and was not recorded, or a return was filed for the period from "
            "somewhere outside this ledger. A nil return is a filing event; an empty month in the books is not one.",
        ))
    band(rows, "What the VAT control account tells you")


def tax_wht(wht) -> None:
    if not wht["wht_heads"]:
        band([("Withholding was not tested", wht["note"])], "What the withholding test tells you")
        return
    rows = [(
        "The scope, and why it is narrow",
        f"{wht['expense_lines']:,} of the lines here are expenses, and {wht['wht_heads']:,} of those describe a "
        "service head that attracts withholding — consultancy, professional fees, management and directors' fees, "
        "rent, other services. Everything else was left alone deliberately. A screen that flagged every purchase as "
        "a withholding risk gets ignored; the list below is the short part of the ledger that carries the tax.",
    )]
    if len(wht["table"]):
        rows.append((
            "The shortfall",
            f"{len(wht['table']):,} line(s) fall short of the required withholding by {_money(wht['unwithheld'])} in "
            f"total, against {_money(wht['declared_total'])} actually deducted."
            + (" The ledger carries a withholding column, so these are declared-versus-expected differences on named "
               "documents — the strongest form of this finding."
               if wht["basis"] == "declared" else
               " The ledger carries no withholding column at all, so the test assumes nobody withheld. Confirm that "
               "against the WHT returns before the number leaves this room; it may live in a separate filing."),
        ))
        rows.append((
            "Whose liability it is",
            "Withholding is deducted from the payee but accounted for by the payer, so a shortfall above is this "
            "company's own cost even though the tax was always somebody else's. The second-order exposure is worse "
            "than the first: an expense suffered without the required withholding can be disallowed as a deduction, "
            "which puts tax on the grossed-up amount as well as the withheld sum.",
        ))
    else:
        extra = (
            " The ledger does carry a withholding column, so this was a comparison against declared figures rather "
            "than an assumption about them."
            if wht["basis"] == "declared" else
            " Note that the ledger carries no withholding column, so agreement here means the schedule expects no "
            "withholding on these heads — it is not evidence that certificates were issued."
        )
        rows.append(("Nothing short",
                     f"All {wht['wht_heads']:,} withholding-head line(s) agree with the schedule you configured, to "
                     f"within fifty sen.{extra}"))
    if len(wht["register"]):
        rows.append((
            "What the certificate register is for",
            f"{len(wht['register']):,} payee(s) are owed a withholding certificate for the tax that should have been "
            "deducted, each with a remittance due date computed as the twentieth of the month following payment. The "
            "due dates are the filing obligation, and they exist whether or not anybody withheld — so this table "
            "doubles as the overdue-filing list and the document pack a payee will ask for.",
        ))
    band(rows, "What the withholding test tells you")


def tax_pins(pins) -> None:
    if not pins["populated"] and not len(pins["table"]):
        band([("Supplier identity was not tested", pins["note"])], "What the supplier PIN test tells you")
        return
    rows = [(
        "Coverage before conclusions",
        f"{pins['coverage']}% of lines carry a PIN ({pins['populated']:,} of them). The unpopulated part is the real "
        "story: a supplier record with no taxpayer identification cannot be matched to the KRA register, cannot be "
        "reconciled against e-TIMS, and is the first thing an officer disallows when a deduction is challenged.",
    )]
    if len(pins["table"]):
        rows.append((
            f"{len(pins['table'])} PIN(s) that fail the shape test",
            f"{pins['malformed']} do not look like an issued PIN at all; {pins['placeholders']} are placeholders "
            "(a digit run like A000000000A typed into a mandatory field so a posting would go through). Placeholder "
            "PINs are a control finding on their own, independent of tax: a required field being bypassed means the "
            "supplier master is not being checked by anybody.",
        ))
    if pins["shared"]:
        rows.append((
            f"{pins['shared']} PIN(s) shared across different payee names",
            "One registration invoicing under two names is either a mis-keyed PIN or a supplier trading as somebody "
            "other than the entity KRA registered. Both produce iTax mismatches between what the supplier declares as "
            "sales and what the buyer declares as purchases, which is the audit trigger that ends in a "
            "non-deductible expense. Resolve by name, not by assuming a typo.",
        ))
    multi = pins["pin_per_payee"]
    if len(multi) and int(multi["Distinct PINs"].max()) > 1:
        rows.append((
            "The same payee invoicing under several PINs",
            f"{int(multi['Distinct PINs'].max())} distinct PINs appear against one supplier name at the top of that "
            "list — the mirror image of the shared-PIN problem, and usually a group of entities billed to one "
            "trading name. Pick the correct registration per contract and keep the evidence of the choice.",
        ))
    band(rows, "What the supplier PIN test tells you")


def tax_sequence(seq) -> None:
    if not seq["groups"]:
        band([("Document sequence was not tested", seq["note"])], "What the sequence test tells you")
        return
    rows = [(
        "What is being counted",
        f"{seq['groups']} series read as {seq['read_by']}, covering {seq['coverage']}% of lines. {seq['gaps']} "
        f"number gap(s), {seq['repeats']} repeated number(s) and {seq['inversions']} date inversion(s). The reading "
        "matters as much as the count: a company that runs separate series for branches and suppliers is not gapping, "
        "and an engine that groups everything into one sequence will manufacture exceptions out of an orderly file.",
    )]
    if seq["gaps"]:
        rows.append((
            "Gaps",
            "A missing invoice number is not proof of anything by itself — cancelled documents, a number block held "
            "back for a branch, or a system re-code all produce them. What makes it a tax question is e-TIMS: every "
            "issued invoice has to transmit, so each gap needs either the document or the cancellation note as the "
            "answer. Work the largest jump first; a gap of forty is a different conversation from a gap of one.",
        ))
    if seq["repeats"]:
        rows.append((
            "Repeated numbers",
            "The same document number used twice is either a duplicate posting or two different invoices carrying one "
            "number. The second is the risk: it is how a value change on an already-issued invoice gets into the "
            "books without a new document. Cross-check these against the near-duplicate register on the forensics "
            "page, which pairs on amount and counterparty rather than on number.",
        ))
    if seq["inversions"]:
        rows.append((
            "Dates running backwards inside a series",
            "Sequential document numbers whose dates go backwards are the signature of backdating — a document "
            "created later and dated earlier, typically to move income or a claim between periods. One inversion is "
            "often a data-entry error; a run of them, or an inversion that crosses a period or rate boundary, is a "
            "finding you should be able to explain in writing before an assessment does it for you.",
        ))
    band(rows, "What the sequence test tells you")


def tax_exposure(exp, vat, wht) -> None:
    if not exp["total"]:
        band([
            ("Nothing to expose",
             "No under-declared VAT and no unwithheld tax were found on this run, so there is no assessment figure "
             "to build. That is a statement about what this file supports, not a guarantee of compliance — see the "
             "basis labels on the VAT and withholding tabs for what was estimated rather than tested."),
        ], "What the exposure summary tells you")
        return
    rates = exp.get("rates") or {}
    rows = [
        ("What this number is",
         f"A provisioning and negotiating figure, not an assessment: {_money(exp['tax'])} of tax at risk, "
         f"{_money(exp['penalty'])} of penalty and {_money(exp['interest'])} of interest over "
         f"{exp['months']:g} month(s) outstanding, totalling {_money(exp['total'])}. Nobody has assessed this and no "
         "penalty has been imposed. Its value is that it is defensible arithmetic, so a client can decide what to "
         "disclose and what to provide for before an audit sets both for them."),
        ("Which assumptions are yours, not the engine's",
         "The rates come from the schedule you configured (late filing "
         f"{rates.get('filing_pct', 0):g}%, late payment {rates.get('payment_pct', 0):g}%, interest "
         f"{rates.get('interest_pm', 0):g}% per month), and the months outstanding are a slider on this page. Change "
         "either and this total moves, so quote the total with the assumptions attached — and re-check them against "
         "the current law for the period in question, which this suite does not and cannot know."),
        ("What is deliberately not netted off",
         f"Under-declared VAT of {_money(vat.get('under_declared', 0.0))} is carried at full value even where this "
         f"same file also shows {_money(vat.get('over_declared', 0.0))} over-declared, and withholding of "
         f"{_money(wht.get('unwithheld', 0.0))} is added rather than offset. An authority assesses the shortfalls and "
         "leaves you to claim the overpayments separately, in a different process, often on a time limit. A total "
         "that netted the two would flatter the position."),
    ]
    if vat["basis"] != "declared":
        rows.append((
            "Why VAT contributes nothing here",
            "The VAT half of this exposure is zero because the ledger carries no declared VAT column to recompute, so "
            "the engine will not pretend to know what was under-declared. The withholding figure stands on its own. "
            "Load the returns or a VAT column and the exposure roughly doubles its claim to be real.",
        ))
    band(rows, "What the exposure summary tells you")


# ---------- sign-off ----------

def signoff(ds, qualified: bool, limitations, recon, tax=None) -> None:
    rows = [(
        "What is actually being signed",
        f"{len(ds.clean_df):,} records of {ds.source}, fingerprint {ds.hash[:16]}… , quality "
        f"{ds.quality['overall']:.1f}%, {sum(1 for _, ok, _ in ds.checks if ok)} of {len(ds.checks)} integrity checks "
        "passed. The signature attaches to those facts and to nothing else — re-upload a different file and the "
        "fingerprint no longer matches, which is what makes the PDF auditable after the fact.") ]
    if recon is None:
        rows.append(("Reconciliation status",
                     "No bank statement has been tied out for this ledger, so the report proves internal consistency "
                     "only. It cannot yet claim the cash actually exists. Run the reconciliation page before a "
                     "third party relies on the figures."))
    elif recon["stats"]["foots"]:
        rows.append(("Reconciliation status",
                     f"Included: {recon['stats']['match_rate']:.1f}% of bank lines tied and the bridge foots. That "
                     "converts the report from 'the books agree with themselves' to 'the books agree with the bank'."))
    else:
        rows.append(("Reconciliation status",
                     f"The bridge does not foot ({_money(recon['stats']['residual'])} unexplained), so the report "
                     "carries that as a written limitation and can only be issued qualified."))
    if tax is None:
        rows.append(("Tax health check",
                     "The tax health check was never run for this ledger, so the report makes no statement about VAT "
                     "or withholding. That is not a clean bill of health — it is simply a page nobody turned. If the "
                     "engagement has a compliance angle, run it before this certifies anything."))
    elif tax["exposure"]["total"]:
        rows.append((
            "Tax health check",
            f"VAT and withholding were re-performed on {tax['rows']:,} line(s) at the schedule the preparer "
            f"configured, producing {_money(tax['exposure']['total'])} of exposure"
            + (" — which the report carries as a written limitation because it clears the 1% materiality floor on the "
               "value tested. A statutory liability that has not been remitted or provided for is disclosed, not "
               "buried in an exception tab."
               if any(lim.startswith("Tax health check") for lim in limitations) else
               ", below the materiality floor, so it is disclosed in the tax section without qualifying the "
               "certificate.")
            + " Either way the certificate now says what the ledger's tax position is worth, and on which "
              "assumptions."))
    else:
        rows.append((
            "Tax health check",
            f"VAT and withholding were re-performed on {tax['rows']:,} line(s) and nothing material surfaced. Where "
            "the VAT basis on that page reads 'derived', this statement is weaker than it looks: it means no declared "
            "figure was available to contradict, not that the returns were proved correct."))
    if qualified:
        rows.append((
            "Before you issue",
            f"{len(limitations)} limitation(s) will be printed on the face of the certificate. A qualified report is "
            "still a legitimate deliverable — it says what was checked and what could not be — but a reader who has "
            "not been told in advance will read it as a failure. Send it with the explanation, not after the questions."))
    else:
        rows.append((
            "Before you issue",
            "Everything passed, so the certificate is unqualified: the evidence supported the figures without "
            "reservation. That is the strongest statement this suite can make — and it is only credible because this "
            "same page will not issue it when the tests do not pass."))
    rows.append((
        "What the reader gets",
        "A PDF that cannot be quietly edited: the hash, timestamp, partner name and the exception counts are printed "
        "inside it, and every table in it can be re-performed from the source file."))
    band(rows, "What this certificate says")
