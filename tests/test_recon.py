import csv
import pytest
from recon.run import reconcile, ROOT, LEDGER, PAYMENTS, write_outputs


def inputs(tmp_path, ledger, payments):
    paths = []
    for name, fields, rows in [
        ("ledger.csv", LEDGER, ledger),
        ("settlements.csv", PAYMENTS, payments),
    ]:
        p = tmp_path / name
        with p.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(fields)
            w.writerows(rows)
        paths.append(p)
    return paths


def test_full_demo_expected_classification():
    s, rows = reconcile(ROOT / "data/ledger.csv", ROOT / "data/settlements.csv", "2026-09-30")
    assert s["status_counts"] == {
        "matched": 947,
        "pending": 10,
        "missing_settlement": 10,
        "amount_mismatch": 10,
        "currency_mismatch": 10,
        "duplicate_ledger": 8,
        "duplicate_settlement": 5,
        "unexpected_settlement": 10,
    }
    assert s["orders_reviewed"] == 1010 and s["exceptions"] == 53
    assert s["unambiguous_difference_cents_by_currency"]["USD"] > 0


def test_split_payments_and_tolerance(tmp_path):
    ledger = [["L1", "O1", "2026-09-01", "USD", 1000]]
    p = [["P1", "S1", "O1", "2026-09-02", "USD", 400], ["P2", "S2", "O1", "2026-09-02", "USD", 599]]
    paths = inputs(tmp_path, ledger, p)
    assert reconcile(*paths, "2026-09-30")[1][0]["status"] == "amount_mismatch"
    assert reconcile(*paths, "2026-09-30", tolerance_cents=1)[1][0]["status"] == "matched"


def test_cutoff_and_grace_boundary(tmp_path):
    ledger = [
        ["L1", "O1", "2026-09-28", "USD", 1000],
        ["L2", "O2", "2026-09-27", "USD", 1000],
        ["L3", "O3", "2026-10-01", "USD", 1000],
    ]
    p = [["P1", "S1", "O1", "2026-10-01", "USD", 1000]]
    s, r = reconcile(*inputs(tmp_path, ledger, p), "2026-09-30")
    assert [x["status"] for x in r] == ["pending", "missing_settlement"]
    assert s["excluded_future_ledger"] == 1 and s["excluded_future_settlements"] == 1


def test_mixed_currency_never_compared_or_summed(tmp_path):
    ledger = [["L1", "O1", "2026-09-01", "USD", 1000]]
    p = [["P1", "S1", "O1", "2026-09-02", "USD", 500], ["P2", "S2", "O1", "2026-09-02", "EUR", 500]]
    s, r = reconcile(*inputs(tmp_path, ledger, p), "2026-09-30")
    assert r[0]["status"] == "currency_mismatch" and r[0]["difference_cents"] is None
    assert s["unambiguous_difference_cents_by_currency"] == {}


def test_duplicate_records_do_not_silently_inflate_totals(tmp_path):
    ledger = [["L1", "O1", "2026-09-01", "USD", 1000]]
    p = [
        ["P1", "S1", "O1", "2026-09-02", "USD", 1000],
        ["P2", "S1", "O1", "2026-09-02", "USD", 1000],
    ]
    _, r = reconcile(*inputs(tmp_path, ledger, p), "2026-09-30")
    assert r[0]["status"] == "duplicate_settlement" and r[0]["settled_cents"] == 1000


def test_duplicate_settlement_id_across_orders_flags_both(tmp_path):
    ledger = [["L1", "O1", "2026-09-01", "USD", 1000], ["L2", "O2", "2026-09-01", "USD", 1000]]
    p = [
        ["P1", "S1", "O1", "2026-09-02", "USD", 1000],
        ["P2", "S1", "O2", "2026-09-02", "USD", 1000],
    ]
    _, r = reconcile(*inputs(tmp_path, ledger, p), "2026-09-30")
    assert len(r) == 2 and all(x["status"] == "duplicate_settlement" for x in r)


@pytest.mark.parametrize("amount", ["-1", "abc", "1000000001"])
def test_invalid_amounts_fail(tmp_path, amount):
    with pytest.raises(ValueError):
        reconcile(*inputs(tmp_path, [["L1", "O1", "2026-09-01", "USD", amount]], []), "2026-09-30")


def test_empty_sources(tmp_path):
    s, r = reconcile(*inputs(tmp_path, [], []), "2026-09-30")
    assert s["orders_reviewed"] == 0 and s["exceptions"] == 0
    write_outputs(s, r, tmp_path / "out")
    assert (tmp_path / "out/exceptions.csv").read_text().strip() == "order_id,status"


def test_deterministic_report():
    a = reconcile(ROOT / "data/ledger.csv", ROOT / "data/settlements.csv", "2026-09-30")
    b = reconcile(ROOT / "data/ledger.csv", ROOT / "data/settlements.csv", "2026-09-30")
    assert a == b
