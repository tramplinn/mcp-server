"""Computes the create/update/unchanged diff between a CoursePlan and Tramplin's current state."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from tramplin_mcp.client import TramplinClient
from tramplin_mcp.models import (
    Change,
    ChangeKind,
    CoursePlan,
    ModulePlan,
    PracticeSetPlan,
    QuizPlan,
)

COURSE_FIELDS = ("title", "summary", "color", "est_hours")
MODULE_FIELDS = ("title", "summary")
LESSON_FIELDS = ("title", "body_md", "est_minutes")
QUIZ_FIELDS = ("title", "lesson_id")
QUESTION_FIELDS = ("position", "prompt_md", "type", "options", "answer", "explain_md")
PRACTICE_FIELDS = ("title", "description", "mode", "duration_minutes")


async def changes_for(
    client: TramplinClient, plan: CoursePlan, current: dict[str, Any] | None
) -> list[Change]:
    if current is None:
        return _all_create_changes(plan)
    changes = [_diff("course", plan.slug, plan, current, COURSE_FIELDS, str(current["id"]))]
    modules = {item["slug"]: item for item in current.get("modules", [])}
    for position, module_plan in enumerate(plan.modules):
        module_path = f"{plan.slug}/{module_plan.slug}"
        module = modules.get(module_plan.slug)
        if module is None:
            changes.extend(_module_create_changes(module_path, module_plan))
            continue
        module_change = _diff(
            "module", module_path, module_plan, module, MODULE_FIELDS, str(module["id"])
        )
        if module.get("position") != position:
            module_change.action = "update"
            module_change.fields.append("position")
        changes.append(module_change)
        lessons = await _lesson_index(client, module)
        for lesson_plan in module_plan.lessons:
            path = f"{module_path}/{lesson_plan.slug}"
            lesson = lessons.get(lesson_plan.slug)
            changes.append(
                Change(action="create", kind="lesson", path=path)
                if lesson is None
                else _diff("lesson", path, lesson_plan, lesson, LESSON_FIELDS, str(lesson["id"]))
            )
        quizzes = await _quiz_index(client, module)
        lesson_ids = {slug: str(item["id"]) for slug, item in lessons.items()}
        for quiz_plan in module_plan.quizzes:
            path = f"{module_path}/{quiz_plan.slug}"
            quiz = quizzes.get(quiz_plan.slug)
            if quiz is None:
                changes.extend(_quiz_create_changes(path, quiz_plan))
                continue
            desired = {
                "title": quiz_plan.title,
                "lesson_id": lesson_ids.get(quiz_plan.lesson_slug or ""),
            }
            changes.append(_diff("quiz", path, desired, quiz, QUIZ_FIELDS, str(quiz["id"])))
            questions = {question["position"]: question for question in quiz.get("questions", [])}
            for question in quiz_plan.questions:
                question_path = f"{path}/questions/{question.position}"
                existing = questions.get(question.position)
                changes.append(
                    Change(action="create", kind="question", path=question_path)
                    if existing is None
                    else _diff(
                        "question",
                        question_path,
                        question,
                        existing,
                        QUESTION_FIELDS,
                        str(existing["id"]),
                    )
                )
        practice_sets = await _practice_index(client, module)
        for practice_plan in module_plan.practice_sets:
            path = f"{module_path}/practice/{practice_plan.title}"
            practice = practice_sets.get(practice_plan.title)
            if practice is None:
                changes.append(Change(action="create", kind="practice", path=path))
                continue
            changes.append(await _diff_practice_set(client, path, practice_plan, practice))
    return changes


async def _diff_practice_set(
    client: TramplinClient,
    path: str,
    plan: PracticeSetPlan,
    current: dict[str, Any],
) -> Change:
    desired = {
        "title": plan.title,
        "description": plan.description,
        "mode": plan.mode,
        "duration_minutes": plan.duration_minutes,
    }
    change = _diff("practice", path, desired, current, PRACTICE_FIELDS, str(current["id"]))
    existing_problem_ids = {str(item["problem_id"]) for item in current.get("problems", [])}
    desired_problem_ids: set[str] = set()
    for slug in plan.problem_slugs:
        problem = await client.get_problem_by_slug(slug)
        if problem is not None:
            desired_problem_ids.add(str(problem["id"]))
    if desired_problem_ids - existing_problem_ids:
        change.action = "update"
        if "problem_slugs" not in change.fields:
            change.fields.append("problem_slugs")
    return change


async def _practice_index(
    client: TramplinClient, module: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in module.get("items", []):
        if item.get("kind") == "practice":
            practice = await client.get_practice_set(str(item["practice_set"]["id"]))
            result[str(practice["title"])] = practice
    return result


async def _lesson_index(
    client: TramplinClient, module: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in module.get("items", []):
        if item.get("kind") == "lesson":
            lesson = dict(item["lesson"])
            if "body_md" not in lesson:
                lesson = await client.get_lesson(str(lesson["id"]))
            result[str(lesson["slug"])] = lesson
    return result


async def _quiz_index(client: TramplinClient, module: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in module.get("items", []):
        if item.get("kind") == "quiz":
            quiz = await client.get_quiz(str(item["quiz"]["id"]))
            result[str(quiz["slug"])] = quiz
    return result


def _all_create_changes(plan: CoursePlan) -> list[Change]:
    changes = [Change(action="create", kind="course", path=plan.slug)]
    for module in plan.modules:
        changes.extend(_module_create_changes(f"{plan.slug}/{module.slug}", module))
    return changes


def _module_create_changes(path: str, plan: ModulePlan) -> list[Change]:
    changes = [Change(action="create", kind="module", path=path)]
    changes.extend(
        Change(action="create", kind="lesson", path=f"{path}/{lesson.slug}")
        for lesson in plan.lessons
    )
    for quiz in plan.quizzes:
        changes.extend(_quiz_create_changes(f"{path}/{quiz.slug}", quiz))
    changes.extend(
        Change(action="create", kind="practice", path=f"{path}/practice/{practice.title}")
        for practice in plan.practice_sets
    )
    return changes


def _quiz_create_changes(path: str, plan: QuizPlan) -> list[Change]:
    return [
        Change(action="create", kind="quiz", path=path),
        *[
            Change(action="create", kind="question", path=f"{path}/questions/{q.position}")
            for q in plan.questions
        ],
    ]


def _diff(
    kind: ChangeKind,
    path: str,
    desired: object,
    current: dict[str, Any],
    fields: tuple[str, ...],
    entity_id: str,
) -> Change:
    lookup = desired.get if isinstance(desired, dict) else lambda field: getattr(desired, field)
    changed = [field for field in fields if _plain(lookup(field)) != current.get(field)]
    return Change(
        action="update" if changed else "unchanged",
        kind=kind,
        path=path,
        entity_id=entity_id,
        fields=changed,
    )


def _plain(value: object) -> object:
    """`desired` values from a CoursePlan are typed models; `current` comes from the API as
    plain JSON. Question `answer`/`options` in particular are now per-type pydantic models
    (see QuestionPlan), so they need dumping before they can be compared to the API's dicts."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value
