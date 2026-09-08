from __future__ import annotations

from typing import Any

import pytest

from tramplin_mcp import algorithm_planner as planner
from tramplin_mcp.models import AlgorithmPlan


class StubClient:
    def __init__(self, problems: dict[str, dict[str, Any]] | None = None) -> None:
        self._problems = problems or {}
        self.applied_payloads: list[dict[str, Any]] = []

    async def get_problem_by_slug(self, slug: str) -> dict[str, Any] | None:
        return self._problems.get(slug)

    async def apply_algorithm_plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.applied_payloads.append(payload)
        return {"created": 1, "updated": 0, "unchanged": 0}


def valid_plan() -> AlgorithmPlan:
    return AlgorithmPlan.model_validate(
        {
            "problems": [
                {
                    "slug": "two-sum",
                    "title": "Two Sum",
                    "statement_md": "Найдите два числа",
                    "difficulty": "easy",
                    "test_cases": [
                        {"position": 0, "expected_output": "3", "is_sample": True},
                        {"position": 1, "expected_output": "5"},
                    ],
                }
            ]
        }
    )


async def test_validate_plan_flags_empty_statement_as_warning() -> None:
    plan = AlgorithmPlan.model_validate(
        {"problems": [{"slug": "p", "title": "P", "difficulty": "easy"}]}
    )
    result = await planner.validate_plan(StubClient(), plan)
    assert result.valid is True
    assert any("условие" in i.message.lower() for i in result.issues)


async def test_validate_plan_requires_external_url_for_external_provider() -> None:
    plan = AlgorithmPlan.model_validate(
        {"problems": [{"slug": "p", "title": "P", "difficulty": "easy", "provider": "external"}]}
    )
    result = await planner.validate_plan(StubClient(), plan)
    assert result.valid is False
    assert any(i.severity == "error" for i in result.issues)


async def test_validate_plan_rejects_non_https_external_url() -> None:
    plan = AlgorithmPlan.model_validate(
        {
            "problems": [
                {
                    "slug": "p",
                    "title": "P",
                    "difficulty": "easy",
                    "provider": "external",
                    "external_url": "http://example.com",
                }
            ]
        }
    )
    result = await planner.validate_plan(StubClient(), plan)
    assert result.valid is False


async def test_validate_plan_warns_about_missing_sample_case() -> None:
    plan = AlgorithmPlan.model_validate(
        {
            "problems": [
                {
                    "slug": "p",
                    "title": "P",
                    "statement_md": "x",
                    "difficulty": "easy",
                    "test_cases": [{"position": 0, "expected_output": "1"}],
                }
            ]
        }
    )
    result = await planner.validate_plan(StubClient(), plan)
    assert result.valid is True
    assert any("sample" in i.message.lower() for i in result.issues)


async def test_preview_plan_for_new_problem_counts_all_as_creates() -> None:
    preview = await planner.preview_plan(StubClient(), valid_plan())
    assert preview.creates == len(preview.changes)
    assert preview.updates == 0
    assert preview.unchanged == 0


async def test_apply_plan_rejects_invalid_plan_without_calling_the_api() -> None:
    plan = AlgorithmPlan.model_validate(
        {"problems": [{"slug": "p", "title": "P", "difficulty": "easy", "provider": "external"}]}
    )
    client = StubClient()
    with pytest.raises(ValueError, match="invalid"):
        await planner.apply_plan(client, plan)
    assert client.applied_payloads == []


async def test_apply_plan_sends_the_plan_and_reports_completion() -> None:
    client = StubClient()
    plan = valid_plan()
    result = await planner.apply_plan(client, plan)
    assert result.completed is True
    assert client.applied_payloads == [plan.model_dump(mode="json")]
    assert result.warnings
