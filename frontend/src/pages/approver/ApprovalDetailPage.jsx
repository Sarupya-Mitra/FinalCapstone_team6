import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { approvalsApi } from '../../api/endpoints'
import {
  AiSummary,
  ChecksList,
  HistoryTimeline,
  InvoiceSummary,
  ItemsTable,
  VendorName,
  checkCounts,
  useVendors,
} from '../../components/invoice'
import {
  Alert,
  Button,
  ButtonLink,
  Container,
  ErrorState,
  Field,
  Hero,
  Loading,
  Section,
  Stat,
  StatRow,
  StatusBadge,
  Tabs,
  TextLink,
} from '../../components/ui'
import { formatDateTime, formatMoney } from '../../lib/format'
import { useAsync } from '../../lib/useAsync'

export default function ApprovalDetailPage() {
  const { id } = useParams()
  const { byId } = useVendors()
  const detail = useAsync(() => approvalsApi.get(id), [id])
  const history = useAsync(() => approvalsApi.history(id), [id])
  const [tab, setTab] = useState('items')
  const [decision, setDecision] = useState(null) // ApprovalResponse once decided

  if (detail.loading && !detail.data) return <Loading />
  if (detail.error && !detail.data)
    return (
      <Container>
        <ErrorState
          error={
            detail.error.status === 404
              ? { ...detail.error, message: 'This invoice is not waiting for approval. It may already have been decided.' }
              : detail.error
          }
          onRetry={detail.reload}
        />
        <TextLink to="/approver">Back to queue</TextLink>
      </Container>
    )

  const { invoice, items, checks } = detail.data
  const counts = checkCounts(checks)
  const latestExtraction = history.data?.extractions?.at(-1)
  const corrections = history.data?.corrections || []
  const vendorName = <VendorName id={invoice.vendor_id} byId={byId} />

  return (
    <>
      <Hero
        eyebrow={
          <span className="inline-flex items-center gap-3">
            Invoice #{invoice.invoice_id}
            <StatusBadge status={decision ? decision.decision : invoice.status} />
          </span>
        }
        title={invoice.invoice_number || invoice.original_filename}
        actions={
          <ButtonLink to="/approver" variant="on-dark">
            ‹ Back to queue
          </ButtonLink>
        }
      >
        {vendorName} · {formatMoney(invoice.total_amount, invoice.currency)}
      </Hero>

      <Container>
        <div className="pt-10">
          <StatRow>
            <Stat label="Invoice total" value={formatMoney(invoice.total_amount, invoice.currency)} />
            <Stat label="Checks passed" value={`${counts.pass}/${checks.length}`} tone={counts.fail ? undefined : 'success'} />
            <Stat label="Checks failed" value={counts.fail} tone={counts.fail ? 'error' : undefined} />
            <Stat label="Clerk corrections" value={history.loading ? '…' : corrections.length} />
          </StatRow>
        </div>

        <div className="grid lg:grid-cols-[1fr_400px] gap-10 items-start">
          <div className="min-w-0">
            {counts.fail > 0 && (
              <Alert tone="error" className="mt-10" title={`${counts.fail} validation check${counts.fail > 1 ? 's' : ''} failed`}>
                Look at the Checks tab before you decide.
              </Alert>
            )}

            <Section title="Invoice details">
              <div className="bg-surface-soft p-6">
                <InvoiceSummary invoice={invoice} vendorName={vendorName} />
              </div>
            </Section>

            <div className="pb-10">
              <Tabs
                value={tab}
                onChange={setTab}
                tabs={[
                  { value: 'items', label: 'Line items', count: items.length },
                  { value: 'checks', label: 'Checks', count: checks.length },
                  { value: 'history', label: 'History', count: history.data ? corrections.length + history.data.extractions.length : undefined },
                ]}
              />
              <div className="pt-6">
                {tab === 'items' && <ItemsTable items={items} currency={invoice.currency} />}
                {tab === 'checks' && <ChecksList checks={checks} />}
                {tab === 'history' &&
                  (history.loading && !history.data ? (
                    <Loading />
                  ) : history.error ? (
                    <ErrorState error={history.error} onRetry={history.reload} />
                  ) : (
                    <HistoryTimeline corrections={corrections} extractions={history.data.extractions} />
                  ))}
              </div>
            </div>

            {latestExtraction && (
              <div className="pb-10">
                <AiSummary extraction={latestExtraction} />
              </div>
            )}
          </div>

          <aside className="lg:sticky lg:top-24 pt-10">
            {decision ? (
              <DecisionResult decision={decision} />
            ) : (
              <DecisionForm invoiceId={invoice.invoice_id} failedChecks={counts.fail} onDecided={setDecision} />
            )}
          </aside>
        </div>
      </Container>
    </>
  )
}

function DecisionForm({ invoiceId, failedChecks, onDecided }) {
  const [choice, setChoice] = useState(null)
  const [note, setNote] = useState('')
  const [error, setError] = useState(null)
  const [touched, setTouched] = useState(false)
  const [saving, setSaving] = useState(false)

  const noteError = touched && !note.trim() ? 'A note is required for the audit trail.' : null

  const onSubmit = async (e) => {
    e.preventDefault()
    setTouched(true)
    if (!choice || !note.trim()) return
    setSaving(true)
    setError(null)
    try {
      onDecided(await approvalsApi.decide(invoiceId, choice, note.trim()))
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const tile = (value, label, desc) => {
    const selected = choice === value
    return (
      <button
        type="button"
        onClick={() => setChoice(value)}
        aria-pressed={selected}
        className={`text-left bg-canvas transition-colors ${
          selected
            ? `border-2 px-[23px] py-[15px] ${value === 'approved' ? 'border-primary' : 'border-error'}`
            : 'border border-hairline-strong px-6 py-4 hover:border-ink'
        }`}
      >
        <span className={`block text-title-sm ${selected && value === 'rejected' ? 'text-error' : ''}`}>{label}</span>
        <span className="block text-body-sm text-muted">{desc}</span>
      </button>
    )
  }

  return (
    <form onSubmit={onSubmit} className="border border-hairline bg-canvas p-6" noValidate>
      <h2 className="text-title-lg">Your decision</h2>
      <p className="mt-1 text-body-sm text-muted">This is final and is recorded in the audit trail.</p>

      <div className="mt-6 grid gap-3">
        {tile('approved', 'Approve', 'The invoice is correct and can be paid.')}
        {tile('rejected', 'Reject', 'Send it back. Say why in the note.')}
      </div>
      {touched && !choice && <p className="mt-2 caption text-error">Choose approve or reject.</p>}

      {choice === 'approved' && failedChecks > 0 && (
        <Alert tone="warning" className="mt-4">
          {failedChecks} check{failedChecks > 1 ? 's' : ''} failed. Say in the note why you are approving anyway.
        </Alert>
      )}

      <Field label="Note" className="mt-6" error={noteError} htmlFor="note">
        <textarea
          id="note"
          rows={5}
          maxLength={5000}
          className={`field !h-auto py-3 resize-y ${noteError ? 'field-error' : ''}`}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          onBlur={() => setTouched(true)}
          placeholder={choice === 'rejected' ? 'Why is this invoice rejected?' : 'Add a note for the audit trail'}
        />
      </Field>

      {error && (
        <Alert tone="error" className="mt-4">
          {error}
        </Alert>
      )}

      <Button type="submit" className="w-full mt-6" loading={saving} disabled={!choice}>
        {choice === 'rejected' ? 'Reject invoice' : choice === 'approved' ? 'Approve invoice' : 'Submit decision'}
      </Button>
    </form>
  )
}

function DecisionResult({ decision }) {
  const approved = decision.decision === 'approved'
  return (
    <div className={`border-2 p-6 bg-canvas ${approved ? 'border-success' : 'border-error'}`}>
      <p className={`label-upper ${approved ? 'text-[#166534]' : 'text-error'}`}>Decision recorded</p>
      <h2 className="mt-2 text-display-sm">{approved ? 'Invoice approved' : 'Invoice rejected'}</h2>
      <p className="mt-3 text-body-md whitespace-pre-line">{decision.note}</p>
      <p className="mt-3 caption text-muted">{formatDateTime(decision.decided_at)}</p>
      <ButtonLink to="/approver" className="w-full mt-6">
        Next invoice
      </ButtonLink>
    </div>
  )
}
