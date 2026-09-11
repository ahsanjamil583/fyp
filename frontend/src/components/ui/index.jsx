/**
 * Shared UI primitives.
 *
 * Pages were each hand-rolling their own headings, cards, pills and empty states, which
 * is why the same idea looked different on every screen. These are the house versions —
 * they encode the colour scheme once so a page only has to say what it means.
 */

import { Link } from "react-router-dom";

import { iconForHeading } from "./SectionTitle.jsx";

/* ------------------------------------------------------------------ card -- */

export function Card({ as: Tag = "div", className = "", padded = true, children, ...rest }) {
  return (
    <Tag className={`ui-card ${padded ? "p-5" : ""} ${className}`.trim()} {...rest}>
      {children}
    </Tag>
  );
}

/* ------------------------------------------------------------- icon tile -- */

const TILE_TONES = {
  violet: "bg-brand-100 text-brand",
  purple: "bg-purple-100 text-purple-600",
  blue: "bg-blue-50 text-blue-500",
  green: "bg-green-50 text-green-600",
  orange: "bg-orange-100 text-orange-600",
  red: "bg-red-50 text-red-500",
  slate: "bg-surface text-muted",
};

export function IconTile({ icon: Icon, tone = "violet", size = 44, className = "" }) {
  return (
    <span
      className={`grid shrink-0 place-items-center rounded-xl ${TILE_TONES[tone] || TILE_TONES.violet} ${className}`.trim()}
      style={{ width: size, height: size }}
    >
      {Icon ? <Icon size={Math.round(size * 0.48)} strokeWidth={2.1} /> : null}
    </span>
  );
}

/* ----------------------------------------------------------------- badge -- */

const BADGE_TONES = {
  green: "bg-green-50 text-green-600",
  orange: "bg-orange-100 text-orange-600",
  purple: "bg-purple-100 text-purple-600",
  violet: "bg-brand-100 text-brand",
  blue: "bg-blue-50 text-blue-600",
  red: "bg-red-50 text-red-600",
  slate: "bg-surface text-muted",
};

export function Badge({ tone = "slate", icon: Icon, className = "", children }) {
  return (
    <span
      className={`inline-flex w-fit items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-bold ${BADGE_TONES[tone] || BADGE_TONES.slate} ${className}`.trim()}
    >
      {Icon ? <Icon size={13} strokeWidth={2.4} /> : null}
      {children}
    </span>
  );
}

/* ---------------------------------------------------------- page header -- */

export function PageHeader({ eyebrow, title, description, icon: Icon, actions = null, children = null }) {
  return (
    <header className="mb-6 border-b border-line-soft pb-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-4">
          {Icon ? <IconTile icon={Icon} size={52} /> : null}
          <div className="min-w-0">
            {eyebrow ? (
              <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-brand">{eyebrow}</p>
            ) : null}
            <h1 className="mt-1.5 text-2xl font-extrabold tracking-tight text-ink">{title}</h1>
            {description ? <p className="mt-2 max-w-2xl text-sm leading-6 text-muted">{description}</p> : null}
          </div>
        </div>
        {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
      {children}
    </header>
  );
}

/* ------------------------------------------------------------ stat tile -- */

/**
 * `icon` and `tone` are optional: when omitted they are derived from the label, so a
 * stat card can never render as a bare label/value box again.
 */
export function StatCard({ label, value, hint, icon, tone, trend = null, className = "" }) {
  const derived = iconForHeading(label);
  const Icon = icon || derived.icon;
  return (
    <Card className={`flex items-start gap-4 transition hover:shadow-lift ${className}`.trim()}>
      <IconTile icon={Icon} tone={tone || derived.tone} />
      <div className="min-w-0">
        <div className="text-xs font-semibold uppercase tracking-[0.1em] text-subtle">{label}</div>
        <div className="mt-1 truncate text-2xl font-extrabold leading-tight text-ink">{value}</div>
        {trend ? (
          <div className={`mt-1 text-xs font-bold ${trend.positive ? "text-green-600" : "text-red-500"}`}>
            {trend.positive ? "▲" : "▼"} {trend.label}
          </div>
        ) : null}
        {hint ? <div className="mt-1 text-xs text-subtle">{hint}</div> : null}
      </div>
    </Card>
  );
}

/* ----------------------------------------------------------- empty state -- */

export function EmptyState({ icon: Icon, title, description, actionLabel, actionTo, onAction }) {
  return (
    <div className="flex flex-col items-center rounded-card border border-dashed border-line bg-surface-purple px-6 py-12 text-center">
      {Icon ? <IconTile icon={Icon} size={56} /> : null}
      <h3 className="mt-4 text-lg font-bold text-ink">{title}</h3>
      {description ? <p className="mt-2 max-w-md text-sm leading-6 text-muted">{description}</p> : null}
      {actionLabel && actionTo ? (
        <Link to={actionTo} className="ui-btn-primary mt-5">
          {actionLabel}
        </Link>
      ) : null}
      {actionLabel && onAction ? (
        <button type="button" onClick={onAction} className="ui-btn-primary mt-5">
          {actionLabel}
        </button>
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------- feedback -- */

export function Alert({ tone = "green", children }) {
  if (!children) return null;
  const tones = {
    green: "border-green-200 bg-green-50 text-green-700",
    red: "border-red-200 bg-red-50 text-red-700",
    orange: "border-orange-200 bg-orange-100 text-orange-700",
    violet: "border-brand-200 bg-brand-100 text-brand-700",
  };
  return (
    <div className={`rounded-xl border px-4 py-3 text-sm font-semibold ${tones[tone] || tones.green}`}>{children}</div>
  );
}

/* --------------------------------------------------------------- layout -- */

export function SectionHeading({ icon: Icon, title, description, actions = null }) {
  return (
    <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
      <div className="flex items-center gap-2.5">
        {Icon ? <Icon size={18} className="text-brand" strokeWidth={2.2} /> : null}
        <div>
          <h2 className="text-base font-bold text-ink">{title}</h2>
          {description ? <p className="text-xs text-muted">{description}</p> : null}
        </div>
      </div>
      {actions}
    </div>
  );
}
