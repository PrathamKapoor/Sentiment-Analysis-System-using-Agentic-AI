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

  const load = () => {
    datasetApi.get(datasetId).then((r) => setDataset(r.data.data)).catch(setError);
  };
  useEffect(load, [datasetId]);

  const onSaveMapping = async () => {
    try {
      const payload = Object.fromEntries(Object.entries(mapping).filter(([, v]) => v));
      await datasetApi.mapColumns(datasetId, payload);
      showToast("Column mapping saved");
      load();
    } catch (err) {
      setError(err);
    }
  };

  const onValidate = async () => {
    try {
      await datasetApi.validate(datasetId);
      showToast("Dataset validated");
      load();
    } catch (err) {
      setError(err);
    }
  };

  const onProcess = async () => {
    try {
      await datasetApi.process(datasetId);
      showToast("Dataset processed into reviews");
      load();
      onChanged?.();
    } catch (err) {
      setError(err);
    }
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
                onChange={(e) => setMapping({ ...mapping, [field]: e.target.value })}
              >
                <option value="">—</option>
                {dataset.preview.columns.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
          ))}
        </div>
        <button className="btn btn-outline-primary btn-sm me-2" onClick={onSaveMapping}>
          Save Mapping
        </button>
        <button className="btn btn-outline-primary btn-sm me-2" onClick={onValidate} disabled={!dataset.columnMapping}>
          Validate
        </button>
        <button
          className="btn btn-primary btn-sm"
          onClick={onProcess}
          disabled={dataset.status !== "validated"}
        >
          Process into Reviews
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
