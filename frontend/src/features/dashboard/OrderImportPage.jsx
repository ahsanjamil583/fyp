import { AlertTriangle, CheckCircle2, Download, FileSpreadsheet, History, Upload } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { Alert, Card, PageHeader, StatCard } from "../../components/ui/index.jsx";
import { useTenant } from "../../context/TenantContext.jsx";
import { getApiErrorMessage } from "../../services/apiError.js";
import {
  confirmOrderImport,
  downloadOrderImportErrors,
  getOrderImportColumns,
  getOrderImportHistory,
  previewOrderImport,
} from "../../services/orderImportApi.js";

/**
 * Upload, look, then commit.
 *
 * The upload step never writes anything: it returns what the parser understood, which
 * rows it could not read, and which ones look like orders the business already has. The
 * owner reads that and confirms, so a mis-mapped column costs a second upload rather
 * than a corrupted order history.
 */

function formatMoney(value) {
  return `PKR ${Number(value || 0).toLocaleString("en-PK", { maximumFractionDigits: 0 })}`;
}

function formatDate(value) {
  if (!value) return "-";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "-" : parsed.toLocaleString("en-PK", { dateStyle: "medium", timeStyle: "short" });
}

export function OrderImportPage() {
  const { selectedTenant } = useTenant();
  const [columns, setColumns] = useState([]);
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [skipDuplicates, setSkipDuplicates] = useState(true);
  const [result, setResult] = useState(null);
  const [history, setHistory] = useState([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [isConfirming, setIsConfirming] = useState(false);

  const loadHistory = useCallback(async () => {
    if (!selectedTenant?.id) return;
    try {
      const data = await getOrderImportHistory(selectedTenant.id, { limit: 10 });
      setHistory(data.items);
    } catch {
      setHistory([]);
    }
  }, [selectedTenant?.id]);

  useEffect(() => {
    if (!selectedTenant?.id) return;
    getOrderImportColumns(selectedTenant.id).then(setColumns).catch(() => setColumns([]));
    loadHistory();
  }, [selectedTenant?.id, loadHistory]);

  async function uploadForPreview(event) {
    event.preventDefault();
    if (!file || !selectedTenant?.id) return;
    setIsUploading(true);
    setError("");
    setMessage("");
    setResult(null);
    try {
      setPreview(await previewOrderImport(selectedTenant.id, file));
    } catch (requestError) {
      setPreview(null);
      setError(getApiErrorMessage(requestError, "That file could not be read."));
    } finally {
      setIsUploading(false);
    }
  }

  async function confirmImport() {
    if (!preview) return;
    const rows = preview.orders.filter((row) => !skipDuplicates || !row.isDuplicate);
    if (!rows.length) {
      setError("Every order in this file is already in your records.");
      return;
    }
    setIsConfirming(true);
    setError("");
    try {
      const data = await confirmOrderImport(selectedTenant.id, {
        fileName: preview.fileName,
        skipDuplicates,
        rows: rows.map((row) => ({
          rowNumber: row.rowNumber,
          orderNumber: row.orderNumber,
          orderDate: row.orderDate,
          customerName: row.customerName,
          customerPhone: row.customerPhone,
          customerEmail: row.customerEmail,
          items: row.items,
          discount: row.discount,
          tax: row.tax,
          totalAmount: row.totalAmount,
          paymentMethod: row.paymentMethod,
          paymentStatus: row.paymentStatus,
          orderStatus: row.orderStatus,
          notes: row.notes,
        })),
      });
      setResult(data);
      setPreview(null);
      setFile(null);
      setMessage(`${data.import.successCount} order(s) imported into your order list.`);
      await loadHistory();
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "The import could not be completed."));
    } finally {
      setIsConfirming(false);
    }
  }

  if (!selectedTenant) {
    return (
      <section className="space-y-4">
        <h1 className="text-2xl font-extrabold tracking-tight text-ink">Import orders</h1>
        <p className="text-sm text-muted">Create a business before importing orders.</p>
        <Link className="ui-btn-primary" to="/dashboard/business">
          Create business
        </Link>
      </section>
    );
  }

  const summary = preview?.summary || {};

  return (
    <section className="space-y-6">
      <PageHeader
        eyebrow="Orders"
        title="Import previous orders"
        icon={FileSpreadsheet}
        description="Bring your old sales sheet into BizXusAI so all your history lives in one place. Imported orders show up in your normal order list, reports and customer history, tagged as imported."
        actions={
          <Link to="/dashboard/transactions?source=imported" className="ui-btn-secondary">
            View imported orders
          </Link>
        }
      />

      {message ? <Alert tone="green">{message}</Alert> : null}
      {error ? <Alert tone="red">{error}</Alert> : null}

      <Card>
        <h2 className="text-base font-bold text-ink">Columns we can read</h2>
        <p className="mt-1 text-sm text-muted">
          Put the column names in the first row. Spelling is flexible - each name below also accepts the alternatives shown. Anything we cannot
          recognise is listed back to you after the upload rather than being guessed at.
        </p>
        <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {columns.map((column) => (
            <div key={column.key} className="rounded-xl border border-line bg-surface px-3 py-2">
              <div className="text-sm font-bold text-ink">{column.label}</div>
              <div className="mt-0.5 truncate text-[11px] text-muted">also: {column.examples.join(", ")}</div>
            </div>
          ))}
        </div>
        <p className="mt-3 text-xs text-muted">
          One row per item. Repeat the same order number on several rows and they become one order with several lines. Supported files:
          .xlsx, .xlsm and .csv — if yours is an old .xls, open it in Excel and save it as .xlsx first.
        </p>
      </Card>

      <Card as="form" onSubmit={uploadForPreview} className="space-y-4">
        <h2 className="text-base font-bold text-ink">1. Upload and check</h2>
        <label className="block space-y-1.5 text-sm font-semibold text-ink">
          <span>Order sheet</span>
          <input
            className="form-input"
            type="file"
            required
            accept=".xlsx,.xlsm,.csv,.xls"
            onChange={(event) => {
              setFile(event.target.files?.[0] || null);
              setPreview(null);
            }}
          />
        </label>
        <button type="submit" className="ui-btn-primary" disabled={isUploading || !file}>
          <Upload size={18} />
          {isUploading ? "Reading the file..." : "Check this file"}
        </button>
        <p className="text-xs text-muted">Nothing is saved at this step. You will see exactly what will be imported before anything is written.</p>
      </Card>

      {preview ? (
        <Card className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-base font-bold text-ink">2. Review {preview.fileName}</h2>
            <span className="text-xs text-muted">{preview.totalSheetRows} sheet row(s) read</span>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard label="Ready to import" value={summary.readyRows ?? 0} icon={CheckCircle2} tone="green" />
            <StatCard label="Already present" value={summary.duplicateRows ?? 0} tone="orange" />
            <StatCard label="Rows with problems" value={summary.failedRows ?? 0} icon={AlertTriangle} tone="red" />
            <StatCard label="Value" value={formatMoney(summary.totalValue)} tone="violet" />
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-xl border border-line bg-surface p-3">
              <div className="text-xs font-bold uppercase tracking-wider text-subtle">Columns matched</div>
              <ul className="mt-2 space-y-1 text-xs text-muted">
                {preview.detectedColumns.map((column) => (
                  <li key={column.header}>
                    <span className="font-semibold text-ink">{column.header}</span> → {column.mappedTo}
                  </li>
                ))}
              </ul>
            </div>
            {preview.unmappedColumns.length ? (
              <div className="rounded-xl border border-orange-200 bg-orange-50 p-3">
                <div className="text-xs font-bold uppercase tracking-wider text-orange-700">Columns ignored</div>
                <p className="mt-2 text-xs text-orange-700">
                  {preview.unmappedColumns.join(", ")} — rename these to one of the supported column names if you need them imported.
                </p>
              </div>
            ) : null}
          </div>

          {preview.errors.length ? (
            <div className="overflow-hidden rounded-xl border border-red-200">
              <div className="bg-red-50 px-4 py-2 text-xs font-bold uppercase tracking-wider text-red-700">Rows that cannot be imported</div>
              <table className="min-w-full divide-y divide-line text-sm">
                <tbody className="divide-y divide-line bg-white">
                  {preview.errors.slice(0, 20).map((rowError) => (
                    <tr key={`${rowError.row}-${rowError.field}`}>
                      <td className="w-16 px-4 py-2 font-bold text-ink">#{rowError.row}</td>
                      <td className="px-4 py-2 text-muted">{rowError.message}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}

          <div className="overflow-x-auto rounded-xl border border-line">
            <table className="min-w-full divide-y divide-line text-sm">
              <thead className="bg-surface text-left text-xs uppercase tracking-wider text-subtle">
                <tr>
                  <th className="px-3 py-2 font-bold">Order</th>
                  <th className="px-3 py-2 font-bold">Date</th>
                  <th className="px-3 py-2 font-bold">Customer</th>
                  <th className="px-3 py-2 font-bold">Items</th>
                  <th className="px-3 py-2 text-right font-bold">Total</th>
                  <th className="px-3 py-2 font-bold">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line bg-white">
                {preview.orders.slice(0, 50).map((row) => (
                  <tr key={`${row.rowNumber}-${row.orderNumber}`} className={row.isDuplicate ? "bg-orange-50" : ""}>
                    <td className="px-3 py-2 font-semibold text-ink">
                      {row.orderNumber || `Row ${row.rowNumber}`}
                      {row.isDuplicate ? <span className="mt-0.5 block text-[11px] font-normal text-orange-700">{row.duplicateReason}</span> : null}
                      {row.totalMismatch ? (
                        <span className="mt-0.5 block text-[11px] font-normal text-orange-700">
                          The stated total does not match the line amounts. The sheet total is used.
                        </span>
                      ) : null}
                    </td>
                    <td className="px-3 py-2 text-muted">{row.orderDate ? row.orderDate.slice(0, 10) : "Not given"}</td>
                    <td className="px-3 py-2 text-muted">
                      {row.customerName || "Not given"}
                      {row.customerPhone ? <span className="block text-[11px]">{row.customerPhone}</span> : null}
                    </td>
                    <td className="px-3 py-2 text-muted">{row.items.map((item) => `${item.name} ×${item.quantity}`).join(", ")}</td>
                    <td className="px-3 py-2 text-right font-bold text-ink">{formatMoney(row.totalAmount)}</td>
                    <td className="px-3 py-2 text-muted">{row.orderStatus || "completed"} / {row.paymentStatus || "unpaid"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {preview.orders.length > 50 ? (
            <p className="text-xs text-muted">Showing the first 50 of {preview.orders.length} orders. All of them will be imported.</p>
          ) : null}

          <label className="flex cursor-pointer items-center gap-2 text-sm font-semibold text-ink">
            <input type="checkbox" className="h-4 w-4 accent-brand" checked={skipDuplicates} onChange={(event) => setSkipDuplicates(event.target.checked)} />
            Skip orders that are already in my records ({summary.duplicateRows ?? 0} found)
          </label>

          <div className="flex flex-wrap gap-2">
            <button type="button" className="ui-btn-primary" disabled={isConfirming} onClick={confirmImport}>
              {isConfirming ? "Importing..." : `Import ${skipDuplicates ? summary.readyRows ?? 0 : preview.orders.length} order(s)`}
            </button>
            <button type="button" className="ui-btn-secondary" onClick={() => { setPreview(null); setFile(null); }}>
              Cancel
            </button>
          </div>
        </Card>
      ) : null}

      {result ? (
        <Card className="space-y-3 border-green-200 bg-green-50">
          <h2 className="flex items-center gap-2 text-base font-bold text-ink">
            <CheckCircle2 size={18} className="text-green-600" />
            Import finished
          </h2>
          <div className="grid gap-3 sm:grid-cols-4">
            <Metric label="Imported" value={result.import.successCount} />
            <Metric label="Skipped" value={result.import.skippedCount} />
            <Metric label="Failed" value={result.import.errorCount} />
            <Metric label="Value" value={formatMoney(result.import.importedValue)} />
          </div>
          <Link to="/dashboard/transactions?source=imported" className="ui-btn-primary w-fit">
            Open the order list
          </Link>
        </Card>
      ) : null}

      <Card>
        <h2 className="mb-3 flex items-center gap-2 text-base font-bold text-ink">
          <History size={18} className="text-brand" />
          Import history
        </h2>
        {history.length ? (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-line text-sm">
              <thead className="bg-surface text-left text-xs uppercase tracking-wider text-subtle">
                <tr>
                  <th className="px-3 py-2 font-bold">File</th>
                  <th className="px-3 py-2 font-bold">Imported by</th>
                  <th className="px-3 py-2 font-bold">When</th>
                  <th className="px-3 py-2 text-right font-bold">Rows</th>
                  <th className="px-3 py-2 text-right font-bold">Imported</th>
                  <th className="px-3 py-2 text-right font-bold">Skipped</th>
                  <th className="px-3 py-2 text-right font-bold">Failed</th>
                  <th className="px-3 py-2 font-bold">Report</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line bg-white">
                {history.map((run) => (
                  <tr key={run.id}>
                    <td className="px-3 py-2 font-semibold text-ink">{run.fileName}</td>
                    <td className="px-3 py-2 text-muted">{run.createdByName || "Owner"}</td>
                    <td className="px-3 py-2 text-muted">{formatDate(run.createdAt)}</td>
                    <td className="px-3 py-2 text-right text-muted">{run.totalRows}</td>
                    <td className="px-3 py-2 text-right font-bold text-green-700">{run.successCount}</td>
                    <td className="px-3 py-2 text-right text-muted">{run.skippedCount ?? 0}</td>
                    <td className="px-3 py-2 text-right font-bold text-red-600">{run.errorCount}</td>
                    <td className="px-3 py-2">
                      {run.errorCount || run.skippedCount ? (
                        <button
                          type="button"
                          className="inline-flex items-center gap-1 text-xs font-bold text-brand"
                          onClick={() => downloadOrderImportErrors(selectedTenant.id, run.id, `${run.fileName}-report.csv`)}
                        >
                          <Download size={14} />
                          Download
                        </button>
                      ) : (
                        <span className="text-xs text-subtle">Clean run</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-muted">No imports yet. Your first upload will be listed here with its full outcome.</p>
        )}
      </Card>
    </section>
  );
}

function Metric({ label, value }) {
  return (
    <div className="rounded-xl bg-white px-3 py-2">
      <div className="text-[10px] font-bold uppercase tracking-wider text-subtle">{label}</div>
      <div className="text-lg font-extrabold text-ink">{value}</div>
    </div>
  );
}
