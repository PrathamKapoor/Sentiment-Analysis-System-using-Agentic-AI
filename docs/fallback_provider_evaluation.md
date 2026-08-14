# Fallback provider evaluation

| Provider | Data | Auth | Provenance | Decision |
|---|---|---|---|---|
| Reddit Official OAuth API | Public product-discussion posts and comment text; bounded search and thread comments | OAuth client credentials | Reddit and post/comment permalink are retained | **APPROVED_FOR_DELIVERABLE** |
| WooCommerce Store/REST APIs | Review text is documented, but each shop exposes its own endpoint/product IDs and access policy | Varies by store | Shop-specific | RESEARCH_ONLY |
| BigCommerce Catalog Reviews API | Review text is documented for a merchant's own catalogue | Store API credentials | Merchant catalogue | UNSUITABLE for arbitrary public product lookup |
| Amazon Product Advertising API | Product catalogue/editorial data; not a suitable independent consumer-review fallback for this system | Associate credentials | Amazon | REJECTED: not used to bypass Amazon collection restrictions |
| API directories/catalogs | Metadata only | Varies | Varies | RESEARCH_ONLY; never automatically executed |

## Approved provider: Reddit Official OAuth API

Reddit's documented API provides listings, search, and comments. The adapter
uses OAuth client credentials, searches a bounded product alias, requests at
most three comment threads, and accepts only relevant comment bodies. It does
not scrape Reddit HTML and does not claim Reddit comments are Amazon reviews.

The API's applicable limits and access rules are controlled by Reddit and the
configured application. This project does not sign up, accept terms, or obtain
credentials automatically. The integration is suitable for academic/demo use
only after the operator reviews Reddit's current terms and registers a client.
