import { apiClient } from "./apiClient.js";

export async function getPaymentOverview(tenantId, params = {}) {
  const response = await apiClient.get(`/tenants/${tenantId}/payments/overview`, { params });
  return { data: response.data.data, meta: response.data.meta };
}

export async function getPaymentSettings(tenantId) {
  const response = await apiClient.get(`/tenants/${tenantId}/payments/settings`);
  return response.data.data;
}

export async function updatePaymentSettings(tenantId, payload) {
  const response = await apiClient.put(`/tenants/${tenantId}/payments/settings`, payload);
  return response.data.data;
}

export async function recordTransactionPayment(tenantId, transactionId, payload) {
  const response = await apiClient.post(`/tenants/${tenantId}/payments/transactions/${transactionId}/record`, payload);
  return response.data.data;
}

export async function refundTransactionPayment(tenantId, transactionId, payload) {
  const response = await apiClient.post(`/tenants/${tenantId}/payments/transactions/${transactionId}/refund`, payload);
  return response.data.data;
}

export async function decidePaymentRecord(tenantId, paymentRecordId, payload) {
  const response = await apiClient.post(`/tenants/${tenantId}/payments/records/${paymentRecordId}/decision`, payload);
  return response.data.data;
}

export async function syncStripePaymentRecord(tenantId, paymentRecordId) {
  const response = await apiClient.post(`/tenants/${tenantId}/payments/records/${paymentRecordId}/stripe-sync`);
  return response.data.data;
}

export async function getOwnerPaymentReceiptHtml(tenantId, paymentRecordId) {
  const response = await apiClient.get(`/tenants/${tenantId}/payments/records/${paymentRecordId}/receipt`, {
    responseType: "text",
  });
  return response.data;
}
