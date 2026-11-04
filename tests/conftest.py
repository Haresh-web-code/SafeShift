import pytest
from fastapi.testclient import TestClient

from app import main
from app.config import Settings, get_settings
from app.main import app


@pytest.fixture
def client(monkeypatch):
    settings = Settings(
        _env_file=None,
        app_name="SafeShift",
        environment="test",
    )
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
