import { joiResolver } from "@hookform/resolvers/joi";
import Joi from "joi";
import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router-dom";

import { useAuth } from "../../context/AuthContext.jsx";
import { useTenant } from "../../context/TenantContext.jsx";
import { getPublicBusinessCategories } from "../../services/businessCategoryApi.js";
import { createTenant, publishTenant, unpublishTenant, updateTenant } from "../../services/tenantApi.js";
import { languageModeOptions, pakistanProvinces } from "../../utils/localization.js";

const schema = Joi.object({
  name: Joi.string().min(2).required().label("Business name"),
  businessCategoryId: Joi.string().required().label("Business category"),
  description: Joi.string().allow("").optional(),
  phone: Joi.string().allow("").optional(),
  whatsapp: Joi.string().allow("").optional(),
  email: Joi.string().email({ tlds: false }).allow("").optional(),
  line1: Joi.string().allow("").optional(),
  city: Joi.string().allow("").optional(),
  province: Joi.string().allow("").optional(),
  languageMode: Joi.string().valid("mixed", "roman_urdu", "english").required(),
});

const steps = [
  { id: 1, label: "Identity" },
  { id: 2, label: "Contact" },
  { id: 3, label: "Review" },
];

const stepFields = {
  1: ["name", "businessCategoryId", "description"],
  2: ["phone", "whatsapp", "email", "line1", "city", "province", "languageMode"],
};

export function BusinessProfile() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { selectedTenant, refreshTenants, selectTenant } = useTenant();
  const [categories, setCategories] = useState([]);
  const [serverMessage, setServerMessage] = useState("");
  const [serverError, setServerError] = useState("");
  const [currentStep, setCurrentStep] = useState(1);

  const form = useForm({
    resolver: joiResolver(schema),
    defaultValues: {
      name: "",
      businessCategoryId: "",
      description: "",
      phone: "",
      whatsapp: "",
      email: "",
      line1: "",
      city: "",
      province: "",
      languageMode: "mixed",
    },
  });

  const stepStorageKey = useMemo(
    () => `bizxus_phase3_step_${selectedTenant?.id || user?.id || "new"}`,
    [selectedTenant?.id, user?.id],
  );

  useEffect(() => {
    getPublicBusinessCategories().then(setCategories).catch(() => setCategories([]));
  }, []);

  useEffect(() => {
    if (selectedTenant) {
      form.reset({
        name: selectedTenant.name || "",
        businessCategoryId: selectedTenant.businessCategoryId || "",
        description: selectedTenant.description || "",
        phone: selectedTenant.contact?.phone || "",
        whatsapp: selectedTenant.contact?.whatsapp || "",
        email: selectedTenant.contact?.email || "",
        line1: selectedTenant.address?.line1 || "",
        city: selectedTenant.address?.city || "",
        province: selectedTenant.address?.province || "",
        languageMode: selectedTenant.settings?.languageMode || "mixed",
      });
      const savedStep = Number(selectedTenant.settings?.onboarding?.phase3?.currentStep || localStorage.getItem(stepStorageKey) || 1);
      setCurrentStep(Math.min(3, Math.max(1, savedStep)));
      return;
    }

    form.reset({
      name: "",
      businessCategoryId: "",
      description: "",
      phone: user?.phone || "",
      whatsapp: "",
      email: user?.email || "",
      line1: "",
      city: "",
      province: "",
      languageMode: "mixed",
    });
    const savedStep = Number(localStorage.getItem(stepStorageKey) || 1);
    setCurrentStep(Math.min(3, Math.max(1, savedStep)));
  }, [form, selectedTenant, stepStorageKey, user?.email, user?.phone]);

  useEffect(() => {
    localStorage.setItem(stepStorageKey, String(currentStep));
  }, [currentStep, stepStorageKey]);

  const watchedValues = form.watch();

  const selectedCategory = useMemo(
    () => categories.find((category) => category.id === watchedValues.businessCategoryId),
    [categories, watchedValues.businessCategoryId],
  );

  const onboardingChecks = useMemo(
    () => [
      { label: "Business name added", done: Boolean(watchedValues.name?.trim()) },
      { label: "Category selected", done: Boolean(watchedValues.businessCategoryId) },
      { label: "Contact channel added", done: Boolean(watchedValues.phone?.trim() || watchedValues.email?.trim()) },
      { label: "Location added", done: Boolean(watchedValues.city?.trim() && watchedValues.province?.trim()) },
      { label: "Language preference selected", done: Boolean(watchedValues.languageMode?.trim()) },
      { label: "Business description written", done: Boolean(watchedValues.description?.trim()) },
    ],
    [watchedValues],
  );
  const completedChecks = onboardingChecks.filter((item) => item.done).length;
  const completionPercent = Math.round((completedChecks / onboardingChecks.length) * 100);
  const isPhase3Complete = completedChecks === onboardingChecks.length;

  function buildOnboardingSettings(stepOverride = currentStep) {
    return {
      ...(selectedTenant?.settings || {}),
      onboarding: {
        ...((selectedTenant?.settings?.onboarding || {})),
        phase3: {
          ...((selectedTenant?.settings?.onboarding?.phase3 || {})),
          currentStep: stepOverride,
          completedSteps: completedChecks,
          totalSteps: onboardingChecks.length,
          isComplete: isPhase3Complete,
          completedAt:
            isPhase3Complete
              ? selectedTenant?.settings?.onboarding?.phase3?.completedAt || new Date().toISOString()
              : null,
        },
      },
    };
  }

  async function saveBusiness(values, stepOverride = currentStep) {
    const payload = {
      name: values.name,
      businessCategoryId: values.businessCategoryId || null,
      description: values.description || "",
      contact: { phone: values.phone || "", email: values.email || "", whatsapp: values.whatsapp || "" },
      address: { line1: values.line1 || "", city: values.city || "", province: values.province || "", country: "Pakistan" },
      settings: { ...buildOnboardingSettings(stepOverride), languageMode: values.languageMode || "mixed" },
    };

    const saved = selectedTenant ? await updateTenant(selectedTenant.id, payload) : await createTenant(payload);
    await refreshTenants();
    selectTenant(saved);
    return saved;
  }

  async function submit(values) {
    setServerError("");
    setServerMessage("");
    try {
      const saved = await saveBusiness(values, 3);
      localStorage.removeItem(stepStorageKey);
      setCurrentStep(3);
      setServerMessage(selectedTenant ? "Business profile updated and onboarding completed." : "Business created. Onboarding completed.");
      selectTenant(saved);
    } catch (error) {
      setServerError(error.response?.data?.detail || "Unable to save business profile.");
    }
  }

  async function handleNextStep() {
    setServerError("");
    setServerMessage("");
    const fields = stepFields[currentStep] || [];
    const valid = await form.trigger(fields);
    if (!valid) {
      return;
    }

    if (selectedTenant || currentStep === 1) {
      try {
        const saved = await saveBusiness(form.getValues(), Math.min(3, currentStep + 1));
        if (!selectedTenant) {
          selectTenant(saved);
        }
        setServerMessage("Step progress saved.");
      } catch (error) {
        setServerError(error.response?.data?.detail || "Unable to save onboarding progress.");
        return;
      }
    }

    setCurrentStep((step) => Math.min(3, step + 1));
  }

  function handlePreviousStep() {
    setServerError("");
    setServerMessage("");
    setCurrentStep((step) => Math.max(1, step - 1));
  }

  async function togglePublish() {
    if (!selectedTenant) return;
    const saved =
      selectedTenant.websiteStatus === "published"
        ? await unpublishTenant(selectedTenant.id)
        : await publishTenant(selectedTenant.id);
    await refreshTenants();
    selectTenant(saved);
  }

  return (
    <section className="space-y-6">
      <div className="flex flex-col gap-4 border-b border-line pb-6 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-brand">Business Foundation</p>
          <h1 className="mt-2 text-3xl font-semibold text-ink">{selectedTenant ? "Business Onboarding" : "Create Your First Business"}</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-muted">
            Finish the setup step by step. Once the foundation is complete, you can enable modules, add items or services, and publish the website.
          </p>
        </div>
        {selectedTenant ? (
          <button className="rounded-md border border-line px-4 py-2 text-sm font-semibold text-ink hover:bg-surface" onClick={togglePublish}>
            {selectedTenant.websiteStatus === "published" ? "Unpublish" : "Publish"}
          </button>
        ) : null}
      </div>

      {serverMessage ? <div className="rounded-md border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">{serverMessage}</div> : null}
      {serverError ? <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{serverError}</div> : null}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
        <form className="space-y-6" onSubmit={form.handleSubmit(submit)}>
          <div className="rounded-md border border-line bg-white p-5 shadow-sm">
            <div className="flex flex-wrap gap-3 border-b border-line pb-4">
              {steps.map((step) => (
                <button
                  key={step.id}
                  type="button"
                  onClick={() => setCurrentStep(step.id)}
                  className={currentStep === step.id ? "rounded-md bg-brand px-3 py-2 text-sm font-semibold text-white" : "rounded-md border border-line px-3 py-2 text-sm font-semibold text-ink hover:bg-surface"}
                >
                  Step {step.id}: {step.label}
                </button>
              ))}
            </div>

            {currentStep === 1 ? (
              <div className="mt-4 space-y-4">
                <div>
                  <div className="text-sm font-semibold uppercase tracking-wide text-brand">Step 1</div>
                  <h2 className="mt-2 text-xl font-semibold text-ink">Business identity</h2>
                  <p className="mt-2 text-sm leading-6 text-muted">
                    Define the name, category, and short description that will shape this workspace.
                  </p>
                </div>
                <div className="grid gap-4 lg:grid-cols-2">
                  <Field label="Business name" error={form.formState.errors.name?.message}>
                    <input className="form-input" {...form.register("name")} placeholder="Burger House" />
                  </Field>
                  <Field label="Business category" error={form.formState.errors.businessCategoryId?.message}>
                    <select className="form-input" {...form.register("businessCategoryId")}>
                      <option value="">Select category</option>
                      {categories.map((category) => (
                        <option key={category.id} value={category.id}>
                          {category.name}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <label className="lg:col-span-2">
                    <span className="mb-1.5 block text-sm font-medium text-ink">Description</span>
                    <textarea className="form-input min-h-28" {...form.register("description")} placeholder="Short business description" />
                  </label>
                </div>
                {selectedCategory ? (
                  <div className="rounded-md border border-line bg-surface p-4">
                    <div className="text-sm font-semibold text-ink">Suggested modules</div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {selectedCategory.suggestedModules.map((module) => (
                        <span key={module} className="rounded-md bg-white px-2.5 py-1 text-xs font-medium text-muted">
                          {module}
                        </span>
                      ))}
                    </div>
                    {selectedCategory.websiteHints ? (
                      <div className="mt-4 grid gap-3 md:grid-cols-2">
                        <HintBlock label="Recommended template" value={selectedCategory.websiteHints.recommendedTemplate || "default"} />
                        <HintBlock label="Suggested primary color" value={selectedCategory.websiteHints.recommendedPrimaryColor || "#2563EB"} />
                      </div>
                    ) : null}
                    {selectedCategory.templateRules ? (
                      <div className="mt-4">
                        <div className="text-sm font-semibold text-ink">Template rules</div>
                        <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted">
                          <span className="rounded-md bg-white px-2.5 py-1">Preset: {selectedCategory.templateRules.recommendedVisualPreset || "auto"}</span>
                          <span className="rounded-md bg-white px-2.5 py-1">Hero style: {selectedCategory.templateRules.heroStyle || "general-purpose"}</span>
                        </div>
                        <div className="mt-2 text-xs text-muted">
                          Preferred sections: {(selectedCategory.templateRules.sectionPriority || []).join(", ") || "standard"}
                        </div>
                      </div>
                    ) : null}
                    {selectedCategory.fulfillmentHints ? (
                      <div className="mt-4">
                        <div className="text-sm font-semibold text-ink">Fulfillment hints</div>
                        <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted">
                          <span className="rounded-md bg-white px-2.5 py-1">Default: {selectedCategory.fulfillmentHints.defaultMode || "none"}</span>
                          <span className="rounded-md bg-white px-2.5 py-1">Delivery: {selectedCategory.fulfillmentHints.supportsDelivery ? "Yes" : "No"}</span>
                          <span className="rounded-md bg-white px-2.5 py-1">Pickup: {selectedCategory.fulfillmentHints.supportsPickup ? "Yes" : "No"}</span>
                          <span className="rounded-md bg-white px-2.5 py-1">In-person: {selectedCategory.fulfillmentHints.supportsInPerson ? "Yes" : "No"}</span>
                        </div>
                      </div>
                    ) : null}
                    {selectedCategory.analyticsConfig?.suggestions?.length ? (
                      <div className="mt-4">
                        <div className="text-sm font-semibold text-ink">Analytics focus</div>
                        <div className="mt-2 space-y-1 text-sm text-muted">
                          {selectedCategory.analyticsConfig.suggestions.map((item) => (
                            <div key={item}>- {item}</div>
                          ))}
                        </div>
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>
            ) : null}

            {currentStep === 2 ? (
              <div className="mt-4 space-y-4">
                <div>
                  <div className="text-sm font-semibold uppercase tracking-wide text-brand">Step 2</div>
                  <h2 className="mt-2 text-xl font-semibold text-ink">Contact, location, and language</h2>
                  <p className="mt-2 text-sm leading-6 text-muted">
                    Add the contact details, Pakistan location, and preferred customer-facing language for this business.
                  </p>
                </div>
                <div className="grid gap-4 lg:grid-cols-2">
                  <Field label="Contact phone">
                    <input className="form-input" {...form.register("phone")} placeholder="03001234567" />
                  </Field>
                  <Field label="WhatsApp">
                    <input className="form-input" {...form.register("whatsapp")} placeholder="03001234567" />
                  </Field>
                  <Field label="Contact email" error={form.formState.errors.email?.message}>
                    <input className="form-input" {...form.register("email")} placeholder="business@company.pk" />
                  </Field>
                  <Field label="Address line 1">
                    <input className="form-input" {...form.register("line1")} placeholder="Main Bazaar Road, G-10 Markaz" />
                  </Field>
                  <Field label="City">
                    <input className="form-input" {...form.register("city")} placeholder="Islamabad" />
                  </Field>
                  <Field label="Province / Territory">
                    <select className="form-input" {...form.register("province")}>
                      <option value="">Select province or territory</option>
                      {pakistanProvinces.map((province) => (
                        <option key={province} value={province}>
                          {province}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <Field label="Preferred language" error={form.formState.errors.languageMode?.message}>
                    <select className="form-input" {...form.register("languageMode")}>
                      {languageModeOptions.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </Field>
                </div>
              </div>
            ) : null}

            {currentStep === 3 ? (
              <div className="mt-4 space-y-5">
                <div>
                  <div className="text-sm font-semibold uppercase tracking-wide text-brand">Step 3</div>
                  <h2 className="mt-2 text-xl font-semibold text-ink">Review and finish</h2>
                  <p className="mt-2 text-sm leading-6 text-muted">
                    Review the setup summary, save the business foundation, and continue into modules or website setup.
                  </p>
                </div>
                <div className="grid gap-4 lg:grid-cols-2">
                  <SummaryCard label="Business name" value={watchedValues.name || "Not added"} />
                  <SummaryCard label="Category" value={selectedCategory?.name || "Not selected"} />
                  <SummaryCard label="Phone or email" value={watchedValues.phone || watchedValues.email || "Not added"} />
                  <SummaryCard label="Location" value={[watchedValues.city, watchedValues.province].filter(Boolean).join(", ") || "Not added"} />
                  <SummaryCard label="Language mode" value={languageModeOptions.find((option) => option.value === watchedValues.languageMode)?.label || "Mixed"} />
                </div>
                <div className="rounded-md border border-line bg-surface p-4 text-sm text-muted">
                  After saving, continue with modules, items/services, and website settings. Publishing will still require the website builder and at least one public item when the items module is enabled.
                </div>
              </div>
            ) : null}

            <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4">
              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={handlePreviousStep}
                  disabled={currentStep === 1}
                  className="rounded-md border border-line px-4 py-2 text-sm font-semibold text-ink hover:bg-surface disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Back
                </button>
                {currentStep < 3 ? (
                  <button
                    type="button"
                    onClick={handleNextStep}
                    className="rounded-md bg-ink px-4 py-2 text-sm font-semibold text-white hover:opacity-90"
                  >
                    Next Step
                  </button>
                ) : (
                  <button className="rounded-md bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700" disabled={form.formState.isSubmitting}>
                    {form.formState.isSubmitting ? "Saving..." : selectedTenant ? "Save and Complete Setup" : "Create Business and Continue"}
                  </button>
                )}
              </div>

              {selectedTenant && currentStep === 3 ? (
                <div className="flex flex-wrap gap-3">
                  <Link className="rounded-md border border-line px-4 py-2 text-sm font-semibold text-ink hover:bg-surface" to="/dashboard/modules">
                    Configure Modules
                  </Link>
                  <Link className="rounded-md border border-line px-4 py-2 text-sm font-semibold text-ink hover:bg-surface" to="/dashboard/public-website">
                    Website Settings
                  </Link>
                </div>
              ) : null}
            </div>
          </div>
        </form>

        <div className="space-y-4">
          <div className="rounded-md border border-line bg-white p-5 shadow-sm">
            <div className="text-sm font-semibold uppercase tracking-wide text-brand">Setup Progress</div>
            <h2 className="mt-2 text-xl font-semibold text-ink">{completionPercent}% complete</h2>
            <div className="mt-4 h-2 overflow-hidden rounded-full bg-surface">
              <div className="h-full rounded-full bg-brand transition-all" style={{ width: `${completionPercent}%` }} />
            </div>
            <div className="mt-4 space-y-3">
              {onboardingChecks.map((item) => (
                <div key={item.label} className="flex items-center justify-between gap-3 rounded-md border border-line px-3 py-2 text-sm">
                  <span className="text-ink">{item.label}</span>
                  <span className={item.done ? "font-semibold text-green-700" : "text-muted"}>{item.done ? "Done" : "Pending"}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-md border border-line bg-white p-5 shadow-sm">
            <div className="text-sm font-semibold uppercase tracking-wide text-brand">Workspace Status</div>
            <div className="mt-4 space-y-3 text-sm">
              <StatusRow label="Business record" value={selectedTenant ? "Created" : "Not created"} />
              <StatusRow label="Visibility" value={selectedTenant?.settings?.publicVisibility ? "Public-ready" : "Private"} />
              <StatusRow label="Website" value={selectedTenant?.websiteStatus || "not_generated"} />
              <StatusRow label="Business state" value={selectedTenant?.status || "draft"} />
            </div>
          </div>

          <div className="rounded-md border border-line bg-white p-5 shadow-sm">
            <div className="text-sm font-semibold uppercase tracking-wide text-brand">Next Best Actions</div>
            <div className="mt-4 space-y-3 text-sm text-muted">
              <p>1. Complete the business identity and contact setup.</p>
              <p>2. Enable the modules this business needs.</p>
              <p>3. Add items or services before publishing the public site.</p>
              <p>4. Configure the website and publish when the setup is ready.</p>
            </div>
            {selectedTenant ? (
              <button
                type="button"
                onClick={() => navigate("/dashboard/modules")}
                className="mt-4 w-full rounded-md border border-line px-4 py-2 text-sm font-semibold text-ink hover:bg-surface"
              >
                Continue to Modules
              </button>
            ) : null}
          </div>
        </div>
      </div>
    </section>
  );
}

function Field({ label, error, children }) {
  return (
    <label>
      <span className="mb-1.5 block text-sm font-medium text-ink">{label}</span>
      {children}
      {error ? <span className="mt-1 block text-xs text-red-600">{error}</span> : null}
    </label>
  );
}

function StatusRow({ label, value }) {
  return (
    <div className="flex items-center justify-between border-b border-line pb-3 last:border-b-0 last:pb-0">
      <span className="text-muted">{label}</span>
      <span className="font-semibold capitalize text-ink">{String(value).replaceAll("_", " ")}</span>
    </div>
  );
}

function SummaryCard({ label, value }) {
  return (
    <div className="rounded-md border border-line bg-white p-4">
      <div className="text-sm text-muted">{label}</div>
      <div className="mt-2 font-semibold text-ink">{value}</div>
    </div>
  );
}

function HintBlock({ label, value }) {
  return (
    <div className="rounded-md bg-white p-3">
      <div className="text-xs uppercase tracking-wide text-muted">{label}</div>
      <div className="mt-1 font-semibold text-ink">{value}</div>
    </div>
  );
}
