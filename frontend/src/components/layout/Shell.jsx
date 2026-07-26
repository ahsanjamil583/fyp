import { Menu, X } from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { BrandLogo } from "../common/BrandLogo.jsx";

function navClass({ isActive }) {
  return [
    "group flex items-center justify-between rounded-2xl px-4 py-3 text-sm font-semibold transition-all duration-200",
    isActive
      ? "bg-gradient-to-r from-brand to-sky-500 text-white shadow-lg shadow-blue-500/20"
      : "text-slate-600 hover:bg-white hover:text-ink hover:shadow-sm",
  ].join(" ");
}

export function Shell({ title, subtitle, navItems, asideExtra = null, asideFooter = null, headerActions = null, outletContext = null }) {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  useEffect(() => {
    if (!mobileNavOpen) {
      return undefined;
    }

    function handleEscape(event) {
      if (event.key === "Escape") {
        setMobileNavOpen(false);
      }
    }

    window.addEventListener("keydown", handleEscape);
    document.body.style.overflow = "hidden";

    return () => {
      window.removeEventListener("keydown", handleEscape);
      document.body.style.overflow = "";
    };
  }, [mobileNavOpen]);

  function closeMobileNav() {
    setMobileNavOpen(false);
  }

  const sidebarContent = (
    <>
      <div className="rounded-[1.5rem] bg-[linear-gradient(135deg,_rgba(37,99,235,0.14),_rgba(14,165,233,0.08))] px-4 py-4">
        <div className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">Navigation</div>
        <div className="mt-2 text-lg font-semibold text-ink">Workspace Menu</div>
        <div className="mt-1 text-sm leading-6 text-slate-600">Move between modules, manage data, and track activity from one focused control panel.</div>
      </div>
      <nav className="mt-4 flex flex-col gap-2">
        {navItems.map((item) => (
          <NavLink key={item.to} to={item.to} end={item.end} className={navClass} onClick={closeMobileNav}>
            <span>{item.label}</span>
            <span className="text-xs opacity-70 transition group-hover:translate-x-0.5 group-hover:opacity-100">{">"}</span>
          </NavLink>
        ))}
      </nav>
      {asideExtra ? <div className="mt-5 border-t border-slate-200 pt-5">{asideExtra}</div> : null}
      {asideFooter ? <div className="mt-5 border-t border-slate-200 pt-5">{asideFooter}</div> : null}
    </>
  );

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(37,99,235,0.16),_transparent_28%),linear-gradient(180deg,_#f7fbff_0%,_#eef3f9_48%,_#e9eef5_100%)]">
      <header className="sticky top-0 z-30 border-b border-white/60 bg-white/80 backdrop-blur-xl">
        <div className="mx-auto max-w-7xl px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex min-w-0 items-start gap-3 sm:gap-4">
            <button
              type="button"
              onClick={() => setMobileNavOpen(true)}
              className="grid h-12 w-12 place-items-center rounded-2xl border border-slate-200 bg-white text-slate-700 shadow-sm transition hover:border-slate-300 hover:text-ink lg:hidden"
              aria-label="Open navigation menu"
            >
              <Menu size={22} />
            </button>
              <BrandLogo
                showWordmark={false}
                className="shrink-0"
                imageClassName="h-14 w-14 rounded-2xl ring-1 ring-slate-200"
              />
              <div className="hidden h-10 w-px bg-slate-200 md:block" />
              <div className="min-w-0">
                <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-500 sm:text-xs sm:tracking-[0.24em]">BizXus Workspace</div>
                <div className="mt-1 text-[1.85rem] font-semibold leading-none tracking-tight text-ink sm:text-[2.1rem] lg:text-lg lg:leading-snug">
                  {title}
                </div>
                <div className="mt-2 text-base leading-6 text-slate-500 sm:text-lg lg:mt-0 lg:text-sm">{subtitle}</div>
              </div>
            </div>
            {headerActions ? <div className="flex items-center lg:justify-end">{headerActions}</div> : null}
          </div>
        </div>
      </header>
      <div className="mx-auto grid max-w-7xl items-start gap-6 px-4 py-6 sm:px-6 lg:grid-cols-[290px_1fr] lg:px-8">
        <aside className="hidden h-fit overflow-hidden rounded-[2rem] border border-white/70 bg-white/72 p-4 shadow-[0_25px_60px_rgba(15,23,42,0.08)] backdrop-blur lg:block">
          {sidebarContent}
        </aside>
        <main className="h-fit min-w-0 overflow-visible rounded-[2rem] border border-white/70 bg-white/82 p-6 shadow-[0_28px_70px_rgba(15,23,42,0.08)] backdrop-blur sm:p-8">
          <Outlet context={outletContext} />
        </main>
      </div>
      <div className={`fixed inset-0 z-40 transition lg:hidden ${mobileNavOpen ? "pointer-events-auto" : "pointer-events-none"}`}>
        <div
          className={`absolute inset-0 bg-slate-950/35 backdrop-blur-sm transition-opacity duration-300 ${mobileNavOpen ? "opacity-100" : "opacity-0"}`}
          onClick={closeMobileNav}
        />
        <aside
          className={`absolute left-0 top-0 flex h-full w-[88vw] max-w-[360px] flex-col overflow-y-auto border-r border-white/70 bg-[linear-gradient(180deg,_rgba(255,255,255,0.94),_rgba(240,246,255,0.98))] p-4 shadow-[0_24px_80px_rgba(15,23,42,0.2)] transition-transform duration-300 ${mobileNavOpen ? "translate-x-0" : "-translate-x-full"}`}
        >
          <div className="mb-4 flex items-center justify-between rounded-[1.4rem] border border-slate-200 bg-white/86 px-4 py-3">
            <div className="min-w-0">
              <div className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">Menu</div>
              <div className="truncate text-lg font-semibold text-ink">{title}</div>
            </div>
            <button
              type="button"
              onClick={closeMobileNav}
              className="grid h-11 w-11 place-items-center rounded-2xl border border-slate-200 bg-white text-slate-700 shadow-sm transition hover:border-slate-300 hover:text-ink"
              aria-label="Close navigation menu"
            >
              <X size={20} />
            </button>
          </div>
          {sidebarContent}
        </aside>
      </div>
      <footer className="mt-8 border-t border-white/60 bg-[linear-gradient(180deg,_rgba(255,255,255,0.76),_rgba(243,247,252,0.98))] backdrop-blur-xl">
        <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
          <div className="grid gap-6 rounded-[2rem] border border-white/80 bg-white/72 p-6 shadow-[0_18px_48px_rgba(15,23,42,0.07)] lg:grid-cols-[1.2fr_0.8fr_0.8fr]">
            <div>
              <BrandLogo imageClassName="h-12 w-12 rounded-2xl ring-1 ring-slate-200" labelClassName="text-[1.7rem] tracking-tight" />
              <p className="mt-4 max-w-xl text-sm leading-7 text-slate-600">
                BizXusAI helps modern businesses run customer operations, digital storefronts, transactions, and growth workflows from one SaaS workspace.
              </p>
              <div className="mt-4 inline-flex items-center gap-2 rounded-full bg-[linear-gradient(135deg,_rgba(37,99,235,0.12),_rgba(14,165,233,0.08))] px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-700">
                <span className="h-2 w-2 rounded-full bg-emerald-500" />
                Unified business operating system
              </div>
            </div>

            <div>
              <div className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">Platform</div>
              <div className="mt-4 grid gap-3">
                {["Customer CRM", "Website Builder", "Transactions", "Analytics"].map((item) => (
                  <div key={item} className="rounded-2xl border border-slate-200/80 bg-white/80 px-4 py-3 text-sm font-semibold text-slate-700 shadow-sm">
                    {item}
                  </div>
                ))}
              </div>
            </div>

            <div>
              <div className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">Why It Fits</div>
              <div className="mt-4 space-y-3 text-sm leading-6 text-slate-600">
                <div className="rounded-2xl border border-slate-200/80 bg-white/80 px-4 py-3 shadow-sm">
                  AI-assisted workflows for orders, websites, and customer growth.
                </div>
                <div className="rounded-2xl border border-slate-200/80 bg-white/80 px-4 py-3 shadow-sm">
                  Shared business data across modules instead of disconnected tools.
                </div>
                <div className="rounded-2xl border border-slate-200/80 bg-white/80 px-4 py-3 shadow-sm">
                  Built for scalable multi-role business operations.
                </div>
              </div>
            </div>
          </div>

          <div className="mt-5 flex flex-col gap-3 px-1 text-xs text-slate-500 sm:flex-row sm:items-center sm:justify-between">
            <div className="font-medium">© 2026 BizXusAI. Built as a modern SaaS business platform.</div>
            <div className="flex flex-wrap gap-4 font-semibold uppercase tracking-[0.18em]">
              <span>Automation First</span>
              <span>Pakistan Ready</span>
              <span>Multi-Role Workspace</span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
