import { useState } from "react";
import { Link } from "react-router-dom";

import { useModules } from "../../context/ModuleContext.jsx";
import { useTenant } from "../../context/TenantContext.jsx";
import { importItems } from "../../services/itemApi.js";

export function ItemImportPage() {
  const { selectedTenant } = useTenant();
  const { hasModule, isLoadingModules } = useModules();
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [isImporting, setIsImporting] = useState(false);

  async function submit(event) {
    event.preventDefault();
    if (!file || !selectedTenant) return;
    setError("");
    setResult(null);
    setIsImporting(true);
    try {
      const data = await importItems(selectedTenant.id, file);
      setResult(data);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to import items.");
    } finally {
      setIsImporting(false);
    }
  }

  if (!selectedTenant || isLoadingModules) {
    return (
      <section className="space-y-4">
        <h1 className="text-3xl font-semibold text-ink">Import Items</h1>
        <p className="text-sm text-muted">Loading item module settings...</p>
      </section>
    );
  }

  if (!hasModule("items")) {
    return (
      <section className="space-y-4">
        <h1 className="text-3xl font-semibold text-ink">Import Items</h1>
        <p className="text-sm text-muted">Enable the Items module before importing Excel files.</p>
      </section>
    );
  }

  return (
    <section className="space-y-6">
      <div className="border-b border-line pb-6">
        <Link className="text-sm font-semibold text-brand" to="/dashboard/items">Back to items</Link>
        <p className="mt-4 text-sm font-semibold uppercase tracking-wide text-brand">Excel Import</p>
        <h1 className="mt-2 text-3xl font-semibold text-ink">Import Items</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-muted">
          Use columns like name, itemType, price, unit, stockQuantity, serviceDurationMinutes, serviceBufferMinutes, serviceDeliveryMode, tags, and custom.field_key for custom fields.
        </p>
      </div>

      <form className="max-w-2xl space-y-4 rounded-md border border-line bg-white p-5 shadow-sm" onSubmit={submit}>
        <label className="block">
          <span className="mb-1.5 block text-sm font-medium text-ink">Excel file</span>
          <input className="form-input" accept=".xlsx,.xlsm" required type="file" onChange={(event) => setFile(event.target.files?.[0] || null)} />
        </label>
        <button className="rounded-md bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700" disabled={isImporting}>
          {isImporting ? "Importing..." : "Import Items"}
        </button>
      </form>

      {error ? <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}

      {result ? (
        <div className="rounded-md border border-line bg-white p-5 shadow-sm">
          <h2 className="text-lg font-semibold text-ink">Import Result</h2>
          <div className="mt-3 grid gap-3 sm:grid-cols-3">
            <Stat label="Rows" value={result.import.totalRows} />
            <Stat label="Created" value={result.import.successCount} />
            <Stat label="Errors" value={result.import.errorCount} />
          </div>
          {result.import.errors?.length ? (
            <div className="mt-5 overflow-hidden rounded-md border border-line">
              <table className="min-w-full divide-y divide-line text-sm">
                <thead className="bg-surface">
                  <tr>
                    <th className="px-4 py-3 text-left font-semibold text-ink">Row</th>
                    <th className="px-4 py-3 text-left font-semibold text-ink">Message</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line bg-white">
                  {result.import.errors.map((rowError) => (
                    <tr key={rowError.row}>
                      <td className="px-4 py-3 text-muted">{rowError.row}</td>
                      <td className="px-4 py-3 text-muted">{rowError.message}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function Stat({ label, value }) {
  return (
    <div className="rounded-md border border-line bg-surface p-4">
      <div className="text-sm text-muted">{label}</div>
      <div className="mt-2 text-2xl font-semibold text-ink">{value}</div>
    </div>
  );
}
