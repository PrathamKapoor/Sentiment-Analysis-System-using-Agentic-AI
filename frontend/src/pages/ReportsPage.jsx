import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { reportApi, downloadReportFile } from "../services/reportApi";
import { useToast } from "../contexts/ToastContext";
import LoadingSpinner from "../components/LoadingSpinner";
import ErrorAlert from "../components/ErrorAlert";
import EmptyState from "../components/EmptyState";
import DataTable from "../components/DataTable";
import FormInput from "../components/FormInput";
import PermissionGuard from "../components/PermissionGuard";
import ConfirmationModal from "../components/ConfirmationModal";

const SECTIONS = [
  ["projectOverview", "Project Overview"], ["executiveSummary", "Executive Summary"],
  ["sentimentDistribution", "Sentiment Distribution"], ["sentimentTrends", "Sentiment Trends"],
  ["topicAnalysis", "Topic Analysis"], ["keywordAnalysis", "Keyword Analysis"],
  ["aspectSentiment", "Aspect-Based Sentiment"], ["recommendations", "Recommendations"],
  ["alerts", "Alerts"], ["representativeReviews", "Representative Reviews"], ["conclusion", "Conclusion"],
];

const STATUS_BADGE = { queued: "secondary", running: "info", complete: "success", failed: "danger" };

export default function ReportsPage() {
  const { projectId } = useParams();
  const { showToast } = useToast();
  const [reports, setReports] = useState(null);
  const [error, setError] = useState(null);
  const [generating, setGenerating] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [form, setForm] = useState({
    reportName: "", dateFrom: "", dateTo: "", fileFormat: "pdf", sections: ["projectOverview", "sentimentDistribution"],
    includeAiSummary: false, includeRecommendations: false, includeRepresentativeReviews: false,
  });

  const load = () => {
    reportApi.list(projectId).then((r) => setReports(r.data.data.items)).catch(setError);
  };
  useEffect(load, [projectId]);

  const toggleSection = (key) => {
    setForm((f) => ({
      ...f,
      sections: f.sections.includes(key) ? f.sections.filter((s) => s !== key) : [...f.sections, key],
    }));
  };

  const generate = async () => {
    if (!form.dateFrom || !form.dateTo) {
      setError({ message: "Select a date range" });
      return;
    }
    setGenerating(true);
    try {
      await reportApi.create(projectId, form);
      showToast("Report generated");
      load();
    } catch (err) {
      setError(err);
    } finally {
      setGenerating(false);
    }
  };

  const download = async (report) => {
    try {
      await downloadReportFile(report.id, `${report.reportName}.${report.fileFormat === "pdf" ? "pdf" : "xlsx"}`);
    } catch (err) {
      setError(err);
    }
  };

  const confirmDelete = async () => {
    try {
      await reportApi.remove(deleteTarget.id);
      showToast("Report deleted");
      setDeleteTarget(null);
      load();
    } catch (err) {
      setError(err);
      setDeleteTarget(null);
    }
  };

  if (reports === null && !error) return <LoadingSpinner />;

  return (
    <div>
      <h2 className="my-3">Reports</h2>
      <ErrorAlert error={error} onDismiss={() => setError(null)} />

      <PermissionGuard permission="generate_report">
        <div className="card p-3 mb-3">
          <h6>Generate Report</h6>
          <div className="row g-2 mb-2">
            <div className="col-md-4">
              <FormInput label="Report name" value={form.reportName} onChange={(e) => setForm({ ...form, reportName: e.target.value })} />
            </div>
            <div className="col-md-3">
              <label className="form-label">From</label>
              <input type="date" className="form-control" value={form.dateFrom} onChange={(e) => setForm({ ...form, dateFrom: e.target.value })} />
            </div>
            <div className="col-md-3">
              <label className="form-label">To</label>
              <input type="date" className="form-control" value={form.dateTo} onChange={(e) => setForm({ ...form, dateTo: e.target.value })} />
            </div>
            <div className="col-md-2">
              <label className="form-label">Format</label>
              <select className="form-select" value={form.fileFormat} onChange={(e) => setForm({ ...form, fileFormat: e.target.value })}>
                <option value="pdf">PDF</option>
                <option value="excel">Excel</option>
              </select>
            </div>
          </div>

          <label className="form-label small">Sections</label>
          <div className="d-flex flex-wrap gap-2 mb-2">
            {SECTIONS.map(([key, label]) => (
              <button
                key={key} type="button"
                className={`btn btn-sm ${form.sections.includes(key) ? "btn-primary" : "btn-outline-secondary"}`}
                onClick={() => toggleSection(key)}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="form-check">
            <input className="form-check-input" type="checkbox" id="incSummary" checked={form.includeAiSummary} onChange={(e) => setForm({ ...form, includeAiSummary: e.target.checked })} />
            <label className="form-check-label" htmlFor="incSummary">Include approved AI summary</label>
          </div>
          <div className="form-check">
            <input className="form-check-input" type="checkbox" id="incRecs" checked={form.includeRecommendations} onChange={(e) => setForm({ ...form, includeRecommendations: e.target.checked })} />
            <label className="form-check-label" htmlFor="incRecs">Include recommendations</label>
          </div>
          <div className="form-check mb-3">
            <input className="form-check-input" type="checkbox" id="incReviews" checked={form.includeRepresentativeReviews} onChange={(e) => setForm({ ...form, includeRepresentativeReviews: e.target.checked })} />
            <label className="form-check-label" htmlFor="incReviews">Include representative reviews</label>
          </div>

          <button className="btn btn-primary" onClick={generate} disabled={generating} style={{ width: 160 }}>
            {generating ? "Generating..." : "Generate"}
          </button>
        </div>
      </PermissionGuard>

      {reports.length === 0 ? (
        <EmptyState title="No reports yet" description="Generate a report using the form above." />
      ) : (
        <DataTable
          columns={[
            { key: "reportName", header: "Name" },
            { key: "fileFormat", header: "Format", render: (r) => r.fileFormat.toUpperCase() },
            { key: "dateRange", header: "Date Range", render: (r) => `${r.dateRangeStart} → ${r.dateRangeEnd}` },
            { key: "generationStatus", header: "Status", render: (r) => <span className={`badge text-bg-${STATUS_BADGE[r.generationStatus]}`}>{r.generationStatus}</span> },
            { key: "createdAt", header: "Generated", render: (r) => new Date(r.createdAt).toLocaleString() },
            {
              key: "actions", header: "",
              render: (r) => (
                <>
                  {r.generationStatus === "complete" && (
                    <button className="btn btn-sm btn-outline-primary me-2" onClick={() => download(r)}>Download</button>
                  )}
                  <PermissionGuard permission="generate_report">
                    <button className="btn btn-sm btn-outline-danger" onClick={() => setDeleteTarget(r)}>Delete</button>
                  </PermissionGuard>
                </>
              ),
            },
          ]}
          rows={reports}
        />
      )}

      <ConfirmationModal
        show={!!deleteTarget}
        title="Delete report"
        message={`Delete "${deleteTarget?.reportName}"? This cannot be undone.`}
        confirmLabel="Delete"
        onConfirm={confirmDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
