import { apiClient } from "./apiClient.js";

export async function getCustomFields(tenantId, params = {}) {
  const response = await apiClient.get(`/tenants/${tenantId}/custom-fields`, { params });
  return response.data.data;
}

export async function createCustomField(tenantId, payload) {
  const response = await apiClient.post(`/tenants/${tenantId}/custom-fields`, payload);
  return response.data.data;
}

export async function updateCustomField(tenantId, fieldId, payload) {
  const response = await apiClient.put(`/tenants/${tenantId}/custom-fields/${fieldId}`, payload);
  return response.data.data;
}

export async function deleteCustomField(tenantId, fieldId) {
  const response = await apiClient.delete(`/tenants/${tenantId}/custom-fields/${fieldId}`);
  return response.data.data;
}

export async function validateCustomValues(tenantId, payload) {
  const response = await apiClient.post(`/tenants/${tenantId}/custom-fields/validate-values`, payload);
  return response.data.data;
}
