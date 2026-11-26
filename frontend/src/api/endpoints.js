// One function per backend endpoint. If the backend contract changes,
// this is the only file that should need updating.
import { request, requestBlob } from './client'

export const authApi = {
  // OAuth2 password flow: form-encoded username/password
  login: (email, password) =>
    request('/auth/login', { method: 'POST', form: { username: email, password } }),
  me: () => request('/auth/me'),
}

export const vendorsApi = {
  list: () => request('/vendors/'),
  get: (id) => request(`/vendors/${id}`),
  create: (data) => request('/vendors/', { method: 'POST', body: data }),
  update: (id, data) => request(`/vendors/${id}`, { method: 'PUT', body: data }),
}

export const invoicesApi = {
  // query: { vendor_id, status, limit, offset }
  list: (query) => request('/invoices/', { query }),
  get: (id) => request(`/invoices/${id}`),
  upload: (vendorId, file) => {
    const fd = new FormData()
    fd.append('vendor_id', vendorId)
    fd.append('file', file)
    return request('/invoices/', { method: 'POST', formData: fd })
  },
  extract: (id) => request(`/invoices/${id}/extract`, { method: 'POST' }),
  review: (id) => request(`/invoices/${id}/review`),
  saveCorrections: (id, data) => request(`/invoices/${id}/review`, { method: 'PUT', body: data }),
  submit: (id) => request(`/invoices/${id}/submit`, { method: 'POST' }),
  pdf: (id) => requestBlob(`/invoices/${id}/pdf`),
}

export const approvalsApi = {
  // query: { limit, offset }
  pending: (query) => request('/approvals/', { query }),
  get: (id) => request(`/approvals/${id}`),
  checks: (id) => request(`/approvals/${id}/checks`),
  history: (id) => request(`/approvals/${id}/history`),
  decide: (id, decision, note) =>
    request(`/approvals/${id}/decision`, { method: 'POST', body: { decision, note } }),
  pdf: (id) => requestBlob(`/approvals/${id}/pdf`),
}

export const auditorApi = {
  // query: { status, limit, offset }
  list: (query) => request('/auditor/invoices', { query }),
  get: (id) => request(`/auditor/invoices/${id}`),
  pdf: (id) => requestBlob(`/auditor/invoices/${id}/pdf`),
}
