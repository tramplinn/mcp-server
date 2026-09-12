from __future__ import annotations

from typing import Any

from tramplin_mcp.client import TramplinClient
from tramplin_mcp.diff import changes_for
from tramplin_mcp.models import (
    ApplyResult,
    CoursePlan,
    CoursePlanPreview,
    CoursePlanValidation,
    ModulePlan,
    PracticeSetPlan,
    ValidationIssue,
)


async def validate_plan(client: TramplinClient, plan: CoursePlan) -> CoursePlanValidation:
    issues: list[ValidationIssue] = []
    for module in plan.modules:
        lesson_slugs = {lesson.slug for lesson in module.lessons}
        for lesson in module.lessons:
            path = f"{plan.slug}/{module.slug}/{lesson.slug}"
            if not lesson.body_md.strip():
                issues.append(ValidationIssue(severity="warning", path=path, message="Пустой урок"))
            else:
                await client.preview_markdown(lesson.body_md)
        for quiz in module.quizzes:
            path = f"{plan.slug}/{module.slug}/{quiz.slug}"
            if quiz.lesson_slug and quiz.lesson_slug not in lesson_slugs:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        path=path,
                        message="lesson_slug должен ссылаться на урок из того же модуля",
                    )
                )
            if not quiz.questions:
                issues.append(
                    ValidationIssue(severity="warning", path=path, message="Тест без вопросов")
                )
        for practice in module.practice_sets:
            path = f"{plan.slug}/{module.slug}/practice/{practice.title}"
            if not practice.problem_slugs:
                issues.append(
                    ValidationIssue(
                        severity="warning", path=path, message="Набор практики без задач"
                    )
                )
            for slug in practice.problem_slugs:
                if await client.get_problem_by_slug(slug) is None:
                    issues.append(
                        ValidationIssue(
                            severity="error",
                            path=path,
                            message=f"problem_slugs ссылается на несуществующую задачу '{slug}'",
                        )
                    )
    return CoursePlanValidation(
        valid=not any(issue.severity == "error" for issue in issues), issues=issues
    )


async def preview_plan(client: TramplinClient, plan: CoursePlan) -> CoursePlanPreview:
    current = await client.get_course(plan.slug)
    changes = await changes_for(client, plan, current)
    return CoursePlanPreview(
        course_slug=plan.slug,
        changes=changes,
        creates=sum(change.action == "create" for change in changes),
        updates=sum(change.action == "update" for change in changes),
        unchanged=sum(change.action == "unchanged" for change in changes),
        warnings=_warnings(current),
    )


async def apply_plan(client: TramplinClient, plan: CoursePlan) -> ApplyResult:
    validation = await validate_plan(client, plan)
    if not validation.valid:
        messages = "; ".join(f"{issue.path}: {issue.message}" for issue in validation.issues)
        raise ValueError(f"Course plan is invalid: {messages}")

    current = await client.get_course(plan.slug)
    changes = await changes_for(client, plan, current)
    await client.apply_course_plan(plan.model_dump(mode="json"))
    return ApplyResult(
        course_slug=plan.slug,
        completed=True,
        changes=changes,
        warnings=_warnings(current),
    )


def _warnings(current: dict[str, Any] | None) -> list[str]:
    return [] if current is None else ["Additive-only: сущности вне плана сохраняются в конце."]


async def _course_plan_for_practice_set(
    client: TramplinClient, course_slug: str, module_slug: str, practice_set: PracticeSetPlan
) -> CoursePlan:
    course = await client.get_course(course_slug)
    if course is None:
        raise ValueError(f"Course '{course_slug}' not found")
    module = next((m for m in course.get("modules", []) if m["slug"] == module_slug), None)
    if module is None:
        raise ValueError(f"Module '{module_slug}' not found in course '{course_slug}'")
    return CoursePlan(
        title=course["title"],
        slug=course_slug,
        summary=course.get("summary"),
        color=course.get("color"),
        est_hours=course.get("est_hours"),
        modules=[
            ModulePlan(
                title=module["title"],
                slug=module_slug,
                summary=module.get("summary"),
                practice_sets=[practice_set],
            )
        ],
    )


async def preview_practice_set(
    client: TramplinClient, course_slug: str, module_slug: str, practice_set: PracticeSetPlan
) -> CoursePlanPreview:
    plan = await _course_plan_for_practice_set(client, course_slug, module_slug, practice_set)
    return await preview_plan(client, plan)


async def validate_practice_set(
    client: TramplinClient, course_slug: str, module_slug: str, practice_set: PracticeSetPlan
) -> CoursePlanValidation:
    plan = await _course_plan_for_practice_set(client, course_slug, module_slug, practice_set)
    return await validate_plan(client, plan)


async def apply_practice_set(
    client: TramplinClient, course_slug: str, module_slug: str, practice_set: PracticeSetPlan
) -> ApplyResult:
    plan = await _course_plan_for_practice_set(client, course_slug, module_slug, practice_set)
    return await apply_plan(client, plan)
