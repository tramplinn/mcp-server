# PRD: авторка алгоритмических задач через MCP

Статус: черновик, не реализовано. Собран по итогам обсуждения в сессии
Claude Code от 2026-09-07. Ниже — объём, который выбрал автор проекта
("всё целиком, включая practice sets"; сопоставление плана с существующей
задачей — по `slug`), и открытые вопросы, которые нужно закрыть перед
реализацией.

## Контекст

Курсовая авторка (`preview_course_plan` / `validate_course_plan` /
`apply_course_plan`) уже реализует нужный паттерн: агент присылает
декларативный план целиком, сервер идемпотентно создаёт/обновляет
сущности, сопоставляя их по стабильному `slug`, и ничего не удаляет.
Задача — перенести этот же паттерн на алгоритмические задачи
(`AlgorithmProblem`) и наборы практики (`PracticeSet`).

Ключевое отличие от курсов: **у задач и наборов практики сейчас нет
`slug`** (`backend/src/tramplin/models/algorithms.py`) — только `id`
(UUID) и, для внешних задач, `external_key`. Значит, до реализации
плана нужна миграция БД.

## Объём (выбран автором проекта)

Всё целиком за один заход:

1. **Задачи** (`AlgorithmProblem`): title, statement_md, difficulty,
   tags, time_limit_ms, memory_limit_kb, provider/external_key/external_url.
2. **Тест-кейсы** (`AlgorithmTestCase`): position, input, expected_output,
   is_sample, weight.
3. **Шаблоны кода** (`AlgorithmTemplate`): starter_code/solution_code на
   язык (ключ — `language`, уже стабилен, миграция не нужна).
4. **Наборы практики** (`PracticeSet` + `PracticeSetProblem`): title,
   description, mode, duration_minutes, состав и порядок задач.

`validate_template` (гоняет solution_code через judge0 по всем
тест-кейсам) **не** входит в `apply` — остаётся отдельным ручным тулом:
это медленная операция с внешней зависимостью (runner), автоматический
вызов на каждый apply был бы сюрпризом и точкой отказа. См. открытый
вопрос ниже про то, нужен ли он вообще в MCP на этот заход.

## Идентификация и миграция

Автор выбрал: **matching по `slug`**, как у курсов — не по `id` и не по
`external_key`. Это самый предсказуемый вариант для агента (он сам
придумывает и переиспользует slug в плане, не обязан сперва читать `id`
через inspect-тул).

Требуется:

- Миграция alembic: колонка `slug` (`String(120)`, паттерн
  `^[a-z0-9]+(?:-[a-z0-9]+)*$`, как `SLUG_PATTERN` в
  `course_plans.py`/`mcp-server/models.py`) на `algorithm_problems` и
  `practice_sets`. Уникальность — глобальная (задачи/наборы не вложены
  в курс, в отличие от модулей/уроков).
- Бэкфилл существующих строк: сгенерировать slug из `title`
  (транслитерация + дедуп, как это наверняка уже где-то в кодовой базе
  для tags/tracks — проверить `services/`), затем `NOT NULL` + unique
  constraint отдельным шагом.
- Обновить схемы: `ProblemCreate`/`ProblemUpdate`/`ProblemOut`/
  `ProblemAuthorOut`, `PracticeSetCreate`/`PracticeSetUpdate`/
  `PracticeSetOut` — добавить `slug`.

## Backend: новый сервис плана

По образцу `CoursePlanService` (`backend/src/tramplin/services/course_plans.py`):

- Новая схема `AlgorithmPlanApply` (`backend/src/tramplin/api/schemas/algorithm_plans.py`):
  ```
  problems: list[ProblemPlan]       # slug, title, provider, external_key,
                                     # external_url, statement_md, difficulty,
                                     # tags, time_limit_ms, memory_limit_kb,
                                     # test_cases: list[TestCasePlan],
                                     # templates: list[TemplatePlan]
  practice_sets: list[PracticeSetPlanItem]  # slug, title, description, mode,
                                             # duration_minutes,
                                             # problem_slugs: list[str]  (порядок = позиция)
  ```
  Задачи и наборы — на одном уровне плана, не вложены друг в друга:
  `practice_sets[].problem_slugs` — плоская ссылка. Это позволяет одним
  `apply` создать и задачи, и набор, который сразу на них ссылается.
- Новый `AlgorithmPlanService.apply()`: транзакция целиком, matching по
  slug, additive-only (задачи/наборы вне плана не трогаются, как модули
  вне курсового плана). Тест-кейсы — matching по `position` (как вопросы
  теста в `_apply_questions`); шаблоны — matching по `language` (уже PK).
  И то, и другое — additive: элементы вне плана внутри существующей
  задачи не удаляются (сохранить симметрию с философией курсового плана).
- Новый роут `POST /authoring/algorithm-plans/apply`, тегом
  `authoring:algorithm-plans`, подключить в `authoring.py`.
- **Проверить перед реализацией**: `create_problem`/`update_problem` в
  `AlgorithmAuthoringService` — не поручают ли они где-то постановку в
  очередь эмбеддинга (`embedding_model`/`embedding_queue_name` в
  `Settings`, поле `embedding: Mapped[list[float] | None]` на
  `AlgorithmProblem`)? Если да — `AlgorithmPlanService` обязан
  воспроизвести тот же побочный эффект, иначе задачи, созданные через
  MCP, выпадут из семантического поиска.
- Для чтения текущего состояния (нужно MCP-клиенту для diff, как
  `GET /authoring/courses/{slug}`) — нужен `GET` по slug для задачи и
  для набора практики. Сейчас `GET /authoring/algorithms/problems/{id}`
  принимает только UUID — добавить поиск по slug (новый роут или
  query-параметр).

## MCP: новые модели, диффер, тулы

- `models.py`: `ProblemPlan`, `TestCasePlan`, `TemplatePlan`,
  `PracticeSetPlan`, `AlgorithmPlan` (агрегат `problems` + `practice_sets`,
  как `CoursePlan` агрегирует `modules`). Плюс `Change`/`*Preview`/
  `*Validation`/`*ApplyResult` — рассмотреть, стоит ли обобщить текущие
  курсовые `Change`/`CoursePlanPreview`/`CoursePlanValidation`/
  `ApplyResult` в доменно-нейтральные имена, раз появляется второй вид
  плана, или завести отдельные `AlgorithmPlanPreview` и т.п. по аналогии
  — решить при реализации, здесь просто зафиксировать факт дублирования.
- `diff.py`: логика `_diff`/`_plain` уже доменно-нейтральна (работает с
  произвольными `fields: tuple[str, ...]`) — можно переиспользовать
  напрямую или вынести в общий `_diff`/`_plain` модуль, а
  `changes_for`/`_lesson_index`-подобные обходы дерева написать отдельно
  для алгоритмов (`algorithm_diff.py`), т.к. форма дерева другая.
- `planner.py` → добавить `algorithm_planner.py` с тем же трёхтактным
  API: `validate_plan`/`preview_plan`/`apply_plan`.
- `client.py`: `list_problems`, `get_problem(slug)`, `get_practice_set(slug)`,
  `apply_algorithm_plan(payload)`, и опционально `validate_template(...)`
  (см. открытый вопрос).
- `server.py`: тулы `list_problems`, `inspect_problem`,
  `list_practice_sets`, `inspect_practice_set`, `preview_algorithm_plan`,
  `validate_algorithm_plan`, `apply_algorithm_plan`. Инструкции тула
  должны явно говорить, что `apply_algorithm_plan` не запускает
  `validate_template` — агент должен понимать, что синтаксическая
  валидность плана не значит, что решение проходит тесты.

## Открытые вопросы (закрыть до реализации)

1. **Нужен ли `validate_template` в MCP вообще на этот заход?** Он бьёт
   в judge0 (внешний runner), может быть медленным/недоступным. Если
   да — как тул явно помечать это в описании (не молчаливый side-effect).
2. **Бэкфилл slug для существующих задач**: транслитерация title,
   дедуп при коллизиях — есть ли уже готовая утилита в
   `backend/src/tramplin/services/` (использовалась для tags/tracks)?
   Переиспользовать, не писать заново.
3. **Побочный эффект эмбеддинга** при create/update — см. пункт выше в
   backend-разделе; нужно явно проверить существующий `create_problem`/
   `update_problem` и/или `AlgorithmDispatchService` перед тем, как
   писать `AlgorithmPlanService.apply()`.
4. **Наименование**: обобщать ли `Change`/`CoursePlanPreview`/
   `CoursePlanValidation`/`ApplyResult` под оба вида планов, или держать
   отдельные типы. Решить, чтобы не плодить два почти одинаковых DTO без
   причины, но и не тащить курсовые имена в алгоритмический домен.
5. **is_sample тест-кейсы**: показывать ли их отдельно в
   `preview_algorithm_plan`/`validate_algorithm_plan` (например
   предупреждение "нет ни одного sample-теста" — по аналогии с "Тест без
   вопросов" у курсов)?

## Тест-план

- Backend: `tests/test_algorithm_plans.py` по образцу
  `tests/test_course_plans.py` — create+update идемпотентно, additive-only
  для задач/наборов вне плана, regression-тест на коллизию slug
  (аналог `uq_modules_course_id_position`, если конфликты позиций
  вообще возможны для test_cases/practice_set_problems).
- MCP: `tests/test_algorithm_diff.py`, `tests/test_algorithm_planner.py`,
  плюс модели в `tests/test_models.py` — по образцу того, что уже
  написано для курсов в этой сессии (`tests/test_diff.py`,
  `tests/test_planner.py`).
- Сквозная проверка (как делали в этой сессии для course-plan): собрать
  `AlgorithmPlan` через MCP-модели, прогнать `model_dump(mode="json")`
  через backend-схему и фейковые репозитории (`tests/fakes.py`), убедиться
  что apply не падает и diff после повторного apply даёт `unchanged`.

## Вне рамок этого PRD

- Практические сессии/сабмишены/прогресс студента — не авторский
  функционал, не трогаем.
- `admin/code-runner/*` эндпоинты — сейчас в процессе удаления в
  backend (см. незакоммиченные изменения в `backend/` на момент
  написания), не завязываться на них.
- Автоматический запуск `validate_template` внутри `apply` — сознательно
  исключено (см. открытый вопрос 1).
