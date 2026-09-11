import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { PaymentLifecycleNote, PaymentProofBadge, PaymentStatusBadge } from "../../components/payments/PaymentStatusBadge.jsx";
import { useTenant } from "../../context/TenantContext.jsx";
import { getTenantTransactions, updateTenantTransaction } from "../../services/transactionApi.js";
import { capitalize, formatTransactionType } from "../../utils/transaction.js";
import { StatCard as KitStatCard } from "../../components/ui/index.jsx";

export function TransactionsPage() {
  const { selectedTenant } = useTenant();
  const [transactions, setTransactions] = useState([]);
  const [meta, setMeta] = useState({});
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [savingId, setSavingId] = useState("");
  const [drafts, setDrafts] = useState({});

  useEffect(() => {
    if (selectedTenant?.id) {
      refreshTransactions();
    }
  }, [selectedTenant?.id, statusFilter, typeFilter, sourceFilter]);

  async function refreshTransactions(nextSearch = search) {
    if (!selectedTenant?.id) {
      return;
    }
    setIsLoading(true);
    setError("");
    try {
      const result = await getTenantTransactions(selectedTenant.id, {
        search: nextSearch || undefined,
        status: statusFilter || undefined,
        transactionType: typeFilter || undefined,
        source: sourceFilter || undefined,
        page: 1,
        limit: 25,
      });
      setTransactions(result.items);
      setMeta(result.meta);
      setDrafts((current) => {
        const next = { ...current };
        result.items.forEach((transaction) => {
          next[transaction.id] = next[transaction.id] || {
            status: transaction.status,
            paymentStatus: transaction.paymentStatus,
            internalNotes: transaction.internalNotes || "",
          };
        });
        return next;
      });
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to load transactions.");
    } finally {
      setIsLoading(false);
    }
  }

  function updateDraft(transactionId, key, value) {
    setDrafts((current) => ({
      ...current,
      [transactionId]: {
        status: current[transactionId]?.status || "",
        paymentStatus: current[transactionId]?.paymentStatus || "",
        internalNotes: current[transactionId]?.internalNotes || "",
        [key]: value,
      },
    }));
  }

  async function saveTransaction(transactionId) {
    const draft = drafts[transactionId];
    if (!draft) return;
    setSavingId(transactionId);
    setMessage("");
    setError("");
    try {
      const updated = await updateTenantTransaction(selectedTenant.id, transactionId, draft);
      setTransactions((current) => current.map((transaction) => (transaction.id === transactionId ? updated : transaction)));
      setDrafts((current) => ({
        ...current,
        [transactionId]: {
          status: updated.status,
          paymentStatus: updated.paymentStatus,
          internalNotes: updated.internalNotes || "",
        },
      }));
      setMessage(`${updated.transactionNumber} updated.`);
      await refreshTransactions();
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to update transaction.");
    } finally {
      setSavingId("");
    }
  }

  if (!selectedTenant) {
    return (
      <section className="space-y-4">
        <h1 className="text-2xl font-extrabold tracking-tight text-ink">Transactions</h1>
        <p className="text-sm text-muted">Create a business before managing transactions.</p>
        <Link className="inline-flex rounded-xl bg-brand px-4 py-2 text-sm font-semibold text-white" to="/dashboard/business">
          Create Business
        </Link>
      </section>
    );
  }

  const summary = meta.summary || {};
  const filters = meta.filters || {};

  return (
    <section className="space-y-6">
      <div className="border-b border-line-soft pb-5">
        <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-brand">Operations</p>
        <h1 className="mt-1.5 text-2xl font-extrabold tracking-tight text-ink">Transactions</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-muted">
          Review orders, quote requests, booking requests, and inquiries from one queue and move them through their workflow.
        </p>
      </div>

      {message ? <div className="rounded-xl border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">{message}</div> : null}
      {error ? <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
        <StatCard label="Total" value={summary.totalTransactions || 0} />
        <StatCard label="Orders" value={summary.byType?.order || 0} />
        <StatCard label="Quotes" value={summary.byType?.quote_request || 0} />
        <StatCard label="Bookings" value={summary.byType?.booking_request || 0} />
        <StatCard label="Inquiries" value={summary.byType?.inquiry || 0} />
      </div>

      <div className="grid gap-4 md:grid-cols-4">
        <StatCard label="Stock Reserved" value={summary.byInventoryStatus?.reserved || 0} />
        <StatCard label="Stock Deducted" value={summary.byInventoryStatus?.deducted || 0} />
        <StatCard label="Stock Released" value={summary.byInventoryStatus?.released || 0} />
        <StatCard label="No Stock Needed" value={summary.byInventoryStatus?.not_required || 0} />
      </div>

      <form
        className="grid gap-3 rounded-xl border border-line bg-white p-5 shadow-card md:grid-cols-2 xl:grid-cols-[1.6fr_1fr_1fr_1fr_auto]"
        onSubmit={(event) => {
          event.preventDefault();
          refreshTransactions(search);
        }}
      >
        <input className="form-input" placeholder="Search by number, customer, phone, email, or item" value={search} onChange={(event) => setSearch(event.target.value)} />
        <select className="form-input" value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}>
          <option value="">All types</option>
          {(filters.transactionTypes || []).map((value) => (
            <option key={value} value={value}>{capitalize(formatTransactionType(value))}</option>
          ))}
        </select>
        <select className="form-input" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
          <option value="">All statuses</option>
          {(filters.statuses || []).map((value) => (
            <option key={value} value={value}>{capitalize(value.replaceAll("_", " "))}</option>
          ))}
        </select>
        <select className="form-input" value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value)}>
          <option value="">All sources</option>
          {(filters.sources || []).map((value) => (
            <option key={value} value={value}>{value}</option>
          ))}
        </select>
        <button className="rounded-xl bg-ink px-4 py-2 text-sm font-semibold text-white">Search</button>
      </form>

      {isLoading ? <div className="text-sm text-muted">Loading transactions...</div> : null}

      <div className="space-y-4">
        {transactions.map((transaction) => {
          const draft = drafts[transaction.id] || {
            status: transaction.status,
            paymentStatus: transaction.paymentStatus,
            internalNotes: transaction.internalNotes || "",
          };
          const statusOptions = transaction.statusOptions || fallbackStatusOptions(transaction.transactionType);
          const paymentOptions = transaction.paymentStatusOptions || fallbackPaymentOptions(transaction.transactionType);
          const paymentNote = PaymentLifecycleNote({ transaction });

          return (
            <div key={transaction.id} className="rounded-xl border border-line bg-white p-5 shadow-card">
              <div className="flex flex-col gap-4 border-b border-line pb-4 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <div className="text-[11px] font-bold uppercase tracking-[0.16em] text-brand">{formatTransactionType(transaction.transactionType)}</div>
                  <h2 className="mt-1 text-lg font-bold text-ink">{transaction.transactionNumber}</h2>
                  <div className="mt-2 text-sm text-muted">
                    {transaction.customerSnapshot?.name || "Guest"} / {transaction.customerSnapshot?.phone || "No phone"} / {transaction.source}
                  </div>
                  <div className="mt-1 text-xs text-muted">{new Date(transaction.createdAt).toLocaleString()}</div>
                </div>
                <div className="text-right text-sm">
                  <div className="font-semibold text-ink">{transaction.pricing?.total ?? 0}</div>
                  <div className="mt-1 capitalize text-muted">Status: {transaction.status}</div>
                  <div className="mt-2 flex justify-end">
                    <PaymentStatusBadge compact status={transaction.paymentStatus} />
                  </div>
                  <div className="mt-2 flex justify-end">
                    <PaymentProofBadge summary={transaction.paymentProofSummary} />
                  </div>
                  <div className="mt-1 capitalize text-muted">Inventory: {transaction.inventoryStatus || "pending"}</div>
                </div>
              </div>

              <div className="mt-4 grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
                <div>
                  <div className="text-sm font-semibold text-ink">Items</div>
                  <div className="mt-3 space-y-2">
                    {(transaction.items || []).length ? (
                      transaction.items.map((item, index) => (
                        <div key={`${transaction.id}-${index}`} className="rounded-xl border border-line px-3 py-2 text-sm">
                          <div className="font-semibold text-ink">{item.name}</div>
                          <div className="mt-1 text-muted">Qty: {item.quantity} / Unit: {item.unitPrice} / Subtotal: {item.subtotal}</div>
                          {item.selectedVariantName || item.selectedOptions ? (
                            <div className="mt-1 text-xs text-muted">
                              Variant: {item.selectedVariantName || "Selected"}
                              {item.selectedOptions ? ` / ${Object.entries(item.selectedOptions).map(([key, value]) => `${key}: ${value}`).join(", ")}` : ""}
                            </div>
                          ) : null}
                          {item.stockSnapshot?.tracked ? (
                            <div className="mt-1 text-xs text-muted">
                              Stock: requested {item.stockSnapshot.requestedQuantity}, available at order time {item.stockSnapshot.availableQuantity}
                            </div>
                          ) : null}
                        </div>
                      ))
                    ) : (
                      <div className="rounded-xl border border-dashed border-line bg-surface p-3 text-sm text-muted">No items attached.</div>
                    )}
                  </div>

                  {transaction.notes ? (
                    <div className="mt-4">
                      <div className="text-sm font-semibold text-ink">Customer Notes</div>
                      <div className="mt-2 rounded-xl border border-line bg-surface px-3 py-2 text-sm text-muted">{transaction.notes}</div>
                    </div>
                  ) : null}

                  {transaction.paymentSummary ? (
                    <div className="mt-4">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="text-sm font-semibold text-ink">Payment Summary</div>
                        <Link className="text-xs font-semibold text-brand" to="/dashboard/payments">Open payments</Link>
                      </div>
                      <div className="mt-2 grid gap-2 rounded-xl border border-line bg-surface px-3 py-2 text-xs text-muted sm:grid-cols-4">
                        <span>Total: {transaction.paymentSummary.total ?? transaction.pricing?.total ?? 0}</span>
                        <span>Paid: {transaction.paymentSummary.paid ?? 0}</span>
                        <span>Pending: {transaction.paymentSummary.pending ?? 0}</span>
                        <span>Balance: {transaction.paymentSummary.balance ?? 0}</span>
                      </div>
                      {paymentNote ? (
                        <div className="mt-2 rounded-xl border border-amber-100 bg-amber-50 px-3 py-2 text-xs font-medium text-amber-800">
                          {paymentNote}
                        </div>
                      ) : null}
                    </div>
                  ) : null}

                  {transaction.inventoryMovementsDetailed?.length ? (
                    <div className="mt-4">
                      <div className="text-sm font-semibold text-ink">Inventory Movements</div>
                      <div className="mt-2 space-y-2">
                        {transaction.inventoryMovementsDetailed.slice(0, 4).map((entry, index) => (
                          <div key={`${transaction.id}-inventory-${index}`} className="rounded-xl border border-line px-3 py-2 text-xs text-muted">
                            <span className="font-semibold text-ink">{entry.movementType}</span> {entry.quantity} x {entry.itemName}
                            {entry.variantName ? ` / ${entry.variantName}` : ""}
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}

                  {transaction.statusHistory?.length ? (
                    <div className="mt-4">
                      <div className="text-sm font-semibold text-ink">Status History</div>
                      <div className="mt-2 space-y-2">
                        {transaction.statusHistory.slice().reverse().slice(0, 4).map((entry, index) => (
                          <div key={`${transaction.id}-history-${index}`} className="rounded-xl border border-line px-3 py-2 text-xs text-muted">
                            <span className="font-semibold text-ink">{entry.field}</span> {entry.from || "new"} to {entry.to}
                            {entry.note ? ` / ${entry.note}` : ""}
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </div>

                <div className="space-y-4 rounded-xl border border-line bg-surface p-4">
                  <div className="text-sm font-semibold text-ink">Workflow Control</div>
                  <Field label="Status">
                    <select className="form-input" value={draft.status || ""} onChange={(event) => updateDraft(transaction.id, "status", event.target.value)}>
                      {statusOptions.map((value) => (
                        <option key={value} value={value}>{capitalize(value.replaceAll("_", " "))}</option>
                      ))}
                    </select>
                  </Field>
                  <Field label="Payment Status">
                    <select className="form-input" value={draft.paymentStatus || ""} onChange={(event) => updateDraft(transaction.id, "paymentStatus", event.target.value)}>
                      {paymentOptions.map((value) => (
                        <option key={value} value={value}>{capitalize(value.replaceAll("_", " "))}</option>
                      ))}
                    </select>
                  </Field>
                  <Field label="Internal Notes">
                    <textarea className="form-input min-h-24" value={draft.internalNotes || ""} onChange={(event) => updateDraft(transaction.id, "internalNotes", event.target.value)} />
                  </Field>
                  <button
                    type="button"
                    className="w-full rounded-xl bg-brand px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
                    disabled={savingId === transaction.id}
                    onClick={() => saveTransaction(transaction.id)}
                  >
                    {savingId === transaction.id ? "Saving..." : "Save Update"}
                  </button>
                </div>
              </div>
            </div>
          );
        })}

        {!transactions.length && !isLoading ? (
          <div className="rounded-xl border border-dashed border-line bg-surface p-6 text-sm text-muted">No transactions matched your current filters.</div>
        ) : null}
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

function fallbackStatusOptions(transactionType) {
  if (transactionType === "quote_request") return ["requested", "quoted", "approved", "rejected", "cancelled"];
  if (transactionType === "booking_request") return ["requested", "confirmed", "completed", "cancelled"];
  if (transactionType === "inquiry") return ["open", "responded", "closed", "cancelled"];
  return ["pending", "confirmed", "processing", "ready", "completed", "cancelled"];
}

function fallbackPaymentOptions(transactionType) {
  if (transactionType === "quote_request") return ["awaiting_quote", "quoted", "paid", "not_applicable"];
  if (transactionType === "inquiry") return ["not_applicable"];
  return ["unpaid", "partially_paid", "paid", "refunded"];
}
