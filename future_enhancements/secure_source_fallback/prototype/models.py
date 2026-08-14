from dataclasses import dataclass, field
from datetime import date as Date, datetime, timezone
from enum import Enum
from typing import Any


class Capability(str, Enum):
    PRODUCT_REVIEWS = "PRODUCT_REVIEWS"
    PRODUCT_DISCUSSION = "PRODUCT_DISCUSSION"
    PRODUCT_RATINGS = "PRODUCT_RATINGS"
    PRODUCT_METADATA = "PRODUCT_METADATA"
    PUBLIC_DISCUSSION = "PUBLIC_DISCUSSION"


class AccessMethod(str, Enum):
    PUBLIC_API = "PUBLIC_API"
    AUTHENTICATED_API = "AUTHENTICATED_API"
    MANUAL_UPLOAD = "MANUAL_UPLOAD"
    UNAVAILABLE = "UNAVAILABLE"


class ResultStatus(str, Enum):
    SUCCESS = "SUCCESS"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    NO_DATA_AVAILABLE = "NO_DATA_AVAILABLE"
    NO_APPROVED_SOURCE = "NO_APPROVED_SOURCE"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    API_CREDENTIALS_REQUIRED = "API_CREDENTIALS_REQUIRED"
    RATE_LIMITED = "RATE_LIMITED"
    POLICY_BLOCKED = "POLICY_BLOCKED"
    INVALID_REQUEST = "INVALID_REQUEST"
    TIMEOUT = "TIMEOUT"
    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass(frozen=True)
class Intent:
    entity: str
    category: str
    requested_source: str | None
    required_capabilities: tuple[Capability, ...]


@dataclass(frozen=True)
class SourceDefinition:
    source_id: str
    display_name: str
    source_type: str
    access_method: AccessMethod
    base_url: str
    capabilities: tuple[Capability, ...]
    requires_api_key: bool = False
    credential_configured: bool = False
    available: bool = True
    enabled: bool = True
    priority: int = 100
    allowed: bool = True
    policy_status: str = "APPROVED"
    provenance_label: str = ""
    adapter_name: str = ""


@dataclass(frozen=True)
class NormalizedReview:
    external_id: str | None
    text: str
    reviewer: str | None = None
    rating: float | None = None
    date: Date | None = None
    source_url: str | None = None
    language: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EncryptedSecret:
    ciphertext: bytes
    wrapped_data_key: bytes
    nonce: bytes
    authentication_tag: bytes
    key_version: str
    algorithm: str = "AES-256-GCM+RSA-OAEP-SHA256"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def public_dict(self) -> dict[str, str]:
        """Safe serialization: ciphertext is encoded but plaintext is impossible to emit."""
        import base64
        return {
            "ciphertext": base64.b64encode(self.ciphertext).decode("ascii"),
            "wrapped_data_key": base64.b64encode(self.wrapped_data_key).decode("ascii"),
            "nonce": base64.b64encode(self.nonce).decode("ascii"),
            "authentication_tag": base64.b64encode(self.authentication_tag).decode("ascii"),
            "key_version": self.key_version,
            "algorithm": self.algorithm,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class ResolutionResult:
    status: ResultStatus
    requested_entity: str
    records: list[NormalizedReview] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
    message: str = ""
