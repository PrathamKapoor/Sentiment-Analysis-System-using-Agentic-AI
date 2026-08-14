# Controlled two-level source fallback

`DataCollectionAgent` continues to call only `CollectionService`.

1. **Level 0 — Direct collection:** existing permitted collector runs first.
2. **Level 1 — API discovery:** optional, bounded catalog connectors produce
   untrusted metadata candidates only. Discovery does not approve or execute
   a provider.
3. **Level 2 — Approved API execution:** only a concrete adapter manually
   registered in `ApprovedSourceRegistry` may be used. There is no generic
   `execute(url)` capability, and catalog URLs, user data, and responses
   cannot set request hosts.

The runtime default is `CURATED_ONLY`. The first approved adapter is the
**official Reddit OAuth API** (`reddit_official_discussions`), configured only
through `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, and optional
`REDDIT_USER_AGENT`. It searches a bounded set of relevant product discussion
posts and normalizes returned comment bodies; it is not an Amazon-review proxy.
Its fixed hosts are `www.reddit.com` (OAuth token) and `oauth.reddit.com`
(search/comments), and every request is validated by the existing SSRF guard.

Reddit requires OAuth access. Missing credentials, malformed responses,
timeouts, rate limiting, and unavailable service all end safely without
fabricating records. It preserves provenance as “Reddit public discussions via
official OAuth API”; this provider supplies public discussion/comment text,
not verified e-commerce purchase reviews. It has no configured credentials in
this repository, so live Samsung Galaxy S25 data is not claimed.

Fallback batches retain requested source, requested URL, canonical entity,
direct status, adapter/provider, actual source, and count in the existing
collection audit metadata. No database migration is required; existing review
deduplication remains in `CollectionService`.

Threat controls: finite catalog/query/source/time budgets prevent discovery
explosion and loops; irrelevant categories are filtered; catalog/API content
is inert data; only allow-listed concrete adapters are executable; adapter
configuration owns fixed hosts and must retain the collection SSRF boundary;
raw responses and credentials are not audited. Provider compromise, rate
limits, malformed data, duplicate amplification, provenance laundering,
redirects, and DNS rebinding remain explicit adapter-review requirements.
