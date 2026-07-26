import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { CustomerPaymentInstructions, getDefaultPaymentMethod } from "../../components/payments/CustomerPaymentInstructions.jsx";
import { WhatsAppAgentCta, WhatsAppAgentInfo } from "../../components/whatsapp/WhatsAppAgentCta.jsx";
import { createPublicStripeCheckout, createPublicTransaction, getPublicBusiness, getPublicItem, resolveUploadUrl } from "../../services/publicWebsiteApi.js";
import { capitalize, formatTransactionLabel, formatTransactionSuccess, transactionTypeOptions } from "../../utils/transaction.js";
import { buildPublicSiteModel, inferItemTransactionType, PublicLoadingState, PublicUnavailableState, PublicWebsiteFrame } from "./publicWebsiteShared.jsx";

export function PublicItemPage() {
  const { tenantSlug, itemId } = useParams();
  const [business, setBusiness] = useState(null);
  const [item, setItem] = useState(null);
  const [form, setForm] = useState({ customerName: "", customerPhone: "", customerEmail: "", quantity: 1, notes: "", transactionType: "auto", paymentMethod: "" });
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function load() {
      setIsLoading(true);
      setError("");
      try {
        const [businessData, itemData] = await Promise.all([getPublicBusiness(tenantSlug), getPublicItem(tenantSlug, itemId)]);
        setBusiness(businessData);
        setItem(itemData);
      } catch (requestError) {
        setError(requestError.response?.data?.detail || "Item unavailable.");
      } finally {
        setIsLoading(false);
      }
    }
    load();
  }, [tenantSlug, itemId]);

  async function submit(event) {
    event.preventDefault();
    setError("");
    setMessage("");
    try {
      const transaction = await createPublicTransaction(tenantSlug, {
        customerName: form.customerName,
        customerPhone: form.customerPhone,
        customerEmail: form.customerEmail,
        transactionType: form.transactionType,
        paymentMethod: form.paymentMethod || getDefaultPaymentMethod(business?.paymentOptions || {}),
        items: [{ itemId, quantity: Number(form.quantity || 1) }],
        fulfillment: { type: "none", address: {} },
        notes: form.notes,
      });
      if ((form.paymentMethod || getDefaultPaymentMethod(business?.paymentOptions || {})) === "stripe_test") {
        setMessage("Opening Stripe Checkout...");
        const checkout = await createPublicStripeCheckout(tenantSlug, transaction.id);
        if (checkout.checkoutUrl) {
          window.location.href = checkout.checkoutUrl;
          return;
        }
      }
      setMessage(formatTransactionSuccess(transaction));
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to submit request.");
    }
  }

  if (isLoading) return <PublicLoadingState label="Loading item..." />;
  if (error && !item) {
    return <PublicUnavailableState title="Item unavailable" error={error} />;
  }

  const siteModel = buildPublicSiteModel(business, item ? [item] : []);
  const activeRequestType = form.transactionType === "auto" ? inferItemTransactionType(item) : form.transactionType;

  return (
    <PublicWebsiteFrame business={business} currentPage="catalog" siteModel={siteModel}>
      <section style={{ background: siteModel.theme.background }}>
        <div className="mx-auto grid max-w-6xl gap-8 px-5 py-10 lg:grid-cols-[1fr_420px]">
          <div>
            <Link className="text-sm font-semibold" style={{ color: siteModel.theme.accent }} to={siteModel.catalogPath}>
              Back to {siteModel.catalogLabel}
            </Link>
            {item.images?.[0]?.url ? (
              <img alt="" className="mt-5 h-80 w-full rounded-[28px] object-cover shadow-sm" src={resolveUploadUrl(item.images[0].url)} />
            ) : (
              <div className="mt-5 h-80 rounded-[28px]" style={{ background: `linear-gradient(135deg, ${siteModel.theme.accent}18, ${siteModel.theme.secondary}12)` }} />
            )}
            <p className="mt-6 text-sm font-semibold uppercase tracking-wide" style={{ color: siteModel.theme.accent }}>{item.itemType?.replace("_", " ")}</p>
            <h1 className="mt-2 text-4xl font-semibold text-ink">{item.name}</h1>
            <p className="mt-4 text-base leading-7 text-muted">{item.description || "No description added."}</p>
            <div className="mt-5 text-2xl font-semibold text-ink">{item.currency} {item.price}</div>
            {item.serviceDetails?.durationMinutes ? (
              <div className="mt-3 text-sm text-muted">
                {item.serviceDetails.durationMinutes} minute service
                {item.serviceDetails.bufferMinutes ? ` + ${item.serviceDetails.bufferMinutes} minute buffer` : ""}
              </div>
            ) : null}
          </div>
          <form className="h-fit space-y-3 rounded-[28px] border border-black/5 bg-white/92 p-5 shadow-sm" onSubmit={submit}>
            <h2 className="text-lg font-semibold text-ink">{capitalize(formatTransactionLabel(activeRequestType))} this item</h2>
            {message ? <div className="rounded-md border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">{message}</div> : null}
            {error ? <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}
            <input className="form-input" required placeholder="Your name" value={form.customerName} onChange={(event) => setForm((current) => ({ ...current, customerName: event.target.value }))} />
            <input className="form-input" required placeholder="Phone" value={form.customerPhone} onChange={(event) => setForm((current) => ({ ...current, customerPhone: event.target.value }))} />
            <input className="form-input" placeholder="Email" value={form.customerEmail} onChange={(event) => setForm((current) => ({ ...current, customerEmail: event.target.value }))} />
            <select className="form-input" value={form.transactionType} onChange={(event) => setForm((current) => ({ ...current, transactionType: event.target.value }))}>
              {transactionTypeOptions.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
            <input className="form-input" min="1" type="number" value={form.quantity} onChange={(event) => setForm((current) => ({ ...current, quantity: event.target.value }))} />
            <CustomerPaymentInstructions
              compact
              options={business?.paymentOptions || {}}
              selectedMethod={form.paymentMethod || getDefaultPaymentMethod(business?.paymentOptions || {})}
              onChange={(value) => setForm((current) => ({ ...current, paymentMethod: value }))}
            />
            <textarea className="form-input min-h-24" placeholder="Notes" value={form.notes} onChange={(event) => setForm((current) => ({ ...current, notes: event.target.value }))} />
            <button className="w-full rounded-md px-4 py-2 text-sm font-semibold text-white" style={{ backgroundColor: siteModel.theme.accent }}>
              Submit {capitalize(formatTransactionLabel(activeRequestType))}
            </button>
            <WhatsAppAgentCta
              agent={business.whatsappAgent}
              className="w-full"
              message={`Hello, I found your business on BizXusAI and I want to ask about ${item.name}.`}
              themeColor="#16a34a"
            />
            <WhatsAppAgentInfo agent={business.whatsappAgent} />
          </form>
        </div>
      </section>
    </PublicWebsiteFrame>
  );
}
