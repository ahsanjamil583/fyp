import { AlertTriangle, CheckCircle2, Clock, PlusCircle, Receipt, TrendingUp } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { Alert, Card, EmptyState, StatCard } from "../../components/ui/index.jsx";
import { getApiErrorMessage } from "../../services/apiError.js";
import { getCashierDashboard } from "../../services/cashierApi.js";
import { formatMoney, formatOrderTime, orderStatusTone, paymentStatusTone, StatusPill } from "./cashierShared.jsx";

export function CashierDashboard() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);

  const refresh = useCallback(async () => {
    setError("");
    try {
      setData(await getCashierDashboard());
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Unable to load the counter dashboard."));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    // A counter is usually left open all day; keep the totals honest without a reload.
    const intervalId = window.setInterval(refresh, 60000);
    return () => window.clearInterval(intervalId);
  }, [refresh]);

  if (isLoading) {
    return <div className="py-10 text-center text-sm text-muted">Opening the counter...</div>;
  }

  if (error && !data) {
    return (
      <div className="space-y-4">
        <Alert tone="red">{error}</Alert>
        <button type="button" className="ui-btn-secondary" onClick={refresh}>
          Try again
        </button>
      </div>
    );
  }

  const currency = data?.business?.currency || "PKR";
  const today = data?.today || {};
  const counters = data?.counters || {};
  const recent = data?.recentOrders || [];
  const peakDay = (data?.trend || []).reduce((best, row) => (row.total > (best?.total || 0) ? row : best), null);

  return (
    <section className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-brand">Counter</p>
          <h1 className="mt-1.5 text-2xl font-extrabold tracking-tight text-ink">
            Hello, {data?.cashier?.name || "Cashier"}
          </h1>
          <p className="mt-2 text-sm text-muted">{data?.business?.name}</p>
        </div>
        <Link to="/cashier/orders/new" className="ui-btn-primary px-6 py-3.5 text-base">
          <PlusCircle size={20} />
          New order
        </Link>
      </header>

      {error ? <Alert tone="orange">{error}</Alert> : null}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Today's sales" value={formatMoney(today.sales, currency)} icon={TrendingUp} tone="violet" />
        <StatCard label="Today's orders" value={today.orders ?? 0} icon={Receipt} tone="blue" />
        <StatCard label="Pending / unpaid" value={counters.unpaidOrders ?? 0} icon={Clock} tone="orange" hint={`${counters.pendingOrders ?? 0} still open`} />
        <StatCard label="Completed" value={counters.completedOrders ?? 0} icon={CheckCircle2} tone="green" />
      </div>

      {counters.unpaidOrders > 0 ? (
        <Card className="flex flex-wrap items-center gap-3 border-orange-200 bg-orange-50">
          <AlertTriangle size={18} className="text-orange-600" />
          <span className="text-sm font-semibold text-orange-700">
            {counters.unpaidOrders} order{counters.unpaidOrders === 1 ? "" : "s"} still waiting for payment.
          </span>
          <Link to="/cashier/orders?status=pending" className="ml-auto text-sm font-bold text-orange-700 underline">
            Review them
          </Link>
        </Card>
      ) : null}

      <Card>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-bold text-ink">Recent orders</h2>
            <p className="text-xs text-muted">
              {peakDay ? `Best day this week: ${peakDay.date} at ${formatMoney(peakDay.total, currency)}` : "Your last counter sales."}
            </p>
          </div>
          <Link to="/cashier/orders" className="text-sm font-bold text-brand">
            View all
          </Link>
        </div>

        {recent.length ? (
          <ul className="divide-y divide-line-soft">
            {recent.map((order) => (
              <li key={order.receiptToken} className="flex flex-wrap items-center gap-3 py-3">
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-bold text-ink">{order.transactionNumber}</div>
                  <div className="truncate text-xs text-muted">
                    {order.customerSnapshot?.name || "Walk-in customer"} · {formatOrderTime(order.createdAt)}
                  </div>
                </div>
                <StatusPill tone={orderStatusTone(order.status)}>{order.status}</StatusPill>
                <StatusPill tone={paymentStatusTone(order.paymentStatus)}>{order.paymentStatus?.replaceAll("_", " ")}</StatusPill>
                <div className="w-24 text-right text-sm font-extrabold text-ink">{formatMoney(order.pricing?.total, currency)}</div>
                <Link
                  to={`/cashier/receipts/${order.receiptToken}`}
                  className="ui-btn-secondary px-3 py-2 text-xs"
                >
                  <Receipt size={14} />
                  Receipt
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState
            icon={Receipt}
            title="No counter sales yet"
            description="Ring up your first in-store order and its receipt will be ready to print straight away."
            actionLabel="Create the first order"
            actionTo="/cashier/orders/new"
          />
        )}
      </Card>
    </section>
  );
}
