import { apiClient } from "./apiClient.js";

export async function getDailySummaryReport(tenantId, params = {}) {
  const response = await apiClient.get(`/tenants/${tenantId}/reports/daily-summary`, { params });
  return response.data.data;
}

export async function generateDailySummaryReport(tenantId, params = {}) {
  const response = await apiClient.post(`/tenants/${tenantId}/reports/daily-summary/generate`, null, { params });
  return response.data.data;
}

export async function getReportDeliverySettings(tenantId) {
  const response = await apiClient.get(`/tenants/${tenantId}/reports/delivery/settings`);
  return response.data.data;
}

export async function updateReportDeliverySettings(tenantId, payload) {
  const response = await apiClient.put(`/tenants/${tenantId}/reports/delivery/settings`, payload);
  return response.data.data;
}

export async function deliverDailySummaryReport(tenantId, payload) {
  const response = await apiClient.post(`/tenants/${tenantId}/reports/delivery/daily-summary`, payload);
  return response.data.data;
}

export async function runScheduledReportDelivery(tenantId, payload) {
  const response = await apiClient.post(`/tenants/${tenantId}/reports/delivery/run-scheduled`, payload);
  return response.data.data;
}

export async function getReportDeliveryLogs(tenantId, params = {}) {
  const response = await apiClient.get(`/tenants/${tenantId}/reports/delivery/logs`, { params });
  return { items: response.data.data, meta: response.data.meta };
}
