# External fallback provider setup

The production collection path and structured product-discovery providers are
documented in [`three_level_collection.md`](./three_level_collection.md).
RapidAPI credentials and endpoint values are operator configuration; only a
user-authorized endpoint with reviewed terms and a tested response schema
should be used. The application does not hard-code the example marketplace
provider or endpoint.

## Optional OpenRouter and NVIDIA LLMs

The backend uses OpenAI-compatible chat completions. `backend/.env.example`
configures OpenRouter as the primary for report interpretation and structured
product discovery, with NVIDIA's compatible endpoint as each fallback. Add
actual credentials only to ignored `backend/.env` or a deployment secret store:

```text
OPENROUTER_API_KEY=<OpenRouter key>
NVIDIA_API_KEY=<NVIDIA key>
```

Report interpretation uses `apodex/apodex-1.1-mini:free` and falls back to
`z-ai/glm-5.3-flash`. Product discovery uses `poolside/laguna-s-2.1:free` and
falls back to `deepseek-ai/deepseek-v4.1-flash`. If a provider fails or returns
unusable structured output, the app proceeds to its next configured fallback
and ultimately its deterministic behavior. Model output is never authoritative
product evidence.

## Reddit Official OAuth API

1. Create an OAuth application through Reddit's developer process and review
   its current API access rules.
2. Set these server-side variables in `backend/.env` (never in frontend code):

```text
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
REDDIT_USER_AGENT=SentimentAnalysisSystem/1.0
```

3. Restart the Flask backend. No migration is needed.
4. In Data Sources, collect a permitted e-commerce/review source. If its
   direct collection returns no review elements, the controlled fallback may
   search relevant Reddit discussion comments.

The adapter uses only `www.reddit.com` and `oauth.reddit.com`, with SSRF
validation, short timeouts, two retries, a 5 MB response cap, finite aliases,
and a one-minute global fallback budget. Missing credentials, rate limits,
timeouts, malformed data, and outages result in an actionable message or safe
`NO_DATA_AVAILABLE`; use the existing dataset upload flow for offline demos.

## Manual acceptance

Configure a project for a product, add a source, and choose **Collect Now**.
Verify the collection details state identifies the requested source, fallback
provider, actual source, and record count. Then open Reviews and run the
existing sentiment analysis. Do not label Reddit comments as Amazon reviews.
