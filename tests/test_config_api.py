"""Operator API against PostgreSQL. Skipped unless ``DATABASE_URL`` is set."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

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
            stage = conn.execute(
                "SELECT id FROM treeversions WHERE parentid = %s AND iconid = 2",
                (root_id,),
            ).fetchone()
            if stage is not None:
                conn.execute("SELECT spdelete(%s)", (stage[0],))
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


def test_deleting_a_vehicle_removes_its_children(
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
        removed = client.delete(f"/api/tree/{root_id}")
        assert removed.status_code == 204
        names = [row["name"] for row in client.get("/api/tree").json()]
        assert "p6-vehicle" not in names
        assert "p6-stage" not in names
        root_id = None
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
