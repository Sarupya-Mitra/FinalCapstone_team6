import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { auditorApi } from '../../api/endpoints'
import { useAuth } from '../../auth/AuthContext'
import { VendorName, useVendors } from '../../components/invoice'
import {
  Button,
  Container,
  EmptyState,
  ErrorState,
  Hero,
  Loading,
  Pagination,
  Section,
  StatusBadge,
  Table,
  Tabs,
  TextLink,
} from '../../components/ui'
import { formatDate, formatDateTime, formatMoney } from '../../lib/format'
import { useAsync } from '../../lib/useAsync'

const LIMIT = 25

const TABS = [
  { value: '', label: 'All' },
  { value: 'pending_approval', label: 'Pending' },
  { value: 'approved', label: 'Approved' },
  { value: 'rejected', label: 'Rejected' },
]

export default function AuditListPage() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const { byId } = useVendors()
  const [status, setStatus] = useState('')
  const [offset, setOffset] = useState(0)
  const list = useAsync(() => auditorApi.list({ status, limit: LIMIT, offset }), [status, offset])
  const data = list.data

  const exportCsv = () => {
    const rows = data?.invoices || []
    const header = ['invoice_id', 'invoice_number', 'vendor', 'invoice_date', 'due_date', 'currency', 'subtotal', 'tax_amount', 'total_amount', 'status', 'duplicate_of', 'created_at']
    const esc = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`
    const lines = rows.map((r) =>
      [r.invoice_id, r.invoice_number, byId[r.vendor_id]?.vendor_name ?? r.vendor_id, r.invoice_date, r.due_date, r.currency, r.subtotal, r.tax_amount, r.total_amount, r.status, r.duplicate_of_invoice_id, r.created_at]
        .map(esc)
        .join(',')
    )
    const blob = new Blob([[header.join(','), ...lines].join('\n')], { type: 'text/csv' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `invoices-${status || 'all'}-page${offset / LIMIT + 1}.csv`
    a.click()
    URL.revokeObjectURL(a.href)
  }

  return (
    <>
      <Hero
        eyebrow={`Auditor · ${user.name}`}
        title="Audit trail"
        actions={
          <Button variant="on-dark" onClick={exportCsv} disabled={!data?.invoices?.length}>
            Export page as CSV
          </Button>
        }
      >
        Every submitted invoice, with its AI extraction runs, clerk corrections, validation checks and approval
        decisions. Read only.
      </Hero>

      <Container>
        <Section>
          <Tabs
            value={status}
            onChange={(v) => {
              setStatus(v)
              setOffset(0)
            }}
            tabs={TABS.map((t) => ({ ...t, count: t.value === status && data ? data.total : undefined }))}
          />
          <div className="pt-6">
            {list.loading && !data ? (
              <Loading />
            ) : list.error ? (
              <ErrorState error={list.error} onRetry={list.reload} />
            ) : (
              <>
                <Table
                  rows={data.invoices}
                  rowKey={(r) => r.invoice_id}
                  onRowClick={(r) => navigate(`/auditor/invoices/${r.invoice_id}`)}
                  empty={<EmptyState title="Nothing to audit">No invoices have this status.</EmptyState>}
                  columns={[
                    { key: 'invoice_id', header: 'ID', render: (r) => <span className="text-muted">#{r.invoice_id}</span> },
                    {
                      key: 'invoice_number',
                      header: 'Invoice',
                      render: (r) => (
                        <div>
                          <p className="font-bold">{r.invoice_number || '—'}</p>
                          {r.duplicate_of_invoice_id && <p className="caption text-error">Duplicate of #{r.duplicate_of_invoice_id}</p>}
                        </div>
                      ),
                    },
                    { key: 'vendor_id', header: 'Vendor', render: (r) => <VendorName id={r.vendor_id} byId={byId} /> },
                    { key: 'invoice_date', header: 'Date', render: (r) => formatDate(r.invoice_date) },
                    { key: 'total_amount', header: 'Total', align: 'right', render: (r) => formatMoney(r.total_amount, r.currency) },
                    { key: 'status', header: 'Status', render: (r) => <StatusBadge status={r.status} /> },
                    { key: 'clerk', header: 'Clerk', render: (r) => <span className="text-muted">#{r.uploaded_by_clerk_id}</span> },
                    { key: 'updated_at', header: 'Last activity', render: (r) => <span className="text-muted">{formatDateTime(r.updated_at)}</span> },
                    { key: 'go', header: '', align: 'right', render: (r) => <TextLink to={`/auditor/invoices/${r.invoice_id}`}>Trail</TextLink> },
                  ]}
                />
                <Pagination offset={offset} limit={LIMIT} total={data.total} onChange={setOffset} />
              </>
            )}
          </div>
        </Section>
      </Container>
    </>
  )
}
