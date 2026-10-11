"""Dataset loading and sample data generation."""

import hashlib
import io

import numpy as np
import pandas as pd
import streamlit as st


def fingerprint(raw_bytes: bytes) -> str:
    """Full SHA-256 digest — this string is quoted as evidence on the certificate."""
    return "SHA256:" + hashlib.sha256(raw_bytes).hexdigest().upper()


@st.cache_data(show_spinner=False)
def sheet_names(raw_bytes: bytes, filename: str) -> list[str]:
    """Worksheets in an Excel workbook; empty list for CSV."""
    if filename.lower().endswith(".csv"):
        return []
    with pd.ExcelFile(io.BytesIO(raw_bytes)) as xl:
        return [str(s) for s in xl.sheet_names]


@st.cache_data(ttl="1h", max_entries=8, show_spinner="Reading ledger…")
def load_dataset(raw_bytes: bytes, filename: str, sheet: str | None = None) -> pd.DataFrame:
    buf = io.BytesIO(raw_bytes)
    if filename.lower().endswith(".csv"):
        return pd.read_csv(buf)
    return pd.read_excel(buf, sheet_name=sheet if sheet is not None else 0)


def _sample_ledger(n: int = 600, seed: int = 7) -> pd.DataFrame:
    r = np.random.default_rng(seed)
    days = pd.date_range("2025-01-01", "2026-09-30", freq="D")
    df = pd.DataFrame(
        {
            "Invoice No": [f"INV-{1000 + i}" for i in range(n)],
            "Invoice Date": r.choice(days, n),
            "Customer": r.choice(
                [
                    "Savannah Traders",
                    "Lake Basin Foods",
                    "Rift Hardware",
                    "Coastline Logistics",
                    "Highland Pharmacy",
                    "Mara Supplies",
                ],
                n,
            ),
            "County": r.choice(["Nairobi", "Mombasa", "Kisumu", "Nakuru", "Eldoret"], n),
            "Quantity": r.integers(1, 60, n),
            "Unit Price": r.choice([450, 1200, 2300, 5800, 9900], n),
        }
    )
    df["Total Amount"] = df["Quantity"] * df["Unit Price"]
    df["KRA PIN"] = [f"P{r.integers(0, 10**9):09d}A" for _ in range(n)]
    # Seed realistic defects so the AI cleaning layer has work to do.
    dirty_idx = r.choice(n, size=n // 20, replace=False)
    df.loc[dirty_idx[: len(dirty_idx) // 2], "County"] = None
    df.loc[dirty_idx[len(dirty_idx) // 2 :], "Customer"] = "  " + df.loc[dirty_idx[len(dirty_idx) // 2 :], "Customer"].astype(str) + " "
    df = pd.concat([df, df.sample(n=4, random_state=int(seed))], ignore_index=True)
    return df


@st.cache_data(show_spinner=False)
def make_sample_csv(n: int = 600, seed: int = 7) -> bytes:
    buf = io.StringIO()
    _sample_ledger(n, seed).to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


@st.cache_data(show_spinner=False)
def make_sample_statement_csv(n: int = 600, seed: int = 7) -> bytes:
    """A bank statement for the sample ledger, with the defects a reconciliation must catch:
    unbanked invoices, bank charges, a double payment, a short payment and a bundled settlement."""
    df = _sample_ledger(n, seed)
    r = np.random.default_rng(seed + 11)
    df = df.drop_duplicates(subset=["Invoice No"], keep="first").reset_index(drop=True)

    banked = df.sample(frac=0.94, random_state=int(seed) + 3).sort_values("Invoice Date")
    lines = []
    for row in banked.to_dict("records"):
        paid = pd.Timestamp(row["Invoice Date"]) + pd.Timedelta(days=int(r.integers(0, 6)))
        lines.append(
            {
                "Transaction Date": paid,
                "Description": f"{row['Customer'].strip()} invoice payment {row['Invoice No']}",
                "Ref No": row["Invoice No"],
                "Deposit (Cr)": round(float(row["Total Amount"]), 2),
                "Withdrawal (Dr)": 0.0,
            }
        )

    # Bank charges and statutory deductions that were never booked in the ledger.
    anchor = pd.Timestamp(lines[5]["Transaction Date"]) if len(lines) > 5 else pd.Timestamp("2025-06-01")
    for offset, (label, amount) in enumerate((("BANK COMMISSION", 150.0), ("ATM CASH WITHDRAWAL", 20000.0), ("STAMP DUTY CHARGE", 85.5))):
        lines.append(
            {
                "Transaction Date": anchor + pd.Timedelta(days=offset),
                "Description": label,
                "Ref No": f"CHG-{int(r.integers(1000, 9999))}",
                "Deposit (Cr)": 0.0,
                "Withdrawal (Dr)": amount,
            }
        )

    # Two short payments: same invoice, different amount → value variance.
    base = lines[10]
    lines.append({**base, "Description": base["Description"] + " part settlement", "Deposit (Cr)": round(base["Deposit (Cr)"] * 0.93, 2)})
    # One duplicate credit: identical amount and narration, three days later.
    dup = lines[20]
    lines.append({**dup, "Transaction Date": pd.Timestamp(dup["Transaction Date"]) + pd.Timedelta(days=3)})
    # One bundled credit settling three invoices in a single transfer.
    trio = lines[30:33]
    lines.append(
        {
            "Transaction Date": pd.Timestamp(trio[2]["Transaction Date"]) if trio else pd.Timestamp("2025-07-01"),
            "Description": "LUMP SUM SETTLEMENT bulk transfer",
            "Ref No": "BULK-778",
            "Deposit (Cr)": round(sum(t["Deposit (Cr)"] for t in trio), 2),
            "Withdrawal (Dr)": 0.0,
        }
    )
    for t in trio:
        lines.remove(t)

    out = pd.DataFrame(lines).sort_values("Transaction Date").reset_index(drop=True)
    out["Withdrawal (Dr)"] = out["Withdrawal (Dr)"].astype(float)
    out["Deposit (Cr)"] = out["Deposit (Cr)"].astype(float)
    opening = 1_450_000.0
    out["Balance"] = opening + (out["Deposit (Cr)"] - out["Withdrawal (Dr)"]).cumsum()
    out["Transaction Date"] = out["Transaction Date"].dt.strftime("%d/%m/%Y")
    out = out[["Transaction Date", "Description", "Ref No", "Withdrawal (Dr)", "Deposit (Cr)", "Balance"]]
    buf = io.StringIO()
    out.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


@st.cache_data(show_spinner=False)
def make_sample_tax_csv(n: int = 240, seed: int = 21) -> bytes:
    """A purchases-and-sales ledger carrying VAT, WHT, tax codes and supplier PINs.

    Deliberately defective in the ways a Kenyan tax health check is bought to find: the old 14% rate
    still being applied, VAT charged on zero-rated supplies, standard-rated supplies raised without
    VAT, net + VAT that does not foot to gross, service expenses suffered without withholding,
    malformed and placeholder PINs, one PIN used by two suppliers, gaps and a repeat in the document
    series, an invoice dated before its neighbours, and a month with no activity at all.
    """
    r = np.random.default_rng(seed)
    suppliers = [
        "Savannah Logistics Ltd", "Lake Basin Foods Ltd", "Rift Hardware Supplies",
        "Coastline Freight Services", "Highland Pharmacy Ltd", "Mara Catering Services",
        "Njoroge Advocates", "Omondi & Co Auditors", "Kapital Facilities Management",
        "Parklands Property Rentals",
    ]
    clients = ["Savannah Traders", "Athi River Works Project", "Mombasa Port Agency",
               "Nairobi County Health", "Recurring Subscription Revenue", "Westminister Partners"]
    services = ["professional fees", "consultancy", "rent", "maintenance services", "audit fees", "cleaning"]
    pins = {
        "Savannah Logistics Ltd": "P051623190Y", "Lake Basin Foods Ltd": "A000123456K",
        "Rift Hardware Supplies": "A012987654L", "Coastline Freight Services": "P052988771B",
        "Highland Pharmacy Ltd": "A004567821M", "Mara Catering Services": "P053311209C",
        "Njoroge Advocates": "A002334455Z", "Omondi & Co Auditors": "P051998877D",
        "Kapital Facilities Management": "A006778899F", "Parklands Property Rentals": "P051446622H",
    }
    # September is skipped on purpose: a silent period is a filing question, not a missing row.
    months = [m for m in pd.period_range("2025-04-01", "2026-03-01", freq="M") if str(m) != "2025-09"]

    rows = []
    for _ in range(n):
        purchase = bool(r.random() < 0.45)
        payee = str(r.choice(suppliers if purchase else clients))
        month = months[int(r.integers(len(months)))]
        day = month.to_timestamp() + pd.Timedelta(days=int(r.integers(1, month.days_in_month)))
        code = "Standard Rated" if r.random() < 0.82 else str(r.choice(["Zero Rated", "Exempt"]))
        net = round(float(r.choice([18_500, 42_000, 76_500, 118_000, 240_000, 385_000])) * (1 + r.random()), 2)
        vat = round(net * (0.16 if code == "Standard Rated" else 0.0), 2)
        wht, service = 0.0, ""
        if purchase and r.random() < 0.4:
            service = str(r.choice(services))
            expected = round(net * (0.08 if service == "rent" else 0.05), 2)
            # Most service expenses are suffered with no withholding at all; a few are done properly.
            wht = expected if r.random() < 0.3 else 0.0
        rows.append({
            "_day": day,
            "Type": "Purchase" if purchase else "Sales",
            "Supplier / Customer": payee,
            "Narration": f"{payee} — {service or 'goods supplied'}" if purchase else f"Invoice to {payee}",
            "Tax Code": code,
            "Payee KRA PIN": pins.get(payee, "") if purchase else "",
            "Net Amount": net,
            "VAT Amount": vat,
            "WHT Amount": wht,
        })

    rows.sort(key=lambda x: x["_day"])
    counters = {"Purchase": 20000, "Sales": 10000}
    for k, row in enumerate(rows):
        counters[row["Type"]] += 1
        if k % 27 == 13:  # a block of numbers that never appears in the file
            counters[row["Type"]] += 3
        row["Invoice No"] = f"WST/{'PUR' if row['Type'] == 'Purchase' else 'SAL'}/{counters[row['Type']]:06d}"

    df = pd.DataFrame(rows)
    df["Date"] = df["_day"].dt.strftime("%d/%m/%Y")
    df["Gross Amount"] = (df["Net Amount"] + df["VAT Amount"]).round(2)

    std = df.index[(df["Tax Code"] == "Standard Rated") & (df["Net Amount"] > 0)]
    pur = df.index[df["Type"] == "Purchase"]

    def pick(count, pool):
        return r.choice(pool, size=min(count, len(pool)), replace=False)

    stale = pick(len(std) // 11, std)                      # still on the pre-July-2022 rate
    df.loc[stale, "VAT Amount"] = (df.loc[stale, "Net Amount"] * 0.14).round(2)
    df.loc[stale, "Gross Amount"] = df.loc[stale, "Net Amount"] + df.loc[stale, "VAT Amount"]
    zeroish = df.index[df["Tax Code"] != "Standard Rated"]
    misfiled = pick(max(3, len(zeroish) // 8), zeroish)    # VAT charged where none is chargeable
    df.loc[misfiled, "VAT Amount"] = (df.loc[misfiled, "Net Amount"] * 0.16).round(2)
    df.loc[misfiled, "Gross Amount"] = df.loc[misfiled, "Net Amount"] + df.loc[misfiled, "VAT Amount"]
    uncharged = pick(len(std) // 14, std)                  # standard-rated supply, no VAT raised
    df.loc[uncharged, "VAT Amount"] = 0.0
    df.loc[uncharged, "Gross Amount"] = df.loc[uncharged, "Net Amount"]
    df.loc[df.index[:4], "Gross Amount"] = df.loc[df.index[:4], "Net Amount"] + df.loc[df.index[:4], "VAT Amount"] + 2_400.0

    note = pur[0]                                          # a credit note, negative throughout
    df.loc[note, ["Net Amount", "VAT Amount", "Gross Amount"]] = [-185_000.0, -29_600.0, -214_600.0]

    # Identity defects on supplier lines.
    df.loc[pur[3], "Payee KRA PIN"] = "P000000000A"
    df.loc[pur[5], "Payee KRA PIN"] = "0P51623190"
    df.loc[pur[7], "Payee KRA PIN"] = "A0012345"
    df.loc[pur[9], "Supplier / Customer"] = "Mara Supplies Ltd"
    df.loc[pur[9], "Payee KRA PIN"] = pins["Highland Pharmacy Ltd"]

    # Sequence defects inside the purchase series.
    df.loc[pur[14], "Invoice No"] = df.loc[pur[13], "Invoice No"]
    df.loc[pur[20], "Date"] = (df.loc[pur[20], "_day"] - pd.DateOffset(months=4)).strftime("%d/%m/%Y")

    columns = ["Date", "Invoice No", "Type", "Supplier / Customer", "Narration", "Tax Code",
               "Payee KRA PIN", "Net Amount", "VAT Amount", "Gross Amount", "WHT Amount"]
    buf = io.StringIO()
    df[columns].to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")
