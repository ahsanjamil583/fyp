import { Shell } from "./Shell.jsx";
import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "../../context/AuthContext.jsx";
import { useModules } from "../../context/ModuleContext.jsx";
import { useTenant } from "../../context/TenantContext.jsx";
import { logoutBusiness } from "../../services/authApi.js";

const navItems = [
  { to: "/dashboard", label: "Overview", end: true },
  { to: "/dashboard/business", label: "Business" },
  { to: "/dashboard/launch-wizard", label: "Launch Wizard" },
  { to: "/dashboard/modules", label: "Modules" },
  { to: "/dashboard/custom-fields", label: "Custom Fields" },
  { to: "/dashboard/transactions", label: "Transactions" },
  { to: "/dashboard/customers", label: "Customers", moduleCode: "customers" },
  { to: "/dashboard/items", label: "Items", moduleCode: "items" },
  { to: "/dashboard/public-website", label: "Website", moduleCode: "website_builder" },
  { to: "/dashboard/analytics", label: "Analytics", moduleCode: "analytics" },
  { to: "/dashboard/ai-conversations", label: "AI Chat", moduleCode: "ai_chat" },
  { to: "/dashboard/knowledge-base", label: "Knowledge Base", moduleCode: "ai_chat" },
  { to: "/dashboard/agent-tools", label: "Agent Tools", moduleCode: "ai_chat" },
  { to: "/dashboard/owner-agent", label: "Owner AI Assistant", moduleCode: "owner_agent" },
  { to: "/dashboard/whatsapp-agent", label: "WhatsApp Agent", moduleCode: "whatsapp_agent" },
  { to: "/dashboard/payments", label: "Payments", moduleCode: "payments" },
  { to: "/dashboard/reports", label: "Reports", moduleCode: "reports" },
  { to: "/dashboard/notifications", label: "Notifications", moduleCode: "notifications" },
  { to: "/dashboard/deployment-readiness", label: "Deployment Readiness" },
  { to: "/dashboard/final-qa", label: "Final QA" },
  { to: "/dashboard/submission-center", label: "Submission Center" },
];

export function DashboardLayout() {
  const navigate = useNavigate();
  const { clearSession, refreshSession, user } = useAuth();
  const { tenants, selectedTenant, selectTenant, refreshTenants } = useTenant();
  const { enabledModules, tenantPlan, refreshTenantModules } = useModules();

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

  const visibleNav = navItems.filter((item) => !item.moduleCode || enabledModules.includes(item.moduleCode));

  const asideExtra = (
    <div className="space-y-2">
      <label className="block text-xs font-semibold uppercase tracking-wide text-muted">Selected Business</label>
      <select
        className="w-full rounded-md border border-line bg-white px-3 py-2 text-sm text-ink"
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
        <div className="rounded-md bg-surface p-3 text-xs text-muted">
          <div className="font-semibold text-ink">{selectedTenant.slug}</div>
          <div className="mt-1 capitalize">{selectedTenant.status} / {selectedTenant.websiteStatus}</div>
          <div className="mt-2 rounded-md bg-white px-2 py-1 font-semibold text-brand">
            Current Plan: {tenantPlan?.displayName || "Basic Free"}
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
    <div className="space-y-3">
      <div className="rounded-md bg-surface p-3 text-xs text-muted">
        <div className="font-semibold text-ink">{user?.fullName || "Signed in"}</div>
        <div className="mt-1 break-all">{user?.email}</div>
      </div>
      <button
        type="button"
        onClick={handleLogout}
        className="w-full rounded-md border border-line px-3 py-2 text-sm font-semibold text-ink transition hover:bg-surface"
      >
        Logout
      </button>
    </div>
  );

  const headerActions = (
    <div className="flex items-center gap-3">
      {selectedTenant ? (
        <div className="hidden rounded-md bg-surface px-3 py-2 text-sm font-semibold text-ink sm:block">
          Current Plan: {tenantPlan?.displayName || "Basic Free"}
        </div>
      ) : null}
      <button
        type="button"
        onClick={handleLogout}
        className="rounded-md border border-line px-3 py-2 text-sm font-semibold text-ink transition hover:bg-surface"
      >
        Logout
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
    />
  );
}
