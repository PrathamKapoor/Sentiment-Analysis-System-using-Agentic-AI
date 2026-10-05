import { useCallback, useEffect, useState } from "react";
import { analysisApi } from "../services/analysisApi";
import { Link } from "react-router-dom";

export default function TemporalIntelligencePanel({ projectId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [sources, themes, anomalies, rootCause] = await Promise.all([
        analysisApi.getSourceStatistics(projectId),
        analysisApi.getEmergingThemes(projectId, { days: 7, baselineDays: 7 }),
        analysisApi.getAnomalies(projectId, { days: 7, baselineDays: 7 }),
        analysisApi.getRootCauseEvidence(projectId, { days: 7, baselineDays: 7 }),
      ]);
      setData({ sources: sources.data.data, themes: themes.data.data, anomalies: anomalies.data.data, rootCause: rootCause.data.data });
    } catch {
      setError("Temporal intelligence could not be loaded.");
    } finally { setLoading(false); }
  }, [projectId]);
  useEffect(() => { load(); }, [load]);

  const detectDuplicates = async () => {
    setWorking(true);
    setError("");
    try { await analysisApi.detectDuplicates(projectId); await load(); }
    catch { setError("Duplicate check failed. Existing source records were left unchanged."); }
    finally { setWorking(false); }
  };

  return (
    <section className="card mb-3" aria-labelledby="temporal-intelligence-heading">
      <div className="card-body">
        <div className="d-flex justify-content-between align-items-start gap-3 flex-wrap">
          <div><span className="page-kicker">Evidence intelligence</span><h2 className="h5" id="temporal-intelligence-heading">Sources and changing themes</h2></div>
          <button type="button" className="btn btn-outline-primary btn-sm" disabled={working || loading} onClick={detectDuplicates}>{working ? "Checking…" : "Check exact duplicates"}</button>
        </div>
        {error && <p className="alert alert-warning py-2" role="alert">{error}</p>}
        {loading ? <p role="status">Loading source and period comparisons…</p> : data && <>
          <p className="small text-muted">{data.sources.recordCount} source records · {data.sources.canonicalEvidenceCount} canonical evidence groups · {data.sources.duplicateRelationshipCount} exact links. Source records remain independently traceable.</p>
          {(data.themes.comparison.truncated || data.anomalies.comparison.truncated) && <p className="alert alert-warning py-2 small">One or more time windows exceeded the analysis sample limit. Full eligible window totals are shown in the period metadata; signal counts use the newest bounded sample.</p>}
          <div className="table-responsive"><table className="table table-sm"><thead><tr><th>Source</th><th>Records</th><th>Canonical evidence</th><th>Sampling note</th></tr></thead><tbody>
            {data.sources.sources.map((source) => <tr key={`${source.sourceType}-${source.sourceId}`}><th>{source.sourceType}</th><td>{source.recordCount}</td><td>{source.canonicalEvidenceCount}</td><td>{source.biasNote}</td></tr>)}
            {!data.sources.sources.length && <tr><td colSpan="4">No eligible source records yet.</td></tr>}
          </tbody></table></div>
          <div className="row g-3">
            <div className="col-lg-6"><h3 className="h6">Emerging themes · previous 7 days vs current 7 days</h3>{data.themes.items.length ? <ul>{data.themes.items.slice(0, 8).map((item) => <li key={item.theme}><strong>{item.theme}</strong>: {item.baselineCount} → {item.currentCount} ({item.rateRatio ? `${item.rateRatio}× rate` : "newly observed"})<span className="d-block small">Evidence: {(item.supportingEvidenceIds || []).slice(0, 3).map((id) => <Link className="me-2" key={id} to={`/projects/${projectId}/reviews?review=${encodeURIComponent(id)}`}>{id}</Link>)}</span></li>)}</ul> : <p className="small text-muted">No theme passed the configured minimum evidence and period-change threshold.</p>}</div>
            <div className="col-lg-6"><h3 className="h6">Volume/category anomalies · period comparison</h3>{data.anomalies.items.length ? <ul>{data.anomalies.items.slice(0, 8).map((item) => <li key={item.metric}><strong>{item.metric}</strong>: {item.baselineCount} → {item.currentCount}<span className="d-block small">Evidence: {(item.evidenceIds || []).slice(0, 3).map((id) => <Link className="me-2" key={id} to={`/projects/${projectId}/reviews?review=${encodeURIComponent(id)}`}>{id}</Link>)}</span></li>)}</ul> : <p className="small text-muted">No period-rate change passed the configured threshold.</p>}</div>
          </div>
          <details className="small mt-2"><summary>Comparison periods and limitations</summary><p className="mb-1">Baseline: {data.themes.comparison.baselineFrom} to {data.themes.comparison.baselineTo} ({data.themes.comparison.baselineEligibleCount} eligible records). Current: {data.themes.comparison.currentFrom} to {data.themes.comparison.currentTo} ({data.themes.comparison.currentEligibleCount} eligible records).</p><ul>{[...data.themes.limitations, ...data.anomalies.limitations].filter((item, index, all) => all.indexOf(item) === index).map((item) => <li key={item}>{item}</li>)}</ul></details>
          {data.rootCause.claims.length > 0 && <section className="mt-3"><h3 className="h6">Evidence layers · no automatic causal conclusion</h3><ul>{data.rootCause.claims.slice(0, 8).map((claim, index) => <li key={`${claim.type}-${index}`}><strong>{claim.type}:</strong> {claim.claim} <span className="text-muted">({claim.evidenceIds.length} evidence IDs)</span><span className="d-block small">{claim.evidenceIds.slice(0, 3).map((id) => <Link className="me-2" key={id} to={`/projects/${projectId}/reviews?review=${encodeURIComponent(id)}`}>{id}</Link>)}</span></li>)}</ul><p className="small text-muted mb-0">Claims reference stored reviews. A version overlap is correlation; hypotheses require human validation.</p></section>}
          <p className="small text-muted mb-0">These deterministic comparisons use dated, eligible reviews. They are not significance tests; source composition and sampling bias remain relevant.</p>
        </>}
      </div>
    </section>
  );
}
