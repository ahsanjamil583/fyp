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
import { SectionTitle } from "../../components/ui/SectionTitle.jsx";
import { StatCard as KitStatCard } from "../../components/ui/index.jsx";
import { getApiErrorMessage } from "../../services/apiError.js";

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
    // Keyed on the tenant id, not the tenant object: background refreshes hand back a
    // new object reference, and re-running this reset discarded unsaved edits.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedTenant?.id]);

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
      setError(getApiErrorMessage(requestError, "Unable to save website settings."));
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
      setMessage(saved.websiteStatus === "published" ? "Website published." : saved.websiteStatus === "pending_review" ? "Website request sent to admin for review." : "Website unpublished.");
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Unable to change publish status. Make sure Website Builder is enabled."));
    }
  }

  if (!selectedTenant) {
    return (
      <section className="space-y-4">
        <h1 className="text-2xl font-extrabold tracking-tight text-ink">Public Website</h1>
        <p className="text-sm text-muted">Create a business before configuring a website.</p>
      </section>
    );
  }

  const previewUrl = `/businesses/${selectedTenant.slug}`;
  const approvalStatus = selectedTenant.websiteApprovalStatus || (selectedTenant.websiteStatus === "published" ? "approved" : "not_requested");
  const approvalCriteria = selectedTenant.websiteApprovalCriteria;
  const approvalChecks = approvalCriteria?.checks || [];
  const websiteIsPublished = selectedTenant.websiteStatus === "published";

  return (
    <section className="space-y-6">
      <div className="flex flex-col gap-3 border-b border-line-soft pb-5 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-brand">Website Builder</p>
          <h1 className="mt-1.5 text-2xl font-extrabold tracking-tight text-ink">Public Website</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-muted">
            Work from top to bottom: choose the look, write the first message, arrange sections, save, preview, then publish.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link className="rounded-xl border border-line px-4 py-2 text-sm font-semibold text-ink hover:bg-surface" to={previewUrl}>
            {websiteIsPublished ? "View live website" : "Preview website"}
          </Link>
          <button className="rounded-xl bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700" onClick={togglePublish}>
            {websiteIsPublished ? "Unpublish website" : approvalStatus === "pending" ? "Resubmit for review" : "Submit for review"}
          </button>
        </div>
      </div>

      {message ? <div className="rounded-xl border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">{message}</div> : null}
      {error ? <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}

      <div className="rounded-2xl border border-brand-100 bg-brand-50 p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="text-[11px] font-bold uppercase tracking-[0.16em] text-brand">Website flow</div>
            <h2 className="mt-1 text-xl font-extrabold text-ink">
              {websiteIsPublished ? "Your website is published" : "Preview before you publish"}
            </h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-brand-900">
              Save your edits first. Preview opens the public page exactly as customers will see it. Publishing sends the website for review or makes it live after approval.
            </p>
          </div>
          <div className="grid gap-2 text-sm font-bold text-brand-900 sm:grid-cols-3 lg:min-w-[420px]">
            {[
              ["1", "Edit content"],
              ["2", "Preview website"],
              ["3", websiteIsPublished ? "Keep updated" : "Submit review"],
            ].map(([number, label]) => (
              <div key={label} className="rounded-xl border border-brand-100 bg-white px-3 py-3">
                <span className="mr-2 inline-grid h-6 w-6 place-items-center rounded-full bg-brand text-xs text-white">{number}</span>
                {label}
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="rounded-xl border border-line bg-white p-5 shadow-card">
        <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
          <div>
            <SectionTitle>Admin website approval</SectionTitle>
            <p className="mt-1 text-sm text-muted">Your website goes live after admin confirms the business is ready.</p>
          </div>
          <span className="rounded-full bg-surface px-3 py-1 text-xs font-bold capitalize text-ink ring-1 ring-line">
            {approvalStatus.replaceAll("_", " ")}
          </span>
        </div>
        {selectedTenant.websiteApprovalNote ? <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">Admin note: {selectedTenant.websiteApprovalNote}</div> : null}
        {approvalChecks.length ? (
          <div className="mt-4 grid gap-2 md:grid-cols-2">
            {approvalChecks.map((check) => (
              <div key={check.key} className={check.passed ? "rounded-xl border border-green-100 bg-green-50 px-3 py-2 text-sm text-green-800" : "rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800"}>
                <div className="font-semibold">{check.passed ? "Done" : "Needed"}: {check.label}</div>
                <div className="mt-1 text-xs">{check.message}</div>
              </div>
            ))}
          </div>
        ) : null}
      </div>

      {selectedCategory ? (
        <div className="rounded-2xl border border-brand-100 bg-brand-50 p-5">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <div className="text-sm font-semibold text-brand-900">Category website guidance for {selectedCategory.name}</div>
              <div className="mt-2 text-sm leading-6 text-brand-800">
                Recommended template: <span className="font-semibold">{selectedCategory.websiteHints?.recommendedTemplate || "default"}</span>
                {" "}with suggested primary color <span className="font-semibold">{selectedCategory.websiteHints?.recommendedPrimaryColor || "#2563EB"}</span>.
              </div>
              {selectedCategory.templateRules?.sectionPriority?.length ? (
                <div className="mt-2 text-sm leading-6 text-brand-800">
                  Preferred sections: <span className="font-semibold">{selectedCategory.templateRules.sectionPriority.join(", ")}</span>.
                </div>
              ) : null}
            </div>
            <button type="button" className="rounded-xl border border-brand-200 bg-white px-4 py-2 text-sm font-semibold text-brand-900" onClick={applyCategoryWebsiteHints}>
              Apply Category Preset
            </button>
          </div>
        </div>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
        <form className="space-y-6 rounded-2xl border border-line bg-white p-5 shadow-card" onSubmit={save}>
          <section className="space-y-4">
            <div>
              <SectionTitle>Template Direction</SectionTitle>
              <p className="mt-1 text-sm text-muted">Pick the structural style that best matches how this business sells or serves.</p>
            </div>
            <div className="grid gap-3 md:grid-cols-3">
              {WEBSITE_TEMPLATE_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => setTemplateCode(option.value)}
                  className={form.templateCode === option.value ? "rounded-xl border-2 border-brand bg-brand-50 p-4 text-left" : "rounded-xl border border-line bg-surface p-4 text-left"}
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
              <SectionTitle>Hero Copy</SectionTitle>
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
                <SectionTitle>Section Builder</SectionTitle>
                <p className="mt-1 text-sm text-muted">Show, hide, remove, and reorder the blocks rendered on the public website.</p>
              </div>
            </div>
            <div className="rounded-xl border border-line bg-surface p-4">
              <div className="text-sm font-semibold text-ink">Add section</div>
              <div className="mt-3 flex flex-wrap gap-2">
                {sectionLibrary.map((item) => (
                  <button key={item.type} type="button" className="rounded-xl border border-line bg-white px-3 py-1.5 text-sm font-semibold text-ink" onClick={() => addSection(item.type)}>
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
                      <button type="button" className="rounded-xl border border-line px-3 py-1.5 text-sm font-semibold text-ink" onClick={() => moveSection(index, -1)}>Up</button>
                      <button type="button" className="rounded-xl border border-line px-3 py-1.5 text-sm font-semibold text-ink" onClick={() => moveSection(index, 1)}>Down</button>
                      <button type="button" className="rounded-xl border border-line px-3 py-1.5 text-sm font-semibold text-ink" onClick={() => updateSection(index, { visible: !section.visible })}>
                        {section.visible ? "Hide" : "Show"}
                      </button>
                      <button type="button" className="rounded-xl border border-line px-3 py-1.5 text-sm font-semibold text-ink" onClick={() => removeSection(index)}>Remove</button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section className="space-y-4">
            <div>
              <SectionTitle>Testimonials</SectionTitle>
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
                  <button type="button" className="mt-3 rounded-xl border border-line px-3 py-1.5 text-sm font-semibold text-ink" onClick={() => removeCollectionRow("testimonials", index)}>
                    Remove testimonial
                  </button>
                </div>
              ))}
            </div>
            <button type="button" className="rounded-xl border border-line px-4 py-2 text-sm font-semibold text-ink" onClick={() => addCollectionRow("testimonials", { quote: "", name: "", role: "" })}>
              Add testimonial
            </button>
          </section>

          <section className="space-y-4">
            <div>
              <SectionTitle>FAQ</SectionTitle>
              <p className="mt-1 text-sm text-muted">Prepare answers for common questions before customers need to ask them.</p>
            </div>
            <div className="space-y-3">
              {form.faq.map((row, index) => (
                <div key={`faq-${index}`} className="rounded-xl border border-line bg-surface p-4">
                  <input className="form-input" placeholder="Question" value={row.question} onChange={(event) => updateCollection("faq", index, "question", event.target.value)} />
                  <textarea className="form-input mt-3 min-h-20" placeholder="Answer" value={row.answer} onChange={(event) => updateCollection("faq", index, "answer", event.target.value)} />
                  <button type="button" className="mt-3 rounded-xl border border-line px-3 py-1.5 text-sm font-semibold text-ink" onClick={() => removeCollectionRow("faq", index)}>
                    Remove question
                  </button>
                </div>
              ))}
            </div>
            <button type="button" className="rounded-xl border border-line px-4 py-2 text-sm font-semibold text-ink" onClick={() => addCollectionRow("faq", { question: "", answer: "" })}>
              Add FAQ item
            </button>
          </section>

          <section className="space-y-4">
            <div>
              <SectionTitle>SEO</SectionTitle>
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

          <button className="rounded-xl bg-ink px-4 py-2 text-sm font-semibold text-white">Save Website Builder</button>
        </form>

        <div className="space-y-4">
          <div className="rounded-2xl border border-line bg-white p-5 shadow-card">
            <SectionTitle>Website Status</SectionTitle>
            <div className="mt-4 space-y-3">
              <InfoCard label="Slug" value={selectedTenant.slug} />
              <InfoCard label="Status" value={selectedTenant.websiteStatus} capitalize />
              <InfoCard label="Template" value={form.templateCode} capitalize />
              <InfoCard label="Preset" value={form.visualPreset} capitalize />
              <div className="rounded-xl bg-surface p-4">
                <div className="text-sm text-muted">Public URL</div>
                <Link className="mt-1 block break-all font-semibold text-brand" to={previewUrl}>{previewUrl}</Link>
              </div>
            </div>
          </div>

          <div className="rounded-2xl border border-line bg-white p-5 shadow-card">
            <SectionTitle>Section Preview</SectionTitle>
            <div className="mt-4 space-y-3">
              {form.sections.map((section, index) => (
                <div key={`preview-${section.type}-${index}`} className="rounded-xl border border-line bg-surface px-4 py-3">
                  <div className="font-semibold text-ink">{index + 1}. {section.label}</div>
                  <div className="mt-1 text-sm text-muted">{section.visible ? "Visible on site" : "Hidden from site"}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-2xl border border-line bg-white p-5 shadow-card">
            <SectionTitle>Preset Notes</SectionTitle>
            <div className="mt-4 space-y-3 text-sm text-muted">
              {presetOptions.map((option) => (
                <div key={`preset-${option.value}`} className={form.visualPreset === option.value ? "rounded-xl border border-brand-200 bg-brand-50 px-4 py-3" : "rounded-xl border border-line bg-surface px-4 py-3"}>
                  <div className="font-semibold text-ink">{option.label}</div>
                  <div className="mt-1">{option.description}</div>
                </div>
              ))}
            </div>
          </div>

          {selectedTenant.settings?.categoryHints?.fulfillment ? (
            <div className="rounded-2xl border border-line bg-white p-5 shadow-card">
              <SectionTitle>Category Rules</SectionTitle>
              <div className="mt-4 space-y-3 text-sm text-muted">
                <div className="rounded-xl border border-line bg-surface px-4 py-3">
                  Allowed fulfillment: {(selectedTenant.settings.categoryHints.fulfillment.allowedTypes || []).join(", ") || "none"}
                </div>
                <div className="rounded-xl border border-line bg-surface px-4 py-3">
                  Default fulfillment: {selectedTenant.settings.categoryHints.fulfillment.defaultType || "none"}
                </div>
                <div className="rounded-xl border border-line bg-surface px-4 py-3">
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
  return <KitStatCard label={label} value={capitalize ? String(value ?? "") : value} />;
}
