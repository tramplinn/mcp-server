from __future__ import annotations

from typing import Any, Literal

from tramplin_mcp.client import TramplinClient
from tramplin_mcp.models import (
    ApplyResult,
    Change,
    CoursePlan,
    CoursePlanPreview,
    CoursePlanValidation,
    ModulePlan,
    QuestionPlan,
    QuizPlan,
    ValidationIssue,
)

COURSE_FIELDS = ("title", "summary", "color", "est_hours")
MODULE_FIELDS = ("title", "summary")
LESSON_FIELDS = ("title", "body_md", "est_minutes")
QUIZ_FIELDS = ("title", "lesson_id")
QUESTION_FIELDS = ("position", "prompt_md", "type", "options", "answer", "explain_md")


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
            for question in quiz.questions:
                message = _question_error(question)
                if message:
                    issues.append(
                        ValidationIssue(
                            severity="error",
                            path=f"{path}/questions/{question.position}",
                            message=message,
                        )
                    )
    return CoursePlanValidation(
        valid=not any(issue.severity == "error" for issue in issues), issues=issues
    )


async def preview_plan(client: TramplinClient, plan: CoursePlan) -> CoursePlanPreview:
    current = await client.get_course(plan.slug)
    changes = await _changes(client, plan, current)
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
    changes = await _changes(client, plan, current)
    await client.apply_course_plan(plan.model_dump(mode="json"))
    return ApplyResult(
        course_slug=plan.slug,
        completed=True,
        changes=changes,
        warnings=_warnings(current),
    )


async def _apply_module(
    client: TramplinClient,
    course_slug: str,
    plan: ModulePlan,
    module: dict[str, Any],
    changes: list[Change],
) -> tuple[list[Change], list[str]]:
    applied: list[Change] = []
    lessons = await _lesson_index(client, module)
    lesson_ids: dict[str, str] = {}
    for lesson_plan in plan.lessons:
        path = f"{course_slug}/{plan.slug}/{lesson_plan.slug}"
        change = _find_change(changes, "lesson", path)
        lesson = lessons.get(lesson_plan.slug)
        if lesson is None:
            lesson = await client.create_lesson(
                str(module["id"]), {**lesson_plan.model_dump(), "status": "draft"}
            )
        elif change.action == "update":
            lesson = await client.update_lesson(
                str(lesson["id"]), _selected_payload(lesson_plan, change.fields)
            )
        lesson_ids[lesson_plan.slug] = str(lesson["id"])
        applied.append(change)

    quizzes = await _quiz_index(client, module)
    quiz_ids: dict[str, str] = {}
    for quiz_plan in plan.quizzes:
        path = f"{course_slug}/{plan.slug}/{quiz_plan.slug}"
        change = _find_change(changes, "quiz", path)
        lesson_id = lesson_ids.get(quiz_plan.lesson_slug or "")
        quiz = quizzes.get(quiz_plan.slug)
        payload = {"title": quiz_plan.title, "slug": quiz_plan.slug, "lesson_id": lesson_id}
        if quiz is None:
            quiz = await client.create_quiz(str(module["id"]), {**payload, "status": "draft"})
            quiz["questions"] = []
        elif change.action == "update":
            quiz = await client.update_quiz(str(quiz["id"]), payload)
            quiz = await client.get_quiz(str(quiz["id"]))
        question_changes = await _apply_questions(client, path, quiz_plan, quiz, changes)
        applied.extend([change, *question_changes])
        quiz_ids[quiz_plan.slug] = str(quiz["id"])

    ids = {**lesson_ids, **quiz_ids}
    order = plan.content_order or [*lesson_ids, *quiz_ids]
    return applied, [ids[slug] for slug in order]


async def _apply_questions(
    client: TramplinClient,
    quiz_path: str,
    plan: QuizPlan,
    quiz: dict[str, Any],
    changes: list[Change],
) -> list[Change]:
    current = {question["position"]: question for question in quiz.get("questions", [])}
    applied: list[Change] = []
    for question_plan in plan.questions:
        path = f"{quiz_path}/questions/{question_plan.position}"
        change = _find_change(changes, "question", path)
        question = current.get(question_plan.position)
        payload = question_plan.model_dump()
        if question is None:
            await client.create_question(str(quiz["id"]), payload)
        elif change.action == "update":
            await client.update_question(str(question["id"]), payload)
        applied.append(change)
    return applied


async def _changes(
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
            changes.append(_diff_dict("quiz", path, desired, quiz, QUIZ_FIELDS, str(quiz["id"])))
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
    return changes


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
    kind: Literal["course", "module", "lesson", "question"],
    path: str,
    desired: object,
    current: dict[str, Any],
    fields: tuple[str, ...],
    entity_id: str,
) -> Change:
    changed = [field for field in fields if getattr(desired, field) != current.get(field)]
    return Change(
        action="update" if changed else "unchanged",
        kind=kind,
        path=path,
        entity_id=entity_id,
        fields=changed,
    )


def _diff_dict(
    kind: Literal["quiz"],
    path: str,
    desired: dict[str, Any],
    current: dict[str, Any],
    fields: tuple[str, ...],
    entity_id: str,
) -> Change:
    changed = [field for field in fields if desired.get(field) != current.get(field)]
    return Change(
        action="update" if changed else "unchanged",
        kind=kind,
        path=path,
        entity_id=entity_id,
        fields=changed,
    )


def _selected_payload(model: object, fields: list[str]) -> dict[str, Any]:
    return {field: getattr(model, field) for field in fields if field != "position"}


def _course_payload(plan: CoursePlan) -> dict[str, Any]:
    return {
        "title": plan.title,
        "slug": plan.slug,
        "summary": plan.summary,
        "color": plan.color,
        "est_hours": plan.est_hours,
        "status": "draft",
    }


def _find_change(changes: list[Change], kind: str, path: str) -> Change:
    return next(change for change in changes if change.kind == kind and change.path == path)


def _complete_order(desired: list[str], existing: list[str]) -> list[str]:
    desired_set = set(desired)
    return [*desired, *(item for item in existing if item not in desired_set)]


def _warnings(current: dict[str, Any] | None) -> list[str]:
    return [] if current is None else ["Additive-only: сущности вне плана сохраняются в конце."]


def _question_error(question: QuestionPlan) -> str | None:
    answer = question.answer
    if question.type == "single" and "value" in answer:
        return None
    if question.type == "multiple" and isinstance(answer.get("values"), list):
        return None
    if question.type == "text":
        accepted = answer.get("accepted")
        if (
            isinstance(accepted, list)
            and accepted
            and all(isinstance(item, str) for item in accepted)
        ):
            return None
    if question.type == "file" and not answer:
        return None
    if question.type in {"matching", "grouping"}:
        key = "pairs" if question.type == "matching" else "groups"
        if isinstance(answer.get(key), dict) and answer[key]:
            return None
    return f"Неверный формат answer для типа {question.type}"
