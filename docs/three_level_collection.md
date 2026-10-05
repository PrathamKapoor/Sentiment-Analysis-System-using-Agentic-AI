# Three-level collection and product discovery

Collection keeps the existing `Review` table as its canonical evidence store.
The collection service records level, method, provider, and identity result in
the existing bounded `source_metadata` JSON field; no parallel evidence table
or schema migration is needed.

## Collection order

1. **Level 1 — direct source.** Existing Amazon/Flipkart HTML adapters, GitHub
   Issues API, imported CSV/XLSX/JSON, and other registered collectors remain
   in place. The direct adapter is preferred and later levels are skipped when
   it returns non-empty review text.
2. **Level 2 — configured scraping API.** If direct collection has no usable
   records, the enabled operator-configured provider is called once for a
   supported source type. The included RapidAPI adapter uses its configured
   host, base URL, and endpoint. It never follows provider redirects and caps
   time, response size, and result count. A process-local minimum request
   interval applies; HTTP 429 is reported without an automatic retry.
3. **Level 3 — approved retrieval with optional LLM search terms.** If Level 2
   also fails, the existing manually approved adapter registry is the only
   retrieval surface. Product-discovery suggestions may refine bounded search
   terms; they never choose a host, URL, tool, or source adapter. With no
   configured LLM, deterministic terms are used and the existing approved
   source fallback remains available.

Fallback runs only through an independently approved source. A direct
`robots.txt`, SSRF, CAPTCHA, disabled-source, or access-policy block is
terminal. Amazon India sign-in responses stop all Amazon requests; the
CollectionService may then try an independently approved provider, never an
Amazon login, challenge, or alternate Amazon endpoint. Other sign-in blocks
remain terminal. Timeout, HTTP/network, parse, no-record, or unusable-record
outcomes may proceed to configured alternatives.
For an Amazon product URL, collection carries its ASIN into fallback search and
uses the public product-page title when available. Those source-specific terms
lead the alternate-source query and the resulting review identity check; they
do not overwrite the project's saved product identity.
No provider or LLM response is treated as evidence until it contains non-empty
review text, provenance, and a deterministic product identity match. Uncertain
or wrong-variant records are excluded from automatic ingestion.

## Product discovery and identity matching

`POST /api/v1/projects/<id>/entity/discover` accepts a short description and
optional known identifiers/product URL and returns a reviewable draft: brand,
product, model, aliases, search terms, collection include/exclude terms,
security/competitor/custom annotation terms, and identifiers copied from known
input. It requires project access and `edit_project`. It does not persist its
response; an editor reviews suggestions and saves accepted terms in the
existing project entity panel. Configured data sources remain explicit and
project-scoped. The existing bulk-collection action applies the same project
identity across all enabled sources.

Adding a source in the UI is URL-only: the server infers the registered source
type, then the UI automatically discovers and saves bounded product search and
annotation terms (when the user has project edit permission) and starts
collection. Collection may also use LLM search terms on the approved fallback
path; model output never chooses the source URL or adapter. Term discovery
failure or missing edit permission does not block collection.

LLM JSON has a strict schema, bounded lists and strings, and no URL field.
The model cannot invent identifier values: any suggested value must exactly
match a user-supplied identifier; an ASIN may also be extracted from a supplied
Amazon product URL. Security and competitor terms remain annotations and are
not security findings or verified competitor claims. The project entity panel
uses editable key/value rows instead of requiring identifier JSON.
Invalid output, timeout, exception, or missing credentials causes one attempt
at the configured fallback LLM, then deterministic extraction. The requested
canonical name always remains the user's own input. Identity matching is a
rule-based heuristic, not calibrated probability: exact canonical name, exact
SKU/identifier, or exact canonical URL can verify a result; known variants
such as Ultra, FE, Plus, Pro, Max, Mini, Lite, and SE are rejected when they
are not the requested model. Matches that cannot be established are uncertain
and do not enter the evidence set.

Level 3 LLM output is limited to search-term suggestions. Retrieved review text
must come from an actual response by an already approved retrieval adapter.
No evidence means `NO_DATA_AVAILABLE`; the model never supplies reviews,
ratings, prices, URLs, provenance, or product facts.

## Local configuration

The backend's existing dotenv loader reads `backend/.env`; start from
`backend/.env.example`. For Docker Compose, Compose reads the ignored repository
root `.env` for interpolation. Copy only the needed non-secret configuration
and secrets into the appropriate local file. Production deployments should
provide the same variables through their secret/environment manager, not bake
`.env` into an image.

```env
# Main and fallback are separate OpenAI-compatible endpoints.
LLM_MAIN_API_KEY=
LLM_MAIN_BASE_URL=
LLM_MAIN_MODEL=
LLM_FALLBACK_API_KEY=
LLM_FALLBACK_BASE_URL=
LLM_FALLBACK_MODEL=

# Configure only an API product to which you have access.
SCRAPING_RAPIDAPI_ENABLED=false
SCRAPING_RAPIDAPI_KEY=
SCRAPING_RAPIDAPI_HOST=
SCRAPING_RAPIDAPI_BASE_URL=
SCRAPING_RAPIDAPI_ENDPOINT=
SCRAPING_RAPIDAPI_SOURCE_TYPES=ecommerce

COLLECTION_DIRECT_ENABLED=true
COLLECTION_SCRAPING_ENABLED=true
COLLECTION_LLM_FALLBACK_ENABLED=true
COLLECTION_MAX_LEVEL=3
COLLECTION_REQUEST_TIMEOUT_SECONDS=30
COLLECTION_MAX_RESULTS_PER_SOURCE=100
COLLECTION_REQUIRE_IDENTITY_MATCH=true
PRODUCT_DISCOVERY_LLM_ENABLED=true
PRODUCT_DISCOVERY_MAX_KEYWORDS=20
```

Older `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_BASE_URL`, and `LLM_MODEL` settings
remain supported as the legacy main provider. They do not populate the fallback
provider. Each new role is enabled only when its own key, base URL, and model
are all configured. For an additional LLM vendor, use an OpenAI-compatible
chat-completions endpoint or add a tested implementation of `LLMProvider` and
register it in `backend/app/services/llm/provider.py`. For another scraping
vendor, implement the small provider contract in
`backend/app/services/scraping_providers.py`, enforce fixed configured hosts,
SSRF validation, response/time/result caps, and normalize only actual review
records. The provider list is a registry so separately configured
implementations can be enabled without changing collection orchestration; only
RapidAPI has a built-in implementation today.

## Provenance and operations

Each review retains its existing data-source relation, source record ID/URL,
collection timestamp, provider/method/level, and identity match reason. The
collection response and audit event include level attempts, bounded provider
status, durations, counts, and identity discovery provider role/model. They
never include API keys, authorization headers, raw provider responses, full
review text, or `.env` contents. Review Management displays level, method,
identity status, and collection time. Reports retain their source and date
provenance without exposing credentials.

The providers in automated tests are mocked. Live RapidAPI and live LLM
integration require operator credentials and were not exercised by those
tests. Third-party provider terms, quotas, endpoint schemas, and source access
rights must be reviewed by the operator.
