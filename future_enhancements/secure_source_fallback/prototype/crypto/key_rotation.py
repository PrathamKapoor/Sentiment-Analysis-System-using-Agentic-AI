from cryptography.hazmat.primitives.asymmetric import rsa

from .envelope import _unwrap, _wrap
from ..models import EncryptedSecret


def rewrap_data_key(record: EncryptedSecret, old_private_key: rsa.RSAPrivateKey, new_public_key: rsa.RSAPublicKey, new_key_version: str) -> EncryptedSecret:
    """Rotation changes only the wrapped random data key, never plaintext/ciphertext."""
    data_key = _unwrap(record.wrapped_data_key, old_private_key)
    return EncryptedSecret(record.ciphertext, _wrap(data_key, new_public_key), record.nonce, record.authentication_tag, new_key_version, record.algorithm, record.created_at)
