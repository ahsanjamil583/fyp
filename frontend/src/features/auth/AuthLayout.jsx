import { BarChart3, Bot, Check, MessageCircle, PackageCheck, ShieldCheck, ShoppingBag, Zap } from "lucide-react";
import { Link } from "react-router-dom";

import { BrandLogo } from "../../components/common/BrandLogo.jsx";

/**
 * The single shell for every authentication screen.
 *
 * Login, register, forced reset and phone reset each used to carry their own split-screen
 * markup and their own copy of `Field`, which is why they drifted apart visually. They all
 * render through this now, so a change lands on all of them at once.
 */

const AUDIENCE = {
  business: {
    headline: "Run your whole business from one workspace.",
    perks: [
      "A storefront you can publish today",
      "An AI assistant that knows your live catalog",
      "WhatsApp replies handled for you",
      "Orders, stock and payments in one place",
    ],
    footnote: "Free plan available. No card required.",
  },
  customer: {
    headline: "Shop local businesses, without the back-and-forth.",
    perks: [
      "Browse every business in one marketplace",
      "Ask a shop anything and get an instant answer",
      "Order in seconds, no phone calls",
      "Pay with JazzCash, Easypaisa, card or cash",
    ],
    footnote: "Free to join. Track every order in one place.",
  },
};

export function AuthLayout({ audience = "business", icon: Icon, title, subtitle, children, footer = null }) {
  const copy = AUDIENCE[audience] || AUDIENCE.business;

  return (
    <div className="auth-shell min-h-screen overflow-hidden bg-page lg:grid lg:grid-cols-[1fr_minmax(480px,560px)]">
      <section className="relative hidden overflow-hidden border-r border-line bg-white/70 p-10 lg:flex lg:flex-col xl:p-14">
        <div
          aria-hidden="true"
          className="auth-ambient pointer-events-none absolute inset-0"
        />
        <div aria-hidden="true" className="auth-grid pointer-events-none absolute inset-0 opacity-[0.32]" />
        <div className="relative flex h-full flex-col">
          <Link to="/" className="inline-flex w-fit items-center gap-3 rounded-2xl">
            <BrandLogo showWordmark={false} className="rounded-2xl border border-line bg-white p-1.5 shadow-card" imageClassName="h-10 w-10" />
            <span className="text-lg font-extrabold tracking-tight text-ink">BizXusAI</span>
          </Link>

          <div className="mt-12 max-w-xl">
            <span className="inline-flex items-center gap-2 rounded-full border border-brand-200 bg-brand-50 px-3.5 py-1.5 text-xs font-bold text-brand">
              <SparkleDot />
              Free plan available. No card required.
            </span>
            <h1 className="mt-5 max-w-lg text-[2.7rem] font-black leading-[1.08] tracking-tight text-ink">
              {copy.headline}
            </h1>
            <p className="mt-4 max-w-md text-base leading-7 text-muted">
              Launch your storefront, answer customers with AI, and keep orders, stock and payments moving from one calm workspace.
            </p>
          </div>

          <ProductPreview audience={audience} />

          <div className="mt-auto flex items-center gap-2 pt-10 text-sm font-semibold text-muted">
            <ShieldCheck size={16} className="text-brand" />
            {copy.footnote}
          </div>
        </div>
      </section>

      <section className="relative flex min-h-screen flex-col">
        <div aria-hidden="true" className="auth-ambient pointer-events-none absolute inset-0 opacity-60 lg:hidden" />
        <div className="relative border-b border-line bg-white/80 px-5 py-4 backdrop-blur lg:hidden">
          <Link to="/" className="inline-flex items-center gap-2.5">
            <BrandLogo showWordmark={false} className="rounded-xl border border-line bg-white p-1 shadow-card" imageClassName="h-8 w-8" />
            <span className="text-base font-extrabold tracking-tight text-ink">BizXusAI</span>
          </Link>
        </div>

        <div className="relative flex flex-1 items-center justify-center px-4 py-8 sm:px-8 sm:py-12">
          <div className="w-full max-w-[420px]">
            <div className="auth-card border border-line bg-white/92 p-6 shadow-lift backdrop-blur-xl sm:p-8">
              <span className="auth-icon grid h-12 w-12 place-items-center rounded-2xl bg-brand-100 text-brand">
                {Icon ? <Icon size={22} strokeWidth={2.1} /> : null}
              </span>
              <h2 className="mt-4 text-2xl font-black tracking-tight text-ink">{title}</h2>
              {subtitle ? <p className="mt-1.5 text-sm leading-6 text-muted">{subtitle}</p> : null}

              <div className="mt-6">{children}</div>
            </div>

            {footer ? <div className="mt-5">{footer}</div> : null}
          </div>
        </div>
      </section>
    </div>
  );
}

function SparkleDot() {
  return <span className="h-2 w-2 rounded-full bg-brand shadow-[0_0_18px_rgba(15,118,110,0.55)]" />;
}

function ProductPreview({ audience }) {
  const isCustomer = audience === "customer";
  return (
    <div className="auth-preview mt-10 max-w-xl">
      <div className="auth-preview-card rounded-card border border-line bg-white/88 p-5 shadow-lift backdrop-blur">
        <div className="flex items-center justify-between gap-3 border-b border-line-soft pb-4">
          <div>
            <div className="text-[11px] font-bold uppercase tracking-[0.18em] text-brand">Live Workspace</div>
            <div className="mt-1 text-sm font-bold text-ink">{isCustomer ? "Smart customer journey" : "Business operations cockpit"}</div>
          </div>
          <span className="rounded-full bg-green-50 px-3 py-1 text-xs font-bold text-green-700">Online</span>
        </div>

        <div className="mt-4 grid gap-3">
          <div className="auth-float-one rounded-2xl border border-line bg-surface px-4 py-3">
            <div className="flex items-start gap-3">
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-brand-100 text-brand">
                <Bot size={17} />
              </span>
              <div>
                <div className="text-sm font-bold text-ink">AI reply ready</div>
                <p className="mt-1 text-xs leading-5 text-muted">
                  Grey Tracksuit is PKR 4,800 and in stock. Want me to place the order?
                </p>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <MiniMetric icon={ShoppingBag} label="Orders today" value="12" />
            <MiniMetric icon={BarChart3} label="Revenue" value="PKR 58K" />
          </div>

          <div className="auth-float-two grid gap-3 rounded-2xl border border-line bg-white px-4 py-3 shadow-card">
            <ActivityRow icon={MessageCircle} label="WhatsApp answered" value="2 sec ago" />
            <ActivityRow icon={PackageCheck} label="Stock reserved" value="3 items" />
            <ActivityRow icon={Zap} label="Storefront live" value="Ready" />
          </div>
        </div>
      </div>

      <ul className="mt-5 grid grid-cols-2 gap-3">
        {(AUDIENCE[audience]?.perks || AUDIENCE.business.perks).slice(0, 4).map((perk) => (
          <li key={perk} className="flex items-start gap-2 rounded-2xl border border-line bg-white/72 px-3 py-2.5 text-xs font-semibold leading-5 text-muted shadow-card backdrop-blur">
            <Check size={14} className="mt-0.5 shrink-0 text-green-600" strokeWidth={3} />
            {perk}
          </li>
        ))}
      </ul>
    </div>
  );
}

function MiniMetric({ icon: Icon, label, value }) {
  return (
    <div className="rounded-2xl border border-line bg-white px-4 py-3 shadow-card">
      <div className="flex items-center gap-2 text-xs font-bold text-subtle">
        <Icon size={14} className="text-brand" />
        {label}
      </div>
      <div className="mt-2 text-xl font-black text-ink">{value}</div>
    </div>
  );
}

function ActivityRow({ icon: Icon, label, value }) {
  return (
    <div className="flex items-center justify-between gap-3 text-sm">
      <span className="flex items-center gap-2 font-semibold text-ink">
        <Icon size={15} className="text-brand" />
        {label}
      </span>
      <span className="text-xs font-bold text-muted">{value}</span>
    </div>
  );
}

/* --------------------------------------------------------------- field -- */

export function AuthField({ icon, label, error, htmlFor, children, hint = "" }) {
  return (
    <div>
      <label htmlFor={htmlFor} className="mb-1.5 block text-sm font-bold text-ink">
        {label}
      </label>
      <div
        className={`auth-field flex items-center gap-2.5 rounded-2xl border bg-white px-3.5 transition focus-within:ring-4 ${
          error
            ? "border-red-300 focus-within:border-red-400 focus-within:ring-red-500/10"
            : "border-line focus-within:border-brand-bright focus-within:ring-brand/12"
        }`}
      >
        {icon ? <span className={error ? "text-red-400" : "text-subtle"}>{icon}</span> : null}
        {children}
      </div>
      {error ? (
        <span className="mt-1.5 block text-xs font-semibold text-red-600">{error}</span>
      ) : hint ? (
        <span className="mt-1.5 block text-xs text-subtle">{hint}</span>
      ) : null}
    </div>
  );
}

/* --------------------------------------------------------------- alerts -- */

export function AuthAlert({ tone = "red", children, actionTo = "", actionLabel = "" }) {
  if (!children) return null;
  const tones = {
    red: "border-red-200 bg-red-50 text-red-700",
    green: "border-green-200 bg-green-50 text-green-700",
    brand: "border-brand-200 bg-brand-50 text-brand-700",
    orange: "border-orange-200 bg-orange-100 text-orange-700",
  };
  return (
    <div
      role={tone === "red" ? "alert" : "status"}
      className={`mb-4 rounded-xl border px-3.5 py-2.5 text-sm font-semibold leading-6 ${tones[tone] || tones.red}`}
    >
      {children}
      {actionTo && actionLabel ? (
        <Link className="ml-1 underline underline-offset-2" to={actionTo}>
          {actionLabel}
        </Link>
      ) : null}
    </div>
  );
}

/* -------------------------------------------------------------- button -- */

export function AuthSubmit({ children, isSubmitting = false, ...rest }) {
  return (
    <button type="submit" disabled={isSubmitting} className="auth-primary-btn ui-btn-primary w-full !py-3.5" {...rest}>
      {isSubmitting ? "Please wait..." : children}
    </button>
  );
}

/* ------------------------------------------------------------- stepper -- */

export function AuthStepper({ steps, activeIndex }) {
  return (
    <ol className="mb-6 flex items-center">
      {steps.map((step, index) => {
        const done = index < activeIndex;
        const current = index === activeIndex;
        return (
          <li key={step.code} className="flex flex-1 items-center last:flex-none">
            <div className="flex items-center gap-2">
              <span
                className={`grid h-7 w-7 shrink-0 place-items-center rounded-full text-xs font-black transition ${
                  done
                    ? "bg-green-500 text-white"
                    : current
                      ? "bg-cta text-white shadow-nav-active"
                      : "bg-surface text-subtle"
                }`}
              >
                {done ? <Check size={13} strokeWidth={3.5} /> : index + 1}
              </span>
              <span
                className={`hidden text-xs font-bold sm:block ${
                  current ? "text-ink" : done ? "text-green-600" : "text-subtle"
                }`}
              >
                {step.label}
              </span>
            </div>
            {index < steps.length - 1 ? (
              <span className={`mx-2 h-px flex-1 ${done ? "bg-green-400" : "bg-line"}`} />
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}

/* ---------------------------------------------------------- cross links -- */

export function AuthFooterLinks({ audience = "business" }) {
  return (
    <div className="rounded-card border border-line bg-white/70 px-5 py-4 text-center text-sm text-muted">
      {audience === "customer" ? (
        <>
          Business owner or admin?{" "}
          <Link className="font-bold text-brand hover:text-brand-hover" to="/login">
            Go to business login
          </Link>
        </>
      ) : (
        <>
          <span className="block">Looking to shop instead?</span>
          <span className="mt-1.5 inline-flex items-center gap-3">
            <Link className="font-bold text-brand hover:text-brand-hover" to="/customer/login">
              Customer login
            </Link>
            <span className="text-line">|</span>
            <Link className="font-bold text-brand hover:text-brand-hover" to="/customer/register">
              Customer register
            </Link>
          </span>
        </>
      )}
    </div>
  );
}
