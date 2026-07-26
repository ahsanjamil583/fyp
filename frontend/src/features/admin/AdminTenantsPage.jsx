import { useEffect, useState } from "react";

import { decideAdminPackageRequest, getAdminTenants, updateAdminTenant } from "../../services/adminApi.js";
import { getAdminBusinessCategories } from "../../services/businessCategoryApi.js";

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
      setError(requestError.response?.data?.detail || "Unable to load tenants.");
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
      setError(requestError.response?.data?.detail || "Unable to update tenant.");
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
      setError(requestError.response?.data?.detail || `Unable to ${status} package request.`);
    } finally {
      setBusyTenant("");
    }
  }

  const pendingRequests = tenants.flatMap((tenant) =>
    (tenant.upgradeRequests || [])
      .filter((request) => request.status === "pending_approval")
      .map((request) => ({ tenant, request }))
  );

  return (
    <section className="space-y-6">
      <div className="border-b border-line pb-6">
        <p className="text-sm font-semibold uppercase tracking-wide text-brand">SaaS Management</p>
        <h1 className="mt-2 text-3xl font-semibold text-ink">Tenants</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-muted">
          Manage tenant status, public visibility, website publication, category assignment, and subscription plan restrictions from one place.
        </p>
      </div>

      {message ? <div className="rounded-md border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">{message}</div> : null}
      {error ? <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}
      {isLoading ? <div className="text-sm text-muted">Loading tenants...</div> : null}

      <div className="rounded-md border border-line bg-white p-5 shadow-sm">
        <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
          <div>
            <h2 className="text-lg font-semibold text-ink">Package upgrade requests</h2>
            <p className="mt-1 text-sm text-muted">Approve paid package requests only after payment confirmation or for demo/admin approval.</p>
          </div>
          <span className={pendingRequests.length ? "rounded-full bg-amber-50 px-3 py-1 text-xs font-bold text-amber-700 ring-1 ring-amber-200" : "rounded-full bg-green-50 px-3 py-1 text-xs font-bold text-green-700 ring-1 ring-green-200"}>
            {pendingRequests.length} pending
          </span>
        </div>
        <div className="mt-4 space-y-3">
          {pendingRequests.map(({ tenant, request }) => (
            <div key={`${tenant.id}-${request.planCode}`} className="rounded-md border border-amber-200 bg-amber-50 p-4">
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
                    className="rounded-md bg-green-600 px-3 py-2 text-sm font-semibold text-white hover:bg-green-700 disabled:opacity-50"
                  >
                    Approve
                  </button>
                  <button
                    type="button"
                    disabled={busyTenant === `${tenant.id}:${request.planCode}`}
                    onClick={() => decidePackageRequest(tenant, request, "rejected")}
                    className="rounded-md border border-red-200 bg-white px-3 py-2 text-sm font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50"
                  >
                    Reject
                  </button>
                </div>
              </div>
            </div>
          ))}
          {!pendingRequests.length && !isLoading ? <div className="rounded-md border border-dashed border-line bg-surface p-4 text-sm text-muted">No pending upgrade requests right now.</div> : null}
        </div>
      </div>

      <div className="space-y-4">
        {tenants.map((tenant) => (
          <article key={tenant.id} className="rounded-md border border-line bg-white p-5 shadow-sm">
            <div className="grid gap-4 xl:grid-cols-[1.6fr_repeat(4,minmax(0,1fr))]">
              <div>
                <div className="text-lg font-semibold text-ink">{tenant.name}</div>
                <div className="mt-1 text-sm text-muted">{tenant.slug}</div>
                <div className="mt-2 text-sm text-muted">Owner: {tenant.owner?.fullName || "Unknown"}</div>
                <div className="mt-1 text-sm text-muted">Modules enabled: {tenant.enabledModuleCount || 0}</div>
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
                  <option value="published">published</option>
                  <option value="unpublished">unpublished</option>
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
              <div className="mt-4 rounded-md border border-line bg-surface p-4">
                <div className="text-sm font-semibold text-ink">Package request history</div>
                <div className="mt-3 grid gap-3 lg:grid-cols-2">
                  {tenant.upgradeRequests.map((request) => (
                    <div key={`${tenant.id}-${request.planCode}-${request.requestedAt || request.status}`} className="rounded-md border border-line bg-white p-3 text-sm">
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
                            className="rounded-md bg-green-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-green-700 disabled:opacity-50"
                          >
                            Approve
                          </button>
                          <button
                            type="button"
                            disabled={busyTenant === `${tenant.id}:${request.planCode}`}
                            onClick={() => decidePackageRequest(tenant, request, "rejected")}
                            className="rounded-md border border-red-200 px-3 py-1.5 text-xs font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50"
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
        {!tenants.length && !isLoading ? <div className="rounded-md border border-dashed border-line bg-surface p-6 text-sm text-muted">No tenants found.</div> : null}
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
