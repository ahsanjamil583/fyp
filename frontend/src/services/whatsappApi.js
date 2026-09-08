import { apiClient } from "./apiClient.js";

export async function getWhatsAppSettings(tenantId) {
  const response = await apiClient.get(`/tenants/${tenantId}/whatsapp/settings`);
  return response.data.data;
}

export async function saveWhatsAppSettings(tenantId, payload) {
  const response = await apiClient.put(`/tenants/${tenantId}/whatsapp/settings`, payload);
  return response.data.data;
}

export async function disconnectWhatsApp(tenantId) {
  const response = await apiClient.post(`/tenants/${tenantId}/whatsapp/disconnect`);
  return response.data.data;
}

export async function refreshWhatsAppBridgeToken(tenantId) {
  const response = await apiClient.post(`/tenants/${tenantId}/whatsapp/bridge-token`);
  return response.data.data;
}

export async function simulateWhatsAppInbound(tenantId, payload) {
  const response = await apiClient.post(`/tenants/${tenantId}/whatsapp/mock/inbound`, payload);
  return response.data.data;
}

export async function sendWhatsAppTest(tenantId, payload) {
  const response = await apiClient.post(`/tenants/${tenantId}/whatsapp/send-test`, payload);
  return response.data.data;
}

export async function getWhatsAppConversations(tenantId, params = {}) {
  const response = await apiClient.get(`/tenants/${tenantId}/whatsapp/conversations`, { params });
  return { items: response.data.data, meta: response.data.meta };
}
