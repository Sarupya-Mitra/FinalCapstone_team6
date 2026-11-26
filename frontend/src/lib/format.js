// Formatting helpers. The backend sends Decimal values as strings ("1000.00")
// and dates as ISO strings.

export function toNumber(v) {
  if (v === null || v === undefined || v === '') return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

export function formatMoney(value, currency = 'USD') {
  const n = toNumber(value)
  if (n === null) return '—'
  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency: currency || 'USD',
      minimumFractionDigits: 2,
    }).format(n)
  } catch {
    return `${n.toFixed(2)} ${currency || ''}`.trim()
  }
}

export function formatNumber(value, digits = 2) {
  const n = toNumber(value)
  if (n === null) return '—'
  return n.toLocaleString(undefined, { maximumFractionDigits: digits })
}

export function formatDate(value) {
  if (!value) return '—'
  // Plain dates ("2026-11-15") would shift timezone if parsed as UTC.
  const d = /^\d{4}-\d{2}-\d{2}$/.test(value) ? new Date(`${value}T00:00:00`) : new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

export function formatDateTime(value) {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function formatBytes(bytes) {
  const n = toNumber(bytes)
  if (n === null) return '—'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(2)} MB`
}

export function humanize(s) {
  if (!s) return ''
  return s.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())
}

// Correction field names: "total_amount" -> "Total amount",
// "items[14].line_total" -> "Item #14 · line total"
export function fieldLabel(name) {
  if (!name) return ''
  const m = /^items?\[(\d+)\](?:\.(\w+))?$/.exec(name)
  if (m) return `Item #${m[1]}${m[2] ? ` · ${humanize(m[2]).toLowerCase()}` : ''}`
  return humanize(name)
}

export const INVOICE_STATUSES = [
  'uploaded',
  'extracted',
  'pending_approval',
  'discrepancy',
  'approved',
  'rejected',
]

export const CHECK_LABELS = {
  duplicate: 'Duplicate invoice',
  line_total: 'Line totals',
  invoice_total: 'Invoice total',
  missing_field: 'Required fields',
  text_readable: 'PDF text readable',
}
