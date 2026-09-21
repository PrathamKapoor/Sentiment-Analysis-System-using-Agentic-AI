import { useEffect, useState } from "react";
import { evaluationApi } from "../services/evaluationApi";
import LoadingSpinner from "../components/LoadingSpinner";
import ErrorAlert from "../components/ErrorAlert";

export default function EvaluationPage() {
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    evaluationApi.getBenchmark().then((r) => setResult(r.data.data)).catch(setError).finally(() => setLoading(false));
  }, []);

  if (loading) return <LoadingSpinner />;
  if (error) return <ErrorAlert error={error} onDismiss={() => setError(null)} />;
  if (!result) return null;

  const { benchmarkId, benchmarkVersion, datasetSha256Prefix, model, sampleCount, metrics, confusionMatrix, evaluatedAt, classCounts } = result;

  return (
    <div>
      <h2 className="my-3">Sentiment Model Quality</h2>
      <div className="alert alert-info small">
        Benchmark performance on a small labelled fixture is a controlled diagnostic. It does not guarantee performance on your project's domain — always validate on your own data.
      </div>

      <div className="card p-3 mb-3">
        <div className="row g-3">
          <div className="col-md-3"><strong>Benchmark</strong><div className="text-muted small">{benchmarkId} v{benchmarkVersion}</div><div className="text-muted small">sha {datasetSha256Prefix || "—"}</div></div>
          <div className="col-md-3"><strong>Model</strong><div className="text-muted small">{model.name} v{model.version}</div></div>
          <div className="col-md-3"><strong>Samples</strong><div className="fs-5">{sampleCount}</div><div className="text-muted small">class counts: {Object.entries(classCounts || {}).map(([k,v])=>`${k}:${v}`).join(" ")}</div></div>
          <div className="col-md-3"><strong>Evaluated</strong><div className="text-muted small">{evaluatedAt ? new Date(evaluatedAt).toLocaleString() : "—"}</div></div>
        </div>
      </div>

      <div className="row g-2 mb-3">
        <div className="col-md-3"><div className="card text-center p-3"><div className="fs-4 fw-bold">{(metrics.accuracy * 100).toFixed(1)}%</div><div className="text-muted small">Accuracy ({metrics.correct}/{metrics.total})</div></div></div>
        <div className="col-md-3"><div className="card text-center p-3"><div className="fs-4 fw-bold">{(metrics.macroPrecision * 100).toFixed(1)}%</div><div className="text-muted small">Macro precision</div></div></div>
        <div className="col-md-3"><div className="card text-center p-3"><div className="fs-4 fw-bold">{(metrics.macroRecall * 100).toFixed(1)}%</div><div className="text-muted small">Macro recall</div></div></div>
        <div className="col-md-3"><div className="card text-center p-3"><div className="fs-4 fw-bold">{(metrics.macroF1 * 100).toFixed(1)}%</div><div className="text-muted small">Macro F1</div></div></div>
      </div>

      <div className="card p-3 mb-3">
        <h5>Per-class metrics</h5>
        <div className="table-responsive">
          <table className="table table-sm mb-0">
            <thead><tr><th>Class</th><th>Precision</th><th>Recall</th><th>F1</th><th>Support</th></tr></thead>
            <tbody>
              {Object.entries(metrics.perClass || {}).map(([cls, m]) => (
                <tr key={cls}><td>{cls}</td><td>{(m.precision*100).toFixed(1)}%</td><td>{(m.recall*100).toFixed(1)}%</td><td>{(m.f1*100).toFixed(1)}%</td><td>{m.support}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card p-3 mb-3">
        <h5>Confusion matrix</h5>
        <div className="text-muted small mb-2">Rows = true label, columns = predicted label.</div>
        <div className="table-responsive">
          <table className="table table-bordered table-sm text-center" style={{ maxWidth: 400 }}>
            <thead><tr><th></th><th>pred positive</th><th>pred negative</th><th>pred neutral</th></tr></thead>
            <tbody>
              {["positive","negative","neutral"].map((trueLabel) => (
                <tr key={trueLabel}><th>{trueLabel}</th>{["positive","negative","neutral"].map((pred) => (
                  <td key={pred} className={trueLabel===pred ? "table-success fw-bold" : ""}>{confusionMatrix?.[trueLabel]?.[pred] ?? "—"}</td>
                ))}</tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card p-3">
        <h5>Honest limitation</h5>
        <p className="small text-muted mb-0">This benchmark is a 62-row synthetic fixture with short English sentences. VADER is a lexicon baseline tuned for short, informal English. On longer, domain-specific, sarcastic, or non-English text, accuracy will differ. Use the benchmark as a diagnostic, not a universal accuracy claim. To measure performance on your domain, run sentiment analysis on your own labelled reviews and compare predicted vs true labels with the same accuracy/F1 logic.</p>
      </div>
    </div>
  );
}
