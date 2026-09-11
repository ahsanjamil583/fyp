import { useEffect, useState } from "react";

import { getAdminOverview } from "../../services/adminApi.js";
import { SectionTitle } from "../../components/ui/SectionTitle.jsx";

function planLabel(planCode) {
  return { starter: "Basic", growth: "AI Ordering", scale: "Full Agent" }[planCode] || "Basic";
}

export function AdminOverviewPage() {
  const [overview, setOverview] = useState(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setIsLoading(true);
    getAdminOverview()
      .then((data) => {
        if (active) {
          setOverview(data);
          setError("");
        }
      })
      .catch((requestError) => {
        if (active) {
          setError(requestError.response?.data?.detail || "Unable to load admin overview.");
        }
      })
      .finally(() => {
        if (active) {
          setIsLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, []);

  const summary = overview?.summary || {};
  const cards = [
    { label: "Users", value: summary.users?.total || 0, detail: `${summary.users?.active || 0} active / ${summary.users?.newLast7Days || 0} new this week` },
    { label: "Tenants", value: summary.tenants?.total || 0, detail: `${summary.tenants?.active || 0} active / ${summary.tenants?.published || 0} published` },
    { label: "Categories", value: summary.categories?.total || 0, detail: `${summary.categories?.active || 0} active configurations` },
    { label: "Modules", value: summary.modules?.total || 0, detail: `${summary.modules?.active || 0} active in catalog` },
  ];

  return (
    <section className="space-y-6">
      <div className="border-b border-line-soft pb-5">
        <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-brand">Platform Control</p>
        <h1 className="mt-1.5 text-2xl font-extrabold tracking-tight text-ink">Admin Overview</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-muted">
          Review live SaaS health across users, tenants, plans, categories, and modules before making operational changes.
        </p>
      </div>

      {error ? <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}
      {isLoading ? <div className="text-sm text-muted">Loading platform overview...</div> : null}

      {overview ? (
        <>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {cards.map((card) => (
              <article key={card.label} className="rounded-xl border border-line bg-surface p-5">
                <div className="text-sm font-medium text-muted">{card.label}</div>
                <div className="mt-3 text-2xl font-extrabold tracking-tight text-ink">{card.value}</div>
                <div className="mt-2 text-sm text-muted">{card.detail}</div>
              </article>
            ))}
          </div>

          <div className="grid gap-4 xl:grid-cols-3">
            <article className="rounded-xl border border-line bg-white p-5 shadow-card xl:col-span-1">
              <SectionTitle>Plan Mix</SectionTitle>
              <div className="mt-4 space-y-3">
                {Object.entries(overview.planBreakdown || {}).map(([planCode, count]) => (
                  <div key={planCode} className="flex items-center justify-between rounded-xl bg-surface px-3 py-2 text-sm">
                    <span className="font-medium text-ink">{planLabel(planCode)}</span>
                    <span className="text-muted">{count}</span>
                  </div>
                ))}
              </div>
            </article>

            <article className="rounded-xl border border-line bg-white p-5 shadow-card xl:col-span-1">
              <SectionTitle>Top Categories</SectionTitle>
              <div className="mt-4 space-y-3">
                {(overview.topCategories || []).map((category) => (
                  <div key={category.id} className="flex items-center justify-between rounded-xl bg-surface px-3 py-2 text-sm">
                    <span className="font-medium text-ink">{category.name}</span>
                    <span className="text-muted">{category.count} tenants</span>
                  </div>
                ))}
                {!overview.topCategories?.length ? <div className="text-sm text-muted">No tenant category data yet.</div> : null}
              </div>
            </article>

            <article className="rounded-xl border border-line bg-white p-5 shadow-card xl:col-span-1">
              <SectionTitle>Top Modules</SectionTitle>
              <div className="mt-4 space-y-3">
                {(overview.topModules || []).map((module) => (
                  <div key={module.code} className="flex items-center justify-between rounded-xl bg-surface px-3 py-2 text-sm">
                    <span className="font-medium text-ink">{module.code}</span>
                    <span className="text-muted">{module.count} enabled</span>
                  </div>
                ))}
                {!overview.topModules?.length ? <div className="text-sm text-muted">No module usage data yet.</div> : null}
              </div>
            </article>
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <article className="rounded-xl border border-line bg-white p-5 shadow-card">
              <SectionTitle>Recent Users</SectionTitle>
              <div className="mt-4 space-y-3">
                {(overview.recentUsers || []).map((user) => (
                  <div key={user.id} className="rounded-xl border border-line p-3">
                    <div className="font-semibold text-ink">{user.fullName}</div>
                    <div className="mt-1 text-sm text-muted">{user.email}</div>
                    <div className="mt-2 text-[11px] font-bold uppercase tracking-[0.12em] text-subtle">
                      {user.globalRole} / {user.status}
                    </div>
                  </div>
                ))}
              </div>
            </article>

            <article className="rounded-xl border border-line bg-white p-5 shadow-card">
              <SectionTitle>Recent Tenants</SectionTitle>
              <div className="mt-4 space-y-3">
                {(overview.recentTenants || []).map((tenant) => (
                  <div key={tenant.id} className="rounded-xl border border-line p-3">
                    <div className="font-semibold text-ink">{tenant.name}</div>
                    <div className="mt-1 text-sm text-muted">
                      {tenant.owner?.fullName || "No owner"} / {planLabel(tenant.settings?.planCode)}
                    </div>
                    <div className="mt-2 text-[11px] font-bold uppercase tracking-[0.12em] text-subtle">
                      {tenant.status} / {tenant.websiteStatus}
                    </div>
                  </div>
                ))}
              </div>
            </article>
          </div>
        </>
      ) : null}
    </section>
  );
}
