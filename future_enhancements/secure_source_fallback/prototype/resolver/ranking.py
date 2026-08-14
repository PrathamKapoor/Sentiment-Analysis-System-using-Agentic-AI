from ..models import Capability, Intent, SourceDefinition


def rank_sources(intent: Intent, sources: list[SourceDefinition]) -> list[SourceDefinition]:
    needed = intent.required_capabilities
    def score(source: SourceDefinition):
        exact = 0 if source.capabilities and source.capabilities[0] == needed[0] else 1
        compatible = 0 if any(capability in source.capabilities for capability in needed) else 1
        return (compatible, exact, 0 if source.allowed and source.enabled else 1, 0 if source.available else 1, 0 if not source.requires_api_key or source.credential_configured else 1, source.priority, source.source_id)
    return sorted((s for s in sources if any(c in s.capabilities for c in needed)), key=score)
