import { ButtonLink } from '../components/ui'

export default function NotFoundPage() {
  return (
    <div className="min-h-screen flex flex-col">
      <section className="bg-surface-dark text-white flex-1 flex items-center">
        <div className="mx-auto max-w-[1440px] w-full px-4 sm:px-12 py-section">
          <p className="label-upper text-on-dark-soft">Error 404</p>
          <h1 className="mt-3 text-white text-[40px] md:text-display-xl">Page not found</h1>
          <p className="mt-4 text-body-md text-on-dark-soft">The page you are looking for does not exist.</p>
          <ButtonLink to="/" variant="on-dark" className="mt-8">
            Go to dashboard
          </ButtonLink>
        </div>
      </section>
    </div>
  )
}
