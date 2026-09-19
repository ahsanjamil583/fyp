import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, ExternalLink, Filter, ShieldCheck, XCircle } from "lucide-react";

import { decideAdminPackageRequest, decideAdminWebsiteRequest, getAdminTenants, updateAdminTenant } from "../../services/adminApi.js";
import { getAdminBusinessCategories } from "../../services/businessCategoryApi.js";
import { SectionTitle } from "../../components/ui/SectionTitle.jsx";
import { getApiErrorMessage } from "../../services/apiError.js";

export function AdminTenantsPage() {
  const [tenants, setTenants] = useState([]);
  const [categories, setCategories] = useState([]);
  const [busyTenant, setBusyTenant] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    refreshPage();
  }, []);

  async function refreshPage() {
    setIsLoading(true);
    try {
      const [tenantRows, categoryRows] = await Promise.all([getAdminTenants(), getAdminBusinessCategories()]);
      setTenants(tenantRows);
      setCategories(categoryRows);
      setError("");
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Unable to load tenants."));
    } finally {
      setIsLoading(false);
    }
  }

  async function saveTenant(tenant, patch) {
    setBusyTenant(tenant.id);
    setError("");
    setMessage("");
    try {
      const updated = await updateAdminTenant(tenant.id, patch);
      setTenants((current) => current.map((item) => (item.id === tenant.id ? updated : item)));
      setMessage(`Updated ${updated.name}.`);
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Unable to update tenant."));
    } finally {
      setBusyTenant("");
    }
  }

  async function decidePackageRequest(tenant, request, status) {
    const note =
      status === "rejected"
        ? window.prompt(`Reject ${request.profileName || request.planName} upgrade for ${tenant.name}. Add an optional reason:`, "")
        : window.prompt(`Approve ${request.profileName || request.planName} upgrade for ${tenant.name}. Optional admin note:`, "Approved for demo/testing.");
    if (note === null) return;
    setBusyTenant(`${tenant.id}:${request.planCode}`);
    setError("");
    setMessage("");
    try {
      const updated = await decideAdminPackageRequest(tenant.id, request.planCode, { status, note });
      setTenants((current) => current.map((item) => (item.id === tenant.id ? updated : item)));
      setMessage(`${request.profileName || request.planName} request ${status} for ${updated.name}.`);
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, `Unable to ${status} package request.`));
    } finally {
      setBusyTenant("");
    }
  }

  async function decideWebsiteRequest(tenant, status) {
    const note =
      status === "rejected"
        ? window.prompt(`Reject website request for ${tenant.name}. Add the reason for the owner:`, "")
        : window.prompt(`Approve and publish ${tenant.name}. Optional admin note:`, "Approved. Business details and website setup are complete.");
    if (note === null) return;
    setBusyTenant(`${tenant.id}:website`);
    setError("");
    setMessage("");
    try {
      const updated = await decideAdminWebsiteRequest(tenant.id, { status, note });
      setTenants((current) => current.map((item) => (item.id === tenant.id ? updated : item)));
      setMessage(`Website request ${status} for ${updated.name}.`);
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, `Unable to ${status} website request.`));
    } finally {
      setBusyTenant("");
    }
  }

  const pendingRequests = tenants.flatMap((tenant) =>
    (tenant.upgradeRequests || [])
      .filter((request) => request.status === "pending_approval")
      .map((request) => ({ tenant, request }))
  );
  const pendingWebsiteRequests = tenants.filter((tenant) => tenant.websiteApprovalStatus === "pending" || tenant.websiteStatus === "pending_review");
  const publishedCount = tenants.filter((tenant) => tenant.websiteStatus === "published").length;
  const activeCount = tenants.filter((tenant) => tenant.status === "active").length;

  return (
    <section className="space-y-6">
      <div className="rounded-2xl border border-line bg-surface-purple p-5 shadow-card">
        <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-brand">SaaS Management</p>
        <h1 className="mt-1.5 text-2xl font-extrabold tracking-tight text-ink">Business / tenant review</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-muted">
          Review business readiness, preview submitted websites, approve or reject publication, and manage tenant status safely.
        </p>
        <div className="mt-5 grid gap-3 sm:grid-cols-3">
          <MiniStat label="Pending websites" value={pendingWebsiteRequests.length} tone={pendingWebsiteRequests.length ? "amber" : "green"} />
          <MiniStat label="Active businesses" value={activeCount} />
          <MiniStat label="Published websites" value={publishedCount} />
        </div>
      </div>

      {message ? <div className="rounded-xl border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">{message}</div> : null}
      {error ? <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}
      {isLoading ? <div className="text-sm text-muted">Loading tenants...</div> : null}

      <div className="rounded-xl border border-line bg-white p-5 shadow-card">
        <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
          <div>
            <SectionTitle>Website approval requests</SectionTitle>
            <p className="mt-1 text-sm text-muted">Approve only serious businesses that completed their profile, contact, location, website template, and at least one public item.</p>
          </div>
          <span className={pendingWebsiteRequests.length ? "rounded-full bg-amber-50 px-3 py-1 text-xs font-bold text-amber-700 ring-1 ring-amber-200" : "rounded-full bg-green-50 px-3 py-1 text-xs font-bold text-green-700 ring-1 ring-green-200"}>
            {pendingWebsiteRequests.length} pending
          </span>
        </div>
        <div className="mt-4 space-y-3">
          {pendingWebsiteRequests.map((tenant) => {
            const criteria = tenant.websiteApprovalCriteria || {};
            const checks = criteria.checks || [];
            const passedChecks = checks.filter((check) => check.passed).length;
            return (
              <div key={`${tenant.id}-website-request`} className="rounded-xl border border-amber-200 bg-amber-50 p-4">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div>
                    <div className="font-semibold text-ink">{tenant.name} requested website publishing</div>
                    <div className="mt-1 text-sm text-muted">
                      Owner: {tenant.owner?.fullName || "Unknown"} / {tenant.owner?.email || "No email"} / Score: {criteria.score ?? passedChecks}/{criteria.total ?? checks.length} / Requested: {tenant.websiteApprovalRequestedAt ? new Date(tenant.websiteApprovalRequestedAt).toLocaleString() : "Unknown time"}
                    </div>
                    {checks.length ? (
                      <div className="mt-3 grid gap-2 md:grid-cols-2">
                        {checks.map((check) => (
                          <div key={check.key} className={check.passed ? "rounded-xl border border-green-100 bg-white px-3 py-2 text-xs text-green-800" : "rounded-xl border border-red-100 bg-white px-3 py-2 text-xs text-red-700"}>
                            {check.passed ? <CheckCircle2 className="mr-1 inline" size={13} /> : <XCircle className="mr-1 inline" size={13} />}
                            <span className="font-semibold">{check.passed ? "Pass" : "Missing"}:</span> {check.label}
                            {check.message ? <div className="mt-1 opacity-80">{check.message}</div> : null}
                          </div>
                        ))}
                      </div>
                    ) : null}
                    {tenant.websiteApprovalNote ? (
                      <div className="mt-3 rounded-xl border border-line bg-white px-3 py-2 text-sm text-muted">
                        Last admin note: {tenant.websiteApprovalNote}
                      </div>
                    ) : null}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {tenant.slug ? (
                      <Link
                        to={`/businesses/${tenant.slug}`}
                        className="rounded-xl border border-line bg-white px-3 py-2 text-sm font-semibold text-ink hover:bg-surface"
                      >
                        <ExternalLink className="mr-1 inline" size={14} />
                        Preview
                      </Link>
                    ) : null}
                    <button
                      type="button"
                      disabled={busyTenant === `${tenant.id}:website`}
                      onClick={() => decideWebsiteRequest(tenant, "approved")}
                      className="rounded-xl bg-green-600 px-3 py-2 text-sm font-semibold text-white hover:bg-green-700 disabled:opacity-50"
                    >
                      <ShieldCheck className="mr-1 inline" size={14} />
                      Approve & publish
                    </button>
                    <button
                      type="button"
                      disabled={busyTenant === `${tenant.id}:website`}
                      onClick={() => decideWebsiteRequest(tenant, "rejected")}
                      className="rounded-xl border border-red-200 bg-white px-3 py-2 text-sm font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50"
                    >
                      Reject
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
          {!pendingWebsiteRequests.length && !isLoading ? <div className="rounded-xl border border-dashed border-line bg-surface p-4 text-sm text-muted">No pending website requests right now.</div> : null}
        </div>
      </div>

      <div className="rounded-xl border border-line bg-white p-5 shadow-card">
        <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
          <div>
            <SectionTitle>Package upgrade requests</SectionTitle>
            <p className="mt-1 text-sm text-muted">Approve paid package requests only after payment confirmation or for demo/admin approval.</p>
          </div>
          <span className={pendingRequests.length ? "rounded-full bg-amber-50 px-3 py-1 text-xs font-bold text-amber-700 ring-1 ring-amber-200" : "rounded-full bg-green-50 px-3 py-1 text-xs font-bold text-green-700 ring-1 ring-green-200"}>
            {pendingRequests.length} pending
          </span>
        </div>
        <div className="mt-4 space-y-3">
          {pendingRequests.map(({ tenant, request }) => (
            <div key={`${tenant.id}-${request.planCode}`} className="rounded-xl border border-amber-200 bg-amber-50 p-4">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                <div>
                  <div className="font-semibold text-ink">{tenant.name} requested {request.profileName || request.planName}</div>
                  <div className="mt-1 text-sm text-muted">
                    Owner: {tenant.owner?.fullName || "Unknown"} | Plan: {request.planName} | Requested: {request.requestedAt ? new Date(request.requestedAt).toLocaleString() : "Unknown time"}
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    disabled={busyTenant === `${tenant.id}:${request.planCode}`}
                    onClick={() => decidePackageRequest(tenant, request, "approved")}
                    className="rounded-xl bg-green-600 px-3 py-2 text-sm font-semibold text-white hover:bg-green-700 disabled:opacity-50"
                  >
                    Approve
                  </button>
                  <button
                    type="button"
                    disabled={busyTenant === `${tenant.id}:${request.planCode}`}
                    onClick={() => decidePackageRequest(tenant, request, "rejected")}
                    className="rounded-xl border border-red-200 bg-white px-3 py-2 text-sm font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50"
                  >
                    Reject
                  </button>
                </div>
              </div>
            </div>
          ))}
          {!pendingRequests.length && !isLoading ? <div className="rounded-xl border border-dashed border-line bg-surface p-4 text-sm text-muted">No pending upgrade requests right now.</div> : null}
        </div>
      </div>

      <div className="space-y-4">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2 text-sm font-bold text-ink">
            <Filter size={16} className="text-brand" />
            All businesses
          </div>
          <div className="text-xs font-semibold text-muted">Scan status, website, plan, visibility, and category before editing.</div>
        </div>
        {tenants.map((tenant) => (
          <article key={tenant.id} className="rounded-xl border border-line bg-white p-5 shadow-card">
            <div className="grid gap-4 xl:grid-cols-[1.6fr_repeat(4,minmax(0,1fr))]">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <div className="text-base font-bold text-ink">{tenant.name}</div>
                  <StatusBadge value={tenant.status} />
                  <StatusBadge value={tenant.websiteStatus} website />
                </div>
                <div className="mt-1 text-sm text-muted">{tenant.slug}</div>
                <div className="mt-2 text-sm text-muted">Owner: {tenant.owner?.fullName || "Unknown"}</div>
                <div className="mt-1 text-sm text-muted">Modules enabled: {tenant.enabledModuleCount || 0}</div>
                {tenant.slug ? (
                  <Link className="mt-3 inline-flex items-center gap-1 text-sm font-bold text-brand hover:underline" to={`/businesses/${tenant.slug}`}>
                    Preview public website
                    <ExternalLink size={13} />
                  </Link>
                ) : null}
                {tenant.pendingUpgradeCount ? (
                  <div className="mt-2 inline-flex rounded-full bg-amber-50 px-2 py-1 text-xs font-semibold text-amber-700 ring-1 ring-amber-200">
                    {tenant.pendingUpgradeCount} upgrade request pending
                  </div>
                ) : null}
              </div>
              <Field label="Tenant status">
                <select className="form-input" value={tenant.status || "draft"} disabled={busyTenant === tenant.id} onChange={(event) => saveTenant(tenant, { status: event.target.value })}>
                  <option value="draft">draft</option>
                  <option value="active">active</option>
                  <option value="archived">archived</option>
                </select>
              </Field>
              <Field label="Website status">
                <select
                  className="form-input"
                  value={tenant.websiteStatus || "not_generated"}
                  disabled={busyTenant === tenant.id}
                  onChange={(event) => saveTenant(tenant, { websiteStatus: event.target.value })}
                >
                  <option value="not_generated">not_generated</option>
                  <option value="pending_review">pending_review</option>
                  <option value="published">published</option>
                  <option value="unpublished">unpublished</option>
                  <option value="rejected">rejected</option>
                </select>
              </Field>
              <Field label="Plan">
                <select
                  className="form-input"
                  value={tenant.settings?.planCode || "starter"}
                  disabled={busyTenant === tenant.id}
                  onChange={(event) =>
                    saveTenant(tenant, {
                      settings: {
                        ...(tenant.settings || {}),
                        planCode: event.target.value,
                      },
                    })
                  }
                >
                  <option value="starter">Basic</option>
                  <option value="growth">AI Ordering</option>
                  <option value="scale">Full Agent</option>
                </select>
              </Field>
              <Field label="Public visibility">
                <select
                  className="form-input"
                  value={String(tenant.settings?.publicVisibility ?? true)}
                  disabled={busyTenant === tenant.id}
                  onChange={(event) =>
                    saveTenant(tenant, {
                      settings: {
                        ...(tenant.settings || {}),
                        publicVisibility: event.target.value === "true",
                      },
                    })
                  }
                >
                  <option value="true">true</option>
                  <option value="false">false</option>
                </select>
              </Field>
              <Field label="Category">
                <select
                  className="form-input"
                  value={tenant.businessCategoryId || ""}
                  disabled={busyTenant === tenant.id}
                  onChange={(event) => saveTenant(tenant, { businessCategoryId: event.target.value || null })}
                >
                  <option value="">None</option>
                  {categories.map((category) => (
                    <option key={category.id} value={category.id}>
                      {category.name}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
            {tenant.upgradeRequests?.length ? (
              <div className="mt-4 rounded-xl border border-line bg-surface p-4">
                <div className="text-sm font-semibold text-ink">Package request history</div>
                <div className="mt-3 grid gap-3 lg:grid-cols-2">
                  {tenant.upgradeRequests.map((request) => (
                    <div key={`${tenant.id}-${request.planCode}-${request.requestedAt || request.status}`} className="rounded-xl border border-line bg-white p-3 text-sm">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="font-semibold text-ink">{request.profileName || request.planName}</div>
                          <div className="mt-1 text-xs text-muted">Requested: {request.requestedAt ? new Date(request.requestedAt).toLocaleString() : "Unknown"}</div>
                          {request.decisionNote ? <div className="mt-1 text-xs text-muted">Note: {request.decisionNote}</div> : null}
                        </div>
                        <span className={request.status === "approved" ? "rounded-full bg-green-50 px-2 py-1 text-xs font-bold text-green-700" : request.status === "rejected" ? "rounded-full bg-red-50 px-2 py-1 text-xs font-bold text-red-700" : "rounded-full bg-amber-50 px-2 py-1 text-xs font-bold text-amber-700"}>
                          {request.status.replace("_", " ")}
                        </span>
                      </div>
                      {request.status === "pending_approval" ? (
                        <div className="mt-3 flex flex-wrap gap-2">
                          <button
                            type="button"
                            disabled={busyTenant === `${tenant.id}:${request.planCode}`}
                            onClick={() => decidePackageRequest(tenant, request, "approved")}
                            className="rounded-xl bg-green-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-green-700 disabled:opacity-50"
                          >
                            Approve
                          </button>
                          <button
                            type="button"
                            disabled={busyTenant === `${tenant.id}:${request.planCode}`}
                            onClick={() => decidePackageRequest(tenant, request, "rejected")}
                            className="rounded-xl border border-red-200 px-3 py-1.5 text-xs font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50"
                          >
                            Reject
                          </button>
                        </div>
                      ) : null}
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </article>
        ))}
        {!tenants.length && !isLoading ? <div className="rounded-xl border border-dashed border-line bg-surface p-6 text-sm text-muted">No tenants found.</div> : null}
      </div>
    </section>
  );
}

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-ink">{label}</span>
      {children}
    </label>
  );
}

function MiniStat({ label, value, tone = "brand" }) {
  const toneClass =
    tone === "amber"
      ? "bg-amber-50 text-amber-800 border-amber-200"
      : tone === "green"
        ? "bg-green-50 text-green-800 border-green-200"
        : "bg-white text-ink border-line";
  return (
    <div className={`rounded-xl border px-4 py-3 ${toneClass}`}>
      <div className="text-xs font-bold uppercase tracking-[0.12em] opacity-70">{label}</div>
      <div className="mt-1 text-2xl font-black">{value}</div>
    </div>
  );
}

function StatusBadge({ value, website = false }) {
  const normalized = String(value || "unknown");
  const green = ["active", "published", "approved"].includes(normalized);
  const amber = ["draft", "pending_review", "pending"].includes(normalized);
  const red = ["archived", "rejected", "suspended"].includes(normalized);
  const className = green
    ? "bg-green-50 text-green-700"
    : amber
      ? "bg-amber-50 text-amber-700"
      : red
        ? "bg-red-50 text-red-700"
        : "bg-surface text-muted";
  return (
    <span className={`rounded-full px-2 py-1 text-[11px] font-bold capitalize ${className}`}>
      {website ? "site: " : ""}
      {normalized.replaceAll("_", " ")}
    </span>
  );
}
