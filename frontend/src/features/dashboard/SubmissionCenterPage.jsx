import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, CheckCircle2, Download, FileCheck2, PackageCheck, RefreshCw, ShieldAlert, XCircle } from "lucide-react";
import { useMemo, useState } from "react";

import { useTenant } from "../../context/TenantContext.jsx";
import { getSubmissionExport, getSubmissionPackage, recordSubmissionSignoff } from "../../services/submissionApi.js";

const badgeStyles = {
  pass: "border-emerald-200 bg-emerald-50 text-emerald-800",
  warn: "border-amber-200 bg-amber-50 text-amber-800",
  fail: "border-red-200 bg-red-50 text-red-800",
  ready: "border-emerald-200 bg-emerald-50 text-emerald-800",
  ready_with_notes: "border-amber-200 bg-amber-50 text-amber-800",
  blocked: "border-red-200 bg-red-50 text-red-800",
};

function StatusBadge({ status }) {
  return <span className={`rounded-full border px-2 py-1 text-xs font-bold uppercase ${badgeStyles[status] || badgeStyles.warn}`}>{String(status || "warn").replaceAll("_", " ")}</span>;
}

function statusText(status) {
  return String(status || "loading").replaceAll("_", " ");
}

function downloadJson(filename, data) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export function SubmissionCenterPage() {
  const queryClient = useQueryClient();
  const { selectedTenant } = useTenant();
  const tenantId = selectedTenant?.id;
  const [status, setStatus] = useState("ready");
  const [reviewerName, setReviewerName] = useState("");
  const [notes, setNotes] = useState("");
  const [includedArtifacts, setIncludedArtifacts] = useState(["latest_zip", "proposal_pdf", "demo_guide", "env_example", "seed_demo_data"]);

  const packageQuery = useQuery({
    queryKey: ["submission-package", tenantId],
    queryFn: () => getSubmissionPackage(tenantId),
    enabled: Boolean(tenantId),
    refetchInterval: 60000,
  });

  const signoffMutation = useMutation({
    mutationFn: () => recordSubmissionSignoff(tenantId, { status, reviewerName, notes, includedArtifacts }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["submission-package", tenantId] });
      setNotes("");
    },
  });

  const exportMutation = useMutation({
    mutationFn: () => getSubmissionExport(tenantId),
    onSuccess: (data) => {
      const slug = selectedTenant?.slug || "tenant";
      downloadJson(`bizxusai-${slug}-submission-snapshot.json`, data);
    },
  });

  const data = packageQuery.data;
  const summary = data?.summary || {};
  const artifactChecklist = data?.artifactChecklist || [];
  const includedSet = useMemo(() => new Set(includedArtifacts), [includedArtifacts]);
  const artifactSummary = summary.artifactSummary || {};
  const requiredArtifacts = useMemo(() => artifactChecklist.filter((artifact) => artifact.required).map((artifact) => artifact.code), [artifactChecklist]);
  const missingRequiredArtifacts = requiredArtifacts.filter((code) => !includedSet.has(code));
  const canSignOffReady = status === "blocked" || missingRequiredArtifacts.length === 0;

  function toggleArtifact(code) {
    setIncludedArtifacts((current) => (current.includes(code) ? current.filter((item) => item !== code) : [...current, code]));
  }

  if (!selectedTenant) {
    return <div className="rounded-2xl border border-line bg-white p-6 text-sm text-muted">Create or select a business first to prepare the final submission package.</div>;
  }

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-line bg-white p-6 shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full bg-primary/10 px-3 py-1 text-xs font-bold uppercase tracking-wide text-primary">
              <PackageCheck className="h-4 w-4" /> Phase 31
            </div>
            <h1 className="mt-3 text-2xl font-bold text-ink">Submission center and evidence pack</h1>
            <p className="mt-2 max-w-3xl text-sm text-muted">
              Use this page as the last step before submission. It maps the proposal requirements to implemented phases,
              lists clean packaging rules, records final sign-off, and exports a safe tenant evidence snapshot.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => packageQuery.refetch()}
              className="inline-flex items-center justify-center gap-2 rounded-lg border border-line px-4 py-2 text-sm font-semibold text-ink transition hover:bg-surface"
            >
              <RefreshCw className="h-4 w-4" /> Refresh
            </button>
            <button
              type="button"
              disabled={exportMutation.isPending}
              onClick={() => exportMutation.mutate()}
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white transition hover:bg-primary-dark disabled:opacity-60"
            >
              <Download className="h-4 w-4" /> {exportMutation.isPending ? "Preparing..." : "Export evidence JSON"}
            </button>
          </div>
        </div>
      </div>

      {packageQuery.isLoading ? (
        <div className="rounded-2xl border border-line bg-white p-6 text-sm text-muted">Preparing submission package...</div>
      ) : packageQuery.isError ? (
        <div className="rounded-2xl border border-red-200 bg-red-50 p-6 text-sm text-red-700">Could not load the submission package. Make sure the backend is running and you are logged in as the owner.</div>
      ) : (
        <>
          <div className="grid gap-4 lg:grid-cols-4">
            <div className="rounded-2xl border border-line bg-white p-5 shadow-sm lg:col-span-1">
              <div className="text-xs font-semibold uppercase tracking-wide text-muted">Submission status</div>
              <div className="mt-2 text-xl font-bold capitalize text-ink">{statusText(summary.status)}</div>
              <div className="mt-3 text-sm text-muted">Required QA: {summary.requiredPercent ?? 0}% · Overall QA: {summary.overallPercent ?? 0}%</div>
            </div>
            <div className="rounded-2xl border border-line bg-white p-5 shadow-sm">
              <div className="text-xs font-semibold uppercase tracking-wide text-muted">Blocking gaps</div>
              <div className="mt-2 text-3xl font-bold text-ink">{summary.blockingCount ?? 0}</div>
            </div>
            <div className="rounded-2xl border border-line bg-white p-5 shadow-sm">
              <div className="text-xs font-semibold uppercase tracking-wide text-muted">Warnings</div>
              <div className="mt-2 text-3xl font-bold text-ink">{summary.warningCount ?? 0}</div>
            </div>
            <div className="rounded-2xl border border-line bg-white p-5 shadow-sm">
              <div className="text-xs font-semibold uppercase tracking-wide text-muted">Sign-off</div>
              <div className="mt-2 text-xl font-bold capitalize text-ink">{statusText(summary.latestSignoffStatus)}</div>
              <div className="mt-3 text-sm text-muted">
                Artifacts: {artifactSummary.includedCount ?? includedArtifacts.length}/{artifactSummary.requiredCount ?? requiredArtifacts.length} required
              </div>
            </div>
          </div>

          <div className="rounded-2xl border border-line bg-white p-6 shadow-sm">
            <div className="flex items-center gap-2">
              <FileCheck2 className="h-5 w-5 text-primary" />
              <h2 className="text-lg font-bold text-ink">Proposal-to-code traceability</h2>
            </div>
            <div className="mt-4 overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead className="text-xs uppercase tracking-wide text-muted">
                  <tr>
                    <th className="border-b border-line py-2 pr-4">Proposal area</th>
                    <th className="border-b border-line py-2 pr-4">Implemented by</th>
                    <th className="border-b border-line py-2 pr-4">Evidence route</th>
                    <th className="border-b border-line py-2">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {(data?.proposalTraceability || []).map((row) => (
                    <tr key={row.proposalArea}>
                      <td className="border-b border-line py-3 pr-4 font-semibold text-ink">{row.proposalArea}</td>
                      <td className="border-b border-line py-3 pr-4 text-muted">{row.implementedBy}</td>
                      <td className="border-b border-line py-3 pr-4 text-primary">{row.evidenceRoute}</td>
                      <td className="border-b border-line py-3"><StatusBadge status={row.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-2xl border border-line bg-white p-6 shadow-sm">
              <div className="flex items-center gap-2">
                <Archive className="h-5 w-5 text-primary" />
                <h2 className="text-lg font-bold text-ink">Final artifact checklist</h2>
              </div>
              <div className="mt-4 space-y-3">
                {artifactChecklist.map((artifact) => (
                  <label key={artifact.code} className="flex cursor-pointer gap-3 rounded-xl border border-line p-4 transition hover:bg-surface">
                    <input
                      type="checkbox"
                      className="mt-1 h-4 w-4"
                      checked={includedSet.has(artifact.code)}
                      onChange={() => toggleArtifact(artifact.code)}
                    />
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-semibold text-ink">{artifact.title}</span>
                        {artifact.required ? <span className="rounded-full bg-red-50 px-2 py-1 text-xs font-bold text-red-700">Required</span> : <span className="rounded-full bg-surface px-2 py-1 text-xs font-bold text-muted">Optional</span>}
                      </div>
                      <div className="mt-1 text-sm text-muted">{artifact.description}</div>
                    </div>
                  </label>
                ))}
                {missingRequiredArtifacts.length ? (
                  <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
                    Missing required artifacts before ready sign-off: {missingRequiredArtifacts.join(", ")}.
                  </div>
                ) : (
                  <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800">
                    Required artifacts are selected for sign-off.
                  </div>
                )}
              </div>
            </div>

            <div className="space-y-4">
              <div className="rounded-2xl border border-line bg-white p-6 shadow-sm">
                <h2 className="text-lg font-bold text-ink">Submit these</h2>
                <div className="mt-4 grid gap-2 text-sm text-muted">
                  {(data?.filesToSubmit || []).map((item) => <code key={item} className="rounded-md bg-surface px-3 py-2">{item}</code>)}
                </div>
              </div>
              <div className="rounded-2xl border border-amber-200 bg-amber-50 p-6 shadow-sm">
                <div className="flex items-center gap-2">
                  <ShieldAlert className="h-5 w-5" />
                  <h2 className="text-lg font-bold">Never submit these</h2>
                </div>
                <div className="mt-4 grid gap-2 text-sm">
                  {(data?.filesToExclude || []).map((item) => <code key={item} className="rounded-md bg-white/70 px-3 py-2">{item}</code>)}
                </div>
              </div>
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-2xl border border-line bg-white p-6 shadow-sm">
              <h2 className="text-lg font-bold text-ink">Tenant evidence counts</h2>
              <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
                {Object.entries(data?.counts || {}).map(([key, value]) => (
                  <div key={key} className="rounded-lg bg-surface p-3">
                    <dt className="text-xs font-semibold uppercase tracking-wide text-muted">{key}</dt>
                    <dd className="mt-1 text-xl font-bold text-ink">{value}</dd>
                  </div>
                ))}
              </dl>
            </div>

            <div className="rounded-2xl border border-line bg-white p-6 shadow-sm">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-5 w-5 text-primary" />
                <h2 className="text-lg font-bold text-ink">Final sign-off</h2>
              </div>
              {data?.latestSignoff ? (
                <div className="mt-4 rounded-lg bg-surface p-3 text-sm text-muted">
                  Last sign-off: <span className="font-semibold text-ink">{statusText(data.latestSignoff.status)}</span> by {data.latestSignoff.reviewerName || "Unknown"}
                </div>
              ) : null}
              <div className="mt-4 space-y-3">
                <label className="block text-sm font-semibold text-ink">
                  Status
                  <select value={status} onChange={(event) => setStatus(event.target.value)} className="mt-1 w-full rounded-md border border-line px-3 py-2 text-sm">
                    <option value="ready">Ready</option>
                    <option value="ready_with_notes">Ready with notes</option>
                    <option value="blocked">Blocked</option>
                  </select>
                </label>
                <label className="block text-sm font-semibold text-ink">
                  Reviewer name
                  <input value={reviewerName} onChange={(event) => setReviewerName(event.target.value)} className="mt-1 w-full rounded-md border border-line px-3 py-2 text-sm" placeholder="Ahsan / Supervisor / Tester" />
                </label>
                <label className="block text-sm font-semibold text-ink">
                  Notes
                  <textarea value={notes} onChange={(event) => setNotes(event.target.value)} className="mt-1 min-h-28 w-full rounded-md border border-line px-3 py-2 text-sm" placeholder="Final submission notes, known warnings, or demo instructions..." />
                </label>
                <button
                  type="button"
                  disabled={signoffMutation.isPending || !canSignOffReady}
                  onClick={() => signoffMutation.mutate()}
                  className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white transition hover:bg-primary-dark disabled:opacity-60"
                >
                  <FileCheck2 className="h-4 w-4" /> {signoffMutation.isPending ? "Saving..." : "Save final sign-off"}
                </button>
                {!canSignOffReady ? <div className="text-sm text-amber-700">Select all required artifacts, or choose Blocked if submission cannot proceed.</div> : null}
                {signoffMutation.isError ? <div className="text-sm text-red-600">Could not save final sign-off.</div> : null}
                {signoffMutation.isSuccess ? <div className="text-sm text-emerald-700">Final sign-off saved.</div> : null}
              </div>
            </div>
          </div>

          {exportMutation.isError ? <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">Could not export evidence JSON.</div> : null}
        </>
      )}
    </div>
  );
}
