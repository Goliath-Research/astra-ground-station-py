from uuid import UUID

import pytest

from astra.exporter import ExportJob, export_job
from astra.exporter.__main__ import main


def test_exporter_is_not_ported() -> None:
    with pytest.raises(NotImplementedError, match="exporter"):
        export_job(1, 2)
    assert main(["--check"]) == 0


def test_job_key_is_packet_id() -> None:
    job = ExportJob(test_id=1, packet_id=2, intf_id=UUID(int=0))
    assert (job.test_id, job.packet_id) == (1, 2)
    assert isinstance(job.intf_id, UUID)
