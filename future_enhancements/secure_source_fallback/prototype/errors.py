class PrototypeError(Exception):
    """Base class with safe, non-secret public messages only."""


class RecoverableSourceError(PrototypeError):
    pass


class SourceUnavailableError(RecoverableSourceError):
    pass


class RateLimitError(RecoverableSourceError):
    pass


class CredentialRequiredError(RecoverableSourceError):
    pass


class PolicyBlockedError(RecoverableSourceError):
    pass


class ResolverTimeoutError(PrototypeError):
    pass


class InvalidSourceError(PrototypeError):
    pass


class CryptoError(PrototypeError):
    pass
