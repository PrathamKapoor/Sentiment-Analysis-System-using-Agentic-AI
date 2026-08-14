import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..errors import CryptoError
from ..models import EncryptedSecret


def generate_rsa_keypair() -> tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
    private = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    return private, private.public_key()


def _aad(credential_id: str, source_id: str) -> bytes:
    """Bind ciphertext to its credential and source, stable across key rewrap."""
    return f"{credential_id}|{source_id}".encode("utf-8")


def _wrap(data_key: bytes, public_key: rsa.RSAPublicKey) -> bytes:
    return public_key.encrypt(data_key, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))


def _unwrap(wrapped_key: bytes, private_key: rsa.RSAPrivateKey) -> bytes:
    return private_key.decrypt(wrapped_key, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))


def encrypt_secret(secret: str, public_key: rsa.RSAPublicKey, *, credential_id: str, source_id: str, key_version: str) -> EncryptedSecret:
    if not secret:
        raise CryptoError("A non-empty credential is required.")
    data_key, nonce = os.urandom(32), os.urandom(12)
    payload = AESGCM(data_key).encrypt(nonce, secret.encode("utf-8"), _aad(credential_id, source_id))
    return EncryptedSecret(payload[:-16], _wrap(data_key, public_key), nonce, payload[-16:], key_version)


def decrypt_secret(record: EncryptedSecret, private_key: rsa.RSAPrivateKey, *, credential_id: str, source_id: str) -> str:
    try:
        data_key = _unwrap(record.wrapped_data_key, private_key)
        plaintext = AESGCM(data_key).decrypt(record.nonce, record.ciphertext + record.authentication_tag, _aad(credential_id, source_id))
        return plaintext.decode("utf-8")
    except (ValueError, InvalidTag) as exc:
        raise CryptoError("Encrypted credential authentication or key unwrap failed.") from exc
