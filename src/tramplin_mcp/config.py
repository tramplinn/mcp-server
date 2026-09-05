from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    api_url: str
    api_token: str
    request_timeout: float
    transport: str
    host: str
    port: int
    public_url: str
    github_client_id: str
    github_client_secret: str
    jwt_signing_key: str
    service_secret: str

    @classmethod
    def from_env(cls) -> Settings:
        api_url = os.getenv("TRAMPLIN_API_URL", "http://localhost:8000/api/v1").rstrip("/")
        token = os.getenv("TRAMPLIN_API_TOKEN", "").strip()
        return cls(
            api_url=api_url,
            api_token=token,
            request_timeout=float(os.getenv("TRAMPLIN_API_TIMEOUT", "30")),
            transport=os.getenv("TRAMPLIN_MCP_TRANSPORT", "http"),
            host=os.getenv("TRAMPLIN_MCP_HOST", "127.0.0.1"),
            port=int(os.getenv("TRAMPLIN_MCP_PORT", "8001")),
            public_url=os.getenv("TRAMPLIN_MCP_PUBLIC_URL", "http://localhost:8001").rstrip("/"),
            github_client_id=os.getenv("TRAMPLIN_MCP_GITHUB_CLIENT_ID", "").strip(),
            github_client_secret=os.getenv("TRAMPLIN_MCP_GITHUB_CLIENT_SECRET", "").strip(),
            jwt_signing_key=os.getenv("TRAMPLIN_MCP_JWT_SIGNING_KEY", "").strip(),
            service_secret=os.getenv("TRAMPLIN_MCP_SERVICE_SECRET", "").strip(),
        )

    @property
    def oauth_configured(self) -> bool:
        return bool(
            self.github_client_id
            and self.github_client_secret
            and self.jwt_signing_key
            and self.service_secret
        )
