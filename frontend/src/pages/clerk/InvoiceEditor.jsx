// Editable form for AI-extracted invoice data (PUT /invoices/{id}/review).
import { useMemo } from 'react'
import { Button, Field } from '../../components/ui'
import { formatMoney, toNumber } from '../../lib/format'

const HEADER_FIELDS = ['invoice_number', 'invoice_date', 'due_date', 'currency', 'subtotal', 'tax_amount', 'total_amount']

const str = (v) => (v === null || v === undefined ? '' : String(v))
const round2 = (n) => Math.round(n * 100) / 100
const close = (a, b) => a !== null && b !== null && Math.abs(a - b) < 0.01

let tempId = 0
const newKey = () => `new-${++tempId}`

// Server data -> form state (all strings, so inputs stay controlled).
export function toForm(invoice, items) {
  const form = Object.fromEntries(HEADER_FIELDS.map((f) => [f, str(invoice[f])]))
  form.currency = form.currency || 'USD'
  form.items = [...items]
    .sort((a, b) => a.line_no - b.line_no)
    .map((it) => ({
      key: `item-${it.item_id}`,
      item_id: it.item_id,
      line_no: it.line_no,
      item_name: str(it.item_name),
      quantity: str(it.quantity),
      unit_price: str(it.unit_price),
      line_total: str(it.line_total),
      source: it.source,
    }))
  return form
}

// Form state -> InvoiceCorrectionSubmit payload.
export function toPayload(form) {
  const dec = (v) => (v === '' ? null : String(v).trim())
  return {
    invoice_number: form.invoice_number.trim() || null,
    invoice_date: form.invoice_date || null,
    due_date: form.due_date || null,
    currency: form.currency.trim().toUpperCase(),
    subtotal: dec(form.subtotal),
    tax_amount: dec(form.tax_amount),
    total_amount: dec(form.total_amount),
    items: form.items.map((it) => ({
      item_id: it.item_id ?? null,
      line_no: it.line_no,
      item_name: it.item_name.trim(),
      quantity: dec(it.quantity),
      unit_price: dec(it.unit_price),
      line_total: dec(it.line_total),
    })),
  }
}

// Mirrors the backend's pydantic rules so most errors are caught before saving.
export function validateForm(form) {
  const errors = {}
  const num = (v) => (v === '' ? null : Number(v))
  if (!/^[A-Za-z]{3}$/.test(form.currency.trim())) errors.currency = 'Use a 3-letter code, e.g. USD'
  if (form.invoice_number.length > 100) errors.invoice_number = 'At most 100 characters'
  for (const f of ['subtotal', 'tax_amount', 'total_amount']) {
    const n = num(form[f])
    if (n !== null && (Number.isNaN(n) || n < 0)) errors[f] = 'Must be a number ≥ 0'
  }
  if (form.invoice_date && form.due_date && form.due_date < form.invoice_date) {
    errors.due_date = 'Due date is before the invoice date'
  }
  form.items.forEach((it) => {
    const e = {}
    if (!it.item_name.trim()) e.item_name = 'Required'
    else if (it.item_name.length > 300) e.item_name = 'Too long'
    const q = num(it.quantity)
    if (q === null || Number.isNaN(q) || q <= 0) e.quantity = '> 0'
    const p = num(it.unit_price)
    if (p === null || Number.isNaN(p) || p < 0) e.unit_price = '≥ 0'
    const t = num(it.line_total)
    if (t !== null && (Number.isNaN(t) || t < 0)) e.line_total = '≥ 0'
    if (Object.keys(e).length) errors[it.key] = e
  })
  return errors
}

export default function InvoiceEditor({ form, setForm, errors, disabled, showErrors }) {
  const setField = (f) => (e) => setForm((s) => ({ ...s, [f]: e.target.value }))
  const setItem = (key, f, v) =>
    setForm((s) => ({ ...s, items: s.items.map((it) => (it.key === key ? { ...it, [f]: v } : it)) }))
  const addItem = () =>
    setForm((s) => ({
      ...s,
      items: [
        ...s.items,
        {
          key: newKey(),
          item_id: null,
          line_no: Math.max(0, ...s.items.map((i) => i.line_no)) + 1,
          item_name: '',
          quantity: '1',
          unit_price: '',
          line_total: '',
          source: 'manual',
        },
      ],
    }))
  const removeItem = (key) => setForm((s) => ({ ...s, items: s.items.filter((it) => it.key !== key) }))

  const err = (f) => (showErrors ? errors[f] : undefined)
  const cur = form.currency?.length === 3 ? form.currency.toUpperCase() : 'USD'

  // Live arithmetic, the same checks the backend runs on submit.
  const math = useMemo(() => {
    const lines = form.items.map((it) => {
      const q = toNumber(it.quantity)
      const p = toNumber(it.unit_price)
      const expected = q !== null && p !== null ? round2(q * p) : null
      const actual = toNumber(it.line_total)
      return { key: it.key, expected, mismatch: actual !== null && expected !== null && !close(actual, expected) }
    })
    const lineSum = round2(
      form.items.reduce((a, it, i) => a + (toNumber(it.line_total) ?? lines[i].expected ?? 0), 0)
    )
    const subtotal = toNumber(form.subtotal)
    const tax = toNumber(form.tax_amount)
    const total = toNumber(form.total_amount)
    const expectedTotal = subtotal !== null ? round2(subtotal + (tax ?? 0)) : null
    return {
      lines: Object.fromEntries(lines.map((l) => [l.key, l])),
      lineSum,
      subtotalMismatch: subtotal !== null && form.items.length > 0 && !close(subtotal, lineSum),
      expectedTotal,
      totalMismatch: total !== null && expectedTotal !== null && !close(total, expectedTotal),
    }
  }, [form])

  const inputCls = (bad) => `field field-sm ${bad ? 'field-error' : ''}`

  return (
    <div className="space-y-10">
      {/* Header fields */}
      <div>
        <h3 className="text-title-lg mb-5">Invoice details</h3>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
          <Field label="Invoice number" error={err('invoice_number')}>
            <input className={inputCls(err('invoice_number'))} value={form.invoice_number} onChange={setField('invoice_number')} disabled={disabled} placeholder="Missing" />
          </Field>
          <Field label="Invoice date" error={err('invoice_date')}>
            <input type="date" className={inputCls(err('invoice_date'))} value={form.invoice_date} onChange={setField('invoice_date')} disabled={disabled} />
          </Field>
          <Field label="Due date" error={err('due_date')}>
            <input type="date" className={inputCls(err('due_date'))} value={form.due_date} onChange={setField('due_date')} disabled={disabled} />
          </Field>
          <Field label="Currency" error={err('currency')}>
            <input className={`${inputCls(err('currency'))} uppercase`} maxLength={3} value={form.currency} onChange={setField('currency')} disabled={disabled} />
          </Field>
        </div>
      </div>

      {/* Line items */}
      <div>
        <div className="flex items-end justify-between gap-4 mb-5">
          <h3 className="text-title-lg">Line items</h3>
          <Button type="button" size="sm" variant="secondary" onClick={addItem} disabled={disabled}>
            + Add line
          </Button>
        </div>

        {form.items.length === 0 ? (
          <div className="bg-surface-card py-10 text-center text-body-sm text-muted">
            No line items. Add the items listed on the invoice.
          </div>
        ) : (
          <div className="overflow-x-auto border border-hairline">
            <table className="w-full min-w-[760px] text-body-sm">
              <thead>
                <tr className="bg-surface-soft border-b border-hairline">
                  {['#', 'Item', 'Qty', 'Unit price', 'Line total', ''].map((h, i) => (
                    <th key={i} className={`label-upper !text-[11px] text-muted px-3 py-3 ${i >= 2 && i <= 4 ? 'text-right' : 'text-left'}`}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {form.items.map((it) => {
                  const e = (showErrors && errors[it.key]) || {}
                  const m = math.lines[it.key]
                  return (
                    <tr key={it.key} className="border-b border-hairline last:border-b-0 align-top">
                      <td className="px-3 py-3 text-muted w-10">
                        {it.line_no}
                        {it.source === 'manual' && !it.item_id && <span className="block caption text-primary">new</span>}
                      </td>
                      <td className="px-2 py-2">
                        <input className={inputCls(e.item_name)} value={it.item_name} onChange={(ev) => setItem(it.key, 'item_name', ev.target.value)} disabled={disabled} placeholder="Description" aria-label="Item name" />
                        {e.item_name && <p className="caption text-error mt-1">{e.item_name}</p>}
                      </td>
                      <td className="px-2 py-2 w-28">
                        <input inputMode="decimal" className={`${inputCls(e.quantity)} text-right`} value={it.quantity} onChange={(ev) => setItem(it.key, 'quantity', ev.target.value)} disabled={disabled} aria-label="Quantity" />
                        {e.quantity && <p className="caption text-error mt-1 text-right">{e.quantity}</p>}
                      </td>
                      <td className="px-2 py-2 w-36">
                        <input inputMode="decimal" className={`${inputCls(e.unit_price)} text-right`} value={it.unit_price} onChange={(ev) => setItem(it.key, 'unit_price', ev.target.value)} disabled={disabled} aria-label="Unit price" />
                        {e.unit_price && <p className="caption text-error mt-1 text-right">{e.unit_price}</p>}
                      </td>
                      <td className="px-2 py-2 w-40">
                        <input
                          inputMode="decimal"
                          className={`${inputCls(e.line_total || m?.mismatch)} text-right`}
                          value={it.line_total}
                          onChange={(ev) => setItem(it.key, 'line_total', ev.target.value)}
                          disabled={disabled}
                          placeholder={m?.expected != null ? m.expected.toFixed(2) : ''}
                          aria-label="Line total"
                        />
                        {m?.mismatch && !disabled && (
                          <button type="button" className="caption text-error mt-1 block ml-auto hover:underline" onClick={() => setItem(it.key, 'line_total', m.expected.toFixed(2))}>
                            Expected {m.expected.toFixed(2)}. Fix
                          </button>
                        )}
                      </td>
                      <td className="px-2 py-2 w-12 text-right">
                        <button
                          type="button"
                          onClick={() => removeItem(it.key)}
                          disabled={disabled}
                          className="grid place-items-center size-10 text-muted hover:text-error disabled:opacity-40"
                          aria-label={`Remove line ${it.line_no}`}
                        >
                          ✕
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Totals */}
      <div className="grid lg:grid-cols-[1fr_420px] gap-8">
        <div className="text-body-sm text-muted space-y-2 lg:pt-8">
          <p>
            Sum of line items: <span className="font-bold text-ink">{formatMoney(math.lineSum, cur)}</span>
          </p>
          {math.expectedTotal !== null && (
            <p>
              Subtotal + tax: <span className="font-bold text-ink">{formatMoney(math.expectedTotal, cur)}</span>
            </p>
          )}
          <p className="pt-2">Fields with a red border don't add up. Submitting still runs the backend checks, which the approver will see.</p>
        </div>
        <div className="space-y-4">
          {[
            ['subtotal', 'Subtotal', math.subtotalMismatch && { value: math.lineSum, text: 'Doesn’t match the line items' }],
            ['tax_amount', 'Tax', null],
            ['total_amount', 'Total', math.totalMismatch && { value: math.expectedTotal, text: 'Doesn’t equal subtotal + tax' }],
          ].map(([f, label, fix]) => (
            <div key={f} className="grid grid-cols-[120px_1fr] items-start gap-4">
              <span className={`pt-2.5 ${f === 'total_amount' ? 'text-title-sm' : 'text-body-sm'}`}>{label}</span>
              <div>
                <input
                  inputMode="decimal"
                  className={`${inputCls(err(f) || fix)} text-right ${f === 'total_amount' ? 'font-bold' : ''}`}
                  value={form[f]}
                  onChange={setField(f)}
                  disabled={disabled}
                  placeholder="Missing"
                  aria-label={label}
                />
                {err(f) && <p className="caption text-error mt-1 text-right">{err(f)}</p>}
                {fix && !disabled && (
                  <button type="button" className="caption text-error mt-1 block ml-auto hover:underline" onClick={() => setForm((s) => ({ ...s, [f]: fix.value.toFixed(2) }))}>
                    {fix.text}. Use {fix.value.toFixed(2)}
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
