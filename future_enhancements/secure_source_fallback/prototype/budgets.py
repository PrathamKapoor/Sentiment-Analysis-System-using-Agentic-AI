from dataclasses import dataclass, field
from time import monotonic

from .errors import ResolverTimeoutError


@dataclass
class ResolutionBudget:
    """One resolver-owned decrement-only budget; adapters receive no reset API."""
    max_sources: int = 5
    max_retries_per_source: int = 2
    max_depth: int = 1
    max_seconds: float = 60.0
    depth: int = 1
    _started: float = field(default_factory=monotonic, repr=False)
    _sources_used: int = 0
    _retries: dict[str, int] = field(default_factory=dict, repr=False)

    def check_time(self) -> None:
        if monotonic() - self._started > self.max_seconds:
            raise ResolverTimeoutError("The bounded fallback time budget was exhausted.")

    def consume_source(self, source_id: str) -> bool:
        self.check_time()
        if self.depth > self.max_depth or self._sources_used >= self.max_sources:
            return False
        self._sources_used += 1
        return True

    def consume_retry(self, source_id: str) -> bool:
        self.check_time()
        used = self._retries.get(source_id, 0)
        if used >= self.max_retries_per_source:
            return False
        self._retries[source_id] = used + 1
        return True

    @property
    def sources_used(self) -> int:
        return self._sources_used
