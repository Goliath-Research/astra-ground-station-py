from astra_ground_station.web import WEB_STACK
from astra_ground_station.web.__main__ import main


def test_web_stack_is_undecided() -> None:
    assert WEB_STACK == "undecided"
    assert main(["--check"]) == 0
