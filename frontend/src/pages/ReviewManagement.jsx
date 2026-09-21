import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { reviewApi } from "../services/reviewApi";
import { useToast } from "../contexts/ToastContext";
import DataTable from "../components/DataTable";
import ErrorAlert from "../components/ErrorAlert";
import FormInput from "../components/FormInput";
import PermissionGuard from "../components/PermissionGuard";
import VaderBreakdown from "../components/VaderBreakdown";

export default function ReviewManagement() {
  const { projectId } = useParams();
  const { showToast } = useToast();
  const [reviews, setReviews] = useState(null);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState("");
  const [editingId, setEditingId] = useState(null);
  const [editText, setEditText] = useState("");
  const [correctingId, setCorrectingId] = useState(null);
  const [correctionLabel, setCorrectionLabel] = useState("positive");
  const [correctionReason, setCorrectionReason] = useState("");
  const [aspectPanelReview, setAspectPanelReview] = useState(null);
  const [aspectPanelData, setAspectPanelData] = useState(null);
  const [breakdownReview, setBreakdownReview] = useState(null);

  const load = () => {
    reviewApi.list(projectId, { search: search || undefined }).then((r) => setReviews(r.data.data.items)).catch(setError);
  };
  useEffect(load, [projectId, search]);

  const onMarkSpam = async (review) => {
    try {
      await reviewApi.markSpam(review.id, !review.isSpam);
      load();
    } catch (err) {
      setError(err);
    }
  };

  const onRemoveDuplicateFlag = async (review) => {
    try {
      await reviewApi.update(review.id, { isDuplicate: !review.isDuplicate });
      load();
    } catch (err) {
      setError(err);
    }
  };

  const startEdit = (review) => {
    setEditingId(review.id);
    setEditText(review.text);
  };

  const saveEdit = async (review) => {
    try {
      await reviewApi.update(review.id, { text: editText });
      showToast("Review updated");
      setEditingId(null);
      load();
    } catch (err) {
      setError(err);
    }
  };

  const startCorrection = (review) => {
    setCorrectingId(review.id);
    setCorrectionLabel(review.sentiment?.sentimentLabel || "positive");
    setCorrectionReason("");
  };

  const confirmCorrection = async (review) => {
    try {
      await reviewApi.correctSentiment(review.id, correctionLabel, correctionReason || undefined);
      showToast("Sentiment corrected");
      setCorrectingId(null);
      load();
    } catch (err) {
      setError(err);
    }
  };

  const toggleAspectPanel = async (review) => {
    if (aspectPanelReview === review.id) {
      setAspectPanelReview(null);
      setAspectPanelData(null);
      return;
    }
    setAspectPanelReview(review.id);
    try {
      const resp = await reviewApi.getAspects(review.id);
      setAspectPanelData(resp.data.data.items);
    } catch (err) {
      setError(err);
    }
  };

  if (reviews === null && !error) return null;

  return (
    <div>
      <h2 className="my-3">Reviews</h2>
      <ErrorAlert error={error} onDismiss={() => setError(null)} />

      <FormInput placeholder="Search reviews..." value={search} onChange={(e) => setSearch(e.target.value)} />

      <DataTable
        columns={[
          {
            key: "text", header: "Text",
            render: (r) =>
              editingId === r.id ? (
                <div className="d-flex gap-2">
                  <input className="form-control form-control-sm" value={editText} onChange={(e) => setEditText(e.target.value)} />
                  <button className="btn btn-sm btn-primary" onClick={() => saveEdit(r)}>Save</button>
                  <button className="btn btn-sm btn-outline-secondary" onClick={() => setEditingId(null)}>Cancel</button>
                </div>
              ) : (
                <span onDoubleClick={() => startEdit(r)}>{r.text}</span>
              ),
          },
          { key: "source", header: "Source" },
          { key: "rating", header: "Rating" },
          { key: "reviewDate", header: "Date" },
          {
            key: "sentiment", header: "Sentiment",
            render: (r) =>
              r.sentiment ? (
                <>
                  <span className={`badge text-bg-${
                    r.sentiment.sentimentLabel === "positive" ? "success"
                      : r.sentiment.sentimentLabel === "negative" ? "danger" : "secondary"
                  } me-1`}>
                    {r.sentiment.sentimentLabel}
                  </span>
                  <span className="text-muted small">{(r.sentiment.confidenceScore * 100).toFixed(0)}%</span>
                  {r.sentiment.isManuallyCorrected && <span className="badge text-bg-info ms-1">corrected</span>}
                </>
              ) : (
                <span className="text-muted small">not analysed</span>
              ),
          },
          {
            key: "aspects", header: "Aspects",
            render: (r) => (
              <button className="btn btn-sm btn-outline-secondary" onClick={() => toggleAspectPanel(r)}>
                {aspectPanelReview === r.id ? "Hide" : "View"}
              </button>
            ),
          },
          {
            key: "explain", header: "Explain",
            render: (r) => r.sentiment ? (
              <button className="btn btn-sm btn-outline-dark" onClick={() => setBreakdownReview(breakdownReview === r.id ? null : r.id)}>
                {breakdownReview === r.id ? "Hide" : "Why?"}
              </button>
            ) : null,
          },
          {
            key: "flags", header: "Flags",
            render: (r) => (
              <>
                {r.isSpam && <span className="badge text-bg-danger me-1">Spam</span>}
                {r.isDuplicate && <span className="badge text-bg-warning">Duplicate</span>}
              </>
            ),
          },
          {
            key: "actions", header: "",
            render: (r) =>
              correctingId === r.id ? (
                <div className="d-flex flex-column gap-1" style={{ minWidth: 220 }}>
                  <div className="btn-group btn-group-sm">
                    {["positive", "negative", "neutral"].map((label) => (
                      <button
                        key={label}
                        className={`btn ${correctionLabel === label ? "btn-primary" : "btn-outline-primary"}`}
                        onClick={() => setCorrectionLabel(label)}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                  <input
                    className="form-control form-control-sm" placeholder="Reason (optional)"
                    value={correctionReason} onChange={(e) => setCorrectionReason(e.target.value)}
                  />
                  <div>
                    <button className="btn btn-sm btn-success me-1" onClick={() => confirmCorrection(r)}>Confirm</button>
                    <button className="btn btn-sm btn-outline-secondary" onClick={() => setCorrectingId(null)}>Cancel</button>
                  </div>
                </div>
              ) : (
                <PermissionGuard permission="correct_sentiment">
                  <button className="btn btn-sm btn-outline-secondary me-1" onClick={() => startEdit(r)}>Edit</button>
                  <button className="btn btn-sm btn-outline-danger me-1" onClick={() => onMarkSpam(r)}>
                    {r.isSpam ? "Unmark Spam" : "Mark Spam"}
                  </button>
                  <button className="btn btn-sm btn-outline-warning me-1" onClick={() => onRemoveDuplicateFlag(r)}>
                    {r.isDuplicate ? "Unmark Duplicate" : "Mark Duplicate"}
                  </button>
                  <button className="btn btn-sm btn-outline-info" onClick={() => startCorrection(r)}>
                    Correct Sentiment
                  </button>
                </PermissionGuard>
              ),
          },
        ]}
        rows={reviews}
        emptyMessage="No reviews yet — connect a source or upload a dataset"
      />

      {breakdownReview && (() => {
        const r = reviews.find((x) => x.id === breakdownReview);
        if (!r?.sentiment) return null;
        return (
          <div className="card mt-3">
            <div className="card-header d-flex justify-content-between">
              <span>Why this sentiment? — VADER explanation</span>
              <button className="btn-close" onClick={() => setBreakdownReview(null)} />
            </div>
            <div className="card-body">
              <VaderBreakdown breakdown={r.sentiment.vaderBreakdown} compound={r.sentiment.compoundScore} modelName={r.sentiment.modelName} modelVersion={r.sentiment.modelVersion} />
              <div className="small text-muted mt-2">
                Label: {r.sentiment.sentimentLabel} · positive {r.sentiment.positiveScore} · negative {r.sentiment.negativeScore} · neutral {r.sentiment.neutralScore} · confidence {(r.sentiment.confidenceScore * 100).toFixed(0)}%
              </div>
            </div>
          </div>
        );
      })()}

      {aspectPanelReview && (
        <div className="card mt-3">
          <div className="card-header d-flex justify-content-between">
            <span>Detected aspects</span>
            <button className="btn-close" onClick={() => { setAspectPanelReview(null); setAspectPanelData(null); }} />
          </div>
          <div className="card-body">
            {aspectPanelData === null ? (
              <span className="text-muted">Loading...</span>
            ) : aspectPanelData.length === 0 ? (
              <span className="text-muted">No aspects detected for this review yet — run aspect analysis.</span>
            ) : (
              <ul className="list-group">
                {aspectPanelData.map((a) => (
                  <li key={a.id} className="list-group-item d-flex justify-content-between align-items-center">
                    <span>{a.aspectName}</span>
                    <span className={`badge text-bg-${a.sentimentLabel === "positive" ? "success" : a.sentimentLabel === "negative" ? "danger" : "secondary"}`}>
                      {a.sentimentLabel}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
