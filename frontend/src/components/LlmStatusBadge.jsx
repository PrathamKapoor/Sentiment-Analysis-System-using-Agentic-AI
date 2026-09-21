import { useEffect, useState } from "react";
import { llmApi } from "../services/llmApi";

/**
 * Small badge that shows whether an LLM is configured for this
 * environment. Falls back to "deterministic" silently if the endpoint
 * is unreachable (e.g. the user has no token, or the server is down).
 */
export default function LlmStatusBadge() {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    llmApi.status()
      .then((r) => { if (!cancelled) setStatus(r.data.data); })
      .catch(() => { if (!cancelled) setError(true); });
    return () => { cancelled = true; };
  }, []);

  if (error) {
    return (
      <span
        className="badge text-bg-secondary"
        title="LLM status is unavailable in this environment."
        aria-label="LLM status unavailable"
      >
        LLM status unavailable
      </span>
    );
  }
  if (!status) {
    return <span className="badge text-bg-light" aria-label="Loading LLM status">LLM status loading…</span>;
  }
  if (!status.configured) {
    return (
      <span
        className="badge text-bg-secondary"
        title="No LLM is configured for this environment. Reports will use the deterministic fallback."
        aria-label="Deterministic fallback only"
      >
        Deterministic fallback only
      </span>
    );
  }
  return (
    <span
      className="badge text-bg-success"
      title={`LLM configured: ${status.provider} (${status.model || "model unspecified"})${status.baseUrlHost ? " @ " + status.baseUrlHost : ""}`}
      aria-label={`LLM enabled: ${status.provider}`}
    >
      LLM enabled — {status.provider}
    </span>
  );
}
