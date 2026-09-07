from __future__ import annotations

from typing import Any

import pytest

from tramplin_mcp import planner
from tramplin_mcp.models import CoursePlan


class StubClient:
    def __init__(self, current: dict[str, Any] | None = None) -> None:
        self.current = current
        self.applied_payloads: list[dict[str, Any]] = []
        self.previewed_markdown: list[str] = []

    async def get_course(self, slug: str) -> dict[str, Any] | None:
        return self.current if self.current and self.current["slug"] == slug else None

    async def preview_markdown(self, body_md: str) -> dict[str, Any]:
        self.previewed_markdown.append(body_md)
        return {"body_html": "<p></p>", "interview_cards": []}

    async def apply_course_plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.applied_payloads.append(payload)
        return {"course_id": "1", "course_slug": payload["slug"]}


def valid_plan() -> CoursePlan:
    return CoursePlan.model_validate(
        {
            "title": "Python",
            "slug": "python",
            "modules": [
                {
                    "title": "Basics",
                    "slug": "basics",
                    "lessons": [{"title": "Intro", "slug": "intro", "body_md": "# Intro"}],
                    "quizzes": [
                        {
                            "title": "Check",
                            "slug": "check",
                            "lesson_slug": "intro",
                            "questions": [
                                {
                                    "position": 0,
                                    "prompt_md": "?",
                                    "type": "text",
                                    "answer": {"accepted": ["42"]},
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    )


async def test_validate_plan_flags_empty_lesson_as_warning() -> None:
    plan = CoursePlan.model_validate(
        {
            "title": "C",
            "slug": "c",
            "modules": [
                {
                    "title": "M",
                    "slug": "m",
                    "lessons": [{"title": "Empty", "slug": "empty", "body_md": "   "}],
                }
            ],
        }
    )
    result = await planner.validate_plan(StubClient(), plan)
    assert result.valid is True
    assert [i.severity for i in result.issues] == ["warning"]
    assert "Пустой" in result.issues[0].message


async def test_validate_plan_flags_cross_module_lesson_link_as_error() -> None:
    plan = CoursePlan.model_validate(
        {
            "title": "C",
            "slug": "c",
            "modules": [
                {
                    "title": "M",
                    "slug": "m",
                    "quizzes": [
                        {
                            "title": "Q",
                            "slug": "q",
                            "lesson_slug": "missing",
                            "questions": [
                                {
                                    "position": 0,
                                    "prompt_md": "?",
                                    "type": "text",
                                    "answer": {"accepted": ["x"]},
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    )
    result = await planner.validate_plan(StubClient(), plan)
    assert result.valid is False
    assert result.issues[0].severity == "error"


async def test_validate_plan_flags_quiz_without_questions_as_warning() -> None:
    plan = CoursePlan.model_validate(
        {
            "title": "C",
            "slug": "c",
            "modules": [{"title": "M", "slug": "m", "quizzes": [{"title": "Q", "slug": "q"}]}],
        }
    )
    result = await planner.validate_plan(StubClient(), plan)
    assert result.valid is True
    assert result.issues[0].severity == "warning"


async def test_validate_plan_previews_non_empty_lesson_markdown() -> None:
    client = StubClient()
    await planner.validate_plan(client, valid_plan())
    assert client.previewed_markdown == ["# Intro"]


async def test_preview_plan_for_new_course_counts_all_as_creates() -> None:
    preview = await planner.preview_plan(StubClient(), valid_plan())
    assert preview.creates == len(preview.changes)
    assert preview.updates == 0
    assert preview.unchanged == 0
    assert preview.warnings == []


async def test_apply_plan_rejects_invalid_plan_without_calling_the_api() -> None:
    plan = CoursePlan.model_validate(
        {
            "title": "C",
            "slug": "c",
            "modules": [
                {
                    "title": "M",
                    "slug": "m",
                    "quizzes": [
                        {
                            "title": "Q",
                            "slug": "q",
                            "lesson_slug": "missing",
                            "questions": [
                                {
                                    "position": 0,
                                    "prompt_md": "?",
                                    "type": "text",
                                    "answer": {"accepted": ["x"]},
                                }
                            ],
                        }
                    ],
                }
            ],
        }
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
    assert result.course_slug == "python"
    assert client.applied_payloads == [plan.model_dump(mode="json")]


async def test_apply_plan_on_existing_course_warns_about_additive_semantics() -> None:
    client = StubClient(current={"id": "1", "slug": "python", "modules": []})
    result = await planner.apply_plan(client, valid_plan())
    assert result.warnings
