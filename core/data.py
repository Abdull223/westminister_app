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
