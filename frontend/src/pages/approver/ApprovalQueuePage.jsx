import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { approvalsApi } from '../../api/endpoints'
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
  Table,
  TextLink,
} from '../../components/ui'
import { formatDate, formatDateTime, formatMoney } from '../../lib/format'
import { useAsync } from '../../lib/useAsync'

const LIMIT = 20

function daysWaiting(createdAt) {
  return Math.max(0, Math.floor((Date.now() - new Date(createdAt).getTime()) / 86_400_000))
}

export default function ApprovalQueuePage() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const { byId } = useVendors()
  const [offset, setOffset] = useState(0)
  const queue = useAsync(() => approvalsApi.pending({ limit: LIMIT, offset }), [offset])
  const rows = queue.data || []

  return (
    <>
      <Hero
        eyebrow={`Approver · ${user.name}`}
        title="Approval queue"
        actions={
          <Button variant="on-dark" onClick={queue.reload} loading={queue.loading && !!queue.data}>
            Refresh
          </Button>
        }
      >
        Invoices submitted by clerks, oldest first. Open one to see the extracted data, the validation checks and the
        correction history, then approve or reject it.
      </Hero>

      <Container>
        <Section
          title={queue.data ? `${rows.length}${rows.length === LIMIT ? '+' : ''} waiting` : 'Waiting'}
          description="Duplicate invoices are left out of the queue."
        >
          {queue.loading && !queue.data ? (
            <Loading />
          ) : queue.error ? (
            <ErrorState error={queue.error} onRetry={queue.reload} />
          ) : (
            <>
              <Table
                rows={rows}
                rowKey={(r) => r.invoice_id}
                onRowClick={(r) => navigate(`/approver/invoices/${r.invoice_id}`)}
                empty={<EmptyState title="Queue is empty">No invoices are waiting for approval.</EmptyState>}
                columns={[
                  { key: 'invoice_id', header: 'ID', render: (r) => <span className="text-muted">#{r.invoice_id}</span> },
                  {
                    key: 'invoice_number',
                    header: 'Invoice',
                    render: (r) => (
                      <div>
                        <p className="font-bold">{r.invoice_number || '—'}</p>
                        <p className="caption text-muted truncate max-w-56">{r.original_filename}</p>
                      </div>
                    ),
                  },
                  { key: 'vendor_id', header: 'Vendor', render: (r) => <VendorName id={r.vendor_id} byId={byId} /> },
                  { key: 'invoice_date', header: 'Invoice date', render: (r) => formatDate(r.invoice_date) },
                  { key: 'due_date', header: 'Due', render: (r) => <DueDate value={r.due_date} /> },
                  { key: 'total_amount', header: 'Total', align: 'right', render: (r) => <span className="font-bold">{formatMoney(r.total_amount, r.currency)}</span> },
                  {
                    key: 'created_at',
                    header: 'Waiting',
                    render: (r) => (
                      <span className="text-muted" title={formatDateTime(r.created_at)}>
                        {daysWaiting(r.created_at)}d
                      </span>
                    ),
                  },
                  { key: 'go', header: '', align: 'right', render: (r) => <TextLink to={`/approver/invoices/${r.invoice_id}`} className="!text-primary">Review</TextLink> },
                ]}
              />
              <Pagination offset={offset} limit={LIMIT} count={rows.length} onChange={setOffset} />
            </>
          )}
        </Section>
      </Container>
    </>
  )
}

function DueDate({ value }) {
  if (!value) return '—'
  const overdue = new Date(`${value}T23:59:59`) < new Date()
  return <span className={overdue ? 'text-error font-normal' : ''}>{formatDate(value)}{overdue && ' · overdue'}</span>
}
