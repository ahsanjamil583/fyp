import { useEffect, useState } from "react";
import { BarChart3, FileText, Globe, SquareStack } from "lucide-react";

import { getAdminReports } from "../../services/adminApi.js";
import { SectionTitle } from "../../components/ui/SectionTitle.jsx";

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
      <div className="rounded-2xl border border-line bg-surface-purple p-5 shadow-card">
        <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-brand">Platform Insights</p>
        <h1 className="mt-1.5 text-2xl font-extrabold tracking-tight text-ink">Admin Reports</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-muted">
          Review platform-wide role distribution, website publication status, plan mix, and module usage in one reporting view.
        </p>
        <div className="mt-5 grid gap-2 text-xs font-bold text-muted sm:grid-cols-4">
          {[
            [BarChart3, "Role mix"],
            [Globe, "Website status"],
            [FileText, "Plan mix"],
            [SquareStack, "Module usage"],
          ].map(([Icon, label]) => (
            <div key={label} className="rounded-xl border border-line bg-white px-3 py-3">
              <Icon className="mr-2 inline text-brand" size={15} />
              {label}
            </div>
          ))}
        </div>
      </div>

      {error ? <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}
      {isLoading ? <div className="text-sm text-muted">Loading reports...</div> : null}

      {reports ? (
        <div className="grid gap-4 xl:grid-cols-3">
          <article className="rounded-xl border border-line bg-white p-5 shadow-card">
            <SectionTitle>User Roles</SectionTitle>
            <div className="mt-4 space-y-3">
              {(reports.userRoleBreakdown || []).map((row) => (
                <div key={row.role} className="flex items-center justify-between rounded-xl bg-surface px-3 py-2 text-sm">
                  <span className="font-medium text-ink">{row.role}</span>
                  <span className="text-muted">{row.count}</span>
                </div>
              ))}
            </div>
          </article>

          <article className="rounded-xl border border-line bg-white p-5 shadow-card">
            <SectionTitle>Website Status</SectionTitle>
            <div className="mt-4 space-y-3">
              {(reports.websiteStatusBreakdown || []).map((row) => (
                <div key={row.status} className="flex items-center justify-between rounded-xl bg-surface px-3 py-2 text-sm">
                  <span className="font-medium text-ink">{row.status}</span>
                  <span className="text-muted">{row.count}</span>
                </div>
              ))}
            </div>
          </article>

          <article className="rounded-xl border border-line bg-white p-5 shadow-card">
            <SectionTitle>Plan Mix</SectionTitle>
            <div className="mt-4 space-y-3">
              {Object.entries(reports.planBreakdown || {}).map(([planCode, count]) => (
                <div key={planCode} className="flex items-center justify-between rounded-xl bg-surface px-3 py-2 text-sm">
                  <span className="font-medium text-ink">{planLabel(planCode)}</span>
                  <span className="text-muted">{count}</span>
                </div>
              ))}
            </div>
          </article>

          <article className="rounded-xl border border-line bg-white p-5 shadow-card xl:col-span-3">
            <SectionTitle>Module Catalog Snapshot</SectionTitle>
            <div className="mt-4 overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead className="border-b border-line text-[11px] font-bold uppercase tracking-[0.12em] text-subtle">
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
