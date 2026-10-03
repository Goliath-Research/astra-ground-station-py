"""Job poller that loads ``.DAT`` files into ``testlog`` tables.

Replaces ``AstraLogExporter`` and its desktop twin. Table creation and
``COPY`` are phase 5.
"""


def export_job(test_id: int, packet_id: int) -> None:
    """Export one job.

    Raises:
        NotImplementedError: always, until phase 5.
    """
    del test_id, packet_id
    raise NotImplementedError("log exporter is not ported")
