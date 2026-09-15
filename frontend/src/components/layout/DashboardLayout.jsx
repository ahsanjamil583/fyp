import {
  Activity,
  BarChart3,
  Bell,
  Bot,
  Boxes,
  Building2,
  ClipboardCheck,
  CreditCard,
  Crown,
  ExternalLink,
  FileText,
  FileUp,
  Globe,
  LayoutDashboard,
  ListChecks,
  LogOut,
  MessageCircle,
  MessageSquare,
  Receipt,
  Rocket,
  SendHorizonal,
  Settings2,
  Sparkles,
  SquareStack,
  Store,
  Users,
} from "lucide-react";
import { Shell } from "./Shell.jsx";
import { useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";

import { useAuth } from "../../context/AuthContext.jsx";
import { useModules } from "../../context/ModuleContext.jsx";
import { useTenant } from "../../context/TenantContext.jsx";
import { logoutBusiness } from "../../services/authApi.js";

const navItems = [
  { to: "/dashboard", label: "Home", end: true, icon: LayoutDashboard, section: "Start here" },
  { to: "/dashboard/business", label: "Business Profile", icon: Building2, section: "Start here" },
  { to: "/dashboard/launch-wizard", label: "Launch Guide", icon: Rocket, section: "Start here", hideWhenPublished: true },
  { to: "/dashboard/public-website", label: "Website Builder", moduleCode: "website_builder", icon: Globe, section: "Start here" },
  { to: "/dashboard/items", label: "Catalog & Stock", moduleCode: "items", icon: Boxes, section: "Sell" },
  { to: "/dashboard/transactions", label: "Orders", icon: Receipt, section: "Sell" },
  { to: "/dashboard/cashiers", label: "Cashiers", moduleCode: "cashier", icon: Store, section: "Sell" },
  { to: "/dashboard/orders/import", label: "Import Orders", moduleCode: "cashier", icon: FileUp, section: "Sell" },
  { to: "/dashboard/customers", label: "Customers", moduleCode: "customers", icon: Users, section: "Sell" },
  { to: "/dashboard/payments", label: "Payments", moduleCode: "payments", icon: CreditCard, section: "Sell" },
  { to: "/dashboard/whatsapp-agent", label: "WhatsApp Agent", moduleCode: "whatsapp_agent", icon: MessageCircle, section: "Automation" },
  { to: "/dashboard/ai-conversations", label: "AI Conversations", moduleCode: "ai_chat", icon: MessageSquare, section: "Automation" },
  { to: "/dashboard/knowledge-base", label: "Knowledge Base", moduleCode: "ai_chat", icon: FileText, section: "Automation" },
  { to: "/dashboard/agent-tools", label: "Agent Tools", moduleCode: "ai_chat", icon: Sparkles, section: "Automation" },
  { to: "/dashboard/analytics", label: "Analytics", moduleCode: "analytics", icon: BarChart3, section: "Insights" },
  { to: "/dashboard/reports", label: "Reports", moduleCode: "reports", icon: ClipboardCheck, section: "Insights" },
  { to: "/dashboard/owner-agent", label: "Owner Assistant", moduleCode: "owner_agent", icon: Bot, section: "Insights" },
  { to: "/dashboard/notifications", label: "Notifications", moduleCode: "notifications", icon: Bell, section: "Insights" },
  { to: "/dashboard/modules", label: "Modules", icon: SquareStack, section: "Settings" },
  { to: "/dashboard/custom-fields", label: "Custom Fields", icon: Settings2, section: "Settings" },
  { to: "/dashboard/deployment-readiness", label: "Deployment Readiness", icon: Activity, section: "Review & handoff", hideWhenPublished: true },
  { to: "/dashboard/final-qa", label: "Final QA", icon: ListChecks, section: "Review & handoff", hideWhenPublished: true },
  { to: "/dashboard/submission-center", label: "Submission Center", icon: SendHorizonal, section: "Review & handoff", hideWhenPublished: true },
];

const NAV_SECTION_ORDER = ["Start here", "Sell", "Automation", "Insights", "Settings", "Review & handoff"];

export function DashboardLayout() {
  const navigate = useNavigate();
  const { clearSession, refreshSession, user } = useAuth();
  const { tenants, selectedTenant, selectTenant, refreshTenants } = useTenant();
  const { enabledModules, tenantModules, tenantPlan, refreshTenantModules } = useModules();

  useEffect(() => {
    refreshTenants().catch(() => {});
  }, [refreshTenants]);

  useEffect(() => {
    async function syncWorkspace() {
      const currentUser = await refreshSession().catch(() => null);
      if (!currentUser) {
        return;
      }
      await refreshTenants().catch(() => {});
    }

    syncWorkspace().catch(() => {});

    function handleFocus() {
      syncWorkspace().catch(() => {});
    }

    window.addEventListener("focus", handleFocus);
    const intervalId = window.setInterval(() => {
      syncWorkspace().catch(() => {});
    }, 30000);

    return () => {
      window.removeEventListener("focus", handleFocus);
      window.clearInterval(intervalId);
    };
  }, [refreshSession, refreshTenants]);

  useEffect(() => {
    refreshTenantModules(selectedTenant?.id).catch(() => {});
  }, [selectedTenant?.id, selectedTenant?.updatedAt, refreshTenantModules]);

  const accessibleModules = tenantModules.length
    ? tenantModules
        .filter((module) => module.tenantStatus === "enabled" && module.planAccess?.isIncluded !== false)
        .map((module) => module.code)
    : enabledModules;
  const websiteIsPublished = selectedTenant?.websiteStatus === "published";
  const visibleNav = navItems.filter((item) => {
    if (websiteIsPublished && item.hideWhenPublished) return false;
    return !item.moduleCode || accessibleModules.includes(item.moduleCode);
  });
  const navSections = NAV_SECTION_ORDER.map((title) => ({
    title,
    collapsedByDefault: title === "Settings" || title === "Review & handoff",
    items: visibleNav.filter((item) => item.section === title),
  })).filter((section) => section.items.length);
  const websiteUrl = selectedTenant?.slug ? `/businesses/${selectedTenant.slug}` : "";

  // Rendered inside the dark rail, so these controls are tinted rather than white.
  const asideExtra = (
    <div className="space-y-2 px-1">
      <label className="block text-[11px] font-semibold uppercase tracking-[0.18em] text-sidebar-muted">
        Selected Business
      </label>
      <select
        className="w-full rounded-rail border border-white/10 bg-sidebar-card px-3 py-2 text-sm font-medium text-white outline-none transition focus:border-purple-glow [&>option]:text-ink"
        value={selectedTenant?.id || ""}
        onChange={(event) => selectTenant(tenants.find((tenant) => tenant.id === event.target.value) || null)}
      >
        <option value="">No business yet</option>
        {tenants.map((tenant) => (
          <option key={tenant.id} value={tenant.id}>
            {tenant.name}
          </option>
        ))}
      </select>
      {selectedTenant ? (
        <div className="rounded-rail bg-sidebar-card p-3 text-xs text-sidebar-muted">
          <div className="font-semibold text-white">{selectedTenant.slug}</div>
          <div className="mt-1 capitalize">
            {selectedTenant.status} / {selectedTenant.websiteStatus}
          </div>
          <div className="mt-2 inline-flex rounded-full bg-sidebar-active px-2.5 py-1 text-[11px] font-bold text-white">
            {tenantPlan?.displayName || "Basic Free"}
          </div>
          <div className="mt-3 grid gap-2">
            <Link
              to="/dashboard/public-website"
              className="rounded-lg border border-white/10 px-3 py-2 text-center text-[11px] font-bold text-white transition hover:bg-sidebar-hover"
            >
              {websiteIsPublished ? "Manage website" : "Prepare website"}
            </Link>
            {websiteUrl ? (
              <Link
                to={websiteUrl}
                className="rounded-lg bg-white px-3 py-2 text-center text-[11px] font-bold text-sidebar-bottom transition hover:bg-white/90"
              >
                View public site
              </Link>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );

  async function handleLogout() {
    try {
      await logoutBusiness();
    } catch {
      // Clear local auth state even if the backend logout request fails.
    }
    clearSession();
    navigate("/login", { replace: true });
  }

  const asideFooter = (
    <div className="space-y-2">
      <div className="flex items-center gap-3 rounded-rail bg-sidebar-card px-3 py-2.5">
        <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-sidebar-active text-sm font-bold text-white">
          {(user?.fullName || "U").charAt(0).toUpperCase()}
        </div>
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-white">{user?.fullName || "Signed in"}</div>
          <div className="truncate text-[11px] text-sidebar-muted">{user?.email}</div>
        </div>
      </div>
      <button
        type="button"
        onClick={handleLogout}
        className="flex w-full items-center gap-3 rounded-rail px-3.5 py-2.5 text-sm font-semibold text-sidebar-text transition hover:bg-sidebar-hover hover:text-white"
      >
        <LogOut size={18} className="shrink-0" />
        Logout
      </button>
    </div>
  );

  const headerActions = (
    <div className="flex items-center gap-2 sm:gap-3">
      {websiteUrl ? (
        <Link
          to={websiteUrl}
          className="hidden items-center gap-1.5 rounded-full border border-line bg-white px-3.5 py-2 text-xs font-bold text-ink transition hover:bg-surface md:inline-flex"
        >
          <ExternalLink size={14} />
          {websiteIsPublished ? "View website" : "Preview site"}
        </Link>
      ) : null}

      {selectedTenant ? (
        <span className="hidden items-center gap-1.5 rounded-full bg-brand-100 px-3.5 py-1.5 text-xs font-bold text-brand xl:inline-flex">
          <Crown size={13} strokeWidth={2.4} />
          {tenantPlan?.displayName || "Basic Free"}
        </span>
      ) : null}

      <span className="hidden h-8 w-px bg-line sm:block" />

      <div className="flex items-center gap-2.5">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-sidebar-active text-sm font-bold text-white">
          {(user?.fullName || "U").charAt(0).toUpperCase()}
        </span>
        <div className="hidden min-w-0 leading-tight sm:block">
          <div className="truncate text-sm font-bold text-ink">{user?.fullName || "Signed in"}</div>
          <div className="truncate text-[11px] font-medium text-subtle">Business Owner</div>
        </div>
      </div>

      <button
        type="button"
        onClick={handleLogout}
        title="Log out"
        className="grid h-9 w-9 shrink-0 place-items-center rounded-full border border-line bg-white text-muted transition hover:border-red-200 hover:bg-red-50 hover:text-red-500"
        aria-label="Log out"
      >
        <LogOut size={16} />
      </button>
    </div>
  );

  return (
    <Shell
      title="Business Dashboard"
      subtitle={selectedTenant ? selectedTenant.name : "Create your first business"}
      navItems={visibleNav}
      navSections={navSections}
      asideExtra={asideExtra}
      asideFooter={asideFooter}
      headerActions={headerActions}
      flowSteps={
        websiteIsPublished
          ? [
              { label: "View Site", icon: Globe },
              { label: "Catalog", icon: Boxes },
              { label: "Orders", icon: Receipt },
              { label: "Customers", icon: Users },
              { label: "Reports", icon: ClipboardCheck },
            ]
          : [
              { label: "Profile", icon: Building2 },
              { label: "Catalog", icon: Boxes },
              { label: "Website", icon: Globe },
              { label: "Publish", icon: Rocket },
              { label: "Orders", icon: Receipt },
            ]
      }
    />
  );
}
