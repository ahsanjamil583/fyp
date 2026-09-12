import { useEffect, useState } from "react";
import { useNavigate, useOutletContext, useParams } from "react-router-dom";
import { Bot, CheckCircle2, MessageCircle, ShoppingCart } from "lucide-react";

import { BusinessAiChatExperience, BusinessAiDraftOrderSummary } from "../../components/chat/BusinessAiChatExperience.jsx";
import { confirmCustomerDraftTransaction, getCustomerChatState, sendCustomerChatMessage } from "../../services/customerPortalApi.js";
import { formatTransactionSuccess } from "../../utils/transaction.js";

const emptyReply = { tenant: null, conversation: null, messages: [], draftOrder: {} };

export function CustomerBusinessChatPage() {
  const { tenantSlug } = useParams();
  const { setCustomerSidebarPanel } = useOutletContext() || {};
  const navigate = useNavigate();
  const [chatState, setChatState] = useState(emptyReply);
  const [messageText, setMessageText] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [isConfirming, setIsConfirming] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [draftQuantities, setDraftQuantities] = useState({});
  const [fulfillmentDraft, setFulfillmentDraft] = useState({ type: "", addressLine1: "", city: "" });

  useEffect(() => {
    async function loadChat() {
      setError("");
      try {
        const data = await getCustomerChatState(tenantSlug);
        setChatState(data);
      } catch (requestError) {
        setError(requestError.response?.data?.detail || "Unable to load customer chat. Please refresh and try again.");
      }
    }

    loadChat();
  }, [tenantSlug]);

  async function submitMessage(event) {
    event.preventDefault();
    if (!messageText.trim()) return;
    setIsSending(true);
    setError("");
    setNotice("");
    try {
      const data = await sendCustomerChatMessage(tenantSlug, { messageText: messageText.trim() });
      setChatState(data);
      setDraftQuantities({});
      setFulfillmentDraft({
        type: data.draftOrder?.fulfillmentPreference?.type === "delivery" ? "delivery" : "pickup",
        paymentMethod: data.tenant?.paymentOptions?.defaultMethod || "",
        addressLine1: "",
        city: "",
      });
      setMessageText("");
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Something went wrong while asking the assistant. Please try again.");
    } finally {
      setIsSending(false);
    }
  }

  async function confirmDraft() {
    if (!chatState.draftOrder?.items?.length) return;
    setIsConfirming(true);
    setError("");
    setNotice("");
    try {
      const fulfillmentType = fulfillmentDraft.type || (chatState.draftOrder.fulfillmentPreference?.type === "delivery" ? "delivery" : "pickup");
      if (fulfillmentType === "delivery" && !fulfillmentDraft.addressLine1.trim()) {
        setError("Unable to confirm order because delivery address is missing.");
        return;
      }
      if (fulfillmentType === "delivery" && !fulfillmentDraft.city.trim()) {
        setError("Unable to confirm order because city is missing.");
        return;
      }
      const order = await confirmCustomerDraftTransaction(tenantSlug, {
        conversationId: chatState.conversation?.id,
        transactionType: chatState.draftOrder.transactionType || "auto",
        paymentMethod: fulfillmentDraft.paymentMethod || chatState.tenant?.paymentOptions?.defaultMethod || undefined,
        items: chatState.draftOrder.items.map((item) => ({
          itemId: item.itemId,
          quantity: Number(draftQuantities[item.itemId] || item.quantity || 1),
          selectedVariantIndex: item.selectedVariantIndex ?? null,
          selectedVariantName: item.selectedVariantName || "",
          selectedOptions: item.selectedOptions || {},
          variantSku: item.variantSku || "",
        })),
        fulfillment: {
          type: fulfillmentType,
          address: fulfillmentType === "delivery" ? { line1: fulfillmentDraft.addressLine1, city: fulfillmentDraft.city } : {},
        },
        notes: "Confirmed from customer AI chat.",
        customFields: {},
      });
      setNotice(`Your order has been confirmed. ${formatTransactionSuccess(order)}`);
      navigate(`/customer/orders/${order.id}`);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Something went wrong while creating your order. Please try again.");
    } finally {
      setIsConfirming(false);
    }
  }

  const business = chatState.tenant;

  useEffect(() => {
    if (!setCustomerSidebarPanel) return undefined;
    if (!business) {
      setCustomerSidebarPanel(null);
      return undefined;
    }

    setCustomerSidebarPanel(
      <BusinessAiDraftOrderSummary
        business={business}
        compact
        showEmpty
        draftOrder={chatState.draftOrder || {}}
        draftQuantities={draftQuantities}
        fulfillmentDraft={fulfillmentDraft}
        isConfirming={isConfirming}
        onConfirmDraft={confirmDraft}
        setDraftQuantities={setDraftQuantities}
        setFulfillmentDraft={setFulfillmentDraft}
        setMessageText={setMessageText}
      />
    );

    return () => setCustomerSidebarPanel(null);
  }, [business, chatState.draftOrder, draftQuantities, fulfillmentDraft, isConfirming, setCustomerSidebarPanel]);

  if (error && !business) {
    return (
      <section className="space-y-4">
        <h1 className="text-2xl font-extrabold tracking-tight text-ink">AI chat unavailable</h1>
        <p className="text-sm text-muted">{error}</p>
      </section>
    );
  }

  if (!business) {
    return <section className="text-sm text-muted">Loading AI chat...</section>;
  }

  return (
    <section className="space-y-5">
      <div className="rounded-2xl border border-line bg-surface-purple p-5 shadow-card">
        <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-brand">AI assistant</p>
        <h1 className="mt-1.5 text-2xl font-extrabold tracking-tight text-ink">Ask {business.name}</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-muted">
          Ask about prices, availability, sizes, colors, delivery, or say what you want to order. The assistant will prepare a draft before you confirm.
        </p>
        <div className="mt-5 grid gap-2 text-xs font-bold text-muted sm:grid-cols-3">
          {[
            [MessageCircle, "Ask a question"],
            [Bot, "Review AI suggestion"],
            [ShoppingCart, "Confirm order"],
          ].map(([Icon, label]) => (
            <div key={label} className="rounded-xl border border-line bg-white px-3 py-3">
              <Icon className="mr-2 inline text-brand" size={15} />
              {label}
            </div>
          ))}
        </div>
        <div className="mt-4 rounded-xl border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-800">
          <CheckCircle2 className="mr-2 inline" size={15} />
          You are always asked before an order is confirmed.
        </div>
      </div>

      <BusinessAiChatExperience
        accentClass="text-brand"
        backLabel={`Back to ${business.name}`}
        backLink={`/customer/businesses/${tenantSlug}`}
        business={business}
        draftOrder={chatState.draftOrder || {}}
        draftQuantities={draftQuantities}
        error={error}
        fulfillmentDraft={fulfillmentDraft}
        isConfirming={isConfirming}
        isSending={isSending}
        messageText={messageText}
        messages={chatState.messages || []}
        notice={notice}
        onConfirmDraft={confirmDraft}
        onSubmitMessage={submitMessage}
        draftPlacement="external"
        setDraftQuantities={setDraftQuantities}
        setFulfillmentDraft={setFulfillmentDraft}
        setMessageText={setMessageText}
      />
    </section>
  );
}
