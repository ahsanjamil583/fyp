import {
  ArrowRight,
  BarChart3,
  Bot,
  Check,
  CreditCard,
  Globe,
  MessageCircle,
  Package,
  ShoppingBag,
  Sparkles,
  Store,
  Zap,
} from "lucide-react";
import { Link } from "react-router-dom";

/**
 * Public landing page.
 *
 * Written for a visitor who has never heard of the product: what it does for them and
 * what they get, rather than the internal build/phase language this page used to show.
 */

const FEATURES = [
  {
    icon: Globe,
    tone: "violet",
    title: "A website that builds itself",
    text: "Pick a template, add your products, publish. Your storefront is online the same day — no designer, no developer, no hosting bill.",
  },
  {
    icon: Bot,
    tone: "purple",
    title: "An AI assistant that knows your catalog",
    text: "It answers price and availability questions from your live stock, so customers get the right answer at midnight without you replying.",
  },
  {
    icon: MessageCircle,
    tone: "green",
    title: "WhatsApp that answers itself",
    text: "Connect your business number and let the assistant handle the repetitive questions your customers already send you every day.",
  },
  {
    icon: Package,
    tone: "blue",
    title: "Stock that stays honest",
    text: "Inventory reserves the moment an order is placed, so two customers can never buy the last item. Low-stock alerts reach you before you run out.",
  },
  {
    icon: CreditCard,
    tone: "orange",
    title: "Get paid the way Pakistan pays",
    text: "Cash on delivery, bank transfer, JazzCash, Easypaisa and card — every payment recorded against the right order automatically.",
  },
  {
    icon: BarChart3,
    tone: "violet",
    title: "Know how the day went",
    text: "A daily summary of orders, revenue and low stock, delivered to your WhatsApp so you never have to open a spreadsheet.",
  },
];

const STEPS = [
  { n: "1", title: "Create your business", text: "Tell us your business name and category. We suggest the modules and layout that fit it." },
  { n: "2", title: "Add what you sell", text: "Products or services, with prices, photos and variants. Import a spreadsheet if you already have one." },
  { n: "3", title: "Go live", text: "Publish your storefront, switch on the AI assistant, and start taking orders." },
];

const HERO_FLOW = [
  { label: "Create profile", icon: Store },
  { label: "Add catalog", icon: Package },
  { label: "Publish website", icon: Globe },
  { label: "AI answers", icon: Bot },
  { label: "Track orders", icon: BarChart3 },
];

const BUSINESS_PERKS = [
  "Your own public storefront with a shareable link",
  "AI assistant trained on your own catalog and FAQs",
  "WhatsApp replies handled automatically",
  "Orders, stock and payments in one place",
  "Daily business summary on WhatsApp",
  "Customer records and repeat-order history",
];

const CUSTOMER_PERKS = [
  "Browse every business in one marketplace",
  "Ask the shop a question and get an instant answer",
  "Order without phone calls or back-and-forth",
  "Pay with JazzCash, Easypaisa, card or cash",
  "Track order status from your account",
  "Reorder your favourites in one tap",
];

const FAQ = [
  {
    q: "Do I need technical skills?",
    a: "No. If you can fill in a form and upload a photo, you can run your storefront. There is nothing to install and nothing to host.",
  },
  {
    q: "What does it cost to start?",
    a: "You can create your business and publish a storefront on the free plan. Paid plans add the AI assistant, WhatsApp automation and advanced reporting.",
  },
  {
    q: "Does it work for services, not just products?",
    a: "Yes. Alongside products you can list services and take booking or quote requests instead of direct orders.",
  },
  {
    q: "Can I use my own WhatsApp number?",
    a: "Yes. You link your existing business number, and the assistant replies from it. You can take over any conversation at any time.",
  },
];

const TILE = {
  violet: "bg-brand-100 text-brand",
  purple: "bg-purple-100 text-purple-600",
  green: "bg-green-50 text-green-600",
  blue: "bg-blue-50 text-blue-500",
  orange: "bg-orange-100 text-orange-600",
};

export function LandingPage() {
  return (
    <>
      {/* ------------------------------------------------------------ hero -- */}
      <section className="relative isolate overflow-hidden bg-sidebar-bottom text-white">
        <div
          aria-hidden="true"
          className="calm-motion-field pointer-events-none absolute inset-0"
        />
        <div aria-hidden="true" className="pointer-events-none absolute inset-0 bg-[linear-gradient(90deg,rgba(8,24,39,0.84),rgba(8,24,39,0.48),rgba(8,24,39,0.74))]" />
        <div className="relative mx-auto max-w-7xl px-5 pb-16 pt-14 lg:px-8 lg:pb-24 lg:pt-20">
          <div className="grid items-center gap-12 lg:grid-cols-[1.05fr_0.95fr]">
            <div>
              <span className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/12 px-3.5 py-1.5 text-xs font-bold text-white backdrop-blur">
                <Sparkles size={14} />
                Built for Pakistani businesses
              </span>

              <h1 className="mt-5 text-4xl font-black leading-[1.08] tracking-tight text-white md:text-[3.4rem]">
                BizXusAI helps your shop{" "}
                <span className="kinetic-word text-teal-200">publish,</span>{" "}
                <span className="kinetic-word text-blue-200">answer,</span>{" "}
                <span className="kinetic-word text-orange-100">sell.</span>
              </h1>

              <p className="mt-5 max-w-xl text-lg leading-8 text-white/78">
                BizXusAI gives your business a storefront, an AI assistant that knows your stock, WhatsApp
                replies, and payments — without hiring a developer or paying for five different tools.
              </p>

              <div className="mt-8 flex flex-col gap-3 sm:flex-row">
                <Link to="/register" className="ui-btn-primary !px-6 !py-3.5 !text-base">
                  Start free
                  <ArrowRight size={18} />
                </Link>
                <Link to="/customer/marketplace" className="inline-flex items-center justify-center gap-2 rounded-xl border border-white/25 bg-white/12 px-6 py-3.5 text-base font-bold text-white backdrop-blur transition hover:bg-white/18">
                  <Store size={18} />
                  Browse the marketplace
                </Link>
              </div>

              <ul className="mt-7 flex flex-wrap gap-x-6 gap-y-2">
                {["Free plan available", "No card required", "Live in one day"].map((t) => (
                  <li key={t} className="inline-flex items-center gap-1.5 text-sm font-semibold text-white/78">
                    <Check size={15} className="text-teal-200" strokeWidth={3} />
                    {t}
                  </li>
                ))}
              </ul>
            </div>

            {/* A concrete picture of the product, not a checklist of build phases. */}
            <div className="relative">
              <div className="rounded-card border border-white/18 bg-white/12 p-5 shadow-lift backdrop-blur-md">
                <div className="flex items-center gap-2 border-b border-white/15 pb-3">
                  <span className="h-2.5 w-2.5 rounded-full bg-red-400" />
                  <span className="h-2.5 w-2.5 rounded-full bg-orange-400" />
                  <span className="h-2.5 w-2.5 rounded-full bg-green-400" />
                  <span className="ml-2 truncate text-xs font-semibold text-white/60">
                    bizxus.ai/your-shop
                  </span>
                </div>

                <div className="space-y-3 pt-4">
                  <div className="flex items-start gap-2.5">
                    <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-white/14 text-xs font-bold text-white/70">
                      C
                    </span>
                    <p className="rounded-2xl rounded-tl-sm bg-white/14 px-3.5 py-2.5 text-sm text-white">
                      Grey tracksuit ka price kya hai? Available hai?
                    </p>
                  </div>
                  <div className="flex items-start justify-end gap-2.5">
                    <p className="rounded-2xl rounded-tr-sm bg-white px-3.5 py-2.5 text-sm font-bold text-brand">
                      Grey Tracksuit is PKR 4,800 and in stock. Want me to place the order?
                    </p>
                    <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-sidebar-active text-white">
                      <Bot size={15} />
                    </span>
                  </div>
                </div>

                <div className="mt-4 grid grid-cols-3 gap-2 border-t border-white/15 pt-4">
                  {[
                    { k: "Orders today", v: "12" },
                    { k: "Revenue", v: "PKR 58K" },
                    { k: "Replies sent", v: "47" },
                  ].map((s) => (
                    <div key={s.k} className="rounded-xl bg-white/12 px-3 py-2.5">
                      <div className="text-[10px] font-bold uppercase tracking-wider text-white/55">{s.k}</div>
                      <div className="mt-0.5 text-base font-extrabold text-white">{s.v}</div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="absolute -bottom-4 -left-4 hidden items-center gap-2 rounded-xl border border-white/18 bg-white px-3.5 py-2.5 shadow-card sm:flex">
                <span className="grid h-8 w-8 place-items-center rounded-lg bg-green-50 text-green-600">
                  <Zap size={16} />
                </span>
                <div>
                  <div className="text-xs font-bold text-ink">Answered in 2 seconds</div>
                  <div className="text-[11px] text-subtle">Even at 2am</div>
                </div>
              </div>
            </div>
          </div>

          <div className="mt-10 rounded-card border border-white/18 bg-white/12 p-3 shadow-lift backdrop-blur-md">
            <ol className="grid gap-2 sm:grid-cols-5">
              {HERO_FLOW.map((step, index) => (
                <li key={step.label} className="rounded-xl bg-white/12 px-3 py-3">
                  <div className="flex items-center gap-2">
                    <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-white text-brand">
                      <step.icon size={15} strokeWidth={2.4} />
                    </span>
                    <div className="min-w-0">
                      <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-white/55">
                        Step {index + 1}
                      </div>
                      <div className="truncate text-sm font-extrabold text-white">{step.label}</div>
                    </div>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </div>
      </section>

      {/* -------------------------------------------------------- features -- */}
      <section id="features" className="scroll-mt-20 border-t border-line bg-page py-16 lg:py-24">
        <div className="mx-auto max-w-7xl px-5 lg:px-8">
          <div className="mx-auto max-w-2xl text-center">
            <span className="text-[11px] font-bold uppercase tracking-[0.16em] text-brand">What you get</span>
            <h2 className="mt-2 text-3xl font-black tracking-tight text-ink md:text-4xl">
              Everything your business needs, already connected
            </h2>
            <p className="mt-3 text-base leading-7 text-muted">
              Most businesses stitch together a website, a spreadsheet, a WhatsApp inbox and a receipt book.
              Here they are one system that agrees with itself.
            </p>
          </div>

          <div className="mt-12 grid gap-5 md:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((f) => (
              <article
                key={f.title}
                className="group rounded-card border border-line bg-white p-6 shadow-card transition hover:-translate-y-0.5 hover:shadow-lift"
              >
                <span className={`grid h-12 w-12 place-items-center rounded-xl ${TILE[f.tone]}`}>
                  <f.icon size={22} strokeWidth={2.1} />
                </span>
                <h3 className="mt-4 text-lg font-bold text-ink">{f.title}</h3>
                <p className="mt-2 text-sm leading-7 text-muted">{f.text}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* ----------------------------------------------------- how it works -- */}
      <section id="how-it-works" className="scroll-mt-20 py-16 lg:py-24">
        <div className="mx-auto max-w-7xl px-5 lg:px-8">
          <div className="mx-auto max-w-2xl text-center">
            <span className="text-[11px] font-bold uppercase tracking-[0.16em] text-brand">How it works</span>
            <h2 className="mt-2 text-3xl font-black tracking-tight text-ink md:text-4xl">
              Online in three steps
            </h2>
          </div>

          <div className="relative mt-12 grid gap-6 md:grid-cols-3">
            <div
              aria-hidden="true"
              className="absolute left-[16%] right-[16%] top-7 hidden h-px bg-line md:block"
            />
            {STEPS.map((s) => (
              <div key={s.n} className="relative text-center">
                <span className="mx-auto grid h-14 w-14 place-items-center rounded-full bg-sidebar-active text-xl font-black text-white shadow-nav-active">
                  {s.n}
                </span>
                <h3 className="mt-4 text-lg font-bold text-ink">{s.title}</h3>
                <p className="mx-auto mt-2 max-w-xs text-sm leading-7 text-muted">{s.text}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* --------------------------------------------------------- audience -- */}
      <section id="audience" className="scroll-mt-20 border-t border-line bg-page py-16 lg:py-24">
        <div className="mx-auto max-w-7xl px-5 lg:px-8">
          <div className="grid gap-6 lg:grid-cols-2">
            <PerkCard
              icon={ShoppingBag}
              tone="violet"
              eyebrow="For business owners"
              title="Run the whole shop from one screen"
              perks={BUSINESS_PERKS}
              cta={{ to: "/register", label: "Create your business" }}
              secondary={{ to: "/login", label: "I already have an account" }}
              highlight
            />
            <PerkCard
              icon={Store}
              tone="blue"
              eyebrow="For customers"
              title="Find local businesses and order in seconds"
              perks={CUSTOMER_PERKS}
              cta={{ to: "/customer/register", label: "Create a customer account" }}
              secondary={{ to: "/customer/marketplace", label: "Browse the marketplace" }}
            />
          </div>
        </div>
      </section>

      {/* -------------------------------------------------------------- faq -- */}
      <section id="faq" className="scroll-mt-20 py-16 lg:py-24">
        <div className="mx-auto max-w-3xl px-5 lg:px-8">
          <div className="text-center">
            <span className="text-[11px] font-bold uppercase tracking-[0.16em] text-brand">Questions</span>
            <h2 className="mt-2 text-3xl font-black tracking-tight text-ink md:text-4xl">Before you start</h2>
          </div>
          <div className="mt-10 grid gap-3">
            {FAQ.map((item) => (
              <details
                key={item.q}
                className="group rounded-card border border-line bg-white px-5 py-4 shadow-card [&_summary::-webkit-details-marker]:hidden"
              >
                <summary className="flex cursor-pointer items-center justify-between gap-4 text-base font-bold text-ink">
                  {item.q}
                  <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-surface text-muted transition group-open:rotate-45">
                    +
                  </span>
                </summary>
                <p className="mt-3 text-sm leading-7 text-muted">{item.a}</p>
              </details>
            ))}
          </div>
        </div>
      </section>

      {/* --------------------------------------------------------- final CTA -- */}
      <section className="px-5 pb-20 lg:px-8">
        <div className="mx-auto max-w-7xl overflow-hidden rounded-card bg-ai-card px-6 py-14 text-center shadow-lift lg:px-16">
          <h2 className="text-3xl font-black tracking-tight text-white md:text-4xl">
            Put your business online today
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-base leading-7 text-white/70">
            Create your storefront on the free plan and see how it feels before you pay anything.
          </p>
          <div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row">
            <Link
              to="/register"
              className="inline-flex items-center justify-center gap-2 rounded-xl bg-white px-6 py-3.5 text-base font-bold text-ink transition hover:bg-white/90"
            >
              Start free
              <ArrowRight size={18} />
            </Link>
            <Link
              to="/customer/marketplace"
              className="inline-flex items-center justify-center gap-2 rounded-xl border border-white/25 px-6 py-3.5 text-base font-bold text-white transition hover:bg-white/10"
            >
              See a live storefront
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}

function PerkCard({ icon: Icon, tone, eyebrow, title, perks, cta, secondary, highlight = false }) {
  return (
    <article
      className={`rounded-card border bg-white p-7 shadow-card ${
        highlight ? "border-brand-200 ring-1 ring-brand-200" : "border-line"
      }`}
    >
      <span className={`grid h-12 w-12 place-items-center rounded-xl ${TILE[tone]}`}>
        <Icon size={22} strokeWidth={2.1} />
      </span>
      <div className="mt-4 text-[11px] font-bold uppercase tracking-[0.16em] text-brand">{eyebrow}</div>
      <h3 className="mt-1.5 text-2xl font-black tracking-tight text-ink">{title}</h3>

      <ul className="mt-5 grid gap-2.5">
        {perks.map((p) => (
          <li key={p} className="flex items-start gap-2.5 text-sm leading-6 text-muted">
            <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full bg-green-50 text-green-600">
              <Check size={12} strokeWidth={3.5} />
            </span>
            {p}
          </li>
        ))}
      </ul>

      <div className="mt-7 flex flex-col gap-2 sm:flex-row">
        <Link to={cta.to} className="ui-btn-primary">
          {cta.label}
          <ArrowRight size={16} />
        </Link>
        <Link to={secondary.to} className="ui-btn-secondary">
          {secondary.label}
        </Link>
      </div>
    </article>
  );
}
