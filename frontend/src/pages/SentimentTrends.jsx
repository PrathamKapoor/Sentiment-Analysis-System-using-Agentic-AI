import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Line } from "react-chartjs-2";
import {
  Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend,
} from "chart.js";
import { analysisApi } from "../services/analysisApi";
import LoadingSpinner from "../components/LoadingSpinner";
import ErrorAlert from "../components/ErrorAlert";
import EmptyState from "../components/EmptyState";
import AnalysisFilters from "../components/AnalysisFilters";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend);

const GRANULARITIES = ["daily", "weekly", "monthly"];

export default function SentimentTrends() {
  const { projectId } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [granularity, setGranularity] = useState("daily");
  const [filters, setFilters] = useState({});
  const [aspects, setAspects] = useState([]);
  const [aspectId, setAspectId] = useState("");

  useEffect(() => {
    analysisApi.listAspects(projectId).then((r) => setAspects(r.data.data.items)).catch(() => setAspects([]));
  }, [projectId]);

  const load = () => {
    analysisApi.getTrends(projectId, { ...filters, granularity, aspectId: aspectId || undefined })
      .then((r) => setData(r.data.data))
      .catch(setError);
  };
  useEffect(load, [projectId, granularity, filters, aspectId]);

  if (data === null && !error) return <LoadingSpinner />;

  return (
    <div>
      <div className="d-flex justify-content-between align-items-center my-3">
        <h2>Sentiment Trends</h2>
        <div className="btn-group">
          {GRANULARITIES.map((g) => (
            <button
              key={g}
              className={`btn btn-outline-primary ${granularity === g ? "active" : ""}`}
              onClick={() => setGranularity(g)}
            >
              {g}
            </button>
          ))}
        </div>
      </div>

      <ErrorAlert error={error} onDismiss={() => setError(null)} />
      <AnalysisFilters projectId={projectId} filters={filters} onChange={setFilters} rating />
      {aspects.length > 0 && (
        <div className="mb-3" style={{ maxWidth: 240 }}>
          <label className="form-label small mb-0">Aspect</label>
          <select className="form-select form-select-sm" value={aspectId} onChange={(e) => setAspectId(e.target.value)}>
            <option value="">All aspects</option>
            {aspects.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
        </div>
      )}

      {!data || data.periods.length === 0 ? (
        <EmptyState title="No trend data" description="No analysed reviews in this range yet." />
      ) : (
        <div className="card p-3">
          <Line
            data={{
              labels: data.periods.map((p) => p.period),
              datasets: [
                { label: "Positive", data: data.periods.map((p) => p.positiveCount), borderColor: "#198754", tension: 0.2 },
                { label: "Negative", data: data.periods.map((p) => p.negativeCount), borderColor: "#dc3545", tension: 0.2 },
                { label: "Neutral", data: data.periods.map((p) => p.neutralCount), borderColor: "#6c757d", tension: 0.2 },
                { label: "Volume", data: data.periods.map((p) => p.totalReviews), borderColor: "#0d6efd", borderDash: [5, 5], tension: 0.2 },
              ],
            }}
            options={{ responsive: true, plugins: { tooltip: { mode: "index", intersect: false } } }}
          />
        </div>
      )}
    </div>
  );
}
