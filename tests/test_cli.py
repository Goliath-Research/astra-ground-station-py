import pytest

from astra.cli.device import main as device_main
from astra.cli.generate import main as generate_main
from astra.cli.tm_encoder import main as encoder_main


def test_cli_checks_exit_cleanly() -> None:
    assert generate_main(["--check"]) == 0
    assert device_main(["--check"]) == 0
    assert encoder_main(["--check"]) == 0


def test_generator_requires_four_arguments() -> None:
    assert generate_main([]) == 2


def test_generator_reports_a_missing_database(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert generate_main(["stage", "node", "packet", "out.csv"]) == 1
    captured = capsys.readouterr()
    assert captured.err.strip() == "DATABASE_URL is not set"
    assert "postgresql://" not in captured.err
