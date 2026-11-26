import { useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { invoicesApi } from '../../api/endpoints'
import { useVendors } from '../../components/invoice'
import { Alert, Button, Container, Field, Hero, Section, Spinner } from '../../components/ui'
import { formatBytes } from '../../lib/format'

const MAX_BYTES = 10 * 1024 * 1024 // matches MAX_FILE_SIZE in backend/app/core/config.py

export default function UploadInvoicePage() {
  const navigate = useNavigate()
  const { vendors, loading: vendorsLoading, error: vendorsError } = useVendors()
  const activeVendors = vendors.filter((v) => v.active)
  const inputRef = useRef(null)

  const [vendorId, setVendorId] = useState('')
  const [file, setFile] = useState(null)
  const [autoExtract, setAutoExtract] = useState(true)
  const [dragging, setDragging] = useState(false)
  const [step, setStep] = useState(null) // null | 'upload' | 'extract'
  const [error, setError] = useState(null)
  const [fieldErrors, setFieldErrors] = useState({})

  const pickFile = (f) => {
    setError(null)
    if (!f) return
    const errs = {}
    if (!f.name.toLowerCase().endsWith('.pdf')) errs.file = 'Only PDF files are allowed.'
    else if (f.size > MAX_BYTES) errs.file = `File is ${formatBytes(f.size)}; the limit is 10 MB.`
    else if (f.size === 0) errs.file = 'The file is empty.'
    setFieldErrors((e) => ({ ...e, file: errs.file }))
    setFile(errs.file ? null : f)
  }

  const onSubmit = async (e) => {
    e.preventDefault()
    const errs = {}
    if (!vendorId) errs.vendor = 'Choose the vendor that issued this invoice.'
    if (!file) errs.file = fieldErrors.file || 'Choose a PDF file.'
    setFieldErrors(errs)
    if (Object.keys(errs).length) return

    setError(null)
    setStep('upload')
    let invoice
    try {
      invoice = await invoicesApi.upload(vendorId, file)
    } catch (err) {
      setError({ message: err.message, duplicate: err.status === 409 ? err.detail : null })
      setStep(null)
      return
    }

    let extractResult = null
    if (autoExtract) {
      setStep('extract')
      try {
        extractResult = await invoicesApi.extract(invoice.invoice_id)
      } catch (err) {
        extractResult = { status: 'failed', message: err.message }
      }
    }
    navigate(`/clerk/invoices/${invoice.invoice_id}`, { state: { justUploaded: true, extractResult } })
  }

  const busy = step !== null

  return (
    <>
      <Hero eyebrow="Clerk · New invoice" title="Upload an invoice">
        PDF only, up to 10 MB. The file is compressed and stored, then AI reads the invoice fields and line items.
      </Hero>

      <Container>
        <Section>
          <form onSubmit={onSubmit} className="grid lg:grid-cols-[1fr_360px] gap-10" noValidate>
            <div className="space-y-6">
              {error && (
                <Alert tone="error" title={error.duplicate ? 'Already uploaded' : 'Upload failed'}>
                  {error.message}
                  {error.duplicate?.uploaded_by_you && (
                    <>
                      {' '}
                      <Link
                        to={`/clerk/invoices/${error.duplicate.duplicate_invoice_id}`}
                        className="text-primary font-bold"
                      >
                        Open invoice #{error.duplicate.duplicate_invoice_id}
                      </Link>
                    </>
                  )}
                </Alert>
              )}
              {vendorsError && <Alert tone="error">Could not load vendors: {vendorsError.message}</Alert>}

              <Field
                label="Vendor"
                htmlFor="vendor"
                error={fieldErrors.vendor}
                hint={
                  <>
                    Vendor not listed?{' '}
                    <Link to="/clerk/vendors" className="text-primary font-normal">
                      Add a vendor
                    </Link>
                  </>
                }
              >
                <select
                  id="vendor"
                  className={`field ${fieldErrors.vendor ? 'field-error' : ''}`}
                  value={vendorId}
                  onChange={(e) => {
                    setVendorId(e.target.value)
                    setFieldErrors((x) => ({ ...x, vendor: undefined }))
                  }}
                  disabled={busy || vendorsLoading}
                >
                  <option value="">{vendorsLoading ? 'Loading vendors…' : 'Select a vendor'}</option>
                  {activeVendors.map((v) => (
                    <option key={v.vendor_id} value={v.vendor_id}>
                      {v.vendor_name} · {v.tax_id}
                    </option>
                  ))}
                </select>
              </Field>

              <Field label="Invoice PDF" error={fieldErrors.file}>
                <div
                  onDragOver={(e) => {
                    e.preventDefault()
                    setDragging(true)
                  }}
                  onDragLeave={() => setDragging(false)}
                  onDrop={(e) => {
                    e.preventDefault()
                    setDragging(false)
                    if (!busy) pickFile(e.dataTransfer.files?.[0])
                  }}
                  onClick={() => !busy && inputRef.current?.click()}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && inputRef.current?.click()}
                  className={`border border-dashed px-6 py-14 text-center transition-colors ${
                    dragging
                      ? 'border-primary bg-[#eff5fd]'
                      : fieldErrors.file
                        ? 'border-error bg-surface-card'
                        : 'border-hairline-strong bg-surface-card hover:border-ink'
                  }`}
                >
                  <input
                    ref={inputRef}
                    type="file"
                    accept="application/pdf,.pdf"
                    className="hidden"
                    onChange={(e) => {
                      pickFile(e.target.files?.[0])
                      e.target.value = ''
                    }}
                  />
                  {file ? (
                    <div>
                      <p className="text-title-md">{file.name}</p>
                      <p className="mt-1 text-body-sm text-muted">{formatBytes(file.size)} · click to choose another file</p>
                    </div>
                  ) : (
                    <div>
                      <svg viewBox="0 0 24 24" className="size-10 mx-auto text-muted" fill="none" stroke="currentColor" strokeWidth="1.4">
                        <path d="M12 16V4M7 9l5-5 5 5M4 16v4h16v-4" />
                      </svg>
                      <p className="mt-4 text-title-sm">Drop a PDF here or click to browse</p>
                      <p className="mt-1 text-body-sm text-muted">One file at a time, up to 10 MB</p>
                    </div>
                  )}
                </div>
              </Field>

              <label className="flex items-start gap-3 cursor-pointer select-none">
                <input
                  type="checkbox"
                  className="mt-1 size-4 accent-primary"
                  checked={autoExtract}
                  onChange={(e) => setAutoExtract(e.target.checked)}
                  disabled={busy}
                />
                <span>
                  <span className="block text-title-sm">Run AI extraction right away</span>
                  <span className="block text-body-sm text-muted">
                    Otherwise you can start the extraction from the invoice page.
                  </span>
                </span>
              </label>

              <div className="flex flex-wrap gap-3 pt-2">
                <Button type="submit" loading={busy}>
                  {step === 'upload' ? 'Uploading…' : step === 'extract' ? 'Extracting with AI…' : 'Upload invoice'}
                </Button>
                <Button type="button" variant="secondary" onClick={() => navigate('/clerk')} disabled={busy}>
                  Cancel
                </Button>
              </div>
            </div>

            <aside className="bg-surface-soft p-6 h-fit">
              <p className="label-upper text-muted mb-5">What happens next</p>
              <ol className="space-y-5">
                {[
                  ['Upload', 'The PDF is checked, compressed and stored.', 'upload'],
                  ['AI extraction', 'Invoice fields and line items are read from the PDF.', 'extract'],
                  ['Your review', 'You check the extracted data and correct mistakes.'],
                  ['Submit', 'Automated checks run and the invoice goes to an approver.'],
                ].map(([t, d, key], i) => (
                  <li key={t} className="flex gap-4">
                    <span
                      className={`grid place-items-center size-7 shrink-0 text-[12px] font-bold ${
                        step === key ? 'bg-primary text-white' : 'bg-canvas text-ink border border-hairline-strong'
                      }`}
                    >
                      {step === key ? <Spinner className="size-3.5" /> : i + 1}
                    </span>
                    <div>
                      <p className="text-title-sm">{t}</p>
                      <p className="text-body-sm text-muted">{d}</p>
                    </div>
                  </li>
                ))}
              </ol>
            </aside>
          </form>
        </Section>
      </Container>
    </>
  )
}
