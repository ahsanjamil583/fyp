import { useEffect, useState } from "react";

import { useModules } from "../../context/ModuleContext.jsx";
import { useTenant } from "../../context/TenantContext.jsx";
import { getUserFacingSourceTitles, humanizeInternalName, isDebugMode } from "../../utils/displaySafety.js";
import { getAgentTools, previewAgentRun } from "../../services/agentApi.js";
import { SectionTitle } from "../../components/ui/SectionTitle.jsx";

function ToolEventCard({ event }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-3 text-sm">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="font-semibold text-ink">{humanizeInternalName(event.tool) || "Step"}</div>
          <div className="mt-1 text-muted">{event.summary}</div>
        </div>
        <span className={event.status === "success" ? "rounded-full bg-green-50 px-2 py-1 text-xs font-semibold text-green-700" : "rounded-full bg-red-50 px-2 py-1 text-xs font-semibold text-red-700"}>
          {event.status || "success"}
        </span>
      </div>
      {/* Raw tool output is a developer aid, not owner-facing information. */}
      {isDebugMode && event.output ? (
        <pre className="mt-3 max-h-44 overflow-auto rounded bg-white p-3 text-xs text-muted">{JSON.stringify(event.output, null, 2)}</pre>
      ) : null}
    </div>
  );
}

export function AgentToolsPage() {
  const { selectedTenant, isLoadingTenants } = useTenant();
  const { enabledModules, isLoadingModules } = useModules();
  const [catalog, setCatalog] = useState(null);
  const [messageText, setMessageText] = useState("2 black shirts order kar do");
  const [channel, setChannel] = useState("owner_preview");
  const [preview, setPreview] = useState(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isPreviewing, setIsPreviewing] = useState(false);

  const aiEnabled = enabledModules.includes("ai_chat");
  const previewSourceTitles = getUserFacingSourceTitles(preview?.ragSources || []);

  async function loadCatalog() {
    if (!selectedTenant || !aiEnabled) {
      setCatalog(null);
      return;
    }
    setIsLoading(true);
    setError("");
    try {
      const data = await getAgentTools(selectedTenant.id);
      setCatalog(data);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to load agent tool catalog.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    loadCatalog().catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedTenant?.id, aiEnabled]);

  async function handlePreview(event) {
    event.preventDefault();
    if (!selectedTenant) return;
    setIsPreviewing(true);
    setPreview(null);
    setError("");
    setNotice("");
    try {
      const data = await previewAgentRun(selectedTenant.id, { messageText, channel });
      setPreview(data);
      setNotice("Agent preview completed. This did not save a customer message or place an order.");
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to run agent preview.");
    } finally {
      setIsPreviewing(false);
    }
  }

  if (isLoadingTenants || isLoadingModules) {
    return <section className="text-sm text-muted">Loading agent workspace...</section>;
  }

  if (!selectedTenant) {
    return <section className="text-sm text-muted">Select a business first to inspect its agent tools.</section>;
  }

  if (!aiEnabled) {
    return <section className="text-sm text-muted">Enable AI Chat before using the Phase 23 Agent Tool Layer.</section>;
  }

  return (
    <section className="space-y-6">
      <div className="rounded-xl border border-line bg-white p-5 shadow-card">
        <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-brand">Phase 23</p>
        <h1 className="mt-1.5 text-2xl font-extrabold tracking-tight text-ink">Real Agent Tool Layer</h1>
        <p className="mt-3 max-w-4xl text-sm leading-6 text-muted">
          This layer separates the assistant into clear agents and tools: language detection, safety, catalog search, intent classification, RAG retrieval, draft order planning, response generation, and localization. Customer Portal, Public Chat, and WhatsApp now use the same orchestrated brain.
        </p>
      </div>

      {notice ? <div className="rounded-xl border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">{notice}</div> : null}
      {error ? <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}
      {isLoading ? <div className="text-sm text-muted">Loading tool catalog...</div> : null}

      <div className="grid gap-6 xl:grid-cols-[0.8fr_1.2fr]">
        <div className="space-y-4 rounded-xl border border-line bg-white p-5 shadow-card">
          <div>
            <SectionTitle>Available tools</SectionTitle>
            <p className="mt-1 text-sm text-muted">These tools run in sequence through the orchestrator.</p>
          </div>
          <div className="space-y-3">
            {(catalog?.tools || []).map((tool) => (
              <div key={`${tool.agent}-${tool.tool}`} className="rounded-xl border border-line p-3">
                <div className="text-sm font-semibold text-ink">{humanizeInternalName(tool.tool)}</div>
                {isDebugMode ? <div className="mt-1 text-xs font-medium text-muted">{tool.agent}</div> : null}
                <p className="mt-2 text-sm leading-5 text-muted">{tool.purpose}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="space-y-5">
          <form onSubmit={handlePreview} className="space-y-4 rounded-xl border border-line bg-white p-5 shadow-card">
            <div>
              <SectionTitle>Preview agent run</SectionTitle>
              <p className="mt-1 text-sm text-muted">Test the brain without saving a conversation or creating a real order.</p>
            </div>
            <label className="text-sm font-medium text-ink">
              Channel
              <select className="mt-1 w-full rounded-xl border border-line px-3 py-2 text-sm" value={channel} onChange={(event) => setChannel(event.target.value)}>
                <option value="owner_preview">Owner Preview</option>
                <option value="customer_portal">Customer Portal</option>
                <option value="website">Public Website</option>
                <option value="whatsapp">WhatsApp</option>
              </select>
            </label>
            <label className="text-sm font-medium text-ink">
              Customer message
              <textarea className="mt-1 min-h-28 w-full rounded-xl border border-line px-3 py-2 text-sm" value={messageText} onChange={(event) => setMessageText(event.target.value)} placeholder="Example: black hoodie chahiye, order kar do" />
            </label>
            <button type="submit" disabled={isPreviewing || !messageText.trim()} className="rounded-xl bg-brand px-4 py-2 text-sm font-semibold text-white disabled:opacity-60">
              {isPreviewing ? "Running agent..." : "Run preview"}
            </button>
          </form>

          {preview ? (
            <div className="space-y-5">
              <div className="rounded-xl border border-line bg-white p-5 shadow-card">
                <SectionTitle>Agent reply</SectionTitle>
                <p className="mt-3 whitespace-pre-line text-sm leading-6 text-muted">{preview.reply}</p>
                <div className="mt-4 grid gap-3 md:grid-cols-3">
                  <div className="rounded-xl bg-surface p-3 text-sm"><span className="font-semibold text-ink">Intent:</span> {preview.meta?.intent}</div>
                  <div className="rounded-xl bg-surface p-3 text-sm"><span className="font-semibold text-ink">Source:</span> {preview.meta?.responseSource}</div>
                  <div className="rounded-xl bg-surface p-3 text-sm"><span className="font-semibold text-ink">Language:</span> {preview.meta?.languageMode}</div>
                </div>
              </div>

              {preview.draftOrder?.items?.length ? (
                <div className="rounded-xl border border-amber-200 bg-amber-50 p-5 shadow-card">
                  <h2 className="text-lg font-semibold text-amber-900">Draft order prepared</h2>
                  {isDebugMode ? (
                    <pre className="mt-3 max-h-64 overflow-auto rounded bg-white p-3 text-xs text-amber-900">{JSON.stringify(preview.draftOrder, null, 2)}</pre>
                  ) : null}
                </div>
              ) : null}

              {/* Internal agent/tool names, summaries and timings are developer output. */}
              {isDebugMode ? (
                <div className="rounded-xl border border-line bg-white p-5 shadow-card">
                  <SectionTitle>Tool trace</SectionTitle>
                  <div className="mt-4 space-y-3">
                    {(preview.toolCalls || []).map((event, index) => (
                      <ToolEventCard key={`${event.tool}-${index}`} event={event} />
                    ))}
                  </div>
                </div>
              ) : null}

              {previewSourceTitles.length || (isDebugMode && preview.ragSources?.length) ? (
                <div className="rounded-xl border border-line bg-white p-5 shadow-card">
                  <SectionTitle>{isDebugMode ? "RAG sources" : "Knowledge used"}</SectionTitle>
                  <div className="mt-4 space-y-3">
                    {isDebugMode
                      ? preview.ragSources.map((source, index) => (
                          <div key={`${source.documentId}-${index}`} className="rounded-xl border border-line p-3 text-sm">
                            <div className="font-semibold text-ink">{source.title || "Knowledge"}</div>
                            <div className="mt-1 text-xs text-muted">{source.sourceType} / confidence {source.confidence}</div>
                            <p className="mt-2 text-muted">{source.excerpt}</p>
                          </div>
                        ))
                      : previewSourceTitles.map((title) => (
                          <div key={title} className="rounded-xl border border-line p-3 text-sm font-semibold text-ink">
                            {title}
                          </div>
                        ))}
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}
