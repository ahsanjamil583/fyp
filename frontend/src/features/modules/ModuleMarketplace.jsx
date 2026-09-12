import { Check, Puzzle, Sparkles, TrendingUp } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Alert, Badge, Card, EmptyState, IconTile, PageHeader } from "../../components/ui/index.jsx";
import { humanizeModuleCode, moduleMeta } from "../../utils/moduleMeta.js";

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
      <EmptyState
        icon={Puzzle}
        title="No business yet"
        description="Create a business profile first. Modules attach to a business, so there is nothing to enable until one exists."
        actionLabel="Create Business"
        actionTo="/dashboard/business"
      />
    );
  }

  return (
    <section className="space-y-6">
      <PageHeader
        icon={Puzzle}
        eyebrow="Module Registry"
        title={`Modules for ${selectedTenant.name}`}
        description="All BizXusAI modules are available freely for this business. Enable the tools you want to use."
      />

      {availablePlans.length ? (
        <div className="grid gap-4 lg:grid-cols-3">
          {availablePlans.map((plan) => {
            const active = tenantPlan?.code === plan.code;
            return (
              <Card
                as="article"
                key={plan.code}
                className={active ? "relative ring-2 ring-brand" : "transition hover:shadow-lift"}
              >
                {active ? (
                  <span className="absolute -top-2.5 left-5 rounded-full bg-sidebar-active px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white shadow-nav-active">
                    Current plan
                  </span>
                ) : null}
                <div className="flex items-start justify-between gap-3">
                  <div className="text-lg font-bold text-ink">{plan.name}</div>
                  <Badge tone="green">{plan.priceLabel || "Free"}</Badge>
                </div>
                <p className="mt-2 text-sm leading-6 text-muted">{plan.description}</p>
                {active ? (
                  <div className="mt-4 flex items-center gap-2 rounded-xl bg-brand-100 px-3 py-2 text-sm font-bold text-brand">
                    <Check size={16} strokeWidth={3} />
                    You are on this plan
                  </div>
                ) : null}
              </Card>
            );
          })}
        </div>
      ) : null}

      {selectedCategory ? (
        <Card className="border-brand-200 bg-surface-purple">
          <div className="flex items-center gap-2 text-sm font-bold text-ink">
            <Sparkles size={16} className="text-brand" />
            Suggested for {selectedCategory.name}
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {selectedCategory.suggestedModules.map((moduleCode) => {
              const meta = moduleMeta(moduleCode);
              return (
                <span
                  key={moduleCode}
                  className="inline-flex items-center gap-1.5 rounded-full border border-line bg-white px-3 py-1.5 text-xs font-bold text-ink shadow-card"
                >
                  <meta.icon size={13} className="text-brand" strokeWidth={2.3} />
                  {meta.label}
                </span>
              );
            })}
          </div>
          {selectedCategory.analyticsSuggestions?.length ? (
            <div className="mt-5">
              <div className="flex items-center gap-2 text-sm font-bold text-ink">
                <TrendingUp size={16} className="text-brand" />
                Recommended analytics focus
              </div>
              <ul className="mt-2 space-y-1.5">
                {selectedCategory.analyticsSuggestions.map((item) => (
                  <li key={item} className="flex items-start gap-2 text-sm leading-6 text-muted">
                    <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-brand" />
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </Card>
      ) : null}

      <Alert tone="green">{serverMessage}</Alert>
      <Alert tone="red">{serverError}</Alert>

      {isLoadingModules ? <div className="text-sm text-muted">Loading modules...</div> : null}

      <div className="grid gap-4 lg:grid-cols-2">
        {tenantModules.map((module) => {
          const suggested = selectedCategory?.suggestedModules.includes(module.code);
          const enabled = module.tenantStatus === "enabled";
          const meta = moduleMeta(module.code);
          return (
            <Card
              as="article"
              key={module.code}
              className={`flex flex-col transition ${
                enabled ? "ring-1 ring-brand-200" : ""
              } hover:shadow-lift`}
            >
              <div className="flex items-start gap-4">
                <IconTile icon={meta.icon} tone={meta.tone} size={46} />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-base font-bold text-ink">{module.name}</h2>
                    {enabled ? <Badge tone="green" icon={Check}>Enabled</Badge> : null}
                    {suggested && !enabled ? <Badge tone="purple" icon={Sparkles}>Suggested</Badge> : null}
                  </div>
                  <p className="mt-1.5 text-sm leading-6 text-muted">{module.description}</p>
                </div>
              </div>

              <dl className="mt-4 space-y-1.5 border-t border-line-soft pt-3 text-xs">
                <div className="flex gap-2">
                  <dt className="w-32 shrink-0 font-semibold text-subtle">Category</dt>
                  <dd className="font-medium text-muted">{humanizeModuleCode(module.category)}</dd>
                </div>
                <div className="flex gap-2">
                  <dt className="w-32 shrink-0 font-semibold text-subtle">Access</dt>
                  <dd className="font-medium text-muted">Free for every business</dd>
                </div>
                {module.dependencies?.length ? (
                  <div className="flex gap-2">
                    <dt className="w-32 shrink-0 font-semibold text-subtle">Requires</dt>
                    <dd className="font-medium text-muted">
                      {module.dependencies.map(humanizeModuleCode).join(", ")}
                    </dd>
                  </div>
                ) : null}
                {module.blockingDependents?.length ? (
                  <div className="flex gap-2">
                    <dt className="w-32 shrink-0 font-semibold text-subtle">Required by</dt>
                    <dd className="font-medium text-muted">
                      {module.blockingDependents.map(humanizeModuleCode).join(", ")}
                    </dd>
                  </div>
                ) : null}
              </dl>

              <div className="mt-4 flex justify-end">
                <button
                  type="button"
                  className={enabled ? "ui-btn-secondary" : "ui-btn-primary"}
                  disabled={busyModule === module.code}
                  onClick={() => toggleModule(module)}
                >
                  {busyModule === module.code
                    ? "Saving..."
                    : enabled
                      ? "Disable"
                      : "Enable"}
                </button>
              </div>
            </Card>
          );
        })}
      </div>
    </section>
  );
}
