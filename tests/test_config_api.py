"""Operator API against PostgreSQL. Skipped unless ``DATABASE_URL`` is set."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from astra.cli.generate import main as generate_main
from astra.db.connection import connect, database_url_from_env
from astra.db.schema_loader import apply_schema
from astra.web import create_app
from astra.web.settings import WebSettings

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL is not set",
)

_TOKEN = "operator-token-test"
_PASSWORD = "pw-do-not-log-91"
_PASSWORD_NEXT = "pw-replaced-value"


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


@pytest.fixture(scope="module")
def database_url() -> str:
    url = database_url_from_env()
    if _function_count(url) < 1:
        schema_dir = Path(__file__).resolve().parents[1] / "database" / "schema"
        apply_schema(url, schema_dir)
    assert _function_count(url) == 1
    return url


@pytest.fixture
def client(database_url: str) -> Iterator[TestClient]:
    app = create_app(
        WebSettings(
            database_url=database_url,
            token=_TOKEN,
            database_error=None,
            token_error=None,
        )
    )
    with TestClient(app) as test_client:
        test_client.headers["Authorization"] = f"Bearer {_TOKEN}"
        yield test_client


def _wipe_named_fixtures(url: str) -> None:
    with connect(url) as conn:
        vehicles = conn.execute("SELECT id FROM treeversions WHERE name = 'p6-vehicle'").fetchall()
        servers = conn.execute("SELECT id FROM servers WHERE name LIKE 'p6-%'").fetchall()
        conn.commit()
    for row in vehicles:
        vehicle_id = row[0]
        if isinstance(vehicle_id, int):
            _cleanup(url, vehicle_id, None)
    for row in servers:
        server_id = row[0]
        if isinstance(server_id, int):
            _cleanup(url, None, server_id)


def _cleanup(url: str, root_id: int | None, server_id: int | None) -> None:
    with connect(url) as conn:
        if server_id is not None:
            conn.execute(
                "DELETE FROM jobs WHERE testid IN (SELECT id FROM tests WHERE serverid = %s)",
                (server_id,),
            )
            conn.execute("DELETE FROM tests WHERE serverid = %s", (server_id,))
            conn.execute("DELETE FROM servers WHERE id = %s", (server_id,))
        if root_id is not None:
            conn.execute(
                """
                WITH RECURSIVE nodes AS (
                    SELECT id FROM treeversions WHERE id = %s
                    UNION ALL
                    SELECT child.id
                    FROM treeversions AS child
                    INNER JOIN nodes ON child.parentid = nodes.id
                )
                DELETE FROM devices WHERE smartnodeid IN (SELECT id FROM nodes)
                """,
                (root_id,),
            )
            while True:
                child = conn.execute(
                    "SELECT id FROM treeversions WHERE parentid = %s ORDER BY id",
                    (root_id,),
                ).fetchone()
                if child is None:
                    break
                conn.execute("SELECT spdelete(%s)", (child[0],))
            conn.execute("DELETE FROM treeversions WHERE id = %s", (root_id,))
        conn.commit()


def test_tree_packet_fields_sizes_and_stream(
    client: TestClient,
    database_url: str,
) -> None:
    root_id: int | None = None
    _wipe_named_fixtures(database_url)
    try:
        vehicle = client.post("/api/tree", json={"name": "p6-vehicle", "icon_id": 1})
        assert vehicle.status_code == 201
        root_id = vehicle.json()["id"]
        stage = client.post(
            "/api/tree",
            json={"name": "p6-stage", "parent_id": root_id, "icon_id": 2},
        )
        assert stage.status_code == 201
        stage_id = stage.json()["id"]
        other = client.post(
            "/api/tree",
            json={"name": "p6-stage-b", "parent_id": root_id, "icon_id": 2, "seq": 2},
        )
        assert other.status_code == 201
        moved = client.patch(f"/api/tree/{other.json()['id']}", json={"seq": 1})
        assert moved.status_code == 200
        siblings = [row for row in client.get("/api/tree").json() if row["parent_id"] == root_id]
        assert siblings[0]["id"] == other.json()["id"]
        assert siblings[0]["seq"] == 20

        version = client.post(
            "/api/tree",
            json={"name": "p6-version", "parent_id": stage_id, "icon_id": 3},
        )
        release = client.post(
            "/api/tree",
            json={"name": "p6-release", "parent_id": version.json()["id"], "icon_id": 4},
        )
        smart = client.post(
            "/api/tree",
            json={"name": "p6-smart", "parent_id": release.json()["id"], "icon_id": 5},
        )
        assert smart.status_code == 201
        smart_id = smart.json()["id"]
        packet_node = client.post(
            "/api/tree",
            json={"name": "p6-r2l", "parent_id": smart_id, "icon_id": 7},
        )
        assert packet_node.status_code == 201
        node_id = packet_node.json()["id"]

        with connect(database_url) as conn:
            conn.execute(
                """
                INSERT INTO vartypes (id, name, scopeid, encsize, decsize)
                VALUES (2, 'u8', %s, 8, 8)
                ON CONFLICT (id) DO NOTHING
                """,
                (root_id,),
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
        scalar_id = 2

        saved = client.put(
            f"/api/nodes/{node_id}/packet",
            json={"packet_id": 910061, "name": "p6-r2l", "is_input": False},
        )
        assert saved.status_code == 200
        body = saved.json()
        assert body["packet_id"] == 910061
        assert body["is_input"] is False
        assert "password" not in body
        var_type_id = body["var_type_id"]

        first = client.post(
            f"/api/vartypes/{var_type_id}/fields",
            json={"name": "bbb", "type_id": scalar_id, "qty": 1},
        )
        second = client.post(
            f"/api/vartypes/{var_type_id}/fields",
            json={"name": "aaa", "type_id": scalar_id, "qty": 3, "override": True, "seq": 1},
        )
        assert first.status_code == 201
        assert second.status_code == 201
        listed = client.get(f"/api/vartypes/{var_type_id}/fields")
        assert listed.status_code == 200
        assert [row["name"] for row in listed.json()] == ["bbb", "aaa"]

        with connect(database_url) as conn:
            procedure = conn.execute(
                "SELECT fieldname FROM spgetvartypefields(%s)",
                (var_type_id,),
            ).fetchall()
        assert [row[0] for row in procedure] == ["bbb", "aaa"]

        sized = client.post(f"/api/nodes/{node_id}/sizes")
        assert sized.status_code == 200
        record = next(row for row in sized.json() if row["id"] == var_type_id)
        # bbb is 8 bits. aaa is 3*8 bits plus one override bit.
        # spcalcvartypesizes then divides dec by 8 and ceilings enc/8.
        assert record["enc_size"] == 5
        assert record["dec_size"] == 5
        packet = client.get(f"/api/nodes/{node_id}/packet").json()
        assert packet["enc_size"] == 5
        assert packet["dec_size"] == 5

        sizes = client.get("/api/packets/input-sizes")
        assert sizes.status_code == 200
        assert any(row["packet_id"] == 910061 and row["enc_size"] == 5 for row in sizes.json())

        stream = client.put("/api/stream/910061", json={"send": True, "rate": 10})
        assert stream.status_code == 200
        assert stream.json() == {"packet_id": 910061, "send": True, "rate": 10}
        listed_stream = client.get("/api/stream").json()
        match = next(row for row in listed_stream if row["packet_id"] == 910061)
        assert match["send"] is True
        assert match["rate"] == 10
        with connect(database_url) as conn:
            columns = conn.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'config' AND table_name = 'packets'
                """
            ).fetchall()
        assert "send" not in {row[0] for row in columns}
        assert "rate" not in {row[0] for row in columns}

        fresh = create_app(
            WebSettings(
                database_url=database_url,
                token=_TOKEN,
                database_error=None,
                token_error=None,
            )
        )
        with TestClient(fresh) as other:
            other.headers["Authorization"] = f"Bearer {_TOKEN}"
            rows = other.get("/api/stream").json()
            again = next(row for row in rows if row["packet_id"] == 910061)
        assert again["send"] is False
        assert again["rate"] == 0

        device = client.post(
            "/api/devices",
            json={"name": "p6-device", "smart_node_id": smart_id, "ipv4": "127.0.0.1"},
        )
        assert device.status_code == 201
        assert device.json()["port"] == 2357
    finally:
        _cleanup(database_url, root_id, None)


def test_field_stores_description_sequence_and_transformation(
    client: TestClient,
    database_url: str,
) -> None:
    root_id: int | None = None
    transform_id: int | None = None
    _wipe_named_fixtures(database_url)
    try:
        vehicle = client.post("/api/tree", json={"name": "p6-vehicle", "icon_id": 1})
        assert vehicle.status_code == 201
        root_id = vehicle.json()["id"]
        packet_node = client.post(
            "/api/tree",
            json={"name": "p6-r2l", "parent_id": root_id, "icon_id": 7},
        )
        assert packet_node.status_code == 201
        node_id = packet_node.json()["id"]
        with connect(database_url) as conn:
            conn.execute(
                """
                INSERT INTO vartypes (id, name, scopeid, encsize, decsize)
                VALUES (2, 'u8', %s, 8, 8)
                ON CONFLICT (id) DO NOTHING
                """,
                (root_id,),
            )
            conn.commit()
        saved = client.put(
            f"/api/nodes/{node_id}/packet",
            json={"packet_id": 910092, "name": "p6-r2l", "is_input": False},
        )
        assert saved.status_code == 200
        record = client.post(
            f"/api/scopes/{node_id}/vartypes",
            json={"name": "p6-group", "description": "group desc", "short_name": "grp"},
        )
        assert record.status_code == 201
        record_id = record.json()["id"]
        assert record.json()["description"] == "group desc"
        assert record.json()["short_name"] == "grp"
        transform = client.post(
            "/api/transformations",
            json={"name": "p6-scale", "expression": "x * 0.1"},
        )
        assert transform.status_code == 201
        transform_id = transform.json()["id"]
        created = client.post(
            f"/api/vartypes/{record_id}/fields",
            json={
                "name": "flags",
                "type_id": 2,
                "qty": 1,
                "seq": 1,
                "initial_value": "0",
                "description": "scaled flag",
                "short_name": "flg",
                "override": False,
                "in_sequence": True,
                "transformation_id": transform_id,
            },
        )
        assert created.status_code == 201
        body = created.json()
        assert body["var_type_id"] == record_id
        assert body["description"] == "scaled flag"
        assert body["short_name"] == "flg"
        assert body["initial_value"] == "0"
        assert body["in_sequence"] is True
        assert body["transformation_id"] == transform_id
        cleared = client.patch(
            f"/api/fields/{body['id']}",
            json={
                "description": None,
                "short_name": None,
                "initial_value": None,
                "in_sequence": False,
                "transformation_id": None,
            },
        )
        assert cleared.status_code == 200
        blank = cleared.json()
        assert blank["description"] is None
        assert blank["short_name"] is None
        assert blank["initial_value"] is None
        assert blank["in_sequence"] is False
        assert blank["transformation_id"] is None
    finally:
        _cleanup(database_url, root_id, None)
        if transform_id is not None:
            with connect(database_url) as conn:
                conn.execute("DELETE FROM transformations WHERE id = %s", (transform_id,))
                conn.commit()


def test_deleting_a_vehicle_leaves_its_children(
    client: TestClient,
    database_url: str,
) -> None:
    root_id: int | None = None
    _wipe_named_fixtures(database_url)
    try:
        vehicle = client.post("/api/tree", json={"name": "p6-vehicle", "icon_id": 1})
        assert vehicle.status_code == 201
        root_id = vehicle.json()["id"]
        stage = client.post(
            "/api/tree",
            json={"name": "p6-stage", "parent_id": root_id, "icon_id": 2},
        )
        assert stage.status_code == 201
        stage_id = stage.json()["id"]
        removed = client.delete(f"/api/tree/{root_id}")
        assert removed.status_code == 204
        rows = client.get("/api/tree").json()
        assert "p6-vehicle" not in [row["name"] for row in rows]
        remaining = next(row for row in rows if row["id"] == stage_id)
        assert remaining["name"] == "p6-stage"
        assert remaining["parent_id"] == root_id
    finally:
        _cleanup(database_url, root_id, None)


def test_moving_a_vehicle_resequences_sibling_roots(
    client: TestClient,
    database_url: str,
) -> None:
    created_ids: list[int] = []
    _wipe_named_fixtures(database_url)
    try:
        for name in ("p6-vehicle", "p6-vehicle-b", "p6-vehicle-c"):
            created = client.post("/api/tree", json={"name": name, "icon_id": 1})
            assert created.status_code == 201
            node_id = created.json()["id"]
            assert isinstance(node_id, int)
            created_ids.append(node_id)

        def root_names() -> list[str]:
            rows = client.get("/api/tree").json()
            names = [row["name"] for row in rows if row["id"] in created_ids]
            assert all(isinstance(name, str) for name in names)
            return names

        def root_index(node_id: int) -> int:
            rows = [row for row in client.get("/api/tree").json() if row["parent_id"] is None]
            return next(index for index, row in enumerate(rows) if row["id"] == node_id)

        assert root_names() == ["p6-vehicle", "p6-vehicle-b", "p6-vehicle-c"]
        moved_down = client.patch(
            f"/api/tree/{created_ids[0]}",
            json={"seq": root_index(created_ids[0]) + 2},
        )
        assert moved_down.status_code == 200
        assert root_names() == ["p6-vehicle-b", "p6-vehicle", "p6-vehicle-c"]

        moved_up = client.patch(
            f"/api/tree/{created_ids[2]}",
            json={"seq": root_index(created_ids[2])},
        )
        assert moved_up.status_code == 200
        assert root_names() == ["p6-vehicle-b", "p6-vehicle-c", "p6-vehicle"]
    finally:
        for root_id in created_ids:
            _cleanup(database_url, root_id, None)


def test_deleting_a_node_removes_devices_on_its_smart_nodes(
    client: TestClient,
    database_url: str,
) -> None:
    root_id: int | None = None
    _wipe_named_fixtures(database_url)
    try:
        vehicle = client.post("/api/tree", json={"name": "p6-vehicle", "icon_id": 1})
        assert vehicle.status_code == 201
        root_id = vehicle.json()["id"]
        smart = client.post(
            "/api/tree",
            json={"name": "p6-smart", "parent_id": root_id, "icon_id": 5},
        )
        assert smart.status_code == 201
        smart_id = smart.json()["id"]
        device = client.post(
            "/api/devices",
            json={"name": "p6-device", "smart_node_id": smart_id, "ipv4": "127.0.0.1"},
        )
        assert device.status_code == 201
        device_id = device.json()["id"]

        removed_smart = client.delete(f"/api/tree/{smart_id}")
        assert removed_smart.status_code == 204
        devices = client.get("/api/devices")
        assert devices.status_code == 200
        assert all(row["id"] != device_id for row in devices.json())
        names = [row["name"] for row in client.get("/api/tree").json()]
        assert "p6-smart" not in names
        assert "p6-vehicle" in names

        smart = client.post(
            "/api/tree",
            json={"name": "p6-smart", "parent_id": root_id, "icon_id": 5},
        )
        assert smart.status_code == 201
        smart_id = smart.json()["id"]
        device = client.post(
            "/api/devices",
            json={
                "name": "p6-device",
                "smart_node_id": smart_id,
                "ipv4": "127.0.0.1",
            },
        )
        assert device.status_code == 201
        device_id = device.json()["id"]
        removed = client.delete(f"/api/tree/{root_id}")
        assert removed.status_code == 204
        root_id = smart_id
        names = [row["name"] for row in client.get("/api/tree").json()]
        assert "p6-vehicle" not in names
        assert "p6-smart" in names
        devices = client.get("/api/devices")
        assert any(row["id"] == device_id for row in devices.json())
    finally:
        _cleanup(database_url, root_id, None)


def test_create_seq_is_a_sibling_position(client: TestClient, database_url: str) -> None:
    root_id: int | None = None
    _wipe_named_fixtures(database_url)
    try:
        vehicle = client.post("/api/tree", json={"name": "p6-vehicle", "icon_id": 1})
        assert vehicle.status_code == 201
        root_id = vehicle.json()["id"]
        first = client.post(
            "/api/tree",
            json={"name": "p6-a", "parent_id": root_id, "icon_id": 2, "seq": 1},
        )
        second = client.post(
            "/api/tree",
            json={"name": "p6-b", "parent_id": root_id, "icon_id": 2, "seq": 2},
        )
        middle = client.post(
            "/api/tree",
            json={"name": "p6-c", "parent_id": root_id, "icon_id": 2, "seq": 2},
        )
        assert first.status_code == 201
        assert second.status_code == 201
        assert middle.status_code == 201
        siblings = [row for row in client.get("/api/tree").json() if row["parent_id"] == root_id]
        assert [row["name"] for row in siblings] == ["p6-a", "p6-c", "p6-b"]
        assert [row["seq"] for row in siblings] == [20, 40, 60]
    finally:
        _cleanup(database_url, root_id, None)


def test_server_password_is_write_only(
    client: TestClient,
    database_url: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    server_id: int | None = None
    _wipe_named_fixtures(database_url)
    caplog.set_level(logging.INFO, logger="astra.web")
    try:
        created = client.post(
            "/api/servers",
            json={
                "name": "p6-server",
                "win_name": "p6-win",
                "full_name": "p6-full",
                "ipv4": "127.0.0.1",
                "opc_server_name": "opc.tcp://127.0.0.1:4840/astra/",
                "sql_server_instance": "local",
                "database_name": "astra",
                "username": "astra",
                "password": _PASSWORD,
            },
        )
        assert created.status_code == 201
        payload = created.json()
        server_id = payload["id"]
        assert payload["password_set"] is True
        assert "password" not in payload
        assert _PASSWORD not in created.text

        listed = client.get("/api/servers")
        assert listed.status_code == 200
        assert _PASSWORD not in listed.text
        match = next(row for row in listed.json() if row["id"] == server_id)
        assert match["username"] == "astra"
        assert "password" not in match

        renamed = client.patch(f"/api/servers/{server_id}", json={"name": "p6-server-b"})
        assert renamed.status_code == 200
        assert renamed.json()["name"] == "p6-server-b"
        assert _PASSWORD not in renamed.text
        with connect(database_url) as conn:
            stored = conn.execute(
                "SELECT password FROM servers WHERE id = %s",
                (server_id,),
            ).fetchone()
        assert stored is not None
        assert stored[0] == _PASSWORD

        replaced = client.patch(f"/api/servers/{server_id}", json={"password": _PASSWORD_NEXT})
        assert replaced.status_code == 200
        assert _PASSWORD_NEXT not in replaced.text
        assert "password" not in replaced.json()
        with connect(database_url) as conn:
            stored = conn.execute(
                "SELECT password FROM servers WHERE id = %s",
                (server_id,),
            ).fetchone()
        assert stored is not None
        assert stored[0] == _PASSWORD_NEXT

        leaked = [
            record.getMessage() for record in caplog.records if _PASSWORD in record.getMessage()
        ]
        leaked_next = [
            record.getMessage()
            for record in caplog.records
            if _PASSWORD_NEXT in record.getMessage()
        ]
        assert leaked == []
        assert leaked_next == []

        test = client.post(
            "/api/tests",
            json={"name": "p6-test", "description": "phase 6", "server_id": server_id},
        )
        assert test.status_code == 201
        test_id = test.json()["id"]
        started = client.post(f"/api/tests/{test_id}/start")
        assert started.status_code == 200
        assert started.json()["active"] is True
        assert started.json()["started"] is not None
        assert _PASSWORD_NEXT not in started.text
        stopped = client.post(f"/api/tests/{test_id}/stop")
        assert stopped.status_code == 200
        assert stopped.json()["active"] is False
        assert stopped.json()["stopped"] is not None

        with connect(database_url) as conn:
            conn.execute(
                """
                INSERT INTO jobs (testid, packetid, intfid, done, msg)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (test_id, 910061, 1, False, "waiting"),
            )
            conn.commit()
        jobs = client.get(f"/api/tests/{test_id}/jobs")
        assert jobs.status_code == 200
        assert jobs.json() == [
            {
                "test_id": test_id,
                "packet_id": 910061,
                "intf_id": 1,
                "done": False,
                "msg": "waiting",
            }
        ]
        assert _PASSWORD_NEXT not in jobs.text
    finally:
        _cleanup(database_url, None, server_id)


def _ensure_u8(url: str, scope_id: int) -> None:
    with connect(url) as conn:
        conn.execute(
            """
            INSERT INTO vartypes (id, name, scopeid, encsize, decsize)
            VALUES (2, 'u8', %s, 8, 8)
            ON CONFLICT (id) DO NOTHING
            """,
            (scope_id,),
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


def test_duplicate_copies_a_stage_and_a_packet(client: TestClient, database_url: str) -> None:
    root_id: int | None = None
    _wipe_named_fixtures(database_url)
    try:
        vehicle = client.post("/api/tree", json={"name": "p6-vehicle", "icon_id": 1})
        assert vehicle.status_code == 201
        root_id = vehicle.json()["id"]
        refused = client.post(f"/api/tree/{root_id}/duplicate")
        assert refused.status_code == 400
        stage = client.post(
            "/api/tree",
            json={"name": "p6-stage", "parent_id": root_id, "icon_id": 2},
        )
        assert stage.status_code == 201
        stage_id = stage.json()["id"]
        version = client.post(
            "/api/tree",
            json={"name": "p6-version", "parent_id": stage_id, "icon_id": 3},
        )
        assert version.status_code == 201
        copied = client.post(f"/api/tree/{stage_id}/duplicate")
        assert copied.status_code == 201
        copy = copied.json()
        assert copy["id"] != stage_id
        assert copy["parent_id"] == root_id
        assert copy["icon_id"] == 2
        assert copy["name"] == "Stage"
        children = [row for row in client.get("/api/tree").json() if row["parent_id"] == copy["id"]]
        assert [row["name"] for row in children] == ["Version"]
        assert children[0]["icon_id"] == 3

        smart = client.post(
            "/api/tree",
            json={"name": "p6-smart", "parent_id": version.json()["id"], "icon_id": 5},
        )
        packet_node = client.post(
            "/api/tree",
            json={"name": "p6-r2l", "parent_id": smart.json()["id"], "icon_id": 7},
        )
        assert packet_node.status_code == 201
        node_id = packet_node.json()["id"]
        empty = client.post(f"/api/tree/{node_id}/duplicate")
        assert empty.status_code == 400
        siblings = [
            row for row in client.get("/api/tree").json() if row["parent_id"] == smart.json()["id"]
        ]
        assert [row["id"] for row in siblings] == [node_id]
        _ensure_u8(database_url, root_id)
        saved = client.put(
            f"/api/nodes/{node_id}/packet",
            json={"packet_id": 910062, "name": "p6-r2l", "is_input": False},
        )
        assert saved.status_code == 200
        var_type_id = saved.json()["var_type_id"]
        field = client.post(
            f"/api/vartypes/{var_type_id}/fields",
            json={"name": "flags", "type_id": 2, "qty": 1},
        )
        assert field.status_code == 201
        packet_copy = client.post(f"/api/tree/{node_id}/duplicate")
        assert packet_copy.status_code == 201
        assert packet_copy.json()["name"] == "p6-r2l"
        assert packet_copy.json()["icon_id"] == 7
        cloned = client.get(f"/api/nodes/{packet_copy.json()['id']}/packet")
        assert cloned.status_code == 200
        assert cloned.json()["packet_id"] != 910062
        assert cloned.json()["is_input"] is False
        cloned_fields = client.get(f"/api/vartypes/{cloned.json()['var_type_id']}/fields")
        assert cloned_fields.status_code == 200
        assert [row["name"] for row in cloned_fields.json()] == ["flags"]
        assert cloned_fields.json()[0]["connection_id"] is None
    finally:
        _cleanup(database_url, root_id, None)


def test_mapping_links_a_field_and_lists_the_pin(
    client: TestClient,
    database_url: str,
) -> None:
    root_id: int | None = None
    _wipe_named_fixtures(database_url)
    try:
        vehicle = client.post("/api/tree", json={"name": "p6-vehicle", "icon_id": 1})
        root_id = vehicle.json()["id"]
        stage = client.post(
            "/api/tree",
            json={"name": "p6-stage", "parent_id": root_id, "icon_id": 2},
        )
        version = client.post(
            "/api/tree",
            json={"name": "p6-version", "parent_id": stage.json()["id"], "icon_id": 3},
        )
        release = client.post(
            "/api/tree",
            json={"name": "p6-release", "parent_id": version.json()["id"], "icon_id": 4},
        )
        smart = client.post(
            "/api/tree",
            json={"name": "p6-smart", "parent_id": release.json()["id"], "icon_id": 5},
        )
        smart_id = smart.json()["id"]
        packet_node = client.post(
            "/api/tree",
            json={"name": "p6-r2l", "parent_id": smart_id, "icon_id": 7},
        )
        node_id = packet_node.json()["id"]
        _ensure_u8(database_url, root_id)
        saved = client.put(
            f"/api/nodes/{node_id}/packet",
            json={"packet_id": 910063, "name": "p6-r2l", "is_input": False},
        )
        var_type_id = saved.json()["var_type_id"]
        with connect(database_url) as conn:
            conn.execute(
                """
                INSERT INTO vartypes (id, name, scopeid)
                VALUES (910200, 'p6-inner', %s)
                ON CONFLICT (id) DO UPDATE
                SET name = EXCLUDED.name, scopeid = EXCLUDED.scopeid
                """,
                (node_id,),
            )
            conn.execute("SELECT identity_insert_bump('config.vartypes', 'id', 910200)")
            hardware = conn.execute(
                """
                INSERT INTO treeversions (name, parentid, iconid)
                VALUES ('p6-hardware', %s, 8)
                RETURNING id
                """,
                (smart_id,),
            ).fetchone()
            if hardware is None:
                raise AssertionError("hardware node was not inserted")
            area = conn.execute(
                """
                INSERT INTO treeversions (name, parentid, iconid)
                VALUES ('p6-area', %s, 9)
                RETURNING id
                """,
                (hardware[0],),
            ).fetchone()
            if area is None:
                raise AssertionError("area node was not inserted")
            board = conn.execute(
                """
                INSERT INTO treeversions (name, parentid, iconid)
                VALUES ('p6-board', %s, 10)
                RETURNING id
                """,
                (area[0],),
            ).fetchone()
            if board is None:
                raise AssertionError("board node was not inserted")
            pin = conn.execute(
                """
                INSERT INTO connections (boardid, firstpin, shortname, description)
                VALUES (%s, 3, 'p6-pin', 'p6 pin')
                RETURNING id
                """,
                (board[0],),
            ).fetchone()
            if pin is None or not isinstance(pin[0], int):
                raise AssertionError("connection was not inserted")
            connection_id = pin[0]
            conn.commit()
        nested = client.post(
            f"/api/vartypes/{var_type_id}/fields",
            json={"name": "inner", "type_id": 910200, "qty": 1},
        )
        assert nested.status_code == 201
        leaf = client.post(
            "/api/vartypes/910200/fields",
            json={"name": "pinfield", "type_id": 2, "qty": 1},
        )
        assert leaf.status_code == 201
        field_id = leaf.json()["id"]
        missing = client.post(
            "/api/mappings",
            json={"field_id": field_id, "connection_id": 999999},
        )
        assert missing.status_code == 404
        linked = client.post(
            "/api/mappings",
            json={"field_id": field_id, "connection_id": connection_id},
        )
        assert linked.status_code == 200
        assert linked.json()["connection_id"] == connection_id
        listed = client.get(f"/api/nodes/{node_id}/mappings")
        assert listed.status_code == 200
        assert len(listed.json()) == 1
        row = listed.json()[0]
        assert row["field"] == "pinfield"
        assert row["area"] == "p6-area"
        assert row["board"] == "p6-board"
        assert row["first_pin"] == 3
        assert row["connection_id"] == connection_id
        root_field = client.post(
            f"/api/vartypes/{var_type_id}/fields",
            json={"name": "flags", "type_id": 2, "qty": 1},
        )
        assert root_field.status_code == 201
        root_field_id = root_field.json()["id"]
        root_linked = client.post(
            "/api/mappings",
            json={"field_id": root_field_id, "connection_id": connection_id},
        )
        assert root_linked.status_code == 200
        both = client.get(f"/api/nodes/{node_id}/mappings")
        assert both.status_code == 200
        by_name = {item["field"]: item for item in both.json()}
        assert set(by_name) == {"pinfield", "flags"}
        assert by_name["flags"]["field_id"] == root_field_id
        assert by_name["flags"]["area"] == "p6-area"
        assert by_name["flags"]["first_pin"] == 3
        cleared_root = client.delete(f"/api/mappings/{root_field_id}")
        assert cleared_root.status_code == 200
        assert cleared_root.json()["connection_id"] is None
        after_root = client.get(f"/api/nodes/{node_id}/mappings")
        assert [item["field"] for item in after_root.json()] == ["pinfield"]

        simulink = client.get(f"/api/nodes/{node_id}/exports/simulink")
        assert simulink.status_code == 200
        assert simulink.headers["content-type"].startswith("text/csv")
        assert simulink.text.startswith(
            "varorder;recordname;recorddescription;fieldname;arraylen;"
            "typename;fielddescription;override;insequence\r\n"
        )
        assert "pinfield" in simulink.text
        assert ";0;0\r\n" in simulink.text
        opcua = client.get(f"/api/nodes/{node_id}/exports/opcua")
        assert opcua.status_code == 200
        assert "Astrap6-r2l/inner\n" in opcua.text
        assert "Astrap6-r2l/pinfield\n" in opcua.text
        mapping_csv = client.get(f"/api/nodes/{node_id}/exports/mapping")
        assert mapping_csv.status_code == 200
        assert mapping_csv.text.startswith("fieldid;connectionid;fieldorder;")
        assert "p6-area;p6-board;3;" in mapping_csv.text
        assert '"p6 pin"' in mapping_csv.text
        missing_export = client.get("/api/nodes/2147483646/exports/simulink")
        assert missing_export.status_code == 404

        cleared = client.delete(f"/api/mappings/{field_id}")
        assert cleared.status_code == 200
        assert cleared.json()["connection_id"] is None
        assert client.get(f"/api/nodes/{node_id}/mappings").json() == []
    finally:
        _cleanup(database_url, root_id, None)


def test_rejected_server_body_does_not_echo_the_password(client: TestClient) -> None:
    denied = client.post("/api/servers", json={"password": _PASSWORD, "extra": 1})
    assert denied.status_code == 400
    assert denied.json() == {"detail": "invalid"}
    assert _PASSWORD not in denied.text


def test_missing_database_does_not_echo_the_url() -> None:
    app = create_app(
        WebSettings(
            database_url=None,
            token=_TOKEN,
            database_error="DATABASE_URL is not set",
            token_error=None,
        )
    )
    with TestClient(app) as test_client:
        denied = test_client.get("/api/tree", headers={"Authorization": f"Bearer {_TOKEN}"})
    assert denied.status_code == 503
    assert denied.json() == {"detail": "DATABASE_URL is not set"}
    assert _TOKEN not in denied.text


def test_generator_writes_the_interface_csv(
    client: TestClient,
    database_url: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root_id: int | None = None
    _wipe_named_fixtures(database_url)
    try:
        vehicle = client.post("/api/tree", json={"name": "p6-vehicle", "icon_id": 1})
        root_id = vehicle.json()["id"]
        stage = client.post(
            "/api/tree",
            json={"name": "p6-stage", "parent_id": root_id, "icon_id": 2},
        )
        version = client.post(
            "/api/tree",
            json={"name": "p6-version", "parent_id": stage.json()["id"], "icon_id": 3},
        )
        release = client.post(
            "/api/tree",
            json={"name": "p6-release", "parent_id": version.json()["id"], "icon_id": 4},
        )
        smart = client.post(
            "/api/tree",
            json={"name": "p6-smart", "parent_id": release.json()["id"], "icon_id": 5},
        )
        packet_node = client.post(
            "/api/tree",
            json={"name": "p6r2l", "parent_id": smart.json()["id"], "icon_id": 7},
        )
        node_id = packet_node.json()["id"]
        _ensure_u8(database_url, root_id)
        saved = client.put(
            f"/api/nodes/{node_id}/packet",
            json={"packet_id": 910066, "name": "p6r2l", "is_input": False},
        )
        assert saved.status_code == 200
        field = client.post(
            f"/api/vartypes/{saved.json()['var_type_id']}/fields",
            json={"name": "flags", "type_id": 2, "qty": 1},
        )
        assert field.status_code == 201
        destination = tmp_path / "interface.csv"
        missing = generate_main(["missing", "missing", "missing", str(destination)])
        assert missing == 1
        assert capsys.readouterr().err.strip() == "not_found"
        assert not destination.exists()
        written = generate_main(["p6-stage", "p6-smart", "p6r2l", str(destination)])
        assert written == 0
        text = destination.read_text(encoding="utf-8")
        assert text.startswith("varorder;recordname;")
        assert "flags" in text
        assert "astra:astra" not in text
    finally:
        _cleanup(database_url, root_id, None)


def test_log_pages_only_after_the_job_is_done(client: TestClient, database_url: str) -> None:
    root_id: int | None = None
    server_id: int | None = None
    table = ""
    _wipe_named_fixtures(database_url)
    try:
        vehicle = client.post("/api/tree", json={"name": "p6-vehicle", "icon_id": 1})
        root_id = vehicle.json()["id"]
        stage = client.post(
            "/api/tree",
            json={"name": "p6-stage", "parent_id": root_id, "icon_id": 2},
        )
        version = client.post(
            "/api/tree",
            json={"name": "p6-version", "parent_id": stage.json()["id"], "icon_id": 3},
        )
        release = client.post(
            "/api/tree",
            json={"name": "p6-release", "parent_id": version.json()["id"], "icon_id": 4},
        )
        smart = client.post(
            "/api/tree",
            json={"name": "p6-smart", "parent_id": release.json()["id"], "icon_id": 5},
        )
        packet_node = client.post(
            "/api/tree",
            json={"name": "p6r2l", "parent_id": smart.json()["id"], "icon_id": 7},
        )
        node_id = packet_node.json()["id"]
        saved = client.put(
            f"/api/nodes/{node_id}/packet",
            json={"packet_id": 910064, "name": "p6r2l", "is_input": False},
        )
        assert saved.status_code == 200
        hyphen_node = client.post(
            "/api/tree",
            json={"name": "p6-r2l", "parent_id": smart.json()["id"], "icon_id": 7},
        )
        hyphen = client.put(
            f"/api/nodes/{hyphen_node.json()['id']}/packet",
            json={"packet_id": 910065, "name": "p6-r2l", "is_input": False},
        )
        assert hyphen.status_code == 200
        server = client.post(
            "/api/servers",
            json={
                "name": "p6-log-server",
                "win_name": "p6-win",
                "full_name": "p6-full",
                "ipv4": "127.0.0.1",
                "opc_server_name": "opc.tcp://127.0.0.1:4840/astra/",
                "sql_server_instance": "local",
                "database_name": "astra",
                "username": "astra",
                "password": _PASSWORD,
            },
        )
        assert server.status_code == 201
        server_id = server.json()["id"]
        created = client.post(
            "/api/tests",
            json={"name": "p6-log", "server_id": server_id},
        )
        assert created.status_code == 201
        test_id = created.json()["id"]
        table = f"p6r2l_{test_id}"
        with connect(database_url) as conn:
            conn.execute(
                """
                INSERT INTO jobs (testid, packetid, intfid, done, msg)
                VALUES (%s, 910064, %s, false, 'waiting')
                """,
                (test_id, node_id),
            )
            conn.execute(
                """
                INSERT INTO jobs (testid, packetid, intfid, done, msg)
                VALUES (%s, 910065, %s, true, 'done')
                """,
                (test_id, hyphen_node.json()["id"]),
            )
            conn.execute(
                f"""
                CREATE TABLE testlog.{table} (
                    stamp timestamp(3) NOT NULL,
                    note varchar(32),
                    flag boolean
                )
                """
            )
            conn.execute(
                f"""
                INSERT INTO testlog.{table} (stamp, note, flag)
                VALUES
                    ('2026-01-01 00:00:00', 'p6 only', false),
                    ('2026-01-01 00:00:01', 'has space', true),
                    ('2026-01-01 00:00:02', 'third', false)
                """
            )
            conn.commit()
        closed = client.get(f"/api/tests/{test_id}/packets/910064/log")
        assert closed.status_code == 409
        assert closed.json() == {"detail": "conflict"}
        unsafe = client.get(f"/api/tests/{test_id}/packets/910065/log")
        assert unsafe.status_code == 400
        with connect(database_url) as conn:
            conn.execute(
                "UPDATE jobs SET done = true WHERE testid = %s AND packetid = 910064",
                (test_id,),
            )
            conn.commit()
        page = client.get(f"/api/tests/{test_id}/packets/910064/log?limit=2&offset=0")
        assert page.status_code == 200
        body = page.json()
        assert body["table"] == table
        assert body["table"] != "l2r_1"
        assert body["total"] == 3
        assert [row["note"] for row in body["rows"]] == ["p6 only", "has space"]
        nxt = client.get(f"/api/tests/{test_id}/packets/910064/log?limit=2&offset=2")
        assert [row["note"] for row in nxt.json()["rows"]] == ["third"]
        exported = client.get(f"/api/tests/{test_id}/packets/910064/log.csv")
        assert exported.status_code == 200
        assert exported.text.startswith("stamp;note;flag\r\n")
        assert '"has space";1' in exported.text
        assert "p6 only" in exported.text
        assert "l2r_1" not in exported.text
    finally:
        if table:
            with connect(database_url) as conn:
                conn.execute(f"DROP TABLE IF EXISTS testlog.{table}")
                conn.commit()
        _cleanup(database_url, root_id, server_id)


def test_hardware_editor_creates_areas_boards_and_pins(
    client: TestClient,
    database_url: str,
) -> None:
    root_id: int | None = None
    field_id: int | None = None
    try:
        vehicle = client.post("/api/tree", json={"name": "p8-vehicle", "icon_id": 1})
        assert vehicle.status_code == 201
        root_id = vehicle.json()["id"]
        stage = client.post(
            "/api/tree",
            json={"name": "p8-stage", "parent_id": root_id, "icon_id": 2},
        )
        assert stage.status_code == 201
        version = client.post(
            "/api/tree",
            json={"name": "p8-version", "parent_id": stage.json()["id"], "icon_id": 3},
        )
        release = client.post(
            "/api/tree",
            json={"name": "p8-release", "parent_id": version.json()["id"], "icon_id": 4},
        )
        smart = client.post(
            "/api/tree",
            json={"name": "p8-smart", "parent_id": release.json()["id"], "icon_id": 5},
        )
        assert smart.status_code == 201
        smart_id = smart.json()["id"]

        misplaced = client.post(
            "/api/tree",
            json={"name": "p8-hardware", "parent_id": stage.json()["id"], "icon_id": 8},
        )
        assert misplaced.status_code == 400

        hardware = client.post(
            "/api/tree",
            json={"name": "p8-hardware", "parent_id": smart_id, "icon_id": 8},
        )
        assert hardware.status_code == 201
        hardware_id = hardware.json()["id"]
        assert hardware.json()["icon_id"] == 8
        second = client.post(
            "/api/tree",
            json={"name": "p8-hardware-2", "parent_id": smart_id, "icon_id": 8},
        )
        assert second.status_code == 409
        frozen = client.patch(f"/api/tree/{hardware_id}", json={"seq": 1})
        assert frozen.status_code == 400
        renamed = client.patch(f"/api/tree/{hardware_id}", json={"name": "p8-hw"})
        assert renamed.status_code == 200
        assert renamed.json()["name"] == "p8-hw"
        copied_root = client.post(f"/api/tree/{hardware_id}/duplicate")
        assert copied_root.status_code == 400

        area_under_smart = client.post(
            "/api/tree",
            json={"name": "p8-area", "parent_id": smart_id, "icon_id": 9},
        )
        assert area_under_smart.status_code == 400
        area = client.post(
            "/api/tree",
            json={"name": "p8-area", "parent_id": hardware_id, "icon_id": 9},
        )
        assert area.status_code == 201
        area_id = area.json()["id"]
        moved = client.patch(f"/api/tree/{area_id}", json={"seq": 1})
        assert moved.status_code == 200

        board_under_hardware = client.post(
            "/api/tree",
            json={"name": "p8-board", "parent_id": hardware_id, "icon_id": 10},
        )
        assert board_under_hardware.status_code == 400
        board = client.post(
            "/api/tree",
            json={"name": "p8-board", "parent_id": area_id, "icon_id": 10},
        )
        assert board.status_code == 201
        board_id = board.json()["id"]

        link = client.post(
            "/api/link-types",
            json={"name": "W", "description": "p8-wire"},
        )
        assert link.status_code == 201
        link_id = link.json()["id"]
        assert link.json()["name"] == "W"
        connector = client.post(
            "/api/connectors",
            json={"part_no": 1001, "description": "p8-plug"},
        )
        assert connector.status_code == 201
        connector_id = connector.json()["id"]
        assert connector.json()["part_no"] == 1001.0

        missing_link = client.post(
            f"/api/boards/{board_id}/connections",
            json={"first_pin": 4, "link_type_id": 999999},
        )
        assert missing_link.status_code == 404
        created = client.post(
            f"/api/boards/{board_id}/connections",
            json={
                "first_pin": 4,
                "link_type_id": link_id,
                "connector_id": connector_id,
                "short_name": "p8",
                "description": "p8-pin",
                "seq": 1,
            },
        )
        assert created.status_code == 201
        pin = created.json()
        assert pin["first_pin"] == 4
        assert pin["link_type_name"] == "W"
        assert pin["part_no"] == 1001.0
        assert pin["short_name"] == "p8"
        cleared = client.patch(f"/api/connections/{pin['id']}", json={"short_name": None})
        assert cleared.status_code == 200
        assert cleared.json()["short_name"] is None
        assert cleared.json()["description"] == "p8-pin"
        empty = client.patch(f"/api/connections/{pin['id']}", json={})
        assert empty.status_code == 400

        listed = client.get(f"/api/boards/{board_id}/connections")
        assert listed.status_code == 200
        assert [row["id"] for row in listed.json()] == [pin["id"]]
        wiring = client.get(f"/api/nodes/{hardware_id}/wiring")
        assert wiring.status_code == 200
        assert wiring.json()[0]["area"] == "p8-area"
        assert wiring.json()[0]["board"] == "p8-board"
        assert wiring.json()[0]["first_pin"] == 4
        not_hardware = client.get(f"/api/nodes/{smart_id}/wiring")
        assert not_hardware.status_code == 400
        not_board = client.get(f"/api/boards/{area_id}/connections")
        assert not_board.status_code == 400

        copied = client.post(f"/api/tree/{board_id}/duplicate")
        assert copied.status_code == 201
        assert copied.json()["icon_id"] == 10
        assert copied.json()["parent_id"] == area_id
        assert copied.json()["name"] == "p8-board"
        clone_pins = client.get(f"/api/boards/{copied.json()['id']}/connections")
        assert clone_pins.status_code == 200
        assert clone_pins.json()[0]["first_pin"] == 4
        assert clone_pins.json()[0]["description"] == "p8-pin"
        assert clone_pins.json()[0]["id"] != pin["id"]

        packet_node = client.post(
            "/api/tree",
            json={"name": "p8-r2l", "parent_id": smart_id, "icon_id": 7},
        )
        assert packet_node.status_code == 201
        node_id = packet_node.json()["id"]
        _ensure_u8(database_url, root_id)
        saved = client.put(
            f"/api/nodes/{node_id}/packet",
            json={"packet_id": 910180, "name": "p8-r2l", "is_input": False},
        )
        assert saved.status_code == 200
        field = client.post(
            f"/api/vartypes/{saved.json()['var_type_id']}/fields",
            json={"name": "p8-flag", "type_id": 2, "qty": 1},
        )
        assert field.status_code == 201
        field_id = field.json()["id"]
        linked = client.post(
            "/api/mappings",
            json={"field_id": field_id, "connection_id": pin["id"]},
        )
        assert linked.status_code == 200
        blocked = client.delete(f"/api/connections/{pin['id']}")
        assert blocked.status_code == 409
        unlinked = client.delete(f"/api/mappings/{field_id}")
        assert unlinked.status_code == 200
        removed = client.delete(f"/api/connections/{pin['id']}")
        assert removed.status_code == 204
        remaining = client.get(f"/api/nodes/{area_id}/wiring")
        assert remaining.status_code == 200
        assert len(remaining.json()) == 1
        assert remaining.json()[0]["board"] == "p8-board"
    finally:
        if field_id is not None:
            client.delete(f"/api/mappings/{field_id}")
        _cleanup(database_url, root_id, None)
        with connect(database_url) as conn:
            conn.execute("DELETE FROM linktypes WHERE description LIKE 'p8-%'")
            conn.execute("DELETE FROM connectors WHERE description LIKE 'p8-%'")
            conn.commit()
