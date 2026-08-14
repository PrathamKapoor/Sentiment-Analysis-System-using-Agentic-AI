import { useEffect, useState } from "react";
import { useParams, useNavigate, Link, useOutletContext } from "react-router-dom";
import { projectApi } from "../services/projectApi";
import { aiSummaryApi } from "../services/aiSummaryApi";
import { alertApi } from "../services/alertApi";
import { reportApi } from "../services/reportApi";
import { dataSourceApi } from "../services/dataSourceApi";
import { useToast } from "../contexts/ToastContext";
import ErrorAlert from "../components/ErrorAlert";
import ConfirmationModal from "../components/ConfirmationModal";
import PermissionGuard from "../components/PermissionGuard";
import AgenticWorkflowPanel from "../components/AgenticWorkflowPanel";

export default function ProjectDetails() {
  const { projectId } = useParams();
  const { project, reloadProject } = useOutletContext();
  const navigate = useNavigate();
  const { showToast } = useToast();
  const [error, setError] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [indicators, setIndicators] = useState(null);

  useEffect(() => {
    Promise.all([
      aiSummaryApi.list(projectId).catch(() => ({ data: { data: { items: [] } } })),
      alertApi.list(projectId, { status: "open" }).catch(() => ({ data: { data: { items: [] } } })),
      reportApi.list(projectId).catch(() => ({ data: { data: { items: [] } } })),
      dataSourceApi.list(projectId).catch(() => ({ data: { data: { items: [] } } })),
    ]).then(([summaries, alerts, reports, sources]) => {
      const openAlerts = alerts.data.data.items.filter((a) => a.triggeredAt);
      const sourceItems = sources.data.data.items;
      const lastCollected = sourceItems
        .map((s) => s.lastCollectedAt)
        .filter(Boolean)
        .sort()
        .pop();
      setIndicators({
        latestSummaryStatus: summaries.data.data.items[0]?.approvalStatus || null,
        activeAlertCount: openAlerts.length,
        latestReport: reports.data.data.items[0] || null,
        activeSourceCount: sourceItems.filter((s) => s.enabled).length,
        lastCollectedAt: lastCollected || null,
      });
    });
  }, [projectId]);

  const onArchiveToggle = async () => {
    try {
      await projectApi.archive(projectId, project.status !== "archived");
      showToast("Project status updated");
      reloadProject();
    } catch (err) {
      setError(err);
    }
  };

  const onDelete = async () => {
    try {
      await projectApi.remove(projectId);
      showToast("Project deleted");
      navigate("/projects");
    } catch (err) {
      setError(err);
      setConfirmDelete(false);
    }
  };

  return (
    <div className="project-workspace-page">
      <ErrorAlert error={error} onDismiss={() => setError(null)} />
      <div className="page-header my-3">
        <div>
          <span className="page-kicker">Sentiment workspace</span>
          <h1 className="mb-0">{project.name}</h1>
        </div>
        <div>
          <PermissionGuard permission="edit_project">
            <button className="btn btn-outline-secondary me-2" onClick={onArchiveToggle}>
              {project.status === "archived" ? "Unarchive" : "Archive"}
            </button>
          </PermissionGuard>
          <PermissionGuard permission="delete_project">
            <button className="btn btn-outline-danger" onClick={() => setConfirmDelete(true)}>
              Delete
            </button>
          </PermissionGuard>
        </div>
      </div>

      {project.status === "archived" && (
        <div className="alert alert-secondary">This project is archived.</div>
      )}

      <div className="card mb-3">
        <div className="card-body">
          <p><strong>Description:</strong> {project.description || "—"}</p>
          <p><strong>Product/Topic:</strong> {project.productOrTopic || "—"}</p>
          <p><strong>Dates:</strong> {project.startDate || "—"} to {project.endDate || "—"}</p>
          <p className="mb-0"><strong>Status:</strong> {project.status}</p>
        </div>
      </div>

      {indicators && (
        <div className="row g-3 mb-3">
          <div className="col-md-3">
            <div className="card p-3 text-center">
              <div className="fs-6 fw-bold">{indicators.latestSummaryStatus || "None yet"}</div>
              <div className="text-muted small">Latest AI Summary Status</div>
            </div>
          </div>
          <div className="col-md-3">
            <div className="card p-3 text-center">
              <div className="fs-6 fw-bold">{indicators.activeAlertCount}</div>
              <div className="text-muted small">Active Alerts</div>
            </div>
          </div>
          <div className="col-md-3">
            <div className="card p-3 text-center">
              <div className="fs-6 fw-bold">{indicators.latestReport ? indicators.latestReport.generationStatus : "None yet"}</div>
              <div className="text-muted small">Latest Report</div>
            </div>
          </div>
          <div className="col-md-3">
            <div className="card p-3 text-center">
              <div className="fs-6 fw-bold">{indicators.activeSourceCount} active</div>
              <div className="text-muted small">
                Data Sources{indicators.lastCollectedAt && ` — last collected ${new Date(indicators.lastCollectedAt).toLocaleDateString()}`}
              </div>
            </div>
          </div>
        </div>
      )}

      <AgenticWorkflowPanel projectId={projectId} />

      <div className="d-flex gap-2 flex-wrap">
        <Link className="btn btn-domain-data" to={`/projects/${projectId}/sources`}>Data Sources</Link>
        <Link className="btn btn-outline-primary" to={`/projects/${projectId}/datasets`}>Datasets</Link>
        <Link className="btn btn-outline-primary" to={`/projects/${projectId}/reviews`}>Reviews</Link>
        <Link className="btn btn-domain-analysis" to={`/projects/${projectId}/analysis/sentiment`}>Sentiment Results</Link>
        <Link className="btn btn-domain-analysis" to={`/projects/${projectId}/analysis/topics`}>Topics</Link>
        <Link className="btn btn-domain-analysis" to={`/projects/${projectId}/analysis/keywords`}>Keywords</Link>
        <Link className="btn btn-domain-analysis" to={`/projects/${projectId}/analysis/trends`}>Trends</Link>
        <Link className="btn btn-domain-analysis" to={`/projects/${projectId}/analysis/aspects`}>Aspects & Recommendations</Link>
        <Link className="btn btn-domain-warning" to={`/projects/${projectId}/ai-summary`}>AI Summary</Link>
        <Link className="btn btn-domain-warning" to={`/projects/${projectId}/alerts`}>Alerts</Link>
        <Link className="btn btn-outline-primary" to={`/projects/${projectId}/reports`}>Reports</Link>
      </div>

      <ConfirmationModal
        show={confirmDelete}
        title="Delete project"
        message={`Delete "${project.name}"? This cannot be undone from the UI.`}
        confirmLabel="Delete"
        onConfirm={onDelete}
        onCancel={() => setConfirmDelete(false)}
      />
    </div>
  );
}
