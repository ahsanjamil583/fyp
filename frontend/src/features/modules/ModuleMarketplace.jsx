import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { useModules } from "../../context/ModuleContext.jsx";
import { useTenant } from "../../context/TenantContext.jsx";
import { getPublicBusinessCategories } from "../../services/businessCategoryApi.js";
import { disableTenantModule, enableTenantModule } from "../../services/moduleApi.js";

export function ModuleMarketplace() {
  const { selectedTenant, refreshTenants, selectTenant } = useTenant();
  const { tenantModules, tenantPlan, availablePlans, refreshTenantModules, isLoadingModules } = useModules();
  const [categories, setCategories] = useState([]);
  const [busyModule, setBusyModule] = useState("");
  const [serverError, setServerError] = useState("");
  const [serverMessage, setServerMessage] = useState("");

  useEffect(() => {
    getPublicBusinessCategories().then(setCategories).catch(() => setCategories([]));
  }, []);

  useEffect(() => {
    if (selectedTenant?.id) {
      refreshTenantModules(selectedTenant.id);
    }
  }, [selectedTenant?.id, refreshTenantModules]);

  const selectedCategory = useMemo(
    () => categories.find((category) => category.id === selectedTenant?.businessCategoryId),
    [categories, selectedTenant],
  );

  async function toggleModule(module) {
    if (!selectedTenant) return;
    setBusyModule(module.code);
    setServerError("");
    setServerMessage("");
    try {
      const data =
        module.tenantStatus === "enabled"
          ? await disableTenantModule(selectedTenant.id, module.code)
          : await enableTenantModule(selectedTenant.id, module.code);
      const tenants = await refreshTenants();
      const updatedTenant = tenants.find((tenant) => tenant.id === selectedTenant.id) || data.tenant;
      selectTenant(updatedTenant);
      await refreshTenantModules(selectedTenant.id);
      setServerMessage(
        module.tenantStatus === "enabled"
          ? `${module.name} disabled successfully.`
          : `${module.name} enabled successfully.`,
      );
    } catch (error) {
      setServerError(error.response?.data?.detail || "Unable to update module.");
    } finally {
      setBusyModule("");
    }
  }

  if (!selectedTenant) {
    return (
      <section className="space-y-4">
        <h1 className="text-3xl font-semibold text-ink">Modules</h1>
        <p className="text-sm text-muted">Create a business before enabling modules.</p>
        <Link className="inline-flex rounded-md bg-brand px-4 py-2 text-sm font-semibold text-white" to="/dashboard/business">
          Create Business
        </Link>
      </section>
    );
  }

  return (
    <section className="space-y-6">
      <div className="border-b border-line pb-6">
        <p className="text-sm font-semibold uppercase tracking-wide text-brand">Module Registry</p>
        <h1 className="mt-2 text-3xl font-semibold text-ink">Modules for {selectedTenant.name}</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-muted">
          Modules are controlled by the active package. Basic is free; paid features unlock only after payment or admin approval.
        </p>
      </div>

      {selectedCategory ? (
        <div className="rounded-md border border-blue-100 bg-blue-50 p-4">
          <div className="text-sm font-semibold text-blue-900">Suggested for {selectedCategory.name}</div>
          <div className="mt-2 flex flex-wrap gap-2">
            {selectedCategory.suggestedModules.map((moduleCode) => (
              <span key={moduleCode} className="rounded-md bg-white px-2.5 py-1 text-xs font-medium text-blue-700">
                {moduleCode}
              </span>
            ))}
          </div>
          {selectedCategory.analyticsSuggestions?.length ? (
            <div className="mt-4">
              <div className="text-sm font-semibold text-blue-900">Recommended analytics focus</div>
              <div className="mt-2 space-y-1 text-sm text-blue-800">
                {selectedCategory.analyticsSuggestions.map((item) => (
                  <div key={item}>- {item}</div>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="rounded-md border border-line bg-white p-5 shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="text-sm font-semibold text-ink">Current package</div>
            <p className="mt-1 text-sm text-muted">
              {tenantPlan?.displayName || tenantPlan?.name || "Basic Free"} controls which modules are enabled or locked.
            </p>
          </div>
          <div className="rounded-md border border-line bg-surface px-4 py-3 text-sm">
            <div className="font-semibold text-ink">{tenantPlan?.displayName || "Basic Free"}</div>
            <div className="mt-1 text-muted">{tenantPlan?.priceLabel || "Free"} package</div>
          </div>
        </div>
        <div className="mt-4 grid gap-3 lg:grid-cols-3">
          {availablePlans.map((plan) => (
            <div
              key={plan.code}
              className={tenantPlan?.code === plan.code ? "rounded-md border border-blue-200 bg-blue-50 p-3" : "rounded-md border border-line bg-surface p-3"}
            >
              <div className="text-sm font-semibold text-ink">{plan.name}</div>
              <div className="mt-1 text-xs font-semibold uppercase tracking-wide text-brand">{plan.priceLabel}</div>
              <p className="mt-1 text-sm text-muted">{plan.description}</p>
            </div>
          ))}
        </div>
      </div>

      {serverMessage ? <div className="rounded-md border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">{serverMessage}</div> : null}
      {serverError ? <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{serverError}</div> : null}

      {isLoadingModules ? <div className="text-sm text-muted">Loading modules...</div> : null}

      <div className="grid gap-4 lg:grid-cols-2">
        {tenantModules.map((module) => {
          const suggested = selectedCategory?.suggestedModules.includes(module.code);
          const enabled = module.tenantStatus === "enabled";
          const planLocked = !module.planAccess?.isIncluded;
          const usageSummary = module.usageSummary;
          return (
            <article key={module.code} className="rounded-md border border-line bg-white p-5 shadow-sm">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-lg font-semibold text-ink">{module.name}</h2>
                    {suggested ? <span className="rounded-md bg-accent/10 px-2 py-1 text-xs font-semibold text-accent">Suggested</span> : null}
                    {planLocked ? <span className="rounded-md bg-amber-100 px-2 py-1 text-xs font-semibold text-amber-800">Locked</span> : null}
                  </div>
                  <p className="mt-2 text-sm leading-6 text-muted">{module.description}</p>
                  <div className="mt-3 text-xs uppercase tracking-wide text-muted">{module.category}</div>
                  <div className="mt-3 text-sm text-muted">
                    Packages: {module.planAccess?.includedPlanNames?.join(", ") || "Basic, AI Ordering, Full Agent"}
                  </div>
                  {module.dependencies?.length ? (
                    <div className="mt-3 text-sm text-muted">
                      Requires: {module.dependencies.join(", ")}
                    </div>
                  ) : null}
                  {module.blockingDependents?.length ? (
                    <div className="mt-2 text-sm text-muted">
                      Required by enabled modules: {module.blockingDependents.join(", ")}
                    </div>
                  ) : null}
                  {planLocked ? (
                    <div className="mt-2 text-sm text-amber-700">
                      This feature is available in the {module.planAccess?.upgradePlanName || "AI Ordering or Full Agent"} plan. Please upgrade to continue.
                    </div>
                  ) : null}
                  {usageSummary ? (
                    <div className={usageSummary.status === "limit_reached" ? "mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700" : usageSummary.status === "near_limit" ? "mt-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800" : "mt-3 rounded-md border border-line bg-surface px-3 py-2 text-sm text-muted"}>
                      {usageSummary.label}: {usageSummary.current}
                      {usageSummary.limit === null ? " / unlimited" : ` / ${usageSummary.limit}`}
                    </div>
                  ) : null}
                </div>
                <button
                  className={enabled ? "rounded-md border border-line px-4 py-2 text-sm font-semibold text-ink hover:bg-surface" : "rounded-md bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700"}
                  disabled={busyModule === module.code}
                  onClick={() => {
                    if (!enabled && planLocked) {
                      setServerError(`This feature is available in the ${module.planAccess?.upgradePlanName || "AI Ordering or Full Agent"} plan. Please upgrade to continue.`);
                      return;
                    }
                    toggleModule(module);
                  }}
                >
                  {busyModule === module.code ? "Saving..." : enabled ? "Disable" : planLocked ? "Locked" : "Enable"}
                </button>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
