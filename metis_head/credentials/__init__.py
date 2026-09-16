"""Credential connection metadata and secret-store boundary."""

from .store import ConnectionRecord, CredentialStore, SecretStoreUnavailable

__all__ = ["ConnectionRecord", "CredentialStore", "SecretStoreUnavailable"]
