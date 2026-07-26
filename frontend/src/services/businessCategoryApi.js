import { apiClient } from "./apiClient.js";

const fallbackBusinessCategories = [
  ["retail-store", "Retail Store", "shopping-bag", "catalog", "#2563EB"],
  ["restaurant", "Restaurant", "utensils", "catalog", "#DC2626"],
  ["pharmacy", "Pharmacy", "pill", "catalog", "#059669"],
  ["fashion-clothing", "Fashion / Clothing", "shirt", "catalog", "#7C3AED"],
  ["services", "Services", "handshake", "service", "#0891B2"],
  ["grocery", "Grocery", "shopping-cart", "catalog", "#16A34A"],
  ["electronics", "Electronics", "cpu", "catalog", "#0F172A"],
  ["beauty-salon", "Beauty / Salon", "sparkles", "service", "#DB2777"],
  ["tailor", "Tailor", "scissors", "service", "#92400E"],
  ["general-business", "General Business", "briefcase", "default", "#2563EB"],
].map(([slug, name, icon, template, color]) => ({
  id: slug,
  slug,
  name,
  icon,
  description: `${name} business category.`,
  isActive: true,
  suggestedModules: ["website_builder", "customer_portal", "ai_chat", "analytics"],
  websiteHints: {
    recommendedTemplate: template,
    recommendedPrimaryColor: color,
    heroStyle: template === "catalog" ? "catalog-first" : template === "service" ? "service-first" : "general-purpose",
  },
  fulfillmentHints: {
    defaultMode: template === "service" ? "consultation" : "pickup_or_delivery",
    supportsDelivery: template !== "service",
    supportsPickup: true,
    supportsInPerson: true,
  },
  templateRules: {
    recommendedTemplate: template,
    recommendedPrimaryColor: color,
    recommendedVisualPreset: template === "catalog" ? "market" : template === "service" ? "studio" : "harbor",
    heroStyle: template === "catalog" ? "catalog-first" : template === "service" ? "service-first" : "general-purpose",
    sectionPriority: template === "service" ? ["hero", "metrics", "services", "faq", "transaction_form", "contact"] : ["hero", "metrics", "catalog", "transaction_form", "testimonials", "contact"],
  },
  analyticsConfig: { suggestions: [], focusMetrics: ["totalTransactions", "grossRevenue"] },
}));

function normalizeCategoryList(categories) {
  return Array.isArray(categories) && categories.length ? categories : fallbackBusinessCategories;
}

export async function getPublicBusinessCategories() {
  try {
    const response = await apiClient.get("/public/business-categories");
    return normalizeCategoryList(response.data.data);
  } catch (error) {
    return fallbackBusinessCategories;
  }
}

export async function getAdminBusinessCategories() {
  const response = await apiClient.get("/admin/business-categories");
  return response.data.data;
}

export async function createAdminBusinessCategory(payload) {
  const response = await apiClient.post("/admin/business-categories", payload);
  return response.data.data;
}

export async function updateAdminBusinessCategory(categoryId, payload) {
  const response = await apiClient.put(`/admin/business-categories/${categoryId}`, payload);
  return response.data.data;
}

export async function deleteAdminBusinessCategory(categoryId) {
  const response = await apiClient.delete(`/admin/business-categories/${categoryId}`);
  return response.data.data;
}
