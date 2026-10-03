import pytest

from astra.cli.device import main as device_main
from astra.cli.generate import main as generate_main
from astra.cli.tm_encoder import main as encoder_main


def test_cli_checks_exit_cleanly() -> None:
    assert generate_main(["--check"]) == 0
    assert device_main(["--check"]) == 0
    assert encoder_main(["--check"]) == 0


def test_generator_is_not_ported() -> None:
    with pytest.raises(NotImplementedError, match="generator"):
        generate_main(["stage", "node", "interface", "out.csv"])
