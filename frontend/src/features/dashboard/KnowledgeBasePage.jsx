import { useEffect, useMemo, useState } from "react";

import { useModules } from "../../context/ModuleContext.jsx";
import { useTenant } from "../../context/TenantContext.jsx";
import {
  createKnowledgeText,
  deleteKnowledgeDocument,
  getKnowledgeDocument,
  getKnowledgeDocuments,
  reindexKnowledgeBase,
  testKnowledgeBaseQuestion,
  updateKnowledgeDocument,
  uploadKnowledgeDocument,
} from "../../services/knowledgeBaseApi.js";

const sourceLabels = {
  owner_text: "Owner text",
  owner_upload: "Owner upload",
  item: "Catalog item",
  tenant_profile: "Business profile",
};

function sourceLabel(sourceType) {
  return sourceLabels[sourceType] || sourceType?.replaceAll("_", " ") || "Knowledge";
}

function isOwnerDocument(document) {
  return ["owner_text", "owner_upload"].includes(document?.sourceType);
}

function normalizeTagsInput(value) {
  return String(value || "")
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean);
}

export function KnowledgeBasePage() {
  const { selectedTenant, isLoadingTenants } = useTenant();
  const { enabledModules, isLoadingModules } = useModules();
  const [documents, setDocuments] = useState([]);
  const [meta, setMeta] = useState({});
  const [search, setSearch] = useState("");
  const [sourceType, setSourceType] = useState("");
  const [selectedDocumentId, setSelectedDocumentId] = useState("");
  const [selectedDocument, setSelectedDocument] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isSavingText, setIsSavingText] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false);
  const [isReindexing, setIsReindexing] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [textForm, setTextForm] = useState({ title: "", tags: "", content: "", isActive: true });
  const [uploadForm, setUploadForm] = useState({ title: "", tags: "", isActive: true, file: null });
  const [editForm, setEditForm] = useState({ title: "", tags: "", content: "", isActive: true });
  const [testForm, setTestForm] = useState({ question: "" });
  const [testResult, setTestResult] = useState(null);

  const aiEnabled = enabledModules.includes("ai_chat");
  const summary = meta.summary || {};
  const pagination = meta || {};

  const filteredSourceOptions = useMemo(
    () => [
      { value: "", label: "All sources" },
      { value: "owner_text", label: "Owner text" },
      { value: "owner_upload", label: "Owner uploads" },
      { value: "item", label: "Catalog items" },
      { value: "tenant_profile", label: "Business profile" },
    ],
    [],
  );

  async function loadDocuments(nextSelectedId = selectedDocumentId) {
    if (!selectedTenant || !aiEnabled) {
      setDocuments([]);
      setSelectedDocumentId("");
      setSelectedDocument(null);
      return;
    }
    setIsLoading(true);
    setError("");
    try {
      const data = await getKnowledgeDocuments(selectedTenant.id, {
        search,
        sourceType: sourceType || undefined,
        page: 1,
        limit: 50,
      });
      setDocuments(data.items || []);
      setMeta(data.meta || {});
      const firstId = data.items?.[0]?.id || "";
      const stillExists = data.items?.some((document) => document.id === nextSelectedId);
      setSelectedDocumentId(stillExists ? nextSelectedId : firstId);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to load knowledge base.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    loadDocuments("").catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedTenant?.id, aiEnabled, sourceType]);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      loadDocuments(selectedDocumentId).catch(() => {});
    }, 350);
    return () => window.clearTimeout(timeoutId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  useEffect(() => {
    async function loadDetail() {
      if (!selectedTenant || !selectedDocumentId) {
        setSelectedDocument(null);
        return;
      }
      try {
        const data = await getKnowledgeDocument(selectedTenant.id, selectedDocumentId);
        const document = data.document;
        setSelectedDocument(document);
        setEditForm({
          title: document.title || "",
          tags: (document.tags || []).join(", "),
          content: document.content || "",
          isActive: Boolean(document.isActive),
        });
      } catch (requestError) {
        setError(requestError.response?.data?.detail || "Unable to load knowledge document.");
      }
    }
    loadDetail();
  }, [selectedDocumentId, selectedTenant]);

  async function handleCreateText(event) {
    event.preventDefault();
    if (!selectedTenant) return;
    setIsSavingText(true);
    setError("");
    setNotice("");
    try {
      const data = await createKnowledgeText(selectedTenant.id, {
        title: textForm.title,
        content: textForm.content,
        moduleCode: "ai_chat",
        tags: normalizeTagsInput(textForm.tags),
        isActive: textForm.isActive,
      });
      setTextForm({ title: "", tags: "", content: "", isActive: true });
      setNotice("Text knowledge saved and indexed successfully.");
      await loadDocuments(data.document?.id || "");
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to save text knowledge.");
    } finally {
      setIsSavingText(false);
    }
  }

  async function handleUpload(event) {
    event.preventDefault();
    if (!selectedTenant) return;
    if (!uploadForm.file) {
      setError("Choose a TXT, PDF, DOCX, CSV, or Excel file first.");
      return;
    }
    setIsUploading(true);
    setError("");
    setNotice("");
    try {
      const data = await uploadKnowledgeDocument(selectedTenant.id, {
        file: uploadForm.file,
        title: uploadForm.title,
        moduleCode: "ai_chat",
        tags: uploadForm.tags,
        isActive: uploadForm.isActive,
      });
      setUploadForm({ title: "", tags: "", isActive: true, file: null });
      const fileInput = document.getElementById("knowledge-upload-file");
      if (fileInput) fileInput.value = "";
      setNotice("File uploaded, text extracted, and RAG indexed successfully.");
      await loadDocuments(data.document?.id || "");
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to upload knowledge document.");
    } finally {
      setIsUploading(false);
    }
  }

  async function handleUpdate(event) {
    event.preventDefault();
    if (!selectedTenant || !selectedDocument || !isOwnerDocument(selectedDocument)) return;
    setIsUpdating(true);
    setError("");
    setNotice("");
    try {
      const data = await updateKnowledgeDocument(selectedTenant.id, selectedDocument.id, {
        title: editForm.title,
        content: editForm.content,
        moduleCode: selectedDocument.moduleCode || "ai_chat",
        tags: normalizeTagsInput(editForm.tags),
        isActive: editForm.isActive,
      });
      setSelectedDocument(data.document);
      setNotice("Knowledge document updated and reindexed successfully.");
      await loadDocuments(data.document?.id || selectedDocument.id);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to update knowledge document.");
    } finally {
      setIsUpdating(false);
    }
  }

  async function handleDelete() {
    if (!selectedTenant || !selectedDocument || !isOwnerDocument(selectedDocument)) return;
    const confirmed = window.confirm("Delete this knowledge document from RAG? This cannot be undone.");
    if (!confirmed) return;
    setError("");
    setNotice("");
    try {
      await deleteKnowledgeDocument(selectedTenant.id, selectedDocument.id);
      setSelectedDocument(null);
      setSelectedDocumentId("");
      setNotice("Knowledge document deleted successfully.");
      await loadDocuments("");
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to delete knowledge document.");
    }
  }

  async function handleReindex() {
    if (!selectedTenant) return;
    setIsReindexing(true);
    setError("");
    setNotice("");
    try {
      await reindexKnowledgeBase(selectedTenant.id);
      setNotice("Full knowledge base reindex completed successfully.");
      await loadDocuments(selectedDocumentId);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to reindex knowledge base.");
    } finally {
      setIsReindexing(false);
    }
  }

  async function handleTestQuestion(event) {
    event.preventDefault();
    if (!selectedTenant || !testForm.question.trim()) return;
    setIsTesting(true);
    setError("");
    setNotice("");
    try {
      const data = await testKnowledgeBaseQuestion(selectedTenant.id, {
        question: testForm.question.trim(),
        channel: "owner_preview",
      });
      setTestResult(data);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to test this knowledge question.");
    } finally {
      setIsTesting(false);
    }
  }

  if (isLoadingTenants || isLoadingModules) {
    return <section className="text-sm text-muted">Loading knowledge base workspace...</section>;
  }

  if (!selectedTenant) {
    return <section className="text-sm text-muted">Select a business first to manage its knowledge base.</section>;
  }

  if (!aiEnabled) {
    return <section className="text-sm text-muted">Enable the AI Chat module before uploading business knowledge into RAG.</section>;
  }

  return (
    <section className="space-y-6">
      <div className="rounded-md border border-line bg-white p-5 shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="text-sm font-semibold uppercase tracking-wide text-brand">Phase 21</p>
            <h1 className="mt-2 text-3xl font-semibold text-ink">Knowledge Base Manager</h1>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-muted">
              Upload policies, FAQs, menus, size guides, service rules, delivery details, and business instructions. BizXus AI will index this content into RAG and use it when answering customers.
            </p>
          </div>
          <button
            className="rounded-md border border-line px-4 py-2 text-sm font-semibold text-ink transition hover:bg-surface disabled:cursor-not-allowed disabled:opacity-60"
            disabled={isReindexing}
            onClick={handleReindex}
            type="button"
          >
            {isReindexing ? "Reindexing..." : "Reindex all knowledge"}
          </button>
        </div>
        {notice ? <div className="mt-4 rounded-md border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">{notice}</div> : null}
        {error ? <div className="mt-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}
        <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Stat label="Total documents" value={pagination.total || 0} />
          <Stat label="Owner uploads" value={summary.ownerUploadCount || 0} />
          <Stat label="Owner text docs" value={summary.ownerTextCount || 0} />
          <Stat label="System docs" value={summary.systemDocumentCount || 0} />
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <form className="rounded-md border border-line bg-white p-5 shadow-sm" onSubmit={handleCreateText}>
          <h2 className="text-lg font-semibold text-ink">Add text knowledge</h2>
          <p className="mt-1 text-sm text-muted">Use this for FAQs, delivery policies, refund rules, or business instructions.</p>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <label className="block">
              <span className="mb-1.5 block text-sm font-medium text-ink">Title</span>
              <input className="form-input" required value={textForm.title} onChange={(event) => setTextForm((form) => ({ ...form, title: event.target.value }))} placeholder="Delivery policy" />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-sm font-medium text-ink">Tags</span>
              <input className="form-input" value={textForm.tags} onChange={(event) => setTextForm((form) => ({ ...form, tags: event.target.value }))} placeholder="delivery, faq, policy" />
            </label>
          </div>
          <label className="mt-4 block">
            <span className="mb-1.5 block text-sm font-medium text-ink">Content</span>
            <textarea className="form-input min-h-44" required value={textForm.content} onChange={(event) => setTextForm((form) => ({ ...form, content: event.target.value }))} placeholder="Write the exact knowledge that the AI should use..." />
          </label>
          <label className="mt-4 flex items-center gap-2 text-sm text-muted">
            <input checked={textForm.isActive} type="checkbox" onChange={(event) => setTextForm((form) => ({ ...form, isActive: event.target.checked }))} />
            Active in AI/RAG
          </label>
          <button className="mt-4 rounded-md bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60" disabled={isSavingText} type="submit">
            {isSavingText ? "Saving..." : "Save and index"}
          </button>
        </form>

        <form className="rounded-md border border-line bg-white p-5 shadow-sm" onSubmit={handleUpload}>
          <h2 className="text-lg font-semibold text-ink">Upload knowledge file</h2>
          <p className="mt-1 text-sm text-muted">Supported formats: TXT, MD, CSV, XLSX, PDF, and DOCX. Files must be 10MB or smaller.</p>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <label className="block">
              <span className="mb-1.5 block text-sm font-medium text-ink">Optional title</span>
              <input className="form-input" value={uploadForm.title} onChange={(event) => setUploadForm((form) => ({ ...form, title: event.target.value }))} placeholder="Menu details" />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-sm font-medium text-ink">Tags</span>
              <input className="form-input" value={uploadForm.tags} onChange={(event) => setUploadForm((form) => ({ ...form, tags: event.target.value }))} placeholder="menu, prices, sizes" />
            </label>
          </div>
          <label className="mt-4 block">
            <span className="mb-1.5 block text-sm font-medium text-ink">File</span>
            <input
              id="knowledge-upload-file"
              className="form-input"
              accept=".txt,.md,.csv,.xlsx,.xlsm,.pdf,.docx"
              required
              type="file"
              onChange={(event) => {
                const file = event.target.files?.[0] || null;
                setUploadForm((form) => ({ ...form, file, title: form.title || (file ? file.name.replace(/\.[^.]+$/, "") : "") }));
                setError("");
              }}
            />
            <div className="mt-2 text-xs text-muted">
              {uploadForm.file ? `Selected: ${uploadForm.file.name} (${Math.ceil(uploadForm.file.size / 1024)} KB)` : "No file selected yet."}
            </div>
          </label>
          <label className="mt-4 flex items-center gap-2 text-sm text-muted">
            <input checked={uploadForm.isActive} type="checkbox" onChange={(event) => setUploadForm((form) => ({ ...form, isActive: event.target.checked }))} />
            Active in AI/RAG
          </label>
          <button className="mt-4 rounded-md bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60" disabled={isUploading || !uploadForm.file} type="submit">
            {isUploading ? "Uploading..." : uploadForm.file ? "Upload and index" : "Choose a file first"}
          </button>
        </form>
      </div>

      <form className="rounded-md border border-line bg-white p-5 shadow-sm" onSubmit={handleTestQuestion}>
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <h2 className="text-lg font-semibold text-ink">Ask a test question from this knowledge base</h2>
            <p className="mt-1 max-w-3xl text-sm leading-6 text-muted">
              Preview how BizXus AI will answer using this business&apos;s RAG, catalog, category, and order tools. Sources and tool trace are visible only here for owner debugging.
            </p>
          </div>
          <button className="rounded-md bg-ink px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60" disabled={isTesting || !testForm.question.trim()} type="submit">
            {isTesting ? "Testing..." : "Test answer"}
          </button>
        </div>
        <textarea
          className="form-input mt-4 min-h-24"
          value={testForm.question}
          onChange={(event) => setTestForm({ question: event.target.value })}
          placeholder="Example: Delivery Wah Cantt mein hoti hai? Return policy kya hai?"
        />
        {testResult ? (
          <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
            <div className="rounded-md border border-blue-100 bg-blue-50 p-4">
              <div className="text-xs font-semibold uppercase tracking-wide text-brand">AI answer preview</div>
              <div className="mt-2 whitespace-pre-wrap text-sm leading-6 text-ink">{testResult.reply || "No answer generated."}</div>
              <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted">
                <span className="rounded-full bg-white px-2 py-1">Intent: {testResult.meta?.intent || "general_info"}</span>
                <span className="rounded-full bg-white px-2 py-1">Knowledge: {testResult.meta?.knowledgeCount || 0}</span>
                <span className="rounded-full bg-white px-2 py-1">Source: {testResult.meta?.responseSource || "preview"}</span>
              </div>
            </div>
            <div className="space-y-3">
              <div className="rounded-md border border-line p-3">
                <div className="text-sm font-semibold text-ink">Top RAG sources</div>
                <div className="mt-2 space-y-2">
                  {(testResult.ragSources || []).slice(0, 3).map((source) => (
                    <div className="rounded-md bg-surface p-2 text-xs text-muted" key={`${source.documentId}-${source.excerpt}`}>
                      <div className="font-semibold text-ink">{source.title || "Knowledge"}</div>
                      <div>{source.matchType || "source"} | score {source.confidence || 0}</div>
                      <div className="mt-1 line-clamp-2">{source.excerpt}</div>
                    </div>
                  ))}
                  {!testResult.ragSources?.length ? <div className="text-xs text-muted">No RAG source matched this question.</div> : null}
                </div>
              </div>
              <div className="rounded-md border border-line p-3">
                <div className="text-sm font-semibold text-ink">Tool trace</div>
                <div className="mt-2 max-h-44 space-y-1 overflow-auto text-xs text-muted">
                  {(testResult.toolCalls || []).map((tool) => (
                    <div className="rounded bg-surface px-2 py-1" key={`${tool.agent}-${tool.tool}`}>
                      {tool.tool}: {tool.status}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        ) : null}
      </form>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
        <div className="rounded-md border border-line bg-white p-5 shadow-sm">
          <div className="flex flex-col gap-3 border-b border-line pb-4 md:flex-row md:items-center md:justify-between">
            <div>
              <h2 className="text-lg font-semibold text-ink">Indexed knowledge</h2>
              <p className="mt-1 text-sm text-muted">Owner uploads and system-generated catalog/business documents used by RAG.</p>
            </div>
            <div className="flex flex-col gap-2 sm:flex-row">
              <input className="form-input sm:w-64" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search knowledge..." />
              <select className="form-input sm:w-48" value={sourceType} onChange={(event) => setSourceType(event.target.value)}>
                {filteredSourceOptions.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </div>
          </div>
          {isLoading ? <div className="mt-4 text-sm text-muted">Loading documents...</div> : null}
          <div className="mt-4 space-y-3">
            {documents.map((document) => (
              <button
                className={selectedDocumentId === document.id ? "w-full rounded-md border border-brand bg-blue-50 p-4 text-left" : "w-full rounded-md border border-line p-4 text-left transition hover:bg-surface"}
                key={document.id}
                onClick={() => setSelectedDocumentId(document.id)}
                type="button"
              >
                <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
                  <div>
                    <div className="font-semibold text-ink">{document.title}</div>
                    <div className="mt-1 line-clamp-2 text-sm leading-6 text-muted">{document.contentPreview || "No preview available."}</div>
                  </div>
                  <div className="flex flex-wrap gap-2 text-xs text-muted md:justify-end">
                    <span className="rounded-full bg-surface px-2 py-1 capitalize">{sourceLabel(document.sourceType)}</span>
                    <span className={document.isActive ? "rounded-full bg-green-50 px-2 py-1 text-green-700" : "rounded-full bg-surface px-2 py-1"}>{document.isActive ? "Active" : "Inactive"}</span>
                    <span className="rounded-full bg-surface px-2 py-1">{document.chunkCount || 0} chunks</span>
                  </div>
                </div>
              </button>
            ))}
            {!documents.length && !isLoading ? <div className="rounded-md border border-dashed border-line bg-surface p-5 text-sm text-muted">No knowledge documents found.</div> : null}
          </div>
        </div>

        <aside className="rounded-md border border-line bg-white p-5 shadow-sm">
          {selectedDocument ? (
            <form onSubmit={handleUpdate}>
              <div className="border-b border-line pb-4">
                <p className="text-sm font-semibold uppercase tracking-wide text-brand">Document detail</p>
                <h2 className="mt-2 text-xl font-semibold text-ink">{selectedDocument.title}</h2>
                <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted">
                  <span className="rounded-full bg-surface px-2 py-1 capitalize">{sourceLabel(selectedDocument.sourceType)}</span>
                  <span className="rounded-full bg-surface px-2 py-1">{selectedDocument.chunkCount || 0} chunks</span>
                  <span className="rounded-full bg-surface px-2 py-1">{selectedDocument.embeddingProvider || "none"}</span>
                </div>
              </div>

              {isOwnerDocument(selectedDocument) ? (
                <>
                  <label className="mt-4 block">
                    <span className="mb-1.5 block text-sm font-medium text-ink">Title</span>
                    <input className="form-input" required value={editForm.title} onChange={(event) => setEditForm((form) => ({ ...form, title: event.target.value }))} />
                  </label>
                  <label className="mt-4 block">
                    <span className="mb-1.5 block text-sm font-medium text-ink">Tags</span>
                    <input className="form-input" value={editForm.tags} onChange={(event) => setEditForm((form) => ({ ...form, tags: event.target.value }))} />
                  </label>
                  <label className="mt-4 block">
                    <span className="mb-1.5 block text-sm font-medium text-ink">Content used by RAG</span>
                    <textarea className="form-input min-h-72" required value={editForm.content} onChange={(event) => setEditForm((form) => ({ ...form, content: event.target.value }))} />
                  </label>
                  <label className="mt-4 flex items-center gap-2 text-sm text-muted">
                    <input checked={editForm.isActive} type="checkbox" onChange={(event) => setEditForm((form) => ({ ...form, isActive: event.target.checked }))} />
                    Active in AI/RAG
                  </label>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <button className="rounded-md bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60" disabled={isUpdating} type="submit">
                      {isUpdating ? "Updating..." : "Update and reindex"}
                    </button>
                    <button className="rounded-md border border-red-200 px-4 py-2 text-sm font-semibold text-red-700 hover:bg-red-50" onClick={handleDelete} type="button">
                      Delete
                    </button>
                  </div>
                </>
              ) : (
                <div className="mt-4 space-y-4">
                  <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-700">
                    This is system-generated knowledge. Update the original business profile, website FAQ, or catalog item and then reindex.
                  </div>
                  <div className="max-h-[520px] overflow-auto whitespace-pre-wrap rounded-md border border-line bg-surface p-4 text-sm leading-6 text-muted">
                    {selectedDocument.content || "No content available."}
                  </div>
                </div>
              )}
            </form>
          ) : (
            <div className="text-sm text-muted">Select a knowledge document to view or edit it.</div>
          )}
        </aside>
      </div>
    </section>
  );
}

function Stat({ label, value }) {
  return (
    <div className="rounded-md border border-line bg-surface p-4">
      <div className="text-sm text-muted">{label}</div>
      <div className="mt-2 text-2xl font-semibold text-ink">{value}</div>
    </div>
  );
}
