import { Link } from "react-router-dom";
import { useEffect, useState } from "react";

import { useModules } from "../../context/ModuleContext.jsx";
import { useTenant } from "../../context/TenantContext.jsx";
import { getAnalyticsSummary } from "../../services/analyticsApi.js";

export function DashboardHome() {
  const { selectedTenant, tenants, isLoadingTenants } = useTenant();
  const { enabledModules } = useModules();
  const [analytics, setAnalytics] = useState(null);
  const analyticsEnabled = enabledModules.includes("analytics");

  useEffect(() => {
    async function loadOverview() {
      if (!selectedTenant || !analyticsEnabled) {
        setAnalytics(null);
        return;
      }

      try {
        const data = await getAnalyticsSummary(selectedTenant.id);
        setAnalytics(data);
      } catch {
        setAnalytics(null);
      }
    }

    loadOverview();
  }, [selectedTenant, analyticsEnabled]);

  if (isLoadingTenants) {
    return <div className="text-sm text-muted">Loading workspace...</div>;
  }

  if (!selectedTenant) {
    return (
      <section className="space-y-5">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-brand">Business Setup</p>
          <h1 className="mt-2 text-3xl font-semibold text-ink">Create your first business</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-muted">
            Phase 4 starts the multi-tenant foundation. Create a business profile, choose a dynamic category, and then enable modules.
          </p>
        </div>
        <Link className="inline-flex rounded-md bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700" to="/dashboard/business">
          Create Business
        </Link>
      </section>
    );
  }

  const summary = [
    { label: "Businesses", value: tenants.length },
    { label: "Enabled modules", value: enabledModules.length },
    { label: "Website", value: selectedTenant.websiteStatus },
    { label: "Status", value: selectedTenant.status },
  ];

  const analyticsSummary = analytics?.summary;
  const phase3Onboarding = selectedTenant.settings?.onboarding?.phase3;
  const analyticsCards = analyticsSummary
    ? [
        { label: "Customers", value: analyticsSummary.totalCustomers ?? 0 },
        { label: "Items", value: analyticsSummary.totalItems ?? 0 },
        { label: "Orders", value: analyticsSummary.totalOrders ?? 0 },
        { label: "Today", value: analyticsSummary.todayOrders ?? 0 },
      ]
    : [];

  return (
    <section className="space-y-6">
      <div className="flex flex-col gap-4 border-b border-line pb-6 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-brand">Overview</p>
          <h1 className="mt-2 text-3xl font-semibold text-ink">{selectedTenant.name}</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-muted">
            Your tenant foundation is ready. Continue by enabling modules that match this business.
          </p>
        </div>
        <Link className="rounded-md bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700" to="/dashboard/modules">
          Manage Modules
        </Link>
      </div>

      <div className="grid gap-4 md:grid-cols-4">
        {summary.map((item) => (
          <div key={item.label} className="rounded-md border border-line bg-surface p-4">
            <div className="text-sm text-muted">{item.label}</div>
            <div className="mt-2 text-xl font-semibold capitalize text-ink">{item.value}</div>
          </div>
        ))}
      </div>

      {phase3Onboarding && !phase3Onboarding.isComplete ? (
        <div className="rounded-md border border-amber-200 bg-amber-50 p-5">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <div className="text-sm font-semibold uppercase tracking-wide text-amber-700">Onboarding Incomplete</div>
              <h2 className="mt-2 text-xl font-semibold text-ink">Finish the business foundation</h2>
              <p className="mt-2 text-sm leading-6 text-muted">
                {phase3Onboarding.completedSteps || 0} of {phase3Onboarding.totalSteps || 5} setup checks are complete. Continue the onboarding wizard to finish the workspace foundation.
              </p>
            </div>
            <Link className="rounded-md bg-amber-600 px-4 py-2 text-sm font-semibold text-white hover:bg-amber-700" to="/dashboard/business">
              Continue Setup
            </Link>
          </div>
        </div>
      ) : null}

      {analyticsCards.length ? (
        <>
          <div className="flex items-center justify-between border-b border-line pb-3">
            <div>
              <h2 className="text-xl font-semibold text-ink">Analytics Snapshot</h2>
              <p className="mt-1 text-sm text-muted">Quick Phase 13 metrics for the selected business.</p>
            </div>
            <Link className="text-sm font-semibold text-brand" to="/dashboard/analytics">
              Open Full Analytics
            </Link>
          </div>
          <div className="grid gap-4 md:grid-cols-4">
            {analyticsCards.map((item) => (
              <div key={item.label} className="rounded-md border border-line bg-white p-4 shadow-sm">
                <div className="text-sm text-muted">{item.label}</div>
                <div className="mt-2 text-xl font-semibold text-ink">{item.value}</div>
              </div>
            ))}
          </div>
        </>
      ) : null}
    </section>
  );
}
