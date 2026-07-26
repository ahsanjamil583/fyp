import { useEffect, useState } from "react";

import { getAdminReports } from "../../services/adminApi.js";

function planLabel(planCode) {
  return { starter: "Basic", growth: "AI Ordering", scale: "Full Agent" }[planCode] || "Basic";
}

function planListLabel(planCodes = []) {
  return planCodes.map(planLabel).join(", ");
}

export function AdminReportsPage() {
  const [reports, setReports] = useState(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setIsLoading(true);
    getAdminReports()
      .then((data) => {
        if (active) {
          setReports(data);
          setError("");
        }
      })
      .catch((requestError) => {
        if (active) {
          setError(requestError.response?.data?.detail || "Unable to load admin reports.");
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

  return (
    <section className="space-y-6">
      <div className="border-b border-line pb-6">
        <p className="text-sm font-semibold uppercase tracking-wide text-brand">Platform Insights</p>
        <h1 className="mt-2 text-3xl font-semibold text-ink">Admin Reports</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-muted">
          Review platform-wide role distribution, website publication status, and the current module catalog in one reporting view.
        </p>
      </div>

      {error ? <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}
      {isLoading ? <div className="text-sm text-muted">Loading reports...</div> : null}

      {reports ? (
        <div className="grid gap-4 xl:grid-cols-3">
          <article className="rounded-md border border-line bg-white p-5 shadow-sm">
            <h2 className="text-lg font-semibold text-ink">User Roles</h2>
            <div className="mt-4 space-y-3">
              {(reports.userRoleBreakdown || []).map((row) => (
                <div key={row.role} className="flex items-center justify-between rounded-md bg-surface px-3 py-2 text-sm">
                  <span className="font-medium text-ink">{row.role}</span>
                  <span className="text-muted">{row.count}</span>
                </div>
              ))}
            </div>
          </article>

          <article className="rounded-md border border-line bg-white p-5 shadow-sm">
            <h2 className="text-lg font-semibold text-ink">Website Status</h2>
            <div className="mt-4 space-y-3">
              {(reports.websiteStatusBreakdown || []).map((row) => (
                <div key={row.status} className="flex items-center justify-between rounded-md bg-surface px-3 py-2 text-sm">
                  <span className="font-medium text-ink">{row.status}</span>
                  <span className="text-muted">{row.count}</span>
                </div>
              ))}
            </div>
          </article>

          <article className="rounded-md border border-line bg-white p-5 shadow-sm">
            <h2 className="text-lg font-semibold text-ink">Plan Mix</h2>
            <div className="mt-4 space-y-3">
              {Object.entries(reports.planBreakdown || {}).map(([planCode, count]) => (
                <div key={planCode} className="flex items-center justify-between rounded-md bg-surface px-3 py-2 text-sm">
                  <span className="font-medium text-ink">{planLabel(planCode)}</span>
                  <span className="text-muted">{count}</span>
                </div>
              ))}
            </div>
          </article>

          <article className="rounded-md border border-line bg-white p-5 shadow-sm xl:col-span-3">
            <h2 className="text-lg font-semibold text-ink">Module Catalog Snapshot</h2>
            <div className="mt-4 overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead className="border-b border-line text-xs uppercase tracking-wide text-muted">
                  <tr>
                    <th className="py-2 pr-4">Module</th>
                    <th className="py-2 pr-4">Category</th>
                    <th className="py-2 pr-4">Plans</th>
                    <th className="py-2 pr-4">Enabled tenants</th>
                    <th className="py-2 pr-4">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {(reports.moduleCatalog || []).map((module) => (
                    <tr key={module.code} className="border-b border-line/70">
                      <td className="py-3 pr-4 font-medium text-ink">{module.name}<div className="text-xs text-muted">{module.code}</div></td>
                      <td className="py-3 pr-4 text-muted">{module.category}</td>
                      <td className="py-3 pr-4 text-muted">{planListLabel(module.availability?.includedPlans || [])}</td>
                      <td className="py-3 pr-4 text-muted">{module.enabledTenantCount || 0}</td>
                      <td className="py-3 pr-4 text-muted">{module.isActive ? "active" : "inactive"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </article>
        </div>
      ) : null}
    </section>
  );
}
