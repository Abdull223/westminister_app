"""Dataset loading and sample data generation."""

import hashlib
import io

import numpy as np
import pandas as pd
import streamlit as st


def fingerprint(raw_bytes: bytes) -> str:
    return "SHA256:" + hashlib.sha256(raw_bytes).hexdigest()[:16].upper()


@st.cache_data(ttl="1h", max_entries=8, show_spinner="Reading ledger…")
def load_dataset(raw_bytes: bytes, filename: str) -> pd.DataFrame:
    buf = io.BytesIO(raw_bytes)
    if filename.lower().endswith(".csv"):
        return pd.read_csv(buf)
    return pd.read_excel(buf)


@st.cache_data(show_spinner=False)
def make_sample_csv(n: int = 600, seed: int = 7) -> bytes:
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
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")
