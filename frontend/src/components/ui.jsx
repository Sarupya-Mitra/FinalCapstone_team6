// Shared UI primitives following DESIGN.md:
// square corners, no shadows, 700/300 type contrast, one blue action colour.
import { Link } from 'react-router-dom'
import { humanize } from '../lib/format'

const cx = (...c) => c.filter(Boolean).join(' ')

/* ---------------------------------------------------------------- Buttons */

const BTN_BASE =
  'inline-flex items-center justify-center gap-2 h-12 px-8 text-[14px] font-bold tracking-[0.5px] leading-none transition-colors select-none whitespace-nowrap'
const BTN_VARIANTS = {
  primary:
    'bg-primary text-white active:bg-primary-active hover:bg-primary-active disabled:bg-primary-disabled disabled:text-muted',
  secondary:
    'bg-canvas text-ink border border-hairline-strong hover:border-ink disabled:text-muted-soft disabled:hover:border-hairline-strong',
  'on-dark': 'bg-transparent text-white border border-white hover:bg-white/10',
  danger: 'bg-canvas text-error border border-error hover:bg-error hover:text-white disabled:opacity-50',
  ghost: 'bg-transparent text-ink hover:bg-surface-soft disabled:text-muted-soft',
}
const BTN_SIZES = { md: '', sm: '!h-10 !px-5 !text-[13px]' }

export function Button({ variant = 'primary', size = 'md', loading, className, children, disabled, ...props }) {
  return (
    <button
      className={cx(BTN_BASE, BTN_VARIANTS[variant], BTN_SIZES[size], className)}
      disabled={disabled || loading}
      {...props}
    >
      {loading && <Spinner className="size-4" />}
      {children}
    </button>
  )
}

export function ButtonLink({ variant = 'primary', size = 'md', className, ...props }) {
  return <Link className={cx(BTN_BASE, BTN_VARIANTS[variant], BTN_SIZES[size], className)} {...props} />
}

// Uppercase letter-spaced inline link, "VIEW ›"
export function TextLink({ to, children, className, onDark, ...props }) {
  const cls = cx(
    'label-upper inline-flex items-center gap-1 hover:text-primary',
    onDark ? 'text-white' : 'text-ink',
    className
  )
  const body = (
    <>
      {children} <span aria-hidden>›</span>
    </>
  )
  if (to) return <Link to={to} className={cls} {...props}>{body}</Link>
  return <button type="button" className={cls} {...props}>{body}</button>
}

/* ---------------------------------------------------------------- Feedback */

export function Spinner({ className }) {
  return (
    <svg className={cx('animate-spin', className || 'size-5')} viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
      <path d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" strokeWidth="3" />
    </svg>
  )
}

export function Loading({ label = 'Loading…' }) {
  return (
    <div className="flex items-center gap-3 py-16 justify-center text-muted" role="status">
      <Spinner /> <span className="text-body-sm">{label}</span>
    </div>
  )
}

const ALERT_TONES = {
  error: 'border-error text-error bg-[#fdf2f2]',
  success: 'border-success text-[#166534] bg-[#f0fdf4]',
  warning: 'border-warning text-[#92400e] bg-[#fffbeb]',
  info: 'border-primary text-primary-active bg-[#eff5fd]',
}

export function Alert({ tone = 'info', title, children, onClose, className }) {
  if (!children && !title) return null
  return (
    <div className={cx('border-l-4 px-4 py-3 flex gap-3 items-start', ALERT_TONES[tone], className)} role="alert">
      <div className="flex-1 text-body-sm whitespace-pre-line">
        {title && <p className="font-bold mb-0.5">{title}</p>}
        {children}
      </div>
      {onClose && (
        <button onClick={onClose} className="text-current opacity-70 hover:opacity-100" aria-label="Dismiss">
          ✕
        </button>
      )}
    </div>
  )
}

export function ErrorState({ error, onRetry }) {
  if (!error) return null
  return (
    <div className="py-10">
      <Alert tone="error" title={error.status === 404 ? 'Not found' : 'Something went wrong'}>
        {error.message}
      </Alert>
      {onRetry && (
        <Button variant="secondary" size="sm" className="mt-4" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  )
}

export function EmptyState({ title, children, action }) {
  return (
    <div className="bg-surface-card py-16 px-6 text-center">
      <p className="text-title-md font-bold text-ink">{title}</p>
      {children && <p className="mt-2 text-body-sm text-muted max-w-md mx-auto">{children}</p>}
      {action && <div className="mt-6">{action}</div>}
    </div>
  )
}

/* ---------------------------------------------------------------- Status */

const STATUS_TONES = {
  uploaded: 'bg-surface-strong text-ink',
  extracted: 'bg-[#eff5fd] text-primary-active',
  pending_approval: 'bg-[#fffbeb] text-[#92400e]',
  discrepancy: 'bg-[#fdf2f2] text-error',
  approved: 'bg-[#f0fdf4] text-[#166534]',
  rejected: 'bg-[#fdf2f2] text-error',
  // extraction run statuses
  success: 'bg-[#f0fdf4] text-[#166534]',
  partial: 'bg-[#fffbeb] text-[#92400e]',
  failed: 'bg-[#fdf2f2] text-error',
  no_text: 'bg-[#fdf2f2] text-error',
  timeout: 'bg-[#fffbeb] text-[#92400e]',
  rate_limited: 'bg-[#fffbeb] text-[#92400e]',
  // check results
  pass: 'bg-[#f0fdf4] text-[#166534]',
  fail: 'bg-[#fdf2f2] text-error',
  warning: 'bg-[#fffbeb] text-[#92400e]',
  // vendors
  active: 'bg-[#f0fdf4] text-[#166534]',
  inactive: 'bg-surface-strong text-muted',
  ai: 'bg-[#eff5fd] text-primary-active',
  manual: 'bg-surface-strong text-ink',
}

export function StatusBadge({ status, label, className }) {
  return (
    <span
      className={cx(
        'inline-flex items-center px-2 py-1 text-[11px] font-bold uppercase tracking-[1px] leading-none whitespace-nowrap',
        STATUS_TONES[status] || 'bg-surface-strong text-ink',
        className
      )}
    >
      {label || humanize(status)}
    </span>
  )
}

/* ---------------------------------------------------------------- Layout */

// The one dark band per page.
export function Hero({ eyebrow, title, children, actions }) {
  return (
    <section className="bg-surface-dark text-white">
      <div className="mx-auto max-w-[1440px] px-4 sm:px-8 lg:px-12 py-12 md:py-16">
        {eyebrow && <p className="label-upper text-on-dark-soft mb-3">{eyebrow}</p>}
        <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div className="min-w-0">
            <h1 className="text-white text-[36px] leading-[1.1] md:text-display-lg break-words">{title}</h1>
            {children && <div className="mt-3 text-body-md text-on-dark-soft max-w-2xl">{children}</div>}
          </div>
          {actions && <div className="flex flex-wrap gap-3 shrink-0">{actions}</div>}
        </div>
      </div>
    </section>
  )
}

export function Container({ className, children }) {
  return <div className={cx('mx-auto max-w-[1440px] px-4 sm:px-8 lg:px-12', className)}>{children}</div>
}

export function Section({ title, actions, children, className, description }) {
  return (
    <section className={cx('py-10', className)}>
      {(title || actions) && (
        <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
          <div>
            {title && <h2 className="text-display-sm">{title}</h2>}
            {description && <p className="mt-1 text-body-sm text-muted">{description}</p>}
          </div>
          {actions && <div className="flex flex-wrap gap-3">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  )
}

export function Card({ className, children, title, actions }) {
  return (
    <div className={cx('bg-canvas border border-hairline', className)}>
      {(title || actions) && (
        <div className="flex items-center justify-between gap-4 px-6 py-4 border-b border-hairline">
          {title && <h3 className="text-title-sm">{title}</h3>}
          {actions}
        </div>
      )}
      <div className="p-6">{children}</div>
    </div>
  )
}

// Spec cell: value on top, uppercase label below.
export function Stat({ label, value, tone }) {
  return (
    <div className="px-6 py-6 border-hairline">
      <p
        className={cx(
          'text-display-sm font-bold break-words',
          tone === 'error' ? 'text-error' : tone === 'success' ? 'text-[#166534]' : 'text-ink'
        )}
      >
        {value}
      </p>
      <p className="label-upper text-muted mt-1">{label}</p>
    </div>
  )
}

export function StatRow({ children }) {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 border border-hairline divide-x divide-y lg:divide-y-0 divide-hairline bg-canvas">
      {children}
    </div>
  )
}

export function KeyValue({ items, cols = 3 }) {
  const grid = { 2: 'sm:grid-cols-2', 3: 'sm:grid-cols-2 lg:grid-cols-3', 4: 'sm:grid-cols-2 lg:grid-cols-4' }[cols]
  return (
    <dl className={cx('grid grid-cols-1 gap-x-8 gap-y-5', grid)}>
      {items.map(([k, v]) => (
        <div key={k}>
          <dt className="caption text-muted uppercase">{k}</dt>
          <dd className="mt-1 text-body-md text-ink break-words">{v ?? '—'}</dd>
        </div>
      ))}
    </dl>
  )
}

/* ---------------------------------------------------------------- Filters & tabs */

export function FilterChips({ options, value, onChange }) {
  return (
    <div className="flex gap-2 overflow-x-auto pb-1 -mx-1 px-1">
      {options.map((opt) => {
        const active = value === opt.value
        return (
          <button
            key={opt.value ?? 'all'}
            type="button"
            onClick={() => onChange(opt.value)}
            className={cx(
              'caption whitespace-nowrap px-[14px] py-2 border transition-colors',
              active ? 'bg-ink text-white border-ink' : 'bg-canvas text-ink border-hairline-strong hover:border-ink'
            )}
          >
            {opt.label}
          </button>
        )
      })}
    </div>
  )
}

export function Tabs({ tabs, value, onChange }) {
  return (
    <div className="flex gap-6 border-b border-hairline overflow-x-auto" role="tablist">
      {tabs.map((t) => {
        const active = t.value === value
        return (
          <button
            key={t.value}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(t.value)}
            className={cx(
              'label-upper py-3 -mb-px border-b-2 whitespace-nowrap transition-colors',
              active ? 'text-ink border-ink' : 'text-muted border-transparent hover:text-ink'
            )}
          >
            {t.label}
            {t.count !== undefined && <span className="ml-2 text-muted-soft">{t.count}</span>}
          </button>
        )
      })}
    </div>
  )
}

export function Pagination({ offset, limit, count, total, onChange }) {
  const page = Math.floor(offset / limit) + 1
  const hasNext = total !== undefined ? offset + limit < total : count === limit
  const pages = total !== undefined ? Math.max(1, Math.ceil(total / limit)) : null
  if (offset === 0 && !hasNext) return null
  return (
    <div className="flex items-center justify-between gap-4 pt-6">
      <p className="text-body-sm text-muted">
        Page {page}
        {pages ? ` of ${pages}` : ''}
        {total !== undefined ? ` · ${total} total` : ''}
      </p>
      <div className="flex gap-2">
        <Button variant="secondary" size="sm" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>
          ‹ Previous
        </Button>
        <Button variant="secondary" size="sm" disabled={!hasNext} onClick={() => onChange(offset + limit)}>
          Next ›
        </Button>
      </div>
    </div>
  )
}

/* ---------------------------------------------------------------- Forms */

export function Field({ label, error, hint, children, className, htmlFor }) {
  return (
    <div className={className}>
      {label && (
        <label htmlFor={htmlFor} className="block caption uppercase text-muted mb-2">
          {label}
        </label>
      )}
      {children}
      {error ? (
        <p className="mt-1.5 text-caption text-error">{error}</p>
      ) : hint ? (
        <p className="mt-1.5 text-caption text-muted">{hint}</p>
      ) : null}
    </div>
  )
}

/* ---------------------------------------------------------------- Table */

// columns: [{ key, header, render?, align?, className? }]
export function Table({ columns, rows, rowKey, onRowClick, empty }) {
  if (!rows?.length) return empty || null
  return (
    <div className="overflow-x-auto border border-hairline bg-canvas">
      <table className="w-full text-body-sm">
        <thead>
          <tr className="border-b border-hairline bg-surface-soft">
            {columns.map((c) => (
              <th
                key={c.key}
                className={cx(
                  'label-upper !text-[11px] text-muted px-4 py-3 whitespace-nowrap',
                  c.align === 'right' ? 'text-right' : 'text-left'
                )}
              >
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr
              key={rowKey ? rowKey(row) : i}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              className={cx(
                'border-b border-hairline last:border-b-0',
                onRowClick && 'cursor-pointer hover:bg-surface-card'
              )}
            >
              {columns.map((c) => (
                <td
                  key={c.key}
                  className={cx('px-4 py-3 align-middle text-ink', c.align === 'right' && 'text-right tabular-nums', c.className)}
                >
                  {c.render ? c.render(row) : row[c.key] ?? '—'}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/* ---------------------------------------------------------------- Modal */

export function Modal({ open, title, onClose, children, footer }) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-surface-dark/60 p-0 sm:p-4" onMouseDown={onClose}>
      <div
        className="w-full sm:max-w-lg bg-canvas max-h-[90vh] flex flex-col"
        role="dialog"
        aria-modal="true"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-hairline">
          <h2 className="text-title-lg">{title}</h2>
          <button onClick={onClose} className="text-muted hover:text-ink text-xl leading-none" aria-label="Close">
            ✕
          </button>
        </div>
        <div className="p-6 overflow-y-auto">{children}</div>
        {footer && <div className="px-6 py-4 border-t border-hairline flex justify-end gap-3">{footer}</div>}
      </div>
    </div>
  )
}
