import { apiClient } from "./apiClient.js";

export async function getPublicBusiness(tenantSlug) {
  const response = await apiClient.get(`/public/businesses/${tenantSlug}`);
  return response.data.data;
}

export async function getPublicItems(tenantSlug, params = {}) {
  const response = await apiClient.get(`/public/businesses/${tenantSlug}/items`, { params });
  return { items: response.data.data, meta: response.data.meta };
}

export async function getPublicItem(tenantSlug, itemId) {
  const response = await apiClient.get(`/public/businesses/${tenantSlug}/items/${itemId}`);
  return response.data.data;
}

export async function createPublicTransaction(tenantSlug, payload) {
  const response = await apiClient.post(`/public/businesses/${tenantSlug}/transactions`, payload);
  return response.data.data;
}

export async function createPublicOrder(tenantSlug, payload) {
  const response = await apiClient.post(`/public/businesses/${tenantSlug}/orders`, payload);
  return response.data.data;
}

export async function createPublicStripeCheckout(tenantSlug, transactionId, payload = {}) {
  const response = await apiClient.post(`/public/businesses/${tenantSlug}/transactions/${transactionId}/stripe-checkout`, payload);
  return response.data.data;
}

export async function syncPublicStripeCheckout(tenantSlug, transactionId, payload = {}) {
  const response = await apiClient.post(`/public/businesses/${tenantSlug}/transactions/${transactionId}/stripe-checkout/sync`, payload);
  return response.data.data;
}

export async function getPublicChatState(tenantSlug, conversationId = null) {
  const response = await apiClient.get(`/public/businesses/${tenantSlug}/chat`, {
    params: conversationId ? { conversationId } : {},
  });
  return response.data.data;
}

export async function sendPublicChatMessage(tenantSlug, payload) {
  const response = await apiClient.post(`/public/businesses/${tenantSlug}/chat/messages`, payload);
  return response.data.data;
}

export function resolveUploadUrl(url) {
  if (!url) return "";
  if (url.startsWith("http")) return url;
  const apiBase = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api/v1";
  return `${apiBase.replace("/api/v1", "")}${url}`;
}
