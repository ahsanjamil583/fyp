import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { useTenant } from "../../context/TenantContext.jsx";
import { finalizeLaunch, getLaunchStatus } from "../../services/onboardingApi.js";
import { formatApiError } from "../../utils/apiErrors.js";
import { getApiErrorMessage } from "../../services/apiError.js";

function StatusPill({ status }) {
  const className =
    status === "complete"
      ? "bg-green-50 text-green-700 ring-green-200"
      : status === "missing"
        ? "bg-amber-50 text-amber-700 ring-amber-200"
        : "bg-slate-50 text-slate-600 ring-slate-200";
  return <span className={`rounded-full px-2 py-1 text-xs font-semibold ring-1 ${className}`}>{status.replace("_", " ")}</span>;
}

function CheckRow({ check }) {
  return (
    <div className="rounded-xl border border-line bg-white p-4 shadow-card">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-semibold text-ink">{check.title}</h3>
            <StatusPill status={check.status} />
            {!check.required ? <span className="rounded-full bg-surface px-2 py-1 text-xs font-semibold text-muted">Optional</span> : null}
          </div>
          <p className="mt-1 text-sm text-muted">{check.description}</p>
          {check.meta?.missingModules?.length ? (
            <p className="mt-2 text-xs text-amber-700">Missing modules: {check.meta.missingModules.join(", ")}</p>
          ) : null}
          {check.meta?.activeItems !== undefined ? (
            <p className="mt-2 text-xs text-muted">Active items: {check.meta.activeItems} · Sellable/bookable: {check.meta.sellableItems}</p>
          ) : null}
          {check.meta?.knowledgeDocuments !== undefined ? (
            <p className="mt-2 text-xs text-muted">Active knowledge docs: {check.meta.knowledgeDocuments}</p>
          ) : null}
        </div>
        {check.route ? (
          <Link className="rounded-xl border border-line px-3 py-2 text-sm font-semibold text-ink transition hover:bg-surface" to={check.route}>
            {check.actionLabel || "Open"}
          </Link>
        ) : null}
      </div>
    </div>
  );
}

export function LaunchWizardPage() {
  const { selectedTenant, refreshTenants, selectTenant } = useTenant();
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function loadStatus() {
    if (!selectedTenant?.id) {
      setStatus(null);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const data = await getLaunchStatus(selectedTenant.id);
      setStatus(data);
    } catch (err) {
      setError(getApiErrorMessage(err, "Unable to load launch wizard."));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadStatus().catch(() => {});
  }, [selectedTenant?.id]);

  async function handleFinalize() {
    if (!selectedTenant?.id) return;
    setLoading(true);
    setMessage("");
    setError("");
    try {
      const data = await finalizeLaunch(selectedTenant.id, { publishWebsite: true, allowWarnings: true });
      setStatus(data);
      const tenants = await refreshTenants();
      const latest = tenants.find((tenant) => tenant.id === selectedTenant.id);
      if (latest) selectTenant(latest);
      setMessage(data.finalized?.publishError ? `Launch saved, but publish needs attention: ${formatApiError(data.finalized.publishError.detail)}` : "Launch finalized and submitted for admin website review.");
    } catch (err) {
      setError(getApiErrorMessage(err, "Unable to finalize launch."));
    } finally {
      setLoading(false);
    }
  }

  if (!selectedTenant) {
    return (
      <div className="rounded-xl border border-line bg-white p-6 shadow-card">
        <h1 className="text-2xl font-bold text-ink">Launch Wizard</h1>
        <p className="mt-2 text-muted">Create or select a business first, then this wizard will guide you from setup to published AI-ready website.</p>
        <Link to="/dashboard/business" className="mt-4 inline-flex rounded-xl bg-brand px-4 py-2 text-sm font-semibold text-white">Create business</Link>
      </div>
    );
  }

  const summary = status?.summary || {};
  const checks = status?.checks || [];

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-line bg-white p-6 shadow-card">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-brand">Phase 28</p>
            <h1 className="mt-1 text-2xl font-bold text-ink">Launch Wizard</h1>
            <p className="mt-2 max-w-3xl text-muted">
              Review readiness, finish required setup, and publish the business website when everything is prepared.
            </p>
          </div>
          <button
            type="button"
            onClick={handleFinalize}
            disabled={loading || (status && !summary.canPublish)}
            title={status && !summary.canPublish ? "Complete required launch checks before requesting publishing." : "Finalize and request admin website review"}
            className="rounded-xl bg-brand px-4 py-2 text-sm font-semibold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Finalize & Request Review
          </button>
        </div>

        <div className="mt-6 grid gap-4 md:grid-cols-4">
          <div className="rounded-xl bg-surface p-4">
            <div className="text-2xl font-bold text-ink">{summary.requiredPercent ?? 0}%</div>
            <div className="text-sm text-muted">Required readiness</div>
          </div>
          <div className="rounded-xl bg-surface p-4">
            <div className="text-2xl font-bold text-ink">{summary.overallPercent ?? 0}%</div>
            <div className="text-sm text-muted">Overall readiness</div>
          </div>
          <div className="rounded-xl bg-surface p-4">
            <div className="text-2xl font-bold capitalize text-ink">{summary.status?.replaceAll("_", " ") || "loading"}</div>
            <div className="text-sm text-muted">Launch status</div>
          </div>
          <div className="rounded-xl bg-surface p-4">
            <div className="text-2xl font-bold capitalize text-ink">{summary.websiteStatus?.replaceAll("_", " ") || selectedTenant.websiteStatus}</div>
            <div className="text-sm text-muted">Website</div>
          </div>
        </div>
      </div>

      {message ? <div className="rounded-xl border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700">{message}</div> : null}
      {error ? <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div> : null}

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-bold text-ink">Launch checklist</h2>
          <button type="button" onClick={loadStatus} disabled={loading} className="rounded-xl border border-line px-3 py-2 text-sm font-semibold text-ink hover:bg-surface">
            Refresh
          </button>
        </div>
        {loading && !checks.length ? <div className="rounded-xl border border-line bg-white p-6 text-muted">Loading launch checklist...</div> : null}
        {checks.map((check) => <CheckRow key={check.code} check={check} />)}
      </div>
    </div>
  );
}
