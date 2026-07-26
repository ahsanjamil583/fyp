import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { useModules } from "../../context/ModuleContext.jsx";
import { useTenant } from "../../context/TenantContext.jsx";
import { getAnalyticsSummary } from "../../services/analyticsApi.js";
import { formatTransactionType } from "../../utils/transaction.js";

function StatCard({ label, value, helper }) {
  return (
    <div className="rounded-md border border-line bg-surface p-4">
      <div className="text-sm text-muted">{label}</div>
      <div className="mt-2 text-2xl font-semibold text-ink">{value}</div>
      {helper ? <div className="mt-2 text-xs text-muted">{helper}</div> : null}
    </div>
  );
}

function MiniBarChart({ title, points, dataKey, colorClass = "bg-brand", valueFormatter = (value) => value }) {
  const max = Math.max(...points.map((point) => Number(point[dataKey] || 0)), 1);
  return (
    <div className="rounded-md border border-line bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between border-b border-line pb-3">
        <h2 className="text-lg font-semibold text-ink">{title}</h2>
        <span className="text-xs uppercase tracking-wide text-muted">Last 7 days</span>
      </div>
      <div className="mt-5 flex items-end gap-3">
        {points.map((point) => {
          const value = Number(point[dataKey] || 0);
          const height = Math.max(14, Math.round((value / max) * 140));
          return (
            <div key={`${title}-${point.date}`} className="flex flex-1 flex-col items-center gap-2">
              <div className="text-xs font-semibold text-ink">{valueFormatter(value)}</div>
              <div className="flex h-36 w-full items-end rounded-md bg-surface px-1">
                <div className={`w-full rounded-t-md ${colorClass}`} style={{ height }} />
              </div>
              <div className="text-xs text-muted">{point.label}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function InsightTile({ label, value, helper }) {
  return (
    <div className="rounded-md border border-line bg-surface p-4">
      <div className="text-sm text-muted">{label}</div>
      <div className="mt-2 text-2xl font-semibold text-ink">{value}</div>
      {helper ? <div className="mt-2 text-xs text-muted">{helper}</div> : null}
    </div>
  );
}

export function AnalyticsPage() {
  const { selectedTenant, isLoadingTenants } = useTenant();
  const { enabledModules } = useModules();
  const [analytics, setAnalytics] = useState(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const analyticsEnabled = enabledModules.includes("analytics");

  useEffect(() => {
    async function loadAnalytics() {
      if (!selectedTenant || !analyticsEnabled) {
        setAnalytics(null);
        return;
      }
      setIsLoading(true);
      setError("");
      try {
        const data = await getAnalyticsSummary(selectedTenant.id);
        setAnalytics(data);
      } catch (requestError) {
        setError(requestError.response?.data?.detail || "Unable to load analytics.");
      } finally {
        setIsLoading(false);
      }
    }

    loadAnalytics();
  }, [selectedTenant, analyticsEnabled]);

  if (isLoadingTenants) {
    return <section className="text-sm text-muted">Loading analytics workspace...</section>;
  }

  if (!selectedTenant) {
    return (
      <section className="space-y-5">
        <h1 className="text-3xl font-semibold text-ink">No business selected</h1>
        <p className="text-sm leading-6 text-muted">Create or select a business first to view analytics.</p>
      </section>
    );
  }

  if (!analyticsEnabled) {
    return (
      <section className="space-y-5">
        <div className="border-b border-line pb-6">
          <p className="text-sm font-semibold uppercase tracking-wide text-brand">Analytics</p>
          <h1 className="mt-2 text-3xl font-semibold text-ink">Enable analytics for {selectedTenant.name}</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-muted">Phase 13 dashboards unlock after the analytics module is enabled for this business.</p>
        </div>
        <Link className="inline-flex rounded-md bg-brand px-4 py-2 text-sm font-semibold text-white" to="/dashboard/modules">
          Manage Modules
        </Link>
      </section>
    );
  }

  const summary = analytics?.summary || {};
  const revenue = analytics?.revenue || {};
  const trends = analytics?.trends || [];
  const topItems = analytics?.topItems || [];
  const conversion = analytics?.conversion || {};
  const categoryGuidance = analytics?.categoryGuidance || {};

  return (
    <section className="space-y-6">
      <div className="flex flex-col gap-4 border-b border-line pb-6 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-brand">Analytics</p>
          <h1 className="mt-2 text-3xl font-semibold text-ink">{selectedTenant.name}</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-muted">
            Monitor transactions, revenue, inventory pressure, and recent business activity from one place.
          </p>
        </div>
        {analytics?.generatedAt ? <div className="text-sm text-muted">Updated {new Date(analytics.generatedAt).toLocaleString()}</div> : null}
      </div>

      {error ? <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}
      {isLoading ? <div className="text-sm text-muted">Loading analytics...</div> : null}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Total Customers" value={summary.totalCustomers ?? 0} />
        <StatCard label="Total Items" value={summary.totalItems ?? 0} />
        <StatCard label="Total Transactions" value={summary.totalTransactions ?? 0} />
        <StatCard label="Total Orders" value={summary.totalOrders ?? 0} />
        <StatCard label="Quote Requests" value={summary.totalQuotes ?? 0} />
        <StatCard label="Booking Requests" value={summary.totalBookings ?? 0} />
        <StatCard label="Inquiries" value={summary.totalInquiries ?? 0} />
        <StatCard label="Today Orders" value={summary.todayOrders ?? 0} />
        <StatCard label="Gross Revenue" value={revenue.grossRevenue ?? 0} helper="Non-cancelled orders" />
        <StatCard label="Avg Order Value" value={revenue.averageOrderValue ?? 0} />
        <StatCard label="Marketplace Orders" value={summary.marketplaceOrderCount ?? 0} helper="Customer portal source" />
        <StatCard label="Website Status" value={selectedTenant.websiteStatus || "n/a"} />
      </div>

      <div className="rounded-md border border-line bg-white p-5 shadow-sm">
        <div className="flex items-center justify-between border-b border-line pb-3">
          <h2 className="text-lg font-semibold text-ink">AI Summary</h2>
          <span className="text-xs uppercase tracking-wide text-muted">Generated overview</span>
        </div>
        <p className="mt-4 text-sm leading-7 text-muted">{analytics?.dashboardSummary || "No analytics summary available yet."}</p>
      </div>

      {categoryGuidance.categoryName || categoryGuidance.suggestions?.length ? (
        <div className="rounded-md border border-line bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between border-b border-line pb-3">
            <h2 className="text-lg font-semibold text-ink">Category Guidance</h2>
            <span className="text-sm text-muted">{categoryGuidance.categoryName || "General"}</span>
          </div>
          <div className="mt-4 grid gap-4 xl:grid-cols-2">
            <div>
              <div className="text-sm font-semibold text-ink">Suggested focus</div>
              <div className="mt-3 space-y-2 text-sm text-muted">
                {(categoryGuidance.suggestions || []).map((item) => (
                  <div key={item} className="rounded-md border border-line bg-surface px-3 py-2">{item}</div>
                ))}
                {!categoryGuidance.suggestions?.length ? <div>No category suggestions available yet.</div> : null}
              </div>
            </div>
            <div>
              <div className="text-sm font-semibold text-ink">Live insight status</div>
              <div className="mt-3 space-y-2 text-sm text-muted">
                {(categoryGuidance.insights || []).map((item) => (
                  <div key={item.label} className={item.status === "attention" ? "rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-amber-900" : item.status === "healthy" ? "rounded-md border border-green-200 bg-green-50 px-3 py-2 text-green-900" : "rounded-md border border-line bg-surface px-3 py-2"}>
                    {item.label}
                  </div>
                ))}
                {!categoryGuidance.insights?.length ? <div>No category insight flags yet.</div> : null}
              </div>
            </div>
          </div>
        </div>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-2">
        <MiniBarChart title="Order Trend" points={trends} dataKey="orders" />
        <MiniBarChart title="Revenue Trend" points={trends} dataKey="revenue" colorClass="bg-emerald-500" valueFormatter={(value) => value} />
      </div>

      <div className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
        <div className="rounded-md border border-line bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between border-b border-line pb-3">
            <h2 className="text-lg font-semibold text-ink">Conversion Summary</h2>
            <span className="text-sm text-muted">Operational ratios</span>
          </div>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <InsightTile label="Marketplace Share" value={`${conversion.marketplaceShare ?? 0}%`} helper="Orders from customer portal" />
            <InsightTile label="Quote Approval" value={`${conversion.quoteApprovalRate ?? 0}%`} helper="Approved quote requests" />
            <InsightTile label="Booking Confirmation" value={`${conversion.bookingConfirmationRate ?? 0}%`} helper="Confirmed booking requests" />
            <InsightTile label="Inquiry Response" value={`${conversion.inquiryResponseRate ?? 0}%`} helper="Responded or closed inquiries" />
          </div>
        </div>

        <div className="rounded-md border border-line bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between border-b border-line pb-3">
            <h2 className="text-lg font-semibold text-ink">Top Products and Services</h2>
            <span className="text-sm text-muted">{topItems.length || 0} shown</span>
          </div>
          <div className="mt-4 space-y-3">
            {topItems.map((item) => (
              <div key={`${item.itemId}-${item.name}`} className="rounded-md border border-line p-4">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <div className="font-semibold text-ink">{item.name}</div>
                    <div className="mt-1 text-sm capitalize text-muted">{formatTransactionType(item.itemType)}</div>
                  </div>
                  <div className="text-right text-sm text-muted">
                    <div>{item.revenue}</div>
                    <div>{item.quantity} qty / {item.orders} orders</div>
                  </div>
                </div>
              </div>
            ))}
            {!topItems.length ? <div className="rounded-md border border-dashed border-line bg-surface p-4 text-sm text-muted">Not enough order data to rank items yet.</div> : null}
          </div>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <div className="rounded-md border border-line bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between border-b border-line pb-3">
            <h2 className="text-lg font-semibold text-ink">Recent Transactions</h2>
            <span className="text-sm text-muted">{analytics?.recentTransactions?.length || 0} shown</span>
          </div>
          <div className="mt-4 space-y-3">
            {(analytics?.recentTransactions || []).map((order) => (
              <div key={order.id} className="rounded-md border border-line p-4">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <div className="font-semibold text-ink">{order.transactionNumber}</div>
                    <div className="mt-1 text-sm text-muted">{new Date(order.createdAt).toLocaleString()}</div>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-semibold capitalize text-ink">{order.status}</div>
                    <div className="mt-1 text-sm text-muted">{order.pricing?.total ?? 0}</div>
                  </div>
                </div>
                <div className="mt-3 text-sm text-muted">
                  Type: <span className="font-medium capitalize text-ink">{formatTransactionType(order.transactionType)}</span>
                </div>
                <div className="mt-1 text-sm text-muted">
                  Source: <span className="font-medium text-ink">{order.source}</span>
                </div>
              </div>
            ))}
            {!analytics?.recentTransactions?.length ? <div className="rounded-md border border-dashed border-line bg-surface p-4 text-sm text-muted">No recent transactions yet.</div> : null}
          </div>
        </div>

        <div className="rounded-md border border-line bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between border-b border-line pb-3">
            <h2 className="text-lg font-semibold text-ink">Low Stock Items</h2>
            <span className="text-sm text-muted">{analytics?.lowStockItems?.length || 0} items</span>
          </div>
          <div className="mt-4 space-y-3">
            {(analytics?.lowStockItems || []).map((item) => (
              <div key={item.id} className="rounded-md border border-line p-4">
                <div className="font-semibold text-ink">{item.name}</div>
                <div className="mt-2 text-sm text-muted">Quantity: {item.stock?.quantity ?? 0}</div>
                <div className="mt-1 text-sm text-muted">Threshold: {item.stock?.lowStockThreshold ?? 0}</div>
              </div>
            ))}
            {!analytics?.lowStockItems?.length ? <div className="rounded-md border border-dashed border-line bg-surface p-4 text-sm text-muted">No low-stock items right now.</div> : null}
          </div>
        </div>
      </div>
    </section>
  );
}
