export default function VaderBreakdown({ breakdown, compound, modelName, modelVersion }) {
  if (!breakdown) return <div className="text-muted small">No VADER breakdown stored for this review (analysed before explainability was added, or manually corrected).</div>;

  const tokens = breakdown.tokens || [];
  const contributing = breakdown.contributingTerms || { positive: [], negative: [] };

  return (
    <div className="small">
      <div className="mb-2">
        <span className="badge text-bg-dark me-2">{modelName || "vader"} v{modelVersion || "3.3.2"}</span>
        {compound != null && <span className="text-muted">compound {compound}</span>}
      </div>
      <div className="alert alert-light border small mb-2">
        This is a <strong>VADER lexicon surface</strong>, not a causal proof. Each matched token shows its lexicon valence; unmatched tokens were not in VADER's 7,500-word lexicon. VADER's sentence-level modifiers — negation (“not good”), boosters (“very”), capitalization, and punctuation emphasis — are <em>not</em> reflected in per-token valence. For example, “good” still shows +1.9 inside “not good” even though that sentence's compound is negative.
      </div>
      {(contributing.positive?.length > 0 || contributing.negative?.length > 0) ? (
        <div className="mb-2">
          <strong>Lexicon terms pointing toward the winning label</strong>
          <div className="text-muted small">Tokens whose lexicon valence aligns with the assigned label (not a proof that the word caused the label).</div>
          {contributing.positive?.length > 0 && (
            <div className="mt-1">
              <span className="badge text-bg-success me-1">positive</span>
              {contributing.positive.map((t, i) => (
                <span key={i} className="badge bg-light text-dark border me-1">{t.token} ({t.valence > 0 ? `+${t.valence}` : t.valence})</span>
              ))}
            </div>
          )}
          {contributing.negative?.length > 0 && (
            <div className="mt-1">
              <span className="badge text-bg-danger me-1">negative</span>
              {contributing.negative.map((t, i) => (
                <span key={i} className="badge bg-light text-dark border me-1">{t.token} ({t.valence})</span>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div className="text-muted mb-2">No lexicon-matched tokens aligned with the winning label (common for short neutral texts).</div>
      )}
      <details>
        <summary className="small">All tokens ({tokens.length})</summary>
        <div className="mt-1 d-flex flex-wrap gap-1">
          {tokens.map((t, i) => (
            <span key={i} className={`badge ${t.matched ? (t.valence > 0 ? "text-bg-success" : t.valence < 0 ? "text-bg-danger" : "text-bg-secondary") : "bg-light text-muted border"}`}>
              {t.token} {t.matched ? `(${t.valence > 0 ? `+${t.valence}` : t.valence})` : ""}
            </span>
          ))}
        </div>
      </details>
    </div>
  );
}
