export function PlaceholderPage({ title, area, description, actions = [] }) {
  return (
    <section className="space-y-6">
      <div className="flex flex-col gap-4 border-b border-line-soft pb-5 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-brand">{area}</p>
          <h1 className="mt-1.5 text-2xl font-extrabold tracking-tight text-ink">{title}</h1>
          {description ? <p className="mt-3 max-w-2xl text-sm leading-6 text-muted">{description}</p> : null}
        </div>
        {actions.length ? (
          <div className="flex flex-wrap gap-2">
            {actions.map((action) => (
              <a
                key={action.href}
                href={action.href}
                className="rounded-xl bg-brand px-4 py-2 text-sm font-semibold text-white shadow-card transition hover:bg-brand-700"
              >
                {action.label}
              </a>
            ))}
          </div>
        ) : null}
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        <div className="rounded-xl border border-line bg-surface p-4">
          <div className="text-sm font-semibold text-ink">Backend</div>
          <div className="mt-2 text-sm text-muted">FastAPI foundation is reachable.</div>
        </div>
        <div className="rounded-xl border border-line bg-surface p-4">
          <div className="text-sm font-semibold text-ink">Database</div>
          <div className="mt-2 text-sm text-muted">MongoDB health is checked by the API.</div>
        </div>
        <div className="rounded-xl border border-line bg-surface p-4">
          <div className="text-sm font-semibold text-ink">Frontend</div>
          <div className="mt-2 text-sm text-muted">Routes and layouts are ready.</div>
        </div>
      </div>
    </section>
  );
}
