from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastmcp.server.auth import OAuthProxy

from tramplin_mcp import auth
from tramplin_mcp.auth import TramplinTokenVerifier, build_auth
from tramplin_mcp.config import Settings

OAUTH_ENV = {
    "TRAMPLIN_API_URL": "http://api.test/api/v1/",
    "TRAMPLIN_OAUTH_BASE_URL": "http://app.test/api/v1/",
    "TRAMPLIN_MCP_PUBLIC_URL": "http://mcp.test/",
    "TRAMPLIN_OAUTH_CLIENT_SECRET": "  client-secret  ",
    "TRAMPLIN_MCP_JWT_SIGNING_KEY": "signing-key-at-least-32-bytes-long!!",
}


def make_settings(**env: str) -> Settings:
    return Settings(_env_file=None, **env)  # type: ignore[call-arg]


# --- Настройки ------------------------------------------------------------------


def test_settings_normalize_urls_and_secrets() -> None:
    settings = make_settings(**OAUTH_ENV, TRAMPLIN_API_TOKEN="  tok \n")

    assert settings.api_url == "http://api.test/api/v1"
    assert settings.oauth_base_url == "http://app.test/api/v1"
    assert settings.public_url == "http://mcp.test"
    assert settings.oauth_client_secret == "client-secret"
    assert settings.api_token == "tok"
    assert settings.oauth_configured


@pytest.mark.parametrize(
    "missing", ["TRAMPLIN_OAUTH_CLIENT_SECRET", "TRAMPLIN_MCP_JWT_SIGNING_KEY"]
)
def test_oauth_not_configured_without_secrets(missing: str) -> None:
    env = {key: value for key, value in OAUTH_ENV.items() if key != missing}

    assert not make_settings(**env).oauth_configured


# --- build_auth -----------------------------------------------------------------


def test_build_auth_disabled_without_oauth() -> None:
    assert build_auth(make_settings()) is None


def test_build_auth_proxies_tramplin_oauth() -> None:
    proxy = build_auth(make_settings(**OAUTH_ENV))

    assert isinstance(proxy, OAuthProxy)
    assert proxy._upstream_authorization_endpoint == "http://app.test/api/v1/oauth/authorize"
    assert proxy._upstream_token_endpoint == "http://api.test/api/v1/oauth/token"


# --- Проверка токена ------------------------------------------------------------


class Introspection:
    """Сеть verify_token: отдаёт заданный ответ или бросает заданную ошибку."""

    def __init__(self) -> None:
        self.result: httpx.Response | Exception = httpx.Response(200, json={"sub": 1})
        self.requests: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.fixture
def introspect(monkeypatch: pytest.MonkeyPatch) -> Introspection:
    fake = Introspection()
    original = httpx.AsyncClient

    def factory(**kwargs: Any) -> httpx.AsyncClient:
        return original(transport=httpx.MockTransport(fake.handle), **kwargs)

    monkeypatch.setattr(auth.httpx, "AsyncClient", factory)
    return fake


async def test_verify_token_returns_access_token(introspect: Introspection) -> None:
    introspect.result = httpx.Response(200, json={"sub": 42, "role": "teacher"})
    verifier = TramplinTokenVerifier(make_settings(**OAUTH_ENV))

    token = await verifier.verify_token("abc")

    assert token is not None
    assert token.token == "abc"
    assert token.subject == "42"
    assert token.client_id == "tramplin-fastmcp"
    assert token.scopes == ["authoring"]
    assert token.claims == {"sub": 42, "role": "teacher"}
    (request,) = introspect.requests
    assert str(request.url) == "http://api.test/api/v1/oauth/introspect"
    assert request.headers["authorization"] == "Bearer abc"


async def test_verify_token_rejects_inactive_token(introspect: Introspection) -> None:
    introspect.result = httpx.Response(401, json={"code": "invalid_token"})
    verifier = TramplinTokenVerifier(make_settings(**OAUTH_ENV))

    assert await verifier.verify_token("abc") is None


async def test_verify_token_treats_network_error_as_invalid(introspect: Introspection) -> None:
    introspect.result = httpx.ConnectError("down")
    verifier = TramplinTokenVerifier(make_settings(**OAUTH_ENV))

    assert await verifier.verify_token("abc") is None
