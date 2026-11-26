import { useState } from 'react'
import { vendorsApi } from '../../api/endpoints'
import { invalidateVendors } from '../../components/invoice'
import {
  Alert,
  Button,
  Container,
  EmptyState,
  ErrorState,
  Field,
  FilterChips,
  Hero,
  Loading,
  Modal,
  Section,
  StatusBadge,
  Table,
  TextLink,
} from '../../components/ui'
import { formatDate } from '../../lib/format'
import { useAsync } from '../../lib/useAsync'

const EMPTY = { vendor_name: '', contact_reference: '', tax_id: '', active: true }

export default function VendorsPage() {
  const vendors = useAsync(() => vendorsApi.list(), [])
  const [filter, setFilter] = useState('all')
  const [query, setQuery] = useState('')
  const [editing, setEditing] = useState(null) // null | 'new' | vendor
  const [flash, setFlash] = useState(null)

  const rows = (vendors.data || [])
    .filter((v) => (filter === 'all' ? true : filter === 'active' ? v.active : !v.active))
    .filter((v) => {
      const q = query.trim().toLowerCase()
      return !q || [v.vendor_name, v.contact_reference, v.tax_id].some((s) => s?.toLowerCase().includes(q))
    })
    .sort((a, b) => a.vendor_name.localeCompare(b.vendor_name))

  const onSaved = (v, isNew) => {
    invalidateVendors()
    setEditing(null)
    setFlash(`${v.vendor_name} ${isNew ? 'added' : 'updated'}.`)
    vendors.setData((list) => (isNew ? [...(list || []), v] : list.map((x) => (x.vendor_id === v.vendor_id ? v : x))))
  }

  const total = vendors.data?.length ?? 0
  const activeCount = vendors.data?.filter((v) => v.active).length ?? 0

  return (
    <>
      <Hero
        eyebrow="Clerk · Master data"
        title="Vendors"
        actions={
          <Button variant="primary" onClick={() => setEditing('new')}>
            Add vendor
          </Button>
        }
      >
        Vendors that issue invoices. Only active vendors appear on the upload form.
      </Hero>

      <Container>
        <Section>
          {flash && (
            <Alert tone="success" className="mb-6" onClose={() => setFlash(null)}>
              {flash}
            </Alert>
          )}
          <div className="flex flex-col md:flex-row md:items-center gap-4 mb-6">
            <div className="flex-1">
              <FilterChips
                value={filter}
                onChange={setFilter}
                options={[
                  { value: 'all', label: `All (${total})` },
                  { value: 'active', label: `Active (${activeCount})` },
                  { value: 'inactive', label: `Inactive (${total - activeCount})` },
                ]}
              />
            </div>
            <input
              className="field field-sm md:w-72"
              placeholder="Search name, contact or tax ID"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              aria-label="Search vendors"
            />
          </div>

          {vendors.loading && !vendors.data ? (
            <Loading />
          ) : vendors.error ? (
            <ErrorState error={vendors.error} onRetry={vendors.reload} />
          ) : (
            <Table
              rows={rows}
              rowKey={(r) => r.vendor_id}
              empty={
                <EmptyState
                  title={total ? 'No vendors match' : 'No vendors yet'}
                  action={!total && <Button onClick={() => setEditing('new')}>Add vendor</Button>}
                />
              }
              columns={[
                { key: 'vendor_id', header: 'ID', render: (r) => <span className="text-muted">#{r.vendor_id}</span> },
                { key: 'vendor_name', header: 'Vendor', render: (r) => <span className="font-bold">{r.vendor_name}</span> },
                { key: 'contact_reference', header: 'Contact' },
                { key: 'tax_id', header: 'Tax ID', render: (r) => <span className="tabular-nums">{r.tax_id}</span> },
                {
                  key: 'active',
                  header: 'Status',
                  render: (r) => <StatusBadge status={r.active ? 'active' : 'inactive'} />,
                },
                { key: 'updated_at', header: 'Updated', render: (r) => <span className="text-muted">{formatDate(r.updated_at)}</span> },
                { key: 'edit', header: '', align: 'right', render: (r) => <TextLink onClick={() => setEditing(r)}>Edit</TextLink> },
              ]}
            />
          )}
        </Section>
      </Container>

      {editing && (
        <VendorModal vendor={editing === 'new' ? null : editing} onClose={() => setEditing(null)} onSaved={onSaved} />
      )}
    </>
  )
}

function VendorModal({ vendor, onClose, onSaved }) {
  const isNew = !vendor
  const [form, setForm] = useState(() => (vendor ? { ...EMPTY, ...vendor } : EMPTY))
  const [errors, setErrors] = useState({})
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(false)

  const set = (f) => (e) => setForm((s) => ({ ...s, [f]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }))

  const validate = () => {
    const e = {}
    if (!form.vendor_name.trim()) e.vendor_name = 'Required'
    else if (form.vendor_name.length > 100) e.vendor_name = 'At most 100 characters'
    if (!form.contact_reference.trim()) e.contact_reference = 'Required'
    else if (form.contact_reference.length > 150) e.contact_reference = 'At most 150 characters'
    if (!form.tax_id.trim()) e.tax_id = 'Required'
    else if (form.tax_id.length > 50) e.tax_id = 'At most 50 characters'
    setErrors(e)
    return !Object.keys(e).length
  }

  const onSubmit = async (e) => {
    e.preventDefault()
    if (!validate()) return
    const data = {
      vendor_name: form.vendor_name.trim(),
      contact_reference: form.contact_reference.trim(),
      tax_id: form.tax_id.trim(),
      active: form.active,
    }
    // The update endpoint rejects nulls, so send only changed fields.
    const payload = isNew ? data : Object.fromEntries(Object.entries(data).filter(([k, v]) => v !== vendor[k]))
    if (!isNew && !Object.keys(payload).length) return onClose()

    setSaving(true)
    setError(null)
    try {
      const saved = isNew ? await vendorsApi.create(payload) : await vendorsApi.update(vendor.vendor_id, payload)
      onSaved(saved, isNew)
    } catch (err) {
      setError(err.status === 409 ? 'A vendor with this contact reference already exists.' : err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      open
      title={isNew ? 'Add vendor' : `Edit ${vendor.vendor_name}`}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button type="submit" form="vendor-form" loading={saving}>
            {isNew ? 'Add vendor' : 'Save changes'}
          </Button>
        </>
      }
    >
      <form id="vendor-form" onSubmit={onSubmit} className="space-y-5" noValidate>
        {error && <Alert tone="error">{error}</Alert>}
        <Field label="Vendor name" error={errors.vendor_name} htmlFor="vn">
          <input id="vn" className={`field ${errors.vendor_name ? 'field-error' : ''}`} value={form.vendor_name} onChange={set('vendor_name')} autoFocus />
        </Field>
        <Field label="Contact reference" error={errors.contact_reference} hint="Billing email or phone. Must be unique." htmlFor="vc">
          <input id="vc" className={`field ${errors.contact_reference ? 'field-error' : ''}`} value={form.contact_reference} onChange={set('contact_reference')} />
        </Field>
        <Field label="Tax ID" error={errors.tax_id} htmlFor="vt">
          <input id="vt" className={`field ${errors.tax_id ? 'field-error' : ''}`} value={form.tax_id} onChange={set('tax_id')} />
        </Field>
        <label className="flex items-center gap-3 cursor-pointer select-none">
          <input type="checkbox" className="size-4 accent-primary" checked={form.active} onChange={set('active')} />
          <span className="text-title-sm">Active</span>
          <span className="text-body-sm text-muted">Inactive vendors are hidden from the upload form.</span>
        </label>
      </form>
    </Modal>
  )
}
