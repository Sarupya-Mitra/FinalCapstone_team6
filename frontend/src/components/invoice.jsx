// Invoice-specific building blocks shared by the clerk, approver and auditor views.
import { useEffect, useState } from 'react'
import { vendorsApi } from '../api/endpoints'
import {
  CHECK_LABELS,
  fieldLabel,
  formatBytes,
  formatDate,
  formatDateTime,
  formatMoney,
  formatNumber,
  humanize,
  toNumber,
} from '../lib/format'
import { EmptyState, KeyValue, StatusBadge, Table } from './ui'

/* ---------------------------------------------------------------- Vendors lookup */

let vendorCache = null
let vendorPromise = null

export function invalidateVendors() {
  vendorCache = null
  vendorPromise = null
}

// Loads the vendor list once and shares it between components.
export function useVendors() {
  const [vendors, setVendors] = useState(vendorCache)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (vendorCache) return
    vendorPromise ||= vendorsApi.list().then((v) => (vendorCache = v))
    vendorPromise.then(setVendors).catch((e) => {
      vendorPromise = null
      setError(e)
    })
  }, [])

  const byId = Object.fromEntries((vendors || []).map((v) => [v.vendor_id, v]))
  return { vendors: vendors || [], byId, loading: !vendors && !error, error }
}

export function VendorName({ id, byId }) {
  const v = byId?.[id]
  return v ? v.vendor_name : `Vendor #${id}`
}

/* ---------------------------------------------------------------- Invoice summary */

export function InvoiceSummary({ invoice, vendorName }) {
  if (!invoice) return null
  return (
    <KeyValue
      cols={4}
      items={[
        ['Vendor', vendorName],
        ['Invoice number', invoice.invoice_number || '—'],
        ['Invoice date', formatDate(invoice.invoice_date)],
        ['Due date', formatDate(invoice.due_date)],
        ['Currency', invoice.currency],
        ['Subtotal', formatMoney(invoice.subtotal, invoice.currency)],
        ['Tax', formatMoney(invoice.tax_amount, invoice.currency)],
        ['Total', <strong key="t" className="font-bold">{formatMoney(invoice.total_amount, invoice.currency)}</strong>],
        ['File', `${invoice.original_filename} (${formatBytes(invoice.file_size_bytes)})`],
        ['Uploaded', formatDateTime(invoice.created_at)],
        ['Last updated', formatDateTime(invoice.updated_at)],
        [
          'Duplicate of',
          invoice.duplicate_of_invoice_id ? (
            <span className="text-error font-normal">Invoice #{invoice.duplicate_of_invoice_id}</span>
          ) : (
            'None'
          ),
        ],
      ]}
    />
  )
}

/* ---------------------------------------------------------------- Line items */

export function ItemsTable({ items, currency }) {
  const rows = [...(items || [])].sort((a, b) => a.line_no - b.line_no)
  const sum = rows.reduce((acc, it) => acc + (toNumber(it.line_total) ?? (toNumber(it.quantity) || 0) * (toNumber(it.unit_price) || 0)), 0)
  return (
    <>
      <Table
        rowKey={(r) => r.item_id ?? r.line_no}
        rows={rows}
        empty={<EmptyState title="No line items">No line items were extracted or entered for this invoice.</EmptyState>}
        columns={[
          { key: 'line_no', header: '#', className: 'text-muted w-12' },
          { key: 'item_name', header: 'Item' },
          { key: 'quantity', header: 'Qty', align: 'right', render: (r) => formatNumber(r.quantity, 3) },
          { key: 'unit_price', header: 'Unit price', align: 'right', render: (r) => formatMoney(r.unit_price, currency) },
          { key: 'line_total', header: 'Line total', align: 'right', render: (r) => formatMoney(r.line_total, currency) },
          ...(rows.some((r) => r.source)
            ? [{ key: 'source', header: 'Source', render: (r) => <StatusBadge status={r.source} label={r.source === 'ai' ? 'AI' : 'Manual'} /> }]
            : []),
        ]}
      />
      {rows.length > 0 && (
        <p className="mt-3 text-right text-body-sm text-muted">
          Sum of line items: <span className="font-bold text-ink">{formatMoney(sum, currency)}</span>
        </p>
      )}
    </>
  )
}

/* ---------------------------------------------------------------- Validation checks */

const CHECK_ICON = {
  pass: (
    <svg viewBox="0 0 20 20" className="size-5 text-success" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M4 10.5l4 4 8-9" />
    </svg>
  ),
  fail: (
    <svg viewBox="0 0 20 20" className="size-5 text-error" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M5 5l10 10M15 5L5 15" />
    </svg>
  ),
  warning: (
    <svg viewBox="0 0 20 20" className="size-5 text-warning" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M10 4v8M10 15v1" />
    </svg>
  ),
}

export function ChecksList({ checks }) {
  if (!checks?.length) {
    return <EmptyState title="No checks yet">Validation checks run when the clerk submits the invoice.</EmptyState>
  }
  return (
    <ul className="border border-hairline divide-y divide-hairline bg-canvas">
      {checks.map((c, i) => (
        <li key={c.check_id ?? i} className="flex gap-4 px-5 py-4">
          <span className="mt-0.5 shrink-0">{CHECK_ICON[c.result]}</span>
          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap items-center gap-3">
              <p className="text-title-sm">{CHECK_LABELS[c.check_type] || humanize(c.check_type)}</p>
              <StatusBadge status={c.result} />
            </div>
            {c.details && <p className="mt-1 text-body-sm text-body break-words">{c.details}</p>}
            {c.checked_at && <p className="mt-1 caption text-muted-soft">{formatDateTime(c.checked_at)}</p>}
          </div>
        </li>
      ))}
    </ul>
  )
}

export function checkCounts(checks = []) {
  return {
    pass: checks.filter((c) => c.result === 'pass').length,
    fail: checks.filter((c) => c.result === 'fail').length,
    warning: checks.filter((c) => c.result === 'warning').length,
  }
}

/* ---------------------------------------------------------------- AI summary */

export function AiSummary({ extraction }) {
  if (!extraction) return null
  return (
    <div className="border border-hairline bg-surface-card p-6">
      <div className="flex flex-wrap items-center gap-3 mb-3">
        <p className="label-upper text-primary">AI extraction</p>
        <StatusBadge status={extraction.status} />
        <span className="caption text-muted">
          {[extraction.provider, extraction.model_name].filter(Boolean).join(' · ')}
          {extraction.duration_ms != null && ` · ${(extraction.duration_ms / 1000).toFixed(1)}s`}
          {extraction.created_at && ` · ${formatDateTime(extraction.created_at)}`}
        </span>
      </div>
      {extraction.ai_summary ? (
        <p className="text-body-md text-body-strong whitespace-pre-line">{extraction.ai_summary}</p>
      ) : (
        <p className="text-body-sm text-muted">No AI summary was recorded for this run.</p>
      )}
      {extraction.error_message && <p className="mt-3 text-body-sm text-error">{extraction.error_message}</p>}
    </div>
  )
}

/* ---------------------------------------------------------------- Audit history */

// Merges corrections, extraction runs and approvals into one timeline.
export function HistoryTimeline({ corrections = [], extractions = [], approvals = [] }) {
  const events = [
    ...extractions.map((e) => ({
      at: e.created_at,
      key: `x${e.run_id}`,
      kind: 'AI extraction',
      badge: <StatusBadge status={e.status} />,
      body: (
        <>
          <p className="text-body-sm text-muted">
            {[e.provider, e.model_name].filter(Boolean).join(' · ') || 'Unknown model'}
            {e.duration_ms != null && ` · ${(e.duration_ms / 1000).toFixed(1)}s`}
          </p>
          {e.ai_summary && <p className="mt-1 text-body-sm text-body whitespace-pre-line">{e.ai_summary}</p>}
          {e.error_message && <p className="mt-1 text-body-sm text-error">{e.error_message}</p>}
        </>
      ),
    })),
    ...corrections.map((c) => ({
      at: c.corrected_at,
      key: `c${c.correction_id}`,
      kind: 'Clerk correction',
      badge: <StatusBadge status="manual" label={`Clerk #${c.clerk_id}`} />,
      body: (
        <p className="text-body-sm text-body break-words">
          <span className="font-bold text-ink">{fieldLabel(c.field_name)}</span>:{' '}
          <span className="line-through text-muted">{shortValue(c.old_value)}</span>{' '}
          <span aria-hidden>→</span> <span className="text-ink">{shortValue(c.new_value)}</span>
        </p>
      ),
    })),
    ...approvals.map((a) => ({
      at: a.decided_at,
      key: `a${a.approval_id}`,
      kind: 'Approver decision',
      badge: <StatusBadge status={a.decision} />,
      body: (
        <p className="text-body-sm text-body whitespace-pre-line">
          <span className="text-muted">Approver #{a.approver_id}: </span>
          {a.note}
        </p>
      ),
    })),
  ].sort((a, b) => new Date(a.at) - new Date(b.at))

  if (!events.length) return <EmptyState title="No history">Nothing has been recorded for this invoice yet.</EmptyState>

  return (
    <ol className="relative border-l border-hairline-strong ml-2">
      {events.map((ev) => (
        <li key={ev.key} className="pl-6 pb-6 last:pb-0 relative">
          <span className="absolute -left-[5px] top-1.5 size-2.5 bg-primary" aria-hidden />
          <div className="flex flex-wrap items-center gap-3">
            <p className="text-title-sm">{ev.kind}</p>
            {ev.badge}
            <span className="caption text-muted">{formatDateTime(ev.at)}</span>
          </div>
          <div className="mt-1">{ev.body}</div>
        </li>
      ))}
    </ol>
  )
}

// Correction values can be JSON blobs for line items; keep them readable.
function shortValue(v) {
  if (v === null || v === undefined || v === '') return '(empty)'
  const s = String(v)
  try {
    const obj = JSON.parse(s.replace(/'/g, '"'))
    if (obj && typeof obj === 'object') {
      return obj.item_name ? `${obj.item_name} × ${obj.quantity} @ ${obj.unit_price}` : JSON.stringify(obj)
    }
  } catch {
    /* not JSON */
  }
  return s.length > 140 ? `${s.slice(0, 140)}…` : s
}
