import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { competitorApi } from "../services/competitorApi";

export default function CompetitorIntelligencePanel({ projectId }) {
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    competitorApi.get(projectId).then(({ data }) => {
      if (active) setResult(data.data);
    }).catch((reason) => {
      if (active) setError(reason?.response?.data?.error?.message || "Could not load competitor intelligence.");
    });
    return () => { active = false; };
  }, [projectId]);

  return (
    <section className="card mb-3" aria-labelledby="competitor-intelligence-title">
      <div className="card-body">
        <h2 className="h5 mb-1" id="competitor-intelligence-title">Competitor mentions and switching signals</h2>
        <p className="text-muted small">Matches configured competitor phrases in eligible project feedback. A switching signal requires explicit language naming that competitor as the destination.</p>
        {error && <div className="alert alert-danger mb-0" role="alert">{error}</div>}
        {!error && !result && <p className="small text-muted mb-0" role="status">Loading competitor evidence…</p>}
        {result && result.summary.competitors === 0 && <p className="small text-muted mb-0">No configured competitor mentions found. Add competitor terms in Product identity and keywords.</p>}
        {result && result.summary.competitors > 0 && <>
          <p className="small mb-2">{result.summary.mentions} review/competitor match(es) · {result.summary.switchingIntent} explicit switching signal(s) · {result.summary.reviewsScanned} eligible reviews scanned</p>
          <div className="d-grid gap-2">
            {result.items.slice(0, 20).map((item) => (
              <article className="border rounded p-3" key={`${item.reviewId}-${item.competitor}`}>
                <div className="d-flex flex-wrap justify-content-between gap-2">
                  <strong>{item.competitor}</strong>
                  <span className={`badge text-bg-${item.switchingIntent ? "warning" : "secondary"}`}>{item.switchingIntent ? "Explicit switching phrase" : "Mention"}</span>
                </div>
                <blockquote className="small border-start ps-2 mt-2 mb-1">{item.evidence.map((evidence) => evidence.text).join(", ")}</blockquote>
                {item.switchingEvidence.map((evidence, index) => <div className="small" key={index}><strong>Switching wording:</strong> {evidence.text}</div>)}
                {item.reason && <div className="small"><strong>Stated reason:</strong> {item.reason.text}</div>}
                <div className="small text-muted mt-1">{item.source || "Unknown source"}{item.sentiment ? ` · ${item.sentiment} sentiment` : " · sentiment not analyzed"}</div>
                <Link className="small" to={`/projects/${projectId}/reviews?review=${item.reviewId}`}>Open source review</Link>
              </article>
            ))}
          </div>
          {result.items.length > 20 && <p className="small text-muted mt-2 mb-0">Showing 20 of {result.summary.mentions} review/competitor matches. Configure specific competitor terms to focus this evidence view.</p>}
          {result.truncated && <p className="small text-muted mt-2 mb-0">The evidence list is capped at {result.resultLimit} matches. Summary counts cover all scanned reviews.</p>}
          <details className="small mt-3"><summary>Method and limitations</summary><ul className="mt-2">{result.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}</ul></details>
        </>}
      </div>
    </section>
  );
}
