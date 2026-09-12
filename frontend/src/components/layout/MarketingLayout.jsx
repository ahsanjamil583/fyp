import { ArrowRight, Menu, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";

import { BrandLogo } from "../common/BrandLogo.jsx";

/**
 * Public marketing chrome: a top navigation bar, not the dashboard rail.
 *
 * The landing page previously rendered inside the app Shell, so visitors met a dark
 * workspace sidebar full of signed-in navigation before they had an account. A public
 * site needs a horizontal nav and a clear call to action instead.
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
      setScrolled(window.scrollY > 8);
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
    <div className="min-h-screen bg-page">
      <header
        className={`sticky top-0 z-50 border-b transition-all ${
          scrolled ? "border-line bg-white/90 backdrop-blur-xl" : "border-transparent bg-page/95"
        }`}
      >
        <nav className="mx-auto flex max-w-7xl items-center gap-6 px-5 py-3.5 lg:px-8">
          <Link to="/" className="flex shrink-0 items-center gap-2.5" onClick={() => setMenuOpen(false)}>
            <BrandLogo showWordmark={false} imageClassName="h-9 w-9" />
            <span className="text-[1.05rem] font-extrabold tracking-tight text-ink">BizXusAI</span>
          </Link>

          <div className="hidden flex-1 items-center gap-1 lg:flex">
            {SECTIONS.map((item) => (
              <a
                key={item.href}
                href={item.href}
                className="rounded-lg px-3 py-2 text-sm font-semibold text-muted transition hover:bg-surface hover:text-ink"
              >
                {item.label}
              </a>
            ))}
            <NavLink
              to="/customer/marketplace"
              className="rounded-lg px-3 py-2 text-sm font-semibold text-muted transition hover:bg-surface hover:text-ink"
            >
              Marketplace
            </NavLink>
          </div>

          <div className="ml-auto hidden items-center gap-2 lg:flex">
            <Link
              to="/login"
              className="rounded-xl px-4 py-2 text-sm font-bold text-ink transition hover:bg-surface"
            >
              Log in
            </Link>
            <Link to="/register" className="ui-btn-primary !py-2.5">
              Get started free
              <ArrowRight size={16} />
            </Link>
          </div>

          <button
            type="button"
            onClick={() => setMenuOpen((v) => !v)}
            className="ml-auto grid h-11 w-11 place-items-center rounded-xl border border-line text-ink lg:hidden"
            aria-label={menuOpen ? "Close menu" : "Open menu"}
            aria-expanded={menuOpen}
          >
            {menuOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </nav>

        {menuOpen ? (
          <div className="border-t border-line bg-white/95 px-5 pb-5 pt-2 backdrop-blur lg:hidden">
            <div className="flex flex-col">
              {SECTIONS.map((item) => (
                <a
                  key={item.href}
                  href={item.href}
                  onClick={() => setMenuOpen(false)}
                  className="rounded-lg px-3 py-3 text-sm font-semibold text-ink transition hover:bg-surface"
                >
                  {item.label}
                </a>
              ))}
              <Link
                to="/customer/marketplace"
                onClick={() => setMenuOpen(false)}
                className="rounded-lg px-3 py-3 text-sm font-semibold text-ink transition hover:bg-surface"
              >
                Marketplace
              </Link>
            </div>
            <div className="mt-3 grid gap-2 border-t border-line pt-4">
              <Link to="/login" onClick={() => setMenuOpen(false)} className="ui-btn-secondary">
                Log in
              </Link>
              <Link to="/register" onClick={() => setMenuOpen(false)} className="ui-btn-primary">
                Get started free
                <ArrowRight size={16} />
              </Link>
            </div>
          </div>
        ) : null}
      </header>

      <main>
        <Outlet />
      </main>

      <footer className="border-t border-line bg-surface">
        <div className="mx-auto max-w-7xl px-5 py-12 lg:px-8">
          <div className="grid gap-10 md:grid-cols-[1.4fr_1fr_1fr_1fr]">
            <div>
              <div className="flex items-center gap-2.5">
                <BrandLogo showWordmark={false} imageClassName="h-9 w-9" />
                <span className="text-[1.05rem] font-extrabold tracking-tight text-ink">BizXusAI</span>
              </div>
              <p className="mt-3 max-w-xs text-sm leading-6 text-muted">
                Websites, orders, payments and an AI assistant for Pakistani businesses — in one workspace.
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

          <div className="mt-10 flex flex-col gap-2 border-t border-line pt-6 text-xs text-subtle sm:flex-row sm:items-center sm:justify-between">
            <span>© 2026 BizXusAI. Built as a modern SaaS business platform.</span>
            <span className="font-semibold uppercase tracking-[0.14em]">Automation first · Pakistan ready</span>
          </div>
        </div>
      </footer>
    </div>
  );
}

function FooterColumn({ title, links }) {
  return (
    <div>
      <div className="text-xs font-bold uppercase tracking-[0.14em] text-subtle">{title}</div>
      <div className="mt-3 grid gap-2">
        {links.map((l) =>
          l.to.startsWith("/#") ? (
            <a key={l.to} href={l.to} className="text-sm font-semibold text-muted transition hover:text-brand">
              {l.label}
            </a>
          ) : (
            <Link key={l.to} to={l.to} className="text-sm font-semibold text-muted transition hover:text-brand">
              {l.label}
            </Link>
          ),
        )}
      </div>
    </div>
  );
}
