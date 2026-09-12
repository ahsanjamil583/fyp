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
  FileText,
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
  Users,
} from "lucide-react";
import { Shell } from "./Shell.jsx";
import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "../../context/AuthContext.jsx";
import { useModules } from "../../context/ModuleContext.jsx";
import { useTenant } from "../../context/TenantContext.jsx";
import { logoutBusiness } from "../../services/authApi.js";

const navItems = [
  { to: "/dashboard", label: "Overview", end: true, icon: LayoutDashboard },
  { to: "/dashboard/business", label: "Business", icon: Building2 },
  { to: "/dashboard/launch-wizard", label: "Launch Wizard", icon: Rocket },
  { to: "/dashboard/modules", label: "Modules", icon: SquareStack },
  { to: "/dashboard/custom-fields", label: "Custom Fields", icon: Settings2 },
  { to: "/dashboard/transactions", label: "Transactions", icon: Receipt },
  { to: "/dashboard/customers", label: "Customers", moduleCode: "customers", icon: Users },
  { to: "/dashboard/items", label: "Items", moduleCode: "items", icon: Boxes },
  { to: "/dashboard/public-website", label: "Website", moduleCode: "website_builder", icon: Globe },
  { to: "/dashboard/analytics", label: "Analytics", moduleCode: "analytics", icon: BarChart3 },
  { to: "/dashboard/ai-conversations", label: "AI Chat", moduleCode: "ai_chat", icon: MessageSquare },
  { to: "/dashboard/knowledge-base", label: "Knowledge Base", moduleCode: "ai_chat", icon: FileText },
  { to: "/dashboard/agent-tools", label: "Agent Tools", moduleCode: "ai_chat", icon: Sparkles },
  { to: "/dashboard/owner-agent", label: "Owner AI Assistant", moduleCode: "owner_agent", icon: Bot },
  { to: "/dashboard/whatsapp-agent", label: "WhatsApp Agent", moduleCode: "whatsapp_agent", icon: MessageCircle },
  { to: "/dashboard/payments", label: "Payments", moduleCode: "payments", icon: CreditCard },
  { to: "/dashboard/reports", label: "Reports", moduleCode: "reports", icon: ClipboardCheck },
  { to: "/dashboard/notifications", label: "Notifications", moduleCode: "notifications", icon: Bell },
  { to: "/dashboard/deployment-readiness", label: "Deployment Readiness", icon: Activity },
  { to: "/dashboard/final-qa", label: "Final QA", icon: ListChecks },
  { to: "/dashboard/submission-center", label: "Submission Center", icon: SendHorizonal },
];

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
  const visibleNav = navItems.filter((item) => !item.moduleCode || accessibleModules.includes(item.moduleCode));

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
      asideExtra={asideExtra}
      asideFooter={asideFooter}
      headerActions={headerActions}
      flowSteps={[
        { label: "Profile", icon: Building2 },
        { label: "Modules", icon: SquareStack },
        { label: "Catalog", icon: Boxes },
        { label: "Website", icon: Globe },
        { label: "Orders", icon: Receipt },
      ]}
    />
  );
}
