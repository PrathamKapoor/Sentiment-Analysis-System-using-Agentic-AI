import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { securityFindingApi } from "../services/securityFindingApi";
import { useToast } from "../contexts/ToastContext";
import PermissionGuard from "./PermissionGuard";
import { analysisApi } from "../services/analysisApi";

export default function SecurityFindingsPanel({ projectId }) {
  const { showToast } = useToast();
  const [findings, setFindings] = useState([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [notes, setNotes] = useState({});
  const [indicators, setIndicators] = useState([]);
  const [incidents, setIncidents] = useState([]);

  const load = useCallback(async () => {
    try {
      const [findingResponse, indicatorResponse, incidentResponse] = await Promise.all([
        securityFindingApi.list(projectId), analysisApi.getSecurityIndicators(projectId), analysisApi.getSecurityIncidents(projectId),
      ]);
      setFindings(findingResponse.data.data.items || []);
      setIndicators(indicatorResponse.data.data.items || []);
      setIncidents(incidentResponse.data.data.items || []);
      setError("");
    } catch (reason) {
      setError(reason?.response?.data?.error?.message || "Could not load security findings.");
    }
  }, [projectId]);

  useEffect(() => { load(); }, [load]);

  const analyze = async () => {
    setBusy(true); setError("");
    try {
      const { data } = await securityFindingApi.analyze(projectId);
      showToast(`${data.data.created} new, ${data.data.updated} updated, ${data.data.stale} stale signal(s)`);
      await load();
    } catch (reason) {
      setError(reason?.response?.data?.error?.message || "Security analysis failed.");
    } finally { setBusy(false); }
  };

  const review = async (finding, status) => {
    setBusy(true); setError("");
    try {
      await securityFindingApi.review(projectId, finding.id, {
        status,
        analystNotes: notes[finding.id] || undefined,
      });
      await load();
    } catch (reason) {
      setError(reason?.response?.data?.error?.message || "Could not update finding.");
    } finally { setBusy(false); }
  };

  return (
    <section className="card mb-3" aria-labelledby="security-findings-title">
      <div className="card-body">
        <div className="d-flex justify-content-between align-items-start gap-3">
          <div>
            <h2 className="h5 mb-1" id="security-findings-title">Security signals</h2>
            <p className="text-muted small mb-0">Signals are matched to specific customer wording and stay unconfirmed until a person reviews the source.</p>
          </div>
          <PermissionGuard permission="review_security_findings">
            <button type="button" className="btn btn-outline-primary btn-sm" onClick={analyze} disabled={busy}>
              {busy ? "Working…" : "Analyze reviews"}
            </button>
          </PermissionGuard>
        </div>
        {error && <div className="alert alert-danger mt-3 mb-0" role="alert">{error}</div>}
        {!error && findings.length === 0 && <p className="text-muted small mt-3 mb-0">No findings yet. Run analysis to check existing reviews.</p>}
        {indicators.length > 0 && <section className="mt-3"><h3 className="h6">Observed indicators</h3><ul className="small">{indicators.slice(0, 30).map((item) => <li key={`${item.reviewId}-${item.type}-${item.value}`}>{item.type}: <code>{item.value}</code> · {item.status} · <Link to={`/projects/${projectId}/reviews?review=${item.reviewId}`}>evidence</Link></li>)}</ul><p className="small text-muted">Indicators are syntax observations only; no maliciousness or reputation lookup is performed.</p></section>}
        {incidents.length > 0 && <section className="mt-3"><h3 className="h6">Correlated patterns</h3>{incidents.map((item) => <article className="border rounded p-2 mb-2" key={`${item.indicatorType}-${item.indicator}`}><strong>{item.status.replaceAll("_", " ")}</strong> · {item.indicatorType}: <code>{item.indicator}</code><div className="small">{item.evidenceCount} reports across {item.sources.join(", ")}</div><p className="small text-muted mb-0">{item.verification}</p></article>)}</section>}
        <div className="mt-3 d-grid gap-2">
          {findings.map((finding) => (
            <article className="border rounded p-3" key={finding.id}>
              <div className="d-flex flex-wrap justify-content-between gap-2">
              <strong>{finding.findingType.replaceAll("_", " ")}</strong>
                <span className={`badge text-bg-${finding.status === "confirmed" ? "danger" : finding.status === "dismissed" ? "secondary" : "warning"}`}>
                  {finding.status.replaceAll("_", " ")}
                </span>
              </div>
              <div className="small text-muted">Category: {finding.category || "OTHER"}</div>
              <div className="small text-muted mt-1">{finding.severity} · {finding.confidence == null ? "confidence not calibrated" : `confidence ${(finding.confidence * 100).toFixed(0)}%`} · {finding.classificationMethod}</div>
              {finding.status === "stale" && <p className="small text-warning mt-2 mb-1">The source review changed or is no longer eligible. This stored evidence is historical; rerun analysis before reviewing it.</p>}
              {finding.evidence?.map((item, index) => <blockquote className="small border-start ps-2 mt-2 mb-1" key={`${finding.id}-${index}`}>{item.text}</blockquote>)}
              <Link className="small" to={`/projects/${projectId}/reviews?review=${finding.reviewId}`}>Open source review</Link>
              {finding.analystNotes && <p className="small mt-2 mb-0"><strong>Analyst note:</strong> {finding.analystNotes}</p>}
              {finding.status === "needs_review" && (
                <PermissionGuard permission="review_security_findings">
                  <label className="form-label small mt-2" htmlFor={`finding-notes-${finding.id}`}>Analyst notes (optional)</label>
                  <textarea
                    id={`finding-notes-${finding.id}`}
                    className="form-control form-control-sm"
                    maxLength={2000}
                    rows="2"
                    value={notes[finding.id] || ""}
                    onChange={(event) => setNotes({ ...notes, [finding.id]: event.target.value })}
                  />
                  <div className="d-flex gap-2 mt-2">
                    <button type="button" className="btn btn-sm btn-outline-danger" disabled={busy} onClick={() => review(finding, "confirmed")}>Confirm text match</button>
                    <button type="button" className="btn btn-sm btn-outline-secondary" disabled={busy} onClick={() => review(finding, "dismissed")}>Dismiss</button>
                  </div>
                </PermissionGuard>
              )}
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
