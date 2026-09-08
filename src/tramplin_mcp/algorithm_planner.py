from __future__ import annotations

from tramplin_mcp.algorithm_diff import changes_for
from tramplin_mcp.client import TramplinClient
from tramplin_mcp.models import (
    AlgorithmPlan,
    AlgorithmPlanApplyResult,
    AlgorithmPlanPreview,
    AlgorithmPlanValidation,
    ValidationIssue,
)

_WARNING = (
    "Additive-only: тест-кейсы/шаблоны существующей задачи вне плана сохраняются; "
    "apply_algorithm_plan не запускает validate_template."
)


async def validate_plan(client: TramplinClient, plan: AlgorithmPlan) -> AlgorithmPlanValidation:
    issues: list[ValidationIssue] = []
    for problem in plan.problems:
        if problem.provider == "internal" and not problem.statement_md.strip():
            issues.append(
                ValidationIssue(severity="warning", path=problem.slug, message="Пустое условие")
            )
        if problem.provider == "external" and not problem.external_url:
            issues.append(
                ValidationIssue(
                    severity="error",
                    path=problem.slug,
                    message="external_url обязателен для внешней задачи",
                )
            )
        if problem.external_url and not problem.external_url.startswith("https://"):
            issues.append(
                ValidationIssue(
                    severity="error", path=problem.slug, message="external_url должен быть HTTPS"
                )
            )
        if not problem.test_cases:
            issues.append(
                ValidationIssue(severity="warning", path=problem.slug, message="Нет тест-кейсов")
            )
        elif not any(case.is_sample for case in problem.test_cases):
            issues.append(
                ValidationIssue(
                    severity="warning", path=problem.slug, message="Нет ни одного sample-теста"
                )
            )
    return AlgorithmPlanValidation(
        valid=not any(issue.severity == "error" for issue in issues), issues=issues
    )


async def preview_plan(client: TramplinClient, plan: AlgorithmPlan) -> AlgorithmPlanPreview:
    changes = await changes_for(client, plan)
    return AlgorithmPlanPreview(
        changes=changes,
        creates=sum(change.action == "create" for change in changes),
        updates=sum(change.action == "update" for change in changes),
        unchanged=sum(change.action == "unchanged" for change in changes),
        warnings=[_WARNING] if plan.problems else [],
    )


async def apply_plan(client: TramplinClient, plan: AlgorithmPlan) -> AlgorithmPlanApplyResult:
    validation = await validate_plan(client, plan)
    if not validation.valid:
        messages = "; ".join(f"{issue.path}: {issue.message}" for issue in validation.issues)
        raise ValueError(f"Algorithm plan is invalid: {messages}")

    changes = await changes_for(client, plan)
    await client.apply_algorithm_plan(plan.model_dump(mode="json"))
    return AlgorithmPlanApplyResult(
        completed=True,
        changes=changes,
        warnings=[_WARNING] if plan.problems else [],
    )
