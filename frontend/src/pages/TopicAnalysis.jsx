import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { analysisApi } from "../services/analysisApi";
import { useToast } from "../contexts/ToastContext";
import LoadingSpinner from "../components/LoadingSpinner";
import ErrorAlert from "../components/ErrorAlert";
import EmptyState from "../components/EmptyState";
import RoleGuard from "../components/RoleGuard";

export default function TopicAnalysis() {
  const { projectId } = useParams();
  const { showToast } = useToast();
  const [topics, setTopics] = useState(null);
  const [selected, setSelected] = useState(null);
  const [selectedReviews, setSelectedReviews] = useState(null);
  const [error, setError] = useState(null);
  const [running, setRunning] = useState(false);
  const [topicCount, setTopicCount] = useState(8);

  const load = () => {
    analysisApi.listTopics(projectId).then((r) => setTopics(r.data.data.items)).catch(setError);
  };
  useEffect(load, [projectId]);

  const run = async () => {
    setRunning(true);
    try {
      await analysisApi.runTopics(projectId, { topicCount: Number(topicCount) });
      showToast("Topic analysis complete");
      load();
    } catch (err) {
      setError(err);
    } finally {
      setRunning(false);
    }
  };

  const openTopic = async (topicId) => {
    try {
      const [detail, reviews] = await Promise.all([
        analysisApi.getTopic(projectId, topicId),
        analysisApi.getTopicReviews(projectId, topicId),
      ]);
      setSelected(detail.data.data);
      setSelectedReviews(reviews.data.data.items);
    } catch (err) {
      setError(err);
    }
  };

  if (topics === null && !error) return <LoadingSpinner />;

  return (
    <div>
      <div className="d-flex justify-content-between align-items-center my-3">
        <h2>Topic Analysis</h2>
        <RoleGuard exclude={["Viewer"]}>
          <div className="d-flex gap-2 align-items-center">
            <label className="small mb-0">Topics:</label>
            <input
              type="number" min={1} max={50} className="form-control form-control-sm" style={{ width: 70 }}
              value={topicCount} onChange={(e) => setTopicCount(e.target.value)}
            />
            <button className="btn btn-primary" onClick={run} disabled={running}>
              {running ? "Running..." : "Run Topic Analysis"}
            </button>
          </div>
        </RoleGuard>
      </div>

      <ErrorAlert error={error} onDismiss={() => setError(null)} />

      {topics.length === 0 ? (
        <EmptyState title="No topics yet" description="Run topic analysis to group reviews by theme." />
      ) : (
        <div className="row g-3">
          {topics.map((t) => (
            <div className="col-md-4" key={t.id}>
              <div className="card p-3 h-100" role="button" onClick={() => openTopic(t.id)}>
                <h5>{t.topicName}</h5>
                <p className="text-muted mb-0">{t.reviewCount} reviews</p>
              </div>
            </div>
          ))}
        </div>
      )}

      {selected && (
        <div className="card mt-4">
          <div className="card-header d-flex justify-content-between">
            <span>{selected.topicName}</span>
            <button className="btn-close" onClick={() => { setSelected(null); setSelectedReviews(null); }} />
          </div>
          <div className="card-body">
            <p><strong>Reviews:</strong> {selected.reviewCount}</p>
            <p>
              <strong>Sentiment:</strong>{" "}
              {selected.sentimentDistribution &&
                `Positive ${selected.sentimentDistribution.positive} / Negative ${selected.sentimentDistribution.negative} / Neutral ${selected.sentimentDistribution.neutral} / Unanalysed ${selected.sentimentDistribution.unanalysed}`}
            </p>
            <h6>Related reviews</h6>
            <ul className="list-group">
              {(selectedReviews || []).slice(0, 10).map((r) => (
                <li key={r.id} className="list-group-item">{r.text}</li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
