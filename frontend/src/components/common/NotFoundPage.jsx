import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-surface px-6 py-12">
      <div className="max-w-lg rounded-3xl border border-line bg-white p-8 text-center shadow-sm">
        <div className="text-sm font-bold uppercase tracking-wide text-primary">404</div>
        <h1 className="mt-2 text-3xl font-black text-ink">Page not found</h1>
        <p className="mt-3 text-sm leading-6 text-muted">The page you opened does not exist in the current BizXusAI build.</p>
        <div className="mt-6 flex flex-col justify-center gap-3 sm:flex-row">
          <Link to="/" className="rounded-lg bg-primary px-4 py-2 text-sm font-bold text-white">Go Home</Link>
          <Link to="/dashboard/final-qa" className="rounded-lg border border-line px-4 py-2 text-sm font-bold text-ink">Final QA</Link>
        </div>
      </div>
    </div>
  );
}
