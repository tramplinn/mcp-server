from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, cast

from fastmcp import Context, FastMCP
from fastmcp.server.auth.providers.github import GitHubProvider
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
auth = (
    GitHubProvider(
        client_id=startup_settings.github_client_id,
        client_secret=startup_settings.github_client_secret,
        base_url=startup_settings.public_url,
        jwt_signing_key=startup_settings.jwt_signing_key,
        require_authorization_consent=True,
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
    settings = Settings.from_env()
    access_token = get_access_token()
    if access_token is None:
        if not settings.api_token:
            raise ValueError("TRAMPLIN_API_TOKEN is required for local stdio mode")
        return base.with_token(settings.api_token)
    provider_id = access_token.claims.get("sub")
    if not isinstance(provider_id, str) or not provider_id:
        raise ValueError("GitHub OAuth token has no subject")
    token = await base.exchange_mcp_identity("github", provider_id, settings.service_secret)
    return base.with_token(token)


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
