# Architecture

```mermaid
flowchart TD
  A[Requested URL or topic] --> B[Deterministic intent extraction]
  B --> C[ApprovedSourceRegistry]
  C --> D[Deterministic capability ranking]
  D --> E[Bounded FallbackResolver]
  E --> F[Registered adapter]
  F --> G[Normalize reviews]
  G --> H[Provenance + terminal result]
```

Future production flow only (not implemented):

```mermaid
flowchart LR
  A[DataCollectionAgent] --> B[CollectionService]
  B --> C[Fallback Resolver]
  C --> D[ApprovedSourceRegistry]
  D --> E[Registered Adapter]
```

The agent must never call the resolver directly. Discovery is informational only; it cannot add sources or fetch arbitrary endpoints. Adapters cannot receive a resolver reference, so recursive fallback is structurally excluded.
