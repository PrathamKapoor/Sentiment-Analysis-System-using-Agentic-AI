import { useEffect, useState } from "react";
import client from "../api/client";
import ErrorAlert from "./ErrorAlert";

export default function DatasetProfilePanel({ datasetId }) {
  const [profile, setProfile] = useState(null);
  const [error, setError] = useState(null);
  const [expandedFlag, setExpandedFlag] = useState(null);

  useEffect(() => {
    if (!datasetId) return;
    setProfile(null);
    setError(null);
    client.get(`/datasets/${datasetId}/profile`)
      .then((r) => setProfile(r.data.data.profile))
      .catch(setError);
  }, [datasetId]);

  if (error) return <ErrorAlert error={error} onDismiss={() => setError(null)} />;
  if (!profile) return <div className="text-muted small">Loading profile...</div>;

  const badgeColor = profile.severity === "error" ? "danger" : profile.severity === "warning" ? "warning" : "info";

  return (
    <div className="mt-3">
      <div className="d-flex align-items-center gap-2 mb-2">
        <h6 className="mb-0">Dataset Profile</h6>
        <span className={`badge text-bg-${badgeColor}`}>{profile.severity}</span>
      </div>

      <div className="row g-2 mb-3">
        <div className="col-md-2"><div className="card text-center p-2"><div className="fw-bold">{profile.rowCount}</div><div className="text-muted small">Rows</div></div></div>
        <div className="col-md-2"><div className="card text-center p-2"><div className="fw-bold text-success">{profile.validRowCount}</div><div className="text-muted small">Usable</div></div></div>
        <div className="col-md-2"><div className="card text-center p-2"><div className="fw-bold text-warning">{profile.duplicateRowCount}</div><div className="text-muted small">Duplicates</div></div></div>
        <div className="col-md-2"><div className="card text-center p-2"><div className="fw-bold text-danger">{profile.emptyTextCount}</div><div className="text-muted small">Empty</div></div></div>
        <div className="col-md-2"><div className="card text-center p-2"><div className="fw-bold">{profile.averageTextLength ?? "—"}</div><div className="text-muted small">Avg chars</div></div></div>
        <div className="col-md-2"><div className="card text-center p-2"><div className="fw-bold">{profile.ratingTextMismatchSampleCount ?? 0}</div><div className="text-muted small">Rating/text mismatch</div></div></div>
      </div>

      <div className="row g-3 mb-3">
        <div className="col-md-4">
          <div className="card p-2">
            <strong className="small">Language</strong>
            <div className="small text-muted">Heuristic: Latin-script vs non-Latin. Not language detection.</div>
            <ul className="list-unstyled mb-0 small mt-1">
              {Object.entries(profile.languageDistribution || {}).map(([k, v]) => (
                <li key={k}>{k}: {v}</li>
              ))}
            </ul>
          </div>
        </div>
        <div className="col-md-4">
          <div className="card p-2">
            <strong className="small">Rating distribution</strong>
            {profile.ratingDistribution?.mean != null ? (
              <div className="small">
                <div>Mean: {profile.ratingDistribution.mean} · Median: {profile.ratingDistribution.median}</div>
                <div>Range: {profile.ratingDistribution.min ?? "—"}–{profile.ratingDistribution.max ?? "—"} · Missing: {profile.ratingDistribution.missing}</div>
                <ul className="list-unstyled mb-0 mt-1">
                  {Object.entries(profile.ratingDistribution.counts || {}).sort((a,b)=>Number(a[0])-Number(b[0])).map(([k,v])=> (
                    <li key={k}>★ {k}: {v}</li>
                  ))}
                </ul>
              </div>
            ) : (
              <div className="small text-muted">No usable numeric ratings.</div>
            )}
          </div>
        </div>
        <div className="col-md-4">
          <div className="card p-2">
            <strong className="small">Text quality flags</strong>
            {Object.keys(profile.qualityFlags?.counts || {}).length === 0 ? (
              <div className="small text-muted">No quality flags.</div>
            ) : (
              <ul className="list-unstyled mb-0 small mt-1">
                {Object.entries(profile.qualityFlags.counts).map(([k, v]) => (
                  <li key={k}>
                    <button className="btn btn-link btn-sm p-0" onClick={() => setExpandedFlag(expandedFlag === k ? null : k)}>
                      {k}: {v} {profile.qualityFlags.samples?.[k]?.length ? "▸" : ""}
                    </button>
                    {expandedFlag === k && profile.qualityFlags.samples?.[k] && (
                      <ul className="ms-3">
                        {profile.qualityFlags.samples[k].slice(0, 3).map((s, i) => (
                          <li key={i}>row {s.row} — {s.flags?.join(", ")}</li>
                        ))}
                      </ul>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>

      {profile.ratingTextMismatches?.some(b => b.samples?.length) && (
        <div className="card p-2 mb-3">
          <strong className="small">Rating/text mismatches (VADER vs rating)</strong>
          <div className="small text-muted mb-1">Strong compound vs rating disagreement. Labelled for review — not declared wrong (sarcasm / annotation noise possible).</div>
          {profile.ratingTextMismatches.map((bucket) => bucket.samples?.length ? (
            <div key={bucket.type} className="small mb-1">
              <span className="fw-bold">{bucket.type.replace(/_/g, " ")}:</span> {bucket.samples.length} sample(s)
              <ul className="mb-0">
                {bucket.samples.map((s, i) => (
                  <li key={i}>row {s.row} — rating {s.rating} ({s.ratingLabel}) vs text compound {s.textCompound} ({s.textLabel})</li>
                ))}
              </ul>
            </div>
          ) : null)}
        </div>
      )}

      {profile.warnings?.length > 0 && (
        <div className="alert alert-warning small mb-2">
          <strong>Warnings</strong>
          <ul className="mb-0">
            {profile.warnings.map((w, i) => <li key={i}>{w}</li>)}
          </ul>
        </div>
      )}
      {profile.info?.length > 0 && (
        <div className="alert alert-info small mb-0">
          <ul className="mb-0">
            {profile.info.map((w, i) => <li key={i}>{w}</li>)}
          </ul>
        </div>
      )}
    </div>
  );
}
