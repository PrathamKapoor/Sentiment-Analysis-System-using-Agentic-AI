import { useEffect, useState } from "react";
import { websiteApi } from "../services/websiteApi";
import PermissionGuard from "./PermissionGuard";
import LoadingSpinner from "./LoadingSpinner";

/**
 * Optional public business-context URL on a project.
 *
 * The product works fully without a URL. Setting one enables the
 * enhanced-report mode to include a small BUSINESS CONTEXT block in the
 * LLM prompt (title, meta description, headings, body excerpt). The
 * extraction is a single bounded public-page read; the URL is
 * never required, never auto-fetched, and can be cleared at any time.
 */
export default function ProjectWebsitePanel({ projectId }) {
  const [ctx, setCtx] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [draft, setDraft] = useState("");
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [saving, setSaving] = useState(false);

  const load = () => {
    setLoading(true);
    websiteApi.getContext(projectId)
      .then((r) => {
        setCtx(r.data.data.context);
        setDraft(r.data.data.context?.websiteUrl || "");
      })
      .catch(setError)
      .finally(() => setLoading(false));
  };
  useEffect(load, [projectId]);

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const trimmed = (draft || "").trim();
      const payload = { websiteUrl: trimmed || null, autoRefresh };
      const r = await websiteApi.setContext(projectId, payload);
      setCtx(r.data.data.context);
      setDraft(r.data.data.context?.websiteUrl || "");
    } catch (e) {
      setError(e);
    } finally {
      setSaving(false);
    }
  };

  const refresh = async () => {
    setSaving(true);
    setError(null);
    try {
      const r = await websiteApi.refreshContext(projectId);
      setCtx(r.data.data.context);
    } catch (e) {
      setError(e);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <LoadingSpinner />;

  const status = ctx?.status || "empty";

  return (
    <PermissionGuard permission="edit_project">
      <div className="card p-3 mb-3" aria-label="Optional business context website">
        <h6 className="mb-1">Optional business context</h6>
        <p className="text-muted small mb-2">
          Provide a public website to give the AI additional context about your
          organization, products, and terminology when generating an enhanced
          report. The URL is optional; the system works fully without one.
          When set, the application performs a single bounded public-page read
          (the URL itself, not a multi-page crawl) and stores a small,
          structured extraction locally.
        </p>
        <div className="row g-2 align-items-end">
          <div className="col-md-8">
            <label htmlFor="website-url" className="form-label small mb-1">
              Company / product website URL
            </label>
            <input
              id="website-url"
              type="url"
              className="form-control"
              placeholder="https://example.com"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              aria-describedby="website-help"
            />
            <div id="website-help" className="form-text small">
              Must be a public, reachable page. Localhost and private network
              addresses are rejected.
            </div>
          </div>
          <div className="col-md-4 d-flex gap-2 align-items-end">
            <div className="form-check pb-2">
              <input
                id="auto-refresh"
                className="form-check-input"
                type="checkbox"
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
              />
              <label htmlFor="auto-refresh" className="form-check-label small">
                Refresh on save
              </label>
            </div>
            <button
              type="button"
              className="btn btn-primary"
              onClick={save}
              disabled={saving}
              aria-label="Save website URL"
            >
              {saving ? "Saving…" : "Save"}
            </button>
          </div>
        </div>

        {ctx && status !== "empty" && (
          <div className="mt-3 small">
            <div>
              <strong>Status:</strong>{" "}
              <span className={`badge text-bg-${status === "ok" ? "success" : status === "pending" ? "secondary" : "warning"}`}>
                {status}
              </span>
              {ctx.extractedAt && (
                <span className="text-muted ms-2">
                  last fetched {new Date(ctx.extractedAt).toLocaleString()}
                </span>
              )}
            </div>
            {status === "ok" && (
              <ul className="list-unstyled mt-2 mb-0">
                {ctx.title && <li><strong>Title:</strong> {ctx.title}</li>}
                {ctx.metaDescription && <li><strong>Description:</strong> {ctx.metaDescription}</li>}
                {ctx.headings && ctx.headings.length > 0 && (
                  <li><strong>Headings:</strong> {ctx.headings.slice(0, 5).join(" · ")}</li>
                )}
                {ctx.contentHash && <li className="text-muted">content hash {ctx.contentHash.slice(0, 12)}…</li>}
              </ul>
            )}
            {ctx.failureReason && (
              <div className="alert alert-warning mt-2 mb-0">
                Last extraction failed: {ctx.failureReason}
              </div>
            )}
            <div className="mt-2">
              <button
                type="button"
                className="btn btn-sm btn-outline-secondary"
                onClick={refresh}
                disabled={saving || !ctx.websiteUrl}
                aria-label="Re-extract website content"
              >
                {saving ? "Refreshing…" : "Re-extract now"}
              </button>
            </div>
          </div>
        )}

        {error && (
          <div className="alert alert-danger mt-2 mb-0">
            {error?.response?.data?.error?.message || error?.message || "Could not save website context."}
          </div>
        )}
      </div>
    </PermissionGuard>
  );
}
