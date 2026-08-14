import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { analysisApi } from "../services/analysisApi";
import { recommendationApi } from "../services/recommendationApi";
import { useToast } from "../contexts/ToastContext";
import LoadingSpinner from "../components/LoadingSpinner";
import ErrorAlert from "../components/ErrorAlert";
import EmptyState from "../components/EmptyState";
import DataTable from "../components/DataTable";
import AnalysisFilters from "../components/AnalysisFilters";
import RoleGuard from "../components/RoleGuard";
import PermissionGuard from "../components/PermissionGuard";
import ConfirmationModal from "../components/ConfirmationModal";

function AspectTab({ projectId }) {
  const { showToast } = useToast();
  const [aspects, setAspects] = useState(null);
  const [error, setError] = useState(null);
  const [running, setRunning] = useState(false);
  const [filters, setFilters] = useState({});
  const [sortBy, setSortBy] = useState("frequency");
  const [selected, setSelected] = useState(null);
  const [selectedReviews, setSelectedReviews] = useState(null);

  const load = () => {
    analysisApi.listAspects(projectId, filters).then((r) => setAspects(r.data.data.items)).catch(setError);
  };
  useEffect(load, [projectId, filters]);

  const run = async (reanalyse) => {
    setRunning(true);
    try {
      if (reanalyse) await analysisApi.reanalyseAspects(projectId);
      else await analysisApi.runAspects(projectId);
      showToast("Aspect analysis complete");
      load();
    } catch (err) {
      setError(err);
    } finally {
      setRunning(false);
    }
  };

  const openAspect = async (aspectId) => {
    try {
      const [detail, reviews] = await Promise.all([
        analysisApi.getAspect(projectId, aspectId, filters),
        analysisApi.getAspectReviews(projectId, aspectId, filters),
      ]);
      setSelected(detail.data.data);
      setSelectedReviews(reviews.data.data.items);
    } catch (err) {
      setError(err);
    }
  };

  if (aspects === null && !error) return <LoadingSpinner />;

  const sorted = [...(aspects || [])].sort((a, b) =>
    sortBy === "negativity" ? b.negativePercentage - a.negativePercentage : b.frequency - a.frequency
  );

  return (
    <div>
      <div className="d-flex justify-content-between align-items-center my-3">
        <div className="btn-group btn-group-sm">
          <button className={`btn btn-outline-secondary ${sortBy === "frequency" ? "active" : ""}`} onClick={() => setSortBy("frequency")}>
            Sort by frequency
          </button>
          <button className={`btn btn-outline-secondary ${sortBy === "negativity" ? "active" : ""}`} onClick={() => setSortBy("negativity")}>
            Sort by negativity
          </button>
        </div>
        <RoleGuard exclude={["Viewer"]}>
          <div>
            <button className="btn btn-primary me-2" onClick={() => run(false)} disabled={running}>
              {running ? "Running..." : "Run Aspect Analysis"}
            </button>
            <button className="btn btn-outline-primary" onClick={() => run(true)} disabled={running}>
              Reanalyse
            </button>
          </div>
        </RoleGuard>
      </div>

      <AnalysisFilters projectId={projectId} filters={filters} onChange={setFilters} />
      <ErrorAlert error={error} onDismiss={() => setError(null)} />

      {sorted.length === 0 ? (
        <EmptyState title="No aspects yet" description="Run aspect analysis to extract aspects like price, delivery, quality, etc." />
      ) : (
        <DataTable
          columns={[
            { key: "name", header: "Aspect", render: (a) => <a href="#" onClick={(e) => { e.preventDefault(); openAspect(a.id); }}>{a.name}</a> },
            { key: "frequency", header: "Frequency" },
            { key: "positivePercentage", header: "Positive %" },
            { key: "negativePercentage", header: "Negative %" },
            { key: "neutralPercentage", header: "Neutral %" },
            { key: "averageConfidence", header: "Avg Confidence" },
          ]}
          rows={sorted}
        />
      )}

      {selected && (
        <div className="card mt-4">
          <div className="card-header d-flex justify-content-between">
            <span>{selected.name}</span>
            <button className="btn-close" onClick={() => { setSelected(null); setSelectedReviews(null); }} />
          </div>
          <div className="card-body">
            <p>
              <strong>Frequency:</strong> {selected.frequency} &nbsp;
              <strong>Positive:</strong> {selected.positivePercentage}% &nbsp;
              <strong>Negative:</strong> {selected.negativePercentage}% &nbsp;
              <strong>Neutral:</strong> {selected.neutralPercentage}% &nbsp;
              <strong>Avg confidence:</strong> {selected.averageConfidence}
            </p>
            <h6>Evidence / related reviews</h6>
            <ul className="list-group">
              {(selectedReviews || []).slice(0, 8).map((r) => (
                <li key={r.id} className="list-group-item">
                  <span className={`badge me-2 text-bg-${r.aspectSentiment.sentimentLabel === "positive" ? "success" : r.aspectSentiment.sentimentLabel === "negative" ? "danger" : "secondary"}`}>
                    {r.aspectSentiment.sentimentLabel}
                  </span>
                  {r.aspectSentiment.evidenceText}
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}

function RecommendationsTab({ projectId }) {
  const { showToast } = useToast();
  const [recs, setRecs] = useState(null);
  const [error, setError] = useState(null);
  const [generating, setGenerating] = useState(false);
  const [statusFilter, setStatusFilter] = useState("");
  const [priorityFilter, setPriorityFilter] = useState("");
  const [confirmAction, setConfirmAction] = useState(null); // {type: 'reject'|'complete', rec}

  const load = () => {
    const params = {};
    if (statusFilter) params.status = statusFilter;
    if (priorityFilter) params.priority = priorityFilter;
    recommendationApi.list(projectId, params).then((r) => setRecs(r.data.data.items)).catch(setError);
  };
  useEffect(load, [projectId, statusFilter, priorityFilter]);

  const generate = async () => {
    setGenerating(true);
    try {
      const resp = await recommendationApi.generate(projectId);
      showToast(`${resp.data.data.createdCount} recommendation(s) generated`);
      load();
    } catch (err) {
      setError(err);
    } finally {
      setGenerating(false);
    }
  };

  const act = async (rec, action) => {
    try {
      if (action === "accept") await recommendationApi.accept(rec.id);
      if (action === "reject") await recommendationApi.reject(rec.id);
      if (action === "complete") await recommendationApi.complete(rec.id);
      showToast("Recommendation updated");
      setConfirmAction(null);
      load();
    } catch (err) {
      setError(err);
      setConfirmAction(null);
    }
  };

  if (recs === null && !error) return <LoadingSpinner />;

  return (
    <div>
      <div className="d-flex justify-content-between align-items-center my-3">
        <div className="d-flex gap-2">
          <select className="form-select form-select-sm" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="">All statuses</option>
            {["new", "assigned", "accepted", "rejected", "completed"].map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <select className="form-select form-select-sm" value={priorityFilter} onChange={(e) => setPriorityFilter(e.target.value)}>
            <option value="">All priorities</option>
            {["low", "medium", "high"].map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>
        <PermissionGuard permission="view_reviews">
          <button className="btn btn-primary" onClick={generate} disabled={generating}>
            {generating ? "Generating..." : "Generate Recommendations"}
          </button>
        </PermissionGuard>
      </div>

      <ErrorAlert error={error} onDismiss={() => setError(null)} />

      {recs.length === 0 ? (
        <EmptyState title="No recommendations" description="Generate recommendations from analysed aspect data." />
      ) : (
        <div className="row g-3">
          {recs.map((rec) => (
            <div className="col-md-6" key={rec.id}>
              <div className="card p-3 h-100">
                <div className="d-flex justify-content-between">
                  <span className={`badge text-bg-${rec.priority === "high" ? "danger" : rec.priority === "medium" ? "warning" : "secondary"}`}>
                    {rec.priority}
                  </span>
                  <span className="badge text-bg-info">{rec.status}</span>
                </div>
                <p className="mt-2">{rec.text}</p>
                <p className="text-muted small mb-1">
                  Aspect: {rec.aspectName || "—"} · Supporting reviews: {rec.supportingReviewCount}
                </p>
                {rec.evidence && (
                  <p className="text-muted small mb-2">
                    Negative: {rec.evidence.negativePercentage}% · Trend: {rec.evidence.trend}
                  </p>
                )}
                <p className="text-muted small mb-2">
                  Assigned: {rec.assignee?.name || "Unassigned"}
                </p>
                <PermissionGuard permission="approve_ai_output">
                  <div className="d-flex gap-2 flex-wrap">
                    {rec.status !== "accepted" && rec.status !== "completed" && rec.status !== "rejected" && (
                      <button className="btn btn-sm btn-success" onClick={() => act(rec, "accept")}>Accept</button>
                    )}
                    {rec.status !== "rejected" && rec.status !== "completed" && (
                      <button className="btn btn-sm btn-outline-danger" onClick={() => setConfirmAction({ type: "reject", rec })}>Reject</button>
                    )}
                    {rec.status !== "completed" && (
                      <button className="btn btn-sm btn-outline-primary" onClick={() => setConfirmAction({ type: "complete", rec })}>Complete</button>
                    )}
                  </div>
                </PermissionGuard>
              </div>
            </div>
          ))}
        </div>
      )}

      <ConfirmationModal
        show={!!confirmAction}
        title={confirmAction?.type === "reject" ? "Reject recommendation" : "Mark as complete"}
        message={`Are you sure you want to ${confirmAction?.type} this recommendation?`}
        confirmLabel={confirmAction?.type === "reject" ? "Reject" : "Complete"}
        onConfirm={() => act(confirmAction.rec, confirmAction.type)}
        onCancel={() => setConfirmAction(null)}
      />
    </div>
  );
}

export default function AspectAndRecommendations() {
  const { projectId } = useParams();
  const [tab, setTab] = useState("aspects");

  return (
    <div>
      <h2 className="my-3">Aspect-Based Sentiment & AI Recommendations</h2>
      <ul className="nav nav-tabs">
        <li className="nav-item">
          <button className={`nav-link ${tab === "aspects" ? "active" : ""}`} onClick={() => setTab("aspects")}>
            Aspect Analysis
          </button>
        </li>
        <li className="nav-item">
          <button className={`nav-link ${tab === "recommendations" ? "active" : ""}`} onClick={() => setTab("recommendations")}>
            Recommendations
          </button>
        </li>
      </ul>

      {tab === "aspects" ? <AspectTab projectId={projectId} /> : <RecommendationsTab projectId={projectId} />}
    </div>
  );
}
