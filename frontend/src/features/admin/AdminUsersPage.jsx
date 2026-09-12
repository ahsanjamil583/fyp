import { useEffect, useState } from "react";
import { ShieldAlert, ShieldCheck, UserRound, Users } from "lucide-react";

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
    if (
      ("globalRole" in patch || "status" in patch) &&
      !window.confirm("This changes account access. Continue only if you have verified the user and reason.")
    ) {
      return;
    }
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
      <div className="rounded-2xl border border-line bg-surface-purple p-5 shadow-card">
        <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-brand">Admin Controls</p>
        <h1 className="mt-1.5 text-2xl font-extrabold tracking-tight text-ink">Users & roles</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-muted">
          Review account health, distinguish customers from business owners, and change platform admin permissions only when necessary.
        </p>
        <div className="mt-5 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          <ShieldAlert className="mr-2 inline" size={16} />
          Role and suspension changes affect access immediately. Confirm the reason before changing them.
        </div>
      </div>

      {message ? <div className="rounded-xl border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">{message}</div> : null}
      {error ? <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}
      {isLoading ? <div className="text-sm text-muted">Loading users...</div> : null}

      <div className="space-y-4">
        {users.map((user) => (
          <article key={user.id} className="rounded-xl border border-line bg-white p-5 shadow-card">
            <div className="grid gap-4 xl:grid-cols-[1.4fr_repeat(4,minmax(0,1fr))]">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="grid h-9 w-9 place-items-center rounded-xl bg-brand-50 text-brand">
                    <UserRound size={17} />
                  </span>
                  <div className="text-base font-bold text-ink">{user.fullName}</div>
                  <RoleBadge role={user.globalRole} />
                  <StatusBadge status={user.status} />
                </div>
                <div className="mt-1 text-sm text-muted">{user.email}</div>
                <div className="mt-1 text-sm text-muted">{user.phone}</div>
                <div className="mt-3 text-[11px] font-bold uppercase tracking-[0.12em] text-subtle">
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
        {!users.length && !isLoading ? <div className="rounded-xl border border-dashed border-line bg-surface p-6 text-sm text-muted">No users found.</div> : null}
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

function RoleBadge({ role }) {
  const admin = role === "platform_admin";
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-1 text-[11px] font-bold ${admin ? "bg-brand-100 text-brand" : "bg-surface text-muted"}`}>
      {admin ? <ShieldCheck size={12} /> : <Users size={12} />}
      {admin ? "Platform admin" : "Standard user"}
    </span>
  );
}

function StatusBadge({ status }) {
  const active = status === "active";
  return (
    <span className={`rounded-full px-2 py-1 text-[11px] font-bold capitalize ${active ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"}`}>
      {status}
    </span>
  );
}
