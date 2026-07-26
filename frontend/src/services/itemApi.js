import { apiClient } from "./apiClient.js";

export async function createItemCategory(tenantId, payload) {
  const response = await apiClient.post(`/tenants/${tenantId}/item-categories`, payload);
  return response.data.data;
}

export async function getItemCategories(tenantId, params = {}) {
  const response = await apiClient.get(`/tenants/${tenantId}/item-categories`, { params });
  return response.data.data;
}

export async function updateItemCategory(tenantId, categoryId, payload) {
  const response = await apiClient.put(`/tenants/${tenantId}/item-categories/${categoryId}`, payload);
  return response.data.data;
}

export async function deleteItemCategory(tenantId, categoryId) {
  const response = await apiClient.delete(`/tenants/${tenantId}/item-categories/${categoryId}`);
  return response.data.data;
}

export async function createItem(tenantId, payload) {
  const response = await apiClient.post(`/tenants/${tenantId}/items`, payload);
  return response.data.data;
}

export async function getItems(tenantId, params = {}) {
  const response = await apiClient.get(`/tenants/${tenantId}/items`, { params });
  return { items: response.data.data, meta: response.data.meta };
}

export async function getItem(tenantId, itemId) {
  const response = await apiClient.get(`/tenants/${tenantId}/items/${itemId}`);
  return response.data.data;
}

export async function updateItem(tenantId, itemId, payload) {
  const response = await apiClient.put(`/tenants/${tenantId}/items/${itemId}`, payload);
  return response.data.data;
}

export async function deleteItem(tenantId, itemId) {
  const response = await apiClient.delete(`/tenants/${tenantId}/items/${itemId}`);
  return response.data.data;
}

export async function uploadItemImage(tenantId, itemId, file) {
  const formData = new FormData();
  formData.append("file", file);
  const response = await apiClient.post(`/tenants/${tenantId}/items/${itemId}/images`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data.data;
}

export async function importItems(tenantId, file) {
  const formData = new FormData();
  formData.append("file", file);
  const response = await apiClient.post(`/tenants/${tenantId}/items/import`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data.data;
}

export function resolveUploadUrl(url) {
  if (!url) return "";
  if (url.startsWith("http")) return url;
  const apiBase = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api/v1";
  return `${apiBase.replace("/api/v1", "")}${url}`;
}
