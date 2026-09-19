import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { CustomerPaymentInstructions } from "../../components/payments/CustomerPaymentInstructions.jsx";
import { PaymentProofBadge, PaymentStatusBadge } from "../../components/payments/PaymentStatusBadge.jsx";
import { useTenant } from "../../context/TenantContext.jsx";
import { decidePaymentRecord, getOwnerPaymentReceiptHtml, getPaymentOverview, recordTransactionPayment, refundTransactionPayment, syncStripePaymentRecord, updatePaymentSettings } from "../../services/paymentApi.js";
import { capitalize } from "../../utils/transaction.js";
import { SectionTitle } from "../../components/ui/SectionTitle.jsx";
import { StatCard as KitStatCard } from "../../components/ui/index.jsx";
import { getApiErrorMessage } from "../../services/apiError.js";

const defaultSettings = {
  codEnabled: true,
  manualEnabled: true,
  bankTransferEnabled: true,
  jazzCashEnabled: false,
  easyPaisaEnabled: false,
  stripeEnabled: false,
  paymentsDemoMode: true,
  requireOwnerApproval: true,
  bankName: "",
  jazzCashNumber: "",
  jazzCashAccountTitle: "",
  easyPaisaNumber: "",
  easyPaisaAccountTitle: "",
  bankAccountTitle: "",
  bankAccountNumber: "",
  bankIban: "",
  defaultMethod: "cod",
  customerInstructions: "",
};

const methodOptions = [
  { value: "cod", label: "Cash on Delivery" },
  { value: "manual_bank", label: "Manual bank transfer" },
  { value: "jazzcash_mock", label: "JazzCash mock" },
  { value: "easypaisa_mock", label: "EasyPaisa mock" },
  { value: "stripe_test", label: "Stripe test card" },
];

export function PaymentsPage() {
  const { selectedTenant } = useTenant();
  const [settings, setSettings] = useState(defaultSettings);
  const [records, setRecords] = useState([]);
  const [outstanding, setOutstanding] = useState([]);
  const [stripeWebhookEvents, setStripeWebhookEvents] = useState([]);
  const [summary, setSummary] = useState({});
  const [drafts, setDrafts] = useState({});
  const [refundDrafts, setRefundDrafts] = useState({});
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [savingSettings, setSavingSettings] = useState(false);
  const [savingPaymentId, setSavingPaymentId] = useState("");
  const [decisionDrafts, setDecisionDrafts] = useState({});

  useEffect(() => {
    if (selectedTenant?.id) {
      refreshOverview();
    }
  }, [selectedTenant?.id]);

  async function refreshOverview() {
    if (!selectedTenant?.id) return;
    setIsLoading(true);
    setError("");
    try {
      const result = await getPaymentOverview(selectedTenant.id, { page: 1, limit: 30 });
      const data = result.data || {};
      setSettings({ ...defaultSettings, ...(data.settings || {}) });
      setRecords(data.records || []);
      setOutstanding(data.outstandingTransactions || []);
      setStripeWebhookEvents(data.stripeWebhookEvents || []);
      setSummary(data.summary || {});
      setDrafts((current) => {
        const next = { ...current };
        (data.outstandingTransactions || []).forEach((transaction) => {
          const balance = transaction.paymentSummary?.balance ?? transaction.pricing?.total ?? 0;
          next[transaction.id] = next[transaction.id] || {
            amount: balance,
            method: data.settings?.defaultMethod || "cod",
            status: "paid",
            referenceNumber: "",
            notes: "",
          };
        });
        return next;
      });
      setRefundDrafts((current) => {
        const next = { ...current };
        (data.records || []).forEach((record) => {
          if (record.recordType === "payment" && ["paid", "completed"].includes(record.status)) {
            next[record.transactionId] = next[record.transactionId] || {
              amount: record.amount,
              method: record.method || "manual_bank",
              referenceNumber: "",
              notes: "",
            };
          }
        });
        return next;
      });
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Unable to load payment overview."));
    } finally {
      setIsLoading(false);
    }
  }

  function updateSetting(key, value) {
    setSettings((current) => ({ ...current, [key]: value }));
  }

  function updateDraft(transactionId, key, value) {
    setDrafts((current) => ({
      ...current,
      [transactionId]: { ...(current[transactionId] || {}), [key]: value },
    }));
  }

  function updateRefundDraft(transactionId, key, value) {
    setRefundDrafts((current) => ({
      ...current,
      [transactionId]: { ...(current[transactionId] || {}), [key]: value },
    }));
  }

  async function saveSettings(event) {
    event.preventDefault();
    setSavingSettings(true);
    setMessage("");
    setError("");
    try {
      const updated = await updatePaymentSettings(selectedTenant.id, settings);
      setSettings({ ...defaultSettings, ...updated });
      setMessage("Payment settings saved.");
      await refreshOverview();
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Unable to save payment settings."));
    } finally {
      setSavingSettings(false);
    }
  }

  async function submitPayment(transactionId) {
    const draft = drafts[transactionId];
    if (!draft) return;
    setSavingPaymentId(transactionId);
    setMessage("");
    setError("");
    try {
      await recordTransactionPayment(selectedTenant.id, transactionId, {
        ...draft,
        amount: Number(draft.amount || 0),
      });
      setMessage("Payment recorded.");
      await refreshOverview();
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Unable to record payment."));
    } finally {
      setSavingPaymentId("");
    }
  }

  async function submitRefund(transactionId) {
    const draft = refundDrafts[transactionId];
    if (!draft) return;
    setSavingPaymentId(`refund-${transactionId}`);
    setMessage("");
    setError("");
    try {
      await refundTransactionPayment(selectedTenant.id, transactionId, {
        ...draft,
        amount: Number(draft.amount || 0),
      });
      setMessage("Refund recorded.");
      await refreshOverview();
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Unable to record refund."));
    } finally {
      setSavingPaymentId("");
    }
  }

  function updateDecisionDraft(recordId, value) {
    setDecisionDrafts((current) => ({ ...current, [recordId]: value }));
  }

  async function submitDecision(recordId, decision) {
    setSavingPaymentId(`decision-${recordId}-${decision}`);
    setMessage("");
    setError("");
    try {
      await decidePaymentRecord(selectedTenant.id, recordId, {
        decision,
        notes: decisionDrafts[recordId] || "",
      });
      setMessage(decision === "approve" ? "Payment proof approved." : "Payment proof rejected.");
      await refreshOverview();
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Unable to save payment decision."));
    } finally {
      setSavingPaymentId("");
    }
  }

  async function syncStripeRecord(recordId) {
    setSavingPaymentId(`stripe-sync-${recordId}`);
    setMessage("");
    setError("");
    try {
      const data = await syncStripePaymentRecord(selectedTenant.id, recordId);
      if (data.providerStatus === "paid") {
        setMessage("Stripe payment confirmed and transaction marked paid.");
      } else {
        setMessage(`Stripe payment checked. Current Stripe status: ${data.providerStatus || "pending"}.`);
      }
      await refreshOverview();
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Unable to sync Stripe payment."));
    } finally {
      setSavingPaymentId("");
    }
  }

  async function openReceipt(recordId) {
    setSavingPaymentId(`receipt-${recordId}`);
    setError("");
    try {
      const html = await getOwnerPaymentReceiptHtml(selectedTenant.id, recordId);
      openReceiptWindow(html);
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Unable to open payment receipt."));
    } finally {
      setSavingPaymentId("");
    }
  }

  if (!selectedTenant) {
    return (
      <section className="space-y-4">
        <h1 className="text-2xl font-extrabold tracking-tight text-ink">Payments</h1>
        <p className="text-sm text-muted">Create a business before configuring payments.</p>
        <Link className="inline-flex rounded-xl bg-brand px-4 py-2 text-sm font-semibold text-white" to="/dashboard/business">
          Create Business
        </Link>
      </section>
    );
  }

  return (
    <section className="space-y-6">
      <div className="border-b border-line-soft pb-5">
        <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-brand">Phase 25</p>
        <h1 className="mt-1.5 text-2xl font-extrabold tracking-tight text-ink">Payments</h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-muted">
          Configure COD, manual, JazzCash, EasyPaisa, and bank transfer instructions. Record verified payments and refunds against orders.
        </p>
      </div>

      {message ? <div className="rounded-xl border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">{message}</div> : null}
      {error ? <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}

      <div className="grid gap-4 md:grid-cols-3 xl:grid-cols-6">
        <StatCard label="Received" value={formatMoney(summary.received || 0)} />
        <StatCard label="Pending review" value={formatMoney(summary.pendingVerification || 0)} />
        <StatCard label="COD selected" value={formatMoney(summary.cod || 0)} />
        <StatCard label="Refunded" value={formatMoney(summary.refunded || 0)} />
        <StatCard label="Net received" value={formatMoney(summary.netReceived || 0)} />
        <StatCard label="Outstanding" value={summary.outstandingTransactions || 0} />
      </div>

      <div className="grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
        <div className="rounded-xl border border-line bg-white p-5 shadow-card">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <SectionTitle>Stripe Test Payment Status</SectionTitle>
              <p className="mt-1 text-sm leading-6 text-muted">Use Stripe test cards for online payment demos. Local COD/manual methods still work independently.</p>
            </div>
            <span className={settings.stripeEnabled ? "w-fit rounded-full bg-brand-50 px-3 py-1 text-xs font-bold text-brand-700" : "w-fit rounded-full bg-slate-50 px-3 py-1 text-xs font-bold text-slate-600"}>
              {settings.stripeEnabled ? "Enabled" : "Disabled"}
            </span>
          </div>
          <div className="mt-4 grid gap-2 text-sm">
            <StatusRow label="Secret key" ready={settings.stripeConfigured} readyText="Configured" missingText="Missing STRIPE_SECRET_KEY" />
            <StatusRow label="Webhook secret" ready={settings.stripeWebhookConfigured} readyText="Configured" missingText="Optional locally, required in production" />
            <StatusRow label="Currency" ready value={settings.stripeCurrency || "PKR"} />
          </div>
          <div className="mt-4 rounded-xl border border-brand-100 bg-brand-50 p-3 text-xs leading-5 text-brand-800">
            Test card: 4242 4242 4242 4242, any future expiry, any CVC. Webhook URL: /api/v1/payments/stripe/webhook.
          </div>
        </div>
        <div className="rounded-xl border border-line bg-white p-5 shadow-card">
          <SectionTitle>Recent Stripe Webhooks</SectionTitle>
          <div className="mt-4 space-y-2">
            {stripeWebhookEvents.map((event) => (
              <div key={event.id} className="rounded-xl border border-line bg-surface p-3 text-sm">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <div className="font-semibold text-ink">{event.eventType || "Stripe event"}</div>
                    <div className="mt-1 text-xs text-muted">{event.eventId}</div>
                    {event.error ? <div className="mt-1 text-xs text-red-700">{event.error}</div> : null}
                  </div>
                  <span className={event.status === "processed" ? "w-fit rounded-full bg-green-50 px-2 py-1 text-xs font-bold text-green-700" : event.status === "failed" ? "w-fit rounded-full bg-red-50 px-2 py-1 text-xs font-bold text-red-700" : "w-fit rounded-full bg-slate-50 px-2 py-1 text-xs font-bold text-slate-700"}>
                    {event.status || "unknown"}
                  </span>
                </div>
              </div>
            ))}
            {!stripeWebhookEvents.length ? <div className="rounded-xl border border-dashed border-line bg-surface p-4 text-sm text-muted">No Stripe webhook events received yet.</div> : null}
          </div>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
        <form className="space-y-4 rounded-xl border border-line bg-white p-5 shadow-card" onSubmit={saveSettings}>
          <div>
            <SectionTitle>Payment Settings</SectionTitle>
            <p className="mt-1 text-sm text-muted">These settings are used by the order workflow and customer-facing payment instructions. COD/manual work without wallet numbers. JazzCash/EasyPaisa numbers are needed only when those wallet methods are enabled.</p>
            <div className="mt-3 rounded-xl border border-brand-100 bg-brand-50 p-3 text-xs leading-5 text-brand-800">
              Demo note: this phase records and verifies payments inside BizXusAI. It does not move real money unless you later connect real gateway credentials.
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Toggle label="COD" checked={settings.codEnabled} onChange={(value) => updateSetting("codEnabled", value)} />
            <Toggle label="Manual verification" checked={settings.manualEnabled} onChange={(value) => updateSetting("manualEnabled", value)} />
            <Toggle label="Bank transfer" checked={settings.bankTransferEnabled} onChange={(value) => updateSetting("bankTransferEnabled", value)} />
            <Toggle label="JazzCash" checked={settings.jazzCashEnabled} onChange={(value) => updateSetting("jazzCashEnabled", value)} />
            <Toggle label="EasyPaisa" checked={settings.easyPaisaEnabled} onChange={(value) => updateSetting("easyPaisaEnabled", value)} />
            <Toggle label="Stripe test card" checked={settings.stripeEnabled} onChange={(value) => updateSetting("stripeEnabled", value)} />
            <Toggle label="Demo mode" checked={settings.paymentsDemoMode} onChange={(value) => updateSetting("paymentsDemoMode", value)} />
            <Toggle label="Owner approval required" checked={settings.requireOwnerApproval} onChange={(value) => updateSetting("requireOwnerApproval", value)} />
          </div>
          <Field label="Default Method">
            <select className="form-input" value={settings.defaultMethod || "cod"} onChange={(event) => updateSetting("defaultMethod", event.target.value)}>
              {methodOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </Field>
          <div className="grid gap-3 sm:grid-cols-2">
            {settings.jazzCashEnabled ? (
              <Field label="JazzCash Number">
                <input className="form-input" value={settings.jazzCashNumber || ""} onChange={(event) => updateSetting("jazzCashNumber", event.target.value)} placeholder="03XXXXXXXXX" />
              </Field>
            ) : null}
            {settings.jazzCashEnabled ? (
              <Field label="JazzCash Account Title">
                <input className="form-input" value={settings.jazzCashAccountTitle || ""} onChange={(event) => updateSetting("jazzCashAccountTitle", event.target.value)} placeholder="Business owner name" />
              </Field>
            ) : null}
            {settings.easyPaisaEnabled ? (
              <Field label="EasyPaisa Number">
                <input className="form-input" value={settings.easyPaisaNumber || ""} onChange={(event) => updateSetting("easyPaisaNumber", event.target.value)} placeholder="03XXXXXXXXX" />
              </Field>
            ) : null}
            {settings.easyPaisaEnabled ? (
              <Field label="EasyPaisa Account Title">
                <input className="form-input" value={settings.easyPaisaAccountTitle || ""} onChange={(event) => updateSetting("easyPaisaAccountTitle", event.target.value)} placeholder="Business owner name" />
              </Field>
            ) : null}
            <Field label="Bank Name">
              <input className="form-input" value={settings.bankName || ""} onChange={(event) => updateSetting("bankName", event.target.value)} placeholder="HBL, Meezan, UBL..." />
            </Field>
            <Field label="Bank Account Title">
              <input className="form-input" value={settings.bankAccountTitle || ""} onChange={(event) => updateSetting("bankAccountTitle", event.target.value)} placeholder="Only for bank/manual transfer" />
            </Field>
            <Field label="Bank Account Number">
              <input className="form-input" value={settings.bankAccountNumber || ""} onChange={(event) => updateSetting("bankAccountNumber", event.target.value)} placeholder="Optional" />
            </Field>
            <Field label="IBAN">
              <input className="form-input" value={settings.bankIban || ""} onChange={(event) => updateSetting("bankIban", event.target.value)} placeholder="Optional" />
            </Field>
          </div>
          <Field label="Customer Payment Instructions">
            <textarea className="form-input min-h-28" value={settings.customerInstructions || ""} onChange={(event) => updateSetting("customerInstructions", event.target.value)} />
          </Field>
          <div>
            <div className="mb-2 text-sm font-semibold text-ink">Customer preview</div>
            <CustomerPaymentInstructions compact options={buildOwnerPaymentPreview(settings)} selectedMethod={settings.defaultMethod || "cod"} onChange={(value) => updateSetting("defaultMethod", value)} />
          </div>
          <button className="rounded-xl bg-brand px-4 py-2 text-sm font-semibold text-white disabled:opacity-60" disabled={savingSettings}>
            {savingSettings ? "Saving..." : "Save Payment Settings"}
          </button>
        </form>

        <div className="space-y-4 rounded-xl border border-line bg-white p-5 shadow-card">
          <div>
            <SectionTitle>Outstanding Transactions</SectionTitle>
            <p className="mt-1 text-sm text-muted">Approve customer-submitted proofs, or record COD/manual payments after checking them.</p>
          </div>
          {isLoading ? <div className="text-sm text-muted">Loading payments...</div> : null}
          <div className="space-y-3">
            {outstanding.map((transaction) => {
              const draft = drafts[transaction.id] || {};
              const balance = transaction.paymentSummary?.balance ?? transaction.pricing?.total ?? 0;
              return (
                <div key={transaction.id} className="rounded-xl border border-line bg-surface p-4">
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                    <div>
                      <div className="font-semibold text-ink">{transaction.transactionNumber}</div>
                      <div className="mt-1 text-xs text-muted">{transaction.customerSnapshot?.name || "Guest"} / {transaction.customerSnapshot?.phone || "No phone"}</div>
                      {transaction.paymentPreference?.methodLabel ? (
                        <div className="mt-2 w-fit rounded-full bg-brand-50 px-2 py-1 text-xs font-semibold text-brand-700">
                          Customer chose {transaction.paymentPreference.methodLabel}
                        </div>
                      ) : null}
                      <div className="mt-2">
                        <PaymentProofBadge summary={transaction.paymentProofSummary} />
                      </div>
                    </div>
                    <div className="text-sm">
                      <div className="font-semibold text-ink">Balance: {formatMoney(balance)}</div>
                      <div className="mt-2 flex justify-end">
                        <PaymentStatusBadge compact status={transaction.paymentStatus} />
                      </div>
                    </div>
                  </div>
                  <div className="mt-3 grid gap-3 md:grid-cols-2">
                    <Field label="Amount">
                      <input className="form-input" type="number" min="1" value={draft.amount ?? balance} onChange={(event) => updateDraft(transaction.id, "amount", event.target.value)} />
                    </Field>
                    <Field label="Method">
                      <select className="form-input" value={draft.method || settings.defaultMethod || "cod"} onChange={(event) => updateDraft(transaction.id, "method", event.target.value)}>
                        {methodOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                      </select>
                    </Field>
                    <Field label="Record Status">
                      <select className="form-input" value={draft.status || "paid"} onChange={(event) => updateDraft(transaction.id, "status", event.target.value)}>
                        <option value="paid">Paid / verified</option>
                        <option value="pending_verification">Pending verification</option>
                        <option value="rejected">Rejected</option>
                      </select>
                    </Field>
                    <Field label="Reference Number">
                      <input className="form-input" value={draft.referenceNumber || ""} onChange={(event) => updateDraft(transaction.id, "referenceNumber", event.target.value)} />
                    </Field>
                    <div className="md:col-span-2">
                      <Field label="Notes">
                        <textarea className="form-input min-h-20" value={draft.notes || ""} onChange={(event) => updateDraft(transaction.id, "notes", event.target.value)} />
                      </Field>
                    </div>
                  </div>
                  <button
                    type="button"
                    className="mt-3 rounded-xl bg-ink px-4 py-2 text-sm font-semibold text-white disabled:opacity-60"
                    disabled={savingPaymentId === transaction.id}
                    onClick={() => submitPayment(transaction.id)}
                  >
                    {savingPaymentId === transaction.id ? "Recording..." : "Record Payment"}
                  </button>
                </div>
              );
            })}
            {!outstanding.length && !isLoading ? <div className="rounded-xl border border-dashed border-line p-4 text-sm text-muted">No outstanding payment transactions.</div> : null}
          </div>
        </div>
      </div>

      <div className="rounded-xl border border-line bg-white p-5 shadow-card">
        <SectionTitle>Recent Payment Records</SectionTitle>
        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full divide-y divide-line text-sm">
            <thead className="bg-surface text-left text-[11px] font-bold uppercase tracking-[0.12em] text-subtle">
              <tr>
                <th className="px-3 py-2">Transaction</th>
                <th className="px-3 py-2">Customer</th>
                <th className="px-3 py-2">Type</th>
                <th className="px-3 py-2">Method</th>
                <th className="px-3 py-2">Amount</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Proof / Reference</th>
                <th className="px-3 py-2">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {records.map((record) => {
                const refundDraft = refundDrafts[record.transactionId] || {};
                const isPendingStripe = record.recordType === "payment" && record.provider === "stripe" && record.status === "pending_verification";
                return (
                  <tr key={record.id}>
                    <td className="px-3 py-3 font-semibold text-ink">{record.transactionNumber}</td>
                    <td className="px-3 py-3 text-muted">{record.customerSnapshot?.name || "Guest"}</td>
                    <td className="px-3 py-3 capitalize text-muted">{record.recordType}</td>
                    <td className="px-3 py-3 capitalize text-muted">
                      {String(record.method || "").replaceAll("_", " ")}
                      {record.flow === "otp" ? (
                        <span className="mt-1 block text-[11px] font-bold uppercase tracking-wider text-amber-700">
                          Verification code
                        </span>
                      ) : null}
                      {record.customerMobile ? (
                        <span className="block text-[11px] normal-case text-subtle">{record.customerMobile}</span>
                      ) : null}
                    </td>
                    <td className="px-3 py-3 text-muted">{formatMoney(record.amount)}</td>
                    <td className="px-3 py-3"><PaymentStatusBadge compact status={record.status} /></td>
                    <td className="px-3 py-3 text-muted">
                      <div className="min-w-44 space-y-1">
                        <div>{record.referenceNumber || "No reference"}</div>
                        {record.provider === "stripe" ? (
                          <>
                            <div className="text-xs font-semibold text-brand-700">Stripe session: {record.providerSessionId || "Not captured"}</div>
                            {record.lastProviderSyncStatus ? <div className="text-xs text-muted">Last sync: {record.lastProviderSyncStatus}</div> : null}
                          </>
                        ) : null}
                        {record.screenshotUrl ? (
                          <a className="font-semibold text-brand" href={resolveUploadUrl(record.screenshotUrl)} target="_blank" rel="noreferrer">
                            View screenshot
                          </a>
                        ) : null}
                        {record.submittedBy === "customer" ? <div className="text-xs font-semibold text-brand-700">Submitted by customer</div> : null}
                        <button
                          type="button"
                          className="rounded-xl border border-line px-2.5 py-1.5 text-xs font-semibold text-ink disabled:opacity-60"
                          disabled={savingPaymentId === `receipt-${record.id}`}
                          onClick={() => openReceipt(record.id)}
                        >
                          {savingPaymentId === `receipt-${record.id}` ? "Opening..." : "Open receipt"}
                        </button>
                      </div>
                    </td>
                    <td className="px-3 py-3">
                      {isPendingStripe ? (
                        <div className="min-w-44">
                          <button
                            className="rounded-xl bg-brand-600 px-3 py-2 text-xs font-semibold text-white disabled:opacity-60"
                            disabled={savingPaymentId === `stripe-sync-${record.id}`}
                            onClick={() => syncStripeRecord(record.id)}
                          >
                            {savingPaymentId === `stripe-sync-${record.id}` ? "Syncing..." : "Sync Stripe"}
                          </button>
                          <p className="mt-2 max-w-48 text-xs leading-5 text-muted">Use this if the customer returned from Stripe but the webhook has not updated yet.</p>
                        </div>
                      ) : record.recordType === "payment" && record.status === "pending_verification" ? (
                        <div className="flex min-w-60 flex-col gap-2">
                          <input
                            className="form-input"
                            placeholder="Decision notes optional"
                            value={decisionDrafts[record.id] || ""}
                            onChange={(event) => updateDecisionDraft(record.id, event.target.value)}
                          />
                          <div className="grid grid-cols-2 gap-2">
                            <button className="rounded-xl bg-green-600 px-3 py-2 text-xs font-semibold text-white disabled:opacity-60" disabled={savingPaymentId === `decision-${record.id}-approve`} onClick={() => submitDecision(record.id, "approve")}>
                              Approve
                            </button>
                            <button className="rounded-xl border border-red-200 px-3 py-2 text-xs font-semibold text-red-700 disabled:opacity-60" disabled={savingPaymentId === `decision-${record.id}-reject`} onClick={() => submitDecision(record.id, "reject")}>
                              Reject
                            </button>
                          </div>
                        </div>
                      ) : record.recordType === "payment" && ["paid", "completed"].includes(record.status) ? (
                        <div className="flex flex-col gap-2 min-w-52">
                          <input className="form-input" type="number" min="1" value={refundDraft.amount ?? record.amount} onChange={(event) => updateRefundDraft(record.transactionId, "amount", event.target.value)} />
                          <input className="form-input" placeholder="Refund reference" value={refundDraft.referenceNumber || ""} onChange={(event) => updateRefundDraft(record.transactionId, "referenceNumber", event.target.value)} />
                          <button className="rounded-xl border border-line px-3 py-2 text-xs font-semibold text-ink" disabled={savingPaymentId === `refund-${record.transactionId}`} onClick={() => submitRefund(record.transactionId)}>
                            {savingPaymentId === `refund-${record.transactionId}` ? "Saving..." : "Record Refund"}
                          </button>
                        </div>
                      ) : <span className="text-xs text-muted">-</span>}
                    </td>
                  </tr>
                );
              })}
              {!records.length ? (
                <tr>
                  <td className="px-3 py-5 text-sm text-muted" colSpan="8">No payment records yet.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}

function StatCard({ label, value }) {
  return <KitStatCard label={label} value={value} />;
}

function Field({ label, children }) {
  return (
    <label className="block space-y-2 text-sm font-medium text-ink">
      <span>{label}</span>
      {children}
    </label>
  );
}

function Toggle({ label, checked, onChange }) {
  return (
    <label className="flex items-center justify-between rounded-xl border border-line px-3 py-2 text-sm text-ink">
      <span>{label}</span>
      <input type="checkbox" checked={Boolean(checked)} onChange={(event) => onChange(event.target.checked)} />
    </label>
  );
}

function StatusRow({ label, ready, readyText = "Ready", missingText = "Needs setup", value = "" }) {
  return (
    <div className="flex items-center justify-between rounded-xl border border-line px-3 py-2">
      <span className="font-medium text-ink">{label}</span>
      <span className={ready ? "rounded-full bg-green-50 px-2 py-1 text-xs font-bold text-green-700" : "rounded-full bg-amber-50 px-2 py-1 text-xs font-bold text-amber-700"}>
        {value || (ready ? readyText : missingText)}
      </span>
    </div>
  );
}

function buildOwnerPaymentPreview(settings = {}) {
  const methods = [];
  if (settings.codEnabled) {
    methods.push({
      code: "cod",
      label: "Cash on Delivery",
      description: "Pay cash when your order is delivered or picked up.",
      requiresOwnerApproval: false,
    });
  }
  if (settings.manualEnabled || settings.bankTransferEnabled) {
    methods.push({
      code: "manual_bank",
      label: "Manual bank transfer",
      description: "Transfer the amount, then share the reference with the business for verification.",
      requiresOwnerApproval: true,
      accountTitle: settings.bankAccountTitle || "",
      accountNumber: settings.bankAccountNumber || "",
      bankName: settings.bankName || "",
      iban: settings.bankIban || "",
    });
  }
  if (settings.jazzCashEnabled) {
    methods.push({
      code: "jazzcash_mock",
      label: "JazzCash mock",
      description: "Send payment through JazzCash, then share the transaction ID for owner verification.",
      requiresOwnerApproval: true,
      accountTitle: settings.jazzCashAccountTitle || "",
      accountNumber: settings.jazzCashNumber || "",
      bankName: "JazzCash",
    });
  }
  if (settings.easyPaisaEnabled) {
    methods.push({
      code: "easypaisa_mock",
      label: "EasyPaisa mock",
      description: "Send payment through EasyPaisa, then share the transaction ID for owner verification.",
      requiresOwnerApproval: true,
      accountTitle: settings.easyPaisaAccountTitle || "",
      accountNumber: settings.easyPaisaNumber || "",
      bankName: "EasyPaisa",
    });
  }
  if (settings.stripeEnabled) {
    methods.push({
      code: "stripe_test",
      label: "Stripe test card",
      description: "Pay online with Stripe Checkout using a test card.",
      requiresOwnerApproval: false,
      isOnline: true,
      provider: "stripe",
      testCard: "4242 4242 4242 4242",
    });
  }
  return {
    enabled: methods.length > 0,
    methods,
    defaultMethod: settings.defaultMethod || methods[0]?.code || "cod",
    customerInstructions: settings.customerInstructions || "",
    paymentsDemoMode: settings.paymentsDemoMode,
    requireOwnerApproval: settings.requireOwnerApproval,
  };
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

function formatMoney(value) {
  const number = Number(value || 0);
  return `PKR ${number.toLocaleString()}`;
}

function resolveUploadUrl(url) {
  if (!url) return "";
  if (url.startsWith("http")) return url;
  const apiBase = import.meta.env.VITE_API_BASE_URL || "/api/v1";
  return `${apiBase.replace("/api/v1", "")}${url}`;
}
