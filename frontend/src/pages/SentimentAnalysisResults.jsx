import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Doughnut } from "react-chartjs-2";
import { Chart as ChartJS, ArcElement, Tooltip, Legend } from "chart.js";
import { analysisApi } from "../services/analysisApi";
import { useToast } from "../contexts/ToastContext";
import LoadingSpinner from "../components/LoadingSpinner";
import ErrorAlert from "../components/ErrorAlert";
import EmptyState from "../components/EmptyState";
import AnalysisFilters from "../components/AnalysisFilters";
import RoleGuard from "../components/RoleGuard";

ChartJS.register(ArcElement, Tooltip, Legend);

export default function SentimentAnalysisResults() {
  const { projectId } = useParams();
  const { showToast } = useToast();
  const [summary, setSummary] = useState(null);
  const [results, setResults] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [filters, setFilters] = useState({});

  const load = () => {
    setLoading(true);
    Promise.all([
      analysisApi.getSentimentSummary(projectId, filters),
      analysisApi.getSentimentResults(projectId, filters),
    ])
      .then(([s, r]) => {
        setSummary(s.data.data);
        setResults(r.data.data.items);
      })
      .catch(setError)
      .finally(() => setLoading(false));
  };
  useEffect(load, [projectId, filters]);

  const runAnalysis = async (reanalyse = false) => {
    setRunning(true);
    try {
      if (reanalyse) await analysisApi.reanalyseSentiment(projectId);
      else await analysisApi.runSentiment(projectId);
      showToast(reanalyse ? "Re-analysis complete" : "Analysis complete");
      load();
    } catch (err) {
      setError(err);
    } finally {
      setRunning(false);
    }
  };

  if (loading) return <LoadingSpinner />;
  if (error) return <ErrorAlert error={error} onDismiss={() => setError(null)} />;

  const sortedByPositive = [...(results || [])].sort((a, b) => b.positiveScore - a.positiveScore);
  const sortedByNegative = [...(results || [])].sort((a, b) => b.negativeScore - a.negativeScore);

  return (
    <div>
      <div className="d-flex justify-content-between align-items-center my-3">
        <h2>Sentiment Analysis Results</h2>
        <RoleGuard exclude={["Viewer"]}>
          <div>
            <button className="btn btn-primary me-2" onClick={() => runAnalysis(false)} disabled={running}>
              {running ? "Running..." : "Run Analysis"}
            </button>
            <button className="btn btn-outline-primary" onClick={() => runAnalysis(true)} disabled={running}>
              Reanalyse
            </button>
          </div>
        </RoleGuard>
      </div>

      <AnalysisFilters projectId={projectId} filters={filters} onChange={setFilters} rating />

      {!summary || summary.analysedReviews === 0 ? (
        <EmptyState title="No analysed reviews yet" description="Run analysis to see sentiment results." />
      ) : (
        <>
          <div className="row g-3 mb-4">
            <div className="col-md-3"><div className="card text-center p-3"><div className="fs-4 fw-bold">{summary.totalReviews}</div><div className="text-muted">Total Reviews</div></div></div>
            <div className="col-md-3"><div className="card text-center p-3"><div className="fs-4 fw-bold">{summary.analysedReviews}</div><div className="text-muted">Analysed</div></div></div>
            <div className="col-md-3"><div className="card text-center p-3"><div className="fs-4 fw-bold">{(summary.averageConfidence * 100).toFixed(1)}%</div><div className="text-muted small">Avg winning-label score</div><div className="text-muted" style={{fontSize:"0.65rem"}}>not a calibrated probability</div></div></div>
            <div className="col-md-3"><div className="card text-center p-3"><div className="fs-6">{summary.model?.name} v{summary.model?.version}</div><div className="text-muted">Model</div></div></div>
          </div>

          <div className="row g-3 mb-4">
            <div className="col-md-4">
              <div className="card p-3">
                <Doughnut
                  data={{
                    labels: ["Positive", "Negative", "Neutral"],
                    datasets: [{
                      data: [summary.positive.count, summary.negative.count, summary.neutral.count],
                      backgroundColor: ["#198754", "#dc3545", "#6c757d"],
                    }],
                  }}
                />
              </div>
            </div>
            <div className="col-md-8">
              <div className="card p-3">
                <table className="table mb-0">
                  <thead><tr><th>Sentiment</th><th>Count</th><th>Percentage</th></tr></thead>
                  <tbody>
                    <tr><td>Positive</td><td>{summary.positive.count}</td><td>{summary.positive.percentage}%</td></tr>
                    <tr><td>Negative</td><td>{summary.negative.count}</td><td>{summary.negative.percentage}%</td></tr>
                    <tr><td>Neutral</td><td>{summary.neutral.count}</td><td>{summary.neutral.percentage}%</td></tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <div className="row g-3">
            <div className="col-md-6">
              <h5>Most Positive Reviews</h5>
              <ul className="list-group">
                {sortedByPositive.slice(0, 5).map((r) => (
                  <li key={r.id} className="list-group-item">
                    <span className="badge text-bg-success me-2">{r.positiveScore.toFixed(2)}</span>
                    Review {r.reviewId.slice(0, 8)}…
                  </li>
                ))}
              </ul>
            </div>
            <div className="col-md-6">
              <h5>Most Negative Reviews</h5>
              <ul className="list-group">
                {sortedByNegative.slice(0, 5).map((r) => (
                  <li key={r.id} className="list-group-item">
                    <span className="badge text-bg-danger me-2">{r.negativeScore.toFixed(2)}</span>
                    Review {r.reviewId.slice(0, 8)}…
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
