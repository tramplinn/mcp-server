"""Computes the create/update/unchanged diff between an AlgorithmPlan and Tramplin's state."""

from __future__ import annotations

from typing import Any

from tramplin_mcp.client import TramplinClient
from tramplin_mcp.diff import _diff, _plain
from tramplin_mcp.models import AlgorithmPlan, Change, ProblemPlan

PROBLEM_FIELDS = (
    "provider",
    "external_key",
    "external_url",
    "title",
    "statement_md",
    "difficulty",
    "time_limit_ms",
    "memory_limit_kb",
)
CASE_FIELDS = ("input", "expected_output", "is_sample", "weight")
TEMPLATE_FIELDS = ("starter_code", "solution_code")


async def changes_for(client: TramplinClient, plan: AlgorithmPlan) -> list[Change]:
    changes: list[Change] = []
    for problem_plan in plan.problems:
        current = await client.get_problem_by_slug(problem_plan.slug)
        if current is None:
            changes.extend(_problem_create_changes(problem_plan))
            continue
        changes.append(_problem_diff(problem_plan.slug, problem_plan, current))
        existing_cases = {case["position"]: case for case in current.get("test_cases", [])}
        for case_plan in problem_plan.test_cases:
            path = f"{problem_plan.slug}/test-cases/{case_plan.position}"
            case = existing_cases.get(case_plan.position)
            changes.append(
                Change(action="create", kind="test_case", path=path)
                if case is None
                else _diff("test_case", path, case_plan, case, CASE_FIELDS, str(case["id"]))
            )
        existing_templates = {t["language"]: t for t in current.get("templates", [])}
        for template_plan in problem_plan.templates:
            path = f"{problem_plan.slug}/templates/{template_plan.language}"
            template = existing_templates.get(template_plan.language)
            changes.append(
                Change(action="create", kind="template", path=path)
                if template is None
                else _diff(
                    "template",
                    path,
                    template_plan,
                    template,
                    TEMPLATE_FIELDS,
                    f"{current['id']}:{template_plan.language}",
                )
            )
    return changes


def _problem_diff(path: str, desired: ProblemPlan, current: dict[str, Any]) -> Change:
    """Tags need their own comparison: the plan lists names, the API returns {id, name} objects."""
    changed = [
        field for field in PROBLEM_FIELDS if _plain(getattr(desired, field)) != current.get(field)
    ]
    current_tags = sorted(tag["name"] for tag in current.get("tags", []))
    if sorted(desired.tags) != current_tags:
        changed.append("tags")
    return Change(
        action="update" if changed else "unchanged",
        kind="problem",
        path=path,
        entity_id=str(current["id"]),
        fields=changed,
    )


def _problem_create_changes(plan: ProblemPlan) -> list[Change]:
    changes = [Change(action="create", kind="problem", path=plan.slug)]
    changes.extend(
        Change(action="create", kind="test_case", path=f"{plan.slug}/test-cases/{case.position}")
        for case in plan.test_cases
    )
    changes.extend(
        Change(action="create", kind="template", path=f"{plan.slug}/templates/{template.language}")
        for template in plan.templates
    )
    return changes
