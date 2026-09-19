import { apiClient } from "./apiClient.js";

export async function getBusinessNotifications(tenantId, params = {}) {
  const response = await apiClient.get(`/tenants/${tenantId}/notifications`, { params });
  return { items: response.data.data, meta: response.data.meta };
}

export async function markBusinessNotificationRead(tenantId, notificationId) {
  const response = await apiClient.post(`/tenants/${tenantId}/notifications/${notificationId}/read`);
  return response.data.data;
}

export async function markAllBusinessNotificationsRead(tenantId) {
  const response = await apiClient.post(`/tenants/${tenantId}/notifications/read-all`);
  return response.data.data;
}

export async function refreshBusinessStockAlerts(tenantId) {
  const response = await apiClient.post(`/tenants/${tenantId}/notifications/refresh-stock-alerts`);
  return response.data.data;
}

export async function getOrderMessageSettings(tenantId) {
  const response = await apiClient.get(`/tenants/${tenantId}/order-messages`);
  return response.data.data;
}

export async function updateOrderMessageSettings(tenantId, payload) {
  const response = await apiClient.put(`/tenants/${tenantId}/order-messages`, payload);
  return response.data.data;
}
