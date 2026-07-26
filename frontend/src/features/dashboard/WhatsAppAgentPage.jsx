import { useEffect, useMemo, useRef, useState } from "react";

import { useModules } from "../../context/ModuleContext.jsx";
import { useTenant } from "../../context/TenantContext.jsx";
import {
  captureWhatsAppEmbeddedSignup,
  disconnectWhatsApp,
  exchangeWhatsAppEmbeddedSignupToken,
  getWhatsAppConversations,
  getWhatsAppConversationTimeline,
  getWhatsAppDiagnostics,
  getWhatsAppGoLiveChecklist,
  getWhatsAppRoutingStatus,
  subscribeWhatsAppEmbeddedSignupWebhooks,
  registerWhatsAppEmbeddedSignupPhone,
  recordWhatsAppGoLiveTestRun,
  getWhatsAppSettings,
  saveWhatsAppSettings,
  sendWhatsAppTest,
  simulateWhatsAppInbound,
  testWhatsAppRouting,
  testWhatsAppLiveWebhookPayload,
} from "../../services/whatsappApi.js";

const defaultForm = {
  provider: "mock",
  businessWhatsAppNumber: "",
  displayName: "",
  phoneNumberId: "",
  whatsappBusinessAccountId: "",
  accessToken: "",
  apiVersion: "v21.0",
  agentEnabled: true,
  autoReplyEnabled: true,
  handoffEnabled: true,
  handoffKeywords: "human, agent, admin, owner, representative, call me, insan, baat karni",
  welcomeMessage:
    "Assalam o Alaikum! Main BizXus AI assistant hoon. Aap products, prices, timing ya order ke bare mein pooch sakte hain.",
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

function loadFacebookSdk(appId, version = "v21.0") {
  if (!appId) {
    return Promise.reject(new Error("Meta App ID is missing."));
  }
  if (window.FB) {
    window.FB.init({ appId, cookie: true, xfbml: false, version });
    return Promise.resolve(window.FB);
  }
  return new Promise((resolve, reject) => {
    const existing = document.getElementById("facebook-jssdk");
    window.fbAsyncInit = function fbAsyncInit() {
      window.FB.init({ appId, cookie: true, xfbml: false, version });
      resolve(window.FB);
    };
    if (existing) {
      let attempts = 0;
      const interval = window.setInterval(() => {
        attempts += 1;
        if (window.FB) {
          window.clearInterval(interval);
          window.FB.init({ appId, cookie: true, xfbml: false, version });
          resolve(window.FB);
        }
        if (attempts > 80) {
          window.clearInterval(interval);
          reject(new Error("Facebook JavaScript SDK did not finish loading."));
        }
      }, 250);
      return;
    }
    const script = document.createElement("script");
    script.id = "facebook-jssdk";
    script.async = true;
    script.defer = true;
    script.crossOrigin = "anonymous";
    script.src = "https://connect.facebook.net/en_US/sdk.js";
    script.onerror = () => reject(new Error("Unable to load Facebook JavaScript SDK."));
    document.body.appendChild(script);
  });
}

function storeSignupDraft(tenantId, payload) {
  if (!tenantId) return;
  sessionStorage.setItem(`bizxus_meta_signup_${tenantId}`, JSON.stringify({ ...payload, savedAt: new Date().toISOString() }));
}

function loadSignupDraft(tenantId) {
  if (!tenantId) return null;
  const tenantDraft = sessionStorage.getItem(`bizxus_meta_signup_${tenantId}`);
  const redirectDraft = sessionStorage.getItem("bizxus_meta_signup_redirect_callback");
  const rawDraft = tenantDraft || redirectDraft;
  if (!rawDraft) return null;
  try {
    const parsed = JSON.parse(rawDraft);
    if (parsed?.query && !parsed.callbackQuery) {
      return {
        source: "redirect_callback",
        authorizationCode: parsed.query.code || "",
        callbackQuery: parsed.query,
        receivedAt: parsed.receivedAt || new Date().toISOString(),
      };
    }
    return parsed;
  } catch {
    return null;
  }
}

function buildSignupCapturePayload(response) {
  const authResponse = response?.authResponse || {};
  const callbackQuery = response?.callbackQuery || {};
  return {
    source: response?.source || "fb_login",
    status: response?.status || "",
    authorizationCode: response?.authorizationCode || authResponse.code || callbackQuery.code || "",
    authResponse,
    embeddedSignup: response?.embeddedSignup || {},
    callbackQuery,
    receivedAt: response?.receivedAt || new Date().toISOString(),
  };
}

export function WhatsAppAgentPage() {
  const { selectedTenant, isLoadingTenants } = useTenant();
  const { enabledModules, isLoadingModules } = useModules();
  const [settings, setSettings] = useState(null);
  const [metaSetup, setMetaSetup] = useState(null);
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
  const [isLaunchingMeta, setIsLaunchingMeta] = useState(false);
  const [isCapturingSignup, setIsCapturingSignup] = useState(false);
  const [isExchangingToken, setIsExchangingToken] = useState(false);
  const [isSubscribingWebhooks, setIsSubscribingWebhooks] = useState(false);
  const [isRegisteringPhone, setIsRegisteringPhone] = useState(false);
  const [phoneRegistrationPin, setPhoneRegistrationPin] = useState("");
  const [routingStatus, setRoutingStatus] = useState(null);
  const [routingTestResult, setRoutingTestResult] = useState(null);
  const [isTestingRouting, setIsTestingRouting] = useState(false);
  const [routingTestForm, setRoutingTestForm] = useState({ customerPhone: "+923001234567", customerName: "Routing Test Customer", messageText: "Zinger burger available hai?", sendReply: false });
  const [diagnostics, setDiagnostics] = useState(null);
  const [isTestingLiveWebhook, setIsTestingLiveWebhook] = useState(false);
  const [liveWebhookResult, setLiveWebhookResult] = useState(null);
  const [liveWebhookForm, setLiveWebhookForm] = useState({ customerPhone: "+923001234567", customerName: "Live Test Customer", messageText: "Zinger burger available hai?", processWithAgent: false });
  const [selectedTimeline, setSelectedTimeline] = useState(null);
  const [isLoadingTimeline, setIsLoadingTimeline] = useState(false);
  const [goLive, setGoLive] = useState(null);
  const [goLiveResult, setGoLiveResult] = useState(null);
  const [isRecordingGoLive, setIsRecordingGoLive] = useState(false);
  const [goLiveForm, setGoLiveForm] = useState({
    customerPhone: "+923001234567",
    customerName: "Live Test Customer",
    testMessage: "Zinger burger available hai?",
    realCustomerMessageReceived: false,
    aiReplyDelivered: false,
    conversationVisible: false,
    orderFlowTested: false,
    orderCreated: false,
    handoffTested: false,
    ownerNotificationCreated: false,
    notes: "",
    result: "auto",
  });
  const [signupStep, setSignupStep] = useState("idle");
  const [signupResponse, setSignupResponse] = useState(null);
  const signupResponseRef = useRef(null);

  const aiEnabled = enabledModules.includes("ai_chat");
  const whatsappEnabled = enabledModules.includes("whatsapp_agent");
  const connected = Boolean(settings?.isConnected);
  const connectionStatus = settings?.connectionStatus || settings?.status || "not_configured";
  const webhookUrl = useMemo(() => {
    const base = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api/v1";
    return `${base.replace(/\/$/, "")}/webhooks/whatsapp`;
  }, []);

  async function loadWorkspace() {
    if (!selectedTenant || !aiEnabled || !whatsappEnabled) {
      setSettings(null);
      setConversations([]);
      setRoutingStatus(null);
      setDiagnostics(null);
      setGoLive(null);
      setSelectedTimeline(null);
      return;
    }
    setIsLoading(true);
    setError("");
    try {
      const data = await getWhatsAppSettings(selectedTenant.id);
      const nextSettings = data.settings || {};
      setSettings(nextSettings);
      setMetaSetup(data.metaEmbeddedSignup || null);
      setForm({
        ...defaultForm,
        provider: nextSettings.provider || "mock",
        businessWhatsAppNumber: nextSettings.businessWhatsAppNumber || selectedTenant.contact?.whatsapp || "",
        displayName: nextSettings.displayName || selectedTenant.name || "",
        phoneNumberId: nextSettings.phoneNumberId || "",
        whatsappBusinessAccountId: nextSettings.whatsappBusinessAccountId || "",
        accessToken: "",
        apiVersion: nextSettings.apiVersion || "v21.0",
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
      try {
        const routingData = await getWhatsAppRoutingStatus(selectedTenant.id);
        setRoutingStatus(routingData.routing || null);
      } catch {
        setRoutingStatus(null);
      }
      try {
        const diagnosticsData = await getWhatsAppDiagnostics(selectedTenant.id);
        setDiagnostics(diagnosticsData.diagnostics || null);
      } catch {
        setDiagnostics(null);
      }
      try {
        const goLiveData = await getWhatsAppGoLiveChecklist(selectedTenant.id);
        setGoLive(goLiveData.phaseJ || null);
      } catch {
        setGoLive(null);
      }
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
    const draft = loadSignupDraft(selectedTenant?.id);
    if (!draft) {
      signupResponseRef.current = null;
      setSignupResponse(null);
      setSignupStep("idle");
      return;
    }
    signupResponseRef.current = draft;
    setSignupResponse(draft);
    if (draft.authorizationCode || draft.authResponse?.code || draft.callbackQuery?.code) {
      setSignupStep("code_received");
    } else if (draft.embeddedSignup?.event === "FINISH") {
      setSignupStep("completed");
    } else {
      setSignupStep("in_progress");
    }
  }, [selectedTenant?.id]);

  useEffect(() => {
    function handleEmbeddedSignupMessage(event) {
      if (!["https://www.facebook.com", "https://web.facebook.com"].includes(event.origin)) return;
      let payload = event.data;
      if (typeof payload === "string") {
        try {
          payload = JSON.parse(payload);
        } catch {
          return;
        }
      }
      if (payload?.type !== "WA_EMBEDDED_SIGNUP") return;
      const nextPayload = {
        source: "message",
        event: payload.event || "",
        data: payload.data || {},
        receivedAt: new Date().toISOString(),
      };
      signupResponseRef.current = { ...(signupResponseRef.current || {}), embeddedSignup: nextPayload };
      setSignupResponse(signupResponseRef.current);
      if (selectedTenant?.id) storeSignupDraft(selectedTenant.id, signupResponseRef.current);
      if (payload.event === "FINISH") {
        setSignupStep("completed");
        setNotice("Meta signup completed in the browser. Phase C will send this signup response to the backend.");
      } else if (payload.event === "CANCEL") {
        setSignupStep("cancelled");
        setError("Meta signup was cancelled before completion.");
      } else if (payload.event === "ERROR") {
        setSignupStep("failed");
        setError(payload.data?.error_message || "Meta signup returned an error.");
      } else {
        setSignupStep("in_progress");
      }
    }
    window.addEventListener("message", handleEmbeddedSignupMessage);
    return () => window.removeEventListener("message", handleEmbeddedSignupMessage);
  }, [selectedTenant?.id]);

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
        phoneNumberId: form.phoneNumberId,
        whatsappBusinessAccountId: form.whatsappBusinessAccountId,
        accessToken: form.accessToken,
        apiVersion: form.apiVersion,
        agentEnabled: form.agentEnabled,
        autoReplyEnabled: form.autoReplyEnabled,
        handoffEnabled: form.handoffEnabled,
        handoffKeywords: toKeywordList(form.handoffKeywords),
        welcomeMessage: form.welcomeMessage,
        fallbackReply: form.fallbackReply,
        businessHoursMode: form.businessHoursMode,
      });
      setSettings(data.settings);
      setForm((current) => ({ ...current, accessToken: "" }));
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
      setNotice("Test message logged/sent successfully.");
      await loadWorkspace();
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to send WhatsApp test message.");
    } finally {
      setIsSendingTest(false);
    }
  }

  async function handleConnectWithMeta() {
    setError("");
    setNotice("");
    setSignupResponse(null);
    signupResponseRef.current = null;
    if (!selectedTenant) return;
    if (!metaSetup?.ready) {
      setSignupStep("blocked");
      setError("Complete Phase A Meta setup first. Add the missing Meta values to backend .env and restart the backend.");
      return;
    }
    setIsLaunchingMeta(true);
    setSignupStep("loading_sdk");
    try {
      const fb = await loadFacebookSdk(metaSetup.metaAppId, metaSetup.graphApiVersion || "v21.0");
      setSignupStep("popup_open");
      fb.login(
        (response) => {
          setIsLaunchingMeta(false);
          const authResponse = response?.authResponse || {};
          const nextPayload = {
            tenantId: selectedTenant.id,
            source: "fb_login",
            authorizationCode: authResponse.code || "",
            authResponse,
            status: response?.status || "",
            receivedAt: new Date().toISOString(),
          };
          signupResponseRef.current = { ...(signupResponseRef.current || {}), ...nextPayload };
          setSignupResponse(signupResponseRef.current);
          storeSignupDraft(selectedTenant.id, signupResponseRef.current);
          if (authResponse.code) {
            setSignupStep("code_received");
            setNotice("Meta returned an authorization code. Save the signup response so the backend can prepare token exchange.");
          } else if (response?.status === "not_authorized") {
            setSignupStep("blocked");
            setError("Meta login was not authorized. Please try again and approve the requested permissions.");
          } else {
            setSignupStep("cancelled");
            setError("Meta signup did not return an authorization code.");
          }
        },
        {
          config_id: metaSetup.embeddedSignupConfigId,
          response_type: "code",
          override_default_response_type: true,
          extras: {
            setup: {},
            feature: "whatsapp_embedded_signup",
            sessionInfoVersion: 2,
          },
        },
      );
    } catch (sdkError) {
      setIsLaunchingMeta(false);
      setSignupStep("failed");
      setError(sdkError.message || "Unable to open Meta Embedded Signup.");
    }
  }

  async function handleCaptureSignup() {
    if (!selectedTenant) return;
    if (!signupResponse) {
      setError("Complete Meta Embedded Signup first, then save the signup response.");
      return;
    }
    const payload = buildSignupCapturePayload(signupResponse);
    if (!payload.authorizationCode) {
      setError("Meta signup did not include an authorization code. Please run Connect with Meta again.");
      return;
    }
    setIsCapturingSignup(true);
    setError("");
    setNotice("");
    try {
      const data = await captureWhatsAppEmbeddedSignup(selectedTenant.id, payload);
      setSettings(data.settings);
      setMetaSetup(data.metaEmbeddedSignup || metaSetup);
      setSignupStep("pending_token_exchange");
      setSignupResponse(null);
      signupResponseRef.current = null;
      sessionStorage.removeItem(`bizxus_meta_signup_${selectedTenant.id}`);
      sessionStorage.removeItem("bizxus_meta_signup_redirect_callback");
      setNotice("Meta signup response saved. Backend status is now pending token exchange for Phase D.");
      await loadWorkspace();
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to save Meta signup response.");
    } finally {
      setIsCapturingSignup(false);
    }
  }

  async function handleExchangeToken() {
    if (!selectedTenant) return;
    setIsExchangingToken(true);
    setError("");
    setNotice("");
    try {
      const data = await exchangeWhatsAppEmbeddedSignupToken(selectedTenant.id);
      setSettings(data.settings);
      setMetaSetup(data.metaEmbeddedSignup || metaSetup);
      setSignupStep("token_exchanged");
      setNotice("Meta token exchanged successfully. WhatsApp is connected at token level; webhook subscription and phone registration are next.");
      await loadWorkspace();
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to exchange Meta signup code for a business token.");
      await loadWorkspace();
    } finally {
      setIsExchangingToken(false);
    }
  }

  async function handleSubscribeWebhooks() {
    if (!selectedTenant) return;
    setIsSubscribingWebhooks(true);
    setError("");
    setNotice("");
    try {
      const data = await subscribeWhatsAppEmbeddedSignupWebhooks(selectedTenant.id);
      setSettings(data.settings);
      setMetaSetup(data.metaEmbeddedSignup || metaSetup);
      setSignupStep("webhook_subscribed");
      setNotice("Meta WABA webhooks subscribed successfully. Incoming customer WhatsApp messages can now reach this backend webhook.");
      await loadWorkspace();
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to subscribe this WABA to WhatsApp webhooks.");
      await loadWorkspace();
    } finally {
      setIsSubscribingWebhooks(false);
    }
  }


  async function handleRegisterPhone() {
    if (!selectedTenant) return;
    const cleanPin = String(phoneRegistrationPin || "").trim();
    if (!/^\d{6}$/.test(cleanPin)) {
      setError("Enter the 6-digit WhatsApp registration PIN you want to set for this business number.");
      return;
    }
    setIsRegisteringPhone(true);
    setError("");
    setNotice("");
    try {
      const data = await registerWhatsAppEmbeddedSignupPhone(selectedTenant.id, { pin: cleanPin });
      setSettings(data.settings);
      setMetaSetup(data.metaEmbeddedSignup || metaSetup);
      setPhoneRegistrationPin("");
      setSignupStep("phone_registered");
      setNotice("Meta phone number registered successfully. This WhatsApp number is now ready for Cloud API webhooks and AI replies.");
      await loadWorkspace();
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to register this WhatsApp phone number for Cloud API use.");
      await loadWorkspace();
    } finally {
      setIsRegisteringPhone(false);
    }
  }

  async function handleTestRouting(event) {
    event.preventDefault();
    if (!selectedTenant) return;
    setIsTestingRouting(true);
    setError("");
    setNotice("");
    setRoutingTestResult(null);
    try {
      const data = await testWhatsAppRouting(selectedTenant.id, routingTestForm);
      setSettings(data.settings || settings);
      setRoutingTestResult(data.routing || data);
      setNotice(data.routing?.sentAgentReply ? "Phone Number ID routed correctly and the agent reply test was processed." : "Phone Number ID routing test passed. It resolves to this selected business.");
      await loadWorkspace();
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to test WhatsApp webhook routing by Phone Number ID.");
      await loadWorkspace();
    } finally {
      setIsTestingRouting(false);
    }
  }

  async function handleLiveWebhookTest(event) {
    event.preventDefault();
    if (!selectedTenant) return;
    setIsTestingLiveWebhook(true);
    setError("");
    setNotice("");
    setLiveWebhookResult(null);
    try {
      const data = await testWhatsAppLiveWebhookPayload(selectedTenant.id, liveWebhookForm);
      setLiveWebhookResult(data);
      setNotice(data.mode === "processed_with_agent" ? "Webhook payload processed through the live WhatsApp agent flow." : "Webhook payload parsed and routed in dry-run mode without sending an AI reply.");
      await loadWorkspace();
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to run WhatsApp live webhook troubleshooting test.");
      await loadWorkspace();
    } finally {
      setIsTestingLiveWebhook(false);
    }
  }

  async function handleLoadTimeline(conversationId) {
    if (!selectedTenant || !conversationId) return;
    setIsLoadingTimeline(true);
    setError("");
    try {
      const data = await getWhatsAppConversationTimeline(selectedTenant.id, conversationId);
      setSelectedTimeline(data);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to load WhatsApp conversation timeline.");
    } finally {
      setIsLoadingTimeline(false);
    }
  }

  async function handleRecordGoLiveTest(event) {
    event.preventDefault();
    if (!selectedTenant) return;
    setIsRecordingGoLive(true);
    setError("");
    setNotice("");
    setGoLiveResult(null);
    try {
      const data = await recordWhatsAppGoLiveTestRun(selectedTenant.id, goLiveForm);
      setGoLive(data.phaseJ || null);
      setGoLiveResult(data.testRun || null);
      setNotice("Phase J WhatsApp go-live test run recorded successfully.");
      await loadWorkspace();
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to record WhatsApp go-live test run.");
    } finally {
      setIsRecordingGoLive(false);
    }
  }

  if (isLoadingTenants || isLoadingModules) {
    return <section className="text-sm text-muted">Loading WhatsApp agent workspace...</section>;
  }

  if (!selectedTenant) {
    return <section className="text-sm text-muted">Select a business first to configure its WhatsApp agent.</section>;
  }

  if (!aiEnabled) {
    return <section className="text-sm text-muted">Enable AI Chat first. The WhatsApp Agent depends on the same RAG and ordering brain.</section>;
  }

  if (!whatsappEnabled) {
    return <section className="text-sm text-muted">Enable the WhatsApp Agent module from Modules before connecting a WhatsApp number.</section>;
  }

  return (
    <section className="space-y-6">
      <div className="rounded-md border border-line bg-white p-5 shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="text-sm font-semibold uppercase tracking-wide text-brand">Phase 22</p>
            <h1 className="mt-2 text-3xl font-semibold text-ink">WhatsApp Agent Integration</h1>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-muted">
              Connect the owner&apos;s WhatsApp number so customer questions that were previously handled manually can now be answered by the BizXus AI agent using RAG, catalog data, and draft order planning.
            </p>
          </div>
          <div className={connected ? "rounded-md border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700" : "rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800"}>
            <div className="font-semibold">
              {connected ? "Connected" : connectionStatus === "pending_token_exchange" ? "Pending token exchange" : "Not connected"}
            </div>
            <div className="mt-1">Provider: {settings?.provider || form.provider}</div>
            <div className="mt-1 text-xs">Status: {connectionStatus.replaceAll("_", " ")}</div>
            <div className="mt-1 text-xs">
              {(settings?.provider || form.provider) === "mock"
                ? "Mock mode replies inside this dashboard only; it will not send messages to your real WhatsApp app."
                : "Meta Cloud mode requires a real access token, phone number ID, test recipient, and public HTTPS webhook."}
            </div>
          </div>
        </div>
      </div>

      {notice ? <div className="rounded-md border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">{notice}</div> : null}
      {error ? <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}
      {isLoading ? <div className="text-sm text-muted">Loading settings...</div> : null}

      <div className="rounded-md border border-line bg-white p-5 shadow-sm">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="text-sm font-semibold uppercase tracking-wide text-brand">Phase A</p>
            <h2 className="mt-1 text-2xl font-semibold text-ink">Meta App preparation</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-muted">
              Prepare the Meta Developer App before Embedded Signup. This phase does not connect a business yet; it confirms the app ID, Embedded Signup configuration,
              public HTTPS backend URL, callback URL, and webhook verify token are ready.
            </p>
          </div>
          <div className={metaSetup?.ready ? "rounded-md border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700" : "rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800"}>
            <div className="font-semibold">{metaSetup?.ready ? "Meta setup ready" : "Meta setup needs values"}</div>
            <div className="mt-1 text-xs">{metaSetup?.ready ? "You can move to Embedded Signup UI next." : "Add missing values to backend .env, then restart backend."}</div>
          </div>
        </div>
        <div className="mt-5 grid gap-3 md:grid-cols-2">
          {(metaSetup?.checks || []).map((check) => (
            <div key={check.code} className={check.status === "pass" ? "rounded-md border border-green-100 bg-green-50 px-3 py-3 text-sm" : "rounded-md border border-amber-100 bg-amber-50 px-3 py-3 text-sm"}>
              <div className={check.status === "pass" ? "font-semibold text-green-800" : "font-semibold text-amber-900"}>
                {check.status === "pass" ? "Ready" : "Missing"}: {check.label}
              </div>
              <div className={check.status === "pass" ? "mt-1 break-all text-xs leading-5 text-green-700" : "mt-1 break-all text-xs leading-5 text-amber-800"}>
                {check.message}
              </div>
            </div>
          ))}
        </div>
        <div className="mt-5 grid gap-3 rounded-md border border-line bg-surface p-4 text-sm md:grid-cols-2">
          <div>
            <div className="font-semibold text-ink">Frontend callback URL</div>
            <div className="mt-1 break-all text-xs text-muted">{metaSetup?.frontendCallbackUrl || "Set FRONTEND_BASE_URL first."}</div>
          </div>
          <div>
            <div className="font-semibold text-ink">Backend webhook URL</div>
            <div className="mt-1 break-all text-xs text-muted">{metaSetup?.webhookCallbackUrl || "Set BACKEND_PUBLIC_URL first."}</div>
          </div>
          <div>
            <div className="font-semibold text-ink">Webhook verify token</div>
            <div className="mt-1 break-all text-xs text-muted">{metaSetup?.webhookVerifyToken || settings?.webhookVerifyToken || "Not set"}</div>
          </div>
          <div>
            <div className="font-semibold text-ink">Required Meta permissions</div>
            <div className="mt-1 text-xs text-muted">{(metaSetup?.requiredScopes || []).join(", ") || "whatsapp_business_management, whatsapp_business_messaging, business_management"}</div>
          </div>
        </div>
      </div>

      <div className="rounded-md border border-line bg-white p-5 shadow-sm">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div>
            <p className="text-sm font-semibold uppercase tracking-wide text-brand">Phase B</p>
            <h2 className="mt-1 text-2xl font-semibold text-ink">Connect WhatsApp with Meta</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-muted">
              Launch Meta Embedded Signup so the owner can select or add a WhatsApp Business number. This phase opens Meta and captures the browser response;
              Phase C saves the response in the backend as pending token exchange.
            </p>
          </div>
          <button
            className={metaSetup?.ready ? "rounded-md bg-ink px-5 py-3 text-sm font-semibold text-white hover:bg-slate-800" : "rounded-md bg-slate-200 px-5 py-3 text-sm font-semibold text-slate-500"}
            disabled={!metaSetup?.ready || isLaunchingMeta}
            onClick={handleConnectWithMeta}
            type="button"
          >
            {isLaunchingMeta ? "Opening Meta..." : "Connect with Meta"}
          </button>
        </div>
        <div className="mt-5 grid gap-3 md:grid-cols-5">
          {[
            ["connect", "Step 1", "Connect WhatsApp", ["idle", "blocked"].includes(signupStep)],
            ["meta", "Step 2", "Complete Meta signup", ["loading_sdk", "popup_open", "in_progress"].includes(signupStep)],
            ["verify", "Step 3", "Verify phone number", signupStep === "completed" || signupStep === "code_received"],
            ["ready", "Step 4", "Exchange token", ["code_received", "completed", "pending_token_exchange", "token_exchanged"].includes(signupStep)],
            ["phone", "Step 5", "Register phone", ["webhook_subscribed", "phone_registration_failed", "phone_registered"].includes(signupStep) || settings?.webhookSubscriptionStatus === "subscribed"],
          ].map(([key, step, label, active]) => (
            <div key={key} className={active ? "rounded-md border border-blue-200 bg-blue-50 p-3" : "rounded-md border border-line bg-surface p-3"}>
              <div className={active ? "text-xs font-bold uppercase tracking-wide text-brand" : "text-xs font-bold uppercase tracking-wide text-muted"}>{step}</div>
              <div className="mt-1 text-sm font-semibold text-ink">{label}</div>
            </div>
          ))}
        </div>
        <div className="mt-4 rounded-md border border-line bg-surface p-4 text-sm">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <div className="font-semibold text-ink">Signup browser status</div>
              <div className="mt-1 text-xs text-muted">
                Current state: <span className="font-semibold">{signupStep.replaceAll("_", " ")}</span>
              </div>
            </div>
            <div className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-muted">
              Mock mode remains available below for FYP demo testing.
            </div>
          </div>
          {signupResponse ? (
            <div className="mt-4 rounded-md border border-blue-100 bg-white p-3">
              <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                <div>
                  <div className="font-semibold text-ink">Captured signup response preview</div>
                  <p className="mt-1 text-xs leading-5 text-muted">
                    Phase C stores the authorization code and selected WhatsApp IDs securely on the backend. The code is masked in future settings responses.
                  </p>
                </div>
                <button
                  className="rounded-md bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:bg-slate-200 disabled:text-slate-500"
                  disabled={isCapturingSignup}
                  onClick={handleCaptureSignup}
                  type="button"
                >
                  {isCapturingSignup ? "Saving..." : "Save signup response"}
                </button>
              </div>
              <pre className="mt-2 max-h-52 overflow-auto whitespace-pre-wrap break-words rounded-md bg-slate-950 p-3 text-xs text-slate-100">
                {JSON.stringify(
                  {
                    status: signupResponse.status,
                    hasAuthorizationCode: Boolean(buildSignupCapturePayload(signupResponse).authorizationCode),
                    embeddedSignupEvent: signupResponse.embeddedSignup?.event,
                    embeddedSignupData: signupResponse.embeddedSignup?.data,
                    callbackQueryReceived: Boolean(signupResponse.callbackQuery && Object.keys(signupResponse.callbackQuery).length),
                  },
                  null,
                  2,
                )}
              </pre>
            </div>
          ) : (
            <div className="mt-4 rounded-md border border-dashed border-line bg-white p-3 text-xs leading-5 text-muted">
              No Meta signup response captured yet. Click Connect with Meta after Phase A is ready.
            </div>
          )}
          {settings?.status === "pending_token_exchange" || settings?.connectionStatus === "pending_token_exchange" ? (
            <div className="mt-4 rounded-md border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-800">
              <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div>
                  Signup response is saved for this business. Current status: <span className="font-semibold">pending token exchange</span>.
                  Phase D will exchange the code for a business token.
                </div>
                <button
                  className="rounded-md bg-ink px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:bg-slate-200 disabled:text-slate-500"
                  disabled={isExchangingToken}
                  onClick={handleExchangeToken}
                  type="button"
                >
                  {isExchangingToken ? "Exchanging..." : "Exchange token"}
                </button>
              </div>
            </div>
          ) : null}
          {["token_exchanged", "webhook_subscription_failed", "webhook_subscribed", "phone_registration_failed", "phone_registered"].includes(settings?.connectionStatus) ? (
            <div className={settings?.webhookSubscriptionStatus === "subscribed" ? "mt-4 rounded-md border border-green-200 bg-green-50 p-3 text-xs leading-5 text-green-800" : "mt-4 rounded-md border border-blue-200 bg-blue-50 p-3 text-xs leading-5 text-blue-800"}>
              <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                <div>
                  <div className="font-semibold">Phase E: Subscribe WABA webhooks</div>
                  <p className="mt-1">
                    Meta business token is saved securely. Webhook subscription status:{" "}
                    <span className="font-semibold">{settings?.webhookSubscriptionStatus || "pending"}</span>. Phone registration status:{" "}
                    <span className="font-semibold">{settings?.phoneRegistrationStatus || "pending"}</span>.
                  </p>
                  <p className="mt-1">
                    This step calls Meta for the connected WhatsApp Business Account so incoming customer WhatsApp messages are delivered to your backend webhook URL.
                  </p>
                  <div className="mt-2 break-all rounded-md bg-white/80 px-3 py-2">Webhook URL: {metaSetup?.webhookCallbackUrl || webhookUrl}</div>
                </div>
                <button
                  className="rounded-md bg-ink px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:bg-slate-200 disabled:text-slate-500"
                  disabled={isSubscribingWebhooks || settings?.webhookSubscriptionStatus === "subscribed"}
                  onClick={handleSubscribeWebhooks}
                  type="button"
                >
                  {settings?.webhookSubscriptionStatus === "subscribed" ? "Webhooks subscribed" : isSubscribingWebhooks ? "Subscribing..." : "Subscribe webhooks"}
                </button>
              </div>
              {settings?.lastError ? <div className="mt-3 rounded-md border border-red-100 bg-red-50 px-3 py-2 text-red-700">Last error: {settings.lastError}</div> : null}
            </div>
          ) : null}
          {settings?.webhookSubscriptionStatus === "subscribed" ? (
            <div className={settings?.phoneRegistrationStatus === "registered" ? "mt-4 rounded-md border border-green-200 bg-green-50 p-3 text-xs leading-5 text-green-800" : "mt-4 rounded-md border border-purple-200 bg-purple-50 p-3 text-xs leading-5 text-purple-900"}>
              <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <div className="font-semibold">Phase F: Register phone number</div>
                  <p className="mt-1">
                    Webhooks are subscribed. Now register this verified WhatsApp phone number for Cloud API use by setting a 6-digit two-step verification PIN.
                    Current phone registration status: <span className="font-semibold">{settings?.phoneRegistrationStatus || "pending"}</span>.
                  </p>
                  <p className="mt-1">
                    BizXusAI sends this PIN once to Meta and does not store it. Keep the PIN safe because Meta may ask for it later when changing two-step verification or migrating the number.
                  </p>
                  <div className="mt-2 break-all rounded-md bg-white/80 px-3 py-2">Phone Number ID: {settings?.phoneNumberId || "Missing"}</div>
                </div>
                {settings?.phoneRegistrationStatus === "registered" ? (
                  <div className="rounded-md bg-white px-4 py-2 text-sm font-semibold text-green-700">Phone registered</div>
                ) : (
                  <div className="w-full max-w-xs space-y-2">
                    <input
                      className="w-full rounded-md border border-line px-3 py-2 text-sm"
                      inputMode="numeric"
                      maxLength={6}
                      pattern="[0-9]{6}"
                      value={phoneRegistrationPin}
                      onChange={(event) => setPhoneRegistrationPin(event.target.value.replace(/\D/g, "").slice(0, 6))}
                      placeholder="6-digit PIN"
                    />
                    <button
                      className="w-full rounded-md bg-ink px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:bg-slate-200 disabled:text-slate-500"
                      disabled={isRegisteringPhone || phoneRegistrationPin.length !== 6}
                      onClick={handleRegisterPhone}
                      type="button"
                    >
                      {isRegisteringPhone ? "Registering..." : "Register phone number"}
                    </button>
                  </div>
                )}
              </div>
              {settings?.connectionStatus === "phone_registration_failed" && settings?.lastError ? (
                <div className="mt-3 rounded-md border border-red-100 bg-red-50 px-3 py-2 text-red-700">Last error: {settings.lastError}</div>
              ) : null}
            </div>
          ) : null}

          {settings?.phoneRegistrationStatus === "registered" ? (
            <div className={routingStatus?.ready ? "mt-4 rounded-md border border-green-200 bg-green-50 p-3 text-xs leading-5 text-green-800" : "mt-4 rounded-md border border-indigo-200 bg-indigo-50 p-3 text-xs leading-5 text-indigo-900"}>
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div className="min-w-0 flex-1">
                  <div className="font-semibold">Phase G: Webhook routing by Phone Number ID</div>
                  <p className="mt-1">
                    Incoming Meta webhooks are routed using <span className="font-semibold">metadata.phone_number_id</span>. This allows multiple businesses to share one BizXusAI webhook while each customer message goes to the correct tenant agent.
                  </p>
                  <div className="mt-2 grid gap-2 md:grid-cols-2">
                    <div className="break-all rounded-md bg-white/80 px-3 py-2">Phone Number ID: {routingStatus?.phoneNumberId || settings?.phoneNumberId || "Missing"}</div>
                    <div className="break-all rounded-md bg-white/80 px-3 py-2">Routing status: {routingStatus?.ready ? "Ready" : "Needs setup"}</div>
                    <div className="break-all rounded-md bg-white/80 px-3 py-2">Last webhook: {formatDate(routingStatus?.lastWebhookReceivedAt)}</div>
                    <div className="break-all rounded-md bg-white/80 px-3 py-2">Webhook URL: {routingStatus?.webhookCallbackUrl || metaSetup?.webhookCallbackUrl || webhookUrl}</div>
                  </div>
                  {routingStatus?.missing?.length ? (
                    <div className="mt-2 rounded-md border border-amber-100 bg-amber-50 px-3 py-2 text-amber-800">Missing: {routingStatus.missing.join(", ")}</div>
                  ) : null}
                </div>
                <form className="w-full max-w-sm space-y-2 rounded-md bg-white/90 p-3" onSubmit={handleTestRouting}>
                  <div className="font-semibold text-ink">Test routing</div>
                  <input className="w-full rounded-md border border-line px-3 py-2 text-sm" value={routingTestForm.customerPhone} onChange={(event) => setRoutingTestForm((current) => ({ ...current, customerPhone: event.target.value }))} placeholder="Customer phone" />
                  <input className="w-full rounded-md border border-line px-3 py-2 text-sm" value={routingTestForm.customerName} onChange={(event) => setRoutingTestForm((current) => ({ ...current, customerName: event.target.value }))} placeholder="Customer name" />
                  <textarea className="min-h-16 w-full rounded-md border border-line px-3 py-2 text-sm" value={routingTestForm.messageText} onChange={(event) => setRoutingTestForm((current) => ({ ...current, messageText: event.target.value }))} />
                  <label className="flex items-center gap-2 text-xs text-muted">
                    <input type="checkbox" checked={routingTestForm.sendReply} onChange={(event) => setRoutingTestForm((current) => ({ ...current, sendReply: event.target.checked }))} />
                    Also process agent reply. In Meta mode this may send a real WhatsApp message.
                  </label>
                  <button className="w-full rounded-md bg-ink px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:bg-slate-200 disabled:text-slate-500" disabled={isTestingRouting || !routingStatus?.ready} type="submit">
                    {isTestingRouting ? "Testing..." : "Test Phone Number ID routing"}
                  </button>
                  {routingTestResult ? (
                    <div className="rounded-md border border-green-100 bg-green-50 px-3 py-2 text-xs text-green-800">
                      Routed to: {routingTestResult.matchedBusinessName || selectedTenant.name} ({routingTestResult.phoneNumberId || settings?.phoneNumberId})
                    </div>
                  ) : null}
                </form>
              </div>
            </div>
          ) : null}

          {settings?.phoneRegistrationStatus === "registered" ? (
            <div className={routingStatus?.ready ? "mt-4 rounded-md border border-green-200 bg-green-50 p-3 text-xs leading-5 text-green-800" : "mt-4 rounded-md border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-800"}>
              <div className="font-semibold">Phase H: Live WhatsApp AI replies</div>
              <p className="mt-1">
                After routing is ready, real incoming WhatsApp messages are passed to the same BizXusAI AI/RAG/catalog/order agent used by customer chat. The agent creates draft orders, collects delivery/pickup details, confirms orders from WhatsApp, saves transactions, reserves stock, and notifies the owner.
              </p>
              <div className="mt-2 grid gap-2 md:grid-cols-3">
                <div className="rounded-md bg-white/80 px-3 py-2">Agent: {settings?.agentEnabled === false ? "Paused" : "Enabled"}</div>
                <div className="rounded-md bg-white/80 px-3 py-2">Auto reply: {settings?.autoReplyEnabled === false ? "Off" : "On"}</div>
                <div className="rounded-md bg-white/80 px-3 py-2">Live ready: {routingStatus?.ready && settings?.agentEnabled !== false && settings?.autoReplyEnabled !== false ? "Yes" : "Needs setup"}</div>
              </div>
              <p className="mt-2 text-xs">
                Test sequence: send “2 zinger burgers order kar do”, then “delivery”, then “House 12, Attock”, then “confirm”. A confirmed WhatsApp order should appear in Transactions.
              </p>
            </div>
          ) : null}
        </div>
      </div>

      <div className="rounded-md border border-line bg-white p-5 shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="text-sm font-semibold uppercase tracking-wide text-brand">Phase I</p>
            <h2 className="mt-1 text-2xl font-semibold text-ink">Live Meta troubleshooting & conversation timeline</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-muted">
              Use this panel after Embedded Signup, webhook subscription, phone registration, and routing are configured. It helps verify the live WhatsApp setup, inspect recent webhook events, and debug why a real customer message did or did not receive an AI reply.
            </p>
          </div>
          <div className={diagnostics?.overallStatus === "ready" ? "rounded-md border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700" : diagnostics?.overallStatus === "warning" ? "rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800" : "rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"}>
            <div className="font-semibold">{diagnostics?.overallStatus ? diagnostics.overallStatus.replaceAll("_", " ") : "Not checked"}</div>
            <div className="mt-1 text-xs">Live replies: {diagnostics?.readyForLiveReplies ? "Ready" : "Needs setup"}</div>
          </div>
        </div>

        <div className="mt-5 grid gap-3 md:grid-cols-2">
          <div className="rounded-md border border-line bg-surface p-4 text-sm">
            <div className="font-semibold text-ink">Live URLs</div>
            <div className="mt-3 space-y-2 text-xs text-muted">
              <div className="break-all rounded-md bg-white px-3 py-2">Webhook URL: {diagnostics?.webhookUrl || metaSetup?.webhookCallbackUrl || webhookUrl}</div>
              <div className="break-all rounded-md bg-white px-3 py-2">Callback URL: {diagnostics?.frontendCallbackUrl || metaSetup?.frontendCallbackUrl || "Set FRONTEND_BASE_URL"}</div>
              <div className="break-all rounded-md bg-white px-3 py-2">Verify token: {diagnostics?.verifyToken || settings?.webhookVerifyToken || "Not set"}</div>
            </div>
          </div>
          <form className="space-y-3 rounded-md border border-line bg-surface p-4" onSubmit={handleLiveWebhookTest}>
            <div>
              <div className="font-semibold text-ink">Webhook payload tester</div>
              <p className="mt-1 text-xs leading-5 text-muted">Dry run checks parsing/routing only. Processing with agent may send a real WhatsApp reply in Meta mode.</p>
            </div>
            <input className="w-full rounded-md border border-line px-3 py-2 text-sm" value={liveWebhookForm.customerPhone} onChange={(event) => setLiveWebhookForm((current) => ({ ...current, customerPhone: event.target.value }))} placeholder="Customer phone" />
            <input className="w-full rounded-md border border-line px-3 py-2 text-sm" value={liveWebhookForm.customerName} onChange={(event) => setLiveWebhookForm((current) => ({ ...current, customerName: event.target.value }))} placeholder="Customer name" />
            <textarea className="min-h-16 w-full rounded-md border border-line px-3 py-2 text-sm" value={liveWebhookForm.messageText} onChange={(event) => setLiveWebhookForm((current) => ({ ...current, messageText: event.target.value }))} />
            <label className="flex items-start gap-2 text-xs leading-5 text-muted">
              <input className="mt-1" type="checkbox" checked={liveWebhookForm.processWithAgent} onChange={(event) => setLiveWebhookForm((current) => ({ ...current, processWithAgent: event.target.checked }))} />
              Process through AI agent. In Meta mode, this can send an outbound WhatsApp message to the test customer.
            </label>
            <button className="w-full rounded-md bg-ink px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:bg-slate-200 disabled:text-slate-500" disabled={isTestingLiveWebhook || !settings?.phoneNumberId} type="submit">
              {isTestingLiveWebhook ? "Testing..." : "Run webhook test"}
            </button>
            {liveWebhookResult ? (
              <div className="rounded-md border border-blue-100 bg-blue-50 px-3 py-2 text-xs leading-5 text-blue-800">
                Mode: {liveWebhookResult.mode}. Processed: {liveWebhookResult.processed?.processedCount ?? liveWebhookResult.processed?.items?.length ?? 0}. Errors: {liveWebhookResult.processed?.errorCount ?? 0}.
              </div>
            ) : null}
          </form>
        </div>

        <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {(diagnostics?.checklist || []).map((check) => (
            <div key={check.code} className={check.status === "pass" ? "rounded-md border border-green-100 bg-green-50 p-3 text-sm" : check.status === "warn" ? "rounded-md border border-amber-100 bg-amber-50 p-3 text-sm" : "rounded-md border border-red-100 bg-red-50 p-3 text-sm"}>
              <div className={check.status === "pass" ? "font-semibold text-green-800" : check.status === "warn" ? "font-semibold text-amber-900" : "font-semibold text-red-800"}>{check.status.toUpperCase()}: {check.label}</div>
              <div className="mt-1 text-xs leading-5 text-muted">{check.detail}</div>
              {check.fix ? <div className="mt-2 text-xs leading-5 text-ink">Fix: {check.fix}</div> : null}
            </div>
          ))}
        </div>

        <div className="mt-5 grid gap-4 lg:grid-cols-2">
          <div className="rounded-md border border-line bg-surface p-4">
            <div className="font-semibold text-ink">Recent routing events</div>
            <div className="mt-3 max-h-72 space-y-2 overflow-auto text-xs">
              {(diagnostics?.recentRoutingEvents || []).length ? diagnostics.recentRoutingEvents.map((event) => (
                <div key={event.id} className="rounded-md bg-white px-3 py-2">
                  <div className="font-semibold text-ink">{event.eventType || "event"} · {event.statusText || "logged"}</div>
                  <div className="mt-1 break-all text-muted">{event.detail || event.phoneNumberId}</div>
                  <div className="mt-1 text-muted">{formatDate(event.createdAt)}</div>
                </div>
              )) : <div className="rounded-md bg-white px-3 py-4 text-muted">No routing events yet.</div>}
            </div>
          </div>
          <div className="rounded-md border border-line bg-surface p-4">
            <div className="font-semibold text-ink">Recent provider message logs</div>
            <div className="mt-3 max-h-72 space-y-2 overflow-auto text-xs">
              {(diagnostics?.recentLogs || []).length ? diagnostics.recentLogs.map((log) => (
                <div key={log.id} className={log.deliveryStatus === "failed" || log.providerStatus === "failed" ? "rounded-md border border-red-100 bg-red-50 px-3 py-2" : "rounded-md bg-white px-3 py-2"}>
                  <div className="font-semibold text-ink">{log.direction || "message"} · {log.deliveryStatus || log.providerStatus || "logged"}</div>
                  <div className="mt-1 line-clamp-2 text-muted">{log.messageText || log.error || log.providerMessageId}</div>
                  <div className="mt-1 text-muted">{formatDate(log.createdAt)}</div>
                </div>
              )) : <div className="rounded-md bg-white px-3 py-4 text-muted">No provider logs yet.</div>}
            </div>
          </div>
        </div>

        {diagnostics?.tips?.length ? (
          <div className="mt-5 rounded-md border border-blue-100 bg-blue-50 p-4 text-xs leading-5 text-blue-900">
            <div className="font-semibold">Troubleshooting tips</div>
            <ul className="mt-2 list-disc space-y-1 pl-5">
              {diagnostics.tips.map((tip) => <li key={tip}>{tip}</li>)}
            </ul>
          </div>
        ) : null}
      </div>


      <div className="rounded-md border border-line bg-white p-5 shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="text-sm font-semibold uppercase tracking-wide text-brand">Phase J</p>
            <h2 className="mt-1 text-2xl font-semibold text-ink">Go-live acceptance test & final runbook</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-muted">
              Use this final panel after Phases E–I. It tells you whether the connected Meta WhatsApp number is ready for a real customer test, gives the exact runbook, and records the final supervisor/live test result.
            </p>
          </div>
          <div className={goLive?.overallStatus === "ready_for_live" ? "rounded-md border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700" : goLive?.overallStatus === "ready_for_demo" ? "rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800" : "rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"}>
            <div className="font-semibold">{goLive?.overallStatus ? goLive.overallStatus.replaceAll("_", " ") : "Not checked"}</div>
            <div className="mt-1 text-xs">Required failures: {goLive?.requiredFailures ?? "-"}</div>
            <div className="mt-1 text-xs">Warnings: {goLive?.warningCount ?? "-"}</div>
          </div>
        </div>

        <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {(goLive?.checklist || []).map((check) => (
            <div key={check.code} className={check.status === "pass" ? "rounded-md border border-green-100 bg-green-50 p-3 text-sm" : check.status === "warn" ? "rounded-md border border-amber-100 bg-amber-50 p-3 text-sm" : "rounded-md border border-red-100 bg-red-50 p-3 text-sm"}>
              <div className={check.status === "pass" ? "font-semibold text-green-800" : check.status === "warn" ? "font-semibold text-amber-900" : "font-semibold text-red-800"}>{check.status.toUpperCase()}: {check.label}</div>
              <div className="mt-1 text-xs leading-5 text-muted">{check.detail}</div>
              {check.fix ? <div className="mt-2 text-xs leading-5 text-ink">Fix: {check.fix}</div> : null}
            </div>
          ))}
        </div>

        <div className="mt-5 grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
          <div className="rounded-md border border-blue-100 bg-blue-50 p-4 text-sm text-blue-950">
            <div className="font-semibold">Final live test runbook</div>
            <ol className="mt-3 list-decimal space-y-2 pl-5 text-xs leading-5">
              {(goLive?.runbook || [
                "Send a real or mock WhatsApp message to the connected business number.",
                "Confirm the AI replies from the correct business catalog/RAG.",
                "Test order flow and handoff flow.",
                "Record the result here before demo."
              ]).map((step) => <li key={step}>{step}</li>)}
            </ol>
            <div className="mt-4 grid gap-2 text-xs md:grid-cols-2">
              <div className="rounded-md bg-white px-3 py-2">Conversations: {goLive?.recentCounts?.whatsappConversations ?? 0}</div>
              <div className="rounded-md bg-white px-3 py-2">Orders: {goLive?.recentCounts?.whatsappTransactions ?? 0}</div>
              <div className="rounded-md bg-white px-3 py-2">Inbound logs: {goLive?.recentCounts?.recentInboundLogs ?? 0}</div>
              <div className="rounded-md bg-white px-3 py-2">Outbound replies: {goLive?.recentCounts?.recentOutboundReplies ?? 0}</div>
            </div>
            {goLive?.latestRun ? (
              <div className="mt-4 rounded-md border border-white/70 bg-white px-3 py-2 text-xs">
                Latest recorded run: <span className="font-semibold">{goLive.latestRun.result}</span> · {formatDate(goLive.latestRun.createdAt)}
              </div>
            ) : null}
          </div>

          <form className="space-y-3 rounded-md border border-line bg-surface p-4" onSubmit={handleRecordGoLiveTest}>
            <div>
              <div className="font-semibold text-ink">Record Phase J test run</div>
              <p className="mt-1 text-xs leading-5 text-muted">Tick what you verified manually with a real Meta customer message or with mock mode for FYP demo.</p>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <input className="rounded-md border border-line px-3 py-2 text-sm" value={goLiveForm.customerPhone} onChange={(event) => setGoLiveForm((current) => ({ ...current, customerPhone: event.target.value }))} placeholder="Customer phone" />
              <input className="rounded-md border border-line px-3 py-2 text-sm" value={goLiveForm.customerName} onChange={(event) => setGoLiveForm((current) => ({ ...current, customerName: event.target.value }))} placeholder="Customer name" />
            </div>
            <textarea className="min-h-16 w-full rounded-md border border-line px-3 py-2 text-sm" value={goLiveForm.testMessage} onChange={(event) => setGoLiveForm((current) => ({ ...current, testMessage: event.target.value }))} placeholder="Test message sent by customer" />
            <div className="grid gap-2 text-xs md:grid-cols-2">
              {[
                ["realCustomerMessageReceived", "Customer message received"],
                ["aiReplyDelivered", "AI reply delivered"],
                ["conversationVisible", "Conversation visible in dashboard"],
                ["orderFlowTested", "Order flow tested"],
                ["orderCreated", "Order created in Transactions"],
                ["handoffTested", "Human handoff tested"],
                ["ownerNotificationCreated", "Owner notification created"],
              ].map(([key, label]) => (
                <label key={key} className="flex items-start gap-2 rounded-md bg-white px-3 py-2 text-muted">
                  <input className="mt-0.5" type="checkbox" checked={Boolean(goLiveForm[key])} onChange={(event) => setGoLiveForm((current) => ({ ...current, [key]: event.target.checked }))} />
                  {label}
                </label>
              ))}
            </div>
            <select className="w-full rounded-md border border-line px-3 py-2 text-sm" value={goLiveForm.result} onChange={(event) => setGoLiveForm((current) => ({ ...current, result: event.target.value }))}>
              <option value="auto">Auto result</option>
              <option value="passed">Passed</option>
              <option value="warning">Passed with warning</option>
              <option value="failed">Failed</option>
            </select>
            <textarea className="min-h-16 w-full rounded-md border border-line px-3 py-2 text-sm" value={goLiveForm.notes} onChange={(event) => setGoLiveForm((current) => ({ ...current, notes: event.target.value }))} placeholder="Notes / issue found" />
            <button className="w-full rounded-md bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:bg-slate-200 disabled:text-slate-500" disabled={isRecordingGoLive} type="submit">
              {isRecordingGoLive ? "Recording..." : "Record go-live test"}
            </button>
            {goLiveResult ? (
              <div className="rounded-md border border-green-100 bg-green-50 px-3 py-2 text-xs text-green-800">
                Recorded result: {goLiveResult.result} · {formatDate(goLiveResult.createdAt)}
              </div>
            ) : null}
          </form>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <form onSubmit={handleSave} className="space-y-5 rounded-md border border-line bg-white p-5 shadow-sm">
          <div>
            <h2 className="text-lg font-semibold text-ink">Connection settings</h2>
            <p className="mt-1 text-sm text-muted">Use mock provider for FYP demo. Use Meta Cloud only when real WhatsApp Cloud API credentials are available.</p>
            {form.provider === "mock" ? (
              <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-800">
                Mock mode means: use the simulator below, AI will reply and save WhatsApp conversations in BizXusAI, but no message will arrive on your personal WhatsApp number.
              </div>
            ) : (
              <div className="mt-3 rounded-md border border-blue-200 bg-blue-50 p-3 text-xs leading-5 text-blue-800">
                Real WhatsApp checklist: Meta Developer App, WhatsApp Cloud API, Phone Number ID, permanent/temporary access token, webhook verify token, ngrok/public HTTPS URL, and approved test recipient number.
                The number entered here must be the same WhatsApp number registered inside Meta Cloud API. A normal personal WhatsApp number cannot auto-reply unless it is onboarded in Meta and has its own Phone Number ID.
              </div>
            )}
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <label className="text-sm font-medium text-ink">
              Provider
              <select className="mt-2 w-full rounded-md border border-line px-3 py-2 text-sm" value={form.provider} onChange={(event) => updateForm("provider", event.target.value)}>
                <option value="mock">Mock / FYP demo</option>
                <option value="meta_cloud">Meta WhatsApp Cloud API</option>
              </select>
            </label>
            <label className="text-sm font-medium text-ink">
              Business WhatsApp number
              <input className="mt-2 w-full rounded-md border border-line px-3 py-2 text-sm" value={form.businessWhatsAppNumber} onChange={(event) => updateForm("businessWhatsAppNumber", event.target.value)} placeholder="+923001234567" required />
              <span className="mt-1 block text-xs font-normal text-muted">
                For real replies, this must be a WhatsApp Cloud API number, not only the owner&apos;s personal WhatsApp contact.
              </span>
            </label>
            <label className="text-sm font-medium text-ink">
              Display name
              <input className="mt-2 w-full rounded-md border border-line px-3 py-2 text-sm" value={form.displayName} onChange={(event) => updateForm("displayName", event.target.value)} placeholder={selectedTenant.name} />
            </label>
            <label className="text-sm font-medium text-ink">
              Phone number ID
              <input className="mt-2 w-full rounded-md border border-line px-3 py-2 text-sm" value={form.phoneNumberId} onChange={(event) => updateForm("phoneNumberId", event.target.value)} placeholder="Only for Meta Cloud API" />
              <span className="mt-1 block text-xs font-normal text-muted">
                This decides which WhatsApp number sends the AI reply. Each business must use a unique Phone Number ID.
              </span>
            </label>
            <label className="text-sm font-medium text-ink">
              WhatsApp Business Account ID
              <input className="mt-2 w-full rounded-md border border-line px-3 py-2 text-sm" value={form.whatsappBusinessAccountId} onChange={(event) => updateForm("whatsappBusinessAccountId", event.target.value)} placeholder="WABA ID from Meta dashboard" />
            </label>
            <label className="text-sm font-medium text-ink">
              API version
              <input className="mt-2 w-full rounded-md border border-line px-3 py-2 text-sm" value={form.apiVersion} onChange={(event) => updateForm("apiVersion", event.target.value)} />
            </label>
            <label className="text-sm font-medium text-ink">
              Access token
              <input className="mt-2 w-full rounded-md border border-line px-3 py-2 text-sm" value={form.accessToken} onChange={(event) => updateForm("accessToken", event.target.value)} placeholder={settings?.accessTokenMasked || "Only for Meta Cloud API"} type="password" />
              <span className="mt-1 block text-xs font-normal text-muted">
                {settings?.hasAccessToken ? "A token is saved securely. Leave blank to keep it." : "Required only for real Meta Cloud mode."}
              </span>
            </label>
          </div>

          <label className="block text-sm font-medium text-ink">
            Welcome message
            <textarea className="mt-2 min-h-24 w-full rounded-md border border-line px-3 py-2 text-sm" value={form.welcomeMessage} onChange={(event) => updateForm("welcomeMessage", event.target.value)} />
          </label>

          <label className="block text-sm font-medium text-ink">
            Default fallback reply
            <textarea className="mt-2 min-h-20 w-full rounded-md border border-line px-3 py-2 text-sm" value={form.fallbackReply} onChange={(event) => updateForm("fallbackReply", event.target.value)} />
            <span className="mt-1 block text-xs font-normal text-muted">Used when the AI cannot answer, the agent is paused, or a safe owner review is needed.</span>
          </label>

          <div className="grid gap-4 md:grid-cols-3">
            <label className="flex items-center gap-2 rounded-md border border-line bg-surface px-3 py-3 text-sm text-ink">
              <input type="checkbox" checked={form.agentEnabled} onChange={(event) => updateForm("agentEnabled", event.target.checked)} />
              Agent enabled
            </label>
            <label className="flex items-center gap-2 rounded-md border border-line bg-surface px-3 py-3 text-sm text-ink">
              <input type="checkbox" checked={form.autoReplyEnabled} onChange={(event) => updateForm("autoReplyEnabled", event.target.checked)} />
              Auto-reply with AI agent
            </label>
            <label className="flex items-center gap-2 rounded-md border border-line bg-surface px-3 py-3 text-sm text-ink">
              <input type="checkbox" checked={form.handoffEnabled} onChange={(event) => updateForm("handoffEnabled", event.target.checked)} />
              Allow human handoff keywords
            </label>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <label className="block text-sm font-medium text-ink">
              Handoff keywords
              <input className="mt-2 w-full rounded-md border border-line px-3 py-2 text-sm" value={form.handoffKeywords} onChange={(event) => updateForm("handoffKeywords", event.target.value)} />
              <span className="mt-1 block text-xs font-normal text-muted">Comma-separated words like human, owner, call me, insan.</span>
            </label>
            <label className="text-sm font-medium text-ink">
              Business hours behavior
              <select className="mt-2 w-full rounded-md border border-line px-3 py-2 text-sm" value={form.businessHoursMode} onChange={(event) => updateForm("businessHoursMode", event.target.value)}>
                <option value="always_on">Always reply with AI</option>
                <option value="business_hours">Reply during business hours</option>
                <option value="offline_handoff">Mark handoff outside hours</option>
              </select>
              <span className="mt-1 block text-xs font-normal text-muted">Business-hour scheduling is stored now and ready for the real provider rollout.</span>
            </label>
          </div>

          <div className="rounded-md bg-surface p-4 text-sm text-muted">
            <div className="font-semibold text-ink">Webhook URL</div>
            <div className="mt-1 break-all">{webhookUrl}</div>
            <div className="mt-3 font-semibold text-ink">Verify token</div>
            <div className="mt-1 break-all">{settings?.webhookVerifyToken || "Save settings to generate tenant verify token."}</div>
            <div className="mt-3 rounded-md border border-line bg-white p-3 text-xs leading-5">
              In Meta Developer Console, paste this callback URL, paste this verify token, then subscribe the WhatsApp webhook to messages.
              For local testing use an HTTPS tunnel like ngrok that points to your backend server.
            </div>
          </div>

          <div className="flex flex-wrap gap-3">
            <button className="rounded-md bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700" disabled={isSaving} type="submit">
              {isSaving ? "Saving..." : "Save / Connect"}
            </button>
            {connected ? (
              <button className="rounded-md border border-line px-4 py-2 text-sm font-semibold text-ink hover:bg-surface" onClick={handleDisconnect} type="button">
                Disconnect
              </button>
            ) : null}
          </div>
        </form>

        <div className="space-y-6">
          <form onSubmit={handleMockInbound} className="space-y-4 rounded-md border border-line bg-white p-5 shadow-sm">
            <div>
              <h2 className="text-lg font-semibold text-ink">Mock customer message</h2>
              <p className="mt-1 text-sm text-muted">Simulate a WhatsApp customer asking the agent a question or requesting an order.</p>
            </div>
            <div className="flex gap-2 overflow-x-auto pb-1">
              {["Menu bhej do", "Zinger burger available hai?", "2 zinger burgers order kar do", "delivery", "House 12, Attock", "confirm"].map((prompt) => (
                <button
                  key={prompt}
                  className="shrink-0 rounded-full border border-line bg-surface px-3 py-2 text-xs font-semibold text-muted hover:border-blue-200 hover:bg-blue-50 hover:text-brand"
                  type="button"
                  onClick={() => setMockForm((current) => ({ ...current, messageText: prompt }))}
                >
                  {prompt}
                </button>
              ))}
            </div>
            <input className="w-full rounded-md border border-line px-3 py-2 text-sm" value={mockForm.customerPhone} onChange={(event) => setMockForm((current) => ({ ...current, customerPhone: event.target.value }))} placeholder="Customer phone" />
            <input className="w-full rounded-md border border-line px-3 py-2 text-sm" value={mockForm.customerName} onChange={(event) => setMockForm((current) => ({ ...current, customerName: event.target.value }))} placeholder="Customer name" />
            <textarea className="min-h-28 w-full rounded-md border border-line px-3 py-2 text-sm" value={mockForm.messageText} onChange={(event) => setMockForm((current) => ({ ...current, messageText: event.target.value }))} />
            <button className="rounded-md bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700" disabled={!connected || isSimulating} type="submit">
              {isSimulating ? "Processing..." : "Process with AI"}
            </button>
            {lastResult ? (
              <div className="space-y-3 rounded-2xl border border-blue-100 bg-gradient-to-br from-blue-50 to-cyan-50 p-4 text-sm text-blue-950">
                <div className="flex items-center justify-between gap-3">
                  <div className="font-semibold">WhatsApp AI reply</div>
                  <span className={lastResult.handoffRequired ? "rounded-full bg-amber-100 px-2 py-1 text-xs font-bold text-amber-800" : "rounded-full bg-green-100 px-2 py-1 text-xs font-bold text-green-800"}>
                    {lastResult.handoffRequired ? "Handoff" : "AI reply"}
                  </span>
                </div>
                <div className="rounded-2xl rounded-bl-md bg-white px-4 py-3 shadow-sm">
                  <p className="leading-6">{lastResult.reply}</p>
                </div>
                {lastResult.confirmedTransaction ? (
                  <div className="rounded-2xl border border-green-200 bg-green-50 p-3 text-green-900">
                    <div className="font-semibold">Order confirmed from WhatsApp</div>
                    <div className="mt-1 text-xs">
                      Transaction: {lastResult.confirmedTransaction.transactionNumber || lastResult.confirmedTransaction.id}
                    </div>
                    <div className="mt-1 text-xs">
                      Total: PKR {Number(lastResult.confirmedTransaction.pricing?.total || 0).toFixed(2)}
                    </div>
                  </div>
                ) : null}
                {lastResult.draftOrder?.items?.length ? (
                  <div className="rounded-2xl border border-white/80 bg-white/80 p-3">
                    <div className="font-semibold text-ink">Draft order prepared</div>
                    <div className="mt-2 space-y-2">
                      {lastResult.draftOrder.items.map((item) => (
                        <div key={`${item.itemId}-${item.name}`} className="flex items-center justify-between rounded-xl bg-surface px-3 py-2 text-xs">
                          <span>{item.quantity} x {item.name}</span>
                          <span>{item.currency || "PKR"} {Number((item.quantity || 1) * (item.unitPrice || 0)).toFixed(2)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>
            ) : null}
          </form>

          <form onSubmit={handleSendTest} className="space-y-4 rounded-md border border-line bg-white p-5 shadow-sm">
            <div>
              <h2 className="text-lg font-semibold text-ink">Send test message</h2>
              <p className="mt-1 text-sm text-muted">Mock mode logs this locally. Meta mode sends through WhatsApp Cloud API if credentials are valid.</p>
            </div>
            <input className="w-full rounded-md border border-line px-3 py-2 text-sm" value={testForm.toPhone} onChange={(event) => setTestForm((current) => ({ ...current, toPhone: event.target.value }))} placeholder="Recipient phone" />
            <textarea className="min-h-20 w-full rounded-md border border-line px-3 py-2 text-sm" value={testForm.messageText} onChange={(event) => setTestForm((current) => ({ ...current, messageText: event.target.value }))} />
            <button className="rounded-md border border-line px-4 py-2 text-sm font-semibold text-ink hover:bg-surface" disabled={!connected || isSendingTest} type="submit">
              {isSendingTest ? "Sending..." : "Send test"}
            </button>
          </form>
        </div>
      </div>

      <div className="rounded-md border border-line bg-white p-5 shadow-sm">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-ink">Recent WhatsApp conversations</h2>
            <p className="mt-1 text-sm text-muted">These also appear in the AI Chat conversation review screen.</p>
          </div>
          <button className="rounded-md border border-line px-3 py-2 text-sm font-semibold text-ink hover:bg-surface" onClick={() => loadWorkspace()} type="button">
            Refresh
          </button>
        </div>
        <div className="mt-4 overflow-hidden rounded-md border border-line">
          <table className="min-w-full divide-y divide-line text-sm">
            <thead className="bg-surface text-left text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="px-4 py-3">Customer</th>
                <th className="px-4 py-3">Last intent</th>
                <th className="px-4 py-3">Summary</th>
                <th className="px-4 py-3">Last message</th>
                <th className="px-4 py-3">Timeline</th>
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
                    <td className="px-4 py-3">
                      <button className="rounded-md border border-line px-3 py-1 text-xs font-semibold text-ink hover:bg-surface" type="button" onClick={() => handleLoadTimeline(conversation.id)}>
                        View timeline
                      </button>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td className="px-4 py-6 text-center text-muted" colSpan="5">
                    No WhatsApp conversations yet. Use the mock simulator to test the flow.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {isLoadingTimeline ? <div className="mt-4 text-sm text-muted">Loading conversation timeline...</div> : null}
        {selectedTimeline ? (
          <div className="mt-5 rounded-md border border-line bg-surface p-4">
            <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
              <div>
                <div className="font-semibold text-ink">Conversation timeline</div>
                <div className="mt-1 text-xs text-muted">{selectedTimeline.conversation?.externalCustomerName || "WhatsApp Customer"} · {selectedTimeline.conversation?.externalCustomerPhone}</div>
              </div>
              <button className="rounded-md border border-line px-3 py-2 text-xs font-semibold text-ink hover:bg-white" type="button" onClick={() => setSelectedTimeline(null)}>Close timeline</button>
            </div>
            <div className="mt-4 max-h-96 space-y-3 overflow-auto">
              {(selectedTimeline.timeline || []).map((item, index) => (
                <div key={`${item.type}-${index}`} className={item.direction === "inbound" ? "rounded-2xl rounded-bl-md border border-blue-100 bg-white p-3 text-sm" : item.direction === "outbound" ? "rounded-2xl rounded-br-md border border-green-100 bg-green-50 p-3 text-sm" : "rounded-md border border-line bg-white p-3 text-sm"}>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="font-semibold text-ink">{item.label}</div>
                    <div className="text-xs text-muted">{formatDate(item.createdAt)}</div>
                  </div>
                  <div className="mt-2 whitespace-pre-wrap text-muted">{item.text || item.status || "Logged"}</div>
                  <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted">
                    {item.intent ? <span className="rounded-full bg-white px-2 py-1">Intent: {item.intent}</span> : null}
                    {item.status ? <span className="rounded-full bg-white px-2 py-1">Status: {item.status}</span> : null}
                    {item.providerMessageId ? <span className="rounded-full bg-white px-2 py-1">Message ID: {item.providerMessageId}</span> : null}
                    {item.error ? <span className="rounded-full bg-red-100 px-2 py-1 text-red-700">Error: {item.error}</span> : null}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}
