import pytest

from astra.exporter import export_job
from astra.exporter.__main__ import main


def test_exporter_is_not_ported() -> None:
    with pytest.raises(NotImplementedError, match="exporter"):
        export_job(1, 2)
    assert main(["--check"]) == 0
