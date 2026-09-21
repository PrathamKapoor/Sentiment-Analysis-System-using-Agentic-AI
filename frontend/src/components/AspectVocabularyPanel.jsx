import { useEffect, useState } from "react";
import { aspectVocabularyApi } from "../services/aspectVocabularyApi";
import ErrorAlert from "./ErrorAlert";
import { useToast } from "../contexts/ToastContext";

export default function AspectVocabularyPanel({ projectId }) {
  const { showToast } = useToast();
  const [items, setItems] = useState(null);
  const [error, setError] = useState(null);
  const [canonicalName, setCanonicalName] = useState("");
  const [surfaceFormsInput, setSurfaceFormsInput] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () => {
    aspectVocabularyApi.list(projectId).then((r) => setItems(r.data.data.items)).catch(setError);
  };
  useEffect(load, [projectId]);

  const onCreate = async (e) => {
    e.preventDefault();
    if (!canonicalName.trim() || !surfaceFormsInput.trim()) return;
    setBusy(true);
    try {
      const surfaceForms = surfaceFormsInput.split(",").map((s) => s.trim()).filter(Boolean);
      await aspectVocabularyApi.create(projectId, { canonicalName: canonicalName.trim(), surfaceForms });
      showToast("Aspect added");
      setCanonicalName("");
      setSurfaceFormsInput("");
      load();
    } catch (err) { setError(err); } finally { setBusy(false); }
  };

  const onDelete = async (id) => {
    try { await aspectVocabularyApi.remove(projectId, id); showToast("Aspect removed"); load(); } catch (err) { setError(err); }
  };

  const onToggle = async (item) => {
    try { await aspectVocabularyApi.update(projectId, item.id, { isActive: !item.isActive }); load(); } catch (err) { setError(err); }
  };

  if (items === null && !error) return <div className="text-muted small">Loading aspect vocabulary...</div>;

  return (
    <div className="mt-4">
      <h5>Project Aspect Vocabulary</h5>
      <p className="text-muted small">Add project-specific aspects (e.g. food, service, ambience, value for a restaurant; waiting time, staff, cleanliness, billing for a hospital). When any rows exist, aspect analysis uses your custom vocabulary plus the global 13-aspect seed. When no rows exist, only the global seed applies.</p>
      <ErrorAlert error={error} onDismiss={() => setError(null)} />
      <form onSubmit={onCreate} className="card p-3 mb-3 d-flex flex-row gap-2 align-items-end flex-wrap">
        <div style={{ minWidth: 180 }}>
          <label className="form-label small mb-0">Canonical name</label>
          <input className="form-control form-control-sm" placeholder="food" value={canonicalName} onChange={(e) => setCanonicalName(e.target.value)} />
        </div>
        <div style={{ minWidth: 260 }}>
          <label className="form-label small mb-0">Surface forms (comma-separated)</label>
          <input className="form-control form-control-sm" placeholder="food, meal, dish, cuisine" value={surfaceFormsInput} onChange={(e) => setSurfaceFormsInput(e.target.value)} />
        </div>
        <button className="btn btn-primary btn-sm" type="submit" disabled={busy || !canonicalName.trim() || !surfaceFormsInput.trim()}>
          {busy ? "Saving..." : "Add aspect"}
        </button>
      </form>
      {items?.length === 0 ? (
        <div className="text-muted small">No project-specific aspects yet. Only the global seed vocabulary is active.</div>
      ) : (
        <div className="table-responsive">
          <table className="table table-sm">
            <thead><tr><th>Canonical</th><th>Surface forms</th><th>Active</th><th></th></tr></thead>
            <tbody>
              {(items || []).map((item) => (
                <tr key={item.id}>
                  <td>{item.canonicalName}</td>
                  <td className="small text-muted">{(item.surfaceForms || []).join(", ")}</td>
                  <td>
                    <button className={`btn btn-sm ${item.isActive ? "btn-success" : "btn-outline-secondary"}`} onClick={() => onToggle(item)}>
                      {item.isActive ? "active" : "inactive"}
                    </button>
                  </td>
                  <td><button className="btn btn-sm btn-outline-danger" onClick={() => onDelete(item.id)}>Remove</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
