WITH ledger_ranked AS (
 SELECT *,COUNT(*) OVER(PARTITION BY order_id) AS ledger_rows,
 ROW_NUMBER() OVER(PARTITION BY order_id ORDER BY row_id) AS rn FROM ledger
), ledger_one AS (
 SELECT * FROM ledger_ranked WHERE rn=1
), payment_ranked AS (
 SELECT *,COUNT(*) OVER(PARTITION BY settlement_id) AS settlement_rows,
 ROW_NUMBER() OVER(PARTITION BY settlement_id ORDER BY row_id) AS rn FROM settlements
), payment_duplicates AS (
 SELECT order_id,MAX(settlement_rows) AS max_duplicate FROM payment_ranked GROUP BY order_id
), payment_sum AS (
 SELECT order_id,SUM(amount_cents) AS settled_cents,
 MIN(currency) AS currency,COUNT(DISTINCT currency) AS currency_count,
 MAX(settlement_rows) AS max_duplicate,MAX(settled_date) AS latest_settled_date,
 COUNT(*) AS settlement_count
 FROM payment_ranked WHERE rn=1 GROUP BY order_id
), keys AS (
 SELECT order_id FROM ledger_one UNION SELECT order_id FROM settlements
), classified AS (
 SELECT k.order_id,l.currency AS ledger_currency,p.currency AS settlement_currency,
 l.order_date,l.amount_cents AS expected_cents,p.settled_cents,
 CASE WHEN l.order_id IS NULL THEN NULL ELSE l.amount_cents-COALESCE(p.settled_cents,0) END AS difference_cents,
 COALESCE(l.ledger_rows,0) AS ledger_rows,COALESCE(p.settlement_count,0) AS settlement_count,
 CASE
 WHEN l.order_id IS NULL THEN 'unexpected_settlement'
 WHEN l.ledger_rows>1 THEN 'duplicate_ledger'
 WHEN d.max_duplicate>1 THEN 'duplicate_settlement'
 WHEN p.currency_count>1 OR p.currency<>l.currency THEN 'currency_mismatch'
 WHEN p.order_id IS NULL AND julianday(:cutoff)-julianday(l.order_date)<=:grace_days THEN 'pending'
 WHEN p.order_id IS NULL THEN 'missing_settlement'
 WHEN ABS(l.amount_cents-p.settled_cents)>:tolerance_cents THEN 'amount_mismatch'
 ELSE 'matched' END AS status
 FROM keys k LEFT JOIN ledger_one l ON k.order_id=l.order_id LEFT JOIN payment_sum p ON k.order_id=p.order_id
 LEFT JOIN payment_duplicates d ON k.order_id=d.order_id
)
SELECT order_id,ledger_currency,settlement_currency,order_date,expected_cents,settled_cents,
 CASE WHEN status IN ('currency_mismatch','unexpected_settlement') THEN NULL ELSE difference_cents END AS difference_cents,
 ledger_rows,settlement_count,status
FROM classified ORDER BY order_id;
