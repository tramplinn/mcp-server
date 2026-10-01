from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, cast

from fastmcp import Context, FastMCP
from fastmcp.server.dependencies import get_access_token
from fastmcp.server.lifespan import lifespan
from mcp.types import ToolAnnotations
from starlette.requests import Request
from starlette.responses import JSONResponse

from tramplin_mcp.auth import build_auth
from tramplin_mcp.client import TramplinClient
from tramplin_mcp.config import Settings
from tramplin_mcp.models import (
    AlgorithmPlan,
    AlgorithmPlanReport,
    CoursePlan,
    CoursePlanReport,
    Index,
    McpModel,
    PracticeSetPlan,
    PracticeSetPlanReport,
    TrackPlan,
    TrackPlanReport,
)

settings = Settings()
auth = build_auth(settings)

INSTRUCTIONS = """\
Tramplin authoring: courses (modules with lessons, quizzes and practice sets), a flat bank of
algorithm problems, and tracks that group courses. All logic lives in the Tramplin backend;
this server only forwards calls.

Workflow for every change:
1. Look first: list_courses / list_tracks / list_problems, then inspect_course /
   inspect_track / inspect_problem for anything you are going to change.
2. preview_*_plan: runs the real apply code and rolls it back. It returns the exact diff
   (`changes`) plus `issues`. Fix every issue with severity 'error' (look at `code` and
   `path`) and preview again; warnings do not block.
3. Show the user what will change, including every entry of `warnings`, then call the
   matching apply_*_plan with the same plan. Apply re-validates; if the plan has errors it
   fails with code invalid_plan, and the failure details list the same issues.

Plan semantics:
- Plans are idempotent and additive-only: nothing is ever deleted, and entities missing from
  a plan are kept. Re-applying the same plan changes nothing.
- Matching keys: course/module/lesson/quiz/problem/track by slug, practice set by title (keep
  titles stable), question and test case by position, template by language.
- Course plans save every course/module/lesson/quiz they mention as a draft, which unpublishes
  published ones. Say so to the user before applying when preview warns about it. To add or
  change a single practice set in an existing module, use apply_practice_set_plan: it does not
  touch statuses or the order of anything else.
- This server cannot publish. Never claim content is published; the author publishes it in
  the Tramplin UI.
- After apply, `changes[].entity_id` holds real ids. For example, inspect_lesson takes a lesson
  id from there or from inspect_course.
- Problems: apply_algorithm_plan does not run reference solutions unless
  validate_templates=true. Without it, a clean apply says nothing about solutions passing tests.
"""

READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
PREVIEW = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)
APPLY = ToolAnnotations(
    readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False
)


@lifespan
async def app_lifespan(_: FastMCP) -> AsyncIterator[dict[str, TramplinClient]]:
    client = TramplinClient(settings.api_url, settings.api_token, settings.request_timeout)
    try:
        yield {"client": client}
    finally:
        await client.close()


mcp = FastMCP(
    "tramplin-authoring",
    version="0.2.0",
    instructions=INSTRUCTIONS,
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


def _dump(model: McpModel) -> dict[str, Any]:
    return model.model_dump(mode="json")


def _omit_body_html(value: object) -> object:
    if isinstance(value, dict):
        return {key: _omit_body_html(item) for key, item in value.items() if key != "body_html"}
    if isinstance(value, list):
        return [_omit_body_html(item) for item in value]
    return value


# --- Courses ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def list_courses(ctx: Context) -> Index:
    """List every course including drafts (id, slug, title, status). Not paginated."""
    return Index.model_validate(await (await _client(ctx)).index_courses())


@mcp.tool(annotations=READ_ONLY)
async def inspect_course(slug: str, ctx: Context) -> dict[str, Any]:
    """Read a course's full authoring tree: modules and their ordered items (lessons, quizzes,
    practice sets) with ids. Lesson bodies are omitted, so use inspect_lesson to read one."""
    course = await (await _client(ctx)).get_course(slug)
    if course is None:
        return {"found": False, "slug": slug}
    return {"found": True, "course": _omit_body_html(course)}


@mcp.tool(annotations=READ_ONLY)
async def inspect_lesson(lesson_id: str, ctx: Context) -> dict[str, Any]:
    """Read one lesson including its Markdown source (body_md). Take lesson_id from
    inspect_course or from changes[].entity_id of an applied course plan."""
    lesson = await (await _client(ctx)).get_lesson(lesson_id)
    return cast(dict[str, Any], _omit_body_html(lesson))


@mcp.tool(annotations=READ_ONLY)
async def preview_markdown(body_md: str, ctx: Context) -> dict[str, Any]:
    """Render lesson Markdown exactly as students will see it and extract interview cards.
    Saves nothing. Use it to check tricky Markdown before putting it into a plan."""
    return await (await _client(ctx)).preview_markdown(body_md)


@mcp.tool(annotations=PREVIEW)
async def preview_course_plan(plan: CoursePlan, ctx: Context) -> CoursePlanReport:
    """Dry-run a course plan. Returns the exact diff the apply would make and validation
    issues (unknown problem slugs, broken Markdown, invalid quiz answers, …). Writes nothing."""
    result = await (await _client(ctx)).course_plan("preview", _dump(plan))
    return CoursePlanReport.model_validate(result)


@mcp.tool(annotations=APPLY)
async def apply_course_plan(plan: CoursePlan, ctx: Context) -> CoursePlanReport:
    """Create or update a course (modules, lessons, quizzes, practice sets) in one transaction.
    Additive and idempotent. Everything the plan mentions is saved as a draft, which
    unpublishes published entities. Preview first. Rejected as a whole (invalid_plan) if the
    plan has errors."""
    result = await (await _client(ctx)).course_plan("apply", _dump(plan))
    return CoursePlanReport.model_validate(result)


def _practice_set_payload(
    course_slug: str, module_slug: str, practice_set: PracticeSetPlan
) -> dict[str, Any]:
    return {
        "course_slug": course_slug,
        "module_slug": module_slug,
        "practice_set": _dump(practice_set),
    }


@mcp.tool(annotations=PREVIEW)
async def preview_practice_set_plan(
    course_slug: str, module_slug: str, practice_set: PracticeSetPlan, ctx: Context
) -> PracticeSetPlanReport:
    """Dry-run one practice set in an existing course module. Writes nothing."""
    payload = _practice_set_payload(course_slug, module_slug, practice_set)
    result = await (await _client(ctx)).practice_set_plan("preview", payload)
    return PracticeSetPlanReport.model_validate(result)


@mcp.tool(annotations=APPLY)
async def apply_practice_set_plan(
    course_slug: str, module_slug: str, practice_set: PracticeSetPlan, ctx: Context
) -> PracticeSetPlanReport:
    """Create or update one practice set (matched by title) in an existing course module
    without restating the course. A new set is appended to the end of the module. Other items,
    their order and statuses are untouched. The course and module must already exist."""
    payload = _practice_set_payload(course_slug, module_slug, practice_set)
    result = await (await _client(ctx)).practice_set_plan("apply", payload)
    return PracticeSetPlanReport.model_validate(result)


# --- Tracks ----------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def list_tracks(ctx: Context) -> Index:
    """List every track including drafts (id, slug, title, status). Not paginated."""
    return Index.model_validate(await (await _client(ctx)).index_tracks())


@mcp.tool(annotations=READ_ONLY)
async def inspect_track(slug: str, ctx: Context) -> dict[str, Any]:
    """Read one track with its courses in display order."""
    track = await (await _client(ctx)).get_track(slug)
    if track is None:
        return {"found": False, "slug": slug}
    return {"found": True, "track": track}


@mcp.tool(annotations=PREVIEW)
async def preview_track_plan(plan: TrackPlan, ctx: Context) -> TrackPlanReport:
    """Dry-run a track plan: the track itself, which courses get attached and whether the
    course order changes. Writes nothing."""
    result = await (await _client(ctx)).track_plan("preview", _dump(plan))
    return TrackPlanReport.model_validate(result)


@mcp.tool(annotations=APPLY)
async def apply_track_plan(plan: TrackPlan, ctx: Context) -> TrackPlanReport:
    """Create or update a track and attach/order its courses in one transaction. Additive
    and idempotent: no course is detached, and the track's status is never changed (a new
    track starts as a draft)."""
    result = await (await _client(ctx)).track_plan("apply", _dump(plan))
    return TrackPlanReport.model_validate(result)


# --- Algorithm problems ----------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def list_problems(ctx: Context) -> Index:
    """List every bank problem including drafts (id, slug, title, status, difficulty)."""
    return Index.model_validate(await (await _client(ctx)).index_problems())


@mcp.tool(annotations=READ_ONLY)
async def inspect_problem(slug: str, ctx: Context) -> dict[str, Any]:
    """Read one problem with its test cases and language templates."""
    problem = await (await _client(ctx)).get_problem_by_slug(slug)
    if problem is None:
        return {"found": False, "slug": slug}
    return {"found": True, "problem": problem}


@mcp.tool(annotations=PREVIEW)
async def preview_algorithm_plan(plan: AlgorithmPlan, ctx: Context) -> AlgorithmPlanReport:
    """Dry-run a problem bank plan: exact diff plus issues (duplicate slugs, test case
    positions, missing external_url, missing reference solutions, …). Writes nothing."""
    result = await (await _client(ctx)).algorithm_plan("preview", _dump(plan))
    return AlgorithmPlanReport.model_validate(result)


@mcp.tool(annotations=APPLY)
async def apply_algorithm_plan(
    plan: AlgorithmPlan, ctx: Context, validate_templates: bool = False
) -> AlgorithmPlanReport:
    """Create or update draft problems, test cases and templates in one transaction.
    Additive and idempotent. With validate_templates=true, after saving it runs every
    template's solution_code against the test cases and reports results in
    template_validations. A failed validation does not roll the plan back."""
    result = await (await _client(ctx)).algorithm_plan(
        "apply", _dump(plan), validate_templates=validate_templates
    )
    return AlgorithmPlanReport.model_validate(result)


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
