import { ChevronDown, Menu, PanelLeftClose, PanelLeftOpen, Search, X } from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { BrandLogo } from "../common/BrandLogo.jsx";

// On the dark rail the active item is the brand gradient with its glow; everything else
// sits at --sidebar-text and lifts to white on hover.
function navClass({ isActive }, collapsed = false) {
  return [
    "group flex items-center rounded-rail text-sm font-semibold transition-all duration-200",
    collapsed ? "justify-center px-2.5 py-2.5" : "gap-3 px-3.5 py-2.5",
    isActive
      ? "bg-sidebar-active text-white shadow-nav-active"
      : "text-sidebar-text hover:bg-sidebar-hover hover:text-white",
  ].join(" ");
}

function buildSections(navItems) {
  const grouped = [];
  for (const item of navItems) {
    const title = item.section || "Workspace";
    let section = grouped.find((candidate) => candidate.title === title);
    if (!section) {
      section = { title, items: [] };
      grouped.push(section);
    }
    section.items.push(item);
  }
  return grouped;
}

function NavList({ navItems, navSections, onNavigate, collapsed = false }) {
  const sections = navSections?.length ? navSections : buildSections(navItems);
  return (
    <nav className="flex flex-col gap-3">
      {sections.map((section) => (
        <details key={section.title} className="group/section" open={collapsed || !section.collapsedByDefault}>
          <summary
            className={`mb-1 flex cursor-pointer list-none items-center justify-between rounded-rail px-2 py-1 text-[10px] font-black uppercase tracking-[0.14em] text-sidebar-muted transition hover:text-white [&::-webkit-details-marker]:hidden ${
              collapsed ? "sr-only" : ""
            }`}
          >
            {section.title}
            <ChevronDown size={13} className="transition group-open/section:rotate-180" />
          </summary>
          <div className="flex flex-col gap-1">
            {section.items.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  className={(state) => navClass(state, collapsed)}
                  onClick={onNavigate}
                  title={collapsed ? item.label : undefined}
                >
                  {Icon ? <Icon size={18} className="shrink-0" strokeWidth={2} /> : <span className="h-[18px] w-[18px] shrink-0" />}
                  {collapsed ? null : <span className="truncate">{item.label}</span>}
                </NavLink>
              );
            })}
          </div>
        </details>
      ))}
    </nav>
  );
}

export function Shell({
  title,
  subtitle,
  navItems,
  navSections = null,
  asideExtra = null,
  asideFooter = null,
  headerActions = null,
  outletContext = null,
  flowSteps = [],
}) {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => localStorage.getItem("bizxus_sidebar_collapsed") === "true");
  const [focusMode, setFocusMode] = useState(() => localStorage.getItem("bizxus_focus_mode") === "true");

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

  function toggleCollapsed() {
    setSidebarCollapsed((current) => {
      const next = !current;
      localStorage.setItem("bizxus_sidebar_collapsed", String(next));
      return next;
    });
  }

  function toggleFocusMode() {
    setFocusMode((current) => {
      const next = !current;
      localStorage.setItem("bizxus_focus_mode", String(next));
      return next;
    });
  }

  const railContent = (
    <>
      <div className={`flex items-center px-2 pb-6 pt-1 ${sidebarCollapsed ? "justify-center" : "gap-3"}`}>
        <BrandLogo tone="dark" showWordmark={false} imageClassName="h-10 w-10" />
        <div className={`min-w-0 ${sidebarCollapsed ? "hidden" : ""}`}>
          <div className="truncate text-[1.05rem] font-extrabold leading-tight tracking-tight text-white">BizXusAI</div>
          <div className="truncate text-[11px] font-medium text-sidebar-muted">Automate. Grow. Together.</div>
        </div>
      </div>

      <div className="rail-scroll min-h-0 flex-1 overflow-y-auto pr-1">
        <NavList navItems={navItems} navSections={navSections} onNavigate={closeMobileNav} collapsed={sidebarCollapsed} />
        {asideExtra && !sidebarCollapsed ? <div className="mt-6 border-t border-white/[0.08] pt-5">{asideExtra}</div> : null}
      </div>

      {!sidebarCollapsed ? (
        <div className="mt-4 space-y-3 border-t border-white/[0.08] pt-4">
          {asideFooter}
          <button
            type="button"
            onClick={toggleCollapsed}
            className="flex w-full items-center gap-3 rounded-rail px-3.5 py-2.5 text-sm font-semibold text-sidebar-text transition hover:bg-sidebar-hover hover:text-white"
          >
            <PanelLeftClose size={18} className="shrink-0" />
            Collapse sidebar
          </button>
        </div>
      ) : (
        <div className="mt-4 border-t border-white/[0.08] pt-4">
          <button
            type="button"
            onClick={toggleCollapsed}
            className="grid h-10 w-full place-items-center rounded-rail text-sidebar-text transition hover:bg-sidebar-hover hover:text-white"
            title="Expand sidebar"
            aria-label="Expand sidebar"
          >
            <PanelLeftOpen size={18} />
          </button>
        </div>
      )}
    </>
  );

  return (
    <div className="min-h-screen bg-page lg:flex">
      {/* Fixed dark rail on large screens. */}
      {!focusMode ? (
      <aside className={`sticky top-0 hidden h-screen shrink-0 flex-col bg-sidebar-rail p-4 shadow-rail transition-all lg:flex ${sidebarCollapsed ? "w-[88px]" : "w-[260px]"}`}>
        {railContent}
      </aside>
      ) : null}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 border-b border-line bg-white">
          <div className="flex items-center gap-3 px-4 py-3.5 sm:px-6 lg:px-8">
            <button
              type="button"
              onClick={() => setMobileNavOpen(true)}
              className="grid h-11 w-11 shrink-0 place-items-center rounded-rail border border-line bg-white text-ink transition hover:bg-surface lg:hidden"
              aria-label="Open navigation menu"
            >
              <Menu size={20} />
            </button>

            <button
              type="button"
              onClick={toggleFocusMode}
              className="hidden h-10 w-10 shrink-0 place-items-center rounded-rail border border-line bg-white text-muted transition hover:bg-surface hover:text-ink lg:grid"
              title={focusMode ? "Show sidebar" : "Hide sidebar for focus"}
              aria-label={focusMode ? "Show sidebar" : "Hide sidebar for focus"}
            >
              {focusMode ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
            </button>

            <div className="relative hidden min-w-0 flex-1 md:block">
              <Search size={18} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-muted" />
              <input
                type="search"
                placeholder="Search anything... (customers, items, transactions, etc.)"
                aria-label="Search the workspace"
                className="w-full rounded-full border border-line bg-surface py-2.5 pl-11 pr-4 text-sm text-ink outline-none transition placeholder:text-muted focus:border-brand-bright focus:bg-white focus:shadow-[0_0_0_3px_rgba(37,99,235,0.14)]"
              />
            </div>

            <div className="min-w-0 flex-1 md:hidden">
              <div className="truncate text-base font-bold leading-tight text-ink">{title}</div>
              <div className="truncate text-xs text-muted">{subtitle}</div>
            </div>

            {headerActions ? <div className="flex shrink-0 items-center">{headerActions}</div> : null}
          </div>
        </header>

        {focusMode ? (
          <button
            type="button"
            onClick={toggleFocusMode}
            className="fixed left-4 top-20 z-30 hidden rounded-full border border-line bg-white px-3 py-2 text-xs font-bold text-ink shadow-card transition hover:bg-surface lg:inline-flex"
          >
            Show sidebar
          </button>
        ) : null}

        <main className="min-w-0 flex-1 px-4 py-6 sm:px-6 lg:px-8">
          <div className="mb-6 hidden md:block">
            <h1 className="text-2xl font-extrabold tracking-tight text-ink lg:text-[1.75rem]">{title}</h1>
            {subtitle ? <p className="mt-1 text-sm text-muted">{subtitle}</p> : null}
          </div>
          {flowSteps.length ? (
            <div className="mb-5 overflow-x-auto rounded-card border border-line bg-white px-3 py-3 shadow-card sm:px-4">
              <ol className="workflow-strip flex min-w-max items-center gap-5">
                {flowSteps.map((step, index) => {
                  const Icon = step.icon;
                  return (
                    <li key={step.label} className="workflow-step flex items-center gap-2 pr-1">
                      <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-brand-50 text-xs font-black text-brand">
                        {Icon ? <Icon size={15} strokeWidth={2.4} /> : index + 1}
                      </span>
                      <span className="whitespace-nowrap text-xs font-bold text-muted">
                        <span className="text-ink">{index + 1}.</span> {step.label}
                      </span>
                    </li>
                  );
                })}
              </ol>
            </div>
          ) : null}
          {/* Most pages render straight into this panel rather than bringing their own
              card, so the workspace surface stays here rather than in each feature. */}
          <div className="ui-card p-5 sm:p-7">
            <Outlet context={outletContext} />
          </div>
        </main>

        <footer className="border-t border-line bg-white px-4 py-5 sm:px-6 lg:px-8">
          <div className="flex flex-col gap-2 text-xs text-muted sm:flex-row sm:items-center sm:justify-between">
            <div className="font-medium">© 2026 BizXusAI. Built as a modern SaaS business platform.</div>
            <div className="flex flex-wrap gap-4 font-semibold uppercase tracking-[0.16em]">
              <span>Automation First</span>
              <span>Pakistan Ready</span>
              <span>Multi-Role Workspace</span>
            </div>
          </div>
        </footer>
      </div>

      {/* Mobile drawer: the same rail, slid in over the content. */}
      <div className={`fixed inset-0 z-40 transition lg:hidden ${mobileNavOpen ? "pointer-events-auto" : "pointer-events-none"}`}>
        <div
          className={`absolute inset-0 bg-ink/50 backdrop-blur-sm transition-opacity duration-300 ${mobileNavOpen ? "opacity-100" : "opacity-0"}`}
          onClick={closeMobileNav}
        />
        <aside
          className={`absolute left-0 top-0 flex h-full w-[86vw] max-w-[300px] flex-col bg-sidebar-rail p-4 shadow-rail transition-transform duration-300 ${mobileNavOpen ? "translate-x-0" : "-translate-x-full"}`}
        >
          <button
            type="button"
            onClick={closeMobileNav}
            className="absolute right-3 top-3 grid h-9 w-9 place-items-center rounded-rail text-sidebar-muted transition hover:bg-sidebar-hover hover:text-white"
            aria-label="Close navigation menu"
          >
            <X size={18} />
          </button>
          <NavList navItems={navItems} navSections={navSections} onNavigate={closeMobileNav} />
          {asideExtra ? <div className="mt-6 border-t border-white/[0.08] pt-5">{asideExtra}</div> : null}
          {asideFooter ? <div className="mt-4 border-t border-white/[0.08] pt-4">{asideFooter}</div> : null}
        </aside>
      </div>
    </div>
  );
}
