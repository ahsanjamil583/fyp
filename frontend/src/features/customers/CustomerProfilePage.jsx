import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { DynamicTable } from "../../components/dynamic/DynamicTable.jsx";
import { useModules } from "../../context/ModuleContext.jsx";
import { useTenant } from "../../context/TenantContext.jsx";
import { getCustomFields } from "../../services/customFieldApi.js";
import { getCustomer } from "../../services/customerApi.js";

export function CustomerProfilePage() {
  const { customerId } = useParams();
  const { selectedTenant } = useTenant();
  const { hasModule, isLoadingModules } = useModules();
  const customersModuleEnabled = hasModule("customers");
  const [customer, setCustomer] = useState(null);
  const [fields, setFields] = useState([]);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function loadProfile() {
      if (!selectedTenant?.id || !customerId || !customersModuleEnabled) return;
      setIsLoading(true);
      setError("");
      try {
        const [customerData, fieldData] = await Promise.all([
          getCustomer(selectedTenant.id, customerId),
          getCustomFields(selectedTenant.id, { moduleCode: "customers", entityType: "customer" }),
        ]);
        setCustomer(customerData);
        setFields(fieldData.filter((field) => field.isActive));
      } catch (requestError) {
        setError(requestError.response?.data?.detail || "Unable to load customer profile.");
      } finally {
        setIsLoading(false);
      }
    }

    loadProfile();
  }, [selectedTenant?.id, customerId, customersModuleEnabled]);

  if (!selectedTenant) {
    return (
      <section className="space-y-4">
        <h1 className="text-3xl font-semibold text-ink">Customer Profile</h1>
        <p className="text-sm text-muted">Create a business before viewing customer profiles.</p>
      </section>
    );
  }

  if (isLoadingModules) {
    return (
      <section className="space-y-4">
        <h1 className="text-3xl font-semibold text-ink">Customer Profile</h1>
        <p className="text-sm text-muted">Loading customer module settings...</p>
      </section>
    );
  }

  if (!customersModuleEnabled) {
    return (
      <section className="space-y-4">
        <h1 className="text-3xl font-semibold text-ink">Customer Profile</h1>
        <p className="text-sm text-muted">Enable the Customers module before viewing customer profiles.</p>
        <Link className="inline-flex rounded-md bg-brand px-4 py-2 text-sm font-semibold text-white" to="/dashboard/modules">
          Enable Module
        </Link>
      </section>
    );
  }

  if (isLoading) {
    return (
      <section className="space-y-4">
        <h1 className="text-3xl font-semibold text-ink">Customer Profile</h1>
        <p className="text-sm text-muted">Loading customer details...</p>
      </section>
    );
  }

  if (error) {
    return (
      <section className="space-y-4">
        <Link className="text-sm font-semibold text-brand" to="/dashboard/customers">
          Back to customers
        </Link>
        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
      </section>
    );
  }

  return (
    <section className="space-y-6">
      <div className="flex flex-col gap-3 border-b border-line pb-6 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <Link className="text-sm font-semibold text-brand" to="/dashboard/customers">
            Back to customers
          </Link>
          <p className="mt-4 text-sm font-semibold uppercase tracking-wide text-brand">Customer Profile</p>
          <h1 className="mt-2 text-3xl font-semibold text-ink">{customer.name}</h1>
          <p className="mt-2 text-sm capitalize text-muted">
            {customer.type} / {customer.status}
          </p>
        </div>
        <div className="rounded-md border border-line bg-white px-4 py-3 text-sm text-muted shadow-sm">
          <div className="font-semibold text-ink">Stats</div>
          <div className="mt-1">Transactions: {customer.stats?.totalTransactions || 0}</div>
          <div>Total spent: {customer.stats?.totalSpent || 0}</div>
          <div>Last activity: {customer.stats?.lastActivityAt ? new Date(customer.stats.lastActivityAt).toLocaleString() : "-"}</div>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_1.2fr]">
        <div className="space-y-5">
          <ProfileCard title="Contact">
            <InfoRow label="Phone" value={customer.phone} />
            <InfoRow label="Email" value={customer.email || "-"} />
            <InfoRow label="Customer user" value={customer.customerUserId || "Not linked"} />
          </ProfileCard>

          <ProfileCard title="Address">
            <InfoRow label="Line 1" value={customer.address?.line1 || "-"} />
            <InfoRow label="City" value={customer.address?.city || "-"} />
          </ProfileCard>

          <ProfileCard title="Tags">
            {customer.tags?.length ? (
              <div className="flex flex-wrap gap-2">
                {customer.tags.map((tag) => (
                  <span key={tag} className="rounded-md bg-surface px-2.5 py-1 text-xs font-semibold text-muted">
                    {tag}
                  </span>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted">No tags added.</p>
            )}
          </ProfileCard>

          <ProfileCard title="Segments">
            {customer.segments?.length ? (
              <div className="flex flex-wrap gap-2">
                {customer.segments.map((segment) => (
                  <span key={segment} className="rounded-md bg-blue-50 px-2.5 py-1 text-xs font-semibold text-blue-700">
                    {segment.replaceAll("_", " ")}
                  </span>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted">No segment detected yet.</p>
            )}
          </ProfileCard>
        </div>

        <ProfileCard title="Custom Fields">
          <DynamicTable fields={fields} rows={[customer.customFields || {}]} />
        </ProfileCard>
      </div>
    </section>
  );
}

function ProfileCard({ title, children }) {
  return (
    <div className="rounded-md border border-line bg-white p-5 shadow-sm">
      <h2 className="mb-4 text-lg font-semibold text-ink">{title}</h2>
      <div className="space-y-3">{children}</div>
    </div>
  );
}

function InfoRow({ label, value }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-line pb-3 last:border-b-0 last:pb-0">
      <span className="text-sm text-muted">{label}</span>
      <span className="text-right text-sm font-semibold text-ink">{value}</span>
    </div>
  );
}
