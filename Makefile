.PHONY: install run check lock

install:
	uv sync

run:
	uv run tramplin-mcp

check:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy src

lock:
	uv lock

