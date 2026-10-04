"""Quoting rules shared with the Delphi CSV writer."""

from astra.web.csv_text import csv_document


def test_csv_quotes_spaces_and_writes_booleans_as_digits() -> None:
    document = csv_document(
        ("name", "note", "override", "insequence"),
        [
            {
                "name": "flags",
                "note": 'has space;and "quote"',
                "override": True,
                "insequence": False,
            }
        ],
    )
    assert document == 'name;note;override;insequence\r\nflags;"has space;and ""quote""";1;0\r\n'
