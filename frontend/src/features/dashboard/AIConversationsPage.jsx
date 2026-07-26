import { useEffect, useState } from "react";

import { useModules } from "../../context/ModuleContext.jsx";
import { useTenant } from "../../context/TenantContext.jsx";
import { getOwnerConversationDetail, getOwnerConversations, getTenantRagStatus, reindexTenantRag } from "../../services/aiConversationApi.js";

export function AIConversationsPage() {
  const { selectedTenant, isLoadingTenants } = useTenant();
  const { enabledModules } = useModules();
  const [conversationList, setConversationList] = useState([]);
  const [selectedConversationId, setSelectedConversationId] = useState("");
  const [detail, setDetail] = useState(null);
  const [ragStatus, setRagStatus] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isReindexing, setIsReindexing] = useState(false);
  const aiEnabled = enabledModules.includes("ai_chat");

  useEffect(() => {
    async function loadConversations() {
      if (!selectedTenant || !aiEnabled) {
        setConversationList([]);
        setSelectedConversationId("");
        setDetail(null);
        return;
      }
      setIsLoading(true);
      setError("");
      try {
        const data = await getOwnerConversations(selectedTenant.id);
        setConversationList(data.items || []);
        const nextId = data.items?.[0]?.id || "";
        setSelectedConversationId(nextId);
        const ragData = await getTenantRagStatus(selectedTenant.id);
        setRagStatus(ragData.rag || null);
      } catch (requestError) {
        setError(requestError.response?.data?.detail || "Unable to load AI conversations.");
      } finally {
        setIsLoading(false);
      }
    }

    loadConversations();
  }, [selectedTenant, aiEnabled]);

  useEffect(() => {
    async function loadDetail() {
      if (!selectedTenant || !selectedConversationId) {
        setDetail(null);
        return;
      }
      try {
        const data = await getOwnerConversationDetail(selectedTenant.id, selectedConversationId);
        setDetail(data);
      } catch (requestError) {
        setError(requestError.response?.data?.detail || "Unable to load conversation detail.");
      }
    }

    loadDetail();
  }, [selectedConversationId, selectedTenant]);

  async function handleReindex() {
    if (!selectedTenant) return;
    setIsReindexing(true);
    setError("");
    setNotice("");
    try {
      const data = await reindexTenantRag(selectedTenant.id);
      setRagStatus(data.rag || null);
      setNotice("RAG reindex completed successfully.");
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to reindex tenant knowledge.");
    } finally {
      setIsReindexing(false);
    }
  }

  if (isLoadingTenants) {
    return <section className="text-sm text-muted">Loading AI workspace...</section>;
  }

  if (!selectedTenant) {
    return <section className="text-sm text-muted">Select a business first to review AI conversations.</section>;
  }

  if (!aiEnabled) {
    return <section className="text-sm text-muted">Enable the AI chat module to review public and customer conversations.</section>;
  }

  return (
    <section className="grid gap-6 xl:grid-cols-[320px_minmax(0,1fr)]">
      <aside className="rounded-md border border-line bg-white p-5 shadow-sm">
        <div className="border-b border-line pb-3">
          <p className="text-sm font-semibold uppercase tracking-wide text-brand">AI Conversations</p>
          <h1 className="mt-2 text-2xl font-semibold text-ink">{selectedTenant.name}</h1>
        </div>
        {notice ? <div className="mt-4 rounded-md border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">{notice}</div> : null}
        {error ? <div className="mt-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}
        {isLoading ? <div className="mt-4 text-sm text-muted">Loading conversations...</div> : null}
        {ragStatus ? (
          <div className="mt-4 rounded-md border border-line bg-surface p-4 text-sm text-muted">
            <div className="font-semibold text-ink">RAG Status</div>
            <div className="mt-2">Documents: {ragStatus.knowledgeDocumentCount || 0}</div>
            <div>Active documents: {ragStatus.activeKnowledgeDocumentCount || 0}</div>
            <div>Chunks: {ragStatus.chunkCount || 0}</div>
            <div>Embedding: {ragStatus.embeddingProvider || "n/a"}</div>
            <button
              className="mt-3 w-full rounded-md border border-line px-3 py-2 text-sm font-semibold text-ink transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-60"
              onClick={handleReindex}
              type="button"
              disabled={isReindexing}
            >
              {isReindexing ? "Reindexing..." : "Reindex knowledge"}
            </button>
          </div>
        ) : null}
        <div className="mt-4 space-y-3">
          {conversationList.map((conversation) => (
            <button
              key={conversation.id}
              className={selectedConversationId === conversation.id ? "w-full rounded-md border border-brand bg-blue-50 px-4 py-3 text-left" : "w-full rounded-md border border-line px-4 py-3 text-left"}
              onClick={() => setSelectedConversationId(conversation.id)}
              type="button"
            >
              <div className="font-semibold text-ink">{conversation.channel}</div>
              <div className="mt-1 text-xs uppercase tracking-wide text-muted">{conversation.status}</div>
              <div className="mt-2 flex flex-wrap gap-2 text-[11px] uppercase tracking-wide text-muted">
                {conversation.languageDetected ? <span>{conversation.languageDetected}</span> : null}
                {conversation.lastIntent ? <span>{conversation.lastIntent.replaceAll("_", " ")}</span> : null}
                {conversation.lastAssistantSource ? <span>{conversation.lastAssistantSource}</span> : null}
              </div>
              <div className="mt-2 line-clamp-2 text-sm text-muted">{conversation.summary || "No summary yet."}</div>
            </button>
          ))}
          {!conversationList.length ? <div className="rounded-md border border-dashed border-line bg-surface p-4 text-sm text-muted">No AI conversations yet.</div> : null}
        </div>
      </aside>

      <div className="rounded-md border border-line bg-white p-5 shadow-sm">
        {detail?.conversation ? (
          <>
            <div className="flex flex-col gap-2 border-b border-line pb-4">
              <div className="text-sm font-semibold uppercase tracking-wide text-brand">{detail.conversation.channel}</div>
              <div className="text-sm text-muted">Last activity: {detail.conversation.lastMessageAt ? new Date(detail.conversation.lastMessageAt).toLocaleString() : "n/a"}</div>
              <div className="flex flex-wrap gap-2 pt-2 text-xs text-muted">
                {detail.conversation.languageDetected ? <span className="rounded-full bg-surface px-2 py-1">{detail.conversation.languageDetected}</span> : null}
                {detail.conversation.lastIntent ? <span className="rounded-full bg-surface px-2 py-1">Intent: {detail.conversation.lastIntent.replaceAll("_", " ")}</span> : null}
                {detail.conversation.lastIntentConfidence ? <span className="rounded-full bg-surface px-2 py-1">Confidence: {detail.conversation.lastIntentConfidence}</span> : null}
                {detail.conversation.lastAssistantSource ? <span className="rounded-full bg-surface px-2 py-1">Provider: {detail.conversation.lastAssistantSource}</span> : null}
                <span className="rounded-full bg-surface px-2 py-1">Knowledge: {detail.conversation.lastKnowledgeCount || 0}</span>
                {detail.conversation.lastLocalizationScore ? <span className="rounded-full bg-surface px-2 py-1">Localization: {detail.conversation.lastLocalizationScore}</span> : null}
              </div>
            </div>
            <div className="mt-4 space-y-3">
              {(detail.messages || []).map((message) => (
                <div key={message.id} className="rounded-md border border-line p-4">
                  <div className="flex items-center justify-between gap-4">
                    <div className="font-semibold capitalize text-ink">{message.sender}</div>
                    <div className="text-xs text-muted">{new Date(message.createdAt).toLocaleString()}</div>
                  </div>
                  <div className="mt-2 text-sm leading-6 text-ink">{message.messageText}</div>
                  <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted">
                    {message.intent ? <span className="rounded-full bg-surface px-2 py-1">Intent: {message.intent.replaceAll("_", " ")}</span> : null}
                    {message.confidence ? <span className="rounded-full bg-surface px-2 py-1">Confidence: {message.confidence}</span> : null}
                  </div>
                  {message.ragSources?.length ? (
                    <div className="mt-3 text-xs text-muted">
                      Sources: {message.ragSources.map((source) => source.title).filter(Boolean).join(", ")}
                    </div>
                  ) : null}
                  {message.toolCalls?.length ? (
                    <div className="mt-3 rounded-md bg-surface p-3 text-xs text-muted">
                      {message.toolCalls.map((toolCall, index) => (
                        <div key={`${message.id}-tool-${index}`}>
                          {Object.entries(toolCall).map(([key, value]) => `${key}: ${String(value)}`).join(" | ")}
                        </div>
                      ))}
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          </>
        ) : (
          <div className="text-sm text-muted">Select a conversation to review its messages.</div>
        )}
      </div>
    </section>
  );
}
