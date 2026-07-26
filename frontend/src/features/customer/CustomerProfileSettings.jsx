import { useEffect, useState } from "react";

import { useCustomer } from "../../context/CustomerContext.jsx";
import { updateCustomerProfile } from "../../services/customerAuthApi.js";

export function CustomerProfileSettings() {
  const { customer, customerProfile, refreshCustomerMe } = useCustomer();
  const [form, setForm] = useState({ phone: "", line1: "", city: "" });
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    refreshCustomerMe().catch(() => {});
  }, [refreshCustomerMe]);

  useEffect(() => {
    if (!customerProfile) return;
    setForm({
      phone: customerProfile.phone || customer?.phone || "",
      line1: customerProfile.defaultAddress?.line1 || "",
      city: customerProfile.defaultAddress?.city || "",
    });
  }, [customerProfile, customer]);

  async function submit(event) {
    event.preventDefault();
    setMessage("");
    setError("");
    try {
      await updateCustomerProfile({
        phone: form.phone,
        defaultAddress: { line1: form.line1, city: form.city },
        savedAddresses: customerProfile?.savedAddresses || [],
        preferences: customerProfile?.preferences || {},
      });
      await refreshCustomerMe();
      setMessage("Customer profile updated.");
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to update profile.");
    }
  }

  return (
    <section className="space-y-6">
      <div className="border-b border-line pb-6">
        <p className="text-sm font-semibold uppercase tracking-wide text-brand">Profile</p>
        <h1 className="mt-2 text-3xl font-semibold text-ink">{customer?.fullName || "Customer Profile"}</h1>
      </div>
      {message ? <div className="rounded-md border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">{message}</div> : null}
      {error ? <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}
      <form className="grid gap-4 rounded-md border border-line bg-white p-5 shadow-sm md:grid-cols-2" onSubmit={submit}>
        <label>
          <span className="mb-1.5 block text-sm font-medium text-ink">Phone</span>
          <input className="form-input" value={form.phone} onChange={(event) => setForm((current) => ({ ...current, phone: event.target.value }))} />
        </label>
        <label>
          <span className="mb-1.5 block text-sm font-medium text-ink">Email</span>
          <input className="form-input" disabled value={customer?.email || ""} />
        </label>
        <label className="md:col-span-2">
          <span className="mb-1.5 block text-sm font-medium text-ink">Default address</span>
          <input className="form-input" value={form.line1} onChange={(event) => setForm((current) => ({ ...current, line1: event.target.value }))} />
        </label>
        <label>
          <span className="mb-1.5 block text-sm font-medium text-ink">City</span>
          <input className="form-input" value={form.city} onChange={(event) => setForm((current) => ({ ...current, city: event.target.value }))} />
        </label>
        <div className="md:col-span-2">
          <button className="rounded-md bg-brand px-4 py-2 text-sm font-semibold text-white">Save Profile</button>
        </div>
      </form>
    </section>
  );
}
