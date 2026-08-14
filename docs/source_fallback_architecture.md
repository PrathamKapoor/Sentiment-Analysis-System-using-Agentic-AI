# Source fallback architecture

```text
DataCollectionAgent -> CollectionService -> Level 0 direct collector
                                      -> approved Reddit OAuth adapter
                                      -> existing Review ingestion/analysis
```

Level 1 catalog discovery produces untrusted metadata only; it cannot grant
execution authority. Level 2 executes only entries manually declared in
`RUNTIME_REGISTRY`. The Reddit adapter has fixed HTTPS hosts and server-side
credentials, applies the shared SSRF connection protection, bounds requests,
and records request/provider/actual-source provenance in the existing
`collection.completed` audit metadata. The review's existing data source stays
the requested source, while the audit batch accurately records fallback origin.

When the provider is not configured, rate limited, unavailable, or returns no
relevant data, the collection remains synchronous and safely terminates. No
loop, generic HTTP tool, arbitrary URL, new table, or migration is introduced.
