import { KeyRound, Power, ShieldCheck, UserPlus, Users } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { Alert, Card, EmptyState, PageHeader, StatCard } from "../../components/ui/index.jsx";
import { useModules } from "../../context/ModuleContext.jsx";
import { useTenant } from "../../context/TenantContext.jsx";
import { getApiErrorMessage } from "../../services/apiError.js";
import {
  createTenantCashier,
  getTenantCashiers,
  removeTenantCashier,
  resetTenantCashierPassword,
  setTenantCashierStatus,
  updateTenantCashier,
} from "../../services/cashierApi.js";
import { enableTenantModule } from "../../services/moduleApi.js";

const EMPTY_FORM = {
  fullName: "",
  email: "",
  phone: "",
  employeeCode: "",
  password: "",
  canViewAllCashierOrders: false,
  canAddCustomItems: true,
  canApplyDiscount: true,
};

const FILTERS = [
  { value: "", label: "All" },
  { value: "active", label: "Active" },
  { value: "inactive", label: "Inactive" },
];

function formatMoney(value) {
  return `PKR ${Number(value || 0).toLocaleString("en-PK", { maximumFractionDigits: 0 })}`;
}

function formatDate(value) {
  if (!value) return "Never";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "Never" : parsed.toLocaleString("en-PK", { dateStyle: "medium", timeStyle: "short" });
}

export function CashiersPage() {
  const { selectedTenant } = useTenant();
  const { hasModule, refreshTenantModules, isLoadingModules } = useModules();
  const [cashiers, setCashiers] = useState([]);
  const [summary, setSummary] = useState({});
  const [filter, setFilter] = useState("");
  const [form, setForm] = useState(EMPTY_FORM);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState("");
  const [editDraft, setEditDraft] = useState({});
  const [resetTarget, setResetTarget] = useState("");
  const [resetPassword, setResetPassword] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  const moduleEnabled = hasModule("cashier");

  const load = useCallback(async () => {
    if (!selectedTenant?.id || !moduleEnabled) return;
    setIsLoading(true);
    setError("");
    try {
      const activeOnly = filter === "active" ? true : filter === "inactive" ? false : undefined;
      const result = await getTenantCashiers(selectedTenant.id, activeOnly === undefined ? {} : { activeOnly });
      setCashiers(result.items);
      setSummary(result.meta?.summary || {});
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Unable to load cashiers."));
    } finally {
      setIsLoading(false);
    }
  }, [selectedTenant?.id, filter, moduleEnabled]);

  useEffect(() => {
    load();
  }, [load]);

  async function enableModule() {
    setError("");
    try {
      await enableTenantModule(selectedTenant.id, "cashier");
      await refreshTenantModules(selectedTenant.id);
      setMessage("Cashier module enabled.");
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Unable to enable the cashier module."));
    }
  }

  async function submitNewCashier(event) {
    event.preventDefault();
    setIsSaving(true);
    setError("");
    setMessage("");
    try {
      const created = await createTenantCashier(selectedTenant.id, {
        fullName: form.fullName,
        email: form.email,
        phone: form.phone,
        employeeCode: form.employeeCode,
        password: form.password,
        permissions: {
          canViewAllCashierOrders: form.canViewAllCashierOrders,
          canAddCustomItems: form.canAddCustomItems,
          canApplyDiscount: form.canApplyDiscount,
        },
      });
      setMessage(
        `${created.cashier.fullName} can now sign in at the business login with ${created.cashier.email || created.cashier.phone}. Share the temporary password you just set.`,
      );
      setForm(EMPTY_FORM);
      setShowForm(false);
      await load();
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Unable to create this cashier."));
    } finally {
      setIsSaving(false);
    }
  }

  async function saveEdit(cashierId) {
    setIsSaving(true);
    setError("");
    try {
      await updateTenantCashier(selectedTenant.id, cashierId, {
        fullName: editDraft.fullName,
        phone: editDraft.phone,
        email: editDraft.email,
        employeeCode: editDraft.employeeCode,
        permissions: {
          canViewAllCashierOrders: Boolean(editDraft.canViewAllCashierOrders),
          canAddCustomItems: Boolean(editDraft.canAddCustomItems),
          canApplyDiscount: Boolean(editDraft.canApplyDiscount),
        },
      });
      setEditingId("");
      setMessage("Cashier updated.");
      await load();
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Unable to update this cashier."));
    } finally {
      setIsSaving(false);
    }
  }

  async function toggleStatus(cashier) {
    setError("");
    try {
      await setTenantCashierStatus(selectedTenant.id, cashier.id, !cashier.isActive);
      setMessage(
        cashier.isActive
          ? `${cashier.fullName} is deactivated and signed out of any open session.`
          : `${cashier.fullName} can sign in again.`,
      );
      await load();
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Unable to change this cashier's status."));
    }
  }

  async function submitPasswordReset(cashierId) {
    setIsSaving(true);
    setError("");
    try {
      await resetTenantCashierPassword(selectedTenant.id, cashierId, { password: resetPassword, mustChangeOnNextLogin: true });
      setResetTarget("");
      setResetPassword("");
      setMessage("Password reset. The cashier is signed out and must set a new password at their next login.");
      await load();
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Unable to reset the password."));
    } finally {
      setIsSaving(false);
    }
  }

  async function removeAccess(cashier) {
    if (!window.confirm(`Remove ${cashier.fullName}'s login? Their past orders and receipts are kept.`)) return;
    setError("");
    try {
      await removeTenantCashier(selectedTenant.id, cashier.id);
      setMessage(`${cashier.fullName} can no longer sign in.`);
      await load();
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Unable to remove this cashier."));
    }
  }

  if (!selectedTenant) {
    return (
      <section className="space-y-4">
        <h1 className="text-2xl font-extrabold tracking-tight text-ink">Cashiers</h1>
        <p className="text-sm text-muted">Create a business before adding cashiers.</p>
        <Link className="ui-btn-primary" to="/dashboard/business">
          Create business
        </Link>
      </section>
    );
  }

  if (isLoadingModules) {
    return <div className="py-8 text-sm text-muted">Loading module settings...</div>;
  }

  if (!moduleEnabled) {
    return (
      <section className="space-y-5">
        <PageHeader
          eyebrow="Counter"
          title="Cashiers"
          icon={Users}
          description="Give your counter staff their own login. They get a simple till screen for in-store orders and printable receipts, and every sale lands in your normal order list."
        />
        {error ? <Alert tone="red">{error}</Alert> : null}
        <EmptyState
          icon={ShieldCheck}
          title="The Cashier module is off for this business"
          description="Turn it on to register cashier accounts, take counter orders, print receipts and import old order sheets."
          actionLabel="Enable the Cashier module"
          onAction={enableModule}
        />
      </section>
    );
  }

  return (
    <section className="space-y-6">
      <PageHeader
        eyebrow="Counter"
        title="Cashiers"
        icon={Users}
        description="Cashiers sign in at the same business login and land on their own till screen. They can only see this business, and only what you allow them to see."
        actions={
          <>
            <Link to="/dashboard/orders/import" className="ui-btn-secondary">
              Import old orders
            </Link>
            <button type="button" className="ui-btn-primary" onClick={() => setShowForm((current) => !current)}>
              <UserPlus size={18} />
              {showForm ? "Close" : "Add cashier"}
            </button>
          </>
        }
      />

      {message ? <Alert tone="green">{message}</Alert> : null}
      {error ? <Alert tone="red">{error}</Alert> : null}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Cashiers" value={summary.total ?? 0} icon={Users} tone="violet" />
        <StatCard label="Active" value={summary.active ?? 0} icon={ShieldCheck} tone="green" />
        <StatCard label="Orders handled" value={summary.totalOrders ?? 0} tone="blue" />
        <StatCard label="Sales handled" value={formatMoney(summary.totalSales)} tone="orange" />
      </div>

      {showForm ? (
        <Card as="form" onSubmit={submitNewCashier} className="space-y-4">
          <h2 className="text-base font-bold text-ink">New cashier</h2>
          <div className="grid gap-3 md:grid-cols-2">
            <Field label="Full name">
              <input className="form-input" required minLength={2} value={form.fullName} onChange={(event) => setForm((current) => ({ ...current, fullName: event.target.value }))} />
            </Field>
            <Field label="Employee code (optional)">
              <input className="form-input" value={form.employeeCode} onChange={(event) => setForm((current) => ({ ...current, employeeCode: event.target.value }))} />
            </Field>
            <Field label="Email (sign-in)">
              <input className="form-input" type="email" placeholder="cashier@yourbusiness.pk" value={form.email} onChange={(event) => setForm((current) => ({ ...current, email: event.target.value }))} />
            </Field>
            <Field label="Phone">
              <input className="form-input" placeholder="03001234567" value={form.phone} onChange={(event) => setForm((current) => ({ ...current, phone: event.target.value }))} />
            </Field>
            <Field label="Temporary password" className="md:col-span-2">
              <input className="form-input" type="text" required minLength={8} value={form.password} onChange={(event) => setForm((current) => ({ ...current, password: event.target.value }))} />
              <span className="text-xs font-normal text-muted">
                At least 8 characters with three of: lowercase, uppercase, number, symbol. Share it with the cashier and reset it whenever you need to.
              </span>
            </Field>
          </div>

          <fieldset className="rounded-xl border border-line bg-surface p-4">
            <legend className="px-1 text-xs font-bold uppercase tracking-wider text-subtle">What this cashier may do</legend>
            <div className="grid gap-2 sm:grid-cols-3">
              <Toggle
                label="See all cashier orders"
                hint="Off means they see only their own."
                checked={form.canViewAllCashierOrders}
                onChange={(value) => setForm((current) => ({ ...current, canViewAllCashierOrders: value }))}
              />
              <Toggle
                label="Add manual items"
                hint="Items not in your catalog."
                checked={form.canAddCustomItems}
                onChange={(value) => setForm((current) => ({ ...current, canAddCustomItems: value }))}
              />
              <Toggle
                label="Apply discounts"
                checked={form.canApplyDiscount}
                onChange={(value) => setForm((current) => ({ ...current, canApplyDiscount: value }))}
              />
            </div>
          </fieldset>

          <div className="flex gap-2">
            <button type="submit" className="ui-btn-primary" disabled={isSaving}>
              {isSaving ? "Creating..." : "Create cashier"}
            </button>
            <button type="button" className="ui-btn-secondary" onClick={() => setShowForm(false)}>
              Cancel
            </button>
          </div>
        </Card>
      ) : null}

      <div className="flex flex-wrap gap-2">
        {FILTERS.map((option) => (
          <button
            key={option.value || "all"}
            type="button"
            onClick={() => setFilter(option.value)}
            className={`rounded-full px-4 py-2 text-xs font-bold transition ${
              filter === option.value ? "bg-brand text-white" : "border border-line bg-white text-muted hover:bg-surface"
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>

      {isLoading ? <div className="py-6 text-sm text-muted">Loading cashiers...</div> : null}

      {!isLoading && !cashiers.length ? (
        <EmptyState
          icon={Users}
          title="No cashiers yet"
          description="Add your first counter account. They will sign in at the normal business login and go straight to the till screen."
          actionLabel="Add cashier"
          onAction={() => setShowForm(true)}
        />
      ) : null}

      <div className="space-y-3">
        {cashiers.map((cashier) => {
          const isEditing = editingId === cashier.id;
          return (
            <Card key={cashier.id} className="space-y-4">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="text-base font-extrabold text-ink">{cashier.fullName}</h3>
                    <span className={`ui-pill ${cashier.isActive ? "bg-green-50 text-green-700" : "bg-orange-100 text-orange-700"}`}>
                      {cashier.isActive ? "Active" : "Inactive"}
                    </span>
                    {cashier.employeeCode ? <span className="ui-pill bg-surface text-muted">{cashier.employeeCode}</span> : null}
                  </div>
                  <div className="mt-1 text-xs text-muted">
                    {cashier.email || "No email"} · {cashier.phone || "No phone"}
                  </div>
                  <div className="mt-1 text-xs text-subtle">Last login: {formatDate(cashier.lastLoginAt)}</div>
                </div>
                <div className="grid grid-cols-2 gap-4 text-right sm:grid-cols-3">
                  <Metric label="Orders" value={cashier.stats?.totalOrders ?? 0} />
                  <Metric label="Sales" value={formatMoney(cashier.stats?.totalSales)} />
                  <Metric label="Last sale" value={cashier.stats?.lastOrderAt ? formatDate(cashier.stats.lastOrderAt) : "-"} />
                </div>
              </div>

              {isEditing ? (
                <div className="space-y-3 rounded-xl border border-line bg-surface p-4">
                  <div className="grid gap-3 md:grid-cols-2">
                    <Field label="Full name">
                      <input className="form-input" value={editDraft.fullName || ""} onChange={(event) => setEditDraft((current) => ({ ...current, fullName: event.target.value }))} />
                    </Field>
                    <Field label="Employee code">
                      <input className="form-input" value={editDraft.employeeCode || ""} onChange={(event) => setEditDraft((current) => ({ ...current, employeeCode: event.target.value }))} />
                    </Field>
                    <Field label="Email">
                      <input className="form-input" value={editDraft.email || ""} onChange={(event) => setEditDraft((current) => ({ ...current, email: event.target.value }))} />
                    </Field>
                    <Field label="Phone">
                      <input className="form-input" value={editDraft.phone || ""} onChange={(event) => setEditDraft((current) => ({ ...current, phone: event.target.value }))} />
                    </Field>
                  </div>
                  <div className="grid gap-2 sm:grid-cols-3">
                    <Toggle label="See all cashier orders" checked={Boolean(editDraft.canViewAllCashierOrders)} onChange={(value) => setEditDraft((current) => ({ ...current, canViewAllCashierOrders: value }))} />
                    <Toggle label="Add manual items" checked={Boolean(editDraft.canAddCustomItems)} onChange={(value) => setEditDraft((current) => ({ ...current, canAddCustomItems: value }))} />
                    <Toggle label="Apply discounts" checked={Boolean(editDraft.canApplyDiscount)} onChange={(value) => setEditDraft((current) => ({ ...current, canApplyDiscount: value }))} />
                  </div>
                  <div className="flex gap-2">
                    <button type="button" className="ui-btn-primary" disabled={isSaving} onClick={() => saveEdit(cashier.id)}>
                      Save changes
                    </button>
                    <button type="button" className="ui-btn-secondary" onClick={() => setEditingId("")}>
                      Cancel
                    </button>
                  </div>
                </div>
              ) : null}

              {resetTarget === cashier.id ? (
                <div className="flex flex-wrap items-end gap-3 rounded-xl border border-line bg-surface p-4">
                  <Field label="New temporary password" className="min-w-[16rem] flex-1">
                    <input className="form-input" type="text" minLength={8} value={resetPassword} onChange={(event) => setResetPassword(event.target.value)} />
                  </Field>
                  <button type="button" className="ui-btn-primary" disabled={isSaving || resetPassword.length < 8} onClick={() => submitPasswordReset(cashier.id)}>
                    Reset password
                  </button>
                  <button type="button" className="ui-btn-secondary" onClick={() => { setResetTarget(""); setResetPassword(""); }}>
                    Cancel
                  </button>
                </div>
              ) : null}

              <div className="flex flex-wrap gap-2 border-t border-line-soft pt-3">
                <button
                  type="button"
                  className="ui-btn-secondary px-3 py-2 text-xs"
                  onClick={() => {
                    setEditingId(isEditing ? "" : cashier.id);
                    setEditDraft({
                      fullName: cashier.fullName,
                      email: cashier.email,
                      phone: cashier.phone,
                      employeeCode: cashier.employeeCode,
                      ...cashier.permissions,
                    });
                  }}
                >
                  {isEditing ? "Close editor" : "Edit"}
                </button>
                <button type="button" className="ui-btn-secondary px-3 py-2 text-xs" onClick={() => setResetTarget(resetTarget === cashier.id ? "" : cashier.id)}>
                  <KeyRound size={14} />
                  Reset password
                </button>
                <button type="button" className="ui-btn-secondary px-3 py-2 text-xs" onClick={() => toggleStatus(cashier)}>
                  <Power size={14} />
                  {cashier.isActive ? "Deactivate" : "Activate"}
                </button>
                <button
                  type="button"
                  className="rounded-xl border border-red-200 bg-white px-3 py-2 text-xs font-semibold text-red-600 transition hover:bg-red-50"
                  onClick={() => removeAccess(cashier)}
                >
                  Remove access
                </button>
                <Link to={`/dashboard/transactions?source=cashier`} className="ml-auto self-center text-xs font-bold text-brand">
                  View cashier orders
                </Link>
              </div>
            </Card>
          );
        })}
      </div>
    </section>
  );
}

function Field({ label, className = "", children }) {
  return (
    <label className={`block space-y-1.5 text-sm font-semibold text-ink ${className}`.trim()}>
      <span>{label}</span>
      {children}
    </label>
  );
}

function Toggle({ label, hint, checked, onChange }) {
  return (
    <label className="flex cursor-pointer items-start gap-2 rounded-lg bg-white px-3 py-2.5 text-sm">
      <input type="checkbox" className="mt-0.5 h-4 w-4 accent-brand" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      <span>
        <span className="font-semibold text-ink">{label}</span>
        {hint ? <span className="block text-xs font-normal text-muted">{hint}</span> : null}
      </span>
    </label>
  );
}

function Metric({ label, value }) {
  return (
    <div>
      <div className="text-[10px] font-bold uppercase tracking-wider text-subtle">{label}</div>
      <div className="text-sm font-extrabold text-ink">{value}</div>
    </div>
  );
}
