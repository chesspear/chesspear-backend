from app.settings import env_bool


def test_env_bool_accepts_explicit_true_and_false(monkeypatch):
    monkeypatch.setenv("TEST_FLAG", "yes")
    assert env_bool("TEST_FLAG", False) is True
    monkeypatch.setenv("TEST_FLAG", "OFF")
    assert env_bool("TEST_FLAG", True) is False


def test_env_bool_uses_safe_default_for_unrecognized_value(monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "treu")
    assert env_bool("AUTH_REQUIRED", True) is True
