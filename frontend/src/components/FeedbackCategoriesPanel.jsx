import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { feedbackIntelligenceApi } from "../services/feedbackIntelligenceApi";

export default function FeedbackCategoriesPanel({ projectId }) {
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    feedbackIntelligenceApi.categories(projectId).then(({ data }) => {
      if (active) setResult(data.data);
    }).catch((reason) => {
      if (active) setError(reason?.response?.data?.error?.message || "Could not load feedback categories.");
    });
    return () => { active = false; };
  }, [projectId]);

  return (
    <section className="card mb-3" aria-labelledby="feedback-categories-title">
      <div className="card-body">
        <h2 className="h5 mb-1" id="feedback-categories-title">Feedback categories</h2>
        <p className="text-muted small">Deterministic phrase matches over eligible stored reviews. A review can match more than one category.</p>
        {error && <div className="alert alert-danger mb-0" role="alert">{error}</div>}
        {!error && !result && <p className="small text-muted mb-0" role="status">Loading feedback categories…</p>}
        {result && result.summary.reviewsScanned === 0 && <p className="small text-muted mb-0">No eligible reviews are available for categorization.</p>}
        {result && result.summary.reviewsScanned > 0 && <>
          <p className="small">{result.summary.classifiedReviews} of {result.summary.reviewsScanned} scanned reviews matched at least one rule. Categories may overlap.</p>
          <div className="d-flex gap-2 flex-wrap mb-3">
            {Object.entries(result.summary.categoryCounts).sort(([a], [b]) => a.localeCompare(b)).map(([category, count]) => (
              <span className="badge text-bg-light border" key={category}>{category.replaceAll("_", " ")}: {count}</span>
            ))}
          </div>
          <div className="d-grid gap-2">
            {result.items.slice(0, 15).map((item) => (
              <article className="border rounded p-3" key={item.reviewId}>
                <div className="d-flex flex-wrap gap-2 mb-2">
                  {item.categories.map((entry) => <span className="badge text-bg-secondary" key={entry.category}>{entry.category.replaceAll("_", " ")}</span>)}
                </div>
                {item.categories.flatMap((entry) => entry.evidence.map((evidence, index) => (
                  <blockquote className="small border-start ps-2 mb-1" key={`${entry.category}-${index}`}><strong>{entry.category}:</strong> {evidence.text}</blockquote>
                )))}
                <Link className="small" to={`/projects/${projectId}/reviews?review=${item.reviewId}`}>Open source review</Link>
              </article>
            ))}
          </div>
          {result.truncated && <p className="small text-muted mt-2 mb-0">The evidence list is capped at {result.resultLimit} reviews; summary counts include all {result.summary.reviewsScanned} scanned reviews.</p>}
          <details className="small mt-3"><summary>Method and limitations</summary><ul className="mt-2">{result.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}</ul></details>
        </>}
      </div>
    </section>
  );
}
