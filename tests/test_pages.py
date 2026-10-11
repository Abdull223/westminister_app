"""Page sweep for the Westminister Intelligence Suite, driven by Streamlit's AppTest harness.

    python tests/test_pages.py

Every page is run against the sample Kenya ledger, with the sample bank statement attached
where the page consumes one. A failure prints the raised exception so the trace is recoverable.
"""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest

from core.data import fingerprint, make_sample_csv, make_sample_statement_csv

# AppTest cannot register a Custom Component v2, so the pen pad is stubbed out: the
# signature is optional in the report, and the rest of the sign-off logic still runs.
import core.signature_pad as _sig

_sig.signature_pad = lambda *args, **kwargs: None

TIMEOUT = 600
PAGES = ("dashboard", "pivot", "findings", "forensics", "quarantine", "signoff")


def _seeded(page: str, *, statement: bool = False, recon: dict | None = None) -> AppTest:
    at = AppTest.from_file(str(ROOT / "app_pages" / f"{page}.py"), default_timeout=TIMEOUT)
    at.session_state["raw_bytes"] = make_sample_csv()
    at.session_state["source_name"] = "sample_kenya_ledger.csv"
    at.session_state["clean_opts"] = {}
    if statement:
        at.session_state["stmt_bytes"] = make_sample_statement_csv()
        at.session_state["stmt_name"] = "sample_bank_statement.csv"
    if recon is not None:
        at.session_state["recon_report"] = recon
    return at


def _fail(page: str, at: AppTest, detail: str) -> None:
    raise AssertionError(f"[{page}] {detail}\n" + "\n".join(str(e.value)[:600] for e in at.exception))


def _cert(at: AppTest) -> bytes | None:
    """AppTest's session-state proxy has no .get(), and an absent key raises."""
    return at.session_state["cert_pdf"] if "cert_pdf" in at.session_state else None


def _recon_payload() -> dict:
    """Run the reconciliation page once and keep the snapshot it publishes for the report."""
    at = _seeded("reconcile", statement=True)
    at.run()
    if at.exception:
        _fail("reconcile", at, "page raised while producing the snapshot")
    return dict(at.session_state["recon_report"])


def test_pages_render() -> None:
    for page in PAGES:
        at = _seeded(page)
        at.run()
        if at.exception:
            _fail(page, at, "page raised")
        assert at.title[0].value, f"[{page}] rendered no title"
        print(f"  {page:11} ok · {len(at.error)} error box(es)")


def test_reconciliation_page() -> None:
    at = _seeded("reconcile", statement=True)
    at.run()
    if at.exception:
        _fail("reconcile", at, "page raised")
    if any("does NOT foot" in e.value for e in at.error):
        _fail("reconcile", at, "bridge did not foot")

    report = dict(at.session_state["recon_report"])
    stats = report["stats"]
    assert report["ledger_hash"] == fingerprint(make_sample_csv()), "recon bound to the wrong ledger"
    assert stats["foots"], f"residual {stats['residual']} — the bridge must foot to zero"
    assert stats["matched_bank"] > 0 and stats["match_rate"] > 95, f"tie-up too low: {stats['match_rate']}"
    # Defects planted in the sample statement that the engine is expected to surface.
    assert stats["bank_only_lines"] >= 3, "bank charges and withdrawals should read as unbooked"
    assert stats["ledger_only_lines"] >= 1, "unbanked invoices should survive pairing"
    assert stats["duplicate_lines"] == 1, "the planted double payment should be caught"
    assert report["bridge"][-1][1] == stats["bank_total"], "the bridge must close on the bank's own total"
    assert len(report["findings"]) >= 4, "findings narrative missing"
    print(f"  reconcile   ok · {stats['matched_bank']}/{stats['bank_lines']} tied, "
          f"bridge {stats['residual']:.2f}, {stats['exceptions']} exception(s)")


def test_signoff_embeds_reconciliation(recon: dict) -> None:
    at = _seeded("signoff", recon=recon)
    at.run()
    if at.exception:
        _fail("sign-off", at, "page raised")
    button = next((b for b in at.button if b.label.startswith("Generate certified PDF")), None)
    assert button is not None, "generate button missing"
    assert not any(b.proto.disabled for b in at.button), "an unqualified report should be issuable directly"
    button.click().run()
    if at.exception:
        _fail("sign-off", at, "PDF generation raised")
    pdf = _cert(at)
    assert pdf and pdf[:5] == b"%PDF-", "no PDF produced"
    assert len(pdf) > 20_000, f"PDF suspiciously small: {len(pdf)} bytes"
    print(f"  sign-off    ok · {len(pdf):,} byte certified report with the reconciliation section")


def test_unfooted_bridge_qualifies_the_report(recon: dict) -> None:
    broken = {**recon, "stats": {**recon["stats"], "foots": False, "residual": 123_456.75}}
    at = _seeded("signoff", recon=broken)
    at.run()
    if at.exception:
        _fail("bridge gate", at, "page raised")
    assert at.checkbox, "the qualification acknowledgement is missing"
    assert all(b.proto.disabled for b in at.button if b.label.startswith("Generate certified PDF")), \
        "a reconciliation that does not foot must not be certifiable"
    assert any("does not foot" in c.value.lower() for c in at.caption), "the limitation was not disclosed"

    at.checkbox[0].check().run()
    next(b for b in at.button if b.label.startswith("Generate certified PDF")).click().run()
    pdf = _cert(at)
    assert pdf and pdf[:5] == b"%PDF-", "an acknowledged qualified report should still be issued"
    print("  bridge gate ok · non-footing bridge blocks, then qualifies the certificate")


def test_empty_states() -> None:
    shell = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=TIMEOUT)
    shell.run()
    if shell.exception:
        _fail("entry point", shell, "shell raised")

    at = AppTest.from_file(str(ROOT / "app_pages" / "reconcile.py"), default_timeout=TIMEOUT)
    at.run()
    if at.exception:
        _fail("reconcile", at, "no-ledger state raised")

    at = _seeded("reconcile")
    at.run()
    if at.exception:
        _fail("reconcile", at, "no-statement state raised")
    assert not at.error, "a missing statement is a prompt, not an error"
    assert any(b.label == "Load sample bank statement" for b in at.button), "no way to start without a statement"
    print("  empty state ok")


if __name__ == "__main__":
    print("→ pages render")
    test_pages_render()
    print("→ reconciliation")
    test_reconciliation_page()
    payload = _recon_payload()
    print("→ sign-off")
    test_signoff_embeds_reconciliation(payload)
    print("→ bridge gate")
    test_unfooted_bridge_qualifies_the_report(payload)
    print("→ empty states")
    test_empty_states()
    print("\nAll page checks passed.")
