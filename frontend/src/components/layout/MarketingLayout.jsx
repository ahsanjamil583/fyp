import { ArrowRight, Menu, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";

import { BrandLogo } from "../common/BrandLogo.jsx";

/**
 * Public marketing chrome: sleek frosted glass navigation and elevated footer
 * inspired by modern AI SaaS benchmarks (AutoBiz AI, Linear, Vercel).
 */

const SECTIONS = [
  { href: "/#features", label: "Features" },
  { href: "/#how-it-works", label: "How it works" },
  { href: "/#audience", label: "Who it's for" },
  { href: "/#faq", label: "FAQ" },
];

export function MarketingLayout() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    function onScroll() {
      setScrolled(window.scrollY > 20);
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    document.body.style.overflow = menuOpen ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [menuOpen]);

  return (
    <div className="min-h-screen bg-page selection:bg-blue-500 selection:text-white">
      {/* ---------------- Sticky Frosted Glass Top Navigation ---------------- */}
      <header
        className={`sticky top-0 z-50 transition-all duration-300 ${
          scrolled
            ? "border-b border-blue-100 bg-white/88 shadow-sm backdrop-blur-xl"
            : "border-b border-blue-50 bg-white/80 backdrop-blur-md"
        }`}
      >
        <nav className="mx-auto flex max-w-7xl items-center gap-6 px-5 py-4 lg:px-8">
          <Link
            to="/"
            className="flex shrink-0 items-center gap-2.5 transition-transform duration-200 hover:scale-[1.02]"
            onClick={() => setMenuOpen(false)}
          >
            <BrandLogo showWordmark={false} imageClassName="h-9 w-9" tone="light" />
            <span className="text-lg font-extrabold tracking-tight text-ink">BizXusAI</span>
          </Link>

          {/* Desktop Navigation Menu */}
          <div className="hidden flex-1 items-center gap-1.5 lg:flex">
            {SECTIONS.map((item) => (
              <a
                key={item.href}
                href={item.href}
                className="rounded-lg px-3.5 py-2 text-sm font-semibold text-slate-600 transition-colors hover:bg-blue-50 hover:text-blue-700"
              >
                {item.label}
              </a>
            ))}
            <NavLink
              to="/customer/marketplace"
              className={({ isActive }) =>
                `rounded-lg px-3.5 py-2 text-sm font-semibold transition-colors ${
                  isActive
                    ? "bg-blue-50 text-blue-700 font-bold"
                    : "text-slate-600 hover:bg-blue-50 hover:text-blue-700"
                }`
              }
            >
              Marketplace
            </NavLink>
          </div>

          {/* Desktop Auth CTAs */}
          <div className="ml-auto hidden items-center gap-3 lg:flex">
            <Link
              to="/login"
              className="rounded-xl px-4 py-2.5 text-sm font-bold text-slate-700 transition-colors hover:bg-blue-50 hover:text-blue-700"
            >
              Log in
            </Link>
            <Link
              to="/register"
              className="ui-btn-primary ai-btn-shimmer !py-2.5 !px-5 !text-sm shadow-[0_0_20px_rgba(37,99,235,0.35)]"
            >
              Get started free
              <ArrowRight size={15} />
            </Link>
          </div>

          {/* Mobile Menu Button */}
          <button
            type="button"
            onClick={() => setMenuOpen((v) => !v)}
            className="ml-auto grid h-10 w-10 place-items-center rounded-xl border border-blue-100 bg-white text-slate-800 shadow-sm transition hover:bg-blue-50 lg:hidden"
            aria-label={menuOpen ? "Close menu" : "Open menu"}
            aria-expanded={menuOpen}
          >
            {menuOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </nav>

        {/* Mobile Dropdown Menu with Framer Motion */}
        <AnimatePresence>
          {menuOpen && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.25, ease: "easeInOut" }}
              className="overflow-hidden border-t border-blue-100 bg-white/95 px-5 pb-6 pt-3 shadow-lg backdrop-blur-2xl lg:hidden"
            >
              <div className="flex flex-col space-y-1">
                {SECTIONS.map((item) => (
                  <a
                    key={item.href}
                    href={item.href}
                    onClick={() => setMenuOpen(false)}
                    className="rounded-lg px-3 py-3 text-sm font-semibold text-slate-700 transition hover:bg-blue-50 hover:text-blue-700"
                  >
                    {item.label}
                  </a>
                ))}
                <Link
                  to="/customer/marketplace"
                  onClick={() => setMenuOpen(false)}
                  className="rounded-lg px-3 py-3 text-sm font-semibold text-slate-700 transition hover:bg-blue-50 hover:text-blue-700"
                >
                  Marketplace
                </Link>
              </div>
              <div className="mt-4 grid gap-2.5 border-t border-blue-100 pt-4">
                <Link
                  to="/login"
                  onClick={() => setMenuOpen(false)}
                  className="inline-flex items-center justify-center rounded-xl border border-blue-100 bg-white px-4 py-3 text-sm font-bold text-slate-800 transition hover:bg-blue-50"
                >
                  Log in
                </Link>
                <Link
                  to="/register"
                  onClick={() => setMenuOpen(false)}
                  className="ui-btn-primary ai-btn-shimmer !py-3 text-sm"
                >
                  Get started free
                  <ArrowRight size={16} />
                </Link>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </header>

      {/* Main Page Body */}
      <main>
        <Outlet />
      </main>

      {/* ---------------- Elevated Footer ---------------- */}
      <footer className="border-t border-line bg-[#070e1c] text-slate-400">
        <div className="mx-auto max-w-7xl px-5 py-14 lg:px-8 lg:py-16">
          <div className="grid gap-12 md:grid-cols-[1.5fr_1fr_1fr_1fr]">
            <div>
              <div className="flex items-center gap-2.5">
                <BrandLogo showWordmark={false} imageClassName="h-9 w-9" tone="dark" />
                <span className="text-lg font-extrabold tracking-tight text-white">BizXusAI</span>
              </div>
              <p className="mt-4 max-w-sm text-sm leading-relaxed text-slate-400">
                Websites, orders, payments and an AI assistant for Pakistani businesses — in one
                workspace.
              </p>
            </div>

            <FooterColumn
              title="Product"
              links={[
                { to: "/#features", label: "Features" },
                { to: "/#how-it-works", label: "How it works" },
                { to: "/customer/marketplace", label: "Marketplace" },
              ]}
            />
            <FooterColumn
              title="Business"
              links={[
                { to: "/register", label: "Create account" },
                { to: "/login", label: "Business login" },
              ]}
            />
            <FooterColumn
              title="Customers"
              links={[
                { to: "/customer/register", label: "Customer register" },
                { to: "/customer/login", label: "Customer login" },
              ]}
            />
          </div>

          <div className="mt-14 flex flex-col gap-3 border-t border-white/10 pt-8 text-xs text-slate-500 sm:flex-row sm:items-center sm:justify-between">
            <span>© 2026 BizXusAI. Built as a modern SaaS business platform.</span>
            <span className="inline-flex items-center gap-1.5 font-bold uppercase tracking-[0.14em] text-slate-400">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
              Automation first · Pakistan ready
            </span>
          </div>
        </div>
      </footer>
    </div>
  );
}

function FooterColumn({ title, links }) {
  return (
    <div>
      <div className="text-xs font-bold uppercase tracking-[0.16em] text-slate-300">{title}</div>
      <div className="mt-4 grid gap-2.5">
        {links.map((l) =>
          l.to.startsWith("/#") ? (
            <a
              key={l.to}
              href={l.to}
              className="text-sm font-semibold text-slate-400 transition hover:text-sky-300"
            >
              {l.label}
            </a>
          ) : (
            <Link
              key={l.to}
              to={l.to}
              className="text-sm font-semibold text-slate-400 transition hover:text-sky-300"
            >
              {l.label}
            </Link>
          ),
        )}
      </div>
    </div>
  );
}
