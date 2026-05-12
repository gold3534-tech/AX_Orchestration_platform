from __future__ import annotations

import json
import os
from typing import Any

from cryptography.fernet import Fernet, InvalidToken


class CredentialEncryptionNotConfiguredError(ValueError):
    pass


class CredentialEncryptionError(ValueError):
    pass


def _fernet() -> Fernet:
    key = os.getenv("CREDENTIAL_ENCRYPTION_KEY")
    if not key:
        raise CredentialEncryptionNotConfiguredError("Credential encryption is not configured.")
    try:
        return Fernet(key.encode("ascii"))
    except (TypeError, UnicodeEncodeError, ValueError):
        raise CredentialEncryptionNotConfiguredError("Credential encryption is not configured.")


def encrypt_secret_payload(secret_json: dict[str, Any]) -> dict[str, str]:
    payload = json.dumps(secret_json, separators=(",", ":")).encode("utf-8")
    token = _fernet().encrypt(payload).decode("ascii")
    return {"cipher": "fernet", "token": token, "key_version": "v1"}


def decrypt_secret_payload(encrypted_secret_json: dict[str, Any]) -> dict[str, Any]:
    try:
        if not isinstance(encrypted_secret_json, dict):
            raise CredentialEncryptionError
        if encrypted_secret_json.get("cipher") != "fernet":
            raise CredentialEncryptionError
        token = encrypted_secret_json.get("token")
        if not isinstance(token, str) or not token:
            raise CredentialEncryptionError
        payload = _fernet().decrypt(token.encode("ascii"))
        secret_json = json.loads(payload.decode("utf-8"))
        if not isinstance(secret_json, dict):
            raise CredentialEncryptionError
        return secret_json
    except CredentialEncryptionNotConfiguredError:
        raise
    except (CredentialEncryptionError, InvalidToken, UnicodeEncodeError, UnicodeDecodeError, json.JSONDecodeError):
        raise CredentialEncryptionError("Credential could not be decrypted.")
