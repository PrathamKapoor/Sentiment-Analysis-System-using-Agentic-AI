# Customer and security intelligence: implemented scope

This document records the customer/security intelligence additions currently
implemented in this repository. It is intentionally narrower than the long-term
product vision: absent capabilities below are not implied to exist.

## VERIFIED in code

- A project can store one canonical entity at `project_entities`: brand,
  product, model, SKU, canonical URL, aliases, identifiers, and inclusion,
  exclusion, security, competitor, and custom keyword groups.
- Project Details exposes the entity form. The API is
  `GET/PUT /api/v1/projects/{projectId}/entity`; project access is enforced and
  updates require `edit_project`.
- Project Details includes a deterministic competitor evidence panel backed by
  `GET /api/v1/projects/{projectId}/analysis/competitors`. It matches only the
  project-configured competitor phrases, excludes deleted/spam/duplicate
  reviews, and returns one result per review/competitor pair with exact source
  spans, source origin, and stored sentiment where available. A switching signal
  requires explicit switching language naming that competitor as destination.
  The quoted reason is text after `because`, `since`, or `as`; it is
  an attributed statement, not validated causality. Results are derived live
  from the latest 5,000 eligible reviews and are not persisted.
- Project Details includes deterministic feedback category results from
  `GET /api/v1/projects/{projectId}/analysis/feedback-categories`. Categories
  include praise, complaint, bug, feature request, question, usability,
  performance, support, pricing, churn, competitive, security, privacy, fraud,
  and OTHER. Evidence spans accompany matched phrases; configured project
  competitor/security terms participate. Categories may overlap. OTHER means
  no configured rule matched, not a semantic judgement. This partial phrase
  vocabulary is recomputed from current reviews (5,000 scan / 500 record cap),
  not persisted, and has no confidence score.
- Canonical entity resolution is deterministic and performs no network fetch.
  It feeds the existing approved-source fallback resolver.
- A project source of type `github_issues` uses the fixed official GitHub REST
  API adapter for public repositories. It excludes pull requests, bounds page,
  record, response, retry, and timeout use, rejects redirects, omits author
  names, and explicitly warns that issues are community reports rather than a
  representative review sample. `GITHUB_TOKEN` is optional and server-side;
  without it GitHub's lower unauthenticated rate limit applies.
- Directly collected reviews now retain bounded item provenance in migration
  `0014`: provider record ID, sanitized item URL, small JSON metadata, and
  retrieval timestamp. Query strings, fragments, and URL credentials are
  removed. Review APIs expose these fields and the review list links to the
  source item. Reports prefer item URLs over generic source URLs.
- During direct source collection, source and project inclusion keywords use
  case-insensitive phrase matching with any-match semantics. Project exclusion
  matches take precedence. Filtered-record counts and an applied-status marker
  are returned in the collection result. This is an ingest filter, not a
  downstream filter that hides already-imported reviews.
- Dataset-imported and collected reviews retain structured `keywordMatches`
  annotations for matched terms. Security, competitor, and custom terms are
  annotations; they do not discard feedback. Dataset imports are not filtered
  by project inclusion/exclusion groups.
- Security rules detect a small set of explicit phrases for account compromise,
  personal-data exposure, payment fraud, phishing/impersonation, authentication
  failure, malware reports, application-vulnerability reports, and TLS
  certificate failures. Findings retain the exact matched evidence and source
  offsets, review, project, organisation, severity label, method, and review
  state. The rules do not claim to verify the reported event; confidence is
  left null because the phrase rules are not statistically calibrated.
- Project Details has an evidence-linked security signal queue. A user with the
  `review_security_findings` permission can run analysis and mark a finding
  confirmed or dismissed with analyst notes. The role is granted to organisation
  owners, administrators, project managers, and analysts. A confirmed signal
  remains a manually reviewed customer report, not a verified cyber incident.
- Reanalysis reconciles evidence against the current eligible review text.
  Findings for changed or no-longer-eligible source reviews are marked `stale`;
  changed matching evidence returns to `needs_review` and clears the prior
  human decision/notes. Stale findings cannot be confirmed until analysis is
  rerun. Historical matched evidence is retained and labelled stale.
- Finding routes are project/organisation scoped and hide cross-tenant resources
  with 404. Finding creation is idempotent by review and finding type.
- PDF/Excel reports can include security findings and an appendix with source
  identifiers, bounded source URLs, eligible record counts/date spans,
  collection-method caveats, evidence, and defined trust labels. Security text
  signals are explicitly described as unverified customer reports. Excel
  writes formula-like external strings as literal cells. Representative-review
  samples obey the report period and exclude deleted, spam, and duplicate rows.
- Migrations `0010`–`0014` add entity data, review keyword matches, security
  findings, source-review fingerprinting, and item-level review provenance.
  The PostgreSQL migration audit script
  now checks upgrade, downgrade to 0009, and re-upgrade in a uniquely named
  temporary schema.
- `frontend/vercel.json` supports SPA route deep links. Vercel setup documented
  here deploys the Vite frontend only; the existing Flask service remains a
  separate managed/container deployment.

## Implemented in the current local extension (not released)

- `Review.id` is the canonical evidence ID. Evidence serialization checks
  project scope and eligible-review visibility and retains stored provenance.
- Exact duplicate relationships live in `review_duplicate_links`; original
  reviews remain intact. Detection uses provider identity, sanitized item URL,
  or normalized exact text hash. Source summaries distinguish source records,
  canonical evidence, and duplicate links.
- On-demand temporal comparisons use the current window and immediately
  preceding explicit baseline. Emerging themes use phrase-category/aspect
  rate increases; anomalies include review volume and stored signal rates.
  Large windows disclose their bounded sampling.
- Root-cause evidence separates facts, observations, version overlap
  correlations, hypotheses, and recommendations. It does not infer causation.
- Security indicator extraction identifies syntax-supported URLs/domains,
  valid IPv4 values, CVEs, and SHA-256 values as `OBSERVED`; no reputation
  lookup is performed. Correlation returns observed patterns or possible
  incidents, never a confirmed incident.
- Current deterministic security phrase coverage maps to account compromise,
  personal-data exposure, payment fraud, phishing/impersonation,
  authentication failure, malware reports, application vulnerability reports,
  and TLS/certificate failures; it is not the full proposed taxonomy.
- Persisted investigations use project/organization-scoped records, a finite
  read-only tool registry, strict JSON/evidence validation, PostgreSQL leases,
  bounded retries, deterministic no-LLM summaries, and persisted review state.
  Investigation reads only already-ingested evidence.

## DOCUMENTED by existing project material

- The existing product uses deterministic VADER sentiment, local topic/aspect
  analytics, organization RBAC, dataset ingestion, reports, and synchronous
  controlled collection. See the root README and production deployment guide.
- Reddit collection remains unavailable in the production collector, even if
  credentials are configured; there is no HTML scraping fallback.
- An optional OpenAI-compatible provider supports enhanced report
  interpretation and the separately bounded persisted investigator. Neither
  provider path is a scraper or arbitrary network tool.

## INCOMPLETE / not implemented

- No general cross-source search/router UI for YouTube, forums, social networks,
  general review sites, or Hacker News. GitHub Issues is one configured
  repository adapter, not product-wide source discovery. The Reddit fallback
  slot remains narrow and its current collector reports unavailable; it is not
  a general search service and does not bypass blocked collection.
- No semantic/exhaustive feedback classifier, LLM entity writer, LLM scraper,
  arbitrary tool calling, or model-directed branching. The investigator uses
  a fixed registered read-only tool set over already-ingested reviews.
- Duplicate matching is conservative and exact (source-scoped provider ID, sanitized URL, or
  normalized full-text hash); near-duplicate semantic similarity is not used.
- Temporal categories are deterministic phrase/aspect signals over explicit
  adjacent periods; there is no calibrated significance test or semantic theme
  clustering. Large periods are sampled with limits disclosed.
- Security indicators are syntactic observations only. There is no reputation
  service, authoritative incident verification, CTI/STIX export, or ATT&CK/ATLAS
  mapping. Customer reports cannot be automatically marked confirmed.
- Findings are generated only when a permitted user explicitly runs analysis;
  collection and upload do not automatically invoke security rules yet.
- The security phrase list is deliberately small and cannot be used to establish
  that an attack occurred. It may miss paraphrases and requires human review.
- No live Vercel deployment, production database migration, or external
  object-storage setup was performed.
  Vercel deployment instructions are frontend-only. The backend's 25 MiB upload
  contract, persistent file handling, Redis state, and process-local serialized collection require redesign before a Vercel
  Function backend can be considered. Vercel supports Flask; the current repo
  does not configure or verify that deployment. See the current platform
  boundary in `docs/vercel_frontend_deployment.md`.

## API example

Save an entity and project keywords:

```http
PUT /api/v1/projects/{projectId}/entity
Authorization: Bearer <access-token>
X-Organisation-Id: <organisation-id>
Content-Type: application/json
```

```json
{
  "brand": "Samsung",
  "product": "Galaxy S25",
  "model": "S25",
  "canonicalUrl": "https://www.flipkart.com/samsung-galaxy-s25/",
  "aliases": ["Samsung S25", "Galaxy S25"],
  "includeKeywords": ["camera", "battery"],
  "excludeKeywords": ["case"],
  "securityKeywords": ["account access", "privacy"],
  "competitorKeywords": ["Pixel 10", "iPhone 17"]
}
```

Run deterministic finding analysis and fetch its evidence-linked results:

```http
POST /api/v1/projects/{projectId}/security-findings/analyze
GET  /api/v1/projects/{projectId}/security-findings
```

The analyze endpoint is deterministic and idempotent. Human status updates use
`PATCH /api/v1/projects/{projectId}/security-findings/{findingId}` with
`{"status":"confirmed"}` or `{"status":"dismissed"}` and optional
`analystNotes`.

Fetch configured competitor mentions and explicit switching evidence:

```http
GET /api/v1/projects/{projectId}/analysis/competitors
Authorization: Bearer <access-token>
X-Organisation-Id: <organisation-id>
```

The endpoint returns `items`, a summary, and limitations. Configure competitor
phrases through the project entity API first. This is local phrase matching over
already-ingested reviews, not cross-site search or a general source router.

Fetch deterministic feedback categories and exact phrase evidence:

```http
GET /api/v1/projects/{projectId}/analysis/feedback-categories
Authorization: Bearer <access-token>
X-Organisation-Id: <organisation-id>
```

The response contains per-category counts, review IDs, evidence spans, scan and
result caps, and method limitations. Counts can overlap because one review can
match several categories.
