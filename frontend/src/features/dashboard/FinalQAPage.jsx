import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, ClipboardCheck, PlayCircle, RefreshCw, Route, Terminal, XCircle } from "lucide-react";
import { useMemo, useState } from "react";

import { useTenant } from "../../context/TenantContext.jsx";
import { getFinalQaChecklist, recordFinalQaDemoRun } from "../../services/qaApi.js";

const badgeStyles = {
  pass: "border-emerald-200 bg-emerald-50 text-emerald-800",
  warn: "border-amber-200 bg-amber-50 text-amber-800",
  fail: "border-red-200 bg-red-50 text-red-800",
};

function StatusIcon({ status }) {
  if (status === "pass") return <CheckCircle2 className="h-5 w-5" />;
  if (status === "fail") return <XCircle className="h-5 w-5" />;
  return <AlertTriangle className="h-5 w-5" />;
}

function StatusBadge({ status }) {
  return <span className={`rounded-full border px-2 py-1 text-xs font-bold uppercase ${badgeStyles[status] || badgeStyles.warn}`}>{status}</span>;
}

function scoreColor(status) {
  if (status === "demo_ready") return "text-emerald-700";
  if (status === "needs_fixes") return "text-red-700";
  return "text-amber-700";
}

export function FinalQAPage() {
  const queryClient = useQueryClient();
  const { selectedTenant } = useTenant();
  const [result, setResult] = useState("pass");
  const [notes, setNotes] = useState("");
  const [reviewerName, setReviewerName] = useState("");
  const [checkedSteps, setCheckedSteps] = useState([]);

  const tenantId = selectedTenant?.id;
  const qaQuery = useQuery({
    queryKey: ["final-qa", tenantId],
    queryFn: () => getFinalQaChecklist(tenantId),
    enabled: Boolean(tenantId),
    refetchInterval: 60000,
  });

  const recordMutation = useMutation({
    mutationFn: () => recordFinalQaDemoRun(tenantId, { result, notes, reviewerName, checkedSteps }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["final-qa", tenantId] });
      setNotes("");
    },
  });

  const report = qaQuery.data;
  const summary = report?.summary;
  const checks = report?.checks || [];
  const demoScript = report?.demoScript || [];
  const commands = report?.commands || [];
  const blockingGaps = summary?.blockingGaps || [];
  const warnings = summary?.warnings || [];
  const nextActions = summary?.nextActions || [];

  const checkedStepSet = useMemo(() => new Set(checkedSteps), [checkedSteps]);

  function toggleStep(step) {
    setCheckedSteps((current) => (current.includes(step) ? current.filter((item) => item !== step) : [...current, step]));
  }

  if (!selectedTenant) {
    return <div className="rounded-2xl border border-line bg-white p-6 text-sm text-muted">Create or select a business first to run final QA.</div>;
  }

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-line bg-white p-6 shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full bg-primary/10 px-3 py-1 text-xs font-bold uppercase tracking-wide text-primary">
              <ClipboardCheck className="h-4 w-4" /> Phase 30
            </div>
            <h1 className="mt-3 text-2xl font-bold text-ink">Final full-system QA and supervisor demo polish</h1>
            <p className="mt-2 max-w-3xl text-sm text-muted">
              This page is for final project testing and supervisor demo readiness, not normal daily business use. It checks whether the selected business is ready for demo by verifying profile, launch wizard, catalog, RAG, customer chatbot ordering, WhatsApp mock/real setup, stock/payments, owner assistant, reports, and phone OTP flow.
            </p>
          </div>
          <button
            type="button"
            onClick={() => qaQuery.refetch()}
            className="inline-flex items-center justify-center gap-2 rounded-lg border border-line px-4 py-2 text-sm font-semibold text-ink transition hover:bg-surface"
          >
            <RefreshCw className="h-4 w-4" /> Refresh QA
          </button>
        </div>
      </div>

      {qaQuery.isLoading ? (
        <div className="rounded-2xl border border-line bg-white p-6 text-sm text-muted">Running final QA checklist...</div>
      ) : qaQuery.isError ? (
        <div className="rounded-2xl border border-red-200 bg-red-50 p-6 text-sm text-red-700">Could not load final QA checklist. Make sure the backend is running and you are logged in as the owner.</div>
      ) : (
        <>
          <div className="grid gap-4 lg:grid-cols-4">
            <div className="rounded-2xl border border-line bg-white p-5 shadow-sm lg:col-span-1">
              <div className="text-xs font-semibold uppercase tracking-wide text-muted">Demo readiness</div>
              <div className="mt-1 text-xs text-muted">PASS = working, WARN = usable but needs attention, FAIL = must fix before demo.</div>
              <div className={`mt-2 text-2xl font-bold capitalize ${scoreColor(summary?.status)}`}>{String(summary?.status || "loading").replaceAll("_", " ")}</div>
              <div className="mt-2 text-sm text-muted">Required: {summary?.requiredPercent ?? 0}% · Overall: {summary?.percent ?? 0}%</div>
            </div>
            {Object.entries(summary?.totals || {}).map(([key, value]) => (
              <div key={key} className="rounded-2xl border border-line bg-white p-5 shadow-sm">
                <div className="text-xs font-semibold uppercase tracking-wide text-muted">{key}</div>
                <div className="mt-2 text-3xl font-bold text-ink">{value}</div>
              </div>
            ))}
          </div>

          {blockingGaps.length || warnings.length ? (
            <div className="grid gap-4 lg:grid-cols-2">
              <div className="rounded-2xl border border-red-200 bg-red-50 p-5">
                <h2 className="font-bold text-red-800">Blocking gaps</h2>
                {blockingGaps.length ? (
                  <ul className="mt-3 space-y-2 text-sm text-red-700">
                    {blockingGaps.map((gap) => <li key={gap.code}>• {gap.title}: {gap.description}</li>)}
                  </ul>
                ) : <p className="mt-3 text-sm text-red-700">No blocking gaps detected.</p>}
              </div>
              <div className="rounded-2xl border border-amber-200 bg-amber-50 p-5">
                <h2 className="font-bold text-amber-800">Warnings</h2>
                <p className="mt-1 text-xs text-amber-700">Warnings usually mean the project can demo, but you should improve that area before final submission.</p>
                {warnings.length ? (
                  <ul className="mt-3 space-y-2 text-sm text-amber-700">
                    {warnings.slice(0, 6).map((warning) => <li key={warning.code}>• {warning.title}: {warning.description}</li>)}
                  </ul>
                ) : <p className="mt-3 text-sm text-amber-700">No warnings detected.</p>}
              </div>
            </div>
          ) : null}

          {nextActions.length ? (
            <div className="rounded-2xl border border-blue-200 bg-blue-50 p-5">
              <h2 className="font-bold text-blue-900">Recommended next actions</h2>
              <div className="mt-3 grid gap-2">
                {nextActions.map((action) => (
                  <div key={action.code} className="rounded-xl bg-white/70 p-3 text-sm text-blue-900">
                    <div className="font-semibold">{action.title}</div>
                    <div className="mt-1 text-blue-800">{action.action}</div>
                    {action.route ? <div className="mt-1 text-xs font-bold uppercase tracking-wide text-blue-700">{action.route}</div> : null}
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          <div className="rounded-2xl border border-line bg-white p-6 shadow-sm">
            <h2 className="text-lg font-bold text-ink">System QA checklist</h2>
            <div className="mt-4 grid gap-3">
              {checks.map((check) => (
                <div key={check.code} className={`rounded-xl border p-4 ${badgeStyles[check.status] || badgeStyles.warn}`}>
                  <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                    <div className="flex items-start gap-3">
                      <StatusIcon status={check.status} />
                      <div>
                        <div className="font-semibold">{check.title}</div>
                        <div className="mt-1 text-sm opacity-90">{check.description}</div>
                        {check.route ? <div className="mt-2 text-xs font-semibold">Fix/Test route: {check.route}</div> : null}
                        {Object.keys(check.evidence || {}).length ? (
                          <div className="mt-2 grid gap-1 text-xs opacity-90 md:grid-cols-2">
                            {Object.entries(check.evidence).slice(0, 6).map(([key, value]) => (
                              <div key={key}>
                                <span className="font-semibold">{key}:</span> {typeof value === "object" ? JSON.stringify(value) : String(value)}
                              </div>
                            ))}
                          </div>
                        ) : null}
                      </div>
                    </div>
                    <StatusBadge status={check.status} />
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-2xl border border-line bg-white p-6 shadow-sm">
            <div className="flex items-center gap-2">
              <Route className="h-5 w-5 text-primary" />
              <h2 className="text-lg font-bold text-ink">Supervisor demo script</h2>
            </div>
            <div className="mt-4 grid gap-3">
              {demoScript.map((step) => (
                <label key={step.step} className="flex cursor-pointer gap-3 rounded-xl border border-line p-4 transition hover:bg-surface">
                  <input
                    type="checkbox"
                    className="mt-1 h-4 w-4"
                    checked={checkedStepSet.has(step.step)}
                    onChange={() => toggleStep(step.step)}
                  />
                  <div>
                    <div className="text-sm font-bold text-ink">Step {step.step}: {step.title}</div>
                    <div className="mt-1 text-sm text-muted">{step.goal}</div>
                    <div className="mt-2 text-xs font-semibold text-primary">{step.route}</div>
                    <div className="mt-1 text-xs text-muted">Expected: {step.expectedResult}</div>
                  </div>
                </label>
              ))}
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-2xl border border-line bg-white p-6 shadow-sm">
              <div className="flex items-center gap-2">
                <Terminal className="h-5 w-5 text-primary" />
                <h2 className="text-lg font-bold text-ink">Final verification commands</h2>
              </div>
              <div className="mt-4 space-y-3">
                {commands.map((item) => (
                  <div key={item.name} className="rounded-xl bg-surface p-4">
                    <div className="font-semibold text-ink">{item.name}</div>
                    <code className="mt-2 block overflow-x-auto rounded-md bg-ink px-3 py-2 text-xs text-white">{item.command}</code>
                    <p className="mt-2 text-xs text-muted">{item.purpose}</p>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-2xl border border-line bg-white p-6 shadow-sm">
              <div className="flex items-center gap-2">
                <PlayCircle className="h-5 w-5 text-primary" />
                <h2 className="text-lg font-bold text-ink">Record manual demo run</h2>
              </div>
              {report?.latestDemoRun ? (
                <div className="mt-4 rounded-lg bg-surface p-3 text-sm text-muted">
                  Last run: <span className="font-semibold text-ink">{report.latestDemoRun.result}</span> by {report.latestDemoRun.reviewerName || "Unknown"}
                  {report.latestDemoRun.demoCoverage ? (
                    <div className="mt-1 text-xs">
                      Demo script coverage: {report.latestDemoRun.demoCoverage.checkedCount}/{report.latestDemoRun.demoCoverage.totalSteps} steps ({report.latestDemoRun.demoCoverage.percent}%)
                    </div>
                  ) : null}
                </div>
              ) : null}
              <div className="mt-4 space-y-3">
                <label className="block text-sm font-semibold text-ink">
                  Result
                  <select value={result} onChange={(event) => setResult(event.target.value)} className="mt-1 w-full rounded-md border border-line px-3 py-2 text-sm">
                    <option value="pass">Pass</option>
                    <option value="warn">Pass with warnings</option>
                    <option value="fail">Fail / needs fixes</option>
                  </select>
                </label>
                <label className="block text-sm font-semibold text-ink">
                  Reviewer name
                  <input value={reviewerName} onChange={(event) => setReviewerName(event.target.value)} className="mt-1 w-full rounded-md border border-line px-3 py-2 text-sm" placeholder="Ahsan / Supervisor / Tester" />
                </label>
                <label className="block text-sm font-semibold text-ink">
                  Notes
                  <textarea value={notes} onChange={(event) => setNotes(event.target.value)} className="mt-1 min-h-28 w-full rounded-md border border-line px-3 py-2 text-sm" placeholder="Write what was tested and any remaining fixes..." />
                </label>
                <button
                  type="button"
                  disabled={recordMutation.isPending}
                  onClick={() => recordMutation.mutate()}
                  className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white transition hover:bg-primary-dark disabled:opacity-60"
                >
                  <ClipboardCheck className="h-4 w-4" /> {recordMutation.isPending ? "Saving..." : "Save demo QA run"}
                </button>
                {recordMutation.isError ? <div className="text-sm text-red-600">Could not save demo run.</div> : null}
                {recordMutation.isSuccess ? <div className="text-sm text-emerald-700">Demo QA run saved.</div> : null}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
