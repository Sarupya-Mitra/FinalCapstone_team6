import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { invoicesApi } from '../../api/endpoints'
import { AiSummary, ChecksList, InvoiceSummary, ItemsTable, VendorName, checkCounts, useVendors } from '../../components/invoice'
import {
  Alert,
  Button,
  ButtonLink,
  Card,
  Container,
  ErrorState,
  Hero,
  Loading,
  Modal,
  Section,
  StatusBadge,
  TextLink,
} from '../../components/ui'
import { humanize } from '../../lib/format'
import { useAsync } from '../../lib/useAsync'
import InvoiceEditor, { toForm, toPayload, validateForm } from './InvoiceEditor'

const EXTRACT_TONE = { success: 'success', no_text: 'error', failed: 'error', timeout: 'warning', rate_limited: 'warning', partial: 'warning' }

export default function InvoiceReviewPage() {
  const { id } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const { byId } = useVendors()
  const review = useAsync(() => invoicesApi.review(id), [id])

  const [form, setForm] = useState(null)
  const [baseline, setBaseline] = useState(null)
  const [showErrors, setShowErrors] = useState(false)
  const [busy, setBusy] = useState(null) // 'extract' | 'save' | 'submit'
  const [notice, setNotice] = useState(() => extractNotice(location.state?.extractResult))
  const [actionError, setActionError] = useState(null)
  const [submitResult, setSubmitResult] = useState(null)
  const [confirmSubmit, setConfirmSubmit] = useState(false)

  // Drop router state so a refresh doesn't show the upload notice again.
  useEffect(() => {
    if (location.state) navigate(location.pathname, { replace: true, state: null })
  }, [location, navigate])

  const invoice = review.data?.invoice
  const items = review.data?.items
  const editable = invoice?.status === 'extracted'

  // Reset the form whenever fresh data arrives from the server.
  useEffect(() => {
    if (invoice && items) {
      const f = toForm(invoice, items)
      setForm(f)
      setBaseline(JSON.stringify(toPayload(f)))
      setShowErrors(false)
    }
  }, [invoice, items])

  const errors = useMemo(() => (form ? validateForm(form) : {}), [form])
  const hasErrors = Object.keys(errors).length > 0
  const dirty = form && baseline !== null && JSON.stringify(toPayload(form)) !== baseline

  const runExtract = async () => {
    setBusy('extract')
    setActionError(null)
    setNotice(null)
    try {
      const res = await invoicesApi.extract(id)
      setNotice(extractNotice(res))
      await review.reload()
    } catch (err) {
      setActionError(err.message)
    } finally {
      setBusy(null)
    }
  }

  const save = async () => {
    setShowErrors(true)
    if (hasErrors) {
      setActionError('Fix the highlighted fields first.')
      return false
    }
    setActionError(null)
    await invoicesApi.saveCorrections(id, toPayload(form))
    return true
  }

  const onSave = async () => {
    setBusy('save')
    setNotice(null)
    try {
      if (await save()) {
        setNotice({ tone: 'success', text: 'Corrections saved.' })
        await review.reload()
      }
    } catch (err) {
      setActionError(err.message)
    } finally {
      setBusy(null)
    }
  }

  const onSubmit = async () => {
    setConfirmSubmit(false)
    setBusy('submit')
    setNotice(null)
    try {
      if (dirty && !(await save())) return
      const res = await invoicesApi.submit(id)
      setSubmitResult(res)
      await review.reload()
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (err) {
      setActionError(err.message)
      // A save may have succeeded before submit failed; refresh to stay in sync.
      review.reload()
    } finally {
      setBusy(null)
    }
  }

  if (review.loading && !review.data) return <Loading />
  if (review.error && !review.data)
    return (
      <Container>
        <ErrorState error={review.error} onRetry={review.reload} />
        <TextLink to="/clerk">Back to invoices</TextLink>
      </Container>
    )

  const vendorName = <VendorName id={invoice.vendor_id} byId={byId} />
  const counts = submitResult ? checkCounts(submitResult.checks) : null

  return (
    <>
      <Hero
        eyebrow={
          <span className="inline-flex items-center gap-3">
            Invoice #{invoice.invoice_id} <StatusBadge status={invoice.status} />
          </span>
        }
        title={invoice.invoice_number || invoice.original_filename}
        actions={
          <ButtonLink to="/clerk" variant="on-dark">
            ‹ All invoices
          </ButtonLink>
        }
      >
        {vendorName} · {stepDescription(invoice.status)}
      </Hero>

      <Container>
        <div className="pt-8 space-y-4">
          {notice && (
            <Alert tone={notice.tone} onClose={() => setNotice(null)}>
              {notice.text}
            </Alert>
          )}
          {actionError && (
            <Alert tone="error" onClose={() => setActionError(null)}>
              {actionError}
            </Alert>
          )}
          {submitResult && (
            <Alert
              tone={counts.fail ? 'warning' : 'success'}
              title={submitResult.message}
              onClose={() => setSubmitResult(null)}
            >
              {submitResult.total_checks} checks ran: {counts.pass} passed, {counts.fail} failed, {counts.warning} warnings.
              {counts.fail > 0 && ' The approver will see the failed checks.'}
            </Alert>
          )}
        </div>

        {/* ---------- Step 1: extraction ---------- */}
        {invoice.status === 'uploaded' && (
          <Section>
            <div className="grid lg:grid-cols-[1fr_360px] gap-8">
              <Card>
                <p className="label-upper text-primary">Next step</p>
                <h2 className="mt-2 text-display-sm">Extract the invoice data with AI</h2>
                <p className="mt-3 text-body-md text-body max-w-xl">
                  The AI reads the stored PDF and fills in the invoice number, dates, amounts and line items. You can
                  check and correct everything afterwards.
                </p>
                <Button className="mt-6" onClick={runExtract} loading={busy === 'extract'}>
                  {busy === 'extract' ? 'Extracting…' : review.data.extraction ? 'Retry extraction' : 'Run AI extraction'}
                </Button>
              </Card>
              <div className="bg-surface-soft p-6">
                <InvoiceSummary invoice={invoice} vendorName={vendorName} />
              </div>
            </div>
            {review.data.extraction && (
              <div className="mt-8">
                <p className="label-upper text-muted mb-3">Last attempt</p>
                <AiSummary extraction={review.data.extraction} />
              </div>
            )}
          </Section>
        )}

        {/* ---------- Step 2: review & correct ---------- */}
        {editable && form && (
          <Section
            title="Review extracted data"
            description="Compare with the PDF and correct anything the AI got wrong. Every change is recorded in the audit trail."
          >
            {review.data.extraction && (
              <div className="mb-10">
                <AiSummary extraction={review.data.extraction} />
              </div>
            )}

            <InvoiceEditor form={form} setForm={setForm} errors={errors} showErrors={showErrors} disabled={busy !== null} />

            <div className="sticky bottom-0 z-10 mt-10 -mx-4 sm:mx-0 bg-canvas border-t border-hairline px-4 sm:px-0 py-3 sm:py-4 grid grid-cols-3 gap-2 sm:flex sm:flex-wrap sm:items-center sm:gap-3 [&>button]:!px-2 sm:[&>button]:!px-8 [&>button]:!h-11 sm:[&>button]:!h-12">
              <p className="hidden sm:block text-body-sm text-muted mr-auto">
                {dirty ? 'You have unsaved changes.' : 'No unsaved changes.'}
                {showErrors && hasErrors && <span className="text-error"> Some fields need attention.</span>}
              </p>
              <Button
                variant="secondary"
                disabled={!dirty || busy !== null}
                onClick={() => {
                  const f = toForm(invoice, items)
                  setForm(f)
                  setShowErrors(false)
                }}
              >
                Discard
              </Button>
              <Button variant="secondary" onClick={onSave} disabled={!dirty || busy !== null} loading={busy === 'save'}>
                Save<span className="hidden sm:inline">&nbsp;corrections</span>
              </Button>
              <Button onClick={() => setConfirmSubmit(true)} disabled={busy !== null} loading={busy === 'submit'}>
                Submit<span className="hidden sm:inline">&nbsp;for approval</span>
              </Button>
            </div>
          </Section>
        )}

        {/* ---------- Step 3+: read only ---------- */}
        {!editable && invoice.status !== 'uploaded' && (
          <>
            <Section title="Invoice details">
              <div className="bg-surface-soft p-6">
                <InvoiceSummary invoice={invoice} vendorName={vendorName} />
              </div>
            </Section>
            <Section title="Line items">
              <ItemsTable items={items} currency={invoice.currency} />
            </Section>
            {submitResult && (
              <Section title="Validation checks">
                <ChecksList checks={submitResult.checks} />
              </Section>
            )}
            {review.data.extraction && (
              <Section title="AI extraction">
                <AiSummary extraction={review.data.extraction} />
              </Section>
            )}
          </>
        )}
      </Container>

      <Modal
        open={confirmSubmit}
        title="Submit for approval?"
        onClose={() => setConfirmSubmit(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirmSubmit(false)}>
              Cancel
            </Button>
            <Button onClick={onSubmit}>{dirty ? 'Save & submit' : 'Submit'}</Button>
          </>
        }
      >
        <p className="text-body-md">
          The backend runs the validation checks (duplicates, line totals, invoice total, required fields) and sends
          the invoice to an approver. You can't edit it after this.
        </p>
        {dirty && <p className="mt-3 text-body-sm text-muted">Your unsaved corrections will be saved first.</p>}
      </Modal>
    </>
  )
}

function extractNotice(res) {
  if (!res) return null
  return {
    tone: EXTRACT_TONE[res.status] || 'info',
    text:
      res.status === 'success'
        ? 'AI extraction finished. Review the data below.'
        : res.message || `Extraction ended with status: ${humanize(res.status)}`,
  }
}

function stepDescription(status) {
  return {
    uploaded: 'Waiting for AI extraction',
    extracted: 'Ready for your review',
    pending_approval: 'Submitted, waiting for an approver',
    discrepancy: 'Submitted with discrepancies',
    approved: 'Approved',
    rejected: 'Rejected by the approver',
  }[status]
}
