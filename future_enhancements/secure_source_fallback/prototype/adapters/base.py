from abc import ABC, abstractmethod
from typing import Any

from ..models import Intent, SourceDefinition


class SourceAdapter(ABC):
    @abstractmethod
    def search(self, source: SourceDefinition, intent: Intent) -> list[dict[str, Any]]:
        """Return structured records only; adapters cannot invoke a resolver."""
