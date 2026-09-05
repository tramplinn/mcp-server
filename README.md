# Tramplin MCP

Отдельный FastMCP-сервис для заполнения учебных материалов агентами. Сервис не
ходит в базу данных: все чтения и записи выполняются через публичный authoring API
Tramplin от имени преподавателя или администратора.

## Что умеет

- просматривать список и полное дерево курсов;
- читать Markdown-исходник урока и проверять его рендеринг;
- валидировать курс, связи тестов и ответы на вопросы без записи;
- показывать декларативный diff перед изменением;
- атомарно и идемпотентно создавать или обновлять черновики курса, модулей,
  уроков, тестов и вопросов.

Сервис не удаляет и не публикует материалы. Сущности сопоставляются по стабильным
`slug`; повторное применение одинакового плана не создаёт дубликаты. Неуказанные
в плане сущности сохраняются и перемещаются в конец соответствующего списка.

Рекомендуемый порядок для агента:

1. `inspect_course` для существующего курса.
2. `validate_course_plan`.
3. `preview_course_plan` и подтверждение diff преподавателем.
4. `apply_course_plan`.

## Подключение

Удалённый Streamable HTTP endpoint:

```text
https://mcp.example.com/mcp
```

Сервер использует browser OAuth. GitHub-аккаунт должен быть заранее привязан к
существующему профилю Tramplin с ролью преподавателя или администратора. Студент,
неактивный пользователь или непривязанный GitHub-аккаунт получит отказ.

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
TRAMPLIN_MCP_GITHUB_CLIENT_ID=
TRAMPLIN_MCP_GITHUB_CLIENT_SECRET=
TRAMPLIN_MCP_JWT_SIGNING_KEY=
TRAMPLIN_MCP_SERVICE_SECRET=
```

Для production замените backend alias на `tramplin-prod-api`. Общая
инфраструктура должна быть поднята первой и создать external network
`tramplin-edge`. В её `.env` настройте `MCP_DOMAIN`, `MCP_STAGE_DOMAIN` и DNS
A/AAAA записи обоих доменов на сервер.

Создайте отдельное GitHub OAuth App для каждого окружения. Callback URL должен
быть строго `https://<mcp-domain>/auth/callback`. Значение
`TRAMPLIN_MCP_SERVICE_SECRET` должно совпадать с `MCP_SERVICE_SECRET` backend;
это серверный секрет и он никогда не передаётся пользователю или MCP-клиенту.

Локальные проверки:

```bash
make check
docker compose --env-file .env.example config --quiet
```
