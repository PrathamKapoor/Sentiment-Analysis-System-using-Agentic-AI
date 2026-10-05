import { useEffect, useState } from "react";
import { entityApi } from "../services/entityApi";
import { useToast } from "../contexts/ToastContext";
import PermissionGuard from "./PermissionGuard";
import LoadingSpinner from "./LoadingSpinner";

const groups = [
  ["includeKeywords", "Include keywords", "Reviews must mention at least one term when collecting this source."],
  ["excludeKeywords", "Exclude keywords", "Matching reviews are omitted from collection."],
  ["securityKeywords", "Security terms", "Matches are recorded as annotations; they do not create security findings."],
  ["competitorKeywords", "Competitor terms", "Matches are recorded as annotations; comparative analysis is not implemented yet."],
  ["customKeywords", "Custom terms", "Project-specific matches are recorded as annotations."],
];

const toLines = (items) => (items || []).join("\n");
const toList = (value) => value.split(/\r?\n|,/).map((item) => item.trim()).filter(Boolean);
const toIdentifierRows = (values) => Object.entries(values || {}).map(([key, value]) => ({ key, value }));
const identifiersFromRows = (rows) => Object.fromEntries(rows
  .filter(({ key, value }) => key.trim() && value.trim())
  .map(({ key, value }) => [key.trim(), value.trim()]));
const mergeTerms = (current, suggested) => [...new Set([
  ...toList(current), ...(suggested || []).map((value) => value.trim()).filter(Boolean),
])];

export default function ProjectEntityPanel({ projectId }) {
  const { showToast } = useToast();
  const [entity, setEntity] = useState(null);
  const [draft, setDraft] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [discovering, setDiscovering] = useState(false);
  const [suggestions, setSuggestions] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    entityApi.get(projectId).then(({ data }) => {
      const value = data.data;
      const form = {
        brand: value.brand || "", product: value.product || "", model: value.model || "",
        sku: value.sku || "", canonicalUrl: value.canonicalUrl || "",
        aliases: toLines(value.aliases), identifiers: toIdentifierRows(value.identifiers),
      };
      groups.forEach(([key]) => { form[key] = toLines(value[key]); });
      if (active) { setEntity(value); setDraft(form); }
    }).catch((reason) => {
      if (active) setError(reason?.response?.data?.error?.message || "Could not load product identity.");
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [projectId]);

  const save = async (event) => {
    event.preventDefault();
    setSaving(true); setError("");
    try {
      const payload = {
        brand: draft.brand.trim() || null, product: draft.product.trim() || null,
        model: draft.model.trim() || null, sku: draft.sku.trim() || null,
        canonicalUrl: draft.canonicalUrl.trim() || null,
        aliases: toList(draft.aliases), identifiers: identifiersFromRows(draft.identifiers),
      };
      groups.forEach(([key]) => { payload[key] = toList(draft[key]); });
      const { data } = await entityApi.save(projectId, payload);
      setEntity(data.data);
      showToast("Product identity and keyword groups saved");
    } catch (reason) {
      setError(reason?.response?.data?.error?.message || "Could not save product identity.");
    } finally { setSaving(false); }
  };

  const discover = async () => {
    const description = [draft.brand, draft.product, draft.model].map((part) => part.trim()).filter(Boolean).join(" ");
    if (description.length < 2) { setError("Enter a brand, product, or model before requesting suggestions."); return; }
    setDiscovering(true); setError("");
    try {
      const { data } = await entityApi.discover(projectId, description, {
        sku: draft.sku,
        canonicalUrl: draft.canonicalUrl,
        identifiers: identifiersFromRows(draft.identifiers),
      });
      setSuggestions(data.data);
    } catch (reason) {
      setError(reason?.response?.data?.error?.message || "Could not generate product identity suggestions.");
    } finally { setDiscovering(false); }
  };

  const applySuggestions = () => {
    if (!suggestions) return;
    const aliases = mergeTerms(draft.aliases, [...(suggestions.aliases || []), ...(suggestions.searchKeywords || [])]);
    const nextIdentifiers = { ...identifiersFromRows(draft.identifiers) };
    for (const [key, value] of Object.entries(suggestions.identifiers || {})) {
      if (!Object.keys(nextIdentifiers).some((existing) => existing.toLowerCase() === key.toLowerCase())) {
        nextIdentifiers[key] = value;
      }
    }
    setDraft({
      ...draft,
      brand: draft.brand || suggestions.brand || "",
      product: draft.product || suggestions.product || "",
      model: draft.model || suggestions.productModel || "",
      aliases: aliases.join("\n"),
      identifiers: toIdentifierRows(nextIdentifiers),
      includeKeywords: mergeTerms(draft.includeKeywords, suggestions.includeKeywords).join("\n"),
      excludeKeywords: mergeTerms(draft.excludeKeywords, suggestions.excludeKeywords).join("\n"),
      securityKeywords: mergeTerms(draft.securityKeywords, suggestions.securityKeywords).join("\n"),
      competitorKeywords: mergeTerms(draft.competitorKeywords, suggestions.competitorKeywords).join("\n"),
      customKeywords: mergeTerms(draft.customKeywords, suggestions.customKeywords).join("\n"),
    });
  };

  if (loading) return <LoadingSpinner />;
  if (!draft) return <div className="alert alert-warning">{error || "Product identity is unavailable."}</div>;

  return (
    <div className="card mb-3" aria-label="Product identity and project keywords">
      <div className="card-body">
        <h2 className="h5">Product identity and search terms</h2>
        <p className="text-muted small">Set the canonical entity used to describe this project. Source and analysis results retain their actual provenance.</p>
        {entity?.canonicalName && <p className="small"><strong>Resolved entity:</strong> {entity.canonicalName}</p>}
        {error && <div className="alert alert-danger" role="alert">{error}</div>}
        <PermissionGuard permission="edit_project">
          <div className="d-flex flex-wrap align-items-center gap-2 mb-3">
            <button type="button" className="btn btn-outline-secondary btn-sm" onClick={discover} disabled={discovering}>
              {discovering ? "Finding terms…" : "Suggest identity, terms and identifiers"}
            </button>
            {suggestions && <span className="small text-muted">{suggestions.providerRole === "deterministic" ? "Deterministic suggestions" : `Suggested by ${suggestions.providerRole} provider (${suggestions.providerModel || suggestions.provider})`}; review before saving.</span>}
          </div>
          {suggestions && <div className="alert alert-info small" role="status">
            <strong>Suggested entity:</strong> {[suggestions.brand, suggestions.product, suggestions.productModel].filter(Boolean).join(" ") || suggestions.canonicalName}
            <div className="mt-1"><strong>Search terms:</strong> {(suggestions.searchKeywords || []).join(", ") || "none"}</div>
            {groups.map(([key, label]) => (suggestions[key]?.length > 0 && <div key={key}><strong>{label}:</strong> {suggestions[key].join(", ")}</div>))}
            {Object.keys(suggestions.identifiers || {}).length > 0 && <div><strong>Identifiers found:</strong> {Object.entries(suggestions.identifiers).map(([key, value]) => `${key}: ${value}`).join(", ")}</div>}
            <button type="button" className="btn btn-sm btn-outline-primary mt-2" onClick={applySuggestions}>Apply suggestions to form</button>
          </div>}
          <form onSubmit={save}>
            <div className="row g-2">
              {[['brand','Brand'],['product','Product'],['model','Model'],['sku','SKU / identifier'],['canonicalUrl','Canonical product URL']].map(([key,label]) => (
                <div className={key === "canonicalUrl" ? "col-12" : "col-md-6"} key={key}>
                  <label className="form-label small" htmlFor={`entity-${key}`}>{label}</label>
                  <input id={`entity-${key}`} type={key === "canonicalUrl" ? "url" : "text"} className="form-control" value={draft[key]} onChange={(event) => setDraft({ ...draft, [key]: event.target.value })} />
                </div>
              ))}
              <div className="col-12">
                <label className="form-label small" htmlFor="entity-aliases">Aliases (one per line)</label>
                <textarea id="entity-aliases" className="form-control" rows="2" value={draft.aliases} onChange={(event) => setDraft({ ...draft, aliases: event.target.value })} />
              </div>
              {groups.map(([key, label, help]) => (
                <div className="col-md-6" key={key}>
                  <label className="form-label small" htmlFor={`entity-${key}`}>{label}</label>
                  <textarea id={`entity-${key}`} className="form-control" rows="3" value={draft[key]} onChange={(event) => setDraft({ ...draft, [key]: event.target.value })} aria-describedby={`entity-${key}-help`} />
                  <div className="form-text" id={`entity-${key}-help`}>{help}</div>
                </div>
              ))}
              <div className="col-12">
                <label className="form-label small">Additional identifiers</label>
                <div className="form-text mb-2">A supplied Amazon product URL can provide its ASIN automatically. Other values are copied only from identifiers you supplied.</div>
                {draft.identifiers.map((identifier, index) => (
                  <div className="row g-2 mb-2" key={`${index}-${identifier.key}`}>
                    <div className="col-md-5"><input className="form-control" aria-label={`Identifier name ${index + 1}`} placeholder="Identifier name (e.g. ASIN)" value={identifier.key} onChange={(event) => setDraft({ ...draft, identifiers: draft.identifiers.map((row, rowIndex) => rowIndex === index ? { ...row, key: event.target.value } : row) })} /></div>
                    <div className="col"><input className="form-control" aria-label={`Identifier value ${index + 1}`} placeholder="Identifier value" value={identifier.value} onChange={(event) => setDraft({ ...draft, identifiers: draft.identifiers.map((row, rowIndex) => rowIndex === index ? { ...row, value: event.target.value } : row) })} /></div>
                    <div className="col-auto"><button type="button" className="btn btn-outline-secondary" aria-label={`Remove identifier ${index + 1}`} onClick={() => setDraft({ ...draft, identifiers: draft.identifiers.filter((_, rowIndex) => rowIndex !== index) })}>Remove</button></div>
                  </div>
                ))}
                <button type="button" className="btn btn-outline-secondary btn-sm" onClick={() => setDraft({ ...draft, identifiers: [...draft.identifiers, { key: "", value: "" }] })}>Add identifier</button>
              </div>
            </div>
            <button type="submit" className="btn btn-primary mt-3" disabled={saving}>{saving ? "Saving…" : "Save identity and terms"}</button>
          </form>
        </PermissionGuard>
      </div>
    </div>
  );
}
