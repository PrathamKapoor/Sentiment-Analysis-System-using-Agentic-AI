# Security Policy

The Agentic AI-Based Sentiment Analysis Management System treats a small set
of properties as P0 (see `AGENTS.md` §40): organisation (tenant) isolation,
authentication/permission enforcement, SSRF containment in the collection
layer, agent tool safety (no arbitrary shell/SQL/HTTP tools), secret
handling, and migration/data integrity.

## Supported versions

| Version | Supported |
| ------- | --------- |
| current `master` (post-Phase 14) | ✅ |

## Reporting a vulnerability

Please report suspected security issues **privately by email** to
[prathamkapoor027@gmail.com](mailto:prathamkapoor027@gmail.com) instead of
opening a public issue. Include:

- a description of the affected capability (auth, tenancy, collection,
  agents, reports, storage, rate limiting);
- steps to reproduce on a local development instance;
- the impact you believe is reachable.

You should receive an acknowledgement within 7 days. Do not disclose the
issue publicly until it has been triaged and fixed.

## What is already hardened (and where to read it)

- **Tenant isolation** — backend authorization in `app/decorators/auth.py`;
  cross-tenant access returns 404 to avoid resource-existence leaks.
  Covered by `tests/test_projects.py` and friends.
- **SSRF containment** — URL shape + DNS + connect-time re-validation in
  `app/services/collectors/security.py` (thread-local guard), with a
  documented blocked-range policy and a dev-only
  `SCRAPER_ALLOW_PRIVATE_TARGETS` escape hatch that is never
  request-controllable. Covered by `tests/test_collection.py`,
  `tests/test_website_security.py`.
- **Prompt-injection / agent tool safety** — external text is untrusted
  analytical content only; agents call explicit trusted services
  (`app/services/agents/`), never generic tools. Covered by
  `tests/test_prompt_injection.py`, `tests/test_deterministic_boundary.py`.
- **Auth tokens** — JWT with server-side revocation
  (`app/services/token_service.py`, fail-closed against Redis outage);
  rate limiting on login/register/report creation (`app/limiter.py`).
- **Client routing** — `react-router-dom` upgraded 6.x → 7.18.4 to clear
  GHSA-wrjc-x8rr-h8h6 (open redirect via backslash in `<Link>` /
  `useNavigate`) and GHSA-337j-9hxr-rxhxg (constructor injection via
  `deserializeErrors()` in SSR hydration). The app is a client-rendered SPA
  and never uses SSR hydration or `deserializeErrors`, so the second was not
  reachable here, but both are cleared. Verified in a real browser: all
  authenticated routes, nested routes and client-side navigation still work
  with 0 console and 0 page errors.
- **Dependency hygiene** — `pip-audit -r requirements.txt` reports no known
  vulnerabilities (16 advisories across 5 packages were cleared: Flask,
  Flask-CORS, marshmallow, python-dotenv, pytest). `npm audit` reports 0
  vulnerabilities in both the production and dev trees.

## Scope notes

This is an academic research system, not a commercial service. Findings
related to the experimental prototype under `future_enhancements/` (not in
production) are welcome but handled at lower priority than production code.
