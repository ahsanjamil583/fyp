import {
  ArrowRight,
  BarChart3,
  Boxes,
  Building2,
  CalendarClock,
  CheckCircle2,
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
  const setupSteps = [
    {
      title: "Complete business profile",
      description: "Confirm the name, category, contact details, and fulfillment rules customers will see.",
      done: Boolean(selectedTenant.businessCategoryId && selectedTenant.slug),
      to: "/dashboard/business",
      action: "Edit profile",
      icon: Building2,
    },
    {
      title: "Choose useful modules",
      description: "Enable only the areas this business needs, so the workspace stays clean.",
      done: enabledModules.length > 0,
      to: "/dashboard/modules",
      action: "Review modules",
      icon: Puzzle,
    },
    {
      title: "Add catalog or services",
      description: "Add products, services, prices, photos, and stock before sharing the website.",
      done: (analyticsSummary?.totalItems ?? 0) > 0,
      to: "/dashboard/items",
      action: "Manage catalog",
      icon: Boxes,
    },
    {
      title: selectedTenant.websiteStatus === "published" ? "Website is live" : "Prepare and publish website",
      description:
        selectedTenant.websiteStatus === "published"
          ? "Your public website is available. Keep the catalog and page content updated from here."
          : "Preview the public website, adjust sections, then submit it for review when ready.",
      done: selectedTenant.websiteStatus === "published",
      to: "/dashboard/public-website",
      action: selectedTenant.websiteStatus === "published" ? "Manage website" : "Open website builder",
      icon: Globe,
    },
  ];
  const nextStep = setupSteps.find((step) => !step.done) || setupSteps[setupSteps.length - 1];
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
        eyebrow={selectedTenant.websiteStatus === "published" ? "Live business workspace" : "Setup guidance"}
        title={selectedTenant.name}
        description={
          selectedTenant.websiteStatus === "published"
            ? "Your website is live. Use this workspace to manage catalog, orders, customers, payments, and reports."
            : "Follow the guided path below. You do not need to configure every module at once."
        }
        actions={
          <Link className="ui-btn-primary" to={nextStep.to}>
            {nextStep.action}
            <ArrowRight size={16} />
          </Link>
        }
      />

      <Card className="bg-surface-purple">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="text-[11px] font-bold uppercase tracking-[0.16em] text-brand">
              Recommended owner flow
            </div>
            <h2 className="mt-1 text-xl font-extrabold text-ink">
              {nextStep.done ? "Keep your live business updated" : `Next: ${nextStep.title}`}
            </h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-muted">
              The dashboard is split into Start here, Sell, Automation, Insights, and Settings. Open one domain at a time and use focus mode when you want a cleaner screen.
            </p>
          </div>
          {selectedTenant.slug ? (
            <Link className="ui-btn-secondary shrink-0" to={`/businesses/${selectedTenant.slug}`}>
              <Globe size={16} />
              {selectedTenant.websiteStatus === "published" ? "View live website" : "Preview website"}
            </Link>
          ) : null}
        </div>

        <div className="mt-5 grid gap-3 lg:grid-cols-4">
          {setupSteps.map((step, index) => (
            <Link
              key={step.title}
              to={step.to}
              className={`rounded-xl border p-4 transition hover:-translate-y-0.5 hover:shadow-lift ${
                step.done ? "border-green-200 bg-green-50" : index === setupSteps.indexOf(nextStep) ? "border-brand-200 bg-white" : "border-line bg-white"
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className={`grid h-10 w-10 place-items-center rounded-xl ${step.done ? "bg-green-100 text-green-700" : "bg-brand-50 text-brand"}`}>
                  {step.done ? <CheckCircle2 size={19} /> : <step.icon size={19} />}
                </span>
                <span className="text-xs font-black text-subtle">Step {index + 1}</span>
              </div>
              <div className="mt-3 text-sm font-extrabold text-ink">{step.title}</div>
              <p className="mt-1.5 text-xs leading-5 text-muted">{step.description}</p>
              <div className="mt-3 text-xs font-bold text-brand">{step.action}</div>
            </Link>
          ))}
        </div>
      </Card>

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
