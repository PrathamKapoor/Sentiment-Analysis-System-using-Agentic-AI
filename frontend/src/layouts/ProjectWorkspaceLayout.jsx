import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useParams } from "react-router-dom";
import Breadcrumbs from "../components/Breadcrumbs";
import LoadingSpinner from "../components/LoadingSpinner";
import { useAuth } from "../contexts/AuthContext";
import { projectApi } from "../services/projectApi";

const WORKSPACE_GROUPS = [
  {
    label: "Project",
    items: [{ path: "", label: "Overview" }],
  },
  {
    label: "Data",
    items: [
      { path: "sources", label: "Data Sources" },
      { path: "datasets", label: "Datasets" },
      { path: "reviews", label: "Reviews", permission: "view_reviews" },
    ],
  },
  {
    label: "Analysis",
    items: [
      { path: "analysis/sentiment", label: "Sentiment", permission: "view_reviews" },
      { path: "analysis/topics", label: "Topics", permission: "view_reviews" },
      { path: "analysis/keywords", label: "Keywords", permission: "view_reviews" },
      { path: "analysis/trends", label: "Trends", permission: "view_reviews" },
      { path: "analysis/aspects", label: "Aspects", permission: "view_reviews" },
    ],
  },
  {
    label: "Intelligence",
    items: [
      { path: "ai-summary", label: "AI Summary", permission: "view_reviews" },
      { path: "alerts", label: "Alerts", permission: "view_reviews" },
      { path: "reports", label: "Reports", permission: "view_reviews" },
    ],
  },
];

const PAGE_LABELS = {
  sources: "Data Sources",
  datasets: "Datasets",
  reviews: "Reviews",
  "analysis/sentiment": "Sentiment Analysis",
  "analysis/topics": "Topic Analysis",
  "analysis/keywords": "Keywords & Word Cloud",
  "analysis/trends": "Sentiment Trends",
  "analysis/aspects": "Aspects & Recommendations",
  "ai-summary": "AI Summary",
  alerts: "Alerts",
  reports: "Reports",
};

export default function ProjectWorkspaceLayout() {
  const { projectId } = useParams();
  const location = useLocation();
  const { hasPermission } = useAuth();
  const [project, setProject] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  const loadProject = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await projectApi.get(projectId);
      setProject(response.data.data);
    } catch (requestError) {
      setProject(null);
      setError(requestError);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => { loadProject(); }, [loadProject]);

  const relativePath = location.pathname
    .replace(`/projects/${projectId}`, "")
    .replace(/^\//, "")
    .replace(/\/$/, "");
  const pageLabel = PAGE_LABELS[relativePath] || "Overview";
  const groups = useMemo(() => WORKSPACE_GROUPS.map((group) => ({
    ...group,
    items: group.items.filter((item) => !item.permission || hasPermission(item.permission)),
  })).filter((group) => group.items.length), [hasPermission]);

  if (loading) {
    return <div className="project-workspace-state" role="status" aria-live="polite"><LoadingSpinner /><span>Loading project workspace…</span></div>;
  }

  if (error) {
    const notFound = error?.response?.status === 404;
    return (
      <section className="project-workspace-error" role="alert">
        <span className="page-kicker">Project workspace</span>
        <h1>{notFound ? "Project not found" : "Unable to load this project"}</h1>
        <p>{notFound ? "This project may have been removed, or you may no longer have access to it." : "The project could not be loaded. Check your connection and try again."}</p>
        <div className="d-flex gap-2 flex-wrap">
          {!notFound && <button type="button" className="btn btn-primary" onClick={loadProject}>Retry</button>}
          <Link className="btn btn-outline-secondary" to="/projects">Back to Projects</Link>
        </div>
      </section>
    );
  }

  return (
    <div className="project-workspace-shell">
      <Breadcrumbs items={[
        { label: "Projects", to: "/projects" },
        { label: project.name, to: relativePath ? `/projects/${projectId}` : undefined },
        ...(relativePath ? [{ label: pageLabel }] : []),
      ]} />
      <div className="project-workspace-heading">
        <div><span className="page-kicker">Project workspace</span><strong>{project.name}</strong></div>
        <Link to="/projects" className="project-workspace-back">← All projects</Link>
      </div>
      <div className="project-workspace-frame">
        <aside className="project-workspace-nav" aria-label={`${project.name} workspace navigation`}>
          {groups.map((group) => (
            <div className="project-nav-group" key={group.label}>
              <span>{group.label}</span>
              <nav>
                {group.items.map((item) => {
                  const to = `/projects/${projectId}${item.path ? `/${item.path}` : ""}`;
                  return <NavLink key={item.path || "overview"} to={to} end={!item.path} className={({ isActive }) => `project-nav-link${isActive ? " is-active" : ""}`}>{item.label}</NavLink>;
                })}
              </nav>
            </div>
          ))}
        </aside>
        <section className="project-workspace-content">
          <Outlet context={{ project, reloadProject: loadProject }} />
        </section>
      </div>
    </div>
  );
}
