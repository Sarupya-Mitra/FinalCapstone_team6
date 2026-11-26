import { Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import { HomeRedirect, RequireAuth } from './auth/guards'
import LoginPage from './pages/LoginPage'
import NotFoundPage from './pages/NotFoundPage'
import ClerkInvoicesPage from './pages/clerk/ClerkInvoicesPage'
import UploadInvoicePage from './pages/clerk/UploadInvoicePage'
import InvoiceReviewPage from './pages/clerk/InvoiceReviewPage'
import VendorsPage from './pages/clerk/VendorsPage'
import ApprovalQueuePage from './pages/approver/ApprovalQueuePage'
import ApprovalDetailPage from './pages/approver/ApprovalDetailPage'
import AuditListPage from './pages/auditor/AuditListPage'
import AuditDetailPage from './pages/auditor/AuditDetailPage'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<HomeRedirect />} />

      <Route element={<RequireAuth role="clerk" />}>
        <Route element={<Layout />}>
          <Route path="/clerk" element={<ClerkInvoicesPage />} />
          <Route path="/clerk/upload" element={<UploadInvoicePage />} />
          <Route path="/clerk/invoices/:id" element={<InvoiceReviewPage />} />
          <Route path="/clerk/vendors" element={<VendorsPage />} />
        </Route>
      </Route>

      <Route element={<RequireAuth role="approver" />}>
        <Route element={<Layout />}>
          <Route path="/approver" element={<ApprovalQueuePage />} />
          <Route path="/approver/invoices/:id" element={<ApprovalDetailPage />} />
        </Route>
      </Route>

      <Route element={<RequireAuth role="auditor" />}>
        <Route element={<Layout />}>
          <Route path="/auditor" element={<AuditListPage />} />
          <Route path="/auditor/invoices/:id" element={<AuditDetailPage />} />
        </Route>
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}
