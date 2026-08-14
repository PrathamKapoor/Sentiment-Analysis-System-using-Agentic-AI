import { useEffect, useState } from "react";
import { Bar } from "react-chartjs-2";
import {
  Chart as ChartJS, CategoryScale, LinearScale, BarElement, Tooltip, Legend,
} from "chart.js";
import { projectApi } from "../services/projectApi";
import { analysisApi } from "../services/analysisApi";
import LoadingSpinner from "../components/LoadingSpinner";
import ErrorAlert from "../components/ErrorAlert";
import EmptyState from "../components/EmptyState";
import Breadcrumbs from "../components/Breadcrumbs";

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip, Legend);

export default function ProductComparison() {
  const [projects, setProjects] = useState([]);
  const [selectedIds, setSelectedIds] = useState([]);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    projectApi.list().then((r) => setProjects(r.data.data.items)).catch(setError);
  }, []);

  const toggleSelect = (id) => {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const compare = async () => {
    if (selectedIds.length < 2) return;
    setLoading(true);
    setError(null);
    try {
      const payload = { targetProjectIds: selectedIds };
      if (dateFrom) payload.dateFrom = dateFrom;
      if (dateTo) payload.dateTo = dateTo;
      const resp = await analysisApi.compareProjects(selectedIds[0], payload);
      setResult(resp.data.data);
    } catch (err) {
      setError(err);
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <Breadcrumbs items={[{ label: "Projects", to: "/projects" }, { label: "Comparison" }]} />
      <h2 className="my-3">Product / Brand Comparison</h2>
      <ErrorAlert error={error} onDismiss={() => setError(null)} />

      <div className="card p-3 mb-3">
        <h6>Select at least two projects to compare</h6>
        <div className="d-flex flex-wrap gap-2 mb-3">
          {projects.map((p) => (
            <button
              key={p.id}
              className={`btn btn-sm ${selectedIds.includes(p.id) ? "btn-primary" : "btn-outline-secondary"}`}
              onClick={() => toggleSelect(p.id)}
            >
              {p.name}
            </button>
          ))}
        </div>
        <div className="d-flex gap-2 align-items-end">
          <div>
            <label className="form-label small mb-0">From</label>
            <input type="date" className="form-control form-control-sm" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </div>
          <div>
            <label className="form-label small mb-0">To</label>
            <input type="date" className="form-control form-control-sm" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </div>
          <button className="btn btn-primary" onClick={compare} disabled={selectedIds.length < 2 || loading}>
            {loading ? "Comparing..." : "Compare"}
          </button>
        </div>
      </div>

      {loading && <LoadingSpinner />}

      {!loading && result && (
        <>
          <div className="row g-3 mb-3">
            {result.entities.map((e) => (
              <div className="col-md-6" key={e.projectId}>
                <div className="card p-3">
                  <h5>{e.name}</h5>
                  <p className="mb-1">Total reviews: {e.totalReviews} (analysed: {e.analysedReviews})</p>
                  <p className="mb-1">
                    Positive: {e.positivePercentage ?? "not available"}% ·
                    Negative: {e.negativePercentage ?? "not available"}% ·
                    Neutral: {e.neutralPercentage ?? "not available"}%
                  </p>
                  <p className="mb-1">Average rating: {e.averageRating ?? "not available"}</p>
                  <p className="mb-1">Top positive aspect: {e.topPositiveAspect ?? "not available"}</p>
                  <p className="mb-1">Top negative aspect: {e.topNegativeAspect ?? "not available"}</p>
                  <p className="mb-0">Top keywords: {e.topKeywords.length ? e.topKeywords.join(", ") : "not available"}</p>
                </div>
              </div>
            ))}
          </div>

          <div className="card p-3 mb-3">
            <h6>Sentiment Comparison</h6>
            <Bar
              data={{
                labels: result.entities.map((e) => e.name),
                datasets: [
                  { label: "Positive %", data: result.entities.map((e) => e.positivePercentage || 0), backgroundColor: "#198754" },
                  { label: "Negative %", data: result.entities.map((e) => e.negativePercentage || 0), backgroundColor: "#dc3545" },
                  { label: "Neutral %", data: result.entities.map((e) => e.neutralPercentage || 0), backgroundColor: "#6c757d" },
                ],
              }}
            />
          </div>

          <div className="card p-3 mb-3">
            <h6>Review Volume</h6>
            <Bar
              data={{
                labels: result.entities.map((e) => e.name),
                datasets: [{ label: "Review Volume", data: result.entities.map((e) => e.reviewVolume), backgroundColor: "#0d6efd" }],
              }}
            />
          </div>

          <div className="card p-3">
            <h6>Observed Data — Summary</h6>
            <p className="mb-0">{result.narrative || "Not enough analysed data to generate a comparison summary."}</p>
            <p className="text-muted small mt-2 mb-0">
              This is a factual, system-generated summary of observed metrics — not a recommendation or causal conclusion.
            </p>
          </div>
        </>
      )}

      {!loading && !result && (
        <EmptyState title="No comparison yet" description="Select two or more projects and click Compare." />
      )}
    </div>
  );
}
