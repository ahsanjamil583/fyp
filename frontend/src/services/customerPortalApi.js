import { apiClient } from "./apiClient.js";

export async function getMarketplaceBusinesses(params = {}) {
  const response = await apiClient.get("/customer/marketplace", { params });
  return { items: response.data.data, meta: response.data.meta };
}

export async function getMarketplaceBusiness(tenantSlug) {
  const response = await apiClient.get(`/customer/businesses/${tenantSlug}`);
  return response.data.data;
}

export async function getMarketplaceItems(tenantSlug, params = {}) {
  const response = await apiClient.get(`/customer/businesses/${tenantSlug}/items`, { params });
  return { items: response.data.data, meta: response.data.meta };
}

export async function getMarketplaceItem(tenantSlug, itemId) {
  const response = await apiClient.get(`/customer/businesses/${tenantSlug}/items/${itemId}`);
  return response.data.data;
}

export async function getCustomerChatState(tenantSlug) {
  const response = await apiClient.get(`/customer/businesses/${tenantSlug}/chat`);
  return response.data.data;
}

export async function sendCustomerChatMessage(tenantSlug, payload) {
  const response = await apiClient.post(`/customer/businesses/${tenantSlug}/chat/messages`, payload);
  return response.data.data;
}

export async function getCustomerCart() {
  const response = await apiClient.get("/customer/cart");
  return response.data.data;
}

export async function getCustomerFavorites() {
  const response = await apiClient.get("/customer/favorites");
  return response.data.data;
}

export async function addCustomerFavorite(payload) {
  const response = await apiClient.post("/customer/favorites/items", payload);
  return response.data.data;
}

export async function removeCustomerFavorite(itemId, tenantId) {
  const response = await apiClient.delete(`/customer/favorites/items/${itemId}`, { params: { tenantId } });
  return response.data.data;
}

export async function addCartItem(payload) {
  const response = await apiClient.post("/customer/cart/items", payload);
  return response.data.data;
}

export async function updateCartItem(itemId, payload) {
  const response = await apiClient.put(`/customer/cart/items/${itemId}`, payload);
  return response.data.data;
}

export async function removeCartItem(itemId) {
  const response = await apiClient.delete(`/customer/cart/items/${itemId}`);
  return response.data.data;
}

export async function createCustomerTransaction(payload) {
  const response = await apiClient.post("/customer/transactions", payload);
  return response.data.data;
}

export async function createCustomerOrder(payload) {
  const response = await apiClient.post("/customer/orders", payload);
  return response.data.data;
}

export async function confirmCustomerDraftTransaction(tenantSlug, payload) {
  const response = await apiClient.post(`/customer/businesses/${tenantSlug}/orders/confirm-draft`, payload);
  return response.data.data;
}

export async function confirmCustomerDraftOrder(tenantSlug, payload) {
  const response = await apiClient.post(`/customer/businesses/${tenantSlug}/orders/confirm-draft`, payload);
  return response.data.data;
}

export async function getCustomerTransactions(params = {}) {
  const response = await apiClient.get("/customer/transactions", { params });
  return { items: response.data.data, meta: response.data.meta };
}

export async function getCustomerOrders(params = {}) {
  const response = await apiClient.get("/customer/orders", { params });
  return { items: response.data.data, meta: response.data.meta };
}

export async function getCustomerTransaction(orderId) {
  const response = await apiClient.get(`/customer/transactions/${orderId}`);
  return response.data.data;
}

export async function submitCustomerPaymentProof(orderId, payload) {
  const formData = new FormData();
  formData.append("amount", payload.amount ?? "");
  formData.append("method", payload.method || "");
  formData.append("referenceNumber", payload.referenceNumber || "");
  formData.append("notes", payload.notes || "");
  if (payload.proofFile) {
    formData.append("proofFile", payload.proofFile);
  }
  const response = await apiClient.post(`/customer/transactions/${orderId}/payment-proof`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data.data;
}

export async function createCustomerStripeCheckout(orderId, payload = {}) {
  const response = await apiClient.post(`/customer/transactions/${orderId}/stripe-checkout`, payload);
  return response.data.data;
}

export async function syncCustomerStripeCheckout(orderId, payload = {}) {
  const response = await apiClient.post(`/customer/transactions/${orderId}/stripe-checkout/sync`, payload);
  return response.data.data;
}

export async function getCustomerPaymentReceiptHtml(orderId, paymentRecordId) {
  const response = await apiClient.get(`/customer/transactions/${orderId}/payments/${paymentRecordId}/receipt`, {
    responseType: "text",
  });
  return response.data;
}

export async function reorderCustomerTransaction(orderId) {
  const response = await apiClient.post(`/customer/transactions/${orderId}/reorder`);
  return response.data.data;
}

export async function getCustomerOrder(orderId) {
  const response = await apiClient.get(`/customer/orders/${orderId}`);
  return response.data.data;
}

export async function getCustomerNotifications(params = {}) {
  const response = await apiClient.get("/customer/notifications", { params });
  return { items: response.data.data, meta: response.data.meta };
}

export async function markCustomerNotificationRead(notificationId) {
  const response = await apiClient.post(`/customer/notifications/${notificationId}/read`);
  return response.data.data;
}

export async function markAllCustomerNotificationsRead() {
  const response = await apiClient.post("/customer/notifications/read-all");
  return response.data.data;
}

export function resolveUploadUrl(url) {
  if (!url) return "";
  if (url.startsWith("http")) return url;
  const apiBase = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api/v1";
  return `${apiBase.replace("/api/v1", "")}${url}`;
}
