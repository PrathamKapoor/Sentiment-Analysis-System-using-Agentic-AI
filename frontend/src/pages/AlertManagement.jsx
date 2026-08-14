import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { alertApi } from "../services/alertApi";
import { useToast } from "../contexts/ToastContext";
import LoadingSpinner from "../components/LoadingSpinner";
import ErrorAlert from "../components/ErrorAlert";
import EmptyState from "../components/EmptyState";
import DataTable from "../components/DataTable";
import FormInput from "../components/FormInput";
import PermissionGuard from "../components/PermissionGuard";

const METRICS = [
  "negative_sentiment_percentage", "negative_review_count", "average_rating",
  "keyword_frequency", "aspect_negativity_percentage", "review_volume", "recommendation_priority",
];
const OPERATORS = [">", ">=", "<", "<=", "=="];
const PRIORITIES = ["low", "medium", "high"];

const EFFECTIVE_BADGE = {
  active: "primary", triggered: "danger", acknowledged: "warning", resolved: "success", disabled: "secondary",
};

export default function AlertManagement() {
  const { projectId } = useParams();
  const { showToast } = useToast();
  const [alerts, setAlerts] = useState(null);
  const [error, setError] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [resolvingId, setResolvingId] = useState(null);
  const [resolutionNotes, setResolutionNotes] = useState("");
  const [form, setForm] = useState({
    name: "", metric: METRICS[0], operator: ">", threshold: "", timeWindowDays: "",
    keyword: "", aspectName: "", priority: "medium",
  });

  const load = () => {
    const params = statusFilter ? { status: statusFilter } : {};
    alertApi.list(projectId, params).then((r) => setAlerts(r.data.data.items)).catch(setError);
  };
  useEffect(load, [projectId, statusFilter]);

  const createAlert = async (e) => {
    e.preventDefault();
    try {
      await alertApi.create(projectId, { ...form, threshold: Number(form.threshold), timeWindowDays: form.timeWindowDays ? Number(form.timeWindowDays) : undefined });
      showToast("Alert rule created");
      setShowForm(false);
      load();
    } catch (err) {
      setError(err);
    }
  };

  const act = async (alert, action) => {
    try {
      if (action === "enable") await alertApi.enable(alert.id);
      if (action === "disable") await alertApi.disable(alert.id);
      if (action === "evaluate") {
        const resp = await alertApi.evaluate(alert.id);
        showToast(resp.data.data.triggered ? "Alert triggered" : "Not triggered");
      }
      if (action === "acknowledge") await alertApi.acknowledge(alert.id);
      load();
    } catch (err) {
      setError(err);
    }
  };

  const evaluateAll = async () => {
    try {
      await alertApi.evaluateProject(projectId);
      showToast("All rules evaluated");
      load();
    } catch (err) {
      setError(err);
    }
  };

  const resolve = async (alert) => {
    try {
      await alertApi.resolve(alert.id, resolutionNotes);
      showToast("Alert resolved");
      setResolvingId(null);
      setResolutionNotes("");
      load();
    } catch (err) {
      setError(err);
    }
  };

  if (alerts === null && !error) return <LoadingSpinner />;

  const filtered = search
    ? alerts.filter((a) => a.name.toLowerCase().includes(search.toLowerCase()))
    : alerts;

  return (
    <div>
      <div className="d-flex justify-content-between align-items-center my-3">
        <h2>Alert Management</h2>
        <PermissionGuard permission="manage_alerts">
          <div>
            <button className="btn btn-outline-primary me-2" onClick={evaluateAll}>Evaluate All Rules</button>
            <button className="btn btn-primary" onClick={() => setShowForm((s) => !s)}>+ Create Rule</button>
          </div>
        </PermissionGuard>
      </div>

      <ErrorAlert error={error} onDismiss={() => setError(null)} />

      {showForm && (
        <form onSubmit={createAlert} className="card p-3 mb-3">
          <div className="row g-2">
            <div className="col-md-4">
              <FormInput label="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </div>
            <div className="col-md-4">
              <label className="form-label">Metric</label>
              <select className="form-select" value={form.metric} onChange={(e) => setForm({ ...form, metric: e.target.value })}>
                {METRICS.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>
            <div className="col-md-2">
              <label className="form-label">Operator</label>
              <select className="form-select" value={form.operator} onChange={(e) => setForm({ ...form, operator: e.target.value })}>
                {OPERATORS.map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            </div>
            <div className="col-md-2">
              <FormInput label="Threshold" type="number" required value={form.threshold} onChange={(e) => setForm({ ...form, threshold: e.target.value })} />
            </div>
            <div className="col-md-3">
              <FormInput label="Time window (days)" type="number" value={form.timeWindowDays} onChange={(e) => setForm({ ...form, timeWindowDays: e.target.value })} />
            </div>
            {form.metric === "keyword_frequency" && (
              <div className="col-md-3">
                <FormInput label="Keyword" value={form.keyword} onChange={(e) => setForm({ ...form, keyword: e.target.value })} />
              </div>
            )}
            {form.metric === "aspect_negativity_percentage" && (
              <div className="col-md-3">
                <FormInput label="Aspect name" value={form.aspectName} onChange={(e) => setForm({ ...form, aspectName: e.target.value })} />
              </div>
            )}
            <div className="col-md-3">
              <label className="form-label">Severity</label>
              <select className="form-select" value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>
                {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>
          </div>
          <button className="btn btn-primary mt-3" type="submit">Create</button>
        </form>
      )}

      <div className="d-flex gap-2 mb-3">
        <FormInput placeholder="Search alerts..." value={search} onChange={(e) => setSearch(e.target.value)} />
        <select className="form-select" style={{ maxWidth: 200 }} value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">All statuses</option>
          <option value="open">Open</option>
          <option value="resolved">Resolved</option>
        </select>
      </div>

      {filtered.length === 0 ? (
        <EmptyState title="No alert rules yet" description="Create a rule to start monitoring sentiment thresholds." />
      ) : (
        <DataTable
          columns={[
            { key: "name", header: "Name" },
            { key: "metric", header: "Metric" },
            { key: "rule", header: "Rule", render: (a) => `${a.operator} ${a.thresholdValue}` },
            { key: "severity", header: "Severity" },
            { key: "effectiveStatus", header: "Status", render: (a) => <span className={`badge text-bg-${EFFECTIVE_BADGE[a.effectiveStatus]}`}>{a.effectiveStatus}</span> },
            { key: "assignee", header: "Assigned", render: (a) => a.assignee?.name || "—" },
            { key: "triggeredAt", header: "Triggered", render: (a) => a.triggeredAt ? new Date(a.triggeredAt).toLocaleString() : "—" },
            {
              key: "actions", header: "",
              render: (a) =>
                resolvingId === a.id ? (
                  <div className="d-flex gap-1">
                    <input className="form-control form-control-sm" placeholder="Resolution notes" value={resolutionNotes} onChange={(e) => setResolutionNotes(e.target.value)} />
                    <button className="btn btn-sm btn-success" onClick={() => resolve(a)}>Save</button>
                    <button className="btn btn-sm btn-outline-secondary" onClick={() => setResolvingId(null)}>Cancel</button>
                  </div>
                ) : (
                  <PermissionGuard permission="manage_alerts">
                    <div className="d-flex gap-1 flex-wrap">
                      <button className="btn btn-sm btn-outline-primary" onClick={() => act(a, "evaluate")}>Evaluate</button>
                      <button className="btn btn-sm btn-outline-secondary" onClick={() => act(a, a.enabled ? "disable" : "enable")}>
                        {a.enabled ? "Disable" : "Enable"}
                      </button>
                      {a.status === "open" && a.triggeredAt && (
                        <>
                          <button className="btn btn-sm btn-outline-warning" onClick={() => act(a, "acknowledge")}>Acknowledge</button>
                          <button className="btn btn-sm btn-outline-success" onClick={() => setResolvingId(a.id)}>Resolve</button>
                        </>
                      )}
                    </div>
                  </PermissionGuard>
                ),
            },
          ]}
          rows={filtered}
        />
      )}
    </div>
  );
}
