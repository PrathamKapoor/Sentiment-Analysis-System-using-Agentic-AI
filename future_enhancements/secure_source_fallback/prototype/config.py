from dataclasses import dataclass


@dataclass(frozen=True)
class FallbackConfig:
    max_fallback_sources: int = 5
    max_retries_per_source: int = 2
    max_fallback_depth: int = 1
    max_total_fallback_time_seconds: float = 60.0
