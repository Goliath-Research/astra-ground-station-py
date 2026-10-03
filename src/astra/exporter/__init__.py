"""Job poller that loads ``.DAT`` files into ``testlog`` tables.

Replaces ``AstraLogExporter`` and its desktop twin. Table creation and
``COPY`` are phase 5.

A job is identified by ``(test_id, packet_id)``, the primary key of
``config.jobs``. ``intf_id`` is a generated UUID and is not that key. The
loaded ``config.jobs.intfid`` column is still ``integer``; widening it is a
later schema change.
"""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ExportJob:
    """One job the exporter will claim.

    ``packet_id`` is ``config.jobs.packetid``. ``intf_id`` is generated
    elsewhere and is not used to select the row.
    """

    test_id: int
    packet_id: int
    intf_id: UUID


def export_job(test_id: int, packet_id: int) -> None:
    """Export the job whose key is ``(test_id, packet_id)``.

    Raises:
        NotImplementedError: always, until phase 5.
    """
    del test_id, packet_id
    raise NotImplementedError("log exporter is not ported")
