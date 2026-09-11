import {
  ArrowRight,
  BarChart3,
  Boxes,
  Building2,
  CalendarClock,
  Globe,
  Puzzle,
  Rocket,
  ShoppingCart,
  Users,
} from "lucide-react";
import { Link } from "react-router-dom";
import { useEffect, useState } from "react";

import { Card, EmptyState, PageHeader, SectionHeading, StatCard } from "../../components/ui/index.jsx";
import { AreaChart, SERIES_COLORS } from "../../components/ui/charts.jsx";

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
      <EmptyState
        icon={Building2}
        title="Create your first business"
        description="Set up a business profile and pick a category. Modules, your storefront and analytics all attach to it."
        actionLabel="Create Business"
        actionTo="/dashboard/business"
      />
    );
  }

  const summary = [
    { label: "Businesses", value: tenants.length, icon: Building2, tone: "violet" },
    { label: "Enabled modules", value: enabledModules.length, icon: Puzzle, tone: "purple" },
    { label: "Website", value: selectedTenant.websiteStatus, icon: Globe, tone: "blue" },
    { label: "Status", value: selectedTenant.status, icon: Rocket, tone: "green" },
  ];

  const analyticsSummary = analytics?.summary;
  const trends = analytics?.trends || [];
  const phase3Onboarding = selectedTenant.settings?.onboarding?.phase3;
  const analyticsCards = analyticsSummary
    ? [
        { label: "Customers", value: analyticsSummary.totalCustomers ?? 0, icon: Users, tone: "blue" },
        { label: "Items", value: analyticsSummary.totalItems ?? 0, icon: Boxes, tone: "violet" },
        { label: "Orders", value: analyticsSummary.totalOrders ?? 0, icon: ShoppingCart, tone: "purple" },
        { label: "Today", value: analyticsSummary.todayOrders ?? 0, icon: CalendarClock, tone: "orange" },
      ]
    : [];

  return (
    <section className="space-y-6">
      <PageHeader
        icon={Building2}
        eyebrow="Overview"
        title={selectedTenant.name}
        description="Your workspace at a glance. Enable the modules that match this business, then track how it performs."
        actions={
          <Link className="ui-btn-primary" to="/dashboard/modules">
            Manage Modules
            <ArrowRight size={16} />
          </Link>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {summary.map((item) => (
          <StatCard key={item.label} label={item.label} value={item.value} icon={item.icon} tone={item.tone} />
        ))}
      </div>

      {phase3Onboarding && !phase3Onboarding.isComplete ? (
        <Card className="border-orange-200 bg-orange-50">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex items-start gap-4">
              <span className="grid h-12 w-12 shrink-0 place-items-center rounded-xl bg-orange-100 text-orange-600">
                <Rocket size={22} strokeWidth={2.1} />
              </span>
              <div>
                <div className="text-[11px] font-bold uppercase tracking-[0.16em] text-orange-600">
                  Onboarding incomplete
                </div>
                <h2 className="mt-1 text-lg font-bold text-ink">Finish the business foundation</h2>
                <p className="mt-1.5 text-sm leading-6 text-muted">
                  {phase3Onboarding.completedSteps || 0} of {phase3Onboarding.totalSteps || 5} setup checks complete.
                </p>
                <div className="mt-3 h-2 w-full max-w-xs overflow-hidden rounded-full bg-orange-100">
                  <div
                    className="h-full rounded-full bg-orange-500 transition-all"
                    style={{
                      width: `${Math.round(((phase3Onboarding.completedSteps || 0) / (phase3Onboarding.totalSteps || 5)) * 100)}%`,
                    }}
                  />
                </div>
              </div>
            </div>
            <Link className="ui-btn-primary shrink-0" to="/dashboard/business">
              Continue Setup
              <ArrowRight size={16} />
            </Link>
          </div>
        </Card>
      ) : null}

      {trends.length ? (
        <Card>
          <SectionHeading
            icon={BarChart3}
            title="Last 7 Days"
            description="Orders and revenue side by side"
            actions={
              <Link className="inline-flex items-center gap-1.5 text-sm font-bold text-brand hover:underline" to="/dashboard/analytics">
                Full analytics
                <ArrowRight size={15} />
              </Link>
            }
          />
          <AreaChart
            data={trends}
            height={250}
            series={[
              { key: "orders", name: "Orders", color: SERIES_COLORS.purple },
              { key: "revenue", name: "Revenue", color: SERIES_COLORS.blue, area: false },
            ]}
          />
        </Card>
      ) : null}

      {analyticsCards.length ? (
        <>
          <SectionHeading
            icon={BarChart3}
            title="Analytics Snapshot"
            description="Live metrics for the selected business."
            actions={
              <Link className="inline-flex items-center gap-1.5 text-sm font-bold text-brand hover:underline" to="/dashboard/analytics">
                Open full analytics
                <ArrowRight size={15} />
              </Link>
            }
          />
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {analyticsCards.map((item) => (
              <StatCard key={item.label} label={item.label} value={item.value} icon={item.icon} tone={item.tone} />
            ))}
          </div>
        </>
      ) : null}
    </section>
  );
}
