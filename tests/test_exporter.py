from astra_ground_station.exporter import EXPORT_HEADER, export_rows


def test_export_placeholder_ignores_rows() -> None:
    assert export_rows([]) == EXPORT_HEADER
    assert export_rows([{"id": 1}]) == EXPORT_HEADER
