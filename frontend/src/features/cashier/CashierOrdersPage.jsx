import { PlusCircle, Receipt, Search } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { Alert, Card, EmptyState } from "../../components/ui/index.jsx";
import { getApiErrorMessage } from "../../services/apiError.js";
import { getCashierOrders, getCashierProfile } from "../../services/cashierApi.js";
import { formatMoney, formatOrderTime, orderStatusTone, paymentStatusTone, StatusPill } from "./cashierShared.jsx";

const STATUS_FILTERS = [
  { value: "", label: "All" },
  { value: "pending", label: "Pending" },
  { value: "completed", label: "Completed" },
  { value: "cancelled", label: "Cancelled" },
];

export function CashierOrdersPage({ receiptsMode = false }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const [orders, setOrders] = useState([]);
  const [meta, setMeta] = useState({});
  const [currency, setCurrency] = useState("PKR");
  const [searchTerm, setSearchTerm] = useState(searchParams.get("search") || "");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);

  const statusFilter = searchParams.get("status") || "";
  const page = Number(searchParams.get("page") || 1);

  useEffect(() => {
    getCashierProfile()
      .then((profile) => setCurrency(profile.business?.currency || "PKR"))
      .catch(() => {});
  }, []);

  const load = useCallback(async () => {
    setIsLoading(true);
    setError("");
    try {
      const result = await getCashierOrders({
        search: searchParams.get("search") || undefined,
        status: statusFilter || undefined,
        page,
        limit: 20,
      });
      setOrders(result.items);
      setMeta(result.meta || {});
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Unable to load your orders."));
    } finally {
      setIsLoading(false);
    }
  }, [searchParams, statusFilter, page]);

  useEffect(() => {
    load();
  }, [load]);

  function updateParams(changes) {
    const next = new URLSearchParams(searchParams);
    Object.entries(changes).forEach(([key, value]) => {
      if (value) next.set(key, String(value));
      else next.delete(key);
    });
    if (!("page" in changes)) next.delete("page");
    setSearchParams(next, { replace: true });
  }

  const title = receiptsMode ? "Receipts" : "Orders";
  const description = receiptsMode
    ? "Every receipt you can reprint, newest first."
    : "The counter orders you created, newest first.";

  return (
    <section className="space-y-5">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-brand">Counter</p>
          <h1 className="mt-1.5 text-2xl font-extrabold tracking-tight text-ink">{title}</h1>
          <p className="mt-2 text-sm text-muted">{description}</p>
        </div>
        <Link to="/cashier/orders/new" className="ui-btn-primary px-5 py-3">
          <PlusCircle size={18} />
          New order
        </Link>
      </header>

      {error ? <Alert tone="red">{error}</Alert> : null}

      <Card>
        <form
          className="flex flex-wrap items-center gap-3"
          onSubmit={(event) => {
            event.preventDefault();
            updateParams({ search: searchTerm });
          }}
        >
          <label className="relative min-w-[16rem] flex-1">
            <Search size={18} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-muted" />
            <input
              className="form-input pl-11"
              placeholder="Search by order number, customer or phone"
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
            />
          </label>
          <button type="submit" className="ui-btn-secondary">
            Search
          </button>
          <div className="flex flex-wrap gap-2">
            {STATUS_FILTERS.map((filter) => (
              <button
                key={filter.value || "all"}
                type="button"
                onClick={() => updateParams({ status: filter.value })}
                className={`rounded-full px-4 py-2 text-xs font-bold transition ${
                  statusFilter === filter.value ? "bg-brand text-white" : "border border-line bg-white text-muted hover:bg-surface"
                }`}
              >
                {filter.label}
              </button>
            ))}
          </div>
        </form>
      </Card>

      {isLoading ? <div className="py-8 text-center text-sm text-muted">Loading orders...</div> : null}

      {!isLoading && !orders.length ? (
        <EmptyState
          icon={Receipt}
          title="Nothing here yet"
          description="Counter orders you create will appear here with a printable receipt."
          actionLabel="Create an order"
          actionTo="/cashier/orders/new"
        />
      ) : null}

      <div className="space-y-3">
        {orders.map((order) => (
          <Card key={order.receiptToken} className="flex flex-wrap items-center gap-4">
            <div className="min-w-[12rem] flex-1">
              <div className="text-sm font-extrabold text-ink">{order.transactionNumber}</div>
              <div className="mt-1 text-xs text-muted">
                {order.customerSnapshot?.name || "Walk-in customer"}
                {order.customerSnapshot?.phone ? ` · ${order.customerSnapshot.phone}` : ""}
              </div>
              <div className="mt-1 text-xs text-subtle">{formatOrderTime(order.createdAt)}</div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <StatusPill tone={orderStatusTone(order.status)}>{order.status}</StatusPill>
              <StatusPill tone={paymentStatusTone(order.paymentStatus)}>{order.paymentStatus?.replaceAll("_", " ")}</StatusPill>
              {order.payment?.methodLabel ? <StatusPill tone="slate">{order.payment.methodLabel}</StatusPill> : null}
            </div>
            <div className="text-right">
              <div className="text-base font-extrabold text-ink">{formatMoney(order.pricing?.total, currency)}</div>
              <div className="text-xs text-muted">{order.items?.length || 0} line(s)</div>
            </div>
            <Link to={`/cashier/receipts/${order.receiptToken}`} className="ui-btn-secondary px-4 py-2.5">
              <Receipt size={16} />
              Receipt
            </Link>
          </Card>
        ))}
      </div>

      {meta.totalPages > 1 ? (
        <div className="flex items-center justify-center gap-3">
          <button
            type="button"
            className="ui-btn-secondary"
            disabled={page <= 1}
            onClick={() => updateParams({ page: page - 1 })}
          >
            Previous
          </button>
          <span className="text-sm font-semibold text-muted">
            Page {meta.page} of {meta.totalPages}
          </span>
          <button
            type="button"
            className="ui-btn-secondary"
            disabled={page >= meta.totalPages}
            onClick={() => updateParams({ page: page + 1 })}
          >
            Next
          </button>
        </div>
      ) : null}
    </section>
  );
}
