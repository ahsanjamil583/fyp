import { useEffect, useState } from "react";

import { getCustomerNotifications, markAllCustomerNotificationsRead, markCustomerNotificationRead } from "../../services/customerPortalApi.js";

export function CustomerNotificationsPage() {
  const [notifications, setNotifications] = useState([]);
  const [meta, setMeta] = useState({});
  const [error, setError] = useState("");

  useEffect(() => {
    refreshNotifications();
  }, []);

  async function refreshNotifications() {
    setError("");
    try {
      const result = await getCustomerNotifications({ page: 1, limit: 30 });
      setNotifications(result.items);
      setMeta(result.meta);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to load notifications.");
    }
  }

  async function markRead(notificationId) {
    await markCustomerNotificationRead(notificationId);
    await refreshNotifications();
  }

  async function markAllRead() {
    await markAllCustomerNotificationsRead();
    await refreshNotifications();
  }

  return (
    <section className="space-y-6">
      <div className="flex flex-col gap-3 border-b border-line pb-6 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-brand">Notifications</p>
          <h1 className="mt-2 text-3xl font-semibold text-ink">Customer Notifications</h1>
          <p className="mt-3 text-sm text-muted">{meta.unread || 0} unread notifications.</p>
        </div>
        <button className="rounded-md border border-line px-4 py-2 text-sm font-semibold text-ink" onClick={markAllRead}>
          Mark all as read
        </button>
      </div>

      {error ? <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}

      <div className="space-y-3">
        {notifications.map((notification) => (
          <div key={notification.id} className={notification.status === "unread" ? "rounded-md border border-blue-200 bg-blue-50 p-4 shadow-sm" : "rounded-md border border-line bg-white p-4 shadow-sm"}>
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <div className="text-sm font-semibold uppercase tracking-wide text-brand">{notification.type?.replaceAll("_", " ")}</div>
                <div className="mt-1 text-lg font-semibold text-ink">{notification.title}</div>
                <div className="mt-2 text-sm leading-6 text-muted">{notification.message}</div>
                <div className="mt-2 text-xs text-muted">
                  {notification.tenant?.name ? `${notification.tenant.name} / ` : ""}{new Date(notification.createdAt).toLocaleString()}
                </div>
              </div>
              {notification.status === "unread" ? (
                <button className="rounded-md border border-line px-3 py-1.5 text-sm font-semibold text-ink" onClick={() => markRead(notification.id)}>
                  Mark as read
                </button>
              ) : (
                <div className="text-xs font-semibold uppercase tracking-wide text-muted">Read</div>
              )}
            </div>
          </div>
        ))}
        {!notifications.length ? (
          <div className="rounded-md border border-dashed border-line bg-surface p-6 text-sm text-muted">No notifications yet.</div>
        ) : null}
      </div>
    </section>
  );
}
