import {
  AlertTriangle,
  BarChart3,
  Boxes,
  CalendarClock,
  CalendarDays,
  ClipboardList,
  Coins,
  Globe,
  Lightbulb,
  MessageSquare,
  Package,
  Receipt,
  ShoppingCart,
  Sparkles,
  Store,
  TrendingUp,
  Users,
} from "lucide-react";
import { useEffect, useState } from "react";

import { Alert, Badge, Card, EmptyState, IconTile, PageHeader, SectionHeading, StatCard } from "../../components/ui/index.jsx";
import { AreaChart, ProgressRing, RankedBarList, SERIES_COLORS, formatCompact } from "../../components/ui/charts.jsx";
import { useModules } from "../../context/ModuleContext.jsx";
import { useTenant } from "../../context/TenantContext.jsx";
import { getAnalyticsSummary } from "../../services/analyticsApi.js";
import { formatTransactionType } from "../../utils/transaction.js";
import { SectionTitle } from "../../components/ui/SectionTitle.jsx";
import { getApiErrorMessage } from "../../services/apiError.js";

const STATUS_TONE = {
  paid: "green",
  completed: "green",
  confirmed: "green",
  pending: "orange",
  pending_verification: "orange",
  cancelled: "red",
  rejected: "red",
};

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
        setError(getApiErrorMessage(requestError, "Unable to load analytics."));
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
      <EmptyState
        icon={BarChart3}
        title="No business selected"
        description="Create or select a business first — analytics are reported per business."
        actionLabel="Create Business"
        actionTo="/dashboard/business"
      />
    );
  }

  if (!analyticsEnabled) {
    return (
      <EmptyState
        icon={BarChart3}
        title={`Enable analytics for ${selectedTenant.name}`}
        description="Dashboards, trends and conversion reporting unlock once the analytics module is enabled for this business."
        actionLabel="Manage Modules"
        actionTo="/dashboard/modules"
      />
    );
  }

  const summary = analytics?.summary || {};
  const revenue = analytics?.revenue || {};
  const trends = analytics?.trends || [];
  const topItems = analytics?.topItems || [];
  const conversion = analytics?.conversion || {};
  const categoryGuidance = analytics?.categoryGuidance || {};
  const recentTransactions = analytics?.recentTransactions || [];
  const lowStockItems = analytics?.lowStockItems || [];

  const totalRequests =
    (summary.totalQuotes ?? 0) + (summary.totalBookings ?? 0) + (summary.totalInquiries ?? 0);

  return (
    <section className="space-y-6">
      <PageHeader
        icon={BarChart3}
        eyebrow="Analytics"
        title={selectedTenant.name}
        description="Monitor transactions, revenue, inventory pressure and recent business activity from one place."
        actions={
          analytics?.generatedAt ? (
            <Badge tone="slate" icon={CalendarClock}>
              Updated {new Date(analytics.generatedAt).toLocaleString()}
            </Badge>
          ) : null
        }
      />

      <Alert tone="red">{error}</Alert>
      {isLoading ? <div className="text-sm text-muted">Loading analytics...</div> : null}

      {/* ---------------------------------------------------------- headline -- */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Gross Revenue" value={formatCompact(revenue.grossRevenue)} hint="Non-cancelled orders" icon={Coins} tone="green" />
        <StatCard label="Avg Order Value" value={formatCompact(revenue.averageOrderValue)} icon={TrendingUp} tone="violet" />
        <StatCard label="Total Orders" value={summary.totalOrders ?? 0} icon={ShoppingCart} tone="purple" />
        <StatCard label="Today Orders" value={summary.todayOrders ?? 0} icon={CalendarDays} tone="orange" />
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Customers" value={summary.totalCustomers ?? 0} icon={Users} tone="blue" />
        <StatCard label="Items" value={summary.totalItems ?? 0} icon={Boxes} tone="violet" />
        <StatCard label="Transactions" value={summary.totalTransactions ?? 0} icon={Receipt} tone="purple" />
        <StatCard label="Marketplace Orders" value={summary.marketplaceOrderCount ?? 0} hint="Customer portal source" icon={Store} tone="green" />
      </div>

      {/* ------------------------------------------------------------ charts -- */}
      <div className="grid gap-6 xl:grid-cols-2">
        <Card>
          <SectionHeading icon={ShoppingCart} title="Order Trend" description="Orders placed per day" />
          <AreaChart
            data={trends}
            series={[{ key: "orders", name: "Orders", color: SERIES_COLORS.purple }]}
            height={230}
          />
        </Card>

        <Card>
          <SectionHeading icon={Coins} title="Revenue Trend" description="Revenue captured per day" />
          <AreaChart
            data={trends}
            series={[{ key: "revenue", name: "Revenue", color: SERIES_COLORS.blue }]}
            height={230}
          />
        </Card>
      </div>

      <Card>
        <SectionHeading
          icon={ClipboardList}
          title="Demand Mix"
          description="Quotes, bookings and inquiries alongside orders"
          actions={<Badge tone="violet">{totalRequests} requests total</Badge>}
        />
        <AreaChart
          data={trends}
          height={280}
          series={[
            { key: "orders", name: "Orders", color: SERIES_COLORS.purple },
            { key: "quotes", name: "Quotes", color: SERIES_COLORS.blue, area: false },
            { key: "bookings", name: "Bookings", color: SERIES_COLORS.orange, area: false },
            { key: "inquiries", name: "Inquiries", color: SERIES_COLORS.green, area: false },
          ]}
        />
      </Card>

      {/* -------------------------------------------------------- conversion -- */}
      <div className="grid gap-6 xl:grid-cols-[1fr_1fr]">
        <Card>
          <SectionHeading icon={TrendingUp} title="Conversion Summary" description="Operational ratios" />
          <div className="grid grid-cols-2 gap-6 pt-2 sm:grid-cols-4 xl:grid-cols-2 2xl:grid-cols-4">
            <ProgressRing value={conversion.marketplaceShare ?? 0} label="Marketplace" caption="Share of orders" color={SERIES_COLORS.purple} />
            <ProgressRing value={conversion.quoteApprovalRate ?? 0} label="Quotes" caption="Approved" color={SERIES_COLORS.blue} />
            <ProgressRing value={conversion.bookingConfirmationRate ?? 0} label="Bookings" caption="Confirmed" color={SERIES_COLORS.orange} />
            <ProgressRing value={conversion.inquiryResponseRate ?? 0} label="Inquiries" caption="Responded" color={SERIES_COLORS.green} />
          </div>
        </Card>

        <Card>
          <SectionHeading
            icon={Package}
            title="Top Products and Services"
            description="Ranked by revenue"
            actions={<Badge tone="slate">{topItems.length} shown</Badge>}
          />
          {topItems.length ? (
            <RankedBarList
              items={topItems.map((item) => ({
                id: `${item.itemId}-${item.name}`,
                name: item.name,
                value: item.revenue,
                caption: `${item.quantity} qty · ${item.orders} orders`,
              }))}
            />
          ) : (
            <p className="rounded-xl border border-dashed border-line bg-surface p-4 text-sm text-muted">
              Not enough order data to rank items yet.
            </p>
          )}
        </Card>
      </div>

      {/* ----------------------------------------------------------- insight -- */}
      {analytics?.dashboardSummary ? (
        <Card className="border-brand-200 bg-surface-purple">
          <div className="flex items-start gap-4">
            <IconTile icon={Sparkles} tone="purple" size={44} />
            <div className="min-w-0">
              <SectionTitle>AI Summary</SectionTitle>
              <p className="mt-1.5 text-sm leading-7 text-muted">{analytics.dashboardSummary}</p>
            </div>
          </div>
        </Card>
      ) : null}

      {categoryGuidance.categoryName || categoryGuidance.suggestions?.length ? (
        <Card>
          <SectionHeading
            icon={Lightbulb}
            title="Category Guidance"
            description="Tailored to this business category"
            actions={<Badge tone="violet">{categoryGuidance.categoryName || "General"}</Badge>}
          />
          <div className="grid gap-6 xl:grid-cols-2">
            <div>
              <div className="text-xs font-bold uppercase tracking-[0.12em] text-subtle">Suggested focus</div>
              <ul className="mt-3 space-y-2">
                {(categoryGuidance.suggestions || []).map((item) => (
                  <li key={item} className="flex items-start gap-2.5 rounded-xl border border-line bg-white px-3.5 py-2.5 text-sm text-muted">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-brand" />
                    {item}
                  </li>
                ))}
                {!categoryGuidance.suggestions?.length ? (
                  <li className="text-sm text-muted">No category suggestions available yet.</li>
                ) : null}
              </ul>
            </div>
            <div>
              <div className="text-xs font-bold uppercase tracking-[0.12em] text-subtle">Live insight status</div>
              <ul className="mt-3 space-y-2">
                {(categoryGuidance.insights || []).map((item) => {
                  const tone =
                    item.status === "attention"
                      ? "border-orange-200 bg-orange-50 text-orange-700"
                      : item.status === "healthy"
                        ? "border-green-200 bg-green-50 text-green-700"
                        : "border-line bg-white text-muted";
                  return (
                    <li key={item.label} className={`flex items-center gap-2.5 rounded-xl border px-3.5 py-2.5 text-sm font-semibold ${tone}`}>
                      {item.status === "attention" ? <AlertTriangle size={15} className="shrink-0" /> : null}
                      {item.label}
                    </li>
                  );
                })}
                {!categoryGuidance.insights?.length ? (
                  <li className="text-sm text-muted">No category insight flags yet.</li>
                ) : null}
              </ul>
            </div>
          </div>
        </Card>
      ) : null}

      {/* ------------------------------------------------------------ tables -- */}
      <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <Card>
          <SectionHeading
            icon={Receipt}
            title="Recent Transactions"
            description="Latest activity across this business"
            actions={<Badge tone="slate">{recentTransactions.length} shown</Badge>}
          />
          <div className="divide-y divide-line-soft">
            {recentTransactions.map((order) => (
              <div key={order.id} className="flex items-center gap-4 py-3 first:pt-0">
                <IconTile icon={ShoppingCart} tone="violet" size={38} />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-bold text-ink">{order.transactionNumber}</div>
                  <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[11px] font-medium text-subtle">
                    <span>{new Date(order.createdAt).toLocaleString()}</span>
                    <span>·</span>
                    <span className="capitalize">{formatTransactionType(order.transactionType)}</span>
                    <span>·</span>
                    <span>{order.source}</span>
                  </div>
                </div>
                <div className="shrink-0 text-right">
                  <div className="text-sm font-extrabold text-ink">{formatCompact(order.pricing?.total ?? 0)}</div>
                  <Badge tone={STATUS_TONE[order.status] || "slate"} className="mt-1 capitalize">
                    {String(order.status || "").replaceAll("_", " ")}
                  </Badge>
                </div>
              </div>
            ))}
            {!recentTransactions.length ? (
              <p className="rounded-xl border border-dashed border-line bg-surface p-4 text-sm text-muted">
                No recent transactions yet.
              </p>
            ) : null}
          </div>
        </Card>

        <Card>
          <SectionHeading
            icon={AlertTriangle}
            title="Low Stock Items"
            description="Below their reorder threshold"
            actions={<Badge tone={lowStockItems.length ? "orange" : "green"}>{lowStockItems.length} items</Badge>}
          />
          <div className="space-y-2.5">
            {lowStockItems.map((item) => {
              const quantity = item.stock?.quantity ?? 0;
              const threshold = item.stock?.lowStockThreshold ?? 0;
              const pct = threshold > 0 ? Math.min(100, Math.round((quantity / threshold) * 100)) : 0;
              return (
                <div key={item.id} className="rounded-xl border border-orange-200 bg-orange-50 p-3.5">
                  <div className="flex items-center justify-between gap-3">
                    <span className="truncate text-sm font-bold text-ink">{item.name}</span>
                    <span className="shrink-0 text-xs font-extrabold text-orange-600">
                      {quantity} / {threshold}
                    </span>
                  </div>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-orange-100">
                    <div className="h-full rounded-full bg-orange-500 transition-all" style={{ width: `${Math.max(4, pct)}%` }} />
                  </div>
                </div>
              );
            })}
            {!lowStockItems.length ? (
              <div className="flex items-center gap-2.5 rounded-xl border border-green-200 bg-green-50 px-3.5 py-3 text-sm font-semibold text-green-700">
                <Package size={16} />
                Every item is above its reorder threshold.
              </div>
            ) : null}
          </div>
        </Card>
      </div>

      {/* Website status sits apart from the metrics: it is a state, not a measurement. */}
      <Card className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <IconTile icon={Globe} tone="blue" size={40} />
          <div>
            <div className="text-sm font-bold text-ink">Website Status</div>
            <div className="text-xs text-subtle">Public storefront visibility</div>
          </div>
        </div>
        <Badge tone={selectedTenant.websiteStatus === "published" ? "green" : "orange"} className="capitalize">
          {selectedTenant.websiteStatus || "not set"}
        </Badge>
      </Card>

      {!trends.length && !recentTransactions.length ? (
        <div className="flex items-center gap-2.5 rounded-xl border border-dashed border-line bg-surface px-4 py-3 text-sm text-muted">
          <MessageSquare size={16} />
          Charts fill in as orders, quotes and bookings come through.
        </div>
      ) : null}
    </section>
  );
}
