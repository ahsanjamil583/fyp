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

export async function captureWhatsAppEmbeddedSignup(tenantId, payload) {
  const response = await apiClient.post(`/tenants/${tenantId}/whatsapp/embedded-signup/capture`, payload);
  return response.data.data;
}

export async function exchangeWhatsAppEmbeddedSignupToken(tenantId) {
  const response = await apiClient.post(`/tenants/${tenantId}/whatsapp/embedded-signup/exchange-token`);
  return response.data.data;
}

export async function subscribeWhatsAppEmbeddedSignupWebhooks(tenantId) {
  const response = await apiClient.post(`/tenants/${tenantId}/whatsapp/embedded-signup/subscribe-webhooks`);
  return response.data.data;
}

export async function registerWhatsAppEmbeddedSignupPhone(tenantId, payload) {
  const response = await apiClient.post(`/tenants/${tenantId}/whatsapp/embedded-signup/register-phone`, payload);
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


export async function getWhatsAppRoutingStatus(tenantId) {
  const response = await apiClient.get(`/tenants/${tenantId}/whatsapp/embedded-signup/routing-status`);
  return response.data.data;
}

export async function testWhatsAppRouting(tenantId, payload) {
  const response = await apiClient.post(`/tenants/${tenantId}/whatsapp/embedded-signup/test-routing`, payload);
  return response.data.data;
}


export async function getWhatsAppDiagnostics(tenantId) {
  const response = await apiClient.get(`/tenants/${tenantId}/whatsapp/diagnostics`);
  return response.data.data;
}

export async function testWhatsAppLiveWebhookPayload(tenantId, payload) {
  const response = await apiClient.post(`/tenants/${tenantId}/whatsapp/diagnostics/test-webhook-payload`, payload);
  return response.data.data;
}

export async function getWhatsAppConversationTimeline(tenantId, conversationId) {
  const response = await apiClient.get(`/tenants/${tenantId}/whatsapp/conversations/${conversationId}/timeline`);
  return response.data.data;
}

export async function getWhatsAppGoLiveChecklist(tenantId) {
  const response = await apiClient.get(`/tenants/${tenantId}/whatsapp/go-live/checklist`);
  return response.data.data;
}

export async function recordWhatsAppGoLiveTestRun(tenantId, payload) {
  const response = await apiClient.post(`/tenants/${tenantId}/whatsapp/go-live/test-run`, payload);
  return response.data.data;
}
