from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, cast

from fastmcp import Context, FastMCP
from fastmcp.server.dependencies import get_access_token
from fastmcp.server.lifespan import lifespan
from starlette.requests import Request
from starlette.responses import JSONResponse

from tramplin_mcp.algorithm_planner import (
    apply_plan as apply_algorithm_plan_impl,
)
from tramplin_mcp.algorithm_planner import (
    preview_plan as preview_algorithm_plan_impl,
)
from tramplin_mcp.algorithm_planner import (
    validate_plan as validate_algorithm_plan_impl,
)
from tramplin_mcp.auth import build_auth
from tramplin_mcp.client import TramplinClient
from tramplin_mcp.config import Settings
from tramplin_mcp.models import (
    AlgorithmPlan,
    AlgorithmPlanApplyResult,
    AlgorithmPlanPreview,
    AlgorithmPlanValidation,
    ApplyResult,
    CoursePlan,
    CoursePlanPreview,
    CoursePlanValidation,
    PracticeSetPlan,
)
from tramplin_mcp.planner import (
    apply_plan,
    apply_practice_set,
    preview_plan,
    preview_practice_set,
    validate_plan,
    validate_practice_set,
)

settings = Settings()
auth = build_auth(settings)


@lifespan
async def app_lifespan(_: FastMCP) -> AsyncIterator[dict[str, TramplinClient]]:
    client = TramplinClient(settings.api_url, settings.api_token, settings.request_timeout)
    try:
        yield {"client": client}
    finally:
        await client.close()


mcp = FastMCP(
    "tramplin-authoring",
    version="0.1.0",
    instructions=(
        "Use inspect_course before editing existing material. Use preview_course_plan before "
        "apply_course_plan. Plans only create or update drafts and never delete content. Never "
        "claim that content was published: this server has no publishing tool. Tracks group "
        "existing courses: use inspect_track before create_track/attach_course_to_track, and "
        "attach_course_to_track (not a course plan) to add a course to a track. Problems are a "
        "flat bank: use preview_algorithm_plan before apply_algorithm_plan; it never runs "
        "validate_template, so a plan applying cleanly does not mean solutions pass their tests. "
        "A module's practice_sets create or update practice sets in that module, referencing bank "
        "problems by slug; a practice set has no slug of its own, so it is matched by title — "
        "keep titles stable across applies to update the same set instead of creating a new one. "
        "To add or update a single practice set in an existing course/module without restating the "
        "rest of the course, use preview_practice_set_plan/apply_practice_set_plan instead of a "
        "full course plan; the course and module must already exist."
    ),
    lifespan=app_lifespan,
    auth=auth,
)


async def _client(ctx: Context) -> TramplinClient:
    base = cast(TramplinClient, ctx.lifespan_context["client"])
    access_token = get_access_token()
    if access_token is None:
        if not settings.api_token:
            raise ValueError("TRAMPLIN_API_TOKEN is required for local stdio mode")
        return base.with_token(settings.api_token)
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
    return {"found": True, "course": cast(dict[str, Any], _omit_body_html(course))}


@mcp.tool
async def inspect_lesson(lesson_id: str, ctx: Context) -> dict[str, Any]:
    """Read one lesson including its Markdown source."""
    lesson = await (await _client(ctx)).get_lesson(lesson_id)
    return cast(dict[str, Any], _omit_body_html(lesson))


def _omit_body_html(value: object) -> object:
    if isinstance(value, dict):
        return {key: _omit_body_html(item) for key, item in value.items() if key != "body_html"}
    if isinstance(value, list):
        return [_omit_body_html(item) for item in value]
    return value


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


@mcp.tool
async def preview_practice_set_plan(
    course_slug: str, module_slug: str, practice_set: PracticeSetPlan, ctx: Context
) -> CoursePlanPreview:
    """Compare a desired practice set for one module with Tramplin without changing data."""
    return await preview_practice_set(await _client(ctx), course_slug, module_slug, practice_set)


@mcp.tool
async def validate_practice_set_plan(
    course_slug: str, module_slug: str, practice_set: PracticeSetPlan, ctx: Context
) -> CoursePlanValidation:
    """Validate a practice set's problem slugs without writes."""
    return await validate_practice_set(await _client(ctx), course_slug, module_slug, practice_set)


@mcp.tool
async def apply_practice_set_plan(
    course_slug: str, module_slug: str, practice_set: PracticeSetPlan, ctx: Context
) -> ApplyResult:
    """Idempotently create/update one draft practice set in an existing course module.

    Matches by title; leaves the rest of the course/module untouched. The course and module
    must already exist (create them with apply_course_plan first).
    """
    return await apply_practice_set(await _client(ctx), course_slug, module_slug, practice_set)


@mcp.tool
async def list_tracks(ctx: Context) -> list[dict[str, Any]]:
    """List all tracks visible to the authenticated teacher, including drafts."""
    return await (await _client(ctx)).list_tracks()


@mcp.tool
async def inspect_track(slug: str, ctx: Context) -> dict[str, Any]:
    """Read one track, including its attached courses, before proposing changes."""
    track = await (await _client(ctx)).get_track(slug)
    if track is None:
        return {"found": False, "slug": slug}
    return {"found": True, "track": track}


@mcp.tool
async def create_track(
    title: str,
    slug: str,
    ctx: Context,
    description: str | None = None,
    color: str | None = None,
) -> dict[str, Any]:
    """Create a draft track (without courses). Use attach_course_to_track to add courses to it."""
    payload = {"title": title, "slug": slug, "description": description, "color": color}
    return await (await _client(ctx)).create_track(payload)


@mcp.tool
async def attach_course_to_track(track_id: str, course_id: str, ctx: Context) -> dict[str, bool]:
    """Attach an existing course to an existing track. Idempotent; never removes courses."""
    await (await _client(ctx)).attach_course_to_track(track_id, course_id)
    return {"attached": True}


@mcp.tool
async def reorder_track_courses(
    track_id: str, course_ids: list[str], ctx: Context
) -> dict[str, bool]:
    """Set the display order of a track's courses; the list must include every attached course."""
    await (await _client(ctx)).reorder_track_courses(track_id, course_ids)
    return {"reordered": True}


@mcp.tool
async def list_problems(ctx: Context) -> list[dict[str, Any]]:
    """List all algorithmic problems visible to the authenticated teacher, including drafts."""
    return await (await _client(ctx)).list_problems()


@mcp.tool
async def inspect_problem(slug: str, ctx: Context) -> dict[str, Any]:
    """Read one problem, including its test cases and language templates, before editing."""
    problem = await (await _client(ctx)).get_problem_by_slug(slug)
    if problem is None:
        return {"found": False, "slug": slug}
    return {"found": True, "problem": problem}


@mcp.tool
async def preview_algorithm_plan(plan: AlgorithmPlan, ctx: Context) -> AlgorithmPlanPreview:
    """Compare a desired bank of problems with Tramplin without changing data."""
    return await preview_algorithm_plan_impl(await _client(ctx), plan)


@mcp.tool
async def validate_algorithm_plan(plan: AlgorithmPlan, ctx: Context) -> AlgorithmPlanValidation:
    """Validate provider/URL consistency and test-case coverage without writes."""
    return await validate_algorithm_plan_impl(await _client(ctx), plan)


@mcp.tool
async def apply_algorithm_plan(plan: AlgorithmPlan, ctx: Context) -> AlgorithmPlanApplyResult:
    """Idempotently create/update draft problems, test cases, and templates; never deletes."""
    return await apply_algorithm_plan_impl(await _client(ctx), plan)


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


def main() -> None:
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
