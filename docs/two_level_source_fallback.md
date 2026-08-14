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

The runtime default is `CURATED_ONLY`; no provider is currently approved or
configured. Therefore a direct collection with no usable records ends safely
as `NO_DATA_AVAILABLE` until a documented, permitted provider is reviewed and
registered. This never bypasses a requested site's robots, challenge,
authentication, or access restrictions.

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
