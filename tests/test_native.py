import pytest

from astra.native import active_backend


def test_default_backend_is_python(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ASTRA_NATIVE_BACKEND", raising=False)
    assert active_backend() == "python"


def test_mojo_backend_is_not_built(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASTRA_NATIVE_BACKEND", "mojo")
    with pytest.raises(RuntimeError, match="pack_records"):
        active_backend()
