import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import ErrorAlert from "../components/ErrorAlert";
import { useAuth } from "../contexts/AuthContext";
import { investigationApi } from "../services/investigationApi";

const ACTIVE = new Set(["QUEUED", "RUNNING", "WAITING"]);
const CANCELLABLE = new Set(["QUEUED", "WAITING"]);

export default function InvestigationWorkspace() {
  const { projectId } = useParams();
  const { hasPermission } = useAuth();
  const [question, setQuestion] = useState("");
  const [items, setItems] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const loadList = useCallback(async () => {
    try {
      const response = await investigationApi.list(projectId);
      const next = response.data.data.items || [];
      setItems(next);
      if (!selectedId && next.length) setSelectedId(next[0].id);
    } catch (reason) { setError(reason); }
  }, [projectId, selectedId]);

  const loadOne = useCallback(async (id) => {
    if (!id) { setSelected(null); return; }
    try {
      const response = await investigationApi.get(projectId, id);
      setSelected(response.data.data);
    } catch (reason) { setError(reason); }
  }, [projectId]);

  useEffect(() => { loadList(); }, [loadList]);
  useEffect(() => { loadOne(selectedId); }, [loadOne, selectedId]);
  useEffect(() => {
    if (!selected || !ACTIVE.has(selected.status)) return undefined;
    const timer = window.setInterval(() => { loadOne(selected.id); loadList(); }, 2500);
    return () => window.clearInterval(timer);
  }, [selected, loadList, loadOne]);

  const create = async (event) => {
    event.preventDefault();
    setSubmitting(true); setError(null);
    try {
      const response = await investigationApi.create(projectId, { question: question.trim() });
      const row = response.data.data;
      setQuestion(""); setSelectedId(row.id); setSelected(row); await loadList();
    } catch (reason) { setError(reason); }
    finally { setSubmitting(false); }
  };

  const cancel = async () => {
    if (!selected) return;
    try { await investigationApi.cancel(projectId, selected.id); await loadOne(selected.id); await loadList(); }
    catch (reason) { setError(reason); }
  };

  const reviewFinding = async (finding, status) => {
    try {
      await investigationApi.reviewFinding(projectId, selected.id, finding.id, { status });
      await loadOne(selected.id);
    } catch (reason) { setError(reason); }
  };

  return (
    <div className="project-workspace-page">
      <div className="page-header my-3"><div><span className="page-kicker">Evidence-grounded analysis</span><h1>Investigations</h1><p>Ask a question about already-ingested project evidence. Investigations do not collect from the web.</p></div></div>
      <ErrorAlert error={error} onDismiss={() => setError(null)} />
      <div className="row g-3">
        <div className="col-lg-4">
          <form className="card card-body mb-3" onSubmit={create}>
            <label htmlFor="investigation-question" className="form-label fw-semibold">Investigation question</label>
            <textarea id="investigation-question" className="form-control mb-3" rows="4" maxLength={2000} minLength={3} required value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Why did negative sentiment increase this week?" />
            <button className="btn btn-primary" disabled={submitting}>{submitting ? "Queueing…" : "Start investigation"}</button>
            <p className="small text-muted mt-2 mb-0">A worker must be running for queued investigations to start. The deterministic summary remains available when the LLM is not configured.</p>
          </form>
          <div className="list-group" aria-label="Previous investigations">
            {items.map((item) => <button key={item.id} type="button" className={`list-group-item list-group-item-action${selectedId === item.id ? " active" : ""}`} onClick={() => setSelectedId(item.id)}><span className="d-block fw-semibold">{item.question}</span><small>{item.status} · {new Date(item.createdAt).toLocaleString()}</small></button>)}
            {!items.length && <div className="list-group-item text-muted">No investigations yet.</div>}
          </div>
        </div>
        <div className="col-lg-8">
          {!selected ? <div className="card card-body text-muted">Choose or start an investigation.</div> : <article className="card card-body">
            <div className="d-flex justify-content-between gap-3 flex-wrap"><div><span className="badge text-bg-secondary">{selected.status}</span><h2 className="h5 mt-2">{selected.question}</h2><small className="text-muted">Created {new Date(selected.createdAt).toLocaleString()} · attempts {selected.attemptCount}/{selected.maxAttempts}</small></div>{CANCELLABLE.has(selected.status) && <button className="btn btn-outline-danger btn-sm align-self-start" onClick={cancel}>Cancel</button>}</div>
            {selected.status === "RUNNING" && <p className="small text-muted">This job has been claimed by a worker and cannot be cancelled mid-call.</p>}
            {selected.status === "QUEUED" && <p role="status" className="alert alert-info mt-3">Queued. The worker will claim this job when available.</p>}
            {selected.result?.answer && <div className="alert alert-light border mt-3"><strong>Result</strong><p className="mb-1" style={{ whiteSpace: "pre-wrap" }}>{selected.result.answer}</p><small>{selected.result.semanticSynthesis?.available ? "LLM structured synthesis" : "Deterministic evidence summary; semantic synthesis unavailable"}</small></div>}
            {selected.result?.sourceComposition?.length > 0 && <section><h3 className="h6">Sources consulted</h3><ul>{selected.result.sourceComposition.map((source) => <li key={`${source.sourceType}-${source.sourceId}`}>{source.sourceType}: {source.recordCount} records · {source.biasNote}</li>)}</ul></section>}
            {selected.findings?.length > 0 && <section><h3 className="h6">Findings</h3>{selected.findings.map((finding) => <div className="border rounded p-3 mb-2" key={finding.id}><div className="d-flex gap-2 flex-wrap"><strong>{finding.status}</strong><span>{finding.findingType}</span><span className="text-muted">Review: {finding.reviewState}</span></div><p className="my-2">{finding.claim}</p>{finding.recommendedAction && <p><strong>Suggested action:</strong> {finding.recommendedAction}</p>}<div className="small">Evidence: {(finding.evidenceIds || []).map((id) => <Link className="me-2" key={id} to={`/projects/${projectId}/reviews?review=${encodeURIComponent(id)}`}>{id}</Link>)}</div>{hasPermission("approve_ai_output") && finding.reviewState === "NEEDS_REVIEW" && <div className="mt-2 d-flex gap-2"><button className="btn btn-sm btn-success" onClick={() => reviewFinding(finding, "ACCEPTED")}>Accept</button><button className="btn btn-sm btn-outline-danger" onClick={() => reviewFinding(finding, "REJECTED")}>Reject</button></div>}</div>)}</section>}
            {selected.activities?.length > 0 && <section><h3 className="h6">Tool activity</h3><ul>{selected.activities.map((event) => <li key={event.id}>{event.tool} — {event.summary} ({event.status})</li>)}</ul></section>}
            {selected.result?.limitations?.length > 0 && <section><h3 className="h6">Limitations</h3><ul>{selected.result.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}</ul></section>}
            {selected.lastError && <p className="alert alert-danger">{selected.lastError}</p>}
          </article>}
        </div>
      </div>
    </div>
  );
}
