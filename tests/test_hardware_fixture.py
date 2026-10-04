"""Real Access pinout and configurator boards from the migrated database.

``tests/fixtures/hardware/real_boards.json`` is a credential-free extract.
EntityDAC tables are not in it. ``Servers`` rows are not in it.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from astra.db.connection import connect, database_url_from_env
from astra.db.schema_loader import apply_schema
from astra.web import create_app
from astra.web.settings import WebSettings

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "hardware" / "real_boards.json"
_TOKEN = "operator-token-test"
_STAGE_LINKS = {"S1Tester1": 153, "S2Tester1": 132, "S1EngineTester1": 55}
_EM_HARDWARE = 18
_EM_BOARD_A1 = 6333
_R2L_NODE = 7
_PACKET_ID = 910733

_IDENTITY_TABLES = (
    "stage",
    "area_list",
    "areas",
    "board",
    "names",
    "connectors",
    "links",
    "link_type",
    "connector_gender",
    "vendors",
    "treeversions",
    "connections",
    "vartypes",
    "fields",
)


def load_boards() -> dict[str, Any]:
    """Return the fixture. It has no ``servers`` key."""
    loaded: object = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise AssertionError("hardware fixture was not an object")
    if "servers" in loaded:
        raise AssertionError("hardware fixture must not include servers")
    return loaded


def test_real_board_fixture_joins_and_counts() -> None:
    boards = load_boards()
    counts = boards["_meta"]["row_counts"]
    assert counts["stage"] == 3
    assert counts["board"] == 8
    assert counts["links"] == 340
    assert counts["treeversions"] == 88
    assert counts["connections"] == 324
    assert [row["stage"] for row in boards["stage"]] == [
        "S1Tester1",
        "S2Tester1",
        "S1EngineTester1",
    ]
    assert {row["board_connector"] for row in boards["board"]} == {
        "M",
        "A1",
        "A2",
        "V1",
        "V2",
        "S1",
        "S2",
        "P",
    }

    stages = {row["id"]: row["stage"] for row in boards["stage"]}
    area_names = {row["id"]: row["area_name"] for row in boards["area_list"]}
    areas = {row["id"]: row for row in boards["areas"]}
    link_counts: Counter[str] = Counter()
    for link in boards["links"]:
        area = areas[link["area_id"]]
        link_counts[stages[area["stage_id"]]] += 1
        assert area["area_id"] in area_names
    assert dict(link_counts) == _STAGE_LINKS
    common = [
        row["id"]
        for row in boards["areas"]
        if stages[row["stage_id"]] == "S1Tester1" and area_names[row["area_id"]] == "C"
    ]
    assert common == [1, 11]

    nodes = {row["id"]: row for row in boards["treeversions"]}
    assert all(
        row["parentid"] is None or row["parentid"] in nodes for row in boards["treeversions"]
    )
    link_types = {row["id"] for row in boards["linktypes"]}
    connector_ids = {row["id"] for row in boards["connectors"]}
    board_ids = {row["id"] for row in nodes.values() if row["iconid"] == 10}
    for pin in boards["connections"]:
        assert pin["boardid"] in board_ids
        assert pin["linktypeid"] in link_types
        assert pin["connectorid"] is None or pin["connectorid"] in connector_ids
    pinned = {pin["boardid"] for pin in boards["connections"]}
    assert len(pinned) == 36


def _ids(rows: list[dict[str, Any]]) -> list[int]:
    found: list[int] = []
    for row in rows:
        value = row["id"]
        if not isinstance(value, int):
            raise AssertionError("fixture id was not an int")
        found.append(value)
    return found


def _rows(boards: dict[str, Any], name: str) -> list[dict[str, Any]]:
    rows = boards[name]
    if not isinstance(rows, list):
        raise AssertionError(f"{name} was not a list")
    return rows


def _insert(conn: psycopg.Connection[Any], sql: str, rows: list[tuple[Any, ...]]) -> None:
    if not rows:
        return
    with conn.cursor() as cur:
        cur.executemany(sql, rows)


def _ordered_nodes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {row["id"]: row for row in rows}
    ordered: list[dict[str, Any]] = []
    seen: set[int] = set()

    def visit(row: dict[str, Any]) -> None:
        node_id = row["id"]
        if not isinstance(node_id, int) or node_id in seen:
            return
        parent = row["parentid"]
        if isinstance(parent, int):
            visit(by_id[parent])
        seen.add(node_id)
        ordered.append(row)

    for row in rows:
        visit(row)
    return ordered


def _bump(conn: psycopg.Connection[Any], table: str) -> None:
    row = conn.execute(f"SELECT MAX(id) FROM {table}").fetchone()
    if row is not None and isinstance(row[0], int):
        conn.execute(
            "SELECT identity_insert_bump(%s, 'id', %s)",
            (f"config.{table}", row[0]),
        )


def _load(conn: psycopg.Connection[Any], boards: dict[str, Any]) -> None:
    _insert(
        conn,
        "INSERT INTO stage (id, stage, stage_order) VALUES (%s, %s, %s)",
        [(row["id"], row["stage"], row["stage_order"]) for row in _rows(boards, "stage")],
    )
    _insert(
        conn,
        """
        INSERT INTO area_list (id, area_name, area_description, area_order)
        VALUES (%s, %s, %s, %s)
        """,
        [
            (row["id"], row["area_name"], row["area_description"], row["area_order"])
            for row in _rows(boards, "area_list")
        ],
    )
    _insert(
        conn,
        "INSERT INTO connector_gender (id, gender) VALUES (%s, %s)",
        [(row["id"], row["gender"]) for row in _rows(boards, "connector_gender")],
    )
    _insert(
        conn,
        "INSERT INTO vendors (id, vendor_name) VALUES (%s, %s)",
        [(row["id"], row["vendor_name"]) for row in _rows(boards, "vendors")],
    )
    _insert(
        conn,
        "INSERT INTO link_type (id, link_type, description) VALUES (%s, %s, %s)",
        [(row["id"], row["link_type"], row["description"]) for row in _rows(boards, "link_type")],
    )
    _insert(
        conn,
        "INSERT INTO linktypes (id, name, description) VALUES (%s, %s, %s)",
        [(row["id"], row["name"], row["description"]) for row in _rows(boards, "linktypes")],
    )
    _insert(
        conn,
        """
        INSERT INTO areas (id, area_id, stage_id, area_multiple, ordering)
        VALUES (%s, %s, %s, %s, %s)
        """,
        [
            (row["id"], row["area_id"], row["stage_id"], row["area_multiple"], row["ordering"])
            for row in _rows(boards, "areas")
        ],
    )
    _insert(
        conn,
        'INSERT INTO board (id, board_connector, "order") VALUES (%s, %s, %s)',
        [(row["id"], row["board_connector"], row["order"]) for row in _rows(boards, "board")],
    )
    _insert(
        conn,
        """
        INSERT INTO names (id, link_description, short_name, internal_name)
        VALUES (%s, %s, %s, %s)
        """,
        [
            (row["id"], row["link_description"], row["short_name"], row["internal_name"])
            for row in _rows(boards, "names")
        ],
    )
    _insert(
        conn,
        """
        INSERT INTO connectors (
            id, "conn part no", vendor_id, circuits, gender_id, rows, description
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        [
            (
                row["id"],
                row["conn part no"],
                row["vendor_id"],
                row["circuits"],
                row["gender_id"],
                row["rows"],
                row["description"],
            )
            for row in _rows(boards, "connectors")
        ],
    )
    _insert(
        conn,
        """
        INSERT INTO links (
            id, names_id, c2_first_pin, c2_type_id, board_id, c1_first_pin,
            c1_type_id, link_type_id, area_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        [
            (
                row["id"],
                row["names_id"],
                row["c2_first_pin"],
                row["c2_type_id"],
                row["board_id"],
                row["c1_first_pin"],
                row["c1_type_id"],
                row["link_type_id"],
                row["area_id"],
            )
            for row in _rows(boards, "links")
        ],
    )
    _insert(
        conn,
        """
        INSERT INTO treeversions (id, name, parentid, iconid, seq)
        VALUES (%s, %s, %s, %s, %s)
        """,
        [
            (row["id"], row["name"], row["parentid"], row["iconid"], row["seq"])
            for row in _ordered_nodes(_rows(boards, "treeversions"))
        ],
    )
    _insert(
        conn,
        """
        INSERT INTO connections (
            id, boardid, firstpin, linktypeid, connectorid, seq, description, shortname
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        [
            (
                row["id"],
                row["boardid"],
                row["firstpin"],
                row["linktypeid"],
                row["connectorid"],
                row["seq"],
                row["description"],
                row["shortname"],
            )
            for row in _rows(boards, "connections")
        ],
    )
    for table in _IDENTITY_TABLES:
        _bump(conn, table)


def _unload(conn: psycopg.Connection[Any], boards: dict[str, Any]) -> None:
    nodes = _rows(boards, "treeversions")
    tree_ids = _ids(nodes)
    stage_ids = [row["id"] for row in nodes if row["iconid"] == 2]
    board_ids = [row["id"] for row in nodes if row["iconid"] == 10]
    connection_ids = _ids(_rows(boards, "connections"))
    linktype_ids = _ids(_rows(boards, "linktypes"))
    connector_ids = _ids(_rows(boards, "connectors"))
    conn.execute(
        """
        UPDATE fields
        SET connectionid = NULL
        WHERE connectionid IN (
            SELECT id FROM connections
            WHERE id = ANY(%s) OR boardid = ANY(%s)
        )
        """,
        (connection_ids, board_ids),
    )
    conn.execute("DELETE FROM connections WHERE id = ANY(%s)", (connection_ids,))
    conn.execute(
        """
        WITH RECURSIVE nodes AS (
            SELECT id FROM treeversions WHERE id = ANY(%s)
            UNION ALL
            SELECT child.id
            FROM treeversions AS child
            INNER JOIN nodes ON child.parentid = nodes.id
        )
        DELETE FROM devices WHERE smartnodeid IN (SELECT id FROM nodes)
        """,
        (tree_ids,),
    )
    for stage_id in stage_ids:
        conn.execute("SELECT spdelete(%s)", (stage_id,))
    conn.execute(
        """
        DELETE FROM treeversions
        WHERE id = 1 AND iconid = 1 AND name = 'Vehicle'
          AND NOT EXISTS (SELECT 1 FROM treeversions AS child WHERE child.parentid = 1)
        """
    )
    conn.execute("DELETE FROM links WHERE id = ANY(%s)", (_ids(_rows(boards, "links")),))
    conn.execute("DELETE FROM areas WHERE id = ANY(%s)", (_ids(_rows(boards, "areas")),))
    conn.execute("DELETE FROM board WHERE id = ANY(%s)", (_ids(_rows(boards, "board")),))
    conn.execute("DELETE FROM names WHERE id = ANY(%s)", (_ids(_rows(boards, "names")),))
    conn.execute(
        "UPDATE connections SET connectorid = NULL WHERE connectorid = ANY(%s)",
        (connector_ids,),
    )
    conn.execute("DELETE FROM connectors WHERE id = ANY(%s)", (connector_ids,))
    conn.execute("DELETE FROM area_list WHERE id = ANY(%s)", (_ids(_rows(boards, "area_list")),))
    conn.execute("DELETE FROM stage WHERE id = ANY(%s)", (_ids(_rows(boards, "stage")),))
    conn.execute("DELETE FROM link_type WHERE id = ANY(%s)", (_ids(_rows(boards, "link_type")),))
    conn.execute(
        "DELETE FROM connector_gender WHERE id = ANY(%s)",
        (_ids(_rows(boards, "connector_gender")),),
    )
    conn.execute("DELETE FROM vendors WHERE id = ANY(%s)", (_ids(_rows(boards, "vendors")),))
    conn.execute(
        "UPDATE connections SET linktypeid = NULL WHERE linktypeid = ANY(%s)",
        (linktype_ids,),
    )
    conn.execute("DELETE FROM linktypes WHERE id = ANY(%s)", (linktype_ids,))


def _function_count(url: str) -> int:
    with psycopg.connect(url) as conn:
        row = conn.execute(
            """
            SELECT COUNT(*)
            FROM pg_proc AS p
            JOIN pg_namespace AS n ON n.oid = p.pronamespace
            WHERE n.nspname = 'config' AND p.proname = 'spcalcvartypesizes'
            """
        ).fetchone()
    if row is None or not isinstance(row[0], int):
        return 0
    return row[0]


def _ensure_schema(url: str) -> None:
    if _function_count(url) < 1:
        schema_dir = Path(__file__).resolve().parents[1] / "database" / "schema"
        apply_schema(url, schema_dir)
    assert _function_count(url) == 1


def _ensure_u8(url: str) -> None:
    with connect(url) as conn:
        conn.execute(
            """
            INSERT INTO vartypes (id, name, scopeid, encsize, decsize)
            VALUES (2, 'u8', 1, 8, 8)
            ON CONFLICT (id) DO NOTHING
            """
        )
        conn.execute(
            """
            UPDATE vartypes
            SET encsize = 8, decsize = 8
            WHERE id = 2 AND encsize IS NULL
            """
        )
        conn.execute("SELECT identity_insert_bump('config.vartypes', 'id', 2)")
        conn.commit()


def _pin_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row["first_pin"],
        row["short_name"],
        row["description"],
        row["link_type_id"],
        row["connector_id"],
    )


@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL is not set")
def test_real_boards_drive_the_editor_tree_wiring_and_opcua() -> None:
    url = database_url_from_env()
    _ensure_schema(url)
    boards = load_boards()
    with connect(url) as conn:
        _unload(conn, boards)
        _load(conn, boards)
        conn.commit()
    try:
        _ensure_u8(url)
        app = create_app(
            WebSettings(
                database_url=url,
                token=_TOKEN,
                database_error=None,
                token_error=None,
            )
        )
        with TestClient(app) as client:
            client.headers["Authorization"] = f"Bearer {_TOKEN}"
            _check_editor(client, boards)
        with connect(url) as conn:
            _check_pinout(conn)
            conn.rollback()
    finally:
        with connect(url) as conn:
            _unload(conn, boards)
            conn.commit()


def _check_pinout(conn: psycopg.Connection[Any]) -> None:
    rows = conn.execute(
        """
        SELECT s.stage, COUNT(*)
        FROM links AS l
        JOIN areas AS a ON a.id = l.area_id
        JOIN stage AS s ON s.id = a.stage_id
        GROUP BY s.stage
        ORDER BY s.stage
        """
    ).fetchall()
    assert {row[0]: row[1] for row in rows} == _STAGE_LINKS


def _check_editor(client: TestClient, boards: dict[str, Any]) -> None:
    tree = {row["id"]: row for row in client.get("/api/tree").json()}
    assert tree[1]["name"] == "Vehicle" and tree[1]["icon_id"] == 1
    assert tree[2]["name"] == "Stage 1" and tree[2]["parent_id"] == 1
    assert tree[5]["name"] == "eMaster" and tree[5]["icon_id"] == 5
    assert tree[_EM_HARDWARE]["name"] == "Hardware"
    assert tree[6332]["name"] == "P" and tree[6332]["parent_id"] == _EM_HARDWARE
    assert tree[_EM_BOARD_A1]["name"] == "A1" and tree[_EM_BOARD_A1]["icon_id"] == 10
    areas = [row["name"] for row in tree.values() if row["parent_id"] == _EM_HARDWARE]
    assert areas == ["P", "I", "C", "E"]

    link_types = {row["id"]: row for row in client.get("/api/link-types").json()}
    for row in boards["linktypes"]:
        assert link_types[row["id"]]["name"] == row["name"]
        assert link_types[row["id"]]["description"] == row["description"]
    connectors = {row["id"]: row for row in client.get("/api/connectors").json()}
    pico = next(row for row in boards["connectors"] if row["id"] == 7)
    assert connectors[7]["part_no"] == pico["conn part no"]
    assert "Pico-Clasp" in connectors[7]["description"]

    expected = [row for row in boards["connections"] if row["boardid"] == _EM_BOARD_A1]
    listed = client.get(f"/api/boards/{_EM_BOARD_A1}/connections")
    assert listed.status_code == 200
    pins = listed.json()
    assert [_pin_key(row) for row in pins] == [
        (
            row["firstpin"],
            row["shortname"],
            row["description"],
            row["linktypeid"],
            row["connectorid"],
        )
        for row in expected
    ]
    tor = next(row for row in pins if row["short_name"] == "TOR1")
    assert tor["description"] == "Oxi Tank Level Temp #1"
    assert tor["first_pin"] == 1
    assert tor["link_type_name"] == "I"

    wiring = client.get(f"/api/nodes/{_EM_HARDWARE}/wiring")
    assert wiring.status_code == 200
    printed = wiring.json()
    under_hardware = {
        row["id"]
        for row in boards["treeversions"]
        if row["iconid"] == 10 and _under(boards, row["id"], _EM_HARDWARE)
    }
    assert len(printed) == sum(
        1 for row in boards["connections"] if row["boardid"] in under_hardware
    )
    printed_tor = next(row for row in printed if row["id"] == tor["id"])
    assert printed_tor["area"] == "P"
    assert printed_tor["board"] == "A1"
    assert printed_tor["part_no"] == pico["conn part no"]
    assert printed_tor["short_name"] == "TOR1"
    smart = client.get("/api/nodes/5/wiring")
    assert smart.status_code == 400

    copied = client.post(f"/api/tree/{_EM_BOARD_A1}/duplicate")
    assert copied.status_code == 201
    copy = copied.json()
    assert copy["name"] == "A1"
    assert copy["parent_id"] == 6332
    assert copy["icon_id"] == 10
    clone = client.get(f"/api/boards/{copy['id']}/connections")
    assert clone.status_code == 200
    assert [_pin_key(row) for row in clone.json()] == [_pin_key(row) for row in pins]
    assert {row["id"] for row in clone.json()}.isdisjoint({row["id"] for row in pins})

    saved = client.put(
        f"/api/nodes/{_R2L_NODE}/packet",
        json={"packet_id": _PACKET_ID, "name": "R2L", "is_input": False},
    )
    assert saved.status_code == 200
    field = client.post(
        f"/api/vartypes/{saved.json()['var_type_id']}/fields",
        json={"name": "TOR1", "type_id": 2, "qty": 1},
    )
    assert field.status_code == 201
    linked = client.post(
        "/api/mappings",
        json={"field_id": field.json()["id"], "connection_id": tor["id"]},
    )
    assert linked.status_code == 200
    assert linked.json()["connection_id"] == tor["id"]
    opcua = client.get(f"/api/nodes/{_R2L_NODE}/exports/opcua")
    assert opcua.status_code == 200
    assert opcua.text == "AstraR2L/TOR1\n"


def _under(boards: dict[str, Any], node_id: int, ancestor_id: int) -> bool:
    nodes = {row["id"]: row for row in boards["treeversions"]}
    current: int | None = node_id
    while isinstance(current, int):
        if current == ancestor_id:
            return True
        parent = nodes[current]["parentid"]
        current = parent if isinstance(parent, int) else None
    return False
