from __future__ import annotations

from typing import Any

from tramplin_mcp.diff import changes_for
from tramplin_mcp.models import CoursePlan


class StubClient:
    def __init__(
        self,
        lessons: dict[str, dict[str, Any]] | None = None,
        quizzes: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self._lessons = lessons or {}
        self._quizzes = quizzes or {}

    async def get_lesson(self, lesson_id: str) -> dict[str, Any]:
        return self._lessons[lesson_id]

    async def get_quiz(self, quiz_id: str) -> dict[str, Any]:
        return self._quizzes[quiz_id]


def plan(**overrides: Any) -> CoursePlan:
    base = {
        "title": "Python",
        "slug": "python",
        "modules": [
            {
                "title": "Basics",
                "slug": "basics",
                "lessons": [{"title": "Intro", "slug": "intro", "body_md": "# Intro"}],
            }
        ],
    }
    base.update(overrides)
    return CoursePlan.model_validate(base)


async def test_new_course_is_all_creates() -> None:
    changes = await changes_for(StubClient(), plan(), None)
    assert [c.action for c in changes] == ["create", "create", "create"]
    assert [c.kind for c in changes] == ["course", "module", "lesson"]


async def test_identical_plan_is_unchanged() -> None:
    current = {
        "id": "course-1",
        "title": "Python",
        "summary": None,
        "color": None,
        "est_hours": None,
        "modules": [
            {
                "id": "module-1",
                "slug": "basics",
                "title": "Basics",
                "summary": None,
                "position": 0,
                "items": [
                    {
                        "kind": "lesson",
                        "lesson": {
                            "id": "lesson-1",
                            "slug": "intro",
                            "title": "Intro",
                            "body_md": "# Intro",
                            "est_minutes": None,
                        },
                    }
                ],
            }
        ],
    }
    changes = await changes_for(StubClient(), plan(), current)
    assert all(c.action == "unchanged" for c in changes)
    assert [c.entity_id for c in changes] == ["course-1", "module-1", "lesson-1"]


async def test_detects_changed_lesson_field() -> None:
    current = {
        "id": "course-1",
        "title": "Python",
        "summary": None,
        "color": None,
        "est_hours": None,
        "modules": [
            {
                "id": "module-1",
                "slug": "basics",
                "title": "Basics",
                "summary": None,
                "position": 0,
                "items": [
                    {
                        "kind": "lesson",
                        "lesson": {
                            "id": "lesson-1",
                            "slug": "intro",
                            "title": "Intro",
                            "body_md": "# Old body",
                            "est_minutes": None,
                        },
                    }
                ],
            }
        ],
    }
    changes = await changes_for(StubClient(), plan(), current)
    lesson_change = next(c for c in changes if c.kind == "lesson")
    assert lesson_change.action == "update"
    assert lesson_change.fields == ["body_md"]


async def test_detects_module_position_change() -> None:
    current = {
        "id": "course-1",
        "title": "Python",
        "summary": None,
        "color": None,
        "est_hours": None,
        "modules": [
            {
                "id": "module-1",
                "slug": "basics",
                "title": "Basics",
                "summary": None,
                "position": 5,
                "items": [],
            }
        ],
    }
    changes = await changes_for(
        StubClient(),
        plan(modules=[{"title": "Basics", "slug": "basics"}]),
        current,
    )
    module_change = next(c for c in changes if c.kind == "module")
    assert module_change.action == "update"
    assert module_change.fields == ["position"]


async def test_new_module_on_existing_course_is_a_create() -> None:
    current = {
        "id": "course-1",
        "title": "Python",
        "summary": None,
        "color": None,
        "est_hours": None,
        "modules": [],
    }
    changes = await changes_for(StubClient(), plan(), current)
    assert [c.action for c in changes] == ["unchanged", "create", "create"]
