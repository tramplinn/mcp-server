from __future__ import annotations

import httpx
from cryptography.fernet import Fernet
from fastmcp.server.auth import AccessToken, OAuthProxy, TokenVerifier
from key_value.aio.stores.postgresql import PostgreSQLStore
from key_value.aio.wrappers.encryption import FernetEncryptionWrapper

from tramplin_mcp.config import Settings


class TramplinTokenVerifier(TokenVerifier):
    def __init__(self, settings: Settings) -> None:
        super().__init__(required_scopes=["authoring"])
        self._api_url = settings.api_url
        self._timeout = settings.request_timeout
        self._client_id = settings.oauth_client_id

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            async with httpx.AsyncClient(base_url=self._api_url, timeout=self._timeout) as client:
                response = await client.get(
                    "/oauth/introspect",
                    headers={"Authorization": f"Bearer {token}"},
                )
        except httpx.HTTPError:
            return None
        if not response.is_success:
            return None
        payload = response.json()
        return AccessToken(
            token=token,
            client_id=self._client_id,
            subject=str(payload["sub"]),
            scopes=["authoring"],
            claims=payload,
        )


def build_storage(settings: Settings) -> PostgreSQLStore | None:
    if not settings.oauth_configured:
        return None
    if (
        not settings.oauth_database_url.get_secret_value()
        or not settings.storage_encryption_key.get_secret_value()
    ):
        raise ValueError("OAuth requires PostgreSQL URL and a storage encryption key")
    # Validate before opening any database connections.
    Fernet(settings.storage_encryption_key.get_secret_value().encode())
    return PostgreSQLStore(url=settings.oauth_database_url.get_secret_value())


def build_auth(settings: Settings, storage: PostgreSQLStore | None = None) -> OAuthProxy | None:
    if not settings.oauth_configured:
        return None
    store = storage if storage is not None else build_storage(settings)
    if store is None:
        raise ValueError("OAuth storage is not configured")
    return OAuthProxy(
        upstream_authorization_endpoint=f"{settings.oauth_base_url}/oauth/authorize",
        upstream_token_endpoint=f"{settings.api_url}/oauth/token",
        upstream_revocation_endpoint=f"{settings.api_url}/oauth/revoke",
        upstream_client_id=settings.oauth_client_id,
        upstream_client_secret=settings.oauth_client_secret,
        token_verifier=TramplinTokenVerifier(settings),
        base_url=settings.public_url,
        jwt_signing_key=settings.jwt_signing_key,
        client_storage=FernetEncryptionWrapper(
            key_value=store,
            fernet=Fernet(settings.storage_encryption_key.get_secret_value().encode()),
        ),
        valid_scopes=["authoring"],
        require_authorization_consent="external",
        token_endpoint_auth_method="client_secret_basic",  # noqa: S106
    )
