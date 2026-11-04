> Production в k3s: [манифесты, настройки и порядок запуска](k8s/).

# Tramplin MCP

A FastMCP server that lets AI agents create course content. Course content is accessed through Tramplin's authoring API on behalf of a
teacher or admin. OAuth state is stored in a separate PostgreSQL database.

## Tools

The server is a thin wrapper. Validation, diffs, and applying changes happen in
the backend; MCP forwards calls and tells the agent how to use them.

| Tool | Backend endpoint |
| --- | --- |
| `list_courses` / `list_tracks` / `list_problems` | `GET /authoring/{courses,tracks,algorithms/problems}/index` |
| `inspect_course` / `inspect_lesson` / `inspect_track` / `inspect_problem` | `GET` the full tree of an entity |
| `preview_markdown` | `POST /authoring/markdown/preview` |
| `preview_course_plan` / `apply_course_plan` | `POST /authoring/course-plans/{preview,apply}` |
| `preview_practice_set_plan` / `apply_practice_set_plan` | `POST /authoring/course-plans/practice-set/{preview,apply}` |
| `preview_track_plan` / `apply_track_plan` | `POST /authoring/track-plans/{preview,apply}` |
| `preview_algorithm_plan` / `apply_algorithm_plan` | `POST /authoring/algorithm-plans/{preview,apply}` (`?validate_templates=true`) |

`preview` runs the same code as `apply` and rolls back, so the diff is exactly
what you'll get. Responses include `valid`, created/updated/unchanged counts,
`changes`, `issues`, and `warnings`. If a plan has errors, `apply` rejects it
entirely.

Nothing gets deleted or published. Entities are matched by `slug` (practice sets
by `title`, questions and test cases by `position`, templates by `language`), so
applying the same plan twice is safe, and anything not in the plan stays as is.
A course plan saves what it touches as drafts, which unpublishes them — you'll get
a warning.

Suggested flow for an agent:

1. `list_*`, then `inspect_*` what you're about to change.
2. `preview_*_plan`, fix every `severity=error` issue, repeat.
3. Show the teacher the changes and warnings.
4. `apply_*_plan` with the same plan.

## Connecting

Endpoint (Streamable HTTP):

```text
https://mcp.tramplinn.tech/mcp
```

You sign in with your Tramplin account in the browser and approve access. Only
teachers and admins get through.

Tokens are stored in PostgreSQL as SHA-256 hashes. Authorization codes are
single-use, refresh tokens rotate on every use, and the web app's regular JWT
doesn't work here.

### Codex

Add to `~/.codex/config.toml` or a trusted project's `.codex/config.toml`:

```toml
[mcp_servers.tramplin]
url = "https://mcp.tramplinn.tech/mcp"
auth = "oauth"
```

Run `codex mcp login tramplin`, approve in the browser, and check with
`codex mcp list` or `/mcp`.

### Claude Code

```bash
claude mcp add --transport http --scope user tramplin https://mcp.tramplinn.tech/mcp
claude mcp get tramplin
```

Then open `/mcp`, pick Tramplin, and sign in. Use `--scope project` to share the
config with your project.

### Other clients

```json
{
  "mcpServers": {
    "tramplin": {
      "type": "http",
      "url": "https://mcp.tramplinn.tech/mcp"
    }
  }
}
```

The client needs OAuth discovery, Dynamic Client Registration, and PKCE.

## Running locally

You need Python 3.14 and `uv`. Over stdio, you can pass a short-lived JWT of a
local user:

```bash
cp .env.example .env
make install
TRAMPLIN_MCP_TRANSPORT=stdio make run
```

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

For local HTTP, configure the OAuth credentials, signing key, PostgreSQL URL
and Fernet key in `.env`, then run `TRAMPLIN_MCP_TRANSPORT=http make run`.
The endpoint is `http://127.0.0.1:8001/mcp`, health is `/health`.

## Deployment

Production configuration and deployment: [k8s/README.md](k8s/).
Infra owns the separate OAuth database and role. The backend owns the shared
OAuth client secret; MCP owns its signing and storage encryption keys.

Checks: `make check`.
