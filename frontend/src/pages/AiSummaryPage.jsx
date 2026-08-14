import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { aiSummaryApi } from "../services/aiSummaryApi";
import { useToast } from "../contexts/ToastContext";
import LoadingSpinner from "../components/LoadingSpinner";
import ErrorAlert from "../components/ErrorAlert";
import EmptyState from "../components/EmptyState";
import PermissionGuard from "../components/PermissionGuard";

const TYPES = ["overall", "executive", "positive", "negative", "comparative", "periodic"];

const STATUS_BADGE = { draft: "secondary", approved: "success", rejected: "danger" };

function SummaryCard({ summary, onAction, expanded, onToggle }) {
  return (
    <div className="card mb-3">
      <div className="card-header d-flex justify-content-between align-items-center" role="button" onClick={onToggle}>
        <div>
          <span className={`badge text-bg-${STATUS_BADGE[summary.approvalStatus]} me-2`}>{summary.approvalStatus}</span>
          <span className="badge text-bg-dark me-2">AI/System Generated</span>
          <strong>{summary.summaryType}</strong>
          <span className="text-muted small ms-2">{summary.dateRangeStart} → {summary.dateRangeEnd}</span>
        </div>
        <span className="text-muted small">{new Date(summary.createdAt).toLocaleString()}</span>
      </div>
      {expanded && (
        <div className="card-body">
          <p className="text-muted small mb-2">Generation method: {summary.generationMethod || "deterministic_template"}</p>
          <p>{summary.sections?.overall}</p>
          <hr />
          <p className="mb-1"><strong>Sentiment:</strong> {summary.sections?.sentiment}</p>
          <p className="mb-1"><strong>Topics:</strong> {summary.sections?.topics}</p>
          <p className="mb-1"><strong>Aspects:</strong> {summary.sections?.aspects}</p>
          <p className="mb-1"><strong>Keywords:</strong> {summary.sections?.keywords}</p>
          <p className="mb-3"><strong>Recommendations:</strong> {summary.sections?.recommendations}</p>

          <PermissionGuard permission="generate_report">
            {summary.approvalStatus === "draft" && (
              <button className="btn btn-sm btn-outline-secondary me-2" onClick={() => onAction(summary, "submit")}>
                Submit for Review
              </button>
            )}
          </PermissionGuard>
          <PermissionGuard permission="approve_ai_output">
            {summary.approvalStatus === "draft" && (
              <>
                <button className="btn btn-sm btn-success me-2" onClick={() => onAction(summary, "approve")}>Approve</button>
                <button className="btn btn-sm btn-outline-danger" onClick={() => onAction(summary, "reject")}>Reject</button>
              </>
            )}
          </PermissionGuard>
        </div>
      )}
    </div>
  );
}

export default function AiSummaryPage() {
  const { projectId } = useParams();
  const { showToast } = useToast();
  const [summaries, setSummaries] = useState(null);
  const [error, setError] = useState(null);
  const [generating, setGenerating] = useState(false);
  const [summaryType, setSummaryType] = useState("overall");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [expandedId, setExpandedId] = useState(null);

  const load = () => {
    aiSummaryApi.list(projectId).then((r) => setSummaries(r.data.data.items)).catch(setError);
  };
  useEffect(load, [projectId]);

  const generate = async () => {
    if (!dateFrom || !dateTo) {
      setError({ message: "Select a date range first" });
      return;
    }
    setGenerating(true);
    try {
      const resp = await aiSummaryApi.generate(projectId, { summaryType, dateFrom, dateTo });
      showToast("Summary generated");
      setExpandedId(resp.data.data.id);
      load();
    } catch (err) {
      setError(err);
    } finally {
      setGenerating(false);
    }
  };

  const onAction = async (summary, action) => {
    try {
      if (action === "submit") await aiSummaryApi.submitForReview(summary.id);
      if (action === "approve") await aiSummaryApi.approve(summary.id);
      if (action === "reject") await aiSummaryApi.reject(summary.id);
      showToast("Summary updated");
      load();
    } catch (err) {
      setError(err);
    }
  };

  if (summaries === null && !error) return <LoadingSpinner />;

  const latest = summaries?.[0];

  return (
    <div>
      <h2 className="my-3">AI Summary</h2>
      <ErrorAlert error={error} onDismiss={() => setError(null)} />

      <PermissionGuard permission="generate_report">
        <div className="card p-3 mb-3 d-flex flex-row gap-2 align-items-end flex-wrap">
          <div>
            <label className="form-label small mb-0">Type</label>
            <select className="form-select form-select-sm" value={summaryType} onChange={(e) => setSummaryType(e.target.value)}>
              {TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div>
            <label className="form-label small mb-0">From</label>
            <input type="date" className="form-control form-control-sm" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </div>
          <div>
            <label className="form-label small mb-0">To</label>
            <input type="date" className="form-control form-control-sm" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </div>
          <button className="btn btn-primary" onClick={generate} disabled={generating}>
            {generating ? "Generating..." : "Generate Summary"}
          </button>
        </div>
      </PermissionGuard>

      {latest && (
        <>
          <h5>Latest Summary</h5>
          <SummaryCard
            summary={latest} onAction={onAction}
            expanded={expandedId === latest.id || expandedId === null}
            onToggle={() => setExpandedId(expandedId === latest.id ? "none" : latest.id)}
          />
        </>
      )}

      {summaries.length === 0 ? (
        <EmptyState title="No summaries yet" description="Generate the first AI summary for this project." />
      ) : (
        <>
          <h5 className="mt-4">Summary History</h5>
          {summaries.slice(1).map((s) => (
            <SummaryCard
              key={s.id} summary={s} onAction={onAction}
              expanded={expandedId === s.id}
              onToggle={() => setExpandedId(expandedId === s.id ? null : s.id)}
            />
          ))}
        </>
      )}
    </div>
  );
}
