from datetime import timedelta

import pytest

from backdate.derive import registry
from backdate.derive.worker import backoff
from server.env import ConfigError, env_bool, env_int, env_list


def test_env_int(monkeypatch):
    monkeypatch.setenv("X", "42")
    assert env_int("X", 1) == 42
    monkeypatch.setenv("X", "")
    assert env_int("X", 1) == 1
    monkeypatch.setenv("X", "forty")
    with pytest.raises(ConfigError):
        env_int("X", 1)


@pytest.mark.parametrize(
    ("raw", "want"), [("1", True), ("YES", True), ("off", False), ("0", False)]
)
def test_env_bool(monkeypatch, raw, want):
    monkeypatch.setenv("B", raw)
    assert env_bool("B", not want) is want


def test_env_bool_rejects_junk(monkeypatch):
    monkeypatch.setenv("B", "maybe")
    with pytest.raises(ConfigError):
        env_bool("B", False)


def test_env_list(monkeypatch):
    monkeypatch.setenv("L", " a, b ,,c ")
    assert env_list("L", []) == ["a", "b", "c"]
    monkeypatch.delenv("L")
    assert env_list("L", ["d"]) == ["d"]


def test_backoff_doubles_and_caps():
    assert [backoff(n).total_seconds() for n in (1, 2, 3, 4)] == [1, 2, 4, 8]
    assert backoff(50) == timedelta(minutes=5)


def test_registry_has_payroll():
    names = [d.name for d in registry.all_derivations()]
    assert "payroll.gross" in names
    assert registry.get("payroll.gross").description.startswith("Gross pay")


def test_registry_rejects_a_second_function_under_one_name():
    @registry.derivation("test.dup")
    def one(ctx, key):
        return 1

    with pytest.raises(registry.DuplicateDerivation):

        @registry.derivation("test.dup")
        def two(ctx, key):
            return 2


def test_unknown_derivation():
    with pytest.raises(registry.UnknownDerivation):
        registry.get("nope")
