import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { DynamicForm } from "../../components/dynamic/DynamicForm.jsx";
import { DynamicTable } from "../../components/dynamic/DynamicTable.jsx";
import { useModules } from "../../context/ModuleContext.jsx";
import { useTenant } from "../../context/TenantContext.jsx";
import { getCustomFields } from "../../services/customFieldApi.js";
import { createCustomer, deleteCustomer, getCustomerInsights, getCustomers, updateCustomer } from "../../services/customerApi.js";
import { StatCard as KitStatCard } from "../../components/ui/index.jsx";
import { SectionTitle } from "../../components/ui/SectionTitle.jsx";

const emptyForm = {
  type: "customer",
  name: "",
  phone: "",
  email: "",
  addressLine1: "",
  city: "",
  tagsText: "",
  status: "active",
};

const segmentLabels = {
  all: "All segments",
  new: "New",
  repeat: "Repeat",
  high_value: "High value",
  inactive: "Inactive",
  vip: "VIP",
  customer_portal: "Customer portal",
  website: "Website",
};

export function CustomersPage() {
  const { selectedTenant } = useTenant();
  const { hasModule, isLoadingModules } = useModules();
  const customersModuleEnabled = hasModule("customers");
  const [customers, setCustomers] = useState([]);
  const [meta, setMeta] = useState({});
  const [insights, setInsights] = useState(null);
  const [availableTags, setAvailableTags] = useState([]);
  const [fields, setFields] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [customValues, setCustomValues] = useState({});
  const [customErrors, setCustomErrors] = useState([]);
  const [editingCustomer, setEditingCustomer] = useState(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [segmentFilter, setSegmentFilter] = useState("all");
  const [tagFilter, setTagFilter] = useState("");
  const [serverMessage, setServerMessage] = useState("");
  const [serverError, setServerError] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (selectedTenant?.id && customersModuleEnabled) {
      refreshCustomers();
      getCustomerInsights(selectedTenant.id).then(setInsights).catch(() => setInsights(null));
      getCustomFields(selectedTenant.id, { moduleCode: "customers", entityType: "customer" })
        .then((data) => setFields(data.filter((field) => field.isActive)))
        .catch(() => setFields([]));
    }
  }, [selectedTenant?.id, statusFilter, segmentFilter, tagFilter, customersModuleEnabled]);

  async function refreshCustomers(nextSearch = search) {
    const result = await getCustomers(selectedTenant.id, {
      search: nextSearch,
      status: statusFilter || undefined,
      segment: segmentFilter !== "all" ? segmentFilter : undefined,
      tag: tagFilter || undefined,
      page: 1,
      limit: 20,
    });
    setCustomers(result.items);
    setMeta(result.meta);
    setAvailableTags(result.meta?.filters?.availableTags || []);
    if (result.meta?.insights) {
      setInsights(result.meta.insights);
    }
  }

  function updateForm(key, value) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function resetForm() {
    setForm(emptyForm);
    setCustomValues({});
    setCustomErrors([]);
    setEditingCustomer(null);
  }

  function editCustomer(customer) {
    setEditingCustomer(customer);
    setForm({
      type: customer.type || "customer",
      name: customer.name || "",
      phone: customer.phone || "",
      email: customer.email || "",
      addressLine1: customer.address?.line1 || "",
      city: customer.address?.city || "",
      tagsText: (customer.tags || []).join(", "),
      status: customer.status || "active",
    });
    setCustomValues(customer.customFields || {});
    setCustomErrors([]);
  }

  async function submit(event) {
    event.preventDefault();
    setServerError("");
    setServerMessage("");
    setCustomErrors([]);
    setIsSaving(true);

    const payload = {
      type: form.type,
      name: form.name,
      phone: form.phone,
      email: form.email,
      status: form.status,
      tags: form.tagsText.split(",").map((tag) => tag.trim()).filter(Boolean),
      address: {
        line1: form.addressLine1,
        city: form.city,
      },
      customFields: customValues,
    };

    try {
      if (editingCustomer) {
        await updateCustomer(selectedTenant.id, editingCustomer.id, payload);
        setServerMessage("Customer updated.");
      } else {
        await createCustomer(selectedTenant.id, payload);
        setServerMessage("Customer created.");
      }
      resetForm();
      await refreshCustomers();
      const insightData = await getCustomerInsights(selectedTenant.id);
      setInsights(insightData);
    } catch (error) {
      const detail = error.response?.data?.detail;
      if (Array.isArray(detail)) {
        setCustomErrors(detail);
        setServerError("Please fix custom field validation errors.");
      } else {
        setServerError(detail || "Unable to save customer.");
      }
    } finally {
      setIsSaving(false);
    }
  }

  async function handleDelete(customerId) {
    await deleteCustomer(selectedTenant.id, customerId);
    await refreshCustomers();
    const insightData = await getCustomerInsights(selectedTenant.id);
    setInsights(insightData);
  }

  const tableRows = useMemo(() => customers.map((customer) => customer.customFields || {}), [customers]);

  if (!selectedTenant) {
    return (
      <section className="space-y-4">
        <h1 className="text-2xl font-extrabold tracking-tight text-ink">Customers</h1>
        <p className="text-sm text-muted">Create a business before adding customers.</p>
        <Link className="inline-flex rounded-xl bg-brand px-4 py-2 text-sm font-semibold text-white" to="/dashboard/business">
          Create Business
        </Link>
      </section>
    );
  }

  if (isLoadingModules) {
    return (
      <section className="space-y-4">
        <h1 className="text-2xl font-extrabold tracking-tight text-ink">Customers</h1>
        <p className="text-sm text-muted">Loading customer module settings...</p>
      </section>
    );
  }

  if (!customersModuleEnabled) {
    return (
      <section className="space-y-4">
        <h1 className="text-2xl font-extrabold tracking-tight text-ink">Customers</h1>
        <p className="text-sm text-muted">Enable the Customers module before managing customer records.</p>
        <Link className="inline-flex rounded-xl bg-brand px-4 py-2 text-sm font-semibold text-white" to="/dashboard/modules">
          Enable Module
        </Link>
      </section>
    );
  }

  return (
    <section className="space-y-6">
      <div className="border-b border-line-soft pb-5">
        <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-brand">Customer Module</p>
        <h1 className="mt-1.5 text-2xl font-extrabold tracking-tight text-ink">Customers</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-muted">
          Manage customers, tags, segments, and repeat-customer insights from one place.
        </p>
      </div>

      {serverMessage ? <div className="rounded-xl border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">{serverMessage}</div> : null}
      {serverError ? <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{serverError}</div> : null}

      {insights ? (
        <div className="grid gap-4 sm:grid-cols-2 2xl:grid-cols-4">
          <InsightCard label="Total Customers" value={insights.summary?.totalCustomers || 0} />
          <InsightCard label="Repeat Customers" value={insights.summary?.repeatCustomers || 0} />
          <InsightCard label="Repeat Rate" value={`${insights.summary?.repeatCustomerRate || 0}%`} />
          <InsightCard label="High Value" value={insights.summary?.highValueCustomers || 0} />
        </div>
      ) : null}

      <div className="grid gap-6">
        <form className="space-y-5 rounded-2xl border border-line bg-white p-5 shadow-card sm:p-6" onSubmit={submit}>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <SectionTitle>{editingCustomer ? "Edit Customer" : "Add Customer"}</SectionTitle>
              <p className="mt-1 text-sm text-muted">Save profile, contact details, tags, and custom customer fields in one clean form.</p>
            </div>
            {editingCustomer ? (
              <button type="button" className="w-fit rounded-xl border border-line px-4 py-2 text-sm font-semibold text-ink hover:bg-surface" onClick={resetForm}>
                Cancel edit
              </button>
            ) : null}
          </div>

          <div className="grid gap-4 2xl:grid-cols-2">
            <Field label="Type">
              <select className="form-input" value={form.type} onChange={(event) => updateForm("type", event.target.value)}>
                <option value="customer">Customer</option>
                <option value="client">Client</option>
                <option value="patient">Patient</option>
                <option value="student">Student</option>
                <option value="member">Member</option>
                <option value="lead">Lead</option>
              </select>
            </Field>
            <Field label="Name">
              <input className="form-input" required value={form.name} onChange={(event) => updateForm("name", event.target.value)} />
            </Field>
            <Field label="Phone">
              <input className="form-input" required value={form.phone} onChange={(event) => updateForm("phone", event.target.value)} />
            </Field>
            <Field label="Email">
              <input className="form-input" value={form.email} onChange={(event) => updateForm("email", event.target.value)} />
            </Field>
            <Field label="Address">
              <input className="form-input" value={form.addressLine1} onChange={(event) => updateForm("addressLine1", event.target.value)} />
            </Field>
            <Field label="City">
              <input className="form-input" value={form.city} onChange={(event) => updateForm("city", event.target.value)} />
            </Field>
            <Field label="Tags">
              <input className="form-input" placeholder="vip, frequent, wholesale" value={form.tagsText} onChange={(event) => updateForm("tagsText", event.target.value)} />
            </Field>
            <Field label="Status">
              <select className="form-input" value={form.status} onChange={(event) => updateForm("status", event.target.value)}>
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
                <option value="blocked">Blocked</option>
              </select>
            </Field>
          </div>

          <div className="rounded-xl border border-line bg-surface p-4">
            <SectionTitle className="mb-3 !text-sm">Custom fields</SectionTitle>
            <DynamicForm fields={fields} values={customValues} onChange={setCustomValues} errors={customErrors} columns="single" />
          </div>

          <div className="flex flex-col gap-2 sm:flex-row">
            <button className="flex-1 rounded-xl bg-brand px-4 py-2.5 text-sm font-semibold text-white hover:bg-brand-700" disabled={isSaving}>
              {isSaving ? "Saving..." : editingCustomer ? "Update Customer" : "Create Customer"}
            </button>
            {editingCustomer ? (
              <button type="button" className="rounded-xl border border-line px-4 py-2.5 text-sm font-semibold text-ink hover:bg-surface" onClick={resetForm}>
                Cancel
              </button>
            ) : null}
          </div>
        </form>

        <div className="space-y-5">
          <div className="rounded-2xl border border-line bg-white p-5 shadow-card sm:p-6">
            <div className="flex flex-col gap-4">
              <div>
                <SectionTitle>Customer Records</SectionTitle>
                <p className="mt-1 text-sm text-muted">{meta.total || 0} records found.</p>
              </div>
              <div className="grid w-full gap-2 sm:grid-cols-2 2xl:grid-cols-[minmax(220px,1fr)_160px_180px_160px_auto]">
                <input className="form-input" placeholder="Search name, phone, email, tag" value={search} onChange={(event) => setSearch(event.target.value)} />
                <select className="form-input" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                  <option value="">All statuses</option>
                  <option value="active">Active</option>
                  <option value="inactive">Inactive</option>
                  <option value="blocked">Blocked</option>
                </select>
                <select className="form-input" value={segmentFilter} onChange={(event) => setSegmentFilter(event.target.value)}>
                  {Object.entries(segmentLabels).map(([code, label]) => (
                    <option key={code} value={code}>{label}</option>
                  ))}
                </select>
                <select className="form-input" value={tagFilter} onChange={(event) => setTagFilter(event.target.value)}>
                  <option value="">All tags</option>
                  {availableTags.map((tag) => (
                    <option key={tag} value={tag}>{tag}</option>
                  ))}
                </select>
                <button type="button" className="rounded-xl bg-ink px-4 py-2 text-sm font-semibold text-white" onClick={() => refreshCustomers()}>
                  Search
                </button>
              </div>
            </div>

            {insights?.popularTags?.length ? (
              <div className="mt-4 flex flex-wrap gap-2">
                {insights.popularTags.map((item) => (
                  <button
                    key={item.tag}
                    type="button"
                    className="rounded-xl border border-line bg-surface px-3 py-1.5 text-xs font-semibold text-muted hover:bg-white"
                    onClick={() => setTagFilter(item.tag)}
                  >
                    {item.tag} ({item.count})
                  </button>
                ))}
              </div>
            ) : null}

            <div className="mt-4 overflow-x-auto rounded-xl border border-line">
              <table className="min-w-[760px] divide-y divide-line text-sm">
                <thead className="bg-surface">
                  <tr>
                    <th className="px-3 py-3 text-left font-semibold text-ink">Name</th>
                    <th className="px-3 py-3 text-left font-semibold text-ink">Phone</th>
                    <th className="px-3 py-3 text-left font-semibold text-ink">Segments</th>
                    <th className="px-3 py-3 text-left font-semibold text-ink">Stats</th>
                    <th className="px-3 py-3 text-right font-semibold text-ink">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line bg-white">
                  {customers.map((customer) => (
                    <tr key={customer.id}>
                      <td className="px-3 py-3">
                        <Link className="font-semibold text-ink hover:text-brand" to={`/dashboard/customers/${customer.id}`}>
                          {customer.name}
                        </Link>
                        <div className="text-xs text-muted">{customer.email || "-"}</div>
                        <div className="mt-2 flex flex-wrap gap-1">
                          {(customer.tags || []).map((tag) => (
                            <span key={tag} className="rounded-xl bg-surface px-2 py-1 text-[11px] font-semibold text-muted">
                              {tag}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="px-3 py-3 text-muted">{customer.phone}</td>
                      <td className="px-3 py-3">
                        <div className="flex flex-wrap gap-1">
                          {(customer.segments || []).length ? (customer.segments || []).map((segment) => (
                            <span key={segment} className="rounded-xl bg-brand-50 px-2 py-1 text-[11px] font-semibold text-brand-700">
                              {segmentLabels[segment] || segment}
                            </span>
                          )) : <span className="text-muted">-</span>}
                        </div>
                      </td>
                      <td className="px-3 py-3 text-muted">
                        <div>{customer.stats?.totalTransactions || 0} transactions</div>
                        <div>PKR {customer.stats?.totalSpent || 0}</div>
                      </td>
                      <td className="whitespace-nowrap px-3 py-3 text-right">
                        <Link className="mr-1 inline-flex rounded-xl border border-line px-2.5 py-1.5 text-sm font-semibold text-ink hover:bg-surface" to={`/dashboard/customers/${customer.id}`}>
                          View
                        </Link>
                        <button type="button" className="mr-1 rounded-xl border border-line px-2.5 py-1.5 text-sm font-semibold text-ink hover:bg-surface" onClick={() => editCustomer(customer)}>
                          Edit
                        </button>
                        <button type="button" className="rounded-xl border border-line px-2.5 py-1.5 text-sm font-semibold text-ink hover:bg-surface" onClick={() => handleDelete(customer.id)}>
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                  {!customers.length ? (
                    <tr>
                      <td className="px-4 py-5 text-sm text-muted" colSpan="5">No customers yet.</td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </div>

          {insights?.topRepeatCustomers?.length ? (
            <div className="rounded-2xl border border-line bg-white p-5 shadow-card sm:p-6">
              <SectionTitle className="mb-4">Top Repeat Customers</SectionTitle>
              <div className="space-y-3">
                {insights.topRepeatCustomers.map((customer) => (
                  <div key={customer.id} className="flex flex-col gap-3 rounded-xl border border-line px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <div className="font-semibold text-ink">{customer.name}</div>
                      <div className="text-sm text-muted">{customer.phone || "-"}</div>
                    </div>
                    <div className="text-right text-sm text-muted">
                      <div>{customer.totalTransactions} transactions</div>
                      <div>PKR {customer.totalSpent}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          <div className="rounded-2xl border border-line bg-white p-5 shadow-card sm:p-6">
            <SectionTitle className="mb-4">Custom Field Table View</SectionTitle>
            <DynamicTable fields={fields} rows={tableRows} />
          </div>
        </div>
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

function InsightCard({ label, value }) {
  return <KitStatCard label={label} value={value} />;
}
