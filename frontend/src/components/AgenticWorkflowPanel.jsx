import { useEffect, useState } from "react";
import { workflowApi } from "../services/workflowApi";
import { useToast } from "../contexts/ToastContext";
import PermissionGuard from "./PermissionGuard";

const WORKFLOW_TYPES = [
  ["FULL_ANALYSIS", "Full Analysis"],
  ["COLLECT_AND_ANALYSE", "Collect & Analyse"],
  ["REFRESH_ANALYSIS", "Refresh Analysis"],
  ["EXECUTIVE_BRIEF", "Executive Brief"],
  ["ALERT_RECHECK", "Alert Recheck"],
  ["REPORT_REFRESH", "Report Refresh"],
];

const STATUS_BADGE = {
  completed: "success", completed_with_warnings: "warning", failed: "danger",
  cancelled: "secondary", waiting_for_approval: "info", running: "primary", pending: "secondary",
};

const STEP_BADGE = {
  completed: "success", failed: "danger", skipped: "secondary", waiting_for_approval: "info",
};

function OptionsForm({ options, setOptions }) {
  const toggle = (key) => setOptions((o) => ({ ...o, [key]: !o[key] }));
  return (
    <div className="d-flex flex-column gap-1 mb-3">
      {[
        ["collectNewData", "Collect new data"],
        ["runSentiment", "Sentiment analysis"],
        ["runTopics", "Topic analysis"],
        ["runAspects", "Aspect analysis"],
        ["generateSummary", "Generate summary"],
        ["generateRecommendations", "Generate recommendations"],
        ["evaluateAlerts", "Evaluate alerts"],
        ["generateReport", "Generate report"],
      ].map(([key, label]) => (
        <div className="form-check" key={key}>
          <input
            className="form-check-input" type="checkbox" id={`wf-opt-${key}`}
            checked={!!options[key]} onChange={() => toggle(key)}
          />
          <label className="form-check-label" htmlFor={`wf-opt-${key}`}>{label}</label>
        </div>
      ))}
    </div>
  );
}

function StepList({ steps }) {
  if (!steps?.length) return <p className="text-muted small mb-0">No steps recorded.</p>;
  return (
    <ul className="list-group list-group-flush">
      {steps.map((s) => (
        <li key={s.agent} className="list-group-item d-flex justify-content-between align-items-start">
          <div>
            <strong>{s.agent}</strong>
            <div className="small text-muted">{s.message}</div>
            {s.warnings?.length > 0 && (
              <ul className="small text-warning mb-0">
                {s.warnings.map((w, i) => <li key={i}>{w}</li>)}
              </ul>
            )}
          </div>
          <span className={`badge text-bg-${STEP_BADGE[s.status] || "secondary"}`}>{s.status}</span>
        </li>
      ))}
    </ul>
  );
}

function WorkflowCard({ workflow, onChanged }) {
  const { showToast } = useToast();
  const [busy, setBusy] = useState(null);
  const [rejectReason, setRejectReason] = useState("");
  const [showReject, setShowReject] = useState(false);

  const act = async (action) => {
    setBusy(action);
    try {
      if (action === "approve") await workflowApi.approve(workflow.id);
      if (action === "resume") await workflowApi.resume(workflow.id);
      if (action === "cancel") await workflowApi.cancel(workflow.id);
      if (action === "reject") await workflowApi.reject(workflow.id, rejectReason);
      showToast("Workflow updated");
      setShowReject(false);
      onChanged();
    } catch (err) {
      showToast(err?.response?.data?.error?.message || "Action failed");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="card mb-2">
      <div className="card-header d-flex justify-content-between align-items-center">
        <div>
          <span className="badge text-bg-dark me-2">Agent-assisted workflow</span>
          <strong>{workflow.workflowType}</strong>
          <span className="text-muted small ms-2">
            started by {workflow.startedBy?.slice(0, 8)} at {new Date(workflow.startedAt).toLocaleString()}
          </span>
        </div>
        <span className={`badge text-bg-${STATUS_BADGE[workflow.status] || "secondary"}`}>{workflow.status}</span>
      </div>
      <div className="card-body">
        <StepList steps={workflow.steps} />
        {workflow.warnings?.length > 0 && (
          <div className="alert alert-warning small mt-2 mb-0">
            {workflow.warnings.map((w, i) => <div key={i}>{w}</div>)}
          </div>
        )}

        {workflow.status === "waiting_for_approval" && (
          <div className="border rounded p-3 mt-3 bg-light">
            <h6>Approval required</h6>
            <p className="small text-muted">
              A step in this workflow generated content that requires human review before continuing
              (see the step list above for what was generated).
            </p>
            <PermissionGuard permission="approve_ai_output" fallback={<p className="small text-muted mb-0">You do not have permission to approve this.</p>}>
              {!showReject ? (
                <div className="d-flex gap-2">
                  <button className="btn btn-sm btn-success" disabled={!!busy} onClick={() => act("approve")}>
                    {busy === "approve" ? "Approving..." : "Approve"}
                  </button>
                  <button className="btn btn-sm btn-outline-primary" disabled={!!busy} onClick={() => act("resume")}>
                    {busy === "resume" ? "Resuming..." : "Resume Workflow"}
                  </button>
                  <button className="btn btn-sm btn-outline-danger" disabled={!!busy} onClick={() => setShowReject(true)}>
                    Reject
                  </button>
                  <button className="btn btn-sm btn-outline-secondary" disabled={!!busy} onClick={() => act("cancel")}>
                    Cancel
                  </button>
                </div>
              ) : (
                <div className="d-flex gap-2">
                  <input
                    className="form-control form-control-sm" placeholder="Reason (optional)"
                    value={rejectReason} onChange={(e) => setRejectReason(e.target.value)}
                  />
                  <button className="btn btn-sm btn-danger" disabled={!!busy} onClick={() => act("reject")}>Confirm Reject</button>
                  <button className="btn btn-sm btn-outline-secondary" onClick={() => setShowReject(false)}>Back</button>
                </div>
              )}
            </PermissionGuard>
          </div>
        )}
      </div>
    </div>
  );
}

export default function AgenticWorkflowPanel({ projectId }) {
  const { showToast } = useToast();
  const [workflows, setWorkflows] = useState(null);
  const [showModal, setShowModal] = useState(false);
  const [workflowType, setWorkflowType] = useState("FULL_ANALYSIS");
  const [options, setOptions] = useState({
    runSentiment: true, runTopics: true, runAspects: true,
    generateSummary: true, generateRecommendations: true, evaluateAlerts: true,
  });
  const [starting, setStarting] = useState(false);
  const [showAll, setShowAll] = useState(false);

  const load = () => {
    workflowApi.list(projectId).then((r) => setWorkflows(r.data.data.items)).catch(() => setWorkflows([]));
  };
  useEffect(load, [projectId]);

  const start = async () => {
    setStarting(true);
    try {
      const idempotencyKey = `ui-${Date.now()}-${Math.random().toString(36).slice(2)}`;
      await workflowApi.start(projectId, { workflowType, options, idempotencyKey });
      showToast("Workflow started");
      setShowModal(false);
      load();
    } catch (err) {
      showToast(err?.response?.data?.error?.message || "Could not start workflow");
    } finally {
      setStarting(false);
    }
  };

  if (workflows === null) return null;
  const latest = workflows[0];
  const history = workflows.slice(1, showAll ? undefined : 4);

  return (
    <div className="mb-3">
      <div className="d-flex justify-content-between align-items-center mb-2">
        <h5 className="mb-0">Agentic Analysis</h5>
        <PermissionGuard permission="view_reviews">
          <button className="btn btn-primary btn-sm" onClick={() => setShowModal(true)}>Run Agentic Analysis</button>
        </PermissionGuard>
      </div>

      {latest ? <WorkflowCard workflow={latest} onChanged={load} /> : (
        <p className="text-muted small">No workflows have been run yet for this project.</p>
      )}

      {history.length > 0 && (
        <>
          <button className="btn btn-sm btn-link px-0" onClick={() => setShowAll((s) => !s)}>
            {showAll ? "Hide" : "Show"} earlier workflows ({workflows.length - 1})
          </button>
          {showAll && history.map((w) => <WorkflowCard key={w.id} workflow={w} onChanged={load} />)}
        </>
      )}

      {showModal && (
        <div className="modal d-block" tabIndex={-1} style={{ background: "rgba(0,0,0,0.5)" }}>
          <div className="modal-dialog">
            <div className="modal-content">
              <div className="modal-header">
                <h5 className="modal-title">Run Agentic Analysis</h5>
                <button type="button" className="btn-close" onClick={() => setShowModal(false)} />
              </div>
              <div className="modal-body">
                <label className="form-label">Workflow type</label>
                <select className="form-select mb-3" value={workflowType} onChange={(e) => setWorkflowType(e.target.value)}>
                  {WORKFLOW_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
                <OptionsForm options={options} setOptions={setOptions} />
                <p className="small text-muted mb-0">
                  Steps you lack permission for (e.g. Report without report-generation access) are
                  skipped automatically, not denied outright — the rest of the workflow still runs.
                </p>
              </div>
              <div className="modal-footer">
                <button className="btn btn-secondary" onClick={() => setShowModal(false)}>Cancel</button>
                <button className="btn btn-primary" disabled={starting} onClick={start}>
                  {starting ? "Starting..." : "Run"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
