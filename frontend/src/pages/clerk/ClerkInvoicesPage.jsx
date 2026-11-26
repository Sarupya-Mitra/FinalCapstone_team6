import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { invoicesApi } from '../../api/endpoints'
import { useAuth } from '../../auth/AuthContext'
import { VendorName, useVendors } from '../../components/invoice'
import {
  ButtonLink,
  Container,
  EmptyState,
  ErrorState,
  FilterChips,
  Hero,
  Loading,
  Pagination,
  Section,
  Stat,
  StatRow,
  StatusBadge,
  Table,
  TextLink,
} from '../../components/ui'
import { formatDate, formatDateTime, formatMoney, humanize, INVOICE_STATUSES } from '../../lib/format'
import { useAsync } from '../../lib/useAsync'

const LIMIT = 20

export const NEXT_STEP = {
  uploaded: 'Extract',
  extracted: 'Review',
}

export default function ClerkInvoicesPage() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const { vendors, byId } = useVendors()
  const [status, setStatus] = useState(null)
  const [vendorId, setVendorId] = useState('')
  const [offset, setOffset] = useState(0)

  // Most recent 100 invoices, used for the headline numbers.
  const overview = useAsync(() => invoicesApi.list({ limit: 100 }), [])
  const list = useAsync(
    () => invoicesApi.list({ status, vendor_id: vendorId, limit: LIMIT, offset }),
    [status, vendorId, offset]
  )

  const all = overview.data || []
  const count = (s) => all.filter((i) => i.status === s).length
  const needsAction = count('uploaded') + count('extracted')

  return (
    <>
      <Hero
        eyebrow={`Clerk · ${user.name}`}
        title="Your invoices"
        actions={
          <ButtonLink to="/clerk/upload" variant="primary">
            Upload invoice
          </ButtonLink>
        }
      >
        Upload invoices, check what the AI extracted, then submit them for approval.
      </Hero>

      <Container>
        <div className="-mt-px pt-10">
          <StatRow>
            <Stat label="Need your action" value={overview.loading ? '…' : needsAction} tone={needsAction ? 'error' : undefined} />
            <Stat label="Awaiting approval" value={overview.loading ? '…' : count('pending_approval')} />
            <Stat label="Approved" value={overview.loading ? '…' : count('approved')} tone="success" />
            <Stat label="Rejected" value={overview.loading ? '…' : count('rejected')} />
          </StatRow>
        </div>

        <Section title="All invoices">
          <div className="flex flex-col lg:flex-row lg:items-center gap-4 mb-6">
            <div className="flex-1 min-w-0">
              <FilterChips
                value={status}
                onChange={(v) => {
                  setStatus(v)
                  setOffset(0)
                }}
                options={[{ value: null, label: 'All' }, ...INVOICE_STATUSES.map((s) => ({ value: s, label: humanize(s) }))]}
              />
            </div>
            <select
              className="field field-sm lg:w-64"
              value={vendorId}
              onChange={(e) => {
                setVendorId(e.target.value)
                setOffset(0)
              }}
              aria-label="Filter by vendor"
            >
              <option value="">All vendors</option>
              {vendors.map((v) => (
                <option key={v.vendor_id} value={v.vendor_id}>
                  {v.vendor_name}
                </option>
              ))}
            </select>
          </div>

          {list.loading && !list.data ? (
            <Loading />
          ) : list.error ? (
            <ErrorState error={list.error} onRetry={list.reload} />
          ) : (
            <>
              <Table
                rows={list.data}
                rowKey={(r) => r.invoice_id}
                onRowClick={(r) => navigate(`/clerk/invoices/${r.invoice_id}`)}
                empty={
                  <EmptyState
                    title={status || vendorId ? 'No invoices match these filters' : 'No invoices yet'}
                    action={!status && !vendorId && <ButtonLink to="/clerk/upload">Upload your first invoice</ButtonLink>}
                  >
                    {status || vendorId ? 'Try another status or vendor.' : 'Upload a PDF invoice to get started.'}
                  </EmptyState>
                }
                columns={[
                  { key: 'invoice_id', header: 'ID', render: (r) => <span className="text-muted">#{r.invoice_id}</span> },
                  {
                    key: 'invoice_number',
                    header: 'Invoice',
                    render: (r) => (
                      <div>
                        <p className="font-bold">{r.invoice_number || <span className="font-light text-muted">Not extracted</span>}</p>
                        <p className="caption text-muted truncate max-w-56">{r.original_filename}</p>
                      </div>
                    ),
                  },
                  { key: 'vendor_id', header: 'Vendor', render: (r) => <VendorName id={r.vendor_id} byId={byId} /> },
                  { key: 'invoice_date', header: 'Date', render: (r) => formatDate(r.invoice_date) },
                  { key: 'total_amount', header: 'Total', align: 'right', render: (r) => formatMoney(r.total_amount, r.currency) },
                  { key: 'status', header: 'Status', render: (r) => <StatusBadge status={r.status} /> },
                  { key: 'created_at', header: 'Uploaded', render: (r) => <span className="text-muted">{formatDateTime(r.created_at)}</span> },
                  {
                    key: 'action',
                    header: '',
                    align: 'right',
                    render: (r) => (
                      <TextLink to={`/clerk/invoices/${r.invoice_id}`} className={NEXT_STEP[r.status] ? '!text-primary' : ''}>
                        {NEXT_STEP[r.status] || 'View'}
                      </TextLink>
                    ),
                  },
                ]}
              />
              <Pagination offset={offset} limit={LIMIT} count={list.data?.length || 0} onChange={setOffset} />
            </>
          )}
        </Section>
      </Container>
    </>
  )
}
