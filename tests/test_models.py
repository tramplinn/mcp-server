from __future__ import annotations

import pytest
from pydantic import ValidationError

from tramplin_mcp.models import (
    CoursePlan,
    FileQuestionPlan,
    GroupingQuestionPlan,
    MatchingQuestionPlan,
    ModulePlan,
    MultipleQuestionPlan,
    QuizPlan,
    SingleQuestionPlan,
    TextQuestionPlan,
)


def test_rejects_invalid_slug() -> None:
    with pytest.raises(ValidationError):
        ModulePlan.model_validate({"title": "M", "slug": "Not Valid"})


def test_quiz_rejects_duplicate_question_positions() -> None:
    with pytest.raises(ValidationError, match="position"):
        QuizPlan.model_validate(
            {
                "title": "Q",
                "slug": "q",
                "questions": [
                    {
                        "position": 0,
                        "prompt_md": "a",
                        "type": "text",
                        "answer": {"accepted": ["x"]},
                    },
                    {
                        "position": 0,
                        "prompt_md": "b",
                        "type": "text",
                        "answer": {"accepted": ["y"]},
                    },
                ],
            }
        )


def test_module_rejects_duplicate_lesson_slugs() -> None:
    with pytest.raises(ValidationError, match="slug"):
        ModulePlan.model_validate(
            {
                "title": "M",
                "slug": "m",
                "lessons": [
                    {"title": "A", "slug": "intro"},
                    {"title": "B", "slug": "intro"},
                ],
            }
        )


def test_module_content_order_must_cover_every_slug() -> None:
    with pytest.raises(ValidationError, match="content_order"):
        ModulePlan.model_validate(
            {
                "title": "M",
                "slug": "m",
                "lessons": [{"title": "A", "slug": "intro"}],
                "content_order": ["intro", "missing"],
            }
        )


def test_module_content_order_accepts_matching_slugs() -> None:
    module = ModulePlan.model_validate(
        {
            "title": "M",
            "slug": "m",
            "lessons": [{"title": "A", "slug": "intro"}],
            "quizzes": [{"title": "Q", "slug": "check"}],
            "content_order": ["check", "intro"],
        }
    )
    assert module.content_order == ["check", "intro"]


def test_course_rejects_duplicate_module_slugs() -> None:
    with pytest.raises(ValidationError, match="module slug"):
        CoursePlan.model_validate(
            {
                "title": "C",
                "slug": "c",
                "modules": [
                    {"title": "A", "slug": "m"},
                    {"title": "B", "slug": "m"},
                ],
            }
        )


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (
            SingleQuestionPlan,
            {
                "position": 0,
                "prompt_md": "?",
                "type": "single",
                "options": [{"id": "a", "label": "A"}],
                "answer": {"value": "a"},
            },
        ),
        (
            MultipleQuestionPlan,
            {
                "position": 0,
                "prompt_md": "?",
                "type": "multiple",
                "options": [{"id": "a", "label": "A"}],
                "answer": {"values": ["a"]},
            },
        ),
        (
            TextQuestionPlan,
            {"position": 0, "prompt_md": "?", "type": "text", "answer": {"accepted": ["42"]}},
        ),
        (FileQuestionPlan, {"position": 0, "prompt_md": "?", "type": "file"}),
        (
            MatchingQuestionPlan,
            {
                "position": 0,
                "prompt_md": "?",
                "type": "matching",
                "options": [
                    {"id": "l1", "label": "L1", "kind": "left"},
                    {"id": "r1", "label": "R1", "kind": "right"},
                ],
                "answer": {"pairs": {"l1": "r1"}},
            },
        ),
        (
            GroupingQuestionPlan,
            {
                "position": 0,
                "prompt_md": "?",
                "type": "grouping",
                "options": [
                    {"id": "i1", "label": "I1", "kind": "item"},
                    {"id": "g1", "label": "G1", "kind": "group"},
                ],
                "answer": {"groups": {"i1": "g1"}},
            },
        ),
    ],
)
def test_each_question_type_round_trips_through_the_discriminated_union(
    model: type[SingleQuestionPlan]
    | type[MultipleQuestionPlan]
    | type[TextQuestionPlan]
    | type[FileQuestionPlan]
    | type[MatchingQuestionPlan]
    | type[GroupingQuestionPlan],
    payload: dict[str, object],
) -> None:
    quiz = QuizPlan.model_validate({"title": "Q", "slug": "q", "questions": [payload]})
    assert isinstance(quiz.questions[0], model)
