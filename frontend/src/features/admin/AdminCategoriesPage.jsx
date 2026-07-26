import { useEffect, useState } from "react";

import {
  createAdminBusinessCategory,
  deleteAdminBusinessCategory,
  getAdminBusinessCategories,
  updateAdminBusinessCategory,
} from "../../services/businessCategoryApi.js";

const emptyCategory = {
  name: "",
  slug: "",
  description: "",
  icon: "",
  isActive: true,
  suggestedModulesText: "",
  aiPromptFragmentsText: "",
  analyticsSuggestionsText: "",
  defaultCustomFieldsText: "[]",
  aiHintsText: "{}",
  websiteHintsText: "{}",
  fulfillmentHintsText: "{}",
};

export function AdminCategoriesPage() {
  const [categories, setCategories] = useState([]);
  const [formValues, setFormValues] = useState(emptyCategory);
  const [editingId, setEditingId] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    refreshCategories();
  }, []);

  async function refreshCategories() {
    setIsLoading(true);
    try {
      const data = await getAdminBusinessCategories();
      setCategories(data);
      setError("");
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to load categories.");
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

  function buildPayload(values) {
    return {
      name: values.name,
      slug: values.slug || null,
      description: values.description,
      icon: values.icon,
      isActive: values.isActive,
      suggestedModules: parseCsv(values.suggestedModulesText),
      aiPromptFragments: parseCsv(values.aiPromptFragmentsText),
      analyticsSuggestions: parseCsv(values.analyticsSuggestionsText),
      defaultCustomFields: parseJson(values.defaultCustomFieldsText, "Default custom fields"),
      aiHints: parseJson(values.aiHintsText, "AI hints"),
      websiteHints: parseJson(values.websiteHintsText, "Website hints"),
      fulfillmentHints: parseJson(values.fulfillmentHintsText, "Fulfillment hints"),
    };
  }

  function loadForEdit(category) {
    setEditingId(category.id);
    setFormValues({
      name: category.name || "",
      slug: category.slug || "",
      description: category.description || "",
      icon: category.icon || "",
      isActive: Boolean(category.isActive),
      suggestedModulesText: (category.suggestedModules || []).join(", "),
      aiPromptFragmentsText: (category.aiPromptFragments || []).join(", "),
      analyticsSuggestionsText: (category.analyticsSuggestions || []).join(", "),
      defaultCustomFieldsText: JSON.stringify(category.defaultCustomFields || [], null, 2),
      aiHintsText: JSON.stringify(category.aiHints || {}, null, 2),
      websiteHintsText: JSON.stringify(category.websiteHints || {}, null, 2),
      fulfillmentHintsText: JSON.stringify(category.fulfillmentHints || {}, null, 2),
    });
  }

  function resetForm() {
    setEditingId("");
    setFormValues(emptyCategory);
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setIsSaving(true);
    setError("");
    setMessage("");
    try {
      const payload = buildPayload(formValues);
      if (editingId) {
        await updateAdminBusinessCategory(editingId, payload);
        setMessage("Business category updated.");
      } else {
        await createAdminBusinessCategory(payload);
        setMessage("Business category created.");
      }
      resetForm();
      await refreshCategories();
    } catch (requestError) {
      setError(requestError.message || requestError.response?.data?.detail || "Unable to save category.");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleDisable(categoryId) {
    setError("");
    setMessage("");
    try {
      await deleteAdminBusinessCategory(categoryId);
      setMessage("Business category disabled.");
      await refreshCategories();
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to disable category.");
    }
  }

  return (
    <section className="space-y-6">
      <div className="border-b border-line pb-6">
        <p className="text-sm font-semibold uppercase tracking-wide text-brand">Configuration</p>
        <h1 className="mt-2 text-3xl font-semibold text-ink">Business Categories</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-muted">
          Maintain the configuration-driven category catalog that powers tenant onboarding, website defaults, module suggestions, and future category rules.
        </p>
      </div>

      {message ? <div className="rounded-md border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">{message}</div> : null}
      {error ? <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 whitespace-pre-wrap">{error}</div> : null}

      <div className="grid gap-6 xl:grid-cols-[460px_1fr]">
        <form className="space-y-4 rounded-md border border-line bg-white p-5 shadow-sm" onSubmit={handleSubmit}>
          <h2 className="text-lg font-semibold text-ink">{editingId ? "Edit category" : "Create category"}</h2>
          <Field label="Name">
            <input className="form-input" value={formValues.name} onChange={(event) => setFormValues((current) => ({ ...current, name: event.target.value }))} required />
          </Field>
          <Field label="Slug">
            <input className="form-input" value={formValues.slug} onChange={(event) => setFormValues((current) => ({ ...current, slug: event.target.value }))} />
          </Field>
          <Field label="Icon">
            <input className="form-input" value={formValues.icon} onChange={(event) => setFormValues((current) => ({ ...current, icon: event.target.value }))} />
          </Field>
          <Field label="Description">
            <textarea className="form-input min-h-24" value={formValues.description} onChange={(event) => setFormValues((current) => ({ ...current, description: event.target.value }))} />
          </Field>
          <Field label="Suggested modules">
            <input className="form-input" placeholder="items, website_builder, analytics" value={formValues.suggestedModulesText} onChange={(event) => setFormValues((current) => ({ ...current, suggestedModulesText: event.target.value }))} />
          </Field>
          <Field label="AI prompt fragments">
            <input className="form-input" placeholder="Ask about freshness, Ask about delivery" value={formValues.aiPromptFragmentsText} onChange={(event) => setFormValues((current) => ({ ...current, aiPromptFragmentsText: event.target.value }))} />
          </Field>
          <Field label="Analytics suggestions">
            <input className="form-input" placeholder="Track repeat buyers, Monitor quote conversion" value={formValues.analyticsSuggestionsText} onChange={(event) => setFormValues((current) => ({ ...current, analyticsSuggestionsText: event.target.value }))} />
          </Field>
          <Field label="Default custom fields JSON">
            <textarea className="form-input min-h-28 font-mono text-xs" value={formValues.defaultCustomFieldsText} onChange={(event) => setFormValues((current) => ({ ...current, defaultCustomFieldsText: event.target.value }))} />
          </Field>
          <Field label="AI hints JSON">
            <textarea className="form-input min-h-24 font-mono text-xs" value={formValues.aiHintsText} onChange={(event) => setFormValues((current) => ({ ...current, aiHintsText: event.target.value }))} />
          </Field>
          <Field label="Website hints JSON">
            <textarea className="form-input min-h-24 font-mono text-xs" value={formValues.websiteHintsText} onChange={(event) => setFormValues((current) => ({ ...current, websiteHintsText: event.target.value }))} />
          </Field>
          <Field label="Fulfillment hints JSON">
            <textarea className="form-input min-h-24 font-mono text-xs" value={formValues.fulfillmentHintsText} onChange={(event) => setFormValues((current) => ({ ...current, fulfillmentHintsText: event.target.value }))} />
          </Field>
          <label className="flex items-center gap-2 rounded-md border border-line px-3 py-2 text-sm text-muted">
            <input type="checkbox" checked={formValues.isActive} onChange={(event) => setFormValues((current) => ({ ...current, isActive: event.target.checked }))} />
            Active category
          </label>
          <div className="flex gap-2">
            <button className="flex-1 rounded-md bg-brand px-4 py-2 text-sm font-semibold text-white" disabled={isSaving} type="submit">
              {isSaving ? "Saving..." : editingId ? "Update category" : "Create category"}
            </button>
            {editingId ? (
              <button className="rounded-md border border-line px-4 py-2 text-sm font-semibold text-ink" onClick={resetForm} type="button">
                Cancel
              </button>
            ) : null}
          </div>
        </form>

        <div className="space-y-4">
          {isLoading ? <div className="text-sm text-muted">Loading categories...</div> : null}
          {categories.map((category) => (
            <article key={category.id} className="rounded-md border border-line bg-white p-5 shadow-sm">
              <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-lg font-semibold text-ink">{category.name}</h2>
                    <span className={category.isActive ? "rounded-full bg-green-100 px-2 py-1 text-xs font-semibold text-green-700" : "rounded-full bg-slate-200 px-2 py-1 text-xs font-semibold text-slate-700"}>
                      {category.isActive ? "active" : "inactive"}
                    </span>
                  </div>
                  <div className="mt-1 text-sm text-muted">{category.slug}</div>
                  <p className="mt-3 text-sm leading-6 text-muted">{category.description || "No description."}</p>
                  <div className="mt-3 text-xs uppercase tracking-wide text-muted">
                    Suggested modules: {(category.suggestedModules || []).join(", ") || "none"}
                  </div>
                </div>
                <div className="flex gap-2">
                  <button className="rounded-md border border-line px-3 py-1.5 text-sm font-semibold text-ink" onClick={() => loadForEdit(category)} type="button">
                    Edit
                  </button>
                  <button className="rounded-md border border-line px-3 py-1.5 text-sm font-semibold text-ink" onClick={() => handleDisable(category.id)} type="button">
                    Disable
                  </button>
                </div>
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
