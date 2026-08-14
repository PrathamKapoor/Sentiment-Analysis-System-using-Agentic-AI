import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { datasetApi } from "../services/datasetApi";
import { useToast } from "../contexts/ToastContext";
import DataTable from "../components/DataTable";
import ErrorAlert from "../components/ErrorAlert";
import PermissionGuard from "../components/PermissionGuard";
import DatasetDetailPanel from "../components/DatasetDetailPanel";
import { useAuth } from "../contexts/AuthContext";

const FILE_TYPES = ["csv", "excel", "json"];

export default function DatasetManagement() {
  const { projectId } = useParams();
  const { showToast } = useToast();
  const { hasPermission } = useAuth();
  const fileInputRef = useRef(null);
  const [datasets, setDatasets] = useState(null);
  const [error, setError] = useState(null);
  const [file, setFile] = useState(null);
  const [fileType, setFileType] = useState("csv");
  const [selectedId, setSelectedId] = useState(null);

  const load = () => {
    datasetApi.list(projectId).then((r) => setDatasets(r.data.data.items)).catch(setError);
  };
  useEffect(load, [projectId]);

  const onUpload = async (e) => {
    e.preventDefault();
    if (!file) return;
    try {
      const resp = await datasetApi.upload(projectId, file, fileType);
      showToast("Dataset uploaded — map its columns next");
      setFile(null);
      setSelectedId(resp.data.data.datasetId);
      load();
    } catch (err) {
      setError(err);
    }
  };

  if (datasets === null && !error) return null;
  if (datasets === null && error) {
    return (
      <section className="project-workspace-error" role="alert">
        <h2>Unable to load datasets</h2>
        <ErrorAlert error={error} />
        <button type="button" className="btn btn-primary" onClick={() => { setError(null); load(); }}>Retry</button>
      </section>
    );
  }

  return (
    <div>
      <h2 className="my-3">Datasets</h2>
      <ErrorAlert error={error} onDismiss={() => setError(null)} />

      <PermissionGuard permission="upload_dataset">
        <form onSubmit={onUpload} className="card p-3 mb-3 d-flex flex-row gap-2 align-items-end flex-wrap">
          <div>
            <label className="form-label">File</label>
            <input ref={fileInputRef} type="file" accept=".csv,.xlsx,.json" className="form-control" onChange={(e) => setFile(e.target.files[0])} />
          </div>
          <div>
            <label className="form-label">Type</label>
            <select className="form-select" value={fileType} onChange={(e) => setFileType(e.target.value)}>
              {FILE_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <button className="btn btn-primary" type="submit" disabled={!file}>Upload</button>
        </form>
      </PermissionGuard>

      {datasets.length === 0 ? (
        <section className="project-empty-state">
          <span className="project-empty-icon" aria-hidden="true">⇧</span>
          <h3>No datasets uploaded</h3>
          <p>Upload a CSV, XLSX, or JSON dataset, or collect public review data from Data Sources.</p>
          <div className="d-flex gap-2 flex-wrap justify-content-center">
            {hasPermission("upload_dataset") && <button type="button" className="btn btn-primary" onClick={() => fileInputRef.current?.click()}>Upload Dataset</button>}
            <Link className="btn btn-domain-data" to={`/projects/${projectId}/sources`}>Go to Data Sources</Link>
          </div>
        </section>
      ) : (
        <DataTable
          columns={[
            { key: "originalFilename", header: "File" },
            { key: "fileType", header: "Type" },
            { key: "status", header: "Status" },
            { key: "rowCount", header: "Rows" },
            {
              key: "actions", header: "",
              render: (d) => (
                <button className="btn btn-sm btn-outline-primary" onClick={() => setSelectedId(d.id)}>
                  Manage
                </button>
              ),
            },
          ]}
          rows={datasets}
        />
      )}

      {selectedId && (
        <DatasetDetailPanel
          datasetId={selectedId}
          onClose={() => setSelectedId(null)}
          onChanged={load}
        />
      )}
    </div>
  );
}
