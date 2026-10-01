from __future__ import annotations

import pytest
from pydantic import ValidationError

from tramplin_mcp.models import (
    CoursePlanReport,
    FileQuestionPlan,
    GroupingQuestionPlan,
    MatchingQuestionPlan,
    ModulePlan,
    MultipleQuestionPlan,
    QuizPlan,
    SingleQuestionPlan,
    TextQuestionPlan,
    TrackPlan,
)


def test_rejects_invalid_slug() -> None:
    with pytest.raises(ValidationError):
        ModulePlan.model_validate({"title": "M", "slug": "Not Valid"})


def test_plan_inputs_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="extra"):
        TrackPlan.model_validate({"title": "T", "slug": "t", "courses": ["a"]})


def test_reports_ignore_new_backend_fields() -> None:
    report = CoursePlanReport.model_validate(
        {
            "course_slug": "c",
            "course_id": "id-1",
            "valid": True,
            "created": 1,
            "updated": 0,
            "unchanged": 0,
            "changes": [
                {
                    "action": "create",
                    "kind": "lesson",
                    "path": "c/m/l",
                    "entity_id": "id-2",
                    "fields": [],
                    "future_field": 1,
                }
            ],
            "issues": [
                {"severity": "warning", "path": "c/m/l", "code": "empty_lesson", "message": "…"}
            ],
            "warnings": [],
            "future_field": True,
        }
    )

    assert report.changes[0].entity_id == "id-2"
    assert report.issues[0].code == "empty_lesson"


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (
            SingleQuestionPlan,
            {
                "position": 0,
                "prompt_md": "?",
                "type": "single",
                "options": [{"value": "a", "label": "A"}],
                "answer": {"value": "a"},
            },
        ),
        (
            MultipleQuestionPlan,
            {
                "position": 0,
                "prompt_md": "?",
                "type": "multiple",
                "options": [{"value": "a", "label": "A"}],
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
