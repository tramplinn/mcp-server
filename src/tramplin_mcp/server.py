from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, cast

import httpx
from fastmcp import Context, FastMCP
from fastmcp.server.auth import AccessToken, OAuthProxy, TokenVerifier
from fastmcp.server.dependencies import get_access_token
from fastmcp.server.lifespan import lifespan
from starlette.requests import Request
from starlette.responses import JSONResponse

from tramplin_mcp.client import TramplinClient
from tramplin_mcp.config import Settings
from tramplin_mcp.models import ApplyResult, CoursePlan, CoursePlanPreview, CoursePlanValidation
from tramplin_mcp.planner import apply_plan, preview_plan, validate_plan


@lifespan
async def app_lifespan(_: FastMCP) -> AsyncIterator[dict[str, TramplinClient]]:
    settings = Settings.from_env()
    client = TramplinClient(settings.api_url, settings.api_token, settings.request_timeout)
    try:
        yield {"client": client}
    finally:
        await client.close()


startup_settings = Settings.from_env()


class TramplinTokenVerifier(TokenVerifier):
    def __init__(self, settings: Settings) -> None:
        super().__init__(required_scopes=["authoring"])
        self._api_url = settings.api_url
        self._timeout = settings.request_timeout

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            async with httpx.AsyncClient(base_url=self._api_url, timeout=self._timeout) as client:
                response = await client.get(
                    "/auth/mcp/introspect",
                    headers={"Authorization": f"Bearer {token}"},
                )
        except httpx.HTTPError:
            return None
        if not response.is_success:
            return None
        payload = response.json()
        return AccessToken(
            token=token,
            client_id=startup_settings.oauth_client_id,
            subject=str(payload["sub"]),
            scopes=["authoring"],
            claims=payload,
        )


auth = (
    OAuthProxy(
        upstream_authorization_endpoint=(f"{startup_settings.oauth_base_url}/auth/mcp/authorize"),
        upstream_token_endpoint=f"{startup_settings.api_url}/auth/mcp/token",
        upstream_revocation_endpoint=f"{startup_settings.api_url}/auth/mcp/revoke",
        upstream_client_id=startup_settings.oauth_client_id,
        upstream_client_secret=startup_settings.oauth_client_secret,
        token_verifier=TramplinTokenVerifier(startup_settings),
        base_url=startup_settings.public_url,
        jwt_signing_key=startup_settings.jwt_signing_key,
        valid_scopes=["authoring"],
        require_authorization_consent="external",
        token_endpoint_auth_method="client_secret_basic",  # noqa: S106
    )
    if startup_settings.oauth_configured
    else None
)


mcp = FastMCP(
    "tramplin-authoring",
    version="0.1.0",
    instructions=(
        "Use inspect_course before editing existing material. Use preview_course_plan before "
        "apply_course_plan. Plans only create or update drafts and never delete content. Never "
        "claim that content was published: this server has no publishing tool."
    ),
    lifespan=app_lifespan,
    auth=auth,
)


async def _client(ctx: Context) -> TramplinClient:
    base = cast(TramplinClient, ctx.lifespan_context["client"])
    access_token = get_access_token()
    if access_token is None:
        if not startup_settings.api_token:
            raise ValueError("TRAMPLIN_API_TOKEN is required for local stdio mode")
        return base.with_token(startup_settings.api_token)
    return base.with_token(access_token.token)


@mcp.tool
async def list_courses(ctx: Context) -> list[dict[str, Any]]:
    """List all courses visible to the authenticated teacher, including drafts."""
    return await (await _client(ctx)).list_courses()


@mcp.tool
async def inspect_course(slug: str, ctx: Context) -> dict[str, Any]:
    """Read the complete authoring tree for one course before proposing edits."""
    course = await (await _client(ctx)).get_course(slug)
    if course is None:
        return {"found": False, "slug": slug}
    return {"found": True, "course": course}


@mcp.tool
async def inspect_lesson(lesson_id: str, ctx: Context) -> dict[str, Any]:
    """Read one lesson including its Markdown source."""
    return await (await _client(ctx)).get_lesson(lesson_id)


@mcp.tool
async def preview_markdown(body_md: str, ctx: Context) -> dict[str, Any]:
    """Render lesson Markdown and extract interview cards without saving anything."""
    return await (await _client(ctx)).preview_markdown(body_md)


@mcp.tool
async def preview_course_plan(plan: CoursePlan, ctx: Context) -> CoursePlanPreview:
    """Compare a complete desired course outline with Tramplin without changing data."""
    return await preview_plan(await _client(ctx), plan)


@mcp.tool
async def validate_course_plan(plan: CoursePlan, ctx: Context) -> CoursePlanValidation:
    """Validate Markdown, lesson links, question answers, and publish-readiness without writes."""
    return await validate_plan(await _client(ctx), plan)


@mcp.tool
async def apply_course_plan(plan: CoursePlan, ctx: Context) -> ApplyResult:
    """Idempotently create/update a draft course, modules, and lessons; never delete or publish."""
    return await apply_plan(await _client(ctx), plan)


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


def main() -> None:
    settings = Settings.from_env()
    if settings.transport == "stdio":
        mcp.run(transport="stdio")
        return
    if settings.transport != "http":
        raise ValueError("TRAMPLIN_MCP_TRANSPORT must be stdio or http")
    if auth is None:
        raise ValueError("HTTP transport requires complete TRAMPLIN_MCP OAuth configuration")
    mcp.run(
        transport="http",
        host=settings.host,
        port=settings.port,
        stateless_http=True,
    )


if __name__ == "__main__":
    main()
