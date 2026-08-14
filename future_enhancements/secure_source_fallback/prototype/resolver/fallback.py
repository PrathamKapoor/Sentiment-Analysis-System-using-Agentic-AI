from ..budgets import ResolutionBudget
from ..errors import CredentialRequiredError, PolicyBlockedError, RateLimitError, ResolverTimeoutError, SourceUnavailableError
from ..models import ResolutionResult, ResultStatus
from ..normalization.review import normalize_reviews
from ..provenance.trace import ProvenanceTrace
from .ranking import rank_sources


class FallbackResolver:
    """Single-pass only: registered adapters have no resolver reference."""
    def __init__(self, registry):
        self.registry = registry

    def resolve(self, intent, *, direct_collection_possible=False, fallback_reason="DIRECT_COLLECTION_NOT_PERMITTED", budget=None):
        budget = budget or ResolutionBudget()
        trace = ProvenanceTrace(intent, direct_collection_possible, fallback_reason)
        candidates = rank_sources(intent, self.registry.sources())
        trace.candidates_considered = [source.source_id for source in candidates]
        if not candidates:
            return ResolutionResult(ResultStatus.NO_APPROVED_SOURCE, intent.entity, provenance=trace.to_dict(ResultStatus.NO_APPROVED_SOURCE.value, 0), message="No approved source supports the requested capability.")
        outcomes = []
        for source in candidates:
            try:
                can_attempt = budget.consume_source(source.source_id)
            except ResolverTimeoutError:
                return ResolutionResult(ResultStatus.TIMEOUT, intent.entity, provenance=trace.to_dict(ResultStatus.TIMEOUT.value, 0))
            if not can_attempt:
                break
            if not source.allowed or not source.enabled:
                trace.attempt(source.source_id, "POLICY_BLOCKED")
                outcomes.append(ResultStatus.POLICY_BLOCKED)
                continue
            if source.requires_api_key and not source.credential_configured:
                trace.attempt(source.source_id, "API_CREDENTIALS_REQUIRED")
                outcomes.append(ResultStatus.API_CREDENTIALS_REQUIRED)
                continue
            if not source.available:
                trace.attempt(source.source_id, "SOURCE_UNAVAILABLE")
                outcomes.append(ResultStatus.SOURCE_UNAVAILABLE)
                continue
            adapter = self.registry.adapter_for(source)
            while budget.consume_retry(source.source_id):
                try:
                    records = normalize_reviews(adapter.search(source, intent), intent.entity)
                    if records:
                        trace.attempt(source.source_id, "SUCCESS", len(records))
                        return ResolutionResult(ResultStatus.SUCCESS, intent.entity, records, trace.to_dict(ResultStatus.SUCCESS.value, len(records)))
                    trace.attempt(source.source_id, "NO_USABLE_DATA")
                    break
                except SourceUnavailableError:
                    trace.attempt(source.source_id, "SOURCE_UNAVAILABLE")
                    outcomes.append(ResultStatus.SOURCE_UNAVAILABLE)
                except RateLimitError:
                    trace.attempt(source.source_id, "RATE_LIMITED")
                    outcomes.append(ResultStatus.RATE_LIMITED)
                except CredentialRequiredError:
                    trace.attempt(source.source_id, "API_CREDENTIALS_REQUIRED")
                    outcomes.append(ResultStatus.API_CREDENTIALS_REQUIRED)
                except PolicyBlockedError:
                    trace.attempt(source.source_id, "POLICY_BLOCKED")
                    outcomes.append(ResultStatus.POLICY_BLOCKED)
                except ResolverTimeoutError:
                    return ResolutionResult(ResultStatus.TIMEOUT, intent.entity, provenance=trace.to_dict(ResultStatus.TIMEOUT.value, 0))
                except Exception:
                    # Adapter exceptions are never surfaced to callers or logs as
                    # raw provider details. Continue only within the shared budget.
                    trace.attempt(source.source_id, "INTERNAL_ERROR")
                    outcomes.append(ResultStatus.INTERNAL_ERROR)
                    break
        status = outcomes[-1] if outcomes and len(outcomes) == 1 else ResultStatus.NO_DATA_AVAILABLE
        return ResolutionResult(status, intent.entity, provenance=trace.to_dict(status.value, 0), message="No approved source returned sufficient matching data.")
