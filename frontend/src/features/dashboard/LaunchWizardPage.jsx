import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { useModules } from "../../context/ModuleContext.jsx";
import { useTenant } from "../../context/TenantContext.jsx";
import { applyLaunchProfile, finalizeLaunch, getLaunchStatus, requestPackageUpgrade } from "../../services/onboardingApi.js";

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
    <div className="rounded-xl border border-line bg-white p-4 shadow-sm">
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
          <Link className="rounded-md border border-line px-3 py-2 text-sm font-semibold text-ink transition hover:bg-surface" to={check.route}>
            {check.actionLabel || "Open"}
          </Link>
        ) : null}
      </div>
    </div>
  );
}

function BootstrappedDefaults({ defaults }) {
  const entries = Object.entries(defaults || {}).filter(([, enabled]) => enabled);
  if (!entries.length) return null;
  return (
    <div className="mt-3 rounded-lg bg-green-50 p-3 text-xs text-green-700">
      Auto-prepared defaults: {entries.map(([key]) => key.replace(/([A-Z])/g, " $1").toLowerCase()).join(", ")}.
    </div>
  );
}

const profileOrder = ["basic_website", "ai_ordering", "full_agent_demo"];

export function LaunchWizardPage() {
  const { selectedTenant, refreshTenants, selectTenant } = useTenant();
  const { refreshTenantModules } = useModules();
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
      setError(err.response?.data?.detail || "Unable to load launch wizard.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadStatus().catch(() => {});
  }, [selectedTenant?.id]);

  const profiles = useMemo(() => {
    const profileMap = status?.profiles || {};
    return profileOrder.filter((code) => profileMap[code]).map((code) => ({ code, ...profileMap[code] }));
  }, [status?.profiles]);

  async function handleApplyProfile(profileCode) {
    if (!selectedTenant?.id) return;
    setLoading(true);
    setMessage("");
    setError("");
    try {
      const data = await applyLaunchProfile(selectedTenant.id, { profileCode, autoUpgradePlan: true });
      setStatus(data);
      await refreshTenantModules(selectedTenant.id);
      const tenants = await refreshTenants();
      const latest = tenants.find((tenant) => tenant.id === selectedTenant.id);
      if (latest) selectTenant(latest);
      const bootstrapped = Object.entries(data.appliedProfile?.bootstrappedDefaults || {}).filter(([, value]) => value).map(([key]) => key);
      setMessage(`${data.appliedProfile?.name || "Launch profile"} applied. Enabled: ${(data.appliedProfile?.enabledModules || []).join(", ") || "already enabled"}.${bootstrapped.length ? ` Defaults prepared: ${bootstrapped.join(", ")}.` : ""}`);
    } catch (err) {
      setError(err.response?.data?.detail || "Unable to apply launch profile.");
    } finally {
      setLoading(false);
    }
  }

  async function handleRequestUpgrade(profileCode) {
    if (!selectedTenant?.id) return;
    setLoading(true);
    setMessage("");
    setError("");
    try {
      const data = await requestPackageUpgrade(selectedTenant.id, { profileCode, autoUpgradePlan: false });
      setStatus(data);
      setMessage(data.upgradeRequest?.message || "Upgrade requested. Admin approval or payment confirmation is required before paid modules unlock.");
    } catch (err) {
      setError(err.response?.data?.detail || "Unable to request package upgrade.");
    } finally {
      setLoading(false);
    }
  }

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
      setMessage(data.finalized?.publishError ? `Launch saved, but publish needs attention: ${data.finalized.publishError.detail}` : "Launch finalized and website published.");
    } catch (err) {
      setError(err.response?.data?.detail || "Unable to finalize launch.");
    } finally {
      setLoading(false);
    }
  }

  if (!selectedTenant) {
    return (
      <div className="rounded-xl border border-line bg-white p-6 shadow-sm">
        <h1 className="text-2xl font-bold text-ink">Launch Wizard</h1>
        <p className="mt-2 text-muted">Create or select a business first, then this wizard will guide you from setup to published AI-ready website.</p>
        <Link to="/dashboard/business" className="mt-4 inline-flex rounded-md bg-brand px-4 py-2 text-sm font-semibold text-white">Create business</Link>
      </div>
    );
  }

  const summary = status?.summary || {};
  const checks = status?.checks || [];

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-line bg-white p-6 shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="text-sm font-semibold uppercase tracking-wide text-brand">Phase 28</p>
            <h1 className="mt-1 text-2xl font-bold text-ink">Launch Wizard</h1>
            <p className="mt-2 max-w-3xl text-muted">
              Choose one package for this business. Basic is free and applies immediately. AI Ordering and Full Agent are paid packages and require payment or admin approval before modules unlock.
            </p>
          </div>
          <button
            type="button"
            onClick={handleFinalize}
            disabled={loading || (status && !summary.canPublish)}
            title={status && !summary.canPublish ? "Complete required launch checks before publishing." : "Finalize and publish website"}
            className="rounded-md bg-brand px-4 py-2 text-sm font-semibold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Finalize & Publish
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

      {message ? <div className="rounded-md border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700">{message}</div> : null}
      {error ? <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div> : null}

      <div className="grid gap-4 lg:grid-cols-3">
        {profiles.map((profile) => (
          <div key={profile.code} className="rounded-xl border border-line bg-white p-5 shadow-sm">
            <div className="flex items-start justify-between gap-3">
              <h2 className="text-lg font-semibold text-ink">{profile.name}</h2>
              <span className={profile.isPaid ? "rounded-full bg-amber-50 px-2 py-1 text-xs font-bold text-amber-700 ring-1 ring-amber-200" : "rounded-full bg-green-50 px-2 py-1 text-xs font-bold text-green-700 ring-1 ring-green-200"}>
                {profile.priceLabel || (profile.isPaid ? "Paid" : "Free")}
              </span>
            </div>
            <p className="mt-2 text-sm text-muted">{profile.description}</p>
            <div className="mt-3 text-xs text-muted">Package: <span className="font-semibold text-ink">{profile.targetPlanDisplayName || profile.targetPlanName}</span></div>
            {profile.features?.length ? (
              <ul className="mt-3 space-y-1 text-sm text-muted">
                {profile.features.map((feature) => (
                  <li key={feature}>- {feature}</li>
                ))}
              </ul>
            ) : null}
            {profile.isPaid && profile.accessStatus !== "approved" ? (
              <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                Payment/admin approval required before these modules can be enabled.
                {profile.accessStatus === "pending_approval" ? " Upgrade request is pending." : ""}
              </div>
            ) : null}
            <div className="mt-3 flex flex-wrap gap-2">
              {(profile.modules || []).slice(0, 7).map((moduleCode) => (
                <span key={moduleCode} className="rounded-full bg-surface px-2 py-1 text-xs text-muted">{moduleCode}</span>
              ))}
              {(profile.modules || []).length > 7 ? <span className="rounded-full bg-surface px-2 py-1 text-xs text-muted">+{profile.modules.length - 7}</span> : null}
            </div>
            {status?.summary?.profileCode === profile.code ? <BootstrappedDefaults defaults={status?.tenant?.settings?.onboarding?.phase28?.bootstrapDefaults} /> : null}
            <button
              type="button"
              onClick={() => (profile.isPaid && profile.accessStatus !== "approved" ? handleRequestUpgrade(profile.code) : handleApplyProfile(profile.code))}
              disabled={loading}
              className={profile.isPaid && profile.accessStatus !== "approved" ? "mt-4 w-full rounded-md bg-ink px-4 py-2 text-sm font-semibold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50" : "mt-4 w-full rounded-md border border-line px-4 py-2 text-sm font-semibold text-ink transition hover:bg-surface disabled:cursor-not-allowed disabled:opacity-50"}
            >
              {profile.isPaid && profile.accessStatus !== "approved" ? "Request upgrade" : "Apply this package"}
            </button>
          </div>
        ))}
      </div>

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-bold text-ink">Launch checklist</h2>
          <button type="button" onClick={loadStatus} disabled={loading} className="rounded-md border border-line px-3 py-2 text-sm font-semibold text-ink hover:bg-surface">
            Refresh
          </button>
        </div>
        {loading && !checks.length ? <div className="rounded-xl border border-line bg-white p-6 text-muted">Loading launch checklist...</div> : null}
        {checks.map((check) => <CheckRow key={check.code} check={check} />)}
      </div>
    </div>
  );
}
