import { useEffect, useState } from "react";

import { getAdminUsers, updateAdminUser } from "../../services/adminApi.js";

export function AdminUsersPage() {
  const [users, setUsers] = useState([]);
  const [busyUser, setBusyUser] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    refreshUsers();
  }, []);

  async function refreshUsers() {
    setIsLoading(true);
    try {
      const data = await getAdminUsers();
      setUsers(data);
      setError("");
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to load users.");
    } finally {
      setIsLoading(false);
    }
  }

  async function saveUser(user, patch) {
    setBusyUser(user.id);
    setError("");
    setMessage("");
    try {
      const updated = await updateAdminUser(user.id, patch);
      setUsers((current) => current.map((item) => (item.id === user.id ? updated : item)));
      setMessage(`Updated ${updated.fullName}.`);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to update user.");
    } finally {
      setBusyUser("");
    }
  }

  return (
    <section className="space-y-6">
      <div className="border-b border-line pb-6">
        <p className="text-sm font-semibold uppercase tracking-wide text-brand">Admin Controls</p>
        <h1 className="mt-2 text-3xl font-semibold text-ink">Users</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-muted">
          Review account health, suspend access when needed, and manage platform admin permissions.
        </p>
      </div>

      {message ? <div className="rounded-md border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">{message}</div> : null}
      {error ? <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}
      {isLoading ? <div className="text-sm text-muted">Loading users...</div> : null}

      <div className="space-y-4">
        {users.map((user) => (
          <article key={user.id} className="rounded-md border border-line bg-white p-5 shadow-sm">
            <div className="grid gap-4 xl:grid-cols-[1.4fr_repeat(4,minmax(0,1fr))]">
              <div>
                <div className="text-lg font-semibold text-ink">{user.fullName}</div>
                <div className="mt-1 text-sm text-muted">{user.email}</div>
                <div className="mt-1 text-sm text-muted">{user.phone}</div>
                <div className="mt-3 text-xs uppercase tracking-wide text-muted">
                  {user.accountType} / {user.ownedTenantCount || 0} tenants
                </div>
              </div>
              <Field label="Status">
                <select className="form-input" value={user.status} disabled={busyUser === user.id} onChange={(event) => saveUser(user, { status: event.target.value })}>
                  <option value="active">active</option>
                  <option value="suspended">suspended</option>
                </select>
              </Field>
              <Field label="Role">
                <select className="form-input" value={user.globalRole} disabled={busyUser === user.id} onChange={(event) => saveUser(user, { globalRole: event.target.value })}>
                  <option value="user">user</option>
                  <option value="platform_admin">platform_admin</option>
                </select>
              </Field>
              <Field label="Email verified">
                <select
                  className="form-input"
                  value={String(Boolean(user.isEmailVerified))}
                  disabled={busyUser === user.id}
                  onChange={(event) => saveUser(user, { isEmailVerified: event.target.value === "true" })}
                >
                  <option value="true">true</option>
                  <option value="false">false</option>
                </select>
              </Field>
              <Field label="Phone verified">
                <select
                  className="form-input"
                  value={String(Boolean(user.isPhoneVerified))}
                  disabled={busyUser === user.id}
                  onChange={(event) => saveUser(user, { isPhoneVerified: event.target.value === "true" })}
                >
                  <option value="true">true</option>
                  <option value="false">false</option>
                </select>
              </Field>
              <div className="text-sm text-muted">
                <div className="font-medium text-ink">Last login</div>
                <div className="mt-1">{user.lastLoginAt ? new Date(user.lastLoginAt).toLocaleString() : "Never"}</div>
                <div className="mt-3 font-medium text-ink">Created</div>
                <div className="mt-1">{user.createdAt ? new Date(user.createdAt).toLocaleString() : "n/a"}</div>
              </div>
            </div>
          </article>
        ))}
        {!users.length && !isLoading ? <div className="rounded-md border border-dashed border-line bg-surface p-6 text-sm text-muted">No users found.</div> : null}
      </div>
    </section>
  );
}

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-ink">{label}</span>
      {children}
    </label>
  );
}
