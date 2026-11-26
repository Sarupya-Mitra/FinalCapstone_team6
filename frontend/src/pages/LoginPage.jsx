import { useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { ROLE_HOME, useAuth } from '../auth/AuthContext'
import { Alert, Button, Field } from '../components/ui'
import { Logo } from '../components/Layout'

// Seeded by backend/init_db.py; shown only in development builds.
const DEMO_ACCOUNTS = [
  { role: 'Clerk', email: 'anita.clerk@example.com' },
  { role: 'Approver', email: 'rahul.approver@example.com' },
  { role: 'Auditor', email: 'meera.auditor@example.com' },
]
const DEMO_PASSWORD = 'Password@123'

export default function LoginPage() {
  const { user, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  if (user) return <Navigate to={ROLE_HOME[user.role]} replace />

  const onSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const me = await login(email.trim(), password)
      const from = location.state?.from
      const target = from && from.startsWith(ROLE_HOME[me.role]) ? from : ROLE_HOME[me.role]
      navigate(target, { replace: true })
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen grid lg:grid-cols-[1.1fr_1fr]">
      {/* Dark band */}
      <section className="bg-surface-dark text-white flex flex-col justify-between px-6 sm:px-12 py-10 lg:py-section">
        <p className="label-upper text-on-dark-soft">Capstone Project 06</p>
        <div className="my-12 lg:my-0">
          <h1 className="text-white text-[40px] leading-[1.05] md:text-display-xl">
            Invoice processing,
            <br />
            approved with confidence.
          </h1>
          <p className="mt-6 text-body-md text-on-dark-soft max-w-lg">
            Clerks upload PDF invoices, AI extracts the data, automated checks catch the mistakes, and approvers make
            the final call. Auditors see every step.
          </p>
        </div>
        <div className="grid grid-cols-3 border-t border-surface-dark-elevated pt-6 gap-4">
          {[
            ['Upload', 'PDF invoices'],
            ['Extract', 'with AI'],
            ['Approve', 'with an audit trail'],
          ].map(([a, b]) => (
            <div key={a}>
              <p className="text-title-md text-white">{a}</p>
              <p className="text-body-sm text-on-dark-soft">{b}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Form */}
      <section className="flex items-center justify-center px-4 sm:px-12 py-16">
        <div className="w-full max-w-md">
          <Logo to="/login" />
          <h2 className="mt-10 text-display-md">Sign in</h2>
          <p className="mt-2 text-body-md text-muted">Use your clerk, approver or auditor account.</p>

          <form onSubmit={onSubmit} className="mt-8 space-y-5" noValidate>
            {error && <Alert tone="error">{error}</Alert>}
            <Field label="Email" htmlFor="email">
              <input
                id="email"
                type="email"
                autoComplete="username"
                className="field"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoFocus
              />
            </Field>
            <Field label="Password" htmlFor="password">
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                className="field"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </Field>
            <Button type="submit" className="w-full" loading={submitting} disabled={!email || !password}>
              Sign in
            </Button>
          </form>

          {import.meta.env.DEV && (
            <div className="mt-10 border-t border-hairline pt-6">
              <p className="caption uppercase text-muted mb-3">Demo accounts (development only)</p>
              <div className="flex flex-wrap gap-2">
                {DEMO_ACCOUNTS.map((a) => (
                  <button
                    key={a.email}
                    type="button"
                    onClick={() => {
                      setEmail(a.email)
                      setPassword(DEMO_PASSWORD)
                    }}
                    className="caption px-[14px] py-2 border border-hairline-strong hover:border-ink"
                  >
                    {a.role}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  )
}
