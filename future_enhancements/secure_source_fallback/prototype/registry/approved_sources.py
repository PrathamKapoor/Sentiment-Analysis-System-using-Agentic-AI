from ..models import SourceDefinition


class ApprovedSourceRegistry:
    """In-memory allow-list. Discovery never writes to this registry."""
    def __init__(self, sources: list[SourceDefinition], adapters: dict[str, object]):
        self._sources = {source.source_id: source for source in sources}
        self._adapters = dict(adapters)

    def sources(self) -> list[SourceDefinition]:
        return list(self._sources.values())

    def adapter_for(self, source: SourceDefinition):
        if source.adapter_name not in self._adapters:
            raise KeyError(f"No registered adapter for {source.source_id}")
        return self._adapters[source.adapter_name]
