from __future__ import annotations

from typing import Any

from tramplin_mcp.client import TramplinClient
from tramplin_mcp.diff import changes_for
from tramplin_mcp.models import (
    ApplyResult,
    CoursePlan,
    CoursePlanPreview,
    CoursePlanValidation,
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
