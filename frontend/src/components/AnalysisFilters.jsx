import { useEffect, useState } from "react";
import { dataSourceApi } from "../services/dataSourceApi";
import { datasetApi } from "../services/datasetApi";

export default function AnalysisFilters({ projectId, filters, onChange, showRating = false }) {
  const [sources, setSources] = useState([]);
  const [datasets, setDatasets] = useState([]);

  useEffect(() => {
    dataSourceApi.list(projectId).then((r) => setSources(r.data.data.items)).catch(() => setSources([]));
    datasetApi.list(projectId).then((r) => setDatasets(r.data.data.items)).catch(() => setDatasets([]));
  }, [projectId]);

  const set = (key, value) => onChange({ ...filters, [key]: value || undefined });

  return (
    <div className="d-flex flex-wrap gap-2 align-items-end mb-3">
      <div>
        <label className="form-label small mb-0">From</label>
        <input type="date" className="form-control form-control-sm" value={filters.dateFrom || ""} onChange={(e) => set("dateFrom", e.target.value)} />
      </div>
      <div>
        <label className="form-label small mb-0">To</label>
        <input type="date" className="form-control form-control-sm" value={filters.dateTo || ""} onChange={(e) => set("dateTo", e.target.value)} />
      </div>
      <div>
        <label className="form-label small mb-0">Source</label>
        <select className="form-select form-select-sm" value={filters.sourceId || ""} onChange={(e) => set("sourceId", e.target.value)}>
          <option value="">All sources</option>
          {sources.map((s) => <option key={s.id} value={s.id}>{s.url}</option>)}
        </select>
      </div>
      <div>
        <label className="form-label small mb-0">Dataset</label>
        <select className="form-select form-select-sm" value={filters.datasetId || ""} onChange={(e) => set("datasetId", e.target.value)}>
          <option value="">All datasets</option>
          {datasets.map((d) => <option key={d.id} value={d.id}>{d.originalFilename}</option>)}
        </select>
      </div>
      {showRating && (
        <div>
          <label className="form-label small mb-0">Rating</label>
          <select className="form-select form-select-sm" value={filters.rating || ""} onChange={(e) => set("rating", e.target.value)}>
            <option value="">Any</option>
            {[1, 2, 3, 4, 5].map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </div>
      )}
    </div>
  );
}
