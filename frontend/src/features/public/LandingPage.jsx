import { ArrowRight, Bot, ClipboardCheck, MessageCircle, ShoppingBag, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";

const features = [
  { icon: ShoppingBag, title: "Launch any business", text: "Use categories, modules, custom fields, catalog items, services, variants, and website sections." },
  { icon: Bot, title: "AI agent brain", text: "Customer portal, public chat, and WhatsApp use the same RAG + catalog + order tool layer." },
  { icon: MessageCircle, title: "WhatsApp-ready", text: "Connect/mock WhatsApp so customer queries that were handled by a person can be answered by the agent." },
  { icon: ClipboardCheck, title: "Final QA dashboard", text: "Run a supervisor-ready checklist before demo, record manual test runs, and verify launch readiness." },
];

export function LandingPage() {
  return (
    <div className="min-h-screen bg-surface">
      <section className="mx-auto max-w-7xl px-6 py-16 lg:py-24">
        <div className="grid gap-12 lg:grid-cols-[1.05fr_0.95fr] lg:items-center">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full bg-primary/10 px-4 py-2 text-sm font-bold text-primary">
              <Sparkles className="h-4 w-4" /> Phase 30 demo-ready build
            </div>
            <h1 className="mt-6 text-4xl font-black tracking-tight text-ink md:text-6xl">
              BizXusAI business automation for Pakistani SMEs
            </h1>
            <p className="mt-5 max-w-2xl text-lg leading-8 text-muted">
              A generalized multi-tenant SaaS platform with public websites, catalog management, RAG knowledge base,
              customer chatbot ordering, WhatsApp agent support, stock/payments, daily reports, and owner AI assistant.
            </p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <Link to="/register" className="inline-flex items-center justify-center gap-2 rounded-xl bg-primary px-5 py-3 text-sm font-bold text-white shadow-sm transition hover:bg-primary-dark">
                Start as Business Owner <ArrowRight className="h-4 w-4" />
              </Link>
              <Link to="/customer/marketplace" className="inline-flex items-center justify-center gap-2 rounded-xl border border-line bg-white px-5 py-3 text-sm font-bold text-ink transition hover:bg-surface">
                Open Marketplace
              </Link>
              <Link to="/businesses/demo-bazaar" className="inline-flex items-center justify-center gap-2 rounded-xl border border-line bg-white px-5 py-3 text-sm font-bold text-ink transition hover:bg-surface">
                Demo Website
              </Link>
            </div>
          </div>

          <div className="rounded-3xl border border-line bg-white p-6 shadow-xl">
            <div className="rounded-2xl bg-gradient-to-br from-primary/10 to-emerald-50 p-6">
              <div className="text-sm font-bold uppercase tracking-wide text-primary">Supervisor demo flow</div>
              <ol className="mt-5 space-y-4 text-sm text-ink">
                {[
                  "Owner logs in with phone OTP.",
                  "Launch Wizard applies Full Agent Demo profile.",
                  "Owner uploads knowledge into RAG.",
                  "Customer asks chatbot to order an item by color/size.",
                  "WhatsApp mock message proves agent replaces manual query handling.",
                  "Payments, stock, reports, and Owner AI are verified from dashboard.",
                ].map((item, index) => (
                  <li key={item} className="flex gap-3">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-white text-xs font-black text-primary shadow-sm">{index + 1}</span>
                    <span>{item}</span>
                  </li>
                ))}
              </ol>
            </div>
          </div>
        </div>

        <div className="mt-14 grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {features.map((feature) => {
            const Icon = feature.icon;
            return (
              <div key={feature.title} className="rounded-2xl border border-line bg-white p-5 shadow-sm">
                <Icon className="h-6 w-6 text-primary" />
                <h2 className="mt-4 font-bold text-ink">{feature.title}</h2>
                <p className="mt-2 text-sm leading-6 text-muted">{feature.text}</p>
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
}
