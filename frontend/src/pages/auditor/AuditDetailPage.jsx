import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { auditorApi } from '../../api/endpoints'
import {
  ChecksList,
  HistoryTimeline,
  InvoiceSummary,
  ItemsTable,
  VendorName,
  checkCounts,
  useVendors,
} from '../../components/invoice'
import {
  ButtonLink,
  Container,
  EmptyState,
  ErrorState,
  Hero,
  Loading,
  Section,
  Stat,
  StatRow,
  StatusBadge,
  Table,
  Tabs,
  TextLink,
} from '../../components/ui'
import { fieldLabel, formatDateTime, formatMoney } from '../../lib/format'
import { useAsync } from '../../lib/useAsync'

export default function AuditDetailPage() {
  const { id } = useParams()
  const { byId } = useVendors()
  const detail = useAsync(() => auditorApi.get(id), [id])
  const [tab, setTab] = useState('timeline')

  if (detail.loading && !detail.data) return <Loading />
  if (detail.error && !detail.data)
    return (
      <Container>
        <ErrorState error={detail.error} onRetry={detail.reload} />
        <TextLink to="/auditor">Back to audit trail</TextLink>
      </Container>
    )

  const { invoice, items, checks, corrections, extractions, approvals } = detail.data
  const counts = checkCounts(checks)
  const finalDecision = approvals.at(-1)
  const vendorName = <VendorName id={invoice.vendor_id} byId={byId} />

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
          <ButtonLink to="/auditor" variant="on-dark">
            ‹ Audit trail
          </ButtonLink>
        }
      >
        {vendorName} · uploaded by clerk #{invoice.uploaded_by_clerk_id} on {formatDateTime(invoice.created_at)}
      </Hero>

      <Container>
        <div className="pt-10">
          <StatRow>
            <Stat label="Total" value={formatMoney(invoice.total_amount, invoice.currency)} />
            <Stat label="AI runs" value={extractions.length} />
            <Stat label="Corrections" value={corrections.length} />
            <Stat label="Failed checks" value={counts.fail} tone={counts.fail ? 'error' : 'success'} />
          </StatRow>
        </div>

        {finalDecision && (
          <div className={`mt-10 border-l-4 p-6 bg-surface-card ${finalDecision.decision === 'approved' ? 'border-success' : 'border-error'}`}>
            <div className="flex flex-wrap items-center gap-3">
              <p className="text-title-md">
                {finalDecision.decision === 'approved' ? 'Approved' : 'Rejected'} by approver #{finalDecision.approver_id}
              </p>
              <span className="caption text-muted">{formatDateTime(finalDecision.decided_at)}</span>
            </div>
            <p className="mt-2 text-body-md whitespace-pre-line">{finalDecision.note}</p>
          </div>
        )}

        <Section title="Invoice details">
          <div className="bg-surface-soft p-6">
            <InvoiceSummary invoice={invoice} vendorName={vendorName} />
          </div>
        </Section>

        <Tabs
          value={tab}
          onChange={setTab}
          tabs={[
            { value: 'timeline', label: 'Timeline', count: corrections.length + extractions.length + approvals.length },
            { value: 'items', label: 'Line items', count: items.length },
            { value: 'checks', label: 'Checks', count: checks.length },
            { value: 'corrections', label: 'Corrections', count: corrections.length },
            { value: 'extractions', label: 'AI runs', count: extractions.length },
          ]}
        />
        <div className="pt-8">
          {tab === 'timeline' && <HistoryTimeline corrections={corrections} extractions={extractions} approvals={approvals} />}
          {tab === 'items' && <ItemsTable items={items} currency={invoice.currency} />}
          {tab === 'checks' && <ChecksList checks={checks} />}
          {tab === 'corrections' && (
            <Table
              rows={corrections}
              rowKey={(r) => r.correction_id}
              empty={<EmptyState title="No corrections">The clerk accepted the AI extraction as it was.</EmptyState>}
              columns={[
                { key: 'corrected_at', header: 'When', render: (r) => <span className="whitespace-nowrap">{formatDateTime(r.corrected_at)}</span> },
                { key: 'field_name', header: 'Field', render: (r) => <span className="font-bold">{fieldLabel(r.field_name)}</span> },
                { key: 'old_value', header: 'Old value', className: 'text-muted break-all max-w-xs', render: (r) => r.old_value ?? '(empty)' },
                { key: 'new_value', header: 'New value', className: 'break-all max-w-xs', render: (r) => r.new_value ?? '(empty)' },
                { key: 'clerk_id', header: 'Clerk', render: (r) => `#${r.clerk_id}` },
              ]}
            />
          )}
          {tab === 'extractions' && <ExtractionRuns runs={extractions} />}
        </div>
      </Container>
    </>
  )
}

function ExtractionRuns({ runs }) {
  const [open, setOpen] = useState(null)
  if (!runs.length) return <EmptyState title="No AI runs">No extraction was recorded for this invoice.</EmptyState>
  return (
    <ul className="border border-hairline divide-y divide-hairline">
      {runs.map((r) => (
        <li key={r.run_id} className="p-5">
          <div className="flex flex-wrap items-center gap-3">
            <p className="text-title-sm">Run #{r.run_id}</p>
            <StatusBadge status={r.status} />
            <span className="caption text-muted">
              {[r.provider, r.model_name].filter(Boolean).join(' · ')}
              {r.duration_ms != null && ` · ${(r.duration_ms / 1000).toFixed(1)}s`} · {formatDateTime(r.created_at)}
            </span>
          </div>
          {r.ai_summary && <p className="mt-2 text-body-sm whitespace-pre-line">{r.ai_summary}</p>}
          {r.error_message && <p className="mt-2 text-body-sm text-error">{r.error_message}</p>}
          {r.extracted_json && (
            <>
              <TextLink className="mt-3" onClick={() => setOpen(open === r.run_id ? null : r.run_id)}>
                {open === r.run_id ? 'Hide raw output' : 'Show raw output'}
              </TextLink>
              {open === r.run_id && (
                <pre className="mt-3 bg-surface-dark text-[#e6e6e6] text-[12px] leading-relaxed p-4 overflow-x-auto">
                  {JSON.stringify(r.extracted_json, null, 2)}
                </pre>
              )}
            </>
          )}
        </li>
      ))}
    </ul>
  )
}
