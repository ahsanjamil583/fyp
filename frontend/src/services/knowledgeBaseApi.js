import { apiClient } from "./apiClient.js";

export async function getKnowledgeDocuments(tenantId, params = {}) {
  const response = await apiClient.get(`/tenants/${tenantId}/knowledge-base`, { params });
  return { items: response.data.data, meta: response.data.meta };
}

export async function getKnowledgeDocument(tenantId, documentId) {
  const response = await apiClient.get(`/tenants/${tenantId}/knowledge-base/${documentId}`);
  return response.data.data;
}

export async function createKnowledgeText(tenantId, payload) {
  const response = await apiClient.post(`/tenants/${tenantId}/knowledge-base/text`, payload);
  return response.data.data;
}

export async function uploadKnowledgeDocument(tenantId, { file, title = "", moduleCode = "ai_chat", tags = "", isActive = true }) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("title", title);
  formData.append("moduleCode", moduleCode);
  formData.append("tags", tags);
  formData.append("isActive", String(isActive));
  const response = await apiClient.post(`/tenants/${tenantId}/knowledge-base/upload`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data.data;
}

export async function updateKnowledgeDocument(tenantId, documentId, payload) {
  const response = await apiClient.put(`/tenants/${tenantId}/knowledge-base/${documentId}`, payload);
  return response.data.data;
}

export async function deleteKnowledgeDocument(tenantId, documentId) {
  const response = await apiClient.delete(`/tenants/${tenantId}/knowledge-base/${documentId}`);
  return response.data.data;
}

export async function reindexKnowledgeBase(tenantId) {
  const response = await apiClient.post(`/tenants/${tenantId}/knowledge-base/reindex`);
  return response.data.data;
}

export async function testKnowledgeBaseQuestion(tenantId, payload) {
  const response = await apiClient.post(`/tenants/${tenantId}/knowledge-base/test-question`, payload);
  return response.data.data;
}
