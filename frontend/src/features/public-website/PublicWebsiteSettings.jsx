import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { useTenant } from "../../context/TenantContext.jsx";
import { getPublicBusinessCategories } from "../../services/businessCategoryApi.js";
import { publishTenant, unpublishTenant, updateTenant } from "../../services/tenantApi.js";
import {
  buildCategoryDrivenWebsiteSettings,
  buildDefaultSections,
  getSectionLibraryItems,
  getTemplatePresetOptions,
  normalizeSections,
  WEBSITE_TEMPLATE_OPTIONS,
} from "./websiteBuilderConfig.js";

function buildEditorState(tenant) {
  const settings = buildCategoryDrivenWebsiteSettings(null, tenant?.websiteSettings || {}, tenant?.name || "");
  return {
    templateCode: settings.templateCode || "default",
    visualPreset: settings.visualPreset || getTemplatePresetOptions(settings.templateCode || "default")[0]?.value || "aurora",
    primaryColor: settings.primaryColor || "#2563EB",
    seoTitle: settings.seo?.title || "",
    seoDescription: settings.seo?.description || "",
    heroHeadline: settings.hero?.headline || "",
    heroSubheadline: settings.hero?.subheadline || "",
    heroCtaLabel: settings.hero?.ctaLabel || "Start now",
    heroSecondaryCtaLabel: settings.hero?.secondaryCtaLabel || "Browse offers",
    sections: normalizeSections(settings.sections, settings.templateCode || "default"),
    testimonials: settings.testimonials?.length ? settings.testimonials : [{ quote: "", name: "", role: "" }],
    faq: settings.faq?.length ? settings.faq : [{ question: "", answer: "" }],
  };
}

export function PublicWebsiteSettings() {
  const { selectedTenant, refreshTenants, selectTenant } = useTenant();
  const [categories, setCategories] = useState([]);
  const [form, setForm] = useState(buildEditorState(null));
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    getPublicBusinessCategories().then(setCategories).catch(() => setCategories([]));
  }, []);

  useEffect(() => {
    if (!selectedTenant) return;
    setForm(buildEditorState(selectedTenant));
  }, [selectedTenant]);

  const selectedCategory = categories.find((category) => category.id === selectedTenant?.businessCategoryId);
  const presetOptions = useMemo(() => getTemplatePresetOptions(form.templateCode), [form.templateCode]);
  const sectionLibrary = useMemo(() => getSectionLibraryItems(), []);

  function setField(key, value) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function setTemplateCode(value) {
    setForm((current) => ({
      ...current,
      templateCode: value,
      visualPreset: getTemplatePresetOptions(value)[0]?.value || current.visualPreset,
      sections: buildDefaultSections(value),
    }));
  }

  function moveSection(index, direction) {
    setForm((current) => {
      const next = [...current.sections];
      const targetIndex = index + direction;
      if (targetIndex < 0 || targetIndex >= next.length) return current;
      [next[index], next[targetIndex]] = [next[targetIndex], next[index]];
      return {
        ...current,
        sections: next.map((section, sectionIndex) => ({ ...section, order: sectionIndex + 1 })),
      };
    });
  }

  function updateSection(index, patch) {
    setForm((current) => ({
      ...current,
      sections: current.sections.map((section, sectionIndex) => (sectionIndex === index ? { ...section, ...patch } : section)),
    }));
  }

  function addSection(type) {
    setForm((current) => ({
      ...current,
      sections: [
        ...current.sections,
        {
          type,
          label: sectionLibrary.find((item) => item.type === type)?.label || type,
          visible: true,
          order: current.sections.length + 1,
          content: {},
        },
      ],
    }));
  }

  function removeSection(index) {
    setForm((current) => ({
      ...current,
      sections: current.sections.filter((_, sectionIndex) => sectionIndex !== index).map((section, sectionIndex) => ({ ...section, order: sectionIndex + 1 })),
    }));
  }

  function updateCollection(collectionKey, index, field, value) {
    setForm((current) => ({
      ...current,
      [collectionKey]: current[collectionKey].map((row, rowIndex) => (rowIndex === index ? { ...row, [field]: value } : row)),
    }));
  }

  function addCollectionRow(collectionKey, row) {
    setForm((current) => ({
      ...current,
      [collectionKey]: [...current[collectionKey], row],
    }));
  }

  function removeCollectionRow(collectionKey, index) {
    setForm((current) => ({
      ...current,
      [collectionKey]: current[collectionKey].filter((_, rowIndex) => rowIndex !== index),
    }));
  }

  function applyCategoryWebsiteHints() {
    const nextSettings = buildCategoryDrivenWebsiteSettings(selectedCategory, selectedTenant?.websiteSettings || {}, selectedTenant?.name || "");
    setForm({
      templateCode: nextSettings.templateCode,
      visualPreset: nextSettings.visualPreset,
      primaryColor: nextSettings.primaryColor,
      seoTitle: nextSettings.seo?.title || "",
      seoDescription: nextSettings.seo?.description || "",
      heroHeadline: nextSettings.hero?.headline || "",
      heroSubheadline: nextSettings.hero?.subheadline || "",
      heroCtaLabel: nextSettings.hero?.ctaLabel || "Start now",
      heroSecondaryCtaLabel: nextSettings.hero?.secondaryCtaLabel || "Browse offers",
      sections: normalizeSections(nextSettings.sections, nextSettings.templateCode),
      testimonials: nextSettings.testimonials?.length ? nextSettings.testimonials : [{ quote: "", name: "", role: "" }],
      faq: nextSettings.faq?.length ? nextSettings.faq : [{ question: "", answer: "" }],
    });
  }

  async function save(event) {
    event.preventDefault();
    if (!selectedTenant) return;
    setError("");
    setMessage("");
    try {
      const saved = await updateTenant(selectedTenant.id, {
        websiteSettings: {
          ...(selectedTenant.websiteSettings || {}),
          templateCode: form.templateCode,
          visualPreset: form.visualPreset,
          primaryColor: form.primaryColor,
          hero: {
            headline: form.heroHeadline,
            subheadline: form.heroSubheadline,
            ctaLabel: form.heroCtaLabel,
            secondaryCtaLabel: form.heroSecondaryCtaLabel,
          },
          sections: form.sections.map((section, index) => ({
            ...section,
            order: index + 1,
          })),
          testimonials: form.testimonials.filter((item) => item.quote?.trim() || item.name?.trim()),
          faq: form.faq.filter((item) => item.question?.trim() || item.answer?.trim()),
          seo: { title: form.seoTitle, description: form.seoDescription },
        },
      });
      await refreshTenants();
      selectTenant(saved);
      setMessage("Website settings saved.");
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to save website settings.");
    }
  }

  async function togglePublish() {
    if (!selectedTenant) return;
    setError("");
    setMessage("");
    try {
      const saved = selectedTenant.websiteStatus === "published"
        ? await unpublishTenant(selectedTenant.id)
        : await publishTenant(selectedTenant.id);
      await refreshTenants();
      selectTenant(saved);
      setMessage(saved.websiteStatus === "published" ? "Website published." : "Website unpublished.");
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to change publish status. Make sure Website Builder is enabled.");
    }
  }

  if (!selectedTenant) {
    return (
      <section className="space-y-4">
        <h1 className="text-3xl font-semibold text-ink">Public Website</h1>
        <p className="text-sm text-muted">Create a business before configuring a website.</p>
      </section>
    );
  }

  const previewUrl = `/businesses/${selectedTenant.slug}`;

  return (
    <section className="space-y-6">
      <div className="flex flex-col gap-3 border-b border-line pb-6 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-brand">Website Builder</p>
          <h1 className="mt-2 text-3xl font-semibold text-ink">Public Website</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-muted">
            Choose a template direction, apply a category visual preset, reorder sections, and publish a category-aware public website.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link className="rounded-md border border-line px-4 py-2 text-sm font-semibold text-ink hover:bg-surface" to={previewUrl}>
            Preview
          </Link>
          <button className="rounded-md bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700" onClick={togglePublish}>
            {selectedTenant.websiteStatus === "published" ? "Unpublish" : "Publish"}
          </button>
        </div>
      </div>

      {message ? <div className="rounded-md border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">{message}</div> : null}
      {error ? <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}

      {selectedCategory ? (
        <div className="rounded-2xl border border-blue-100 bg-blue-50 p-5">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <div className="text-sm font-semibold text-blue-900">Category website guidance for {selectedCategory.name}</div>
              <div className="mt-2 text-sm leading-6 text-blue-800">
                Recommended template: <span className="font-semibold">{selectedCategory.websiteHints?.recommendedTemplate || "default"}</span>
                {" "}with suggested primary color <span className="font-semibold">{selectedCategory.websiteHints?.recommendedPrimaryColor || "#2563EB"}</span>.
              </div>
              {selectedCategory.templateRules?.sectionPriority?.length ? (
                <div className="mt-2 text-sm leading-6 text-blue-800">
                  Preferred sections: <span className="font-semibold">{selectedCategory.templateRules.sectionPriority.join(", ")}</span>.
                </div>
              ) : null}
            </div>
            <button type="button" className="rounded-md border border-blue-200 bg-white px-4 py-2 text-sm font-semibold text-blue-900" onClick={applyCategoryWebsiteHints}>
              Apply Category Preset
            </button>
          </div>
        </div>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
        <form className="space-y-6 rounded-2xl border border-line bg-white p-5 shadow-sm" onSubmit={save}>
          <section className="space-y-4">
            <div>
              <h2 className="text-lg font-semibold text-ink">Template Direction</h2>
              <p className="mt-1 text-sm text-muted">Pick the structural style that best matches how this business sells or serves.</p>
            </div>
            <div className="grid gap-3 md:grid-cols-3">
              {WEBSITE_TEMPLATE_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => setTemplateCode(option.value)}
                  className={form.templateCode === option.value ? "rounded-xl border-2 border-brand bg-blue-50 p-4 text-left" : "rounded-xl border border-line bg-surface p-4 text-left"}
                >
                  <div className="font-semibold text-ink">{option.label}</div>
                  <div className="mt-2 text-sm text-muted">{option.description}</div>
                </button>
              ))}
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <label className="block">
                <span className="mb-1.5 block text-sm font-medium text-ink">Visual preset</span>
                <select className="form-input" value={form.visualPreset} onChange={(event) => setField("visualPreset", event.target.value)}>
                  {presetOptions.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="mb-1.5 block text-sm font-medium text-ink">Primary color</span>
                <input className="form-input h-12" type="color" value={form.primaryColor} onChange={(event) => setField("primaryColor", event.target.value)} />
              </label>
            </div>
          </section>

          <section className="space-y-4">
            <div>
              <h2 className="text-lg font-semibold text-ink">Hero Copy</h2>
              <p className="mt-1 text-sm text-muted">Control the first message visitors read on the public website.</p>
            </div>
            <label className="block">
              <span className="mb-1.5 block text-sm font-medium text-ink">Headline</span>
              <input className="form-input" value={form.heroHeadline} onChange={(event) => setField("heroHeadline", event.target.value)} />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-sm font-medium text-ink">Subheadline</span>
              <textarea className="form-input min-h-24" value={form.heroSubheadline} onChange={(event) => setField("heroSubheadline", event.target.value)} />
            </label>
            <div className="grid gap-4 md:grid-cols-2">
              <label className="block">
                <span className="mb-1.5 block text-sm font-medium text-ink">Primary CTA label</span>
                <input className="form-input" value={form.heroCtaLabel} onChange={(event) => setField("heroCtaLabel", event.target.value)} />
              </label>
              <label className="block">
                <span className="mb-1.5 block text-sm font-medium text-ink">Secondary CTA label</span>
                <input className="form-input" value={form.heroSecondaryCtaLabel} onChange={(event) => setField("heroSecondaryCtaLabel", event.target.value)} />
              </label>
            </div>
          </section>

          <section className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-lg font-semibold text-ink">Section Builder</h2>
                <p className="mt-1 text-sm text-muted">Show, hide, remove, and reorder the blocks rendered on the public website.</p>
              </div>
            </div>
            <div className="rounded-xl border border-line bg-surface p-4">
              <div className="text-sm font-semibold text-ink">Add section</div>
              <div className="mt-3 flex flex-wrap gap-2">
                {sectionLibrary.map((item) => (
                  <button key={item.type} type="button" className="rounded-md border border-line bg-white px-3 py-1.5 text-sm font-semibold text-ink" onClick={() => addSection(item.type)}>
                    {item.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="space-y-3">
              {form.sections.map((section, index) => (
                <div key={`${section.type}-${index}`} className="rounded-xl border border-line bg-white p-4">
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                    <div>
                      <div className="font-semibold text-ink">{section.label}</div>
                      <div className="mt-1 text-sm text-muted">{sectionLibrary.find((item) => item.type === section.type)?.description || "Custom section."}</div>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <button type="button" className="rounded-md border border-line px-3 py-1.5 text-sm font-semibold text-ink" onClick={() => moveSection(index, -1)}>Up</button>
                      <button type="button" className="rounded-md border border-line px-3 py-1.5 text-sm font-semibold text-ink" onClick={() => moveSection(index, 1)}>Down</button>
                      <button type="button" className="rounded-md border border-line px-3 py-1.5 text-sm font-semibold text-ink" onClick={() => updateSection(index, { visible: !section.visible })}>
                        {section.visible ? "Hide" : "Show"}
                      </button>
                      <button type="button" className="rounded-md border border-line px-3 py-1.5 text-sm font-semibold text-ink" onClick={() => removeSection(index)}>Remove</button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section className="space-y-4">
            <div>
              <h2 className="text-lg font-semibold text-ink">Testimonials</h2>
              <p className="mt-1 text-sm text-muted">Add optional proof points to strengthen the public page.</p>
            </div>
            <div className="space-y-3">
              {form.testimonials.map((row, index) => (
                <div key={`testimonial-${index}`} className="rounded-xl border border-line bg-surface p-4">
                  <textarea className="form-input min-h-20" placeholder="Quote" value={row.quote} onChange={(event) => updateCollection("testimonials", index, "quote", event.target.value)} />
                  <div className="mt-3 grid gap-3 md:grid-cols-2">
                    <input className="form-input" placeholder="Name" value={row.name} onChange={(event) => updateCollection("testimonials", index, "name", event.target.value)} />
                    <input className="form-input" placeholder="Role or context" value={row.role} onChange={(event) => updateCollection("testimonials", index, "role", event.target.value)} />
                  </div>
                  <button type="button" className="mt-3 rounded-md border border-line px-3 py-1.5 text-sm font-semibold text-ink" onClick={() => removeCollectionRow("testimonials", index)}>
                    Remove testimonial
                  </button>
                </div>
              ))}
            </div>
            <button type="button" className="rounded-md border border-line px-4 py-2 text-sm font-semibold text-ink" onClick={() => addCollectionRow("testimonials", { quote: "", name: "", role: "" })}>
              Add testimonial
            </button>
          </section>

          <section className="space-y-4">
            <div>
              <h2 className="text-lg font-semibold text-ink">FAQ</h2>
              <p className="mt-1 text-sm text-muted">Prepare answers for common questions before customers need to ask them.</p>
            </div>
            <div className="space-y-3">
              {form.faq.map((row, index) => (
                <div key={`faq-${index}`} className="rounded-xl border border-line bg-surface p-4">
                  <input className="form-input" placeholder="Question" value={row.question} onChange={(event) => updateCollection("faq", index, "question", event.target.value)} />
                  <textarea className="form-input mt-3 min-h-20" placeholder="Answer" value={row.answer} onChange={(event) => updateCollection("faq", index, "answer", event.target.value)} />
                  <button type="button" className="mt-3 rounded-md border border-line px-3 py-1.5 text-sm font-semibold text-ink" onClick={() => removeCollectionRow("faq", index)}>
                    Remove question
                  </button>
                </div>
              ))}
            </div>
            <button type="button" className="rounded-md border border-line px-4 py-2 text-sm font-semibold text-ink" onClick={() => addCollectionRow("faq", { question: "", answer: "" })}>
              Add FAQ item
            </button>
          </section>

          <section className="space-y-4">
            <div>
              <h2 className="text-lg font-semibold text-ink">SEO</h2>
              <p className="mt-1 text-sm text-muted">Store title and description for cleaner search and sharing metadata.</p>
            </div>
            <label className="block">
              <span className="mb-1.5 block text-sm font-medium text-ink">SEO title</span>
              <input className="form-input" value={form.seoTitle} onChange={(event) => setField("seoTitle", event.target.value)} />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-sm font-medium text-ink">SEO description</span>
              <textarea className="form-input min-h-24" value={form.seoDescription} onChange={(event) => setField("seoDescription", event.target.value)} />
            </label>
          </section>

          <button className="rounded-md bg-ink px-4 py-2 text-sm font-semibold text-white">Save Website Builder</button>
        </form>

        <div className="space-y-4">
          <div className="rounded-2xl border border-line bg-white p-5 shadow-sm">
            <h2 className="text-lg font-semibold text-ink">Website Status</h2>
            <div className="mt-4 space-y-3">
              <InfoCard label="Slug" value={selectedTenant.slug} />
              <InfoCard label="Status" value={selectedTenant.websiteStatus} capitalize />
              <InfoCard label="Template" value={form.templateCode} capitalize />
              <InfoCard label="Preset" value={form.visualPreset} capitalize />
              <div className="rounded-md bg-surface p-4">
                <div className="text-sm text-muted">Public URL</div>
                <Link className="mt-1 block break-all font-semibold text-brand" to={previewUrl}>{previewUrl}</Link>
              </div>
            </div>
          </div>

          <div className="rounded-2xl border border-line bg-white p-5 shadow-sm">
            <h2 className="text-lg font-semibold text-ink">Section Preview</h2>
            <div className="mt-4 space-y-3">
              {form.sections.map((section, index) => (
                <div key={`preview-${section.type}-${index}`} className="rounded-md border border-line bg-surface px-4 py-3">
                  <div className="font-semibold text-ink">{index + 1}. {section.label}</div>
                  <div className="mt-1 text-sm text-muted">{section.visible ? "Visible on site" : "Hidden from site"}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-2xl border border-line bg-white p-5 shadow-sm">
            <h2 className="text-lg font-semibold text-ink">Preset Notes</h2>
            <div className="mt-4 space-y-3 text-sm text-muted">
              {presetOptions.map((option) => (
                <div key={`preset-${option.value}`} className={form.visualPreset === option.value ? "rounded-md border border-blue-200 bg-blue-50 px-4 py-3" : "rounded-md border border-line bg-surface px-4 py-3"}>
                  <div className="font-semibold text-ink">{option.label}</div>
                  <div className="mt-1">{option.description}</div>
                </div>
              ))}
            </div>
          </div>

          {selectedTenant.settings?.categoryHints?.fulfillment ? (
            <div className="rounded-2xl border border-line bg-white p-5 shadow-sm">
              <h2 className="text-lg font-semibold text-ink">Category Rules</h2>
              <div className="mt-4 space-y-3 text-sm text-muted">
                <div className="rounded-md border border-line bg-surface px-4 py-3">
                  Allowed fulfillment: {(selectedTenant.settings.categoryHints.fulfillment.allowedTypes || []).join(", ") || "none"}
                </div>
                <div className="rounded-md border border-line bg-surface px-4 py-3">
                  Default fulfillment: {selectedTenant.settings.categoryHints.fulfillment.defaultType || "none"}
                </div>
                <div className="rounded-md border border-line bg-surface px-4 py-3">
                  Category: {selectedTenant.settings.categoryHints.categoryName || "Not selected"}
                </div>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}

function InfoCard({ label, value, capitalize = false }) {
  return (
    <div className="rounded-md bg-surface p-4">
      <div className="text-sm text-muted">{label}</div>
      <div className={`mt-1 font-semibold text-ink ${capitalize ? "capitalize" : ""}`}>{value}</div>
    </div>
  );
}
