import { useEffect, useState } from "react";

import { createAdminModule, getAdminModules, updateAdminModule } from "../../services/moduleApi.js";
import { SectionTitle } from "../../components/ui/SectionTitle.jsx";

const emptyModule = {
  code: "",
  name: "",
  description: "",
  category: "core",
  isActive: true,
  dependenciesText: "",
  permissionsText: "",
  frontendRoutesText: "",
  apiPrefix: "",
  aiToolsText: "",
  configSchemaText: "{}",
  availabilityText: "{\"includedPlans\": [\"starter\", \"growth\", \"scale\"]}",
  usageLimitsText: "{}",
};

function planLabel(planCode) {
  return { starter: "Basic", growth: "AI Ordering", scale: "Full Agent" }[planCode] || "Basic";
}

function planListLabel(planCodes = []) {
  return planCodes.map(planLabel).join(", ");
}

export function AdminModulesPage() {
  const [modules, setModules] = useState([]);
  const [formValues, setFormValues] = useState(emptyModule);
  const [editingCode, setEditingCode] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    refreshModules();
  }, []);

  async function refreshModules() {
    setIsLoading(true);
    try {
      const data = await getAdminModules();
      setModules(data);
      setError("");
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to load modules.");
    } finally {
      setIsLoading(false);
    }
  }

  function parseCsv(text) {
    return text
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean);
  }

  function parseJson(text, label) {
    try {
      return JSON.parse(text);
    } catch {
      throw new Error(`${label} must be valid JSON.`);
    }
  }

  function buildPayload(values, includeCode) {
    return {
      ...(includeCode ? { code: values.code } : {}),
      name: values.name,
      description: values.description,
      category: values.category,
      isActive: values.isActive,
      dependencies: parseCsv(values.dependenciesText),
      permissions: parseCsv(values.permissionsText),
      frontendRoutes: parseCsv(values.frontendRoutesText),
      apiPrefix: values.apiPrefix,
      aiTools: parseCsv(values.aiToolsText),
      configSchema: parseJson(values.configSchemaText, "Config schema"),
      availability: parseJson(values.availabilityText, "Availability"),
      usageLimits: parseJson(values.usageLimitsText, "Usage limits"),
    };
  }

  function loadForEdit(module) {
    setEditingCode(module.code);
    setFormValues({
      code: module.code || "",
      name: module.name || "",
      description: module.description || "",
      category: module.category || "core",
      isActive: Boolean(module.isActive),
      dependenciesText: (module.dependencies || []).join(", "),
      permissionsText: (module.permissions || []).join(", "),
      frontendRoutesText: (module.frontendRoutes || []).join(", "),
      apiPrefix: module.apiPrefix || "",
      aiToolsText: (module.aiTools || []).join(", "),
      configSchemaText: JSON.stringify(module.configSchema || {}, null, 2),
      availabilityText: JSON.stringify(module.availability || {}, null, 2),
      usageLimitsText: JSON.stringify(module.usageLimits || {}, null, 2),
    });
  }

  function resetForm() {
    setEditingCode("");
    setFormValues(emptyModule);
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setIsSaving(true);
    setError("");
    setMessage("");
    try {
      if (editingCode) {
        await updateAdminModule(editingCode, buildPayload(formValues, false));
        setMessage("Module updated.");
      } else {
        await createAdminModule(buildPayload(formValues, true));
        setMessage("Module created.");
      }
      resetForm();
      await refreshModules();
    } catch (requestError) {
      setError(requestError.message || requestError.response?.data?.detail || "Unable to save module.");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <section className="space-y-6">
      <div className="border-b border-line-soft pb-5">
        <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-brand">Capability Catalog</p>
        <h1 className="mt-1.5 text-2xl font-extrabold tracking-tight text-ink">Modules</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-muted">
          Manage the platform-wide module catalog, plan availability, dependencies, and usage-limit definitions that power tenant restrictions.
        </p>
      </div>

      {message ? <div className="rounded-xl border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">{message}</div> : null}
      {error ? <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 whitespace-pre-wrap">{error}</div> : null}

      <div className="grid gap-6 xl:grid-cols-[460px_1fr]">
        <form className="space-y-4 rounded-xl border border-line bg-white p-5 shadow-card" onSubmit={handleSubmit}>
          <SectionTitle>{editingCode ? "Edit module" : "Create module"}</SectionTitle>
          <Field label="Code">
            <input className="form-input" disabled={Boolean(editingCode)} required value={formValues.code} onChange={(event) => setFormValues((current) => ({ ...current, code: event.target.value }))} />
          </Field>
          <Field label="Name">
            <input className="form-input" required value={formValues.name} onChange={(event) => setFormValues((current) => ({ ...current, name: event.target.value }))} />
          </Field>
          <Field label="Category">
            <input className="form-input" value={formValues.category} onChange={(event) => setFormValues((current) => ({ ...current, category: event.target.value }))} />
          </Field>
          <Field label="Description">
            <textarea className="form-input min-h-24" value={formValues.description} onChange={(event) => setFormValues((current) => ({ ...current, description: event.target.value }))} />
          </Field>
          <Field label="Dependencies">
            <input className="form-input" placeholder="website_builder, items" value={formValues.dependenciesText} onChange={(event) => setFormValues((current) => ({ ...current, dependenciesText: event.target.value }))} />
          </Field>
          <Field label="Permissions">
            <input className="form-input" value={formValues.permissionsText} onChange={(event) => setFormValues((current) => ({ ...current, permissionsText: event.target.value }))} />
          </Field>
          <Field label="Frontend routes">
            <input className="form-input" value={formValues.frontendRoutesText} onChange={(event) => setFormValues((current) => ({ ...current, frontendRoutesText: event.target.value }))} />
          </Field>
          <Field label="API prefix">
            <input className="form-input" value={formValues.apiPrefix} onChange={(event) => setFormValues((current) => ({ ...current, apiPrefix: event.target.value }))} />
          </Field>
          <Field label="AI tools">
            <input className="form-input" value={formValues.aiToolsText} onChange={(event) => setFormValues((current) => ({ ...current, aiToolsText: event.target.value }))} />
          </Field>
          <Field label="Config schema JSON">
            <textarea className="form-input min-h-24 font-mono text-xs" value={formValues.configSchemaText} onChange={(event) => setFormValues((current) => ({ ...current, configSchemaText: event.target.value }))} />
          </Field>
          <Field label="Availability JSON">
            <textarea className="form-input min-h-24 font-mono text-xs" value={formValues.availabilityText} onChange={(event) => setFormValues((current) => ({ ...current, availabilityText: event.target.value }))} />
          </Field>
          <Field label="Usage limits JSON">
            <textarea className="form-input min-h-28 font-mono text-xs" value={formValues.usageLimitsText} onChange={(event) => setFormValues((current) => ({ ...current, usageLimitsText: event.target.value }))} />
          </Field>
          <label className="flex items-center gap-2 rounded-xl border border-line px-3 py-2 text-sm text-muted">
            <input type="checkbox" checked={formValues.isActive} onChange={(event) => setFormValues((current) => ({ ...current, isActive: event.target.checked }))} />
            Active module
          </label>
          <div className="flex gap-2">
            <button className="flex-1 rounded-xl bg-brand px-4 py-2 text-sm font-semibold text-white" disabled={isSaving} type="submit">
              {isSaving ? "Saving..." : editingCode ? "Update module" : "Create module"}
            </button>
            {editingCode ? (
              <button className="rounded-xl border border-line px-4 py-2 text-sm font-semibold text-ink" onClick={resetForm} type="button">
                Cancel
              </button>
            ) : null}
          </div>
        </form>

        <div className="space-y-4">
          {isLoading ? <div className="text-sm text-muted">Loading modules...</div> : null}
          {modules.map((module) => (
            <article key={module.code} className="rounded-xl border border-line bg-white p-5 shadow-card">
              <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <SectionTitle>{module.name}</SectionTitle>
                    <span className={module.isActive ? "rounded-full bg-green-100 px-2 py-1 text-xs font-semibold text-green-700" : "rounded-full bg-slate-200 px-2 py-1 text-xs font-semibold text-slate-700"}>
                      {module.isActive ? "active" : "inactive"}
                    </span>
                  </div>
                  <div className="mt-1 text-sm text-muted">{module.code} / {module.category}</div>
                  <p className="mt-3 text-sm leading-6 text-muted">{module.description || "No description."}</p>
                  <div className="mt-3 text-sm text-muted">
                    Packages: {planListLabel(module.availability?.includedPlans || []) || "Basic, AI Ordering, Full Agent"}
                  </div>
                  <div className="mt-1 text-sm text-muted">Enabled for {module.enabledTenantCount || 0} tenants</div>
                </div>
                <button className="rounded-xl border border-line px-3 py-1.5 text-sm font-semibold text-ink" onClick={() => loadForEdit(module)} type="button">
                  Edit
                </button>
              </div>
            </article>
          ))}
        </div>
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
