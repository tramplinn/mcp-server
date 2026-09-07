from __future__ import annotations

from typing import Annotated

from pydantic import BeforeValidator, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _strip(value: object) -> object:
    return value.strip() if isinstance(value, str) else value


def _strip_trailing_slash(value: object) -> object:
    return value.rstrip("/") if isinstance(value, str) else value


Stripped = Annotated[str, BeforeValidator(_strip)]
UrlNoTrailingSlash = Annotated[str, BeforeValidator(_strip_trailing_slash)]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    api_url: UrlNoTrailingSlash = Field(
        default="http://localhost:8000/api/v1", validation_alias="TRAMPLIN_API_URL"
    )
    api_token: Stripped = Field(default="", validation_alias="TRAMPLIN_API_TOKEN")
    request_timeout: float = Field(default=30.0, validation_alias="TRAMPLIN_API_TIMEOUT")
    transport: str = Field(default="http", validation_alias="TRAMPLIN_MCP_TRANSPORT")
    host: str = Field(default="127.0.0.1", validation_alias="TRAMPLIN_MCP_HOST")
    port: int = Field(default=8001, validation_alias="TRAMPLIN_MCP_PORT")
    public_url: UrlNoTrailingSlash = Field(
        default="http://localhost:8001", validation_alias="TRAMPLIN_MCP_PUBLIC_URL"
    )
    oauth_base_url: UrlNoTrailingSlash = Field(
        default="http://localhost:8000/api/v1", validation_alias="TRAMPLIN_OAUTH_BASE_URL"
    )
    oauth_client_id: Stripped = Field(
        default="tramplin-fastmcp", validation_alias="TRAMPLIN_OAUTH_CLIENT_ID"
    )
    oauth_client_secret: Stripped = Field(
        default="", validation_alias="TRAMPLIN_OAUTH_CLIENT_SECRET"
    )
    jwt_signing_key: Stripped = Field(default="", validation_alias="TRAMPLIN_MCP_JWT_SIGNING_KEY")

    @property
    def oauth_configured(self) -> bool:
        return bool(
            self.oauth_base_url
            and self.oauth_client_id
            and self.oauth_client_secret
            and self.jwt_signing_key
        )
