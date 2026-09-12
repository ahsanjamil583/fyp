import { ProductImage } from "../common/ProductImage.jsx";
import { useEffect, useMemo, useRef } from "react";

import { CustomerPaymentInstructions } from "../payments/CustomerPaymentInstructions.jsx";
import { formatDisplayValue } from "../../utils/displaySafety.js";
import { getDefaultPaymentMethod } from "../payments/paymentMethods.js";

function formatTime(value) {
  if (!value) return "";
  try {
    return new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

function formatMoney(currency = "PKR", value = 0) {
  return `${currency || "PKR"} ${Number(value || 0).toFixed(2)}`;
}

function splitReply(text = "") {
  return String(text)
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean);
}

function optionText(options = {}) {
  // Customer-facing: an object value here previously printed "[object Object]".
  const entries = Object.entries(options || {})
    .map(([key, value]) => [key, formatDisplayValue(value, { fallback: "" })])
    .filter(([, text]) => text.trim() !== "");
  if (!entries.length) return "";
  return entries.map(([key, text]) => `${key}: ${text}`).join(" | ");
}

function inferCategoryName(business = {}) {
  return business.businessCategory?.name || business.category?.name || business.categoryName || business.businessCategoryName || "Business";
}

function quickPromptsForBusiness(business = {}) {
  const text = `${business.name || ""} ${inferCategoryName(business)} ${(business.description || "")}`.toLowerCase();
  if (/(restaurant|food|burger|pizza|cafe|chai|fast)/.test(text)) {
    return ["Show today's menu", "Zinger burger available?", "Delivery charges?", "Payment methods?", "Make an order"];
  }
  if (/(fashion|clothing|shirt|shoes|tailor|boutique|dress)/.test(text)) {
    return ["Show black shirts", "Size guide", "Delivery charges?", "Payment methods?", "Order shoes"];
  }
  return ["Show menu", "What is available?", "Delivery charges?", "Payment methods?", "Make an order"];
}

function MessageBubble({ message }) {
  const isCustomer = message.sender === "customer";
  const paragraphs = splitReply(message.messageText);
  return (
    <div className={isCustomer ? "flex justify-end" : "flex justify-start"}>
      <div
        className={
          isCustomer
            ? "max-w-[82%] rounded-[24px] rounded-br-lg bg-gradient-to-br from-brand-600 to-cyan-600 px-4 py-3 text-sm text-white shadow-card"
            : "max-w-[82%] rounded-[24px] rounded-bl-lg border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 shadow-card"
        }
      >
        <div className="mb-1 flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.18em] opacity-70">
          <span>{isCustomer ? "You" : "AI Assistant"}</span>
          {formatTime(message.createdAt) ? <span>{formatTime(message.createdAt)}</span> : null}
        </div>
        <div className="space-y-2 leading-6">
          {paragraphs.length ? paragraphs.map((paragraph) => <p key={paragraph}>{paragraph}</p>) : <p>{message.messageText}</p>}
        </div>
      </div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex justify-start">
      <div className="rounded-[24px] rounded-bl-lg border border-slate-200 bg-white px-4 py-3 shadow-card">
        <div className="flex items-center gap-2 text-sm text-slate-500">
          <span className="h-2 w-2 animate-pulse rounded-full bg-brand-500" />
          <span className="h-2 w-2 animate-pulse rounded-full bg-brand-400 [animation-delay:120ms]" />
          <span className="h-2 w-2 animate-pulse rounded-full bg-cyan-400 [animation-delay:240ms]" />
          <span className="ml-2">AI is checking catalog, stock, and knowledge...</span>
        </div>
      </div>
    </div>
  );
}

// The API reports availability as a band rather than a count, so customers cannot
// read a business's exact inventory out of a draft order.
function stockLabel(stock) {
  if (!stock?.tracked) return "Stock not tracked or service item";
  if (stock.status === "out_of_stock") return "Currently out of stock";
  if (stock.status === "low_stock") return "Only a few left in stock";
  return "In stock";
}

function DraftItemCard({ item, quantity, onQuantityChange }) {
  const options = optionText(item.selectedOptions);
  const stock = item.stockSnapshot || {};
  const lineTotal = Number(quantity || item.quantity || 1) * Number(item.unitPrice || 0);
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-card">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="font-semibold text-slate-950">{item.name}</div>
          {item.selectedVariantName ? <div className="mt-1 text-xs text-slate-500">Variant: {item.selectedVariantName}</div> : null}
          {options ? <div className="mt-1 text-xs text-slate-500">Options: {options}</div> : null}
        </div>
        <span className={stock.available === false ? "rounded-full bg-red-50 px-2 py-1 text-xs font-bold text-red-700" : "rounded-full bg-green-50 px-2 py-1 text-xs font-bold text-green-700"}>
          {stock.available === false ? "Out of stock" : "Available"}
        </span>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
        <label className="block">
          <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">Quantity</span>
          <input
            className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2"
            min="1"
            max="99"
            type="number"
            value={quantity || item.quantity || 1}
            onChange={(event) => onQuantityChange(item, event.target.value)}
          />
        </label>
        <div>
          <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Unit price</div>
          <div className="mt-2 font-semibold text-slate-950">{formatMoney(item.currency, item.unitPrice)}</div>
        </div>
      </div>
      <div className="mt-3 flex items-center justify-between rounded-xl bg-slate-50 px-3 py-2 text-sm">
        <span className="text-slate-500">Line total</span>
        <span className="font-semibold text-slate-950">{formatMoney(item.currency, lineTotal)}</span>
      </div>
      <div className="mt-2 text-xs text-slate-500">{stockLabel(stock)}</div>
    </div>
  );
}

function ProductSuggestionCard({ item, onAskForItem, resolveUploadUrl }) {
  const image = item.images?.[0]?.url || item.imageUrl || item.image || "";
  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-card">
      {image ? <ProductImage alt="" className="h-28 w-full object-cover" src={resolveUploadUrl ? resolveUploadUrl(image) : image} /> : null}
      <div className="p-3">
        <div className="font-semibold text-slate-950">{item.name}</div>
        {item.matchedVariant?.name ? <div className="mt-1 text-xs text-slate-500">Variant: {item.matchedVariant.name}</div> : null}
        <div className="mt-2 flex items-center justify-between text-sm">
          <span className="font-semibold text-brand-700">{formatMoney(item.currency, item.price)}</span>
          <span className="rounded-full bg-green-50 px-2 py-1 text-xs font-bold text-green-700">Suggested</span>
        </div>
        <button className="mt-3 w-full rounded-xl bg-slate-950 px-3 py-2 text-xs font-semibold text-white" type="button" onClick={() => onAskForItem?.(`I want ${item.name}`)}>
          Add to draft
        </button>
      </div>
    </div>
  );
}

export function BusinessAiDraftOrderSummary({
  business = {},
  draftOrder = {},
  draftQuantities = {},
  setDraftQuantities,
  fulfillmentDraft = { type: "", addressLine1: "", city: "" },
  setFulfillmentDraft,
  checkout = {},
  setCheckout,
  publicMode = false,
  isConfirming,
  onConfirmDraft,
  setMessageText,
  resolveUploadUrl,
  showEmpty = false,
  compact = false,
}) {
  const draftItems = draftOrder.items || [];
  const fulfillmentType = publicMode
    ? checkout?.fulfillmentType || (draftOrder.fulfillmentPreference?.type === "delivery" ? "delivery" : "pickup")
    : fulfillmentDraft?.type || (draftOrder.fulfillmentPreference?.type === "delivery" ? "delivery" : "pickup");
  const isDelivery = fulfillmentType === "delivery";
  const paymentOptions = business?.paymentOptions || {};
  const selectedPaymentMethod = publicMode
    ? checkout?.paymentMethod || getDefaultPaymentMethod(paymentOptions)
    : fulfillmentDraft?.paymentMethod || getDefaultPaymentMethod(paymentOptions);
  const missing = [];
  if (draftItems.length && publicMode && !checkout?.customerName?.trim()) missing.push("Please enter your name.");
  if (draftItems.length && publicMode && !checkout?.customerPhone?.trim()) missing.push("Please enter your phone number.");
  if (draftItems.length && isDelivery && publicMode && !checkout?.addressLine1?.trim()) missing.push("Please enter delivery address.");
  if (draftItems.length && isDelivery && publicMode && !checkout?.city?.trim()) missing.push("Please enter city.");
  if (draftItems.length && isDelivery && !publicMode && !fulfillmentDraft?.addressLine1?.trim()) missing.push("Please enter delivery address.");
  if (draftItems.length && isDelivery && !publicMode && !fulfillmentDraft?.city?.trim()) missing.push("Please enter city.");
  if (draftItems.length && !fulfillmentType) missing.push("Please select pickup or delivery.");
  const draftCanConfirm = Boolean(draftItems.length) && draftOrder.canConfirm !== false && missing.length === 0;

  function updateDraftQuantity(item, value) {
    const nextQuantity = Math.max(1, Math.min(Number(value || 1), 99));
    setDraftQuantities?.((current) => ({ ...current, [item.itemId]: nextQuantity }));
  }

  function askForItem(prompt) {
    setMessageText?.(prompt);
  }

  if (!draftItems.length && !showEmpty) {
    return null;
  }

  return (
    <div className={compact ? "rounded-2xl border border-brand-100 bg-white p-3 shadow-card" : "rounded-[30px] border border-white/80 bg-white p-5 shadow-xl shadow-slate-200/70"}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.22em] text-brand-700">Draft Order</div>
          <h2 className={compact ? "mt-1 text-base font-bold text-slate-950" : "mt-1 text-xl font-bold text-slate-950"}>Order summary</h2>
        </div>
        <span className={draftItems.length ? "rounded-full bg-brand-50 px-2 py-1 text-[10px] font-bold text-brand-700" : "rounded-full bg-slate-100 px-2 py-1 text-[10px] font-bold text-slate-500"}>
          {draftItems.length ? "Review" : "No draft"}
        </span>
      </div>

      {draftItems.length ? (
        <div className="mt-4 space-y-3">
          {draftItems.map((item) => (
            <DraftItemCard
              key={`${draftOrder.conversationId || draftOrder.tenantId || "draft"}-${item.itemId}-${item.selectedVariantIndex ?? "base"}`}
              item={item}
              quantity={draftQuantities[item.itemId] || item.quantity}
              onQuantityChange={updateDraftQuantity}
            />
          ))}

          {draftOrder.pricing?.total ? (
            <div className="rounded-2xl bg-slate-950 p-4 text-white">
              <div className="text-sm text-slate-300">Estimated total</div>
              <div className={compact ? "mt-1 text-xl font-bold" : "mt-1 text-2xl font-bold"}>{formatMoney(draftOrder.pricing.currency, draftOrder.pricing.total)}</div>
            </div>
          ) : null}

          {draftOrder.confirmationIssues?.length ? (
            <div className="rounded-2xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">
              {draftOrder.confirmationIssues.map((issue) => <div key={issue}>{issue}</div>)}
            </div>
          ) : null}

          {missing.length ? (
            <div className="rounded-2xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
              {missing.map((item) => <div key={item}>{item}</div>)}
            </div>
          ) : null}

          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-3">
            <div className="text-sm font-bold text-slate-950">Fulfillment</div>
            <select
              className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"
              value={fulfillmentType}
              onChange={(event) => {
                if (publicMode) setCheckout?.((current) => ({ ...current, fulfillmentType: event.target.value }));
                else setFulfillmentDraft?.((current) => ({ ...current, type: event.target.value }));
              }}
            >
              <option value="pickup">Pickup</option>
              <option value="delivery">Delivery</option>
            </select>

            {publicMode ? (
              <div className={compact ? "mt-3 grid gap-2" : "mt-3 grid gap-2 md:grid-cols-3"}>
                <input className="rounded-xl border border-slate-200 px-3 py-2 text-sm" placeholder="Your name" value={checkout.customerName || ""} onChange={(event) => setCheckout?.((current) => ({ ...current, customerName: event.target.value }))} />
                <input className="rounded-xl border border-slate-200 px-3 py-2 text-sm" placeholder="Phone / WhatsApp number" value={checkout.customerPhone || ""} onChange={(event) => setCheckout?.((current) => ({ ...current, customerPhone: event.target.value }))} />
                <input className="rounded-xl border border-slate-200 px-3 py-2 text-sm" placeholder="Email optional" value={checkout.customerEmail || ""} onChange={(event) => setCheckout?.((current) => ({ ...current, customerEmail: event.target.value }))} />
              </div>
            ) : null}

            {isDelivery ? (
              <div className={compact ? "mt-3 grid gap-2" : "mt-3 grid gap-2 md:grid-cols-2"}>
                <input
                  className="rounded-xl border border-slate-200 px-3 py-2 text-sm"
                  placeholder="Delivery address"
                  value={publicMode ? checkout.addressLine1 || "" : fulfillmentDraft.addressLine1 || ""}
                  onChange={(event) => {
                    if (publicMode) setCheckout?.((current) => ({ ...current, addressLine1: event.target.value }));
                    else setFulfillmentDraft?.((current) => ({ ...current, addressLine1: event.target.value }));
                  }}
                />
                <input
                  className="rounded-xl border border-slate-200 px-3 py-2 text-sm"
                  placeholder="City"
                  value={publicMode ? checkout.city || "" : fulfillmentDraft.city || ""}
                  onChange={(event) => {
                    if (publicMode) setCheckout?.((current) => ({ ...current, city: event.target.value }));
                    else setFulfillmentDraft?.((current) => ({ ...current, city: event.target.value }));
                  }}
                />
              </div>
            ) : null}
          </div>

          <CustomerPaymentInstructions
            compact={compact}
            options={paymentOptions}
            selectedMethod={selectedPaymentMethod}
            onChange={(value) => {
              if (publicMode) setCheckout?.((current) => ({ ...current, paymentMethod: value }));
              else setFulfillmentDraft?.((current) => ({ ...current, paymentMethod: value }));
            }}
          />

          {draftOrder.suggestedItems?.length ? (
            <div>
              <div className="text-sm font-bold text-slate-950">Product suggestions</div>
              <div className={compact ? "mt-3 grid gap-3" : "mt-3 grid gap-3 md:grid-cols-2"}>
                {draftOrder.suggestedItems.map((item) => (
                  <ProductSuggestionCard key={`suggested-${item.itemId}-${item.name}`} item={item} onAskForItem={askForItem} resolveUploadUrl={resolveUploadUrl} />
                ))}
              </div>
            </div>
          ) : null}

          <div className="grid gap-2">
            <button className="rounded-2xl bg-slate-950 px-4 py-3 text-sm font-bold text-white disabled:cursor-not-allowed disabled:opacity-50" disabled={isConfirming || !draftCanConfirm} onClick={onConfirmDraft} type="button">
              {!draftCanConfirm ? "Complete missing details" : isConfirming ? "Confirming..." : "Confirm order"}
            </button>
            <button className="rounded-2xl border border-slate-200 px-4 py-3 text-sm font-bold text-slate-700" type="button" onClick={() => setMessageText?.("Cancel this draft order")}>
              Cancel draft
            </button>
          </div>
        </div>
      ) : (
        <div className="mt-4 rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-3 text-xs leading-5 text-slate-600">
          No draft yet. Ask for an item and quantity, for example: &quot;2 burgers delivery kar do&quot;.
        </div>
      )}
    </div>
  );
}

export function BusinessAiChatExperience({
  business,
  backLink,
  backLabel,
  messages = [],
  draftOrder = {},
  messageText,
  setMessageText,
  isSending,
  isConfirming,
  error,
  notice,
  onSubmitMessage,
  onConfirmDraft,
  draftQuantities = {},
  setDraftQuantities,
  fulfillmentDraft,
  setFulfillmentDraft,
  checkout,
  setCheckout,
  publicMode = false,
  resolveUploadUrl,
  accentClass = "text-brand-700",
  draftPlacement = "below",
}) {
  const scrollRef = useRef(null);
  const prompts = useMemo(() => quickPromptsForBusiness(business), [business]);
  const draftItems = draftOrder.items || [];
  const fulfillmentType = publicMode
    ? checkout?.fulfillmentType || (draftOrder.fulfillmentPreference?.type === "delivery" ? "delivery" : "pickup")
    : fulfillmentDraft?.type || (draftOrder.fulfillmentPreference?.type === "delivery" ? "delivery" : "pickup");
  const isDelivery = fulfillmentType === "delivery";
  const missing = [];
  if (draftItems.length && publicMode && !checkout?.customerName?.trim()) missing.push("Please enter your name.");
  if (draftItems.length && publicMode && !checkout?.customerPhone?.trim()) missing.push("Please enter your phone number.");
  if (draftItems.length && isDelivery && publicMode && !checkout?.addressLine1?.trim()) missing.push("Please enter delivery address.");
  if (draftItems.length && isDelivery && publicMode && !checkout?.city?.trim()) missing.push("Please enter city.");
  if (draftItems.length && isDelivery && !publicMode && !fulfillmentDraft?.addressLine1?.trim()) missing.push("Please enter delivery address.");
  if (draftItems.length && isDelivery && !publicMode && !fulfillmentDraft?.city?.trim()) missing.push("Please enter city.");
  if (draftItems.length && !fulfillmentType) missing.push("Please select pickup or delivery.");
  const draftCanConfirm = Boolean(draftItems.length) && draftOrder.canConfirm !== false && missing.length === 0;

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, isSending]);

  function updateDraftQuantity(item, value) {
    const nextQuantity = Math.max(1, Math.min(Number(value || 1), 99));
    setDraftQuantities?.((current) => ({ ...current, [item.itemId]: nextQuantity }));
  }

  function askForItem(prompt) {
    setMessageText(prompt);
  }

  return (
    <section className="mx-auto max-w-5xl space-y-5">
      <div className="min-w-0 overflow-hidden rounded-[30px] border border-white/80 bg-slate-100/80 shadow-2xl shadow-slate-200/70">
        <div className="border-b border-white/80 bg-white/90 p-5 backdrop-blur">
          {backLink ? <a className={`text-sm font-semibold ${accentClass}`} href={backLink}>{backLabel || "Back"}</a> : null}
          <div className="mt-4 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="text-xs font-bold uppercase tracking-[0.24em] text-brand-700">AI Business Assistant</div>
              <h1 className="mt-2 text-2xl font-bold text-slate-950">Chat with {business.name}</h1>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">Ask about products, prices, stock, delivery, and orders. I can guide you step by step and prepare a safe draft order.</p>
            </div>
            <div className="rounded-2xl border border-green-100 bg-green-50 px-4 py-3 text-sm text-green-800">
              <div className="font-bold">Online</div>
              <div className="text-xs">AI Assistant active | {inferCategoryName(business)}</div>
            </div>
          </div>
        </div>

        {notice ? <div className="mx-5 mt-4 rounded-2xl border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700">{notice}</div> : null}
        {error ? <div className="mx-5 mt-4 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div> : null}

        <div className="flex h-[min(660px,calc(100vh-260px))] min-h-[520px] flex-col">
          <div className="flex-1 space-y-4 overflow-y-auto px-5 py-5">
            {!messages.length ? (
              <div className="rounded-[28px] border border-dashed border-brand-200 bg-white/80 p-6 text-center shadow-card">
                <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-50 text-2xl">AI</div>
                <h2 className="mt-4 text-lg font-bold text-slate-950">Hi! I am the AI assistant for this business.</h2>
                <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-600">You can ask about products, prices, stock, delivery, or place an order.</p>
              </div>
            ) : null}
            {messages.map((message) => <MessageBubble key={message.id || `${message.sender}-${message.createdAt}-${message.messageText}`} message={message} />)}
            {isSending ? <TypingIndicator /> : null}
            <div ref={scrollRef} />
          </div>

          <form className="border-t border-white/80 bg-white/95 p-4" onSubmit={onSubmitMessage}>
            <div className="mb-3 flex gap-2 overflow-x-auto pb-1">
              {prompts.map((prompt) => (
                <button key={prompt} className="shrink-0 rounded-full border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-700 hover:border-brand-200 hover:bg-brand-50" type="button" onClick={() => setMessageText(prompt)}>
                  {prompt}
                </button>
              ))}
            </div>
            <div className="flex items-end gap-3">
              <textarea
                className="min-h-12 flex-1 resize-none rounded-2xl border border-slate-200 px-4 py-3 text-sm outline-none transition focus:border-brand-400 focus:ring-4 focus:ring-brand-100"
                placeholder="Type your message, e.g. '2 zinger burgers delivery kar do'"
                value={messageText}
                onChange={(event) => setMessageText(event.target.value)}
              />
              <button className="rounded-2xl bg-gradient-to-br from-brand-600 to-cyan-600 px-5 py-3 text-sm font-bold text-white shadow-card disabled:cursor-not-allowed disabled:opacity-60" disabled={isSending || !messageText.trim()}>
                {isSending ? "Sending..." : "Send"}
              </button>
            </div>
          </form>
        </div>
      </div>

      {draftPlacement === "below" ? (
        <BusinessAiDraftOrderSummary
          checkout={checkout}
          draftOrder={draftOrder}
          draftQuantities={draftQuantities}
          fulfillmentDraft={fulfillmentDraft}
          isConfirming={isConfirming}
          onConfirmDraft={onConfirmDraft}
          publicMode={publicMode}
          resolveUploadUrl={resolveUploadUrl}
          setCheckout={setCheckout}
          business={business}
          setDraftQuantities={setDraftQuantities}
          setFulfillmentDraft={setFulfillmentDraft}
          setMessageText={setMessageText}
        />
      ) : null}
    </section>
  );
}
