import { motion } from "framer-motion";
import {
  ArrowRight,
  Bot,
  Check,
  CheckCircle2,
  Package,
  Search,
  ShoppingBag,
  Store,
  Truck,
} from "lucide-react";
import { Link } from "react-router-dom";

export function AudienceShowcase({ businessPerks, customerPerks }) {
  return (
    <motion.div
      className="grid gap-8 lg:grid-cols-2"
      initial="hidden"
      whileInView="show"
      viewport={{ once: true, amount: 0.18 }}
      variants={{
        hidden: {},
        show: {
          transition: {
            staggerChildren: 0.1,
          },
        },
      }}
    >
      {/* ---------------- Business Owner Flagship Card ---------------- */}
      <motion.article
        variants={{
          hidden: { opacity: 0, y: 28 },
          show: {
            opacity: 1,
            y: 0,
            transition: { duration: 0.55, ease: "easeOut" },
          },
        }}
        whileHover={{ y: -4, transition: { duration: 0.3 } }}
        className="group relative flex flex-col justify-between overflow-hidden rounded-[1.6rem] border border-blue-200/80 bg-gradient-to-b from-white via-white to-blue-50/40 p-7 shadow-card transition-all duration-300 hover:border-brand-400 hover:shadow-xl md:p-9"
      >
        {/* Ambient Top Glow */}
        <div className="pointer-events-none absolute -right-20 -top-20 h-56 w-56 rounded-full bg-blue-500/10 blur-3xl transition-opacity duration-300 group-hover:opacity-100" />
        <div className="pointer-events-none absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-blue-600 via-sky-400 to-indigo-600" />

        <div>
          {/* Header */}
          <div className="flex items-center justify-between">
            <span className="grid h-14 w-14 place-items-center rounded-2xl bg-blue-600 text-white shadow-[0_8px_20px_-4px_rgba(37,99,235,0.5)]">
              <ShoppingBag size={26} strokeWidth={2} />
            </span>
            <span className="rounded-full border border-blue-500/30 bg-blue-50 px-3 py-1 text-xs font-bold text-brand">
              Merchant Workspace
            </span>
          </div>

          <div className="mt-5 text-[11px] font-bold uppercase tracking-[0.16em] text-brand">
            For business owners
          </div>
          <h3 className="mt-1.5 text-2xl font-black tracking-tight text-ink md:text-3xl">
            Run the whole shop from one screen
          </h3>

          {/* Interactive Mini-Dashboard Preview: Storefront, AI, Orders, Payments */}
          <div className="mt-6 overflow-hidden rounded-2xl border border-line bg-surface p-4 shadow-sm">
            <div className="flex items-center justify-between border-b border-line-soft pb-3">
              <div className="flex items-center gap-2">
                <span className="flex h-2.5 w-2.5 rounded-full bg-sky-500 ring-4 ring-sky-500/20" />
                <span className="text-xs font-bold text-ink">Storefront: Online</span>
              </div>
              <span className="inline-flex items-center gap-1 rounded-md bg-blue-100 px-2 py-0.5 text-[10px] font-bold text-brand">
                <Bot size={11} />
                AI Assistant Active
              </span>
            </div>

            <div className="mt-3 space-y-2">
              <div className="flex items-center justify-between rounded-xl bg-white p-2.5 text-xs shadow-sm">
                <div className="flex items-center gap-2">
                  <span className="grid h-6 w-6 place-items-center rounded-lg bg-blue-50 text-blue-600">
                    <CheckCircle2 size={13} />
                  </span>
                  <div>
                    <div className="font-bold text-ink">Order #BX-9042 · Tracksuit</div>
                    <div className="text-[10px] text-muted">JazzCash Verified · Reserved</div>
                  </div>
                </div>
                <div className="text-right">
                  <div className="font-extrabold text-brand">PKR 4,800</div>
                  <div className="text-[10px] text-blue-600">Paid</div>
                </div>
              </div>

              <div className="flex items-center justify-between rounded-xl bg-white p-2.5 text-xs shadow-sm">
                <div className="flex items-center gap-2">
                  <span className="grid h-6 w-6 place-items-center rounded-lg bg-sky-50 text-sky-600">
                    <Package size={13} />
                  </span>
                  <div>
                    <div className="font-bold text-ink">Inventory Sync</div>
                    <div className="text-[10px] text-muted">WhatsApp auto-deducted stock</div>
                  </div>
                </div>
                <span className="text-[11px] font-bold text-ink">4 units left</span>
              </div>
            </div>
          </div>

          {/* Perks list */}
          <ul className="mt-6 grid gap-3">
            {businessPerks.map((p) => (
              <li key={p} className="flex items-start gap-3 text-sm leading-6 text-muted">
                <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full bg-blue-100 text-brand">
                  <Check size={12} strokeWidth={3.5} />
                </span>
                <span>{p}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* CTA Actions */}
        <div className="mt-8 flex flex-col gap-3 sm:flex-row">
          <Link to="/register" className="ui-btn-primary ai-btn-shimmer !py-3 !text-sm">
            Create your business
            <ArrowRight size={16} />
          </Link>
          <Link to="/login" className="ui-btn-secondary !py-3 !text-sm">
            I already have an account
          </Link>
        </div>
      </motion.article>

      {/* ---------------- Customer Flagship Card ---------------- */}
      <motion.article
        variants={{
          hidden: { opacity: 0, y: 28 },
          show: {
            opacity: 1,
            y: 0,
            transition: { duration: 0.55, ease: "easeOut" },
          },
        }}
        whileHover={{ y: -4, transition: { duration: 0.3 } }}
        className="group relative flex flex-col justify-between overflow-hidden rounded-[1.6rem] border border-blue-100 bg-gradient-to-b from-white via-white to-sky-50/30 p-7 shadow-card transition-all duration-300 hover:border-sky-400 hover:shadow-xl md:p-9"
      >
        {/* Ambient Top Glow */}
        <div className="pointer-events-none absolute -right-20 -top-20 h-56 w-56 rounded-full bg-sky-500/10 blur-3xl transition-opacity duration-300 group-hover:opacity-100" />
        <div className="pointer-events-none absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-sky-400 via-blue-500 to-indigo-500" />

        <div>
          {/* Header */}
          <div className="flex items-center justify-between">
            <span className="grid h-14 w-14 place-items-center rounded-2xl bg-sky-500 text-white shadow-[0_8px_20px_-4px_rgba(14,165,233,0.5)]">
              <Store size={26} strokeWidth={2} />
            </span>
            <span className="rounded-full border border-sky-500/30 bg-sky-50 px-3 py-1 text-xs font-bold text-sky-700">
              Buyer Experience
            </span>
          </div>

          <div className="mt-5 text-[11px] font-bold uppercase tracking-[0.16em] text-brand">
            For customers
          </div>
          <h3 className="mt-1.5 text-2xl font-black tracking-tight text-ink md:text-3xl">
            Find local businesses and order in seconds
          </h3>

          {/* Interactive Mini-Marketplace & Order Tracking Preview */}
          <div className="mt-6 overflow-hidden rounded-2xl border border-line bg-surface p-4 shadow-sm">
            {/* Search Simulation */}
            <div className="flex items-center gap-2 rounded-xl border border-line bg-white px-3 py-2 text-xs text-muted shadow-sm">
              <Search size={14} className="text-brand" />
              <span className="text-ink">Grey tracksuit, fashion, footwear...</span>
              <span className="ml-auto rounded bg-blue-50 px-1.5 py-0.5 text-[10px] font-semibold text-brand">
                Search
              </span>
            </div>

            {/* Order Tracking Simulation */}
            <div className="mt-3 rounded-xl bg-white p-3 shadow-sm">
              <div className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-2 font-bold text-ink">
                  <Truck size={14} className="text-sky-600" />
                  <span>Order #BX-9042 Tracking</span>
                </div>
                <span className="rounded-full bg-blue-50 px-2 py-0.5 text-[10px] font-bold text-blue-600">
                  Dispatched
                </span>
              </div>

              {/* Progress Tracker */}
              <div className="mt-3 flex items-center justify-between text-[10px] font-medium text-muted">
                <div className="flex items-center gap-1 font-bold text-blue-600">
                  <span className="h-2 w-2 rounded-full bg-blue-500" />
                  <span>Confirmed</span>
                </div>
                <div className="h-0.5 flex-1 mx-2 bg-blue-500" />
                <div className="flex items-center gap-1 font-bold text-sky-600">
                  <span className="h-2 w-2 rounded-full bg-sky-500" />
                  <span>On the way</span>
                </div>
                <div className="h-0.5 flex-1 mx-2 bg-line" />
                <div className="flex items-center gap-1 text-muted">
                  <span className="h-2 w-2 rounded-full bg-line" />
                  <span>Delivered</span>
                </div>
              </div>
            </div>
          </div>

          {/* Perks list */}
          <ul className="mt-6 grid gap-3">
            {customerPerks.map((p) => (
              <li key={p} className="flex items-start gap-3 text-sm leading-6 text-muted">
                <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full bg-sky-100 text-sky-700">
                  <Check size={12} strokeWidth={3.5} />
                </span>
                <span>{p}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* CTA Actions */}
        <div className="mt-8 flex flex-col gap-3 sm:flex-row">
          <Link to="/customer/register" className="ui-btn-primary ai-btn-shimmer !py-3 !text-sm">
            Create a customer account
            <ArrowRight size={16} />
          </Link>
          <Link to="/customer/marketplace" className="ui-btn-secondary !py-3 !text-sm">
            Browse the marketplace
          </Link>
        </div>
      </motion.article>
    </motion.div>
  );
}
