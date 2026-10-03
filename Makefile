.PHONY: install run test check lock

install:
	uv sync

run:
	uv run tramplin-mcp

test:
	uv run pytest

check:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy src
	uv run pytest

lock:
	uv lock

