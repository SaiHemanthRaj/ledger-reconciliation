"""Reconcile synthetic ledger and settlement CSVs as of an explicit business date."""

import argparse
import csv
import hashlib
import json
import os
import sqlite3
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ["row_id", "order_id", "order_date", "currency", "amount_cents"]
PAYMENTS = ["row_id", "settlement_id", "order_id", "settled_date", "currency", "amount_cents"]
STATUSES = {
    "matched",
    "pending",
    "duplicate_ledger",
    "duplicate_settlement",
    "currency_mismatch",
    "amount_mismatch",
    "missing_settlement",
    "unexpected_settlement",
}


def read_input(path, fields, day_field):
    result = []
    row_ids = set()
    with Path(path).open(newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != fields:
            raise ValueError("Unexpected input schema")
        for line, r in enumerate(reader, 2):
            if any(not r.get(k) for k in fields) or None in r:
                raise ValueError(f"Missing or extra field on line {line}")
            if r["row_id"] in row_ids:
                raise ValueError("row_id must be unique")
            row_ids.add(r["row_id"])
            date.fromisoformat(r[day_field])
            if (
                len(r["currency"]) != 3
                or not r["currency"].isalpha()
                or r["currency"] != r["currency"].upper()
            ):
                raise ValueError("Currency must be three uppercase letters")
            amount = int(r["amount_cents"])
            if amount < 0 or amount > 1_000_000_000:
                raise ValueError("Invalid amount_cents")
            r["amount_cents"] = amount
            result.append(tuple(r[k] for k in fields))
    return result


def reconcile(ledger, settlements, cutoff, grace_days=2, tolerance_cents=0):
    cutoff = date.fromisoformat(cutoff)
    if grace_days < 0 or tolerance_cents < 0:
        raise ValueError("Parameters must be nonnegative")
    ledger_rows = read_input(ledger, LEDGER, "order_date")
    settlement_rows = read_input(settlements, PAYMENTS, "settled_date")
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    try:
        db.executescript("""CREATE TABLE ledger(row_id TEXT PRIMARY KEY,order_id TEXT,order_date TEXT,currency TEXT,amount_cents INTEGER);
         CREATE TABLE settlements(row_id TEXT PRIMARY KEY,settlement_id TEXT,order_id TEXT,settled_date TEXT,currency TEXT,amount_cents INTEGER);""")
        # Future rows are excluded consistently on both sides. Input counts and exclusion counts remain visible.
        included_l = [r for r in ledger_rows if r[2] <= cutoff.isoformat()]
        included_p = [r for r in settlement_rows if r[3] <= cutoff.isoformat()]
        db.executemany("INSERT INTO ledger VALUES (?,?,?,?,?)", included_l)
        db.executemany("INSERT INTO settlements VALUES (?,?,?,?,?,?)", included_p)
        params = {
            "cutoff": cutoff.isoformat(),
            "grace_days": grace_days,
            "tolerance_cents": tolerance_cents,
        }
        rows = [dict(r) for r in db.execute((ROOT / "sql/reconcile.sql").read_text(), params)]
        counts = Counter(r["status"] for r in rows)
        if set(counts) - STATUSES:
            raise RuntimeError("Unknown status")
        currencies = {}
        # Financial exposure never combines currencies and excludes ambiguous duplicates/currency mismatches.
        for r in rows:
            if r["status"] in ("missing_settlement", "amount_mismatch"):
                c = r["ledger_currency"]
                currencies[c] = currencies.get(c, 0) + r["difference_cents"]
        summary = {
            "cutoff": cutoff.isoformat(),
            "grace_days": grace_days,
            "tolerance_cents": tolerance_cents,
            "input_ledger_rows": len(ledger_rows),
            "input_settlement_rows": len(settlement_rows),
            "excluded_future_ledger": len(ledger_rows) - len(included_l),
            "excluded_future_settlements": len(settlement_rows) - len(included_p),
            "orders_reviewed": len(rows),
            "status_counts": dict(sorted(counts.items())),
            "exceptions": sum(n for s, n in counts.items() if s not in ("matched", "pending")),
            "unambiguous_difference_cents_by_currency": currencies,
            "inputs_sha256": {
                Path(p).name: hashlib.sha256(Path(p).read_bytes()).hexdigest()
                for p in [ledger, settlements]
            },
        }
        return summary, rows
    finally:
        db.close()


def write_outputs(summary, rows, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    with (output / "exceptions.csv").open("w", newline="") as f:
        fields = list(rows[0]) if rows else ["order_id", "status"]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(r for r in rows if r["status"] not in ("matched", "pending"))
    with (output / "all_orders.csv").open("w", newline="") as f:
        fields = list(rows[0]) if rows else ["order_id", "status"]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ledger", default=str(ROOT / "data/ledger.csv"))
    p.add_argument("--settlements", default=str(ROOT / "data/settlements.csv"))
    p.add_argument("--cutoff", required=True)
    p.add_argument("--grace-days", type=int, default=2)
    p.add_argument("--tolerance-cents", type=int, default=0)
    p.add_argument("--output", default=os.getenv("RECON_OUTPUT", "artifacts"))
    p.add_argument("--fail-on-exceptions", action="store_true")
    args = p.parse_args()
    summary, rows = reconcile(
        args.ledger, args.settlements, args.cutoff, args.grace_days, args.tolerance_cents
    )
    write_outputs(summary, rows, args.output)
    print(json.dumps(summary, indent=2))
    if args.fail_on_exceptions and summary["exceptions"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
