import { useEffect, useMemo, useState } from "react";

import { useModules } from "../../context/ModuleContext.jsx";
import { useTenant } from "../../context/TenantContext.jsx";
import { getOwnerAgentHistory, getOwnerAgentInsights, sendOwnerAgentMessage } from "../../services/ownerAgentApi.js";

const quickPrompts = [
  "Summarize today's business performance",
  "Which items are low stock?",
  "Show pending orders",
  "Which items are selling best?",
  "Give me promotion ideas",
  "What is my payment status?",
  "Summarize customer chats",
];

function formatDate(value) {
  if (!value) return "";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return "";
  }
}

export function OwnerAgentPage() {
  const { selectedTenant, isLoadingTenants } = useTenant();
  const { enabledModules, isLoadingModules } = useModules();
  const [insights, setInsights] = useState(null);
  const [history, setHistory] = useState([]);
  const [messageText, setMessageText] = useState("Summarize today's business performance");
  const [lastContext, setLastContext] = useState(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isSending, setIsSending] = useState(false);

  const ownerAgentEnabled = enabledModules.includes("owner_agent");
  const analyticsEnabled = enabledModules.includes("analytics");
  const reportsEnabled = enabledModules.includes("reports");

  async function loadWorkspace() {
    if (!selectedTenant?.id || !ownerAgentEnabled) {
      setInsights(null);
      setHistory([]);
      return;
    }
    setIsLoading(true);
    setError("");
    try {
      const [insightData, historyData] = await Promise.all([
        getOwnerAgentInsights(selectedTenant.id),
        getOwnerAgentHistory(selectedTenant.id, { limit: 40 }),
      ]);
      setInsights(insightData);
      setHistory(historyData.items || []);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to load owner assistant workspace.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    loadWorkspace().catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedTenant?.id, ownerAgentEnabled]);

  async function handleSubmit(event) {
    event.preventDefault();
    if (!selectedTenant?.id || !messageText.trim()) return;
    const outgoing = messageText.trim();
    setIsSending(true);
    setError("");
    setNotice("");
    setHistory((current) => [
      ...current,
      { id: `local-${Date.now()}`, sender: "owner", messageText: outgoing, createdAt: new Date().toISOString() },
    ]);
    setMessageText("");
    try {
      const data = await sendOwnerAgentMessage(selectedTenant.id, { messageText: outgoing, includeHistory: true });
      setHistory(data.history || []);
      setLastContext(data);
      setNotice(`Owner assistant used ${data.intent?.replaceAll("_", " ") || "business"} tools.`);
      const insightData = await getOwnerAgentInsights(selectedTenant.id);
      setInsights(insightData);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to get an owner assistant reply.");
    } finally {
      setIsSending(false);
    }
  }

  const visibleHistory = useMemo(() => history.slice(-20), [history]);

  if (isLoadingTenants || isLoadingModules) {
    return <section className="text-sm text-muted">Loading owner assistant...</section>;
  }

  if (!selectedTenant) {
    return <section className="text-sm text-muted">Select a business first to use the owner-side AI assistant.</section>;
  }

  if (!ownerAgentEnabled) {
    return <section className="text-sm text-muted">Enable the Owner AI Assistant module first. It depends on AI Chat, Analytics, Reports, and Notifications.</section>;
  }

  if (!analyticsEnabled || !reportsEnabled) {
    return <section className="text-sm text-muted">Enable Analytics and Reports to give the owner assistant enough business data.</section>;
  }

  return (
    <section className="space-y-6">
      <div className="rounded-md border border-line bg-white p-5 shadow-sm">
        <p className="text-sm font-semibold uppercase tracking-wide text-brand">Phase 26</p>
        <h1 className="mt-2 text-3xl font-semibold text-ink">Owner AI Assistant</h1>
        <p className="mt-3 max-w-4xl text-sm leading-6 text-muted">
          Ask business questions like “What sold the most today?”, “Which items are low stock?”, “Show pending orders”, “Summarize customer chats”, or “Create promotion ideas”. The assistant reads analytics, transactions, stock, payments, notifications, reports, and conversations.
        </p>
      </div>

      {notice ? <div className="rounded-md border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">{notice}</div> : null}
      {error ? <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}
      {isLoading ? <div className="text-sm text-muted">Loading assistant insights...</div> : null}

      {insights ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {(insights.cards || []).map((card) => (
            <div key={card.label} className="rounded-md border border-line bg-white p-4 shadow-sm">
              <div className="text-sm text-muted">{card.label}</div>
              <div className="mt-2 text-2xl font-semibold text-ink">{card.value}</div>
              <div className="mt-1 text-xs text-muted">{card.hint}</div>
            </div>
          ))}
        </div>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
        <div className="space-y-6">
          <div className="rounded-md border border-line bg-white p-5 shadow-sm">
            <h2 className="text-lg font-semibold text-ink">Recommended actions</h2>
            <div className="mt-3 space-y-2">
              {(insights?.actions || []).length ? (
                insights.actions.map((action) => (
                  <div key={action} className="rounded-md border border-line bg-surface px-3 py-2 text-sm text-muted">{action}</div>
                ))
              ) : (
                <div className="rounded-md border border-dashed border-line bg-surface p-4 text-sm text-muted">No urgent action detected yet.</div>
              )}
            </div>
          </div>

          <div className="rounded-md border border-line bg-white p-5 shadow-sm">
            <h2 className="text-lg font-semibold text-ink">Quick prompts</h2>
            <div className="mt-3 flex flex-wrap gap-2">
              {quickPrompts.map((prompt) => (
                <button key={prompt} type="button" onClick={() => setMessageText(prompt)} className="rounded-full border border-line px-3 py-2 text-xs font-semibold text-ink transition hover:bg-surface">
                  {prompt}
                </button>
              ))}
            </div>
          </div>

          <div className="rounded-md border border-line bg-white p-5 shadow-sm">
            <h2 className="text-lg font-semibold text-ink">Top and low-stock context</h2>
            <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-1">
              <ContextList title="Top items" items={insights?.topItems || []} empty="No top items yet." />
              <ContextList title="Low stock" items={insights?.lowStockItems || []} empty="No low-stock items." stock />
            </div>
          </div>
        </div>

        <div className="rounded-md border border-line bg-white p-5 shadow-sm">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold text-ink">Assistant chat</h2>
              <p className="mt-1 text-sm text-muted">Conversation is saved separately from customer chats.</p>
            </div>
            <button type="button" onClick={() => loadWorkspace().catch(() => {})} className="rounded-md border border-line px-3 py-2 text-sm font-semibold text-ink hover:bg-surface">Refresh</button>
          </div>

          <div className="mt-4 max-h-[520px] space-y-3 overflow-auto rounded-md border border-line bg-surface p-3">
            {visibleHistory.length ? (
              visibleHistory.map((message) => (
                <div key={message.id || message._id || `${message.createdAt}-${message.sender}`} className={message.sender === "owner" ? "ml-auto max-w-[85%] rounded-lg bg-brand px-4 py-3 text-sm text-white" : "mr-auto max-w-[90%] rounded-lg bg-white px-4 py-3 text-sm text-ink shadow-sm"}>
                  <div className="whitespace-pre-line leading-6">{message.messageText}</div>
                  <div className={message.sender === "owner" ? "mt-2 text-xs text-white/75" : "mt-2 text-xs text-muted"}>{message.sender} {formatDate(message.createdAt)}</div>
                </div>
              ))
            ) : (
              <div className="rounded-md border border-dashed border-line bg-white p-5 text-sm text-muted">Ask the owner assistant a business question to start.</div>
            )}
          </div>

          <form onSubmit={handleSubmit} className="mt-4 space-y-3">
            <textarea className="min-h-24 w-full rounded-md border border-line px-3 py-2 text-sm" value={messageText} onChange={(event) => setMessageText(event.target.value)} placeholder="Ask: Which items are low stock?" />
            <button type="submit" disabled={isSending || !messageText.trim()} className="rounded-md bg-brand px-4 py-2 text-sm font-semibold text-white disabled:opacity-60">
              {isSending ? "Thinking..." : "Ask assistant"}
            </button>
          </form>

          {lastContext?.toolCalls?.length ? (
            <div className="mt-4 rounded-md bg-surface p-3 text-xs text-muted">
              Last tool: {lastContext.toolCalls.map((tool) => tool.tool).join(", ")}
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}

function ContextList({ title, items, empty, stock = false }) {
  return (
    <div className="rounded-md border border-line p-3">
      <div className="text-sm font-semibold text-ink">{title}</div>
      <div className="mt-2 space-y-2">
        {items.length ? items.slice(0, 5).map((item) => (
          <div key={item.id || item.itemId || item.name} className="text-sm text-muted">
            <span className="font-medium text-ink">{item.name}</span>
            {stock ? ` — qty ${item.stock?.quantity ?? 0}` : ` — ${item.quantity ?? 0} qty`}
          </div>
        )) : <div className="text-sm text-muted">{empty}</div>}
      </div>
    </div>
  );
}
