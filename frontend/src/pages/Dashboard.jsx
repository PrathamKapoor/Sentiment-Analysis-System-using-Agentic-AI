import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { projectApi } from "../services/projectApi";
import { alertApi } from "../services/alertApi";
import { aiSummaryApi } from "../services/aiSummaryApi";
import { reportApi } from "../services/reportApi";
import { workflowApi } from "../services/workflowApi";

const MAX_PROJECTS_SCANNED = 5; // keep the dashboard light — not a full org-wide crawl

export default function Dashboard() {
  const { user, activeOrganisation } = useAuth();
  const [stats, setStats] = useState(null);

  useEffect(() => {
    projectApi.list().then(async (r) => {
      const projects = r.data.data.items.slice(0, MAX_PROJECTS_SCANNED);
      const perProject = await Promise.all(
        projects.map((p) =>
          Promise.all([
            alertApi.list(p.id, { status: "open" }).catch(() => ({ data: { data: { items: [] } } })),
            aiSummaryApi.list(p.id).catch(() => ({ data: { data: { items: [] } } })),
            reportApi.list(p.id).catch(() => ({ data: { data: { items: [] } } })),
            workflowApi.list(p.id).catch(() => ({ data: { data: { items: [] } } })),
          ]).then(([alerts, summaries, reports, workflows]) => ({
            project: p,
            alerts: alerts.data.data.items.filter((a) => a.triggeredAt),
            summaries: summaries.data.data.items,
            reports: reports.data.data.items,
            workflows: workflows.data.data.items,
          }))
        )
      );

      const recentAlerts = perProject.flatMap((x) => x.alerts.map((a) => ({ ...a, projectName: x.project.name })))
        .sort((a, b) => new Date(b.triggeredAt) - new Date(a.triggeredAt)).slice(0, 5);
      const recentSummaries = perProject.flatMap((x) => x.summaries.map((s) => ({ ...s, projectName: x.project.name })))
        .sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt)).slice(0, 5);
      const recentReports = perProject.flatMap((x) => x.reports.map((rp) => ({ ...rp, projectName: x.project.name })))
        .sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt)).slice(0, 5);
      const recentWorkflows = perProject.flatMap((x) => x.workflows.map((w) => ({ ...w, projectName: x.project.name })))
        .sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt)).slice(0, 5);

      setStats({
        activeProjects: r.data.data.items.filter((p) => p.status === "active").length,
        openAlertCount: perProject.reduce((sum, x) => sum + x.alerts.length, 0),
        reportCount: perProject.reduce((sum, x) => sum + x.reports.length, 0),
        recentAlerts, recentSummaries, recentReports, recentWorkflows,
      });
    });
  }, []);

  return (
    <div>
      <h2>Welcome, {user?.name}</h2>
      <p className="text-muted">
        Organisation: {activeOrganisation?.organisationName} — Roles:{" "}
        {(activeOrganisation?.roles || []).join(", ") || "none"}
      </p>

      <div className="row g-3 mt-2">
        <div className="col-md-3">
          <div className="card text-center p-3">
            <div className="fs-4 fw-bold">{stats?.activeProjects ?? "—"}</div>
            <div className="text-muted">Active Projects</div>
          </div>
        </div>
        <div className="col-md-3">
          <div className="card text-center p-3">
            <div className="fs-4 fw-bold">—</div>
            <div className="text-muted">Reviews Analysed</div>
          </div>
        </div>
        <div className="col-md-3">
          <div className="card text-center p-3">
            <div className="fs-4 fw-bold">{stats?.openAlertCount ?? "—"}</div>
            <div className="text-muted">Open Alerts</div>
          </div>
        </div>
        <div className="col-md-3">
          <div className="card text-center p-3">
            <div className="fs-4 fw-bold">{stats?.reportCount ?? "—"}</div>
            <div className="text-muted">Reports</div>
          </div>
        </div>
      </div>

      {stats && (
        <div className="row g-3 mt-1">
          <div className="col-md-4">
            <div className="card">
              <div className="card-header">Recent Alerts</div>
              <ul className="list-group list-group-flush">
                {stats.recentAlerts.length === 0 && <li className="list-group-item text-muted">None</li>}
                {stats.recentAlerts.map((a) => (
                  <li key={a.id} className="list-group-item">
                    <Link to={`/projects/${a.projectId}/alerts`}>{a.name}</Link> — {a.projectName}
                  </li>
                ))}
              </ul>
            </div>
          </div>
          <div className="col-md-4">
            <div className="card">
              <div className="card-header">Recent Summaries</div>
              <ul className="list-group list-group-flush">
                {stats.recentSummaries.length === 0 && <li className="list-group-item text-muted">None</li>}
                {stats.recentSummaries.map((s) => (
                  <li key={s.id} className="list-group-item">
                    <Link to={`/projects/${s.projectId}/ai-summary`}>{s.summaryType}</Link> ({s.approvalStatus}) — {s.projectName}
                  </li>
                ))}
              </ul>
            </div>
          </div>
          <div className="col-md-4">
            <div className="card">
              <div className="card-header">Recent Reports</div>
              <ul className="list-group list-group-flush">
                {stats.recentReports.length === 0 && <li className="list-group-item text-muted">None</li>}
                {stats.recentReports.map((rp) => (
                  <li key={rp.id} className="list-group-item">
                    <Link to={`/projects/${rp.projectId}/reports`}>{rp.reportName}</Link> — {rp.projectName}
                  </li>
                ))}
              </ul>
            </div>
          </div>
          <div className="col-md-4">
            <div className="card">
              <div className="card-header">Recent Workflows <span className="badge text-bg-dark">Agent-assisted</span></div>
              <ul className="list-group list-group-flush">
                {stats.recentWorkflows.length === 0 && <li className="list-group-item text-muted">None</li>}
                {stats.recentWorkflows.map((w) => (
                  <li key={w.id} className="list-group-item">
                    <Link to={`/projects/${w.projectId}`}>{w.workflowType}</Link> ({w.status}) — {w.projectName}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}

      <div className="card mt-3">
        <div className="card-header">Account</div>
        <div className="card-body">
          <p className="mb-1"><strong>Name:</strong> {user?.name}</p>
          <p className="mb-1"><strong>Email:</strong> {user?.email}</p>
          <p className="mb-0"><strong>Contact:</strong> {user?.contact || "—"}</p>
        </div>
      </div>
    </div>
  );
}
