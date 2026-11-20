-- Required SQL demonstrations (project spec, section 03).
-- Run with:  psql -U postgres -d invoice_processing -f backend/sql/queries.sql

-- 1) Join invoices with vendors: vendor, invoice number, date and approval status
SELECT v.vendor_name,
       i.invoice_number,
       i.invoice_date,
       i.status,
       a.decision   AS last_decision,
       a.approver_name,
       a.decided_at
FROM invoices i
JOIN vendors v ON v.vendor_id = i.vendor_id
LEFT JOIN LATERAL (
    SELECT ap.decision, apr.app_name AS approver_name, ap.decided_at
    FROM invoice_approvals ap
    JOIN approvers apr ON apr.app_id = ap.approver_id
    WHERE ap.invoice_id = i.invoice_id
    ORDER BY ap.decided_at DESC
    LIMIT 1
) a ON true
ORDER BY v.vendor_name, i.invoice_date NULLS LAST;

-- 2) Aggregate invoice totals by vendor, with pending counts
--    (flagged duplicates are counted but excluded from amounts so money isn't double-counted)
SELECT v.vendor_name,
       COUNT(i.invoice_id)                                                        AS invoice_count,
       COALESCE(SUM(i.total_amount) FILTER (WHERE i.duplicate_of_invoice_id IS NULL), 0)
                                                                                  AS total_amount,
       COALESCE(SUM(i.total_amount) FILTER (WHERE i.status = 'approved'), 0)      AS approved_amount,
       COUNT(*) FILTER (WHERE i.status IN ('uploaded', 'extracted', 'pending_approval', 'discrepancy'))
                                                                                  AS pending_count
FROM vendors v
LEFT JOIN invoices i ON i.vendor_id = v.vendor_id
GROUP BY v.vendor_name
ORDER BY v.vendor_name;

-- 3) Find invoice discrepancies: duplicate, missing-field and arithmetic failures
SELECT v.vendor_name,
       i.invoice_id,
       COALESCE(i.invoice_number, '(not extracted)') AS invoice_number,
       c.check_type,
       c.result,
       c.details,
       c.checked_at
FROM invoice_checks c
JOIN invoices i ON i.invoice_id = c.invoice_id
JOIN vendors  v ON v.vendor_id  = i.vendor_id
WHERE c.result = 'fail'
ORDER BY i.invoice_id, c.check_type;

-- Bonus: recompute line totals in SQL and compare with what the document stated
SELECT i.invoice_number,
       it.line_no,
       it.item_name,
       it.quantity * it.unit_price AS computed_total,
       it.line_total               AS stated_total
FROM invoice_items it
JOIN invoices i ON i.invoice_id = it.invoice_id
WHERE it.line_total IS DISTINCT FROM ROUND(it.quantity * it.unit_price, 2);
