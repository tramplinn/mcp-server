import os

import pytest

from tramplin_mcp.config import Settings


@pytest.fixture(autouse=True)
def isolate_settings_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Production CI variables must not change unit-test settings."""
    names = {
        str(field.validation_alias or name).upper() for name, field in Settings.model_fields.items()
    }
    for name in os.environ:
        if name.upper() in names:
            monkeypatch.delenv(name)
