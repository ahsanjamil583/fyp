import { BarChart3, Bot, Check, Globe2, LockKeyhole, MessageCircle, PackageCheck, ShieldCheck, ShoppingBag } from "lucide-react";
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
    eyebrow: "Business owner access",
    perks: [
      "A storefront you can publish today",
      "An AI assistant that knows your live catalog",
      "WhatsApp replies handled for you",
      "Orders, stock and payments in one place",
    ],
    steps: ["Sign in", "Choose business", "Manage orders"],
    footnote: "Free plan available. No card required.",
  },
  customer: {
    headline: "Shop local businesses, without the back-and-forth.",
    eyebrow: "Customer access",
    perks: [
      "Browse every business in one marketplace",
      "Ask a shop anything and get an instant answer",
      "Order in seconds, no phone calls",
      "Pay with JazzCash, Easypaisa, card or cash",
    ],
    steps: ["Sign in", "Browse stores", "Track orders"],
    footnote: "Free to join. Track every order in one place.",
  },
};

export function AuthLayout({ audience = "business", icon: Icon, title, subtitle, children, footer = null }) {
  const copy = AUDIENCE[audience] || AUDIENCE.business;

  return (
    <div className="auth-shell relative min-h-screen overflow-hidden">
      <div aria-hidden="true" className="auth-ambient pointer-events-none absolute inset-0 opacity-80" />
      <div aria-hidden="true" className="auth-grid pointer-events-none absolute inset-0 opacity-65" />

      <div className="relative mx-auto flex min-h-screen max-w-7xl flex-col px-5 py-5 sm:px-8 lg:px-10">
        <header className="flex items-center justify-between rounded-2xl border border-blue-100 bg-white/90 px-4 py-3 shadow-sm backdrop-blur-xl">
          <Link to="/" className="inline-flex items-center gap-2.5">
            <BrandLogo tone="light" showWordmark={false} imageClassName="h-10 w-10" />
            <span className="text-lg font-extrabold tracking-tight text-ink">BizXusAI</span>
          </Link>
          <Link
            to="/"
            className="rounded-xl border border-blue-100 bg-white px-4 py-2 text-sm font-bold text-slate-700 shadow-sm transition hover:border-blue-200 hover:bg-blue-50 hover:text-blue-700"
          >
            Back to home
          </Link>
        </header>

        <main className="grid flex-1 items-center gap-8 py-8 lg:grid-cols-[minmax(0,1fr)_minmax(390px,480px)] lg:gap-12 lg:py-10">
          <section className="auth-story-panel relative isolate overflow-hidden rounded-[2rem] border border-blue-100 bg-gradient-to-br from-blue-50 via-white to-sky-100/80 p-6 shadow-xl shadow-blue-950/8 backdrop-blur-xl sm:p-8 lg:p-10">
            <div aria-hidden="true" className="pointer-events-none absolute -right-28 -top-28 h-96 w-96 rounded-full bg-blue-200/60 blur-3xl" />
            <div aria-hidden="true" className="pointer-events-none absolute -bottom-28 left-12 h-80 w-80 rounded-full bg-sky-200/50 blur-3xl" />

            <div className="relative">
              <span className="inline-flex items-center gap-2 rounded-full border border-blue-100 bg-white px-3.5 py-1.5 text-xs font-bold text-blue-700 shadow-sm">
                <SparkleDot />
                {copy.eyebrow}
              </span>
              <h1 className="mt-5 max-w-2xl text-4xl font-black leading-[1.08] tracking-tight text-slate-950 sm:text-5xl">
                {copy.headline}
              </h1>
              <p className="mt-4 max-w-xl text-base leading-8 text-slate-600">
                Launch your storefront, answer customers with AI, and keep orders, stock and payments moving from one calm workspace.
              </p>

              <ol className="mt-8 grid gap-3 sm:grid-cols-3">
                {copy.steps.map((step, index) => (
                  <li key={step} className="rounded-2xl border border-blue-100 bg-white/82 px-3 py-3 shadow-sm backdrop-blur">
                    <div className="flex items-center gap-2">
                      <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-blue-600 text-xs font-black text-white shadow-sm">
                        {index + 1}
                      </span>
                      <span className="min-w-0 text-xs font-extrabold text-slate-800">{step}</span>
                    </div>
                  </li>
                ))}
              </ol>

              <ProductPreview audience={audience} />

              <div className="mt-8 flex items-center gap-2 text-sm font-semibold text-slate-600">
                <ShieldCheck size={16} className="text-blue-600" />
                {copy.footnote}
              </div>
            </div>
          </section>

          <section className="relative">
            <div className="auth-card rounded-[2rem] border border-blue-100 bg-white p-6 shadow-2xl shadow-blue-950/12 sm:p-8">
              <div className="flex items-start justify-between gap-4">
                <span className="auth-icon grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-blue-600 text-white shadow-lg shadow-blue-600/20">
                  {Icon ? <Icon size={22} strokeWidth={2.1} /> : null}
                </span>
                <span className="inline-flex items-center gap-1.5 rounded-full border border-blue-100 bg-blue-50 px-3 py-1 text-[11px] font-bold text-blue-700">
                  <LockKeyhole size={12} />
                  Secure login
                </span>
              </div>
              <h2 className="mt-5 text-3xl font-black tracking-tight text-ink">{title}</h2>
              {subtitle ? <p className="mt-2 text-sm leading-6 text-muted">{subtitle}</p> : null}

              <div className="mt-7">{children}</div>
            </div>

            {footer ? <div className="mt-5">{footer}</div> : null}
          </section>
        </main>
      </div>
    </div>
  );
}

function SparkleDot() {
  return <span className="h-2 w-2 rounded-full bg-blue-600 shadow-[0_0_18px_rgba(37,99,235,0.35)]" />;
}

function ProductPreview({ audience }) {
  const isCustomer = audience === "customer";
  return (
    <div className="auth-preview mt-10 max-w-2xl">
        <div className="auth-preview-card rounded-[1.5rem] border border-blue-100 bg-white/92 p-5 shadow-lift backdrop-blur-xl">
        <div className="flex items-center justify-between gap-3 border-b border-blue-100 pb-4">
          <div>
            <div className="text-[11px] font-bold uppercase tracking-[0.18em] text-blue-600">Live Workspace</div>
            <div className="mt-1 text-sm font-bold text-slate-950">{isCustomer ? "Smart customer journey" : "Business operations cockpit"}</div>
          </div>
          <span className="rounded-full bg-blue-50 px-3 py-1 text-xs font-bold text-blue-700">Online</span>
        </div>

        <div className="mt-4 grid gap-3">
          <div className="auth-float-one rounded-2xl border border-blue-100 bg-slate-50 px-4 py-3">
            <div className="flex items-start gap-3">
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-white text-brand shadow-sm">
                <Bot size={17} />
              </span>
              <div>
                <div className="text-sm font-bold text-slate-950">AI reply ready</div>
                <p className="mt-1 text-xs leading-5 text-slate-600">
                  Grey Tracksuit is PKR 4,800 and in stock. Want me to place the order?
                </p>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <MiniMetric icon={ShoppingBag} label="Orders today" value="12" />
            <MiniMetric icon={BarChart3} label="Revenue" value="PKR 58K" />
          </div>

          <div className="auth-float-two grid gap-3 rounded-2xl border border-blue-100 bg-slate-50 px-4 py-3 shadow-card">
            <ActivityRow icon={MessageCircle} label="WhatsApp answered" value="2 sec ago" />
            <ActivityRow icon={PackageCheck} label="Stock reserved" value="3 items" />
            <ActivityRow icon={Globe2} label="Storefront live" value="Ready" />
          </div>
        </div>
      </div>

      <ul className="mt-5 grid grid-cols-2 gap-3">
        {(AUDIENCE[audience]?.perks || AUDIENCE.business.perks).slice(0, 4).map((perk) => (
          <li key={perk} className="flex items-start gap-2 rounded-2xl border border-blue-100 bg-white/82 px-3 py-2.5 text-xs font-semibold leading-5 text-slate-600 shadow-card backdrop-blur">
            <Check size={14} className="mt-0.5 shrink-0 text-blue-600" strokeWidth={3} />
            {perk}
          </li>
        ))}
      </ul>
    </div>
  );
}

function MiniMetric({ icon: Icon, label, value }) {
  return (
    <div className="rounded-2xl border border-blue-100 bg-white px-4 py-3 shadow-card">
      <div className="flex items-center gap-2 text-xs font-bold text-slate-500">
        <Icon size={14} className="text-blue-600" />
        {label}
      </div>
      <div className="mt-2 text-xl font-black text-slate-950">{value}</div>
    </div>
  );
}

function ActivityRow({ icon: Icon, label, value }) {
  return (
    <div className="flex items-center justify-between gap-3 text-sm">
      <span className="flex items-center gap-2 font-semibold text-slate-800">
        <Icon size={15} className="text-blue-600" />
        {label}
      </span>
      <span className="text-xs font-bold text-slate-500">{value}</span>
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
            : "border-blue-100 focus-within:border-blue-400 focus-within:ring-blue-500/10"
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
    green: "border-blue-200 bg-blue-50 text-blue-700",
    brand: "border-blue-200 bg-blue-50 text-blue-700",
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
                    ? "bg-blue-600 text-white"
                    : current
                      ? "bg-cta text-white shadow-nav-active"
                      : "bg-surface text-subtle"
                }`}
              >
                {done ? <Check size={13} strokeWidth={3.5} /> : index + 1}
              </span>
              <span
                className={`hidden text-xs font-bold sm:block ${
                  current ? "text-ink" : done ? "text-blue-600" : "text-subtle"
                }`}
              >
                {step.label}
              </span>
            </div>
            {index < steps.length - 1 ? (
              <span className={`mx-2 h-px flex-1 ${done ? "bg-blue-400" : "bg-line"}`} />
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
    <div className="rounded-2xl border border-blue-100 bg-white/78 px-5 py-4 text-center text-sm text-muted shadow-sm backdrop-blur-xl">
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
