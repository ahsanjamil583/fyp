import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import { BusinessAiChatExperience } from "../../components/chat/BusinessAiChatExperience.jsx";
import { createPublicOrder, getPublicChatState, sendPublicChatMessage, resolveUploadUrl } from "../../services/publicWebsiteApi.js";
import { buildPublicSiteModel, PublicLoadingState, PublicUnavailableState, PublicWebsiteFrame } from "./publicWebsiteShared.jsx";

const emptyReply = { tenant: null, conversation: null, messages: [], draftOrder: {} };

export function PublicBusinessChatPage() {
  const { tenantSlug } = useParams();
  const storageKey = useMemo(() => `bizxus_public_chat_${tenantSlug}`, [tenantSlug]);
  const [chatState, setChatState] = useState(emptyReply);
  const [messageText, setMessageText] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [isConfirming, setIsConfirming] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [draftQuantities, setDraftQuantities] = useState({});
  const [checkout, setCheckout] = useState({ customerName: "", customerPhone: "", customerEmail: "", fulfillmentType: "", paymentMethod: "", addressLine1: "", city: "" });

  useEffect(() => {
    async function loadChat() {
      setError("");
      try {
        const conversationId = localStorage.getItem(storageKey);
        const data = await getPublicChatState(tenantSlug, conversationId);
        if (data.conversation?.id) localStorage.setItem(storageKey, data.conversation.id);
        setChatState(data);
      } catch (requestError) {
        setError(requestError.response?.data?.detail || "Unable to load public AI chat. Please refresh and try again.");
      }
    }

    loadChat();
  }, [storageKey, tenantSlug]);

  async function submitMessage(event) {
    event.preventDefault();
    if (!messageText.trim()) return;
    setIsSending(true);
    setError("");
    setNotice("");
    try {
      const data = await sendPublicChatMessage(tenantSlug, {
        messageText: messageText.trim(),
        conversationId: chatState.conversation?.id || localStorage.getItem(storageKey),
      });
      if (data.conversation?.id) localStorage.setItem(storageKey, data.conversation.id);
      setChatState(data);
      setDraftQuantities({});
      setMessageText("");
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Something went wrong while asking the assistant. Please try again.");
    } finally {
      setIsSending(false);
    }
  }

  async function confirmPublicDraft() {
    if (!chatState.draftOrder?.items?.length || chatState.draftOrder.canConfirm === false) return;
    const fulfillmentType = checkout.fulfillmentType || (chatState.draftOrder.fulfillmentPreference?.type === "delivery" ? "delivery" : "pickup");
    if (!checkout.customerName.trim()) {
      setError("Unable to confirm order because customer name is missing.");
      return;
    }
    if (!checkout.customerPhone.trim()) {
      setError("Unable to confirm order because phone number is missing.");
      return;
    }
    if (fulfillmentType === "delivery" && !checkout.addressLine1.trim()) {
      setError("Unable to confirm order because delivery address is missing.");
      return;
    }
    if (fulfillmentType === "delivery" && !checkout.city.trim()) {
      setError("Unable to confirm order because city is missing.");
      return;
    }
    setIsConfirming(true);
    setError("");
    setNotice("");
    try {
      const order = await createPublicOrder(tenantSlug, {
        customerName: checkout.customerName.trim(),
        customerPhone: checkout.customerPhone.trim(),
        customerEmail: checkout.customerEmail.trim(),
        conversationId: chatState.conversation?.id || localStorage.getItem(storageKey),
        transactionType: chatState.draftOrder.transactionType || "auto",
        paymentMethod: checkout.paymentMethod || chatState.tenant?.paymentOptions?.defaultMethod || undefined,
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
          address: fulfillmentType === "delivery" ? { line1: checkout.addressLine1, city: checkout.city } : {},
        },
        notes: "Confirmed from public AI chat.",
        customFields: {},
      });
      setNotice(`Your order has been confirmed. Order number: ${order.transactionNumber || order.id}.`);
      const refreshed = await getPublicChatState(tenantSlug, chatState.conversation?.id || localStorage.getItem(storageKey));
      setChatState(refreshed);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Something went wrong while creating your order. Please try again.");
    } finally {
      setIsConfirming(false);
    }
  }

  const business = chatState.tenant;
  const draftOrder = chatState.draftOrder || {};

  if (error && !business) {
    return <PublicUnavailableState title="Public AI chat unavailable" error={error} />;
  }

  if (!business) {
    return <PublicLoadingState label="Loading public AI chat..." />;
  }

  const siteModel = buildPublicSiteModel(business, draftOrder.items || []);

  return (
    <PublicWebsiteFrame business={business} currentPage="chat" siteModel={siteModel}>
      <div className="mx-auto max-w-7xl px-5 py-10">
        <BusinessAiChatExperience
          accentClass="text-brand-700"
          business={business}
          checkout={checkout}
          draftOrder={draftOrder}
          draftQuantities={draftQuantities}
          error={error}
          isConfirming={isConfirming}
          isSending={isSending}
          messageText={messageText}
          messages={chatState.messages || []}
          notice={notice}
          onConfirmDraft={confirmPublicDraft}
          onSubmitMessage={submitMessage}
          publicMode
          resolveUploadUrl={resolveUploadUrl}
          setCheckout={setCheckout}
          setDraftQuantities={setDraftQuantities}
          setMessageText={setMessageText}
        />
      </div>
    </PublicWebsiteFrame>
  );
}
