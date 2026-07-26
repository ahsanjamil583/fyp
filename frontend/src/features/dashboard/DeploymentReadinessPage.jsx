import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, RefreshCw, ShieldCheck, XCircle } from "lucide-react";

import { getDemoAccounts, getReadinessReport } from "../../services/readinessApi.js";

const statusStyles = {
  pass: "border-emerald-200 bg-emerald-50 text-emerald-800",
  warn: "border-amber-200 bg-amber-50 text-amber-800",
  fail: "border-red-200 bg-red-50 text-red-800",
};

function StatusIcon({ status }) {
  if (status === "pass") return <CheckCircle2 className="h-5 w-5" />;
  if (status === "fail") return <XCircle className="h-5 w-5" />;
  return <AlertTriangle className="h-5 w-5" />;
}

function StatusBadge({ status }) {
  return <span className={`rounded-full border px-2 py-1 text-xs font-semibold uppercase ${statusStyles[status] || statusStyles.warn}`}>{status}</span>;
}

export function DeploymentReadinessPage() {
  const readinessQuery = useQuery({ queryKey: ["deployment-readiness"], queryFn: getReadinessReport, refetchInterval: 60000 });
  const demoQuery = useQuery({ queryKey: ["demo-accounts"], queryFn: getDemoAccounts });

  const report = readinessQuery.data;
  const demo = demoQuery.data;
  const overall = report?.overallStatus || "loading";

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-line bg-white p-6 shadow-sm">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-primary">
              <ShieldCheck className="h-4 w-4" /> Phase 27
            </div>
            <h1 className="mt-2 text-2xl font-bold text-ink">Final hardening and deployment readiness</h1>
            <p className="mt-2 max-w-3xl text-sm text-muted">
              Use this page before demo/submission to confirm core runtime configuration, health checks,
              directories, integrations, rate limiting, and demo account information.
            </p>
          </div>
          <button
            type="button"
            onClick={() => readinessQuery.refetch()}
            className="inline-flex items-center justify-center gap-2 rounded-lg border border-line px-4 py-2 text-sm font-semibold text-ink transition hover:bg-surface"
          >
            <RefreshCw className="h-4 w-4" /> Refresh
          </button>
        </div>
      </div>

      {readinessQuery.isLoading ? (
        <div className="rounded-2xl border border-line bg-white p-6 text-sm text-muted">Loading readiness report...</div>
      ) : readinessQuery.isError ? (
        <div className="rounded-2xl border border-red-200 bg-red-50 p-6 text-sm text-red-700">Could not load readiness report. Make sure the backend is running.</div>
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-4">
            <div className="rounded-2xl border border-line bg-white p-5 shadow-sm md:col-span-1">
              <div className="text-xs font-semibold uppercase tracking-wide text-muted">Overall status</div>
              <div className="mt-2 text-xl font-bold capitalize text-ink">{overall.replaceAll("_", " ")}</div>
              <div className="mt-3 text-xs text-muted">Version {report?.runtime?.appVersion} · {report?.runtime?.buildLabel}</div>
            </div>
            {Object.entries(report?.totals || {}).map(([key, value]) => (
              <div key={key} className="rounded-2xl border border-line bg-white p-5 shadow-sm">
                <div className="text-xs font-semibold uppercase tracking-wide text-muted">{key}</div>
                <div className="mt-2 text-3xl font-bold text-ink">{value}</div>
              </div>
            ))}
          </div>

          <div className="rounded-2xl border border-line bg-white p-6 shadow-sm">
            <h2 className="text-lg font-bold text-ink">Readiness checks</h2>
            <div className="mt-4 grid gap-3">
              {(report?.checks || []).map((check) => (
                <div key={check.code} className={`rounded-xl border p-4 ${statusStyles[check.status] || statusStyles.warn}`}>
                  <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                    <div className="flex items-start gap-3">
                      <StatusIcon status={check.status} />
                      <div>
                        <div className="font-semibold">{check.label}</div>
                        <div className="mt-1 text-sm opacity-90">{check.message}</div>
                      </div>
                    </div>
                    <StatusBadge status={check.status} />
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-2xl border border-line bg-white p-6 shadow-sm">
              <h2 className="text-lg font-bold text-ink">Runtime</h2>
              <dl className="mt-4 space-y-3 text-sm">
                {Object.entries(report?.runtime || {}).map(([key, value]) => (
                  <div key={key} className="flex justify-between gap-4 border-b border-line pb-2 last:border-0">
                    <dt className="font-semibold text-muted">{key}</dt>
                    <dd className="text-right text-ink">{String(value)}</dd>
                  </div>
                ))}
              </dl>
            </div>
            <div className="rounded-2xl border border-line bg-white p-6 shadow-sm">
              <h2 className="text-lg font-bold text-ink">Demo accounts</h2>
              {demoQuery.isLoading ? (
                <p className="mt-4 text-sm text-muted">Loading demo account info...</p>
              ) : (
                <div className="mt-4 space-y-3 text-sm">
                  {demo ? (
                    <>
                      <div className="rounded-lg bg-surface p-3">
                        <div className="font-semibold text-ink">Business Owner</div>
                        <div className="text-muted">{demo.businessOwner.email} / {demo.businessOwner.password}</div>
                      </div>
                      <div className="rounded-lg bg-surface p-3">
                        <div className="font-semibold text-ink">Customer</div>
                        <div className="text-muted">{demo.customer.email} / {demo.customer.password}</div>
                      </div>
                      <div className="rounded-lg bg-surface p-3">
                        <div className="font-semibold text-ink">Public demo slug</div>
                        <div className="text-muted">/businesses/{demo.businessSlug}</div>
                      </div>
                    </>
                  ) : null}
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
