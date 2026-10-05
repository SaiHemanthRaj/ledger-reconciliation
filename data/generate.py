from pathlib import Path
import csv
import random

ROOT = Path(__file__).resolve().parents[1]
rng = random.Random(43)
ledger = []
payments = []
for i in range(1, 1001):
    amount = rng.randint(1, 50) * 100
    order = f"O{i:04}"
    day = "2026-09-29" if i > 990 else "2026-09-01"
    ledger.append([f"L{i:04}", order, day, "USD", amount])
    if i <= 950:
        payments.append([f"P{i:04}", f"S{i:04}", order, "2026-09-03", "USD", amount])
    elif i <= 960:
        payments.append([f"P{i:04}", f"S{i:04}", order, "2026-09-03", "USD", amount + 100])
    elif i <= 970:
        payments.extend(
            [
                [f"P{i:04}a", f"S{i:04}a", order, "2026-09-03", "USD", amount // 2],
                [f"P{i:04}b", f"S{i:04}b", order, "2026-09-03", "USD", amount - amount // 2],
            ]
        )
    elif i <= 980:
        payments.append([f"P{i:04}", f"S{i:04}", order, "2026-09-03", "EUR", amount])
for i in range(6, 14):
    r = ledger[i - 1].copy()
    r[0] += "dup"
    ledger.append(r)
for i in range(5):
    r = payments[i].copy()
    r[0] += "dup"
    payments.append(r)
for i in range(1, 11):
    payments.append([f"PX{i:03}", f"SX{i:03}", f"X{i:03}", "2026-09-03", "USD", 1000])
for name, fields, rows in [
    ("ledger.csv", ["row_id", "order_id", "order_date", "currency", "amount_cents"], ledger),
    (
        "settlements.csv",
        ["row_id", "settlement_id", "order_id", "settled_date", "currency", "amount_cents"],
        payments,
    ),
]:
    p = ROOT / "data" / name
    p.parent.mkdir(exist_ok=True)
    with p.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(fields)
        w.writerows(rows)
