# Matching decisions

The business key is order_id, not CSV row_id. Settlement IDs identify installment transactions.
Window counts diagnose repeated business keys. ROW_NUMBER produces a diagnostic representative record
so duplicates do not inflate the displayed sum; any duplicated settlement ID is flagged for each involved
order, including when conflicting rows name different orders.

Classification precedence is unexpected settlement, duplicate ledger, duplicate settlement, currency
mismatch, pending/missing settlement, amount mismatch, then matched. This deliberately yields one
primary status; it is not an all-causes exception engine. A missing ledger cannot supply an expected currency.

Amounts in duplicate rows are not authoritative. The exposure summary includes only unambiguous missing
or mismatched amounts, with a separate total per currency. The net can include overpayments as negative
differences. No currency conversions are performed.

The grace boundary is inclusive: at a September 30 cutoff, an unpaid September 28 order is pending with
a two-day grace period, while a September 27 order is overdue. Future ledger and settlement rows are
excluded independently and their counts remain visible.

A tolerance of one cent can absorb a one-cent discrepancy, but the demo defaults to exact equality.
Negative values are rejected. Refunds and fees need separate business event types before they can be modeled.

All fixtures are deliberately synthetic. This is an explainable data quality workflow, not a claim of
financial reconciliation work for an employer or a substitute for accounting controls.
