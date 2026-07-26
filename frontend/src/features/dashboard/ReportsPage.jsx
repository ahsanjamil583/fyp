import { useEffect, useState } from "react";

import { useModules } from "../../context/ModuleContext.jsx";
import { useTenant } from "../../context/TenantContext.jsx";
import {
  deliverDailySummaryReport,
  generateDailySummaryReport,
  getDailySummaryReport,
  getReportDeliveryLogs,
  getReportDeliverySettings,
  updateReportDeliverySettings,
} from "../../services/reportApi.js";

function todayDateValue() {
  return new Date().toISOString().slice(0, 10);
}

const defaultDeliveryForm = {
  enabled: true,
  whatsappEnabled: true,
  smsEnabled: false,
  deliveryTime: "21:00",
  timezone: "Asia/Karachi",
  whatsappRecipient: "",
  smsRecipient: "",
  languageMode: "auto",
  includeLowStock: true,
  includeTopItems: true,
  includeRecentOrders: true,
};

export function ReportsPage() {
  const { selectedTenant, isLoadingTenants } = useTenant();
  const { enabledModules } = useModules();
  const [summaryDate, setSummaryDate] = useState(todayDateValue());
  const [report, setReport] = useState(null);
  const [deliveryForm, setDeliveryForm] = useState(defaultDeliveryForm);
  const [deliveryLogs, setDeliveryLogs] = useState([]);
  const [lastDelivery, setLastDelivery] = useState(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isSavingDelivery, setIsSavingDelivery] = useState(false);
  const [isDelivering, setIsDelivering] = useState(false);

  const reportsEnabled = enabledModules.includes("reports");

  useEffect(() => {
    if (!selectedTenant?.id || !reportsEnabled) {
      setReport(null);
      return;
    }
    loadReport(summaryDate);
    loadDeliveryWorkspace();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedTenant?.id, reportsEnabled, summaryDate]);

  async function loadReport(dateValue) {
    if (!selectedTenant?.id) return;
    setIsLoading(true);
    setError("");
    try {
      const data = await getDailySummaryReport(selectedTenant.id, { date: dateValue });
      setReport(data);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to load the daily summary.");
    } finally {
      setIsLoading(false);
    }
  }

  async function loadDeliveryWorkspace() {
    if (!selectedTenant?.id) return;
    try {
      const [settingsData, logsData] = await Promise.all([
        getReportDeliverySettings(selectedTenant.id),
        getReportDeliveryLogs(selectedTenant.id, { limit: 10 }),
      ]);
      setDeliveryForm({ ...defaultDeliveryForm, ...(settingsData.settings || {}) });
      setDeliveryLogs(logsData.items || []);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to load daily report delivery settings.");
    }
  }

  async function handleGenerate() {
    if (!selectedTenant?.id) return;
    setIsGenerating(true);
    setError("");
    setMessage("");
    try {
      const data = await generateDailySummaryReport(selectedTenant.id, { date: summaryDate });
      setReport(data);
      setMessage(`Daily summary generated for ${summaryDate}.`);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to generate the daily summary.");
    } finally {
      setIsGenerating(false);
    }
  }

  function updateDeliveryField(field, value) {
    setDeliveryForm((current) => ({ ...current, [field]: value }));
  }

  async function handleSaveDelivery(event) {
    event.preventDefault();
    if (!selectedTenant?.id) return;
    setIsSavingDelivery(true);
    setError("");
    setMessage("");
    try {
      const data = await updateReportDeliverySettings(selectedTenant.id, deliveryForm);
      setDeliveryForm({ ...defaultDeliveryForm, ...(data.settings || {}) });
      setMessage("Daily report delivery settings saved.");
      await loadDeliveryWorkspace();
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to save delivery settings.");
    } finally {
      setIsSavingDelivery(false);
    }
  }

  async function handleDeliverNow(dryRun = false) {
    if (!selectedTenant?.id) return;
    setIsDelivering(true);
    setError("");
    setMessage("");
    setLastDelivery(null);
    try {
      const channels = [];
      if (deliveryForm.whatsappEnabled) channels.push("whatsapp");
      if (deliveryForm.smsEnabled) channels.push("sms");
      const data = await deliverDailySummaryReport(selectedTenant.id, { summaryDate, channels, dryRun });
      setLastDelivery(data);
      setReport(data.summary || report);
      setMessage(dryRun ? "Dry-run delivery logged successfully." : `Daily report delivery status: ${data.deliveryStatus}.`);
      await loadDeliveryWorkspace();
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to deliver the daily summary.");
    } finally {
      setIsDelivering(false);
    }
  }

  if (isLoadingTenants) {
    return <section className="text-sm text-muted">Loading reports workspace...</section>;
  }

  if (!selectedTenant) {
    return <section className="text-sm text-muted">Select a business first to view reports.</section>;
  }

  if (!reportsEnabled) {
    return <section className="text-sm text-muted">Enable the reports module to generate daily summaries.</section>;
  }

  const metrics = report?.metrics || {};

  return (
    <section className="space-y-6">
      <div className="flex flex-col gap-3 border-b border-line pb-6 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-brand">Reports</p>
          <h1 className="mt-2 text-3xl font-semibold text-ink">Daily Business Summary</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-muted">
            Generate a business-owner summary and deliver it through WhatsApp/SMS. This completes the proposal flow where the owner receives daily operational insights automatically.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <input className="form-input" type="date" value={summaryDate} onChange={(event) => setSummaryDate(event.target.value)} />
          <button className="rounded-md bg-brand px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60" disabled={isGenerating} onClick={handleGenerate} type="button">
            {isGenerating ? "Generating..." : "Generate Summary"}
          </button>
        </div>
      </div>

      {message ? <div className="rounded-md border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">{message}</div> : null}
      {error ? <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}
      {isLoading ? <div className="text-sm text-muted">Loading daily summary...</div> : null}

      {report ? (
        <>
          <div className="rounded-md border border-line bg-white p-5 shadow-sm">
            <div className="text-sm font-semibold uppercase tracking-wide text-brand">{report.summaryDate}</div>
            <h2 className="mt-2 text-2xl font-semibold text-ink">{report.headline}</h2>
            <p className="mt-3 text-sm leading-7 text-muted">{report.analyticsSummary || "No additional analytics summary yet."}</p>
          </div>

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <MetricCard label="New Transactions" value={metrics.newTransactions || 0} />
            <MetricCard label="New Orders" value={metrics.newOrders || 0} />
            <MetricCard label="Unread Alerts" value={metrics.unreadAlerts || 0} />
            <MetricCard label="Low Stock Alerts" value={metrics.lowStockAlerts || 0} />
            <MetricCard label="Quotes" value={metrics.newQuotes || 0} />
            <MetricCard label="Bookings" value={metrics.newBookings || 0} />
            <MetricCard label="Gross Revenue" value={metrics.grossRevenue || 0} />
            <MetricCard label="Avg Order Value" value={metrics.averageOrderValue || 0} />
          </div>

          <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
            <div className="space-y-6">
              <Panel title="Top Items" emptyMessage="No ranked items yet.">
                {(report.topItems || []).map((item) => (
                  <div key={item.itemId || item.name} className="rounded-md border border-line px-3 py-2 text-sm">
                    <div className="font-semibold text-ink">{item.name}</div>
                    <div className="mt-1 text-muted">Orders: {item.orders} / Quantity: {item.quantity} / Revenue: {item.revenue}</div>
                  </div>
                ))}
              </Panel>

              <Panel title="Recent Transactions" emptyMessage="No recent transactions.">
                {(report.recentTransactions || []).map((item) => (
                  <div key={item.id} className="rounded-md border border-line px-3 py-2 text-sm">
                    <div className="font-semibold text-ink">{item.transactionNumber}</div>
                    <div className="mt-1 text-muted">{item.transactionType} / {item.status} / {item.source}</div>
                  </div>
                ))}
              </Panel>
            </div>

            <div className="space-y-6">
              <Panel title="Low Stock Items" emptyMessage="No low-stock items right now.">
                {(report.lowStockItems || []).map((item) => (
                  <div key={item.id} className="rounded-md border border-line px-3 py-2 text-sm">
                    <div className="font-semibold text-ink">{item.name}</div>
                    <div className="mt-1 text-muted">Quantity: {item.stock?.quantity ?? 0} / Threshold: {item.stock?.lowStockThreshold ?? 0}</div>
                  </div>
                ))}
              </Panel>

              <div className="rounded-md border border-line bg-white p-5 shadow-sm">
                <div className="text-sm font-semibold text-ink">Hook Preview</div>
                <div className="mt-3 space-y-2 text-sm text-muted">
                  <div>Webhook event: {report.hookPreview?.webhookEvent?.event || "n/a"}</div>
                  <div>WhatsApp template: {report.hookPreview?.whatsapp?.template || "n/a"}</div>
                  <div>SMS template: {report.hookPreview?.sms?.template || "n/a"}</div>
                </div>
                <div className="mt-4 rounded-md bg-surface p-3 text-xs text-muted">
                  {report.generatedAt ? `Generated at ${new Date(report.generatedAt).toLocaleString()}` : "Generated summary ready."}
                </div>
              </div>
            </div>
          </div>
        </>
      ) : null}

      <div className="rounded-md border border-line bg-white p-5 shadow-sm">
        <div className="flex flex-col gap-2 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="text-sm font-semibold uppercase tracking-wide text-brand">Phase 26</p>
            <h2 className="mt-1 text-2xl font-semibold text-ink">Daily WhatsApp/SMS Delivery</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-muted">Save the owner recipient numbers, choose channels, and send the daily report now. The mock providers log delivery for FYP demos; real provider credentials can be configured later.</p>
          </div>
          <div className="flex gap-2">
            <button type="button" disabled={isDelivering} onClick={() => handleDeliverNow(true)} className="rounded-md border border-line px-3 py-2 text-sm font-semibold text-ink disabled:opacity-60">Dry Run</button>
            <button type="button" disabled={isDelivering} onClick={() => handleDeliverNow(false)} className="rounded-md bg-brand px-3 py-2 text-sm font-semibold text-white disabled:opacity-60">{isDelivering ? "Delivering..." : "Deliver Now"}</button>
          </div>
        </div>

        <form onSubmit={handleSaveDelivery} className="mt-5 grid gap-4 lg:grid-cols-3">
          <label className="text-sm font-medium text-ink">Delivery time
            <input className="mt-1 w-full rounded-md border border-line px-3 py-2 text-sm" type="time" value={deliveryForm.deliveryTime || "21:00"} onChange={(event) => updateDeliveryField("deliveryTime", event.target.value)} />
          </label>
          <label className="text-sm font-medium text-ink">Timezone
            <input className="mt-1 w-full rounded-md border border-line px-3 py-2 text-sm" value={deliveryForm.timezone || "Asia/Karachi"} onChange={(event) => updateDeliveryField("timezone", event.target.value)} />
          </label>
          <label className="text-sm font-medium text-ink">Language
            <select className="mt-1 w-full rounded-md border border-line px-3 py-2 text-sm" value={deliveryForm.languageMode || "auto"} onChange={(event) => updateDeliveryField("languageMode", event.target.value)}>
              <option value="auto">Auto</option>
              <option value="english">English</option>
              <option value="roman_urdu">Roman Urdu</option>
              <option value="mixed">Mixed</option>
            </select>
          </label>
          <label className="text-sm font-medium text-ink">WhatsApp recipient
            <input className="mt-1 w-full rounded-md border border-line px-3 py-2 text-sm" value={deliveryForm.whatsappRecipient || ""} onChange={(event) => updateDeliveryField("whatsappRecipient", event.target.value)} placeholder="+923001234567" />
          </label>
          <label className="text-sm font-medium text-ink">SMS recipient
            <input className="mt-1 w-full rounded-md border border-line px-3 py-2 text-sm" value={deliveryForm.smsRecipient || ""} onChange={(event) => updateDeliveryField("smsRecipient", event.target.value)} placeholder="+923001234567" />
          </label>
          <div className="flex flex-wrap items-end gap-4 text-sm text-ink">
            <label className="flex items-center gap-2"><input type="checkbox" checked={deliveryForm.enabled !== false} onChange={(event) => updateDeliveryField("enabled", event.target.checked)} /> Enabled</label>
            <label className="flex items-center gap-2"><input type="checkbox" checked={deliveryForm.whatsappEnabled !== false} onChange={(event) => updateDeliveryField("whatsappEnabled", event.target.checked)} /> WhatsApp</label>
            <label className="flex items-center gap-2"><input type="checkbox" checked={Boolean(deliveryForm.smsEnabled)} onChange={(event) => updateDeliveryField("smsEnabled", event.target.checked)} /> SMS</label>
          </div>
          <div className="flex flex-wrap gap-4 text-sm text-ink lg:col-span-3">
            <label className="flex items-center gap-2"><input type="checkbox" checked={deliveryForm.includeLowStock !== false} onChange={(event) => updateDeliveryField("includeLowStock", event.target.checked)} /> Include low stock</label>
            <label className="flex items-center gap-2"><input type="checkbox" checked={deliveryForm.includeTopItems !== false} onChange={(event) => updateDeliveryField("includeTopItems", event.target.checked)} /> Include top items</label>
            <label className="flex items-center gap-2"><input type="checkbox" checked={deliveryForm.includeRecentOrders !== false} onChange={(event) => updateDeliveryField("includeRecentOrders", event.target.checked)} /> Include recent orders</label>
          </div>
          <div className="lg:col-span-3">
            <button type="submit" disabled={isSavingDelivery} className="rounded-md border border-line px-4 py-2 text-sm font-semibold text-ink disabled:opacity-60">{isSavingDelivery ? "Saving..." : "Save delivery settings"}</button>
          </div>
        </form>

        {lastDelivery ? (
          <div className="mt-5 rounded-md bg-surface p-3 text-sm text-muted">Last delivery status: <span className="font-semibold text-ink">{lastDelivery.deliveryStatus}</span></div>
        ) : null}

        <div className="mt-5">
          <h3 className="text-sm font-semibold text-ink">Recent delivery logs</h3>
          <div className="mt-3 space-y-2">
            {deliveryLogs.length ? deliveryLogs.map((log) => (
              <div key={log.id} className="rounded-md border border-line px-3 py-2 text-sm">
                <div className="font-semibold text-ink">{log.channel} / {log.deliveryStatus} / {log.summaryDate}</div>
                <div className="mt-1 text-muted">To: {log.recipient || "n/a"} / Provider: {log.provider || "mock"}</div>
                {log.error ? <div className="mt-1 text-red-700">{log.error}</div> : null}
              </div>
            )) : <div className="rounded-md border border-dashed border-line bg-surface p-4 text-sm text-muted">No delivery logs yet.</div>}
          </div>
        </div>
      </div>
    </section>
  );
}

function MetricCard({ label, value }) {
  return (
    <div className="rounded-md border border-line bg-white p-4 shadow-sm">
      <div className="text-sm text-muted">{label}</div>
      <div className="mt-2 text-2xl font-semibold text-ink">{value}</div>
    </div>
  );
}

function Panel({ title, emptyMessage, children }) {
  const items = Array.isArray(children) ? children.filter(Boolean) : [];

  return (
    <div className="rounded-md border border-line bg-white p-5 shadow-sm">
      <div className="text-sm font-semibold text-ink">{title}</div>
      <div className="mt-3 space-y-2">
        {items.length ? items : <div className="rounded-md border border-dashed border-line bg-surface p-4 text-sm text-muted">{emptyMessage}</div>}
      </div>
    </div>
  );
}
