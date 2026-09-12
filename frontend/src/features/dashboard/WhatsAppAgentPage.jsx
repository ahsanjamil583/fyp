import { useEffect, useMemo, useState } from "react";

import { useModules } from "../../context/ModuleContext.jsx";
import { useTenant } from "../../context/TenantContext.jsx";
import { isDebugMode } from "../../utils/displaySafety.js";
import {
  disconnectWhatsApp,
  getWhatsAppConversations,
  getWhatsAppSettings,
  refreshWhatsAppBridgeToken,
  saveWhatsAppSettings,
  sendWhatsAppTest,
  simulateWhatsAppInbound,
} from "../../services/whatsappApi.js";
import { SectionTitle } from "../../components/ui/SectionTitle.jsx";

const defaultForm = {
  provider: "baileys",
  businessWhatsAppNumber: "",
  displayName: "",
  agentEnabled: true,
  autoReplyEnabled: true,
  handoffEnabled: true,
  handoffKeywords: "human, agent, admin, owner, representative, call me, insan, baat karni",
  welcomeMessage: "Assalam o Alaikum! Main BizXus AI assistant hoon. Aap products, prices, timing ya order ke bare mein pooch sakte hain.",
  fallbackReply: "Sorry, main is waqt WhatsApp reply complete nahi kar pa raha. Business owner ko notify kar diya gaya hai.",
  businessHoursMode: "always_on",
};

function toKeywordList(value) {
  return String(value || "")
    .split(",")
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean);
}

function formatDate(value) {
  if (!value) return "Not yet";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return "Not yet";
  }
}

export function WhatsAppAgentPage() {
  const { selectedTenant, isLoadingTenants } = useTenant();
  const { enabledModules, isLoadingModules } = useModules();
  const [settings, setSettings] = useState(null);
  const [form, setForm] = useState(defaultForm);
  const [mockForm, setMockForm] = useState({ customerPhone: "+923001234567", customerName: "Demo Customer", messageText: "2 burgers order kar do" });
  const [testForm, setTestForm] = useState({ toPhone: "+923001234567", messageText: "BizXus WhatsApp agent test message." });
  const [conversations, setConversations] = useState([]);
  const [lastResult, setLastResult] = useState(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isSimulating, setIsSimulating] = useState(false);
  const [isSendingTest, setIsSendingTest] = useState(false);
  const [isRefreshingToken, setIsRefreshingToken] = useState(false);

  const aiEnabled = enabledModules.includes("ai_chat");
  const whatsappEnabled = enabledModules.includes("whatsapp_agent");
  const connected = Boolean(settings?.provider === "baileys" ? settings?.bridgeOnline : settings?.isConnected);
  const connectionStatus = settings?.connectionStatus || settings?.status || "not_configured";
  const webhookUrl = useMemo(() => {
    const base = import.meta.env.VITE_API_BASE_URL || "/api/v1";
    return `${base.replace(/\/$/, "")}/webhooks/whatsapp`;
  }, []);
  const apiBaseUrl = useMemo(() => {
    return new URL(import.meta.env.VITE_API_BASE_URL || "/api/v1", window.location.origin).href.replace(/\/$/, "");
  }, []);
  const bridgeStatusUrl = `${apiBaseUrl}/whatsapp/bridge/status`;
  const bridgeInboundUrl = `${apiBaseUrl}/whatsapp/bridge/inbound`;
  // The pairing page is per business, so the owner opens their own QR and never sees
  // another tenant on the same bridge. The API supplies it; the fallback keeps the
  // button working against an older backend.
  const bridgeQrUrl =
    settings?.bridgePairingUrl ||
    (selectedTenant ? `http://localhost:3005/pair/${encodeURIComponent(selectedTenant.id)}` : "http://localhost:3005");
  // Shown on screen with the token masked; `bridgeEnv` (with the real token) is only
  // ever written to the clipboard by the Copy env button.
  const bridgeEnvRedacted = selectedTenant
    ? [
        `BIZXUS_API_BASE_URL=${apiBaseUrl}`,
        `BIZXUS_TENANT_ID=${selectedTenant.id}`,
        "BIZXUS_WHATSAPP_BRIDGE_TOKEN=********  (use Copy env)",
        `WHATSAPP_AUTH_PATH=.baileys_auth/${selectedTenant.id}`,
        "PORT=3005",
      ].join("\n")
    : "";
  const bridgeEnv = selectedTenant
    ? [
        `BIZXUS_API_BASE_URL=${apiBaseUrl}`,
        `BIZXUS_TENANT_ID=${selectedTenant.id}`,
        `BIZXUS_WHATSAPP_BRIDGE_TOKEN=${settings?.bridgeToken || "SAVE_SETTINGS_FIRST"}`,
        `WHATSAPP_AUTH_PATH=.baileys_auth/${selectedTenant.id}`,
        "PORT=3005",
      ].join("\n")
    : "";

  async function loadWorkspace() {
    if (!selectedTenant || !aiEnabled || !whatsappEnabled) {
      setSettings(null);
      setConversations([]);
      return;
    }
    setIsLoading(true);
    setError("");
    try {
      const data = await getWhatsAppSettings(selectedTenant.id);
      const nextSettings = data.settings || {};
      setSettings(nextSettings);
      setForm({
        ...defaultForm,
        provider: nextSettings.provider || "baileys",
        businessWhatsAppNumber: nextSettings.businessWhatsAppNumber || selectedTenant.contact?.whatsapp || "",
        displayName: nextSettings.displayName || selectedTenant.name || "",
        agentEnabled: nextSettings.agentEnabled !== false,
        autoReplyEnabled: nextSettings.autoReplyEnabled !== false,
        handoffEnabled: nextSettings.handoffEnabled !== false,
        handoffKeywords: (nextSettings.handoffKeywords || defaultForm.handoffKeywords.split(",")).join(", "),
        welcomeMessage: nextSettings.welcomeMessage || defaultForm.welcomeMessage,
        fallbackReply: nextSettings.fallbackReply || defaultForm.fallbackReply,
        businessHoursMode: nextSettings.businessHoursMode || "always_on",
      });
      const conversationData = await getWhatsAppConversations(selectedTenant.id, { page: 1, limit: 8 });
      setConversations(conversationData.items || []);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to load WhatsApp agent settings.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    loadWorkspace().catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedTenant?.id, aiEnabled, whatsappEnabled]);

  useEffect(() => {
    if (!selectedTenant?.id || !aiEnabled || !whatsappEnabled) return undefined;
    let active = true;
    const timer = setInterval(() => {
      getWhatsAppSettings(selectedTenant.id).then((data) => {
        if (active) setSettings(data.settings || {});
      }).catch(() => {
        if (active) setSettings((current) => ({ ...current, bridgeOnline: false, connectionStatus: "status_unavailable" }));
      });
    }, 15000);
    return () => { active = false; clearInterval(timer); };
  }, [selectedTenant?.id, aiEnabled, whatsappEnabled]);

  function updateForm(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function handleSave(event) {
    event.preventDefault();
    if (!selectedTenant) return;
    setIsSaving(true);
    setError("");
    setNotice("");
    try {
      const data = await saveWhatsAppSettings(selectedTenant.id, {
        provider: form.provider,
        businessWhatsAppNumber: form.businessWhatsAppNumber,
        displayName: form.displayName,
        agentEnabled: form.agentEnabled,
        autoReplyEnabled: form.autoReplyEnabled,
        handoffEnabled: form.handoffEnabled,
        handoffKeywords: toKeywordList(form.handoffKeywords),
        welcomeMessage: form.welcomeMessage,
        fallbackReply: form.fallbackReply,
        businessHoursMode: form.businessHoursMode,
      });
      setSettings(data.settings);
      setNotice("WhatsApp agent settings saved successfully.");
      await loadWorkspace();
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to save WhatsApp settings.");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleDisconnect() {
    if (!selectedTenant) return;
    const confirmed = window.confirm("Disconnect the WhatsApp agent for this business?");
    if (!confirmed) return;
    setError("");
    setNotice("");
    try {
      const data = await disconnectWhatsApp(selectedTenant.id);
      setSettings(data.settings);
      setNotice("WhatsApp agent disconnected.");
      await loadWorkspace();
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to disconnect WhatsApp agent.");
    }
  }

  async function handleMockInbound(event) {
    event.preventDefault();
    if (!selectedTenant) return;
    setIsSimulating(true);
    setError("");
    setNotice("");
    setLastResult(null);
    try {
      const data = await simulateWhatsAppInbound(selectedTenant.id, mockForm);
      setLastResult(data);
      setNotice("Mock customer message processed by the WhatsApp AI agent.");
      await loadWorkspace();
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to process mock WhatsApp message.");
    } finally {
      setIsSimulating(false);
    }
  }

  async function handleSendTest(event) {
    event.preventDefault();
    if (!selectedTenant) return;
    setIsSendingTest(true);
    setError("");
    setNotice("");
    try {
      await sendWhatsAppTest(selectedTenant.id, testForm);
      setNotice("Test message logged successfully.");
      await loadWorkspace();
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to send WhatsApp test message.");
    } finally {
      setIsSendingTest(false);
    }
  }

  async function handleRefreshToken() {
    if (!selectedTenant) return;
    const confirmed = window.confirm("Refresh the WhatsApp bridge token? Your currently running bridge will need the new token.");
    if (!confirmed) return;
    setIsRefreshingToken(true);
    setError("");
    setNotice("");
    try {
      const data = await refreshWhatsAppBridgeToken(selectedTenant.id);
      setSettings(data.settings);
      setNotice("WhatsApp bridge token refreshed. Update your bridge .env before restarting it.");
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to refresh WhatsApp bridge token.");
    } finally {
      setIsRefreshingToken(false);
    }
  }

  async function copyText(value, message = "Copied.") {
    try {
      await navigator.clipboard.writeText(value);
      setNotice(message);
    } catch {
      setError("Unable to copy text. Please select and copy it manually.");
    }
  }

  if (isLoadingTenants || isLoadingModules || isLoading) {
    return <div className="rounded-xl border border-line bg-white p-6 text-sm text-muted">Loading WhatsApp agent...</div>;
  }

  if (!selectedTenant) {
    return <div className="rounded-xl border border-line bg-white p-6 text-sm text-muted">Select a business first.</div>;
  }

  if (!aiEnabled || !whatsappEnabled) {
    return (
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-6 text-sm text-amber-800">
        Enable AI Chat and WhatsApp Agent modules before configuring the WhatsApp assistant.
      </div>
    );
  }

  return (
    <section className="space-y-6">
      <div className="rounded-2xl border border-line bg-white p-6 shadow-card">
        <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-brand">WhatsApp Agent</p>
        <div className="mt-3 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <h1 className="text-2xl font-extrabold tracking-tight text-ink">WhatsApp Agent for {selectedTenant.name}</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-muted">
              Keep this page ready for your new WhatsApp method. For now, the local simulator lets you test AI replies,
              handoff keywords, order drafts, and conversation history. The Baileys bridge lets a business owner scan
              WhatsApp Linked Devices and reply from their own WhatsApp number.
            </p>
          </div>
          <div className={connected ? "rounded-xl border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800" : "rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800"}>
            <div className="font-semibold">{connected ? "Connected" : settings?.isConnected ? "Waiting for bridge connection" : "Needs WhatsApp number"}</div>
            <div className="mt-1 text-xs">Status: {connectionStatus}</div>
            {settings?.bridgeStatus ? <div className="mt-1 text-xs">Bridge: {settings.bridgeStatus.replaceAll("_", " ")}</div> : null}
            {settings?.provider === "baileys" && settings?.bridgeStatus !== "ready" ? (
              <a className="mt-2 inline-block text-xs font-bold underline" href={bridgeQrUrl} rel="noreferrer noopener" target="_blank">
                Open WhatsApp connection page
              </a>
            ) : null}
          </div>
        </div>
      </div>

      {notice ? <div className="rounded-xl border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700">{notice}</div> : null}
      {error ? <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div> : null}

      <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <form onSubmit={handleSave} className="space-y-5 rounded-xl border border-line bg-white p-5 shadow-card">
          <div>
            <SectionTitle>Connection settings</SectionTitle>
            <p className="mt-1 text-sm text-muted">
              This is a clean provider-neutral setup. Save the business WhatsApp contact number and test the AI flow with the simulator.
            </p>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <label className="text-sm font-medium text-ink">
              Provider
              <select className="mt-2 w-full rounded-xl border border-line px-3 py-2 text-sm" value={form.provider} onChange={(event) => updateForm("provider", event.target.value)}>
                <option value="baileys">Baileys linked device</option>
                <option value="mock">Mock / local simulator</option>
              </select>
              <span className="mt-1 block text-xs font-normal text-muted">Baileys is the WhatsApp Web linked-device approach from your ZIP project.</span>
            </label>
            <label className="text-sm font-medium text-ink">
              Business WhatsApp number
              <input className="mt-2 w-full rounded-xl border border-line px-3 py-2 text-sm" value={form.businessWhatsAppNumber} onChange={(event) => updateForm("businessWhatsAppNumber", event.target.value)} placeholder="+923001234567" required />
              <span className="mt-1 block text-xs font-normal text-muted">This number is shown to customers as the business contact number.</span>
            </label>
            <label className="text-sm font-medium text-ink">
              Display name
              <input className="mt-2 w-full rounded-xl border border-line px-3 py-2 text-sm" value={form.displayName} onChange={(event) => updateForm("displayName", event.target.value)} placeholder={selectedTenant.name} />
            </label>
            <label className="text-sm font-medium text-ink">
              Business hours behavior
              <select className="mt-2 w-full rounded-xl border border-line px-3 py-2 text-sm" value={form.businessHoursMode} onChange={(event) => updateForm("businessHoursMode", event.target.value)}>
                <option value="always_on">Always reply with AI</option>
                <option value="business_hours">Reply during business hours</option>
                <option value="offline_handoff">Mark handoff outside hours</option>
              </select>
            </label>
          </div>

          <label className="block text-sm font-medium text-ink">
            Welcome message
            <textarea className="mt-2 min-h-24 w-full rounded-xl border border-line px-3 py-2 text-sm" value={form.welcomeMessage} onChange={(event) => updateForm("welcomeMessage", event.target.value)} />
          </label>

          <label className="block text-sm font-medium text-ink">
            Default fallback reply
            <textarea className="mt-2 min-h-20 w-full rounded-xl border border-line px-3 py-2 text-sm" value={form.fallbackReply} onChange={(event) => updateForm("fallbackReply", event.target.value)} />
          </label>

          <div className="grid gap-4 md:grid-cols-3">
            <label className="flex items-center gap-2 rounded-xl border border-line bg-surface px-3 py-3 text-sm text-ink">
              <input type="checkbox" checked={form.agentEnabled} onChange={(event) => updateForm("agentEnabled", event.target.checked)} />
              Agent enabled
            </label>
            <label className="flex items-center gap-2 rounded-xl border border-line bg-surface px-3 py-3 text-sm text-ink">
              <input type="checkbox" checked={form.autoReplyEnabled} onChange={(event) => updateForm("autoReplyEnabled", event.target.checked)} />
              Auto-reply with AI agent
            </label>
            <label className="flex items-center gap-2 rounded-xl border border-line bg-surface px-3 py-3 text-sm text-ink">
              <input type="checkbox" checked={form.handoffEnabled} onChange={(event) => updateForm("handoffEnabled", event.target.checked)} />
              Allow human handoff keywords
            </label>
          </div>

          <label className="block text-sm font-medium text-ink">
            Handoff keywords
            <input className="mt-2 w-full rounded-xl border border-line px-3 py-2 text-sm" value={form.handoffKeywords} onChange={(event) => updateForm("handoffKeywords", event.target.value)} />
            <span className="mt-1 block text-xs font-normal text-muted">Comma-separated words like human, owner, call me, insan.</span>
          </label>

          <div className="rounded-xl bg-surface p-4 text-sm text-muted">
            <div className="font-semibold text-ink">WhatsApp connection</div>
            {isDebugMode ? (
              <div className="mt-1 break-all">{webhookUrl}</div>
            ) : (
              <div className="mt-1">Configured automatically for this workspace.</div>
            )}
            <div className="mt-3 font-semibold text-ink">Verify token</div>
            <div className="mt-1">
              {settings?.webhookVerifyToken ? (
                <span className="inline-flex items-center gap-2">
                  <span className="font-semibold text-ink">Configured</span>
                  <button
                    type="button"
                    className="rounded-lg border border-line bg-white px-2 py-1 text-xs font-bold text-brand"
                    onClick={() => copyText(settings.webhookVerifyToken, "Verify token copied.")}
                  >
                    Copy
                  </button>
                </span>
              ) : (
                "Save settings to generate the verify token."
              )}
            </div>
            <div className="mt-3 rounded-xl border border-line bg-white p-3 text-xs leading-5">
              This endpoint is kept as a provider-neutral placeholder for your new WhatsApp method.
            </div>
          </div>

          {form.provider === "baileys" ? (
            <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-950">
              <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                <div>
                  <div className="font-semibold">Baileys bridge setup</div>
                  <p className="mt-1 leading-6">
                    Save your settings first. When the bridge is connected, BizXusAI handles replies through this tenant.
                  </p>
                </div>
                {isDebugMode ? (
                  <button className="rounded-xl border border-emerald-300 bg-white px-3 py-2 text-xs font-bold text-emerald-800" onClick={() => copyText(bridgeEnv, "Bridge environment copied.")} type="button">
                  Copy env
                  </button>
                ) : null}
              </div>

              <div className="mt-3 rounded-xl border border-emerald-300 bg-white p-4">
                <div className="text-sm font-bold text-ink">Connect this business&apos;s WhatsApp</div>
                <p className="mt-1 text-xs leading-5 text-slate-600">
                  {isDebugMode
                    ? "Opens the pairing page for this business in a new tab. Keep the bridge running while you scan."
                    : "Connection details are handled by the workspace setup. Save settings and check the connected number below."}
                </p>
                {isDebugMode ? (
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <a
                      className="rounded-xl bg-emerald-600 px-4 py-2 text-sm font-bold text-white hover:bg-emerald-700"
                      href={bridgeQrUrl}
                      rel="noreferrer noopener"
                      target="_blank"
                    >
                      Open WhatsApp connection page
                    </a>
                    <button className="rounded-xl border border-emerald-300 bg-white px-3 py-2 text-xs font-bold text-emerald-800" onClick={() => copyText(bridgeQrUrl, "Connection page link copied.")} type="button">
                      Copy link
                    </button>
                  </div>
                ) : null}
                {isDebugMode ? (
                  <div className="mt-2 break-all text-xs text-slate-500">{bridgeQrUrl}</div>
                ) : null}
              </div>

              {/* The env block carries the bridge token, so it is never rendered as
                  text. "Copy env" still puts the real values on the clipboard. */}
              {isDebugMode ? (
                <pre className="mt-3 overflow-x-auto rounded-xl bg-white p-3 text-xs leading-5 text-ink">{bridgeEnvRedacted}</pre>
              ) : null}
              <div className="mt-3 grid gap-3 md:grid-cols-2">
                <div className="rounded-xl bg-white p-3">
                  <div className="text-xs font-bold uppercase tracking-wide text-emerald-700">Connected number</div>
                  <div className="mt-1 font-semibold text-ink">{settings?.bridgeConnectedNumber || settings?.businessWhatsAppNumber || "Not connected yet"}</div>
                </div>
                {isDebugMode ? (
                  <>
                    <div className="rounded-xl bg-white p-3">
                      <div className="text-xs font-bold uppercase tracking-wide text-emerald-700">Status endpoint</div>
                      <div className="mt-1 break-all text-xs font-semibold text-ink">{bridgeStatusUrl}</div>
                    </div>
                    <div className="rounded-xl bg-white p-3">
                      <div className="text-xs font-bold uppercase tracking-wide text-emerald-700">Inbound endpoint</div>
                      <div className="mt-1 break-all text-xs font-semibold text-ink">{bridgeInboundUrl}</div>
                    </div>
                  </>
                ) : null}
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {isDebugMode ? (
                  <button className="rounded-xl border border-emerald-300 bg-white px-3 py-2 text-xs font-bold text-emerald-800" onClick={() => copyText(`cd whatsapp-bridge\nnpm install\nnpm run dev`, "Bridge run commands copied.")} type="button">
                    Copy run commands
                  </button>
                ) : null}
                {isDebugMode ? (
                  <button className="rounded-xl border border-amber-300 bg-white px-3 py-2 text-xs font-bold text-amber-800" disabled={isRefreshingToken} onClick={handleRefreshToken} type="button">
                    {isRefreshingToken ? "Refreshing..." : "Refresh bridge token"}
                  </button>
                ) : null}
              </div>
            </div>
          ) : null}

          <div className="flex flex-wrap gap-3">
            <button className="rounded-xl bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700" disabled={isSaving} type="submit">
              {isSaving ? "Saving..." : "Save / Connect"}
            </button>
            {connected ? (
              <button className="rounded-xl border border-line px-4 py-2 text-sm font-semibold text-ink hover:bg-surface" onClick={handleDisconnect} type="button">
                Disconnect
              </button>
            ) : null}
          </div>
        </form>

        <div className="space-y-6">
          <form onSubmit={handleMockInbound} className="space-y-4 rounded-xl border border-line bg-white p-5 shadow-card">
            <div>
              <SectionTitle>Mock customer message</SectionTitle>
              <p className="mt-1 text-sm text-muted">Simulate a WhatsApp customer asking the agent a question or requesting an order.</p>
            </div>
            <div className="flex gap-2 overflow-x-auto pb-1">
              {["Menu bhej do", "Zinger burger available hai?", "Delivery charges?", "2 items order kar do"].map((prompt) => (
                <button
                  key={prompt}
                  className="shrink-0 rounded-full border border-line bg-surface px-3 py-2 text-xs font-semibold text-muted hover:border-brand-200 hover:bg-brand-50 hover:text-brand"
                  type="button"
                  onClick={() => setMockForm((current) => ({ ...current, messageText: prompt }))}
                >
                  {prompt}
                </button>
              ))}
            </div>
            <input className="w-full rounded-xl border border-line px-3 py-2 text-sm" value={mockForm.customerPhone} onChange={(event) => setMockForm((current) => ({ ...current, customerPhone: event.target.value }))} placeholder="Customer phone" />
            <input className="w-full rounded-xl border border-line px-3 py-2 text-sm" value={mockForm.customerName} onChange={(event) => setMockForm((current) => ({ ...current, customerName: event.target.value }))} placeholder="Customer name" />
            <textarea className="min-h-28 w-full rounded-xl border border-line px-3 py-2 text-sm" value={mockForm.messageText} onChange={(event) => setMockForm((current) => ({ ...current, messageText: event.target.value }))} />
            <button className="rounded-xl bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700" disabled={!connected || isSimulating} type="submit">
              {isSimulating ? "Processing..." : "Process with AI"}
            </button>
            {lastResult ? (
              <div className="space-y-3 rounded-2xl border border-brand-100 bg-gradient-to-br from-brand-50 to-cyan-50 p-4 text-sm text-brand-900">
                <div className="flex items-center justify-between gap-3">
                  <div className="font-semibold">WhatsApp AI reply</div>
                  <span className={lastResult.handoffRequired ? "rounded-full bg-amber-100 px-2 py-1 text-xs font-bold text-amber-800" : "rounded-full bg-green-100 px-2 py-1 text-xs font-bold text-green-800"}>
                    {lastResult.handoffRequired ? "Handoff" : "AI reply"}
                  </span>
                </div>
                <div className="rounded-2xl rounded-bl-lg bg-white px-4 py-3 shadow-card">
                  <p className="leading-6">{lastResult.reply}</p>
                </div>
              </div>
            ) : null}
          </form>

          <form onSubmit={handleSendTest} className="space-y-4 rounded-xl border border-line bg-white p-5 shadow-card">
            <div>
              <SectionTitle>Send test message</SectionTitle>
              <p className="mt-1 text-sm text-muted">This logs a local outbound message for testing and review.</p>
            </div>
            <input className="w-full rounded-xl border border-line px-3 py-2 text-sm" value={testForm.toPhone} onChange={(event) => setTestForm((current) => ({ ...current, toPhone: event.target.value }))} placeholder="Recipient phone" />
            <textarea className="min-h-20 w-full rounded-xl border border-line px-3 py-2 text-sm" value={testForm.messageText} onChange={(event) => setTestForm((current) => ({ ...current, messageText: event.target.value }))} />
            <button className="rounded-xl border border-line px-4 py-2 text-sm font-semibold text-ink hover:bg-surface" disabled={!connected || isSendingTest} type="submit">
              {isSendingTest ? "Sending..." : "Log test"}
            </button>
          </form>
        </div>
      </div>

      <div className="rounded-xl border border-line bg-white p-5 shadow-card">
        <div className="flex items-center justify-between gap-4">
          <div>
            <SectionTitle>Recent WhatsApp conversations</SectionTitle>
            <p className="mt-1 text-sm text-muted">These also appear in the AI Chat conversation review screen.</p>
          </div>
          <button className="rounded-xl border border-line px-3 py-2 text-sm font-semibold text-ink hover:bg-surface" onClick={() => loadWorkspace()} type="button">
            Refresh
          </button>
        </div>
        <div className="mt-4 overflow-hidden rounded-xl border border-line">
          <table className="min-w-full divide-y divide-line text-sm">
            <thead className="bg-surface text-left text-[11px] font-bold uppercase tracking-[0.12em] text-subtle">
              <tr>
                <th className="px-4 py-3">Customer</th>
                <th className="px-4 py-3">Last intent</th>
                <th className="px-4 py-3">Summary</th>
                <th className="px-4 py-3">Last message</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line bg-white">
              {conversations.length ? (
                conversations.map((conversation) => (
                  <tr key={conversation.id}>
                    <td className="px-4 py-3">
                      <div className="font-medium text-ink">{conversation.externalCustomerName || "WhatsApp Customer"}</div>
                      <div className="text-xs text-muted">{conversation.externalCustomerPhone}</div>
                    </td>
                    <td className="px-4 py-3 text-muted">{conversation.lastIntent || "-"}</td>
                    <td className="px-4 py-3 text-muted">{conversation.summary || "-"}</td>
                    <td className="px-4 py-3 text-muted">{formatDate(conversation.lastMessageAt)}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td className="px-4 py-6 text-center text-muted" colSpan="4">
                    No WhatsApp conversations yet. Use the mock simulator to test the flow.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
