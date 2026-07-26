import { apiClient } from "./apiClient.js";

export async function createCustomer(tenantId, payload) {
  const response = await apiClient.post(`/tenants/${tenantId}/customers`, payload);
  return response.data.data;
}

export async function getCustomers(tenantId, params = {}) {
  const response = await apiClient.get(`/tenants/${tenantId}/customers`, { params });
  return { items: response.data.data, meta: response.data.meta };
}

export async function getCustomerInsights(tenantId) {
  const response = await apiClient.get(`/tenants/${tenantId}/customers/insights`);
  return response.data.data;
}

export async function getCustomer(tenantId, customerId) {
  const response = await apiClient.get(`/tenants/${tenantId}/customers/${customerId}`);
  return response.data.data;
}

export async function updateCustomer(tenantId, customerId, payload) {
  const response = await apiClient.put(`/tenants/${tenantId}/customers/${customerId}`, payload);
  return response.data.data;
}

export async function deleteCustomer(tenantId, customerId) {
  const response = await apiClient.delete(`/tenants/${tenantId}/customers/${customerId}`);
  return response.data.data;
}
