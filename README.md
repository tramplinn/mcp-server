# Tramplin MCP

Отдельный FastMCP-сервис для заполнения учебных материалов агентами. Сервис не
ходит в базу данных: все чтения и записи выполняются через публичный authoring API
Tramplin от имени преподавателя или администратора.

## Что умеет

Сервер — тонкая прослойка над authoring API: вся логика (валидация, diff, применение)
живёт в бэкенде, а MCP только пробрасывает вызовы и объясняет агенту, как ими
пользоваться (инструкции сервера, docstring'и тулов, описания полей схем).

| Тул | Ручка бэкенда |
| --- | --- |
| `list_courses` / `list_tracks` / `list_problems` | `GET /authoring/{courses,tracks,algorithms/problems}/index` — все сущности, без пагинации |
| `inspect_course` / `inspect_lesson` / `inspect_track` / `inspect_problem` | `GET` дерева курса, урока, трека, задачи |
| `preview_markdown` | `POST /authoring/markdown/preview` |
| `preview_course_plan` / `apply_course_plan` | `POST /authoring/course-plans/{preview,apply}` |
| `preview_practice_set_plan` / `apply_practice_set_plan` | `POST /authoring/course-plans/practice-set/{preview,apply}` |
| `preview_track_plan` / `apply_track_plan` | `POST /authoring/track-plans/{preview,apply}` |
| `preview_algorithm_plan` / `apply_algorithm_plan` | `POST /authoring/algorithm-plans/{preview,apply}` (`?validate_templates=true`) |

`preview` прогоняет тот же код, что и `apply`, и откатывает транзакцию, поэтому diff
совпадает с реальным результатом. Ответ любого плана одинаков: `valid`, счётчики
`created/updated/unchanged`, `changes[]` (`action`, `kind`, `path`, `entity_id`,
`fields`), `issues[]` (`severity`, `path`, `code`, `message`) и `warnings[]`. План с
ошибками `apply` отклоняет целиком с кодом `invalid_plan` и теми же `details.issues`.

Сервис не удаляет и не публикует материалы. Сущности сопоставляются по стабильным
`slug` (наборы практики — по `title`, вопросы и тест-кейсы — по `position`, шаблоны —
по `language`); повторное применение одинакового плана ничего не меняет. Неуказанные
в плане сущности сохраняются. План курса сохраняет упомянутые курс, модули, уроки и
тесты черновиками, поэтому опубликованные снимаются с публикации (об этом есть
предупреждение). План набора практики и план трека статусы не трогают.

Рекомендуемый порядок для агента:

1. `list_*`, затем `inspect_*` для сущностей, которые будут меняться.
2. `preview_*_plan`: исправить все `issues` с `severity=error` и повторить.
3. Показать преподавателю `changes` и `warnings`.
4. `apply_*_plan` с тем же планом.

## Подключение

Удалённый Streamable HTTP endpoint:

```text
https://mcp.example.com/mcp
```

Сервер использует browser OAuth самого Tramplin. Пользователь входит в обычный
аккаунт Tramplin и подтверждает доступ на странице Tramplin; GitHub и Яндекс
остаются только способами входа в основной продукт. Студент или неактивный
пользователь получит отказ. Доступ разрешён преподавателям и администраторам.

Tramplin хранит authorization grants и OAuth access/refresh-токены в PostgreSQL.
В базе находятся только SHA-256-хэши токенов; authorization code одноразовый,
refresh ротируется при каждом обмене, а отозванные токены помечаются отдельно.
Обычный access JWT веб-интерфейса MCP не принимает.

### Codex CLI и IDE

Добавьте в `~/.codex/config.toml` или в `.codex/config.toml` доверенного проекта:

```toml
[mcp_servers.tramplin]
url = "https://mcp.example.com/mcp"
auth = "oauth"
```

Выполните `codex mcp login tramplin`, подтвердите доступ в браузере, затем
проверьте подключение командами `codex mcp list` и `/mcp` внутри Codex.

### Claude Code

```bash
claude mcp add --transport http --scope user tramplin https://mcp.example.com/mcp
claude mcp get tramplin
```

Откройте `/mcp` внутри Claude Code и выберите Tramplin — браузер откроет OAuth
вход. Для общей конфигурации проекта замените `--scope user` на `--scope project`.

### Другой MCP-клиент

Для клиента с JSON-конфигурацией используйте Streamable HTTP:

```json
{
  "mcpServers": {
    "tramplin": {
      "type": "http",
      "url": "https://mcp.example.com/mcp"
    }
  }
}
```

Клиент должен поддерживать OAuth discovery, Dynamic Client Registration и PKCE.

## Локальный запуск

Нужны Python 3.14 и `uv`:

```bash
cp .env.example .env.runtime
# Для stdio можно временно передать короткий access JWT локального пользователя.
make install
TRAMPLIN_MCP_TRANSPORT=stdio make run
```

Пример локального stdio-сервера:

```json
{
  "mcpServers": {
    "tramplin": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/mcp-server",
        "run",
        "tramplin-mcp"
      ],
      "env": {
        "TRAMPLIN_MCP_TRANSPORT": "stdio",
        "TRAMPLIN_API_URL": "http://localhost:8000/api/v1",
        "TRAMPLIN_API_TOKEN": "short-lived-access-jwt"
      }
    }
  }
}
```

Для локального HTTP:

```bash
cp .env.example .env.runtime
docker network create tramplin-edge 2>/dev/null || true
docker compose --env-file .env.runtime up -d --build --wait
```

Endpoint будет на `http://127.0.0.1:8001/mcp`, healthcheck — на
`http://127.0.0.1:8001/health`.

## Деплой и CI/CD

GitLab pipeline выполняет Ruff, форматирование, mypy, gitleaks, Semgrep и Trivy;
для веток `stage` и `main` собирает immutable image, разворачивает его по SSH и
запускает Nuclei после деплоя.

Protected CI/CD variables:

- `SERVER_IP`, `SSH_PORT`, `SSH_USER`, `SSH_PRIVATE_KEY`;
- `STAGE_ENV` и `PROD_ENV` типа File;
- `STAGE_URL` и `PROD_URL`, например `https://mcp-stage.example.com` и
  `https://mcp.example.com`.

Содержимое environment file:

```dotenv
TRAMPLIN_API_URL=http://tramplin-stage-api:8000/api/v1
TRAMPLIN_API_TIMEOUT=30
TRAMPLIN_MCP_TRANSPORT=http
TRAMPLIN_MCP_HOST=0.0.0.0
TRAMPLIN_MCP_PORT=8001
TRAMPLIN_MCP_PUBLIC_URL=https://mcp-stage.example.com
TRAMPLIN_OAUTH_BASE_URL=https://api.staging.example.com/api/v1
TRAMPLIN_OAUTH_CLIENT_ID=tramplin-fastmcp
TRAMPLIN_OAUTH_CLIENT_SECRET=
TRAMPLIN_MCP_JWT_SIGNING_KEY=
```

Для production замените backend alias на `tramplin-prod-api`. Общая
инфраструктура должна быть поднята первой и создать external network
`tramplin-edge`. В её `.env` настройте `MCP_DOMAIN`, `MCP_STAGE_DOMAIN` и DNS
A/AAAA записи обоих доменов на сервер.

Для каждого окружения задайте backend-настройки с теми же client credentials:

```dotenv
MCP_OAUTH_CLIENT_ID=tramplin-fastmcp
MCP_OAUTH_CLIENT_SECRET=<случайный-секрет>
MCP_OAUTH_REDIRECT_URI=https://<mcp-domain>/auth/callback
```

`TRAMPLIN_OAUTH_CLIENT_SECRET` и `MCP_OAUTH_CLIENT_SECRET` должны совпадать. Это
стандартные credentials конфиденциального OAuth-клиента между двумя сервисами;
они не передаются пользователю, Codex или Claude Code. Отдельный вручную
создаваемый MCP-токен и дополнительный service secret не используются.

Локальные проверки:

```bash
make check
docker compose --env-file .env.example config --quiet
```
