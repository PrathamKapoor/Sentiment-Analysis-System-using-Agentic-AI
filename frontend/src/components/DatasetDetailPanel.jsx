import { useEffect, useState } from "react";
import { datasetApi } from "../services/datasetApi";
import { useToast } from "../contexts/ToastContext";
import ErrorAlert from "../components/ErrorAlert";

const FIELDS = ["text", "rating", "date", "source"];

export default function DatasetDetailPanel({ datasetId, onClose, onChanged }) {
  const { showToast } = useToast();
  const [dataset, setDataset] = useState(null);
  const [error, setError] = useState(null);
  const [mapping, setMapping] = useState({ text: "", rating: "", date: "", source: "" });
  const [busy, setBusy] = useState(null);

  const load = () => {
    datasetApi.get(datasetId).then((r) => { setDataset(r.data.data); setMapping((current) => ({ ...current, ...(r.data.data.columnMapping || {}) })); }).catch(setError);
  };
  useEffect(load, [datasetId]);

  const onSaveMapping = async () => {
    if (busy) return;
    setBusy("mapping"); setError(null);
    try {
      const payload = Object.fromEntries(Object.entries(mapping).filter(([, v]) => v));
      await datasetApi.mapColumns(datasetId, payload);
      showToast("Column mapping saved");
      load();
    } catch (err) { setError(err); } finally { setBusy(null); }
  };

  const onValidate = async () => {
    if (busy) return;
    setBusy("validation"); setError(null);
    try {
      await datasetApi.validate(datasetId);
      showToast("Dataset validated");
      load();
    } catch (err) { setError(err); } finally { setBusy(null); }
  };

  const onProcess = async () => {
    if (busy) return;
    setBusy("processing"); setError(null);
    try {
      await datasetApi.process(datasetId);
      showToast("Dataset processed into reviews");
      load();
      onChanged?.();
    } catch (err) { setError(err); } finally { setBusy(null); }
  };

  if (!dataset) return null;

  return (
    <div className="card mt-3">
      <div className="card-header d-flex justify-content-between align-items-center">
        <span>{dataset.originalFilename} — {dataset.status}</span>
        <button className="btn-close" onClick={onClose} />
      </div>
      <div className="card-body">
        <ErrorAlert error={error} onDismiss={() => setError(null)} />
        {dataset.preview.columnStats?.[mapping.rating]?.max > 5 && (
          <div className="alert alert-warning" role="alert">Column “{mapping.rating}” contains values up to {dataset.preview.columnStats[mapping.rating].max}; the supported Rating range is 0–5. Leave Rating unmapped or choose another column.</div>
        )}
        {busy && <div className="dataset-stage" role="status" aria-live="polite">{busy === "processing" ? "Processing dataset…" : busy === "validation" ? "Validating dataset…" : "Saving column mapping…"}</div>}

        <h6>Preview</h6>
        <div className="table-responsive mb-3" style={{ maxHeight: 200 }}>
          <table className="table table-sm">
            <thead>
              <tr>{dataset.preview.columns.map((c) => <th key={c}>{c}</th>)}</tr>
            </thead>
            <tbody>
              {dataset.preview.rows.map((row, i) => (
                <tr key={i}>
                  {dataset.preview.columns.map((c) => <td key={c}>{String(row[c] ?? "")}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <h6>Column mapping</h6>
        <div className="row g-2 mb-3">
          {FIELDS.map((field) => (
            <div className="col-md-3" key={field}>
              <label className="form-label text-capitalize">{field}</label>
              <select
                className="form-select"
                value={mapping[field]}
                disabled={!!busy}
                onChange={(e) => setMapping({ ...mapping, [field]: e.target.value })}
              >
                <option value="">—</option>
                {dataset.preview.columns.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
          ))}
        </div>
        <button className="btn btn-outline-primary btn-sm me-2" onClick={onSaveMapping} disabled={!!busy}>
          {busy === "mapping" ? "Saving…" : "Save Mapping"}
        </button>
        <button className="btn btn-outline-primary btn-sm me-2" onClick={onValidate} disabled={!dataset.columnMapping || !!busy}>
          {busy === "validation" ? "Validating…" : "Validate"}
        </button>
        <button
          className="btn btn-primary btn-sm"
          onClick={onProcess}
          disabled={dataset.status !== "validated" || !!busy}
        >
          {busy === "processing" ? "Processing…" : "Process into Reviews"}
        </button>

        {dataset.rowCount != null && (
          <div className="mt-3 text-muted">
            Rows: {dataset.rowCount} · Valid: {dataset.validRowCount} · Invalid: {dataset.invalidRowCount} · Duplicates: {dataset.duplicateRowCount}
          </div>
        )}
      </div>
    </div>
  );
}
