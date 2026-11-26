// Thin fetch wrapper around the FastAPI backend.
// All requests go to /api/* which Vite proxies to the backend (see vite.config.js).

const BASE = import.meta.env.VITE_API_BASE || '/api'
const TOKEN_KEY = 'ip_token'

export const tokenStore = {
  get: () => {
    try { return localStorage.getItem(TOKEN_KEY) } catch { return null }
  },
  set: (t) => {
    try { localStorage.setItem(TOKEN_KEY, t) } catch { /* ignore */ }
  },
  clear: () => {
    try { localStorage.removeItem(TOKEN_KEY) } catch { /* ignore */ }
  },
}

export class ApiError extends Error {
  constructor(status, message, detail) {
    super(message)
    this.status = status
    this.detail = detail
  }
}

let onUnauthorized = () => {}
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn
}

// FastAPI errors come as {detail: "text"} or, for 422, {detail: [{loc, msg}, ...]}.
function messageFromDetail(detail, fallback) {
  if (!detail) return fallback
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        const loc = (d.loc || []).filter((p) => p !== 'body').join(' › ')
        return loc ? `${loc}: ${d.msg}` : d.msg
      })
      .join('\n')
  }
  return fallback
}

export async function request(path, { method = 'GET', body, form, formData, query } = {}) {
  const headers = {}
  const token = tokenStore.get()
  if (token) headers.Authorization = `Bearer ${token}`

  let payload
  if (formData) {
    payload = formData
  } else if (form) {
    headers['Content-Type'] = 'application/x-www-form-urlencoded'
    payload = new URLSearchParams(form).toString()
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }

  let url = `${BASE}${path}`
  if (query) {
    const qs = new URLSearchParams(
      Object.entries(query).filter(([, v]) => v !== undefined && v !== null && v !== '')
    ).toString()
    if (qs) url += `?${qs}`
  }

  let res
  try {
    res = await fetch(url, { method, headers, body: payload })
  } catch {
    throw new ApiError(0, 'Cannot reach the server. Is the backend running?')
  }

  const text = await res.text()
  let data = null
  if (text) {
    try { data = JSON.parse(text) } catch { data = text }
  }

  if (!res.ok) {
    if (res.status === 401 && token) onUnauthorized()
    const fallback = res.status >= 500 ? 'Server error. Please try again.' : `Request failed (${res.status})`
    throw new ApiError(res.status, messageFromDetail(data?.detail, fallback), data?.detail)
  }
  return data
}
