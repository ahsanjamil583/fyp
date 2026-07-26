const SECTION_LIBRARY = {
  hero: {
    type: "hero",
    label: "Hero",
    description: "Headline, intro copy, and top CTA.",
  },
  metrics: {
    type: "metrics",
    label: "Highlights",
    description: "Quick business stats and trust signals.",
  },
  catalog: {
    type: "catalog",
    label: "Catalog Grid",
    description: "Products, bundles, and featured inventory.",
  },
  services: {
    type: "services",
    label: "Service Grid",
    description: "Service-focused cards with duration and delivery mode.",
  },
  transaction_form: {
    type: "transaction_form",
    label: "Quick Request Form",
    description: "Public form for orders, bookings, quotes, or inquiries.",
  },
  testimonials: {
    type: "testimonials",
    label: "Testimonials",
    description: "Manually managed customer proof block.",
  },
  faq: {
    type: "faq",
    label: "FAQ",
    description: "Common questions and business answers.",
  },
  contact: {
    type: "contact",
    label: "Contact",
    description: "Location, phone, email, and WhatsApp details.",
  },
};

export const WEBSITE_TEMPLATE_OPTIONS = [
  { value: "default", label: "Showcase", description: "Balanced layout for mixed businesses." },
  { value: "catalog", label: "Catalog", description: "Product-led storefront with strong browsing focus." },
  { value: "service", label: "Service", description: "Service-led landing page with consultation and booking focus." },
];

export const WEBSITE_PRESET_OPTIONS = {
  default: [
    { value: "aurora", label: "Aurora", description: "Warm spotlight gradient with polished cards.", background: "linear-gradient(135deg, #fff7ed 0%, #ffedd5 45%, #ffffff 100%)", surface: "#ffffff", accent: "#ea580c", secondary: "#9a3412" },
    { value: "harbor", label: "Harbor", description: "Soft blue editorial feel for mixed storefronts.", background: "linear-gradient(135deg, #eff6ff 0%, #dbeafe 48%, #ffffff 100%)", surface: "#ffffff", accent: "#2563eb", secondary: "#1d4ed8" },
  ],
  catalog: [
    { value: "market", label: "Market", description: "Dense retail-inspired layout with crisp contrast.", background: "linear-gradient(135deg, #fafaf9 0%, #f5f5f4 40%, #ffffff 100%)", surface: "#ffffff", accent: "#0f766e", secondary: "#115e59" },
    { value: "bazaar", label: "Bazaar", description: "Lively storefront style for discovery and offers.", background: "linear-gradient(135deg, #fefce8 0%, #fef3c7 42%, #ffffff 100%)", surface: "#ffffff", accent: "#ca8a04", secondary: "#a16207" },
  ],
  service: [
    { value: "studio", label: "Studio", description: "Premium service presentation with calm spacing.", background: "linear-gradient(135deg, #f8fafc 0%, #e2e8f0 48%, #ffffff 100%)", surface: "#ffffff", accent: "#334155", secondary: "#0f172a" },
    { value: "care", label: "Care", description: "Welcoming layout for consultative and appointment-based work.", background: "linear-gradient(135deg, #ecfeff 0%, #cffafe 45%, #ffffff 100%)", surface: "#ffffff", accent: "#0891b2", secondary: "#0e7490" },
  ],
};

export function getTemplatePresetOptions(templateCode) {
  return WEBSITE_PRESET_OPTIONS[templateCode] || WEBSITE_PRESET_OPTIONS.default;
}

export function getPresetMeta(templateCode, presetCode) {
  const options = getTemplatePresetOptions(templateCode);
  return options.find((option) => option.value === presetCode) || options[0];
}

export function getSectionLibraryItems() {
  return Object.values(SECTION_LIBRARY);
}

export function createSection(type, order, overrides = {}) {
  const base = SECTION_LIBRARY[type];
  return {
    type,
    label: overrides.label || base?.label || type,
    visible: overrides.visible ?? true,
    order,
    content: overrides.content || {},
  };
}

export function buildDefaultSections(templateCode) {
  if (templateCode === "catalog") {
    return [
      createSection("hero", 1),
      createSection("metrics", 2),
      createSection("catalog", 3),
      createSection("transaction_form", 4),
      createSection("testimonials", 5),
      createSection("contact", 6),
    ];
  }
  if (templateCode === "service") {
    return [
      createSection("hero", 1),
      createSection("metrics", 2),
      createSection("services", 3),
      createSection("faq", 4),
      createSection("transaction_form", 5),
      createSection("contact", 6),
    ];
  }
  return [
    createSection("hero", 1),
    createSection("metrics", 2),
    createSection("catalog", 3),
    createSection("services", 4),
    createSection("transaction_form", 5),
    createSection("contact", 6),
  ];
}

export function normalizeSections(sections, templateCode) {
  const fallback = buildDefaultSections(templateCode);
  if (!Array.isArray(sections) || !sections.length) {
    return fallback;
  }
  return sections
    .map((section, index) => createSection(section.type, Number(section.order || index + 1), section))
    .sort((left, right) => left.order - right.order);
}

export function suggestVisualPreset(category, templateCode) {
  const name = `${category?.name || ""} ${category?.slug || ""}`.toLowerCase();
  if (templateCode === "service") {
    if (name.includes("clinic") || name.includes("health") || name.includes("pharmacy")) return "care";
    return "studio";
  }
  if (templateCode === "catalog") {
    if (name.includes("fashion") || name.includes("retail") || name.includes("grocery")) return "market";
    return "bazaar";
  }
  return name.includes("restaurant") || name.includes("food") ? "aurora" : "harbor";
}

export function buildCategoryDrivenWebsiteSettings(category, currentSettings = {}, businessName = "") {
  const templateCode = category?.websiteHints?.recommendedTemplate || currentSettings.templateCode || "default";
  const primaryColor = category?.websiteHints?.recommendedPrimaryColor || currentSettings.primaryColor || "#2563EB";
  const presetCode = suggestVisualPreset(category, templateCode);
  const fallbackHeadline = businessName ? `${businessName} made easy to browse, book, and contact online.` : "Bring your business online with a clear, modern public website.";
  return {
    ...currentSettings,
    templateCode,
    visualPreset: presetCode,
    primaryColor,
    hero: {
      headline: currentSettings.hero?.headline || fallbackHeadline,
      subheadline: currentSettings.hero?.subheadline || "Show your offers, answer common questions, and let customers take action from one polished page.",
      ctaLabel: currentSettings.hero?.ctaLabel || "Start now",
      secondaryCtaLabel: currentSettings.hero?.secondaryCtaLabel || "Browse offers",
    },
    sections: normalizeSections(currentSettings.sections, templateCode),
    seo: currentSettings.seo || {},
    testimonials: currentSettings.testimonials || [],
    faq: currentSettings.faq || [],
  };
}

export function buildWebsiteTheme(websiteSettings = {}) {
  const templateCode = websiteSettings.templateCode || "default";
  const preset = getPresetMeta(templateCode, websiteSettings.visualPreset);
  return {
    templateCode,
    presetCode: preset.value,
    background: preset.background,
    surface: preset.surface,
    accent: websiteSettings.primaryColor || preset.accent,
    secondary: preset.secondary,
  };
}

export function buildBusinessHighlights(business, items = []) {
  const bookableCount = items.filter((item) => item.isBookable || item.itemType === "service" || item.itemType === "bookable").length;
  const catalogCount = items.filter((item) => item.isSellable).length;
  const bundleCount = items.filter((item) => item.bundleComponents?.length).length;
  const city = business?.address?.city || "Online";
  return [
    { label: "Location", value: city },
    { label: "Offers", value: String(items.length || 0) },
    { label: "Services", value: String(bookableCount) },
    { label: "Bundles", value: String(bundleCount) },
    { label: "Products", value: String(catalogCount) },
  ];
}

export function getVisibleSections(websiteSettings = {}) {
  return normalizeSections(websiteSettings.sections, websiteSettings.templateCode || "default").filter((section) => section.visible !== false);
}

