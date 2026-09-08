from __future__ import annotations

from typing import Any

from tramplin_mcp.algorithm_diff import changes_for
from tramplin_mcp.models import AlgorithmPlan


class StubClient:
    def __init__(self, problems: dict[str, dict[str, Any]] | None = None) -> None:
        self._problems = problems or {}

    async def get_problem_by_slug(self, slug: str) -> dict[str, Any] | None:
        return self._problems.get(slug)


def plan(**overrides: Any) -> AlgorithmPlan:
    base: dict[str, Any] = {
        "problems": [
            {
                "slug": "two-sum",
                "title": "Two Sum",
                "difficulty": "easy",
                "test_cases": [
                    {"position": 0, "expected_output": "3", "is_sample": True},
                ],
            }
        ]
    }
    base.update(overrides)
    return AlgorithmPlan.model_validate(base)


async def test_new_problem_is_all_creates() -> None:
    changes = await changes_for(StubClient(), plan())
    assert [c.action for c in changes] == ["create", "create"]
    assert [c.kind for c in changes] == ["problem", "test_case"]


async def test_identical_plan_is_unchanged() -> None:
    current = {
        "two-sum": {
            "id": "problem-1",
            "provider": "internal",
            "external_key": None,
            "external_url": None,
            "title": "Two Sum",
            "statement_md": "",
            "difficulty": "easy",
            "tags": [],
            "time_limit_ms": 1000,
            "memory_limit_kb": 262144,
            "test_cases": [
                {"id": "case-1", "position": 0, "input": "", "expected_output": "3", "weight": 1}
                | {"is_sample": True}
            ],
            "templates": [],
        }
    }
    changes = await changes_for(StubClient(current), plan())
    assert all(c.action == "unchanged" for c in changes)
    assert [c.entity_id for c in changes] == ["problem-1", "case-1"]


async def test_detects_changed_title_and_tags() -> None:
    current = {
        "two-sum": {
            "id": "problem-1",
            "provider": "internal",
            "external_key": None,
            "external_url": None,
            "title": "Old title",
            "statement_md": "",
            "difficulty": "easy",
            "tags": [{"id": "t1", "name": "arrays"}],
            "time_limit_ms": 1000,
            "memory_limit_kb": 262144,
            "test_cases": [],
            "templates": [],
        }
    }
    changes = await changes_for(StubClient(current), plan())
    problem_change = next(c for c in changes if c.kind == "problem")
    assert problem_change.action == "update"
    assert "title" in problem_change.fields
    assert "tags" in problem_change.fields


async def test_new_test_case_on_existing_problem_is_a_create() -> None:
    current = {
        "two-sum": {
            "id": "problem-1",
            "provider": "internal",
            "external_key": None,
            "external_url": None,
            "title": "Two Sum",
            "statement_md": "",
            "difficulty": "easy",
            "tags": [],
            "time_limit_ms": 1000,
            "memory_limit_kb": 262144,
            "test_cases": [],
            "templates": [],
        }
    }
    changes = await changes_for(StubClient(current), plan())
    case_change = next(c for c in changes if c.kind == "test_case")
    assert case_change.action == "create"
