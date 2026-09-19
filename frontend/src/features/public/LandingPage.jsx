import {
  ArrowRight,
  BarChart3,
  Bot,
  Check,
  CreditCard,
  Globe,
  MessageCircle,
  Package,
  Sparkles,
  Store,
} from "lucide-react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";

import { BackgroundGlow } from "./components/BackgroundGlow.jsx";
import { HeroAiShowcase } from "./components/HeroAiShowcase.jsx";
import { FeatureCard } from "./components/FeatureCard.jsx";
import { HowItWorksFlow } from "./components/HowItWorksFlow.jsx";
import { AudienceShowcase } from "./components/AudienceShowcase.jsx";
import { FaqAccordion } from "./components/FaqAccordion.jsx";

/**
 * Premium Modern AI SaaS Landing Page for BizXusAI.
 * 
 * Strict content preservation: all titles, descriptions, button labels,
 * and information hierarchy are fully retained while elevating design,
 * typography, interactivity, and animations to world-class startup quality.
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
  {
    n: "1",
    title: "Create your business",
    text: "Tell us your business name and category. We suggest the modules and layout that fit it.",
  },
  {
    n: "2",
    title: "Add what you sell",
    text: "Products or services, with prices, photos and variants. Import a spreadsheet if you already have one.",
  },
  {
    n: "3",
    title: "Go live",
    text: "Publish your storefront, switch on the AI assistant, and start taking orders.",
  },
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

export function LandingPage() {
  return (
    <div className="relative overflow-hidden">
      {/* ------------------------------------------------------------ HERO -- */}
      <section className="relative isolate overflow-hidden border-b border-blue-100 bg-[#f8fbff] pb-20 pt-14 text-slate-950 lg:pb-28 lg:pt-20">
        {/* Modern AI Ambient Glow & Tech Grid */}
        <BackgroundGlow variant="heroLight" />

        <div className="relative mx-auto max-w-7xl px-5 lg:px-8">
          <div className="mx-auto max-w-4xl text-center">
            {/* Left Hero Content */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
            >
              {/* Eyebrow Badge */}
              <div className="inline-flex items-center gap-2 rounded-full border border-blue-100 bg-white px-4 py-1.5 text-xs font-bold text-blue-700 shadow-sm backdrop-blur-md">
                <Sparkles size={14} className="text-blue-500" />
                <span>Built for Pakistani businesses</span>
              </div>

              {/* Display Headline */}
              <h1 className="mt-6 text-4xl font-black leading-[1.05] tracking-tight text-slate-950 sm:text-5xl lg:text-7xl">
                BizXusAI helps your shop{" "}
                <span className="bg-gradient-to-r from-blue-900 via-blue-700 to-sky-600 bg-clip-text text-transparent">
                  publish,
                </span>{" "}
                <span className="bg-gradient-to-r from-blue-800 via-blue-600 to-sky-500 bg-clip-text text-transparent">
                  answer,
                </span>{" "}
                <span className="bg-gradient-to-r from-blue-700 via-sky-600 to-blue-500 bg-clip-text text-transparent">
                  sell.
                </span>
              </h1>

              {/* Subheading */}
              <p className="mx-auto mt-6 max-w-2xl text-base leading-8 text-slate-600 md:text-lg">
                BizXusAI gives your business a storefront, an AI assistant that knows your stock, WhatsApp
                replies, and payments — without hiring a developer or paying for five different tools.
              </p>

              {/* Action Buttons */}
              <div className="mt-9 flex flex-col justify-center gap-3.5 sm:flex-row sm:items-center">
                <Link
                  to="/register"
                  className="ui-btn-primary ai-btn-shimmer !px-7 !py-4 !text-base shadow-[0_0_25px_rgba(37,99,235,0.35)]"
                >
                  Start free
                  <ArrowRight size={18} />
                </Link>
                <Link
                  to="/customer/marketplace"
                  className="inline-flex items-center justify-center gap-2.5 rounded-xl border border-blue-100 bg-white px-7 py-4 text-base font-bold text-slate-800 shadow-sm backdrop-blur-xl transition-all duration-200 hover:border-blue-200 hover:bg-blue-50"
                >
                  <Store size={18} className="text-blue-600" />
                  Browse the marketplace
                </Link>
              </div>

              {/* Trust Indicators */}
              <ul className="mt-8 flex flex-wrap justify-center gap-x-6 gap-y-2.5">
                {["Free plan available", "No card required", "Live in one day"].map((t) => (
                  <li
                    key={t}
                    className="inline-flex items-center gap-2 text-sm font-semibold text-slate-600"
                  >
                    <span className="grid h-4 w-4 place-items-center rounded-full bg-blue-50 text-blue-600 ring-1 ring-blue-100">
                      <Check size={11} strokeWidth={3.5} />
                    </span>
                    {t}
                  </li>
                ))}
              </ul>
            </motion.div>

          </div>

          {/* Interactive AI Product Showcase Animation */}
          <motion.div
            initial={{ opacity: 0, y: 34, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ duration: 0.8, delay: 0.18, ease: [0.16, 1, 0.3, 1] }}
            className="mx-auto mt-14 max-w-5xl"
          >
            <HeroAiShowcase />
          </motion.div>

          {/* 5-Step Hero Flow Pipeline */}
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.3, ease: "easeOut" }}
            className="mx-auto mt-12 max-w-6xl rounded-2xl border border-blue-100 bg-white/80 p-3 shadow-xl backdrop-blur-xl"
          >
            <ol className="grid gap-2 sm:grid-cols-5">
              {HERO_FLOW.map((step, index) => {
                const Icon = step.icon;
                return (
                  <li
                    key={step.label}
                    className="group relative rounded-xl border border-blue-100 bg-white p-3 transition-all duration-300 hover:border-blue-200 hover:bg-blue-50/60"
                  >
                    <div className="flex items-center gap-3">
                      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-gradient-to-tr from-blue-600 to-sky-500 text-white shadow-md transition-transform duration-300 group-hover:scale-110">
                        <Icon size={16} strokeWidth={2.4} />
                      </span>
                      <div className="min-w-0">
                        <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-blue-500">
                          Step {index + 1}
                        </div>
                        <div className="truncate text-sm font-extrabold text-slate-950">
                          {step.label}
                        </div>
                      </div>
                    </div>
                  </li>
                );
              })}
            </ol>
          </motion.div>
        </div>
      </section>

      {/* -------------------------------------------------------- FEATURES -- */}
      <section
        id="features"
        className="relative scroll-mt-20 border-t border-line bg-page py-20 lg:py-28"
      >
        <BackgroundGlow variant="light" />

        <div className="relative mx-auto max-w-7xl px-5 lg:px-8">
          <motion.div
            className="mx-auto max-w-2xl text-center"
            initial={{ opacity: 0, y: 18 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.45 }}
            transition={{ duration: 0.5, ease: "easeOut" }}
          >
            <span className="inline-block rounded-full bg-blue-50 px-3.5 py-1 text-[11px] font-bold uppercase tracking-[0.16em] text-brand">
              What you get
            </span>
            <h2 className="mt-3 text-3xl font-black tracking-tight text-ink md:text-4xl lg:text-5xl">
              Everything your business needs, already connected
            </h2>
            <p className="mt-4 text-base leading-8 text-muted md:text-lg">
              Most businesses stitch together a website, a spreadsheet, a WhatsApp inbox and a receipt
              book. Here they are one system that agrees with itself.
            </p>
          </motion.div>

          <div className="mt-16 grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((f, i) => (
              <FeatureCard
                key={f.title}
                icon={f.icon}
                tone={f.tone}
                title={f.title}
                text={f.text}
                index={i}
              />
            ))}
          </div>
        </div>
      </section>

      {/* ----------------------------------------------------- HOW IT WORKS -- */}
      <section id="how-it-works" className="relative scroll-mt-20 py-20 lg:py-28 bg-white border-t border-line">
        <div className="relative mx-auto max-w-7xl px-5 lg:px-8">
          <motion.div
            className="mx-auto max-w-2xl text-center"
            initial={{ opacity: 0, y: 18 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.45 }}
            transition={{ duration: 0.5, ease: "easeOut" }}
          >
            <span className="inline-block rounded-full bg-blue-50 px-3.5 py-1 text-[11px] font-bold uppercase tracking-[0.16em] text-brand">
              How it works
            </span>
            <h2 className="mt-3 text-3xl font-black tracking-tight text-ink md:text-4xl lg:text-5xl">
              Online in three steps
            </h2>
          </motion.div>

          <HowItWorksFlow steps={STEPS} />
        </div>
      </section>

      {/* --------------------------------------------------------- AUDIENCE -- */}
      <section
        id="audience"
        className="relative scroll-mt-20 border-t border-line bg-page py-20 lg:py-28"
      >
        <BackgroundGlow variant="light" />

        <motion.div
          className="relative mx-auto max-w-7xl px-5 lg:px-8"
          initial={{ opacity: 0, y: 18 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, amount: 0.16 }}
          transition={{ duration: 0.5, ease: "easeOut" }}
        >
          <AudienceShowcase
            businessPerks={BUSINESS_PERKS}
            customerPerks={CUSTOMER_PERKS}
          />
        </motion.div>
      </section>

      {/* -------------------------------------------------------------- FAQ -- */}
      <section id="faq" className="relative scroll-mt-20 border-t border-line bg-white py-20 lg:py-28">
        <div className="mx-auto max-w-3xl px-5 lg:px-8">
          <motion.div
            className="text-center"
            initial={{ opacity: 0, y: 18 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.45 }}
            transition={{ duration: 0.5, ease: "easeOut" }}
          >
            <span className="inline-block rounded-full bg-blue-50 px-3.5 py-1 text-[11px] font-bold uppercase tracking-[0.16em] text-brand">
              Questions
            </span>
            <h2 className="mt-3 text-3xl font-black tracking-tight text-ink md:text-4xl">
              Before you start
            </h2>
          </motion.div>

          <div className="mt-12">
            <FaqAccordion items={FAQ} />
          </div>
        </div>
      </section>

      {/* --------------------------------------------------------- FINAL CTA -- */}
      <section className="relative px-5 pb-24 pt-4 lg:px-8">
        <div className="relative mx-auto max-w-7xl overflow-hidden rounded-3xl bg-gradient-to-br from-[#071329] via-[#091b36] to-[#0d284f] px-7 py-16 text-center text-white shadow-2xl lg:px-20 lg:py-20 border border-white/15">
          {/* Subtle Glow Overlay */}
          <div className="ai-glow-animate pointer-events-none absolute -top-32 left-1/2 h-[350px] w-[600px] -translate-x-1/2 rounded-full bg-blue-600/30 blur-[120px]" />
          <div className="ai-grid-bg pointer-events-none absolute inset-0 opacity-50" />

          <div className="relative z-10 mx-auto max-w-3xl">
            <h2 className="text-3xl font-black tracking-tight text-white md:text-4xl lg:text-5xl">
              Put your business online today
            </h2>
            <p className="mx-auto mt-4 max-w-xl text-base leading-8 text-slate-300 md:text-lg">
              Create your storefront on the free plan and see how it feels before you pay anything.
            </p>

            <div className="mt-9 flex flex-col justify-center gap-3.5 sm:flex-row sm:items-center">
              <Link
                to="/register"
                className="ui-btn-primary ai-btn-shimmer !bg-white !text-slate-900 !px-8 !py-4 !text-base font-extrabold shadow-xl hover:!bg-slate-100"
              >
                Start free
                <ArrowRight size={18} className="text-slate-900" />
              </Link>
              <Link
                to="/customer/marketplace"
                className="inline-flex items-center justify-center gap-2 rounded-xl border border-white/25 bg-white/10 px-8 py-4 text-base font-bold text-white backdrop-blur-xl transition-all hover:bg-white/20"
              >
                See a live storefront
              </Link>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
