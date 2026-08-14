import { useCallback, useEffect, useMemo, useState } from "react";
import { projectApi } from "../services/projectApi";
import { useToast } from "../contexts/ToastContext";
import { usePermission } from "../hooks/usePermission";
import LoadingSpinner from "../components/LoadingSpinner";
import ErrorAlert from "../components/ErrorAlert";
import FormInput from "../components/FormInput";
import PermissionGuard from "../components/PermissionGuard";
import ConfirmationModal from "../components/ConfirmationModal";
import SwipeableProjectRow from "../components/SwipeableProjectRow";

const EMPTY_FORM = {
  name: "", description: "", productOrTopic: "", startDate: "", endDate: "",
};

export default function ProjectManagement() {
  const { showToast } = useToast();
  const canDelete = usePermission("delete_project");
  const [projects, setProjects] = useState(null);
  const [error, setError] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [creating, setCreating] = useState(false);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [sort, setSort] = useState("newest");
  const [openProjectId, setOpenProjectId] = useState(null);
  const [pendingDelete, setPendingDelete] = useState(null);
  const [deletingId, setDeletingId] = useState(null);
  const [archivingId, setArchivingId] = useState(null);

  const load = useCallback(() => {
    setError(null);
    projectApi
      .list({ search: search || undefined, status: status || undefined })
      .then((resp) => setProjects(resp.data.data.items))
      .catch(setError);
  }, [search, status]);

  useEffect(() => { load(); }, [load]);

  const sortedProjects = useMemo(() => {
    const items = [...(projects || [])];
    if (sort === "name-asc") return items.sort((a, b) => a.name.localeCompare(b.name));
    if (sort === "name-desc") return items.sort((a, b) => b.name.localeCompare(a.name));
    if (sort === "oldest") return items.sort((a, b) => new Date(a.createdAt || 0) - new Date(b.createdAt || 0));
    return items.sort((a, b) => new Date(b.createdAt || 0) - new Date(a.createdAt || 0));
  }, [projects, sort]);

  const onCreate = async (event) => {
    event.preventDefault();
    if (creating) return;
    setCreating(true);
    try {
      const payload = Object.fromEntries(
        Object.entries(form).map(([key, value]) => [key, value || null]),
      );
      payload.name = form.name;
      await projectApi.create(payload);
      showToast("Sentiment workspace created");
      setShowForm(false);
      setForm(EMPTY_FORM);
      load();
    } catch (err) {
      setError(err);
    } finally {
      setCreating(false);
    }
  };

  const onArchive = async (project) => {
    if (archivingId) return;
    setArchivingId(project.id);
    try {
      const response = await projectApi.archive(project.id, project.status !== "archived");
      setProjects((current) => current?.map((item) => item.id === project.id ? response.data.data : item));
      showToast(project.status === "archived" ? "Project unarchived" : "Project archived");
    } catch (err) {
      showToast(err?.response?.data?.error?.message || "Project status could not be updated", "danger");
    } finally {
      setArchivingId(null);
    }
  };

  const confirmDelete = async () => {
    if (!pendingDelete || deletingId) return;
    const project = pendingDelete;
    setDeletingId(project.id);
    try {
      await projectApi.remove(project.id);
      setPendingDelete(null);
      showToast("Project removed");
      window.setTimeout(() => {
        setProjects((current) => current?.filter((item) => item.id !== project.id));
        setDeletingId(null);
      }, 320);
    } catch (err) {
      setDeletingId(null);
      setPendingDelete(null);
      setOpenProjectId(null);
      showToast(err?.response?.data?.error?.message || "Project could not be deleted", "danger");
    }
  };

  if (projects === null && !error) return <LoadingSpinner />;

  return (
    <div className="projects-page">
      <header className="page-header">
        <div>
          <span className="page-kicker">Sentiment workspaces</span>
          <h1>Projects</h1>
          <p>Organise product, brand, campaign, and customer-feedback analysis.</p>
        </div>
        <PermissionGuard permission="create_project">
          <button className="btn btn-primary" onClick={() => setShowForm((current) => !current)}>
            <span aria-hidden="true">＋</span> New Project
          </button>
        </PermissionGuard>
      </header>

      <ErrorAlert error={error} onDismiss={() => setError(null)} />

      {showForm ? (
        <form onSubmit={onCreate} className="project-create-card card">
          <div className="card-body">
            <div className="form-section-heading">
              <div><span className="page-kicker">New workspace</span><h2>Create a sentiment project</h2></div>
              <button type="button" className="btn-close" aria-label="Close create form" onClick={() => setShowForm(false)} />
            </div>
            <div className="row g-3">
              <div className="col-md-6"><FormInput label="Project name" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
              <div className="col-md-6"><FormInput label="Product or topic" value={form.productOrTopic} onChange={(e) => setForm({ ...form, productOrTopic: e.target.value })} /></div>
              <div className="col-12"><FormInput label="Description" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></div>
              <div className="col-md-6"><FormInput label="Start date" type="date" value={form.startDate} onChange={(e) => setForm({ ...form, startDate: e.target.value })} /></div>
              <div className="col-md-6"><FormInput label="End date" type="date" value={form.endDate} onChange={(e) => setForm({ ...form, endDate: e.target.value })} /></div>
            </div>
            <div className="d-flex justify-content-end gap-2">
              <button className="btn btn-secondary" type="button" onClick={() => setShowForm(false)}>Cancel</button>
              <button className="btn btn-success" type="submit" disabled={creating}>{creating ? "Creating..." : "Create Project"}</button>
            </div>
          </div>
        </form>
      ) : null}

      <div className="projects-toolbar" aria-label="Project filters">
        <div className="project-search">
          <span aria-hidden="true">⌕</span>
          <input className="form-control" placeholder="Search projects..." aria-label="Search projects" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <select className="form-select" aria-label="Filter by status" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="archived">Archived</option>
        </select>
        <select className="form-select" aria-label="Sort projects" value={sort} onChange={(e) => setSort(e.target.value)}>
          <option value="newest">Newest first</option>
          <option value="oldest">Oldest first</option>
          <option value="name-asc">Name A–Z</option>
          <option value="name-desc">Name Z–A</option>
        </select>
      </div>

      <div className="project-list-heading">
        <span>{sortedProjects.length} {sortedProjects.length === 1 ? "workspace" : "workspaces"}</span>
        {canDelete ? <span className="swipe-hint">Swipe left on touch devices to reveal Delete</span> : null}
      </div>

      <div className="project-list" role="list">
        {sortedProjects.length ? sortedProjects.map((project) => (
          <SwipeableProjectRow
            key={project.id}
            project={project}
            isOpen={openProjectId === project.id}
            isRemoving={deletingId === project.id}
            isArchiving={archivingId === project.id}
            canDelete={canDelete}
            onReveal={() => setOpenProjectId(project.id)}
            onClose={() => setOpenProjectId((current) => current === project.id ? null : current)}
            onDelete={setPendingDelete}
            onArchive={onArchive}
          />
        )) : (
          <div className="empty-project-state">
            <strong>No projects found</strong>
            <span>{search || status ? "Try adjusting the search or status filter." : "Create your first sentiment-analysis workspace."}</span>
          </div>
        )}
      </div>

      <ConfirmationModal
        show={!!pendingDelete}
        title="Delete project?"
        message={pendingDelete ? `“${pendingDelete.name}” will be removed from normal project views. This action cannot be undone from the UI.` : ""}
        confirmLabel="Delete Project"
        onConfirm={confirmDelete}
        onCancel={() => { if (!deletingId) setPendingDelete(null); }}
        confirmBusy={!!deletingId}
      />
    </div>
  );
}
