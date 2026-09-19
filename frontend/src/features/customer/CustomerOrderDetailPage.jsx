import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { ArrowRight, CheckCircle2, CreditCard, PackageCheck } from "lucide-react";

import { CustomerPaymentInstructions } from "../../components/payments/CustomerPaymentInstructions.jsx";
import { getDefaultPaymentMethod } from "../../components/payments/paymentMethods.js";
import { PaymentProofBadge, PaymentStatusBadge } from "../../components/payments/PaymentStatusBadge.jsx";
import { getCustomerOrderReceiptLink, orderReceiptUrl, getCustomerPaymentReceiptHtml, getCustomerTransaction, reorderCustomerTransaction, resolveUploadUrl, submitCustomerPaymentProof, syncCustomerStripeCheckout } from "../../services/customerPortalApi.js";
import { capitalize, formatTransactionType } from "../../utils/transaction.js";
import { isOnlinePaymentMethod, isOtpPaymentMethod, startOnlinePayment } from "../../services/paymentRedirect.js";
import { useCustomer } from "../../context/CustomerContext.jsx";
import { WalletOtpDialog } from "./WalletOtpDialog.jsx";
import { SectionTitle } from "../../components/ui/SectionTitle.jsx";
import { getApiErrorMessage } from "../../services/apiError.js";

export function CustomerOrderDetailPage() {
  const { orderId } = useParams();
  const location = useLocation();
  const [order, setOrder] = useState(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [proofDraft, setProofDraft] = useState({ amount: "", method: "", referenceNumber: "", notes: "", proofFile: null });
  const [isSubmittingProof, setIsSubmittingProof] = useState(false);
  const [isStartingStripe, setIsStartingStripe] = useState(false);
  const [isSyncingStripe, setIsSyncingStripe] = useState(false);
  const [openingReceiptId, setOpeningReceiptId] = useState("");
  const syncedReturnRef = useRef("");
  // The emailed-code flow finishes on this page instead of leaving for a gateway.
  const [otpMethod, setOtpMethod] = useState(null);
  const { customer } = useCustomer();

  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    loadOrder();
  }, [orderId]);

  // Checkout sends the customer here with ?pay=<method> when the chosen wallet settles
  // by emailed code. Opening the dialog on arrival keeps "place order" and "pay" feeling
  // like one step, the way a redirect gateway does.
  useEffect(() => {
    if (!order || otpMethod) return;
    const requested = new URLSearchParams(location.search).get("pay");
    if (!requested) return;
    const details = (order.paymentInstructions?.methods || []).find((entry) => entry.code === requested);
    if (details && isOtpPaymentMethod(details) && order.paymentStatus !== "paid") {
      setOtpMethod(details);
    }
  }, [order, otpMethod, location.search]);

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    if (params.get("payment") === "stripe_success") {
      const sessionId = params.get("session_id") || "";
      const syncKey = `${orderId}:${sessionId || "return"}`;
      if (syncedReturnRef.current === syncKey) return;
      syncedReturnRef.current = syncKey;
      syncStripeReturn(sessionId);
    }
    if (params.get("payment") === "stripe_cancelled") {
      setError("Stripe payment was cancelled. You can try again or choose another payment method.");
    }
    // JazzCash and Easypaisa settle server-side before redirecting here, so the order is
    // already up to date and only the confirmation still needs showing.
    const gatewayResult = params.get("payment");
    if (gatewayResult === "success") {
      setMessage("Payment received. Your order is now marked paid.");
    }
    if (gatewayResult === "cancelled") {
      setError("The payment was cancelled. You can try again or choose another payment method.");
    }
    if (gatewayResult === "failed") {
      setError("The payment could not be confirmed. Nothing was charged. Please try again.");
    }
  }, [location.search]);

  async function loadOrder() {
    // A 404 or 403 used to leave "Loading transaction..." on screen forever. This is
    // where customers land after checkout and after every gateway redirect, so a
    // permanent spinner is the worst possible outcome here.
    let data;
    try {
      data = await getCustomerTransaction(orderId);
      setLoadError("");
    } catch (requestError) {
      setLoadError(getApiErrorMessage(requestError, "This order could not be loaded."));
      return;
    }
    setOrder(data);
    setProofDraft((current) => ({
      ...current,
      amount: current.amount || data.paymentSummary?.balance || data.pricing?.total || "",
      method: current.method || data.paymentPreference?.method || getDefaultPaymentMethod(data.paymentInstructions || {}),
    }));
  }

  async function syncStripeReturn(sessionId) {
    setIsSyncingStripe(true);
    setMessage("Stripe payment completed. Syncing payment status...");
    setError("");
    try {
      const data = await syncCustomerStripeCheckout(orderId, { sessionId });
      if (data.providerStatus === "paid") {
        setMessage("Stripe payment confirmed. Your order is now marked paid.");
      } else {
        setMessage(`Stripe checkout was checked. Current Stripe status: ${data.providerStatus || "pending"}.`);
      }
      await loadOrder();
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Stripe payment completed, but we could not sync the status yet. It may update when the webhook arrives."));
      setMessage("");
    } finally {
      setIsSyncingStripe(false);
    }
  }

  async function submitProof(event) {
    event.preventDefault();
    setMessage("");
    setError("");
    setIsSubmittingProof(true);
    try {
      await submitCustomerPaymentProof(order.id, {
        ...proofDraft,
        amount: Number(proofDraft.amount || 0),
      });
      setMessage("Payment proof submitted. The business owner will verify it soon.");
      setProofDraft((current) => ({ ...current, referenceNumber: "", notes: "", proofFile: null }));
      await loadOrder();
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Unable to submit payment proof."));
    } finally {
      setIsSubmittingProof(false);
    }
  }

  // Covers Stripe, JazzCash, and Easypaisa. It is also the retry path when a customer
  // abandons a payment or the redirect fails, so it must work for every online method.
  async function startOnlineCheckout(method) {
    setMessage("");
    setError("");
    const details = (order.paymentInstructions?.methods || []).find((entry) => entry.code === method) || null;
    // A wallet configured for emailed codes stays here; everything else leaves for a
    // hosted page. The server tells us which through the method's `flow`.
    if (isOtpPaymentMethod(details)) {
      setOtpMethod(details);
      return;
    }
    setIsStartingStripe(true);
    try {
      await startOnlinePayment(order.id, method, details);
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Unable to open the payment page."));
      setIsStartingStripe(false);
    }
  }

  async function handleOtpPaid(result) {
    if (result?.transaction) {
      setOrder(result.transaction);
    }
    setMessage("Payment confirmed. Your order is marked as paid.");
    await loadOrder();
  }

  // The order receipt covers the whole order; the payment receipt below covers one
  // payment. Opened in a tab rather than fetched, because the server renders it and the
  // same URL is what goes out in the confirmation email.
  async function openOrderReceipt() {
    setError("");
    try {
      const { receiptToken } = await getCustomerOrderReceiptLink(order.id);
      window.open(orderReceiptUrl(receiptToken), "_blank", "noopener");
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Unable to open the receipt."));
    }
  }

  async function openReceipt(paymentRecordId) {
    setOpeningReceiptId(paymentRecordId);
    setError("");
    try {
      const html = await getCustomerPaymentReceiptHtml(order.id, paymentRecordId);
      openReceiptWindow(html);
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Unable to open payment receipt."));
    } finally {
      setOpeningReceiptId("");
    }
  }

  if (!order && loadError) {
    return (
      <section className="rounded-xl border border-dashed border-line bg-surface p-8 text-center">
        <div className="font-bold text-ink">This order is not available</div>
        <p className="mt-1 text-sm text-muted">{loadError}</p>
        <div className="mt-5 flex flex-wrap justify-center gap-2">
          <button className="ui-btn-primary" type="button" onClick={() => loadOrder()}>
            Try again
          </button>
          <Link className="ui-btn-secondary" to="/customer/orders">
            Back to my orders
          </Link>
        </div>
      </section>
    );
  }
  if (!order) return <section className="text-sm text-muted">Loading transaction...</section>;

  const paymentMethods = order.paymentInstructions?.methods || [];
  const selectedMethod = proofDraft.method || order.paymentPreference?.method || getDefaultPaymentMethod(order.paymentInstructions || {});
  const settledStatuses = ["paid", "cod", "refunded"];
  const isOnlineMethod = isOnlinePaymentMethod(selectedMethod);
  const canPayOnline = isOnlineMethod && !settledStatuses.includes(order.paymentStatus);
  // A gateway confirms its own payments, so asking the customer for a reference to be
  // verified by hand only applies to the offline methods.
  const canSubmitProof = selectedMethod && !isOnlineMethod && selectedMethod !== "cod" && !settledStatuses.includes(order.paymentStatus);
  const selectedMethodDetails = paymentMethods.find((method) => method.code === selectedMethod) || null;
  const onlineMethodLabel = selectedMethodDetails?.label || "the payment page";
  const nextAction =
    canPayOnline
      ? `Pay online with ${onlineMethodLabel}`
      : canSubmitProof
        ? "Submit payment proof"
        : order.paymentStatus === "paid"
          ? "Payment complete"
          : selectedMethod === "cod"
            ? "Pay cash on delivery"
            : "Track status";

  return (
    <section className="space-y-6">
      {otpMethod ? (
        <WalletOtpDialog
          order={order}
          method={otpMethod}
          customerEmail={customer?.email || ""}
          onClose={() => setOtpMethod(null)}
          onPaid={handleOtpPaid}
        />
      ) : null}
      <div className="rounded-2xl border border-line bg-surface-purple p-5 shadow-card">
        <Link className="text-sm font-semibold text-brand" to="/customer/orders">Back to orders</Link>
        <p className="mt-4 text-[11px] font-bold uppercase tracking-[0.16em] text-brand">Order detail</p>
        <h1 className="mt-1.5 text-2xl font-extrabold tracking-tight text-ink">{order.transactionNumber}</h1>
        <div className="mt-4 grid gap-3 lg:grid-cols-[1fr_auto] lg:items-center">
          <div className="rounded-xl border border-line bg-white p-4">
            <div className="flex items-center gap-2 text-sm font-bold text-ink">
              {order.paymentStatus === "paid" ? <CheckCircle2 size={17} className="text-green-600" /> : <CreditCard size={17} className="text-brand" />}
              Next step: {nextAction}
            </div>
            <p className="mt-1 text-sm leading-6 text-muted">
              Check the status, payment method, and proof section below. If payment is pending, finish it from this page.
            </p>
          </div>
          <button
            type="button"
            className="rounded-xl border border-line bg-white px-4 py-2 text-sm font-semibold text-ink"
            onClick={openOrderReceipt}
          >
            View receipt
          </button>
          <button
            type="button"
            className="rounded-xl border border-line bg-white px-4 py-2 text-sm font-semibold text-ink"
            onClick={async () => {
              // The orders list wraps its reorder button; this one did not, so a failure
              // here was an unhandled rejection and a button that appeared to do nothing.
              setError("");
              try {
                const result = await reorderCustomerTransaction(order.id);
                setMessage(`Items were added back to your cart for ${result.tenantSlug}.`);
              } catch (requestError) {
                setError(getApiErrorMessage(requestError, "That order could not be added to your cart."));
              }
            }}
          >
            Reorder these items
          </button>
        </div>
      </div>
      {message ? <div className="rounded-xl border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">{message}</div> : null}
      {error ? <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}
      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <div className="space-y-6">
          <div className="rounded-xl border border-line bg-white p-5 shadow-card">
            <SectionTitle>Items</SectionTitle>
            <div className="mt-4 space-y-3">
              {order.items.map((item) => (
                <div key={`${order.id}-${item.itemId}`} className="flex items-center justify-between rounded-xl border border-line p-4">
                  <div>
                    <div className="font-semibold text-ink">{item.name}</div>
                    <div className="text-sm text-muted">Qty: {item.quantity}</div>
                  </div>
                  <div className="text-sm font-semibold text-ink">{item.subtotal}</div>
                </div>
              ))}
            </div>
          </div>

          <form className="rounded-xl border border-line bg-white p-5 shadow-card" onSubmit={submitProof}>
            <div className="flex flex-col gap-2 border-b border-line pb-4 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <SectionTitle>Submit payment proof</SectionTitle>
                <p className="mt-1 text-sm text-muted">For bank, JazzCash, or EasyPaisa payments, send the reference and optional screenshot for owner verification.</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <PaymentStatusBadge status={order.paymentStatus} />
                <PaymentProofBadge summary={order.paymentProofSummary} />
              </div>
            </div>
            {canPayOnline ? (
              <div className="mt-4 rounded-2xl border border-brand-100 bg-brand-50 p-4">
                <h3 className="text-sm font-bold text-brand-900">Pay online with {onlineMethodLabel}</h3>
                <p className="mt-1 text-sm leading-6 text-brand-800">
                  You will be taken to the {onlineMethodLabel} payment page and returned here once it is done.
                  {selectedMethod === "stripe_test" && selectedMethodDetails?.mode !== "live"
                    ? " Test card 4242 4242 4242 4242 with any future expiry and CVC."
                    : ""}
                </p>
                {selectedMethodDetails?.simulated ? (
                  <p className="mt-2 rounded-xl bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-800">
                    Simulated gateway: no real money moves.
                  </p>
                ) : null}
                <button
                  type="button"
                  className="mt-3 inline-flex items-center gap-2 rounded-xl bg-brand px-4 py-2 text-sm font-semibold text-white disabled:opacity-60"
                  disabled={isStartingStripe}
                  onClick={() => startOnlineCheckout(selectedMethod)}
                >
                  {isStartingStripe ? "Opening payment page..." : `Pay with ${onlineMethodLabel}`}
                  <ArrowRight size={15} />
                </button>
              </div>
            ) : null}
            {isSyncingStripe ? (
              <div className="mt-4 rounded-xl border border-brand-100 bg-white p-3 text-sm font-semibold text-brand-800">
                Checking Stripe payment status...
              </div>
            ) : null}
            {canSubmitProof ? (
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                <label className="block text-sm font-medium text-ink">
                  <span className="mb-1.5 block">Amount</span>
                  <input className="form-input" min="1" required type="number" value={proofDraft.amount} onChange={(event) => setProofDraft((current) => ({ ...current, amount: event.target.value }))} />
                </label>
                <label className="block text-sm font-medium text-ink">
                  <span className="mb-1.5 block">Payment method</span>
                  <select className="form-input" value={selectedMethod} onChange={(event) => setProofDraft((current) => ({ ...current, method: event.target.value }))}>
                    {paymentMethods.filter((method) => method.code !== "cod").map((method) => (
                      <option key={method.code} value={method.code}>{method.label}</option>
                    ))}
                  </select>
                </label>
                <label className="block text-sm font-medium text-ink">
                  <span className="mb-1.5 block">Reference / Transaction ID</span>
                  <input className="form-input" placeholder="JazzCash/EasyPaisa/bank reference" value={proofDraft.referenceNumber} onChange={(event) => setProofDraft((current) => ({ ...current, referenceNumber: event.target.value }))} />
                </label>
                <label className="block text-sm font-medium text-ink">
                  <span className="mb-1.5 block">Proof screenshot</span>
                  <input className="form-input" accept="image/*" type="file" onChange={(event) => setProofDraft((current) => ({ ...current, proofFile: event.target.files?.[0] || null }))} />
                </label>
                <label className="block text-sm font-medium text-ink md:col-span-2">
                  <span className="mb-1.5 block">Notes</span>
                  <textarea className="form-input min-h-20" placeholder="Optional note for the business owner" value={proofDraft.notes} onChange={(event) => setProofDraft((current) => ({ ...current, notes: event.target.value }))} />
                </label>
                <button className="rounded-xl bg-brand px-4 py-2 text-sm font-semibold text-white disabled:opacity-60 md:col-span-2" disabled={isSubmittingProof}>
                  {isSubmittingProof ? "Submitting..." : "Submit proof for verification"}
                </button>
              </div>
            ) : !canPayOnline ? (
              <div className="mt-4 rounded-xl border border-dashed border-line bg-surface p-4 text-sm text-muted">
                {order.paymentStatus === "paid"
                  ? "This order is already marked paid."
                  : selectedMethod === "cod"
                    ? "COD does not need proof. The business will collect cash directly."
                    : "Payment proof is not needed for this order right now."}
              </div>
            ) : null}
          </form>

          <div className="rounded-xl border border-line bg-white p-5 shadow-card">
            <SectionTitle>Payment proof history</SectionTitle>
            <div className="mt-4 space-y-3">
              {(order.paymentRecords || []).map((record) => (
                <div key={record.id} className="rounded-xl border border-line bg-surface p-4 text-sm">
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                    <div>
                      <div className="font-semibold text-ink">{record.methodLabel || record.method}</div>
                      <div className="mt-1 text-muted">Reference: {record.referenceNumber || "Not provided"}</div>
                      {record.notes ? <div className="mt-1 text-muted">Notes: {record.notes}</div> : null}
                      {record.screenshotUrl ? <a className="mt-2 inline-flex font-semibold text-brand" href={resolveUploadUrl(record.screenshotUrl)} target="_blank" rel="noreferrer">View proof screenshot</a> : null}
                      <button
                        type="button"
                        className="mt-2 inline-flex rounded-xl border border-line px-3 py-1.5 text-xs font-semibold text-ink disabled:opacity-60"
                        disabled={openingReceiptId === record.id}
                        onClick={() => openReceipt(record.id)}
                      >
                        {openingReceiptId === record.id ? "Opening..." : "Open receipt"}
                      </button>
                    </div>
                    <div className="text-right">
                      <div className="font-semibold text-ink">PKR {Number(record.amount || 0).toLocaleString()}</div>
                      <div className="mt-1"><PaymentStatusBadge compact status={record.status} /></div>
                    </div>
                  </div>
                </div>
              ))}
              {!(order.paymentRecords || []).length ? <div className="rounded-xl border border-dashed border-line bg-surface p-4 text-sm text-muted">No payment proof submitted yet.</div> : null}
            </div>
          </div>
        </div>
        <div className="rounded-xl border border-line bg-white p-5 shadow-card">
          <SectionTitle>Summary</SectionTitle>
          <div className="mt-4 rounded-xl bg-brand-50 p-4">
            <div className="flex items-center gap-2 text-sm font-bold text-brand-900">
              <PackageCheck size={17} />
              {nextAction}
            </div>
          </div>
          <div className="mt-4 space-y-3 text-sm">
            <InfoRow label="Type" value={capitalize(formatTransactionType(order.transactionType))} />
            <InfoRow label="Status" value={order.status} />
            <div className="flex items-center justify-between border-b border-line-soft pb-3">
              <span className="text-muted">Payment</span>
              <PaymentStatusBadge compact status={order.paymentStatus} />
            </div>
            <InfoRow label="Preferred method" value={order.paymentPreference?.methodLabel || "-"} />
            <InfoRow label="Source" value={order.source} />
            <InfoRow label="Total" value={order.pricing?.total} />
          </div>
          {order.paymentInstructions ? (
            <div className="mt-5">
              <CustomerPaymentInstructions
                compact
                options={order.paymentInstructions}
                selectedMethod={order.paymentPreference?.method || order.paymentInstructions?.defaultMethod}
              />
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}

function openReceiptWindow(html) {
  const receiptWindow = window.open("", "_blank", "width=960,height=800");
  if (!receiptWindow) {
    throw new Error("Popup blocked. Please allow popups to view the receipt.");
  }
  receiptWindow.opener = null;
  receiptWindow.document.open();
  receiptWindow.document.write(html);
  receiptWindow.document.close();
}

function InfoRow({ label, value }) {
  return (
    <div className="flex items-center justify-between border-b border-line-soft pb-3 last:border-b-0 last:pb-0">
      <span className="text-muted">{label}</span>
      <span className="font-semibold capitalize text-ink">{value}</span>
    </div>
  );
}
