import { useEffect, useState } from "react";

import { getAdminOverview } from "../../services/adminApi.js";

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
      <div className="border-b border-line pb-6">
        <p className="text-sm font-semibold uppercase tracking-wide text-brand">Platform Control</p>
        <h1 className="mt-2 text-3xl font-semibold text-ink">Admin Overview</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-muted">
          Review live SaaS health across users, tenants, plans, categories, and modules before making operational changes.
        </p>
      </div>

      {error ? <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}
      {isLoading ? <div className="text-sm text-muted">Loading platform overview...</div> : null}

      {overview ? (
        <>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {cards.map((card) => (
              <article key={card.label} className="rounded-md border border-line bg-surface p-5">
                <div className="text-sm font-medium text-muted">{card.label}</div>
                <div className="mt-3 text-3xl font-semibold text-ink">{card.value}</div>
                <div className="mt-2 text-sm text-muted">{card.detail}</div>
              </article>
            ))}
          </div>

          <div className="grid gap-4 xl:grid-cols-3">
            <article className="rounded-md border border-line bg-white p-5 shadow-sm xl:col-span-1">
              <h2 className="text-lg font-semibold text-ink">Plan Mix</h2>
              <div className="mt-4 space-y-3">
                {Object.entries(overview.planBreakdown || {}).map(([planCode, count]) => (
                  <div key={planCode} className="flex items-center justify-between rounded-md bg-surface px-3 py-2 text-sm">
                    <span className="font-medium text-ink">{planLabel(planCode)}</span>
                    <span className="text-muted">{count}</span>
                  </div>
                ))}
              </div>
            </article>

            <article className="rounded-md border border-line bg-white p-5 shadow-sm xl:col-span-1">
              <h2 className="text-lg font-semibold text-ink">Top Categories</h2>
              <div className="mt-4 space-y-3">
                {(overview.topCategories || []).map((category) => (
                  <div key={category.id} className="flex items-center justify-between rounded-md bg-surface px-3 py-2 text-sm">
                    <span className="font-medium text-ink">{category.name}</span>
                    <span className="text-muted">{category.count} tenants</span>
                  </div>
                ))}
                {!overview.topCategories?.length ? <div className="text-sm text-muted">No tenant category data yet.</div> : null}
              </div>
            </article>

            <article className="rounded-md border border-line bg-white p-5 shadow-sm xl:col-span-1">
              <h2 className="text-lg font-semibold text-ink">Top Modules</h2>
              <div className="mt-4 space-y-3">
                {(overview.topModules || []).map((module) => (
                  <div key={module.code} className="flex items-center justify-between rounded-md bg-surface px-3 py-2 text-sm">
                    <span className="font-medium text-ink">{module.code}</span>
                    <span className="text-muted">{module.count} enabled</span>
                  </div>
                ))}
                {!overview.topModules?.length ? <div className="text-sm text-muted">No module usage data yet.</div> : null}
              </div>
            </article>
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <article className="rounded-md border border-line bg-white p-5 shadow-sm">
              <h2 className="text-lg font-semibold text-ink">Recent Users</h2>
              <div className="mt-4 space-y-3">
                {(overview.recentUsers || []).map((user) => (
                  <div key={user.id} className="rounded-md border border-line p-3">
                    <div className="font-semibold text-ink">{user.fullName}</div>
                    <div className="mt-1 text-sm text-muted">{user.email}</div>
                    <div className="mt-2 text-xs uppercase tracking-wide text-muted">
                      {user.globalRole} / {user.status}
                    </div>
                  </div>
                ))}
              </div>
            </article>

            <article className="rounded-md border border-line bg-white p-5 shadow-sm">
              <h2 className="text-lg font-semibold text-ink">Recent Tenants</h2>
              <div className="mt-4 space-y-3">
                {(overview.recentTenants || []).map((tenant) => (
                  <div key={tenant.id} className="rounded-md border border-line p-3">
                    <div className="font-semibold text-ink">{tenant.name}</div>
                    <div className="mt-1 text-sm text-muted">
                      {tenant.owner?.fullName || "No owner"} / {planLabel(tenant.settings?.planCode)}
                    </div>
                    <div className="mt-2 text-xs uppercase tracking-wide text-muted">
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
