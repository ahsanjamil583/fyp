export function PlaceholderPage({ title, area, description, actions = [] }) {
  return (
    <section className="space-y-6">
      <div className="flex flex-col gap-4 border-b border-line pb-6 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-brand">{area}</p>
          <h1 className="mt-2 text-3xl font-semibold text-ink">{title}</h1>
          {description ? <p className="mt-3 max-w-2xl text-sm leading-6 text-muted">{description}</p> : null}
        </div>
        {actions.length ? (
          <div className="flex flex-wrap gap-2">
            {actions.map((action) => (
              <a
                key={action.href}
                href={action.href}
                className="rounded-md bg-brand px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-700"
              >
                {action.label}
              </a>
            ))}
          </div>
        ) : null}
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        <div className="rounded-md border border-line bg-surface p-4">
          <div className="text-sm font-semibold text-ink">Backend</div>
          <div className="mt-2 text-sm text-muted">FastAPI foundation is reachable.</div>
        </div>
        <div className="rounded-md border border-line bg-surface p-4">
          <div className="text-sm font-semibold text-ink">Database</div>
          <div className="mt-2 text-sm text-muted">MongoDB health is checked by the API.</div>
        </div>
        <div className="rounded-md border border-line bg-surface p-4">
          <div className="text-sm font-semibold text-ink">Frontend</div>
          <div className="mt-2 text-sm text-muted">Routes and layouts are ready.</div>
        </div>
      </div>
    </section>
  );
}
