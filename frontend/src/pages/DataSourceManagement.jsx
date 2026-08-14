import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import ConfirmationModal from "../components/ConfirmationModal";
import ErrorAlert from "../components/ErrorAlert";
import FormInput from "../components/FormInput";
import PermissionGuard from "../components/PermissionGuard";
import { useToast } from "../contexts/ToastContext";
import { dataSourceApi } from "../services/dataSourceApi";

const SOURCE_TYPES = ["review_site", "ecommerce", "reddit", "forum", "blog", "news", "survey"];

function normalizedKeywords(values) {
  const seen = new Set();
  return (values || []).flatMap((value) => String(value).split(",")).map((value) => value.trim().replace(/\s+/g, " ")).filter((value) => {
    const key = value.toLocaleLowerCase();
    if (!value || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function sourceIdentity(source) {
  try {
    const url = new URL(source.url);
    const hostname = url.hostname.replace(/^www\./, "");
    if (hostname === "amazon.in") return { name: "Amazon India", hostname };
    if (hostname === "flipkart.com") return { name: "Flipkart", hostname };
    const name = hostname.split(".").slice(0, -1).join(" ").replace(/(^|\s)\S/g, (letter) => letter.toUpperCase());
    return { name: name || hostname, hostname };
  } catch {
    return { name: "Data source", hostname: "Invalid URL" };
  }
}

function shortUrl(value) {
  try {
    const url = new URL(value);
    const parts = url.pathname.split("/").filter(Boolean);
    const identity = parts.find((part) => /^(B[A-Z0-9]{9}|itm[a-z0-9]+)$/i.test(part));
    return `${url.hostname.replace(/^www\./, "")}/…${identity ? `/${identity}` : ""}`;
  } catch {
    return value;
  }
}

function friendlyAction(action) {
  return ({
    "collection.completed": "Collection completed",
    "collection.failed": "Collection failed",
    "collection.started": "Collection started",
    "collection.blocked_by_policy": "Collection blocked",
    "collection.preview": "Preview generated",
    "data_source.test_connection": "Source tested",
  })[action] || action?.replaceAll(".", " ") || "Not collected";
}

function resultMessage(result) {
  if (!result) return "Collection finished.";
  if (result.status === "failed") return result.safeErrorMessage || "Collection failed.";
  return result.resultMessage || `${result.recordsInserted || 0} reviews collected.`;
}

function FallbackDetails({ fallback }) {
  if (!fallback) return null;
  const provider = fallback.apiProvider || (fallback.approvedCandidates ? "Approved provider" : null);
  return (
    <div className="collection-fallback" role="status">
      <strong>Fallback resolution</strong>
      <span>Direct collection did not return usable review data for {fallback.canonicalEntity || "this source"}.</span>
      {provider && <span>Provider: {provider}</span>}
      {fallback.actualSource && <span>Actual source: {fallback.actualSource}</span>}
      {fallback.terminalStatus === "API_CREDENTIALS_REQUIRED" && <span>Server-side provider credentials are required.</span>}
      {fallback.terminalStatus === "RATE_LIMITED" && <span>The provider is temporarily rate limited. Try again later.</span>}
      {!provider && <span>No approved alternative source is currently available. You can upload a dataset instead.</span>}
    </div>
  );
}

function KeywordViewer({ keywords }) {
  const [expanded, setExpanded] = useState(false);
  const [query, setQuery] = useState("");
  const normalized = useMemo(() => normalizedKeywords(keywords), [keywords]);
  const visible = expanded
    ? normalized.filter((keyword) => keyword.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()))
    : normalized.slice(0, 5);

  return (
    <div className="source-keywords">
      <div className="source-section-label">Keywords <span>· {normalized.length}</span></div>
      {expanded && normalized.length > 8 && (
        <label className="keyword-search">
          <span className="visually-hidden">Search configured keywords</span>
          <input className="form-control form-control-sm" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search keywords" />
        </label>
      )}
      <div className="keyword-chip-list" aria-label={`${normalized.length} configured keywords`}>
        {visible.map((keyword) => <span className="keyword-chip" key={keyword.toLocaleLowerCase()}>{keyword}</span>)}
        {!expanded && normalized.length > 5 && (
          <button type="button" className="keyword-more" onClick={() => setExpanded(true)}>+{normalized.length - 5} more</button>
        )}
        {normalized.length === 0 && <span className="source-empty-value">No keyword filter — collect all product reviews</span>}
      </div>
      {expanded && (
        <button type="button" className="keyword-collapse" onClick={() => { setExpanded(false); setQuery(""); }}>Show fewer</button>
      )}
    </div>
  );
}

function DiagnosticGrid({ result }) {
  if (!result) return null;
  const items = [
    ["Status", result.resultMessage || result.safeErrorMessage || friendlyAction(result.lastAction)],
    ["Fetched", result.pagesFetched != null ? `${result.pagesFetched} page${result.pagesFetched === 1 ? "" : "s"}` : "—"],
    ["Candidates", result.candidateItemsFound ?? result.recordsFound ?? "—"],
    ["Parsed", result.itemsParsed ?? result.recordsFound ?? "—"],
    ["After filter", result.itemsAfterFilter ?? result.recordsFound ?? "—"],
    ["Saved", result.itemsSaved ?? result.recordsInserted ?? "—"],
    ["Duplicates", result.recordsDuplicate ?? "—"],
    ["Invalid", result.recordsInvalid ?? "—"],
  ];
  return (
    <div className="collection-diagnostic-grid">
      {items.map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}
    </div>
  );
}

function CollectionDetails({ source, latestResult }) {
  const [status, setStatus] = useState(null);
  const [history, setHistory] = useState(null);
  const [preview, setPreview] = useState(null);
  const [testResult, setTestResult] = useState(null);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const { showToast } = useToast();

  const loadStatus = useCallback(async (isCancelled = () => false) => {
    try {
      const response = await dataSourceApi.collectionStatus(source.id);
      if (!isCancelled()) setStatus(response.data.data);
    } catch (requestError) {
      if (!isCancelled()) setError(requestError);
    }
  }, [source.id]);

  useEffect(() => {
    let cancelled = false;
    void loadStatus(() => cancelled);
    return () => { cancelled = true; };
  }, [loadStatus]);

  const runTest = async () => {
    setBusy("test"); setError(null);
    try {
      const response = await dataSourceApi.testConnection(source.id);
      setTestResult(response.data.data);
      const collectable = response.data.data.available && response.data.data.diagnosticCode === "COLLECTION_SUCCESS";
      showToast(response.data.data.message || (collectable ? "Source is collectable." : "Source test needs attention."), collectable ? "success" : "warning");
      void loadStatus();
    } catch (requestError) { setError(requestError); } finally { setBusy(null); }
  };

  const runPreview = async () => {
    setBusy("preview"); setError(null);
    try { setPreview((await dataSourceApi.preview(source.id)).data.data); }
    catch (requestError) { setError(requestError); }
    finally { setBusy(null); }
  };

  const loadHistory = async () => {
    setBusy("history"); setError(null);
    try { setHistory((await dataSourceApi.collectionHistory(source.id)).data.data.items); }
    catch (requestError) { setError(requestError); }
    finally { setBusy(null); }
  };

  const persistedResult = status?.lastResult;
  const displayResult = latestResult || persistedResult;
  return (
    <section className="collection-details" aria-label={`Collection details for ${sourceIdentity(source).name}`}>
      <ErrorAlert error={error} onDismiss={() => setError(null)} />
      <div className="collection-details-heading">
        <div>
          <span className="source-section-label">Last collection</span>
          <h3>{displayResult?.resultMessage || displayResult?.safeErrorMessage || friendlyAction(status?.lastAction)}</h3>
          <p>{status?.lastCollectedAt ? new Date(status.lastCollectedAt).toLocaleString() : "This source has not completed a collection yet."}</p>
        </div>
        <div className="source-detail-actions">
          <PermissionGuard permission="manage_data_sources">
            <button type="button" className="btn btn-sm btn-outline-secondary" disabled={!!busy} onClick={runTest}>{busy === "test" ? "Testing…" : "Test source"}</button>
            <button type="button" className="btn btn-sm btn-domain-data" disabled={!!busy || !source.enabled} onClick={runPreview}>{busy === "preview" ? "Preparing…" : "Preview"}</button>
          </PermissionGuard>
          <button type="button" className="btn btn-sm btn-outline-secondary" disabled={!!busy} onClick={loadHistory}>{busy === "history" ? "Loading…" : history ? "Refresh history" : "View history"}</button>
        </div>
      </div>
      <DiagnosticGrid result={displayResult} />
      <FallbackDetails fallback={displayResult?.fallback} />
      {displayResult && (
        <details className="collection-technical">
          <summary>Technical details</summary>
          <dl>
            <div><dt>Adapter</dt><dd>{displayResult.adapter || "—"}</dd></div>
            <div><dt>HTTP status</dt><dd>{displayResult.httpStatus || "—"}</dd></div>
            <div><dt>Result code</dt><dd>{displayResult.resultCode || displayResult.errorCode || "—"}</dd></div>
            <div><dt>Normalized URL</dt><dd title={displayResult.normalizedUrl}>{displayResult.normalizedUrl || source.url}</dd></div>
          </dl>
        </details>
      )}
      {testResult && (
        <div className="collection-preview" role="status">
          <div><strong>Source test · {testResult.platform || sourceIdentity(source).name}</strong><span>{testResult.message}</span></div>
          <dl className="collection-technical">
            <div><dt>Adapter</dt><dd>{testResult.adapterClass || testResult.adapter || "—"}</dd></div>
            <div><dt>Product identity</dt><dd>{testResult.productIdentity || "—"}</dd></div>
            <div><dt>Product page</dt><dd>{testResult.productPage?.status || "—"}{testResult.productPage?.httpStatus ? ` · HTTP ${testResult.productPage.httpStatus}` : ""}</dd></div>
            <div><dt>Review page</dt><dd>{testResult.reviewPage?.status || "—"}{testResult.reviewPage?.httpStatus ? ` · HTTP ${testResult.reviewPage.httpStatus}` : ""}</dd></div>
            <div><dt>Page type</dt><dd>{testResult.pageType?.replaceAll("_", " ") || "—"}</dd></div>
            <div><dt>Review discovery</dt><dd>{testResult.reviewPage?.discoveryMethod?.replaceAll("_", " ") || "—"}</dd></div>
            <div><dt>Parser</dt><dd>{testResult.parserStatus || "—"}</dd></div>
            <div><dt>Candidates</dt><dd>{testResult.reviewCandidatesDetected ?? "—"}</dd></div>
            <div><dt>Valid reviews</dt><dd>{testResult.validReviewsParsed ?? "—"}</dd></div>
            <div><dt>Keyword filtering</dt><dd>{testResult.keywordFilteringStatus?.replaceAll("_", " ") || "—"}</dd></div>
            <div><dt>Diagnostic code</dt><dd>{testResult.diagnosticCode || "—"}</dd></div>
          </dl>
        </div>
      )}
      {preview && (
        <div className="collection-preview">
          <div><strong>{preview.pageTitle || "Public source preview"}</strong><span>{preview.detectedRecordCountEstimate || 0} candidates detected</span></div>
          {preview.warnings?.map((warning) => <p className="text-warning" key={warning}>{warning}</p>)}
          {preview.sampleRecords?.map((record, index) => <blockquote key={`${record.review_text}-${index}`}>{record.source_metadata?.title && <strong>{record.source_metadata.title}</strong>}{record.review_text || <em>No text detected</em>}{record.rating != null && <small>{record.rating} / 5</small>}</blockquote>)}
        </div>
      )}
      {history && (
        <div className="collection-history" aria-label="Collection history">
          {history.length === 0 && <p className="source-empty-value">No collection activity yet.</p>}
          {history.map((entry) => (
            <article key={entry.id}>
              <div><strong>{friendlyAction(entry.action)}</strong><time>{new Date(entry.timestamp).toLocaleString()}</time></div>
              <span>{entry.metadata?.resultMessage || entry.metadata?.safeErrorMessage || entry.metadata?.reason || "Recorded"}</span>
              {entry.metadata?.itemsSaved != null && <small>Found {entry.metadata.candidateItemsFound ?? entry.metadata.recordsFound ?? 0} · Saved {entry.metadata.itemsSaved} · Duplicates {entry.metadata.recordsDuplicate || 0}</small>}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function SourceCard({ source, expanded, busy, latestResult, onCollect, onDetails, onToggle, onRemove }) {
  const identity = sourceIdentity(source);
  const copySourceUrl = () => navigator.clipboard?.writeText(source.url).catch(() => {});
  return (
    <article className={`source-card${expanded ? " is-expanded" : ""}`}>
      <div className="source-card-main">
        <header className="source-card-header">
          <div className="source-platform">
            <span className="source-platform-mark" aria-hidden="true">{identity.name.charAt(0)}</span>
            <div>
              <h2>{identity.name}</h2>
              <div className="source-badges"><span className="source-type-badge">{source.type.replace("_", " ")}</span><span className={`source-state ${source.enabled ? "is-enabled" : "is-disabled"}`}><i />{source.enabled ? "Enabled" : "Disabled"}</span></div>
            </div>
          </div>
          <PermissionGuard permission="manage_data_sources">
            <button type="button" role="switch" aria-checked={source.enabled} className={`source-switch ${source.enabled ? "is-on" : ""}`} onClick={() => onToggle(source)}><span /><span className="visually-hidden">{source.enabled ? "Disable" : "Enable"} {identity.name}</span></button>
          </PermissionGuard>
        </header>
        <div className="source-url-row">
          <a href={source.url} target="_blank" rel="noreferrer" title={source.url} aria-label={`Open ${identity.name} source in a new tab`}>{shortUrl(source.url)} <span aria-hidden="true">↗</span></a>
          <button type="button" onClick={copySourceUrl} aria-label={`Copy ${identity.name} source URL`}>Copy URL</button>
        </div>
        <KeywordViewer keywords={source.keywords} />
        <div className="source-card-meta"><span>Last collection</span><strong>{source.lastCollectedAt ? new Date(source.lastCollectedAt).toLocaleString() : "Never"}</strong></div>
      </div>
      <footer className="source-card-actions">
        <PermissionGuard permission="manage_data_sources">
          <button type="button" className="btn btn-domain-data" disabled={busy || !source.enabled} onClick={() => onCollect(source)}>{busy ? "Collecting…" : "Collect Now"}</button>
        </PermissionGuard>
        <PermissionGuard permission="view_reviews">
          <button type="button" className="btn btn-outline-secondary" aria-expanded={expanded} onClick={() => onDetails(source.id)}>{expanded ? "Hide details" : "Details"}</button>
        </PermissionGuard>
        <PermissionGuard permission="manage_data_sources">
          <button type="button" className="btn btn-outline-danger source-remove" onClick={() => onRemove(source)}>Remove</button>
        </PermissionGuard>
      </footer>
      {latestResult && !expanded && <div className={`source-inline-result ${latestResult.status === "failed" ? "is-error" : (["no_records", "partial_success"].includes(latestResult.status) || latestResult.parserStatus === "PARSER_MISMATCH" ? "is-warning" : "")}`} role="status">{resultMessage(latestResult)}</div>}
      {expanded && <CollectionDetails source={source} latestResult={latestResult} />}
    </article>
  );
}

export default function DataSourceManagement() {
  const { projectId } = useParams();
  const { showToast } = useToast();
  const [sources, setSources] = useState(null);
  const [error, setError] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [expandedId, setExpandedId] = useState(null);
  const [busySourceId, setBusySourceId] = useState(null);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [latestResults, setLatestResults] = useState({});
  const [removeTarget, setRemoveTarget] = useState(null);
  const [removing, setRemoving] = useState(false);
  const [form, setForm] = useState({ type: SOURCE_TYPES[0], url: "", keywords: "" });

  const load = useCallback(async (isCancelled = () => false) => {
    try {
      const response = await dataSourceApi.list(projectId);
      if (!isCancelled()) {
        setSources(response.data.data.items);
        setError(null);
      }
    } catch (requestError) {
      if (!isCancelled()) setError(requestError);
    }
  }, [projectId]);

  useEffect(() => {
    let cancelled = false;
    setSources(null);
    setError(null);
    void load(() => cancelled);
    return () => { cancelled = true; };
  }, [load]);

  const onCreate = async (event) => {
    event.preventDefault(); setError(null);
    try {
      await dataSourceApi.create(projectId, { type: form.type, url: form.url, keywords: normalizedKeywords([form.keywords]) });
      showToast("Data source added.");
      setShowForm(false); setForm({ type: SOURCE_TYPES[0], url: "", keywords: "" }); void load();
    } catch (requestError) { setError(requestError); }
  };

  const onToggle = async (source) => {
    try { await dataSourceApi.update(source.id, { enabled: !source.enabled }); showToast(`${sourceIdentity(source).name} ${source.enabled ? "disabled" : "enabled"}.`); void load(); }
    catch (requestError) { setError(requestError); }
  };

  const onCollect = async (source) => {
    if (busySourceId) return;
    setBusySourceId(source.id); setError(null);
    try {
      const result = (await dataSourceApi.collect(source.id)).data.data;
      setLatestResults((previous) => ({ ...previous, [source.id]: result }));
      showToast(resultMessage(result), result.status === "no_records" || result.status === "partial_success" ? "warning" : "success");
      void load();
    } catch (requestError) {
      const apiError = requestError?.response?.data?.error;
      const failed = { status: "failed", errorCode: apiError?.code, safeErrorMessage: apiError?.message, ...(apiError?.details || {}) };
      setLatestResults((previous) => ({ ...previous, [source.id]: failed }));
      setExpandedId(source.id);
      showToast(apiError?.message || "Collection failed.", "danger");
    } finally { setBusySourceId(null); }
  };

  const confirmRemove = async () => {
    if (!removeTarget || removing) return;
    setRemoving(true);
    try { await dataSourceApi.remove(removeTarget.id); showToast("Data source removed. Collected reviews were retained."); setRemoveTarget(null); void load(); }
    catch (requestError) { setError(requestError); }
    finally { setRemoving(false); }
  };

  const collectAllEnabled = async () => {
    if (bulkBusy) return;
    setBulkBusy(true); setError(null);
    try {
      const results = (await dataSourceApi.collectEnabled(projectId)).data.data.items;
      setLatestResults((previous) => ({ ...previous, ...Object.fromEntries(results.map((item) => [item.sourceId, item])) }));
      const saved = results.reduce((total, item) => total + (item.itemsSaved ?? item.recordsInserted ?? 0), 0);
      const failures = results.filter((item) => item.status === "failed").length;
      showToast(`${saved} reviews collected from ${results.length - failures} source${results.length - failures === 1 ? "" : "s"}${failures ? `; ${failures} failed` : ""}.`, failures ? "warning" : "success");
      void load();
    } catch (requestError) { setError(requestError); }
    finally { setBulkBusy(false); }
  };

  if (sources === null && !error) return null;
  return (
    <div className="data-sources-page">
      <header className="page-header source-page-header">
        <div><span className="page-kicker">Web collection</span><h1>Data Sources</h1><p>Manage controlled public sources that feed reviews into this sentiment workspace.</p></div>
        {sources !== null && (
          <PermissionGuard permission="manage_data_sources">
            <div className="source-page-actions">
              <button className="btn btn-domain-data" disabled={bulkBusy || !sources.some((source) => source.enabled)} onClick={collectAllEnabled}>{bulkBusy ? "Collecting…" : "Collect All Enabled"}</button>
              <button className="btn btn-primary" onClick={() => setShowForm((visible) => !visible)}>{showForm ? "Close" : "+ Add Source"}</button>
            </div>
          </PermissionGuard>
        )}
      </header>
      {sources === null && error ? (
        <section className="project-workspace-error" role="alert">
          <h2>Unable to load data sources</h2>
          <p>The source list could not be retrieved. Check your connection and try again.</p>
          <ErrorAlert error={error} />
          <button type="button" className="btn btn-primary" onClick={() => { setError(null); void load(); }}>Retry</button>
        </section>
      ) : (
        <>
      <ErrorAlert error={error} onDismiss={() => setError(null)} />
      {showForm && (
        <form onSubmit={onCreate} className="card source-create-card">
          <div className="form-section-heading"><div><span className="page-kicker">New source</span><h2>Add a public data source</h2></div></div>
          <div className="source-create-grid">
            <label className="form-label">Type<select className="form-select mt-1" value={form.type} onChange={(event) => setForm({ ...form, type: event.target.value })}>{SOURCE_TYPES.map((type) => <option key={type} value={type}>{type.replace("_", " ")}</option>)}</select></label>
            <FormInput label="Public URL" required value={form.url} onChange={(event) => setForm({ ...form, url: event.target.value })} />
          </div>
          <FormInput label="Keywords (comma-separated, optional)" value={form.keywords} onChange={(event) => setForm({ ...form, keywords: event.target.value })} />
          <p className="form-hint">For ecommerce product URLs, keywords help describe the analysis scope; they do not require every review to contain every term.</p>
          <div><button className="btn btn-primary" type="submit">Add Source</button></div>
        </form>
      )}
      <div className="source-list">
        {sources?.map((source) => <SourceCard key={source.id} source={source} expanded={expandedId === source.id} busy={busySourceId === source.id} latestResult={latestResults[source.id]} onCollect={onCollect} onDetails={(id) => setExpandedId((current) => current === id ? null : id)} onToggle={onToggle} onRemove={setRemoveTarget} />)}
        {sources?.length === 0 && <div className="empty-project-state"><strong>No data sources yet</strong><span>Add a controlled public source, or use dataset upload for local files.</span></div>}
      </div>
        </>
      )}
      <ConfirmationModal show={!!removeTarget} title="Remove data source?" message={`${sourceIdentity(removeTarget || {}).name} will be removed from this project. Reviews already collected from it will be retained.`} confirmLabel="Remove Source" confirmBusy={removing} onConfirm={confirmRemove} onCancel={() => !removing && setRemoveTarget(null)} />
    </div>
  );
}
