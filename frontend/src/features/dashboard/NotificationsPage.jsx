import { useEffect, useState } from "react";

import { useModules } from "../../context/ModuleContext.jsx";
import { useTenant } from "../../context/TenantContext.jsx";
import {
  getBusinessNotifications,
  markAllBusinessNotificationsRead,
  markBusinessNotificationRead,
  refreshBusinessStockAlerts,
} from "../../services/notificationApi.js";

export function NotificationsPage() {
  const { selectedTenant, isLoadingTenants } = useTenant();
  const { enabledModules } = useModules();
  const [notifications, setNotifications] = useState([]);
  const [meta, setMeta] = useState({});
  const [typeFilter, setTypeFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isRefreshingStock, setIsRefreshingStock] = useState(false);

  const notificationsEnabled = enabledModules.includes("notifications");

  useEffect(() => {
    if (!selectedTenant?.id || !notificationsEnabled) {
      setNotifications([]);
      setMeta({});
      return;
    }
    refreshNotifications();
  }, [selectedTenant?.id, notificationsEnabled, typeFilter, statusFilter]);

  async function refreshNotifications() {
    if (!selectedTenant?.id) return;
    setIsLoading(true);
    setError("");
    try {
      const result = await getBusinessNotifications(selectedTenant.id, {
        page: 1,
        limit: 30,
        type: typeFilter || undefined,
        status: statusFilter || undefined,
      });
      setNotifications(result.items || []);
      setMeta(result.meta || {});
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to load business notifications.");
    } finally {
      setIsLoading(false);
    }
  }

  async function handleMarkRead(notificationId) {
    if (!selectedTenant?.id) return;
    setMessage("");
    setError("");
    try {
      await markBusinessNotificationRead(selectedTenant.id, notificationId);
      await refreshNotifications();
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to update notification.");
    }
  }

  async function handleMarkAllRead() {
    if (!selectedTenant?.id) return;
    setMessage("");
    setError("");
    try {
      const result = await markAllBusinessNotificationsRead(selectedTenant.id);
      setMessage(`${result.updatedCount || 0} notifications marked as read.`);
      await refreshNotifications();
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to mark all notifications as read.");
    }
  }

  async function handleRefreshStockAlerts() {
    if (!selectedTenant?.id) return;
    setIsRefreshingStock(true);
    setMessage("");
    setError("");
    try {
      const result = await refreshBusinessStockAlerts(selectedTenant.id);
      setMessage(`Stock alerts refreshed. ${result.activeLowStockAlerts || 0} active, ${result.clearedAlerts || 0} cleared.`);
      await refreshNotifications();
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to refresh stock alerts.");
    } finally {
      setIsRefreshingStock(false);
    }
  }

  if (isLoadingTenants) {
    return <section className="text-sm text-muted">Loading notifications workspace...</section>;
  }

  if (!selectedTenant) {
    return <section className="text-sm text-muted">Select a business first to review notifications.</section>;
  }

  if (!notificationsEnabled) {
    return <section className="text-sm text-muted">Enable the notifications module to review business alerts.</section>;
  }

  const filters = meta.filters || {};

  return (
    <section className="space-y-6">
      <div className="flex flex-col gap-3 border-b border-line pb-6 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-brand">Notifications</p>
          <h1 className="mt-2 text-3xl font-semibold text-ink">Business Alerts</h1>
          <p className="mt-3 text-sm text-muted">{meta.unread || 0} unread alerts for {selectedTenant.name}.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button className="rounded-md border border-line px-4 py-2 text-sm font-semibold text-ink" onClick={handleMarkAllRead} type="button">
            Mark all as read
          </button>
          <button
            className="rounded-md bg-brand px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
            disabled={isRefreshingStock}
            onClick={handleRefreshStockAlerts}
            type="button"
          >
            {isRefreshingStock ? "Refreshing..." : "Refresh stock alerts"}
          </button>
        </div>
      </div>

      {message ? <div className="rounded-md border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">{message}</div> : null}
      {error ? <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}

      <div className="grid gap-3 rounded-md border border-line bg-white p-5 shadow-sm md:grid-cols-3">
        <select className="form-input" value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}>
          <option value="">All alert types</option>
          {(filters.types || []).map((value) => (
            <option key={value} value={value}>{value.replaceAll("_", " ")}</option>
          ))}
        </select>
        <select className="form-input" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
          <option value="">All statuses</option>
          {(filters.statuses || []).map((value) => (
            <option key={value} value={value}>{value}</option>
          ))}
        </select>
        <div className="rounded-md bg-surface px-4 py-3 text-sm text-muted">
          Hook-ready alerts include `webhook`, `WhatsApp`, and `SMS` preview payloads.
        </div>
      </div>

      {isLoading ? <div className="text-sm text-muted">Loading business alerts...</div> : null}

      <div className="space-y-3">
        {notifications.map((notification) => (
          <div key={notification.id} className={notification.status === "unread" ? "rounded-md border border-amber-200 bg-amber-50 p-4 shadow-sm" : "rounded-md border border-line bg-white p-4 shadow-sm"}>
            <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
              <div className="space-y-2">
                <div className="flex flex-wrap items-center gap-2 text-xs uppercase tracking-wide text-muted">
                  <span className="rounded-full bg-white px-2 py-1 font-semibold text-ink">{notification.type?.replaceAll("_", " ")}</span>
                  <span className="rounded-full bg-white px-2 py-1">{notification.priority}</span>
                  <span>{new Date(notification.createdAt).toLocaleString()}</span>
                </div>
                <div className="text-lg font-semibold text-ink">{notification.title}</div>
                <div className="text-sm leading-6 text-muted">{notification.message}</div>
                {notification.metadata?.transactionNumber ? (
                  <div className="text-xs text-muted">Transaction: {notification.metadata.transactionNumber}</div>
                ) : null}
                {notification.metadata?.itemName ? (
                  <div className="text-xs text-muted">Item: {notification.metadata.itemName}</div>
                ) : null}
              </div>
              <div className="min-w-0 xl:w-[360px]">
                {notification.status === "unread" ? (
                  <button className="mb-3 rounded-md border border-line px-3 py-1.5 text-sm font-semibold text-ink" onClick={() => handleMarkRead(notification.id)} type="button">
                    Mark as read
                  </button>
                ) : (
                  <div className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted">Read</div>
                )}
                <div className="rounded-md border border-line bg-surface p-3 text-xs text-muted">
                  <div className="font-semibold text-ink">Hook Preview</div>
                  <div className="mt-2">Webhook event: {notification.hookPreview?.webhookEvent?.event || "n/a"}</div>
                  <div>WhatsApp template: {notification.hookPreview?.whatsapp?.template || "n/a"}</div>
                  <div>SMS template: {notification.hookPreview?.sms?.template || "n/a"}</div>
                </div>
              </div>
            </div>
          </div>
        ))}
        {!notifications.length && !isLoading ? (
          <div className="rounded-md border border-dashed border-line bg-surface p-6 text-sm text-muted">No business alerts matched your filters.</div>
        ) : null}
      </div>
    </section>
  );
}
