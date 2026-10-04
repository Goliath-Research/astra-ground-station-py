"""Read and write the configurator tables through the migrated functions.

Tree duplicate, delete, move, packet save, and Enc/Dec size stay in
``spduplicate``, ``spdelete``, ``spmovenodetoseq``, ``spsetpacket``, and
``spcalcvartypesizes``. This module does not reimplement those rules.

``config.servers.password`` is accepted on insert and update and is never
part of a returned row. Callers see ``password_set`` only.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

import psycopg
from psycopg.rows import dict_row

from astra.db.errors import ConfigError

# TreeVersions.IconID values the configurator draws. 8, 9, and 10 are the
# hardware editor and are not created here.
ICON_VEHICLE = 1
ICON_STAGE = 2
ICON_VERSION = 3
ICON_RELEASE = 4
ICON_SMART_NODE = 5
ICON_L2R = 6
ICON_R2L = 7
CREATABLE_ICONS = frozenset(
    {
        ICON_VEHICLE,
        ICON_STAGE,
        ICON_VERSION,
        ICON_RELEASE,
        ICON_SMART_NODE,
        ICON_L2R,
        ICON_R2L,
    }
)

_SERVER_PUBLIC = """
id, name, winname, fullname, ipv4, port, opcservername, sqlserverinstance,
databasename, username, (octet_length(password) > 0) AS password_set
"""

_FIELD_SELECT = """
SELECT f.id, f.name, f.qty, f.typeid, f.initialvalue, t.name AS typename,
       COALESCE(f.description, t.description) AS description,
       f.override, f.insequence, f.transformationid, f.seq, f.shortname,
       f.vartypeid
FROM fields AS f
INNER JOIN vartypes AS t ON f.typeid = t.id
"""

_SERVER_COLUMNS: dict[str, str] = {
    "name": "name",
    "win_name": "winname",
    "full_name": "fullname",
    "ipv4": "ipv4",
    "port": "port",
    "opc_server_name": "opcservername",
    "sql_server_instance": "sqlserverinstance",
    "database_name": "databasename",
    "username": "username",
    "password": "password",
}

_DEVICE_COLUMNS: dict[str, str] = {
    "name": "name",
    "smart_node_id": "smartnodeid",
    "ipv4": "ipv4",
    "port": "port",
}

_FIELD_COLUMNS: dict[str, str] = {
    "name": "name",
    "qty": "qty",
    "type_id": "typeid",
    "initial_value": "initialvalue",
    "seq": "seq",
    "override": "override",
    "in_sequence": "insequence",
    "description": "description",
    "short_name": "shortname",
    "transformation_id": "transformationid",
}


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="milliseconds")
    if isinstance(value, Decimal):
        integral = value.to_integral_value()
        if value == integral:
            return int(integral)
        return float(value)
    return value


def _tree(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "parent_id": row["parentid"],
        "icon_id": row["iconid"],
        "seq": row["seq"],
    }


def _var_type(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "scope_id": row["scopeid"],
        "description": row["description"],
        "short_name": row["shortname"],
        "dec_size": row["decsize"],
        "enc_size": row["encsize"],
    }


def _field(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "qty": row["qty"],
        "type_id": row["typeid"],
        "type_name": row["typename"],
        "initial_value": row["initialvalue"],
        "description": row["description"],
        "override": row["override"],
        "in_sequence": row["insequence"],
        "transformation_id": row["transformationid"],
        "seq": row["seq"],
        "short_name": row["shortname"],
        "var_type_id": row["vartypeid"],
    }


def _server(row: dict[str, Any]) -> dict[str, Any]:
    if "password" in row:
        raise ConfigError("invalid")
    return {
        "id": row["id"],
        "name": row["name"],
        "win_name": row["winname"],
        "full_name": row["fullname"],
        "ipv4": row["ipv4"],
        "port": row["port"],
        "opc_server_name": row["opcservername"],
        "sql_server_instance": row["sqlserverinstance"],
        "database_name": row["databasename"],
        "username": row["username"],
        "password_set": bool(row["password_set"]),
    }


def _device(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "smart_node_id": row["smartnodeid"],
        "ipv4": row["ipv4"],
        "port": row["port"],
    }


def _transformation(row: dict[str, Any]) -> dict[str, Any]:
    return {"id": row["id"], "name": row["name"], "expression": row["expression"]}


def _test(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "server_id": row["serverid"],
        "active": row["active"],
        "started": row["started"],
        "stopped": row["stopped"],
        "export": row["export"],
    }


def _job(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "test_id": row["testid"],
        "packet_id": row["packetid"],
        "intf_id": row["intfid"],
        "done": row["done"],
        "msg": row["msg"],
    }


def _assignments(changes: dict[str, Any], columns: dict[str, str]) -> tuple[str, list[Any]]:
    if not changes:
        raise ConfigError("invalid")
    sets: list[str] = []
    params: list[Any] = []
    for key, value in changes.items():
        column = columns.get(key)
        if column is None:
            raise ConfigError("invalid")
        if key == "password":
            if not isinstance(value, str) or value == "" or len(value) > 64:
                raise ConfigError("invalid")
        sets.append(f"{column} = %s")
        params.append(value)
    return ", ".join(sets), params


class ConfigRepo:
    """One transaction's view of ``config``.

    The caller commits. Methods raise :class:`ConfigError` for rules this
    module checks itself. PostgreSQL errors propagate so the caller can
    roll back without logging the statement.
    """

    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        self._conn = conn

    def _fetch(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            fetched = cur.fetchall()
        return [{key: _jsonable(value) for key, value in row.items()} for row in fetched]

    def _one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        rows = self._fetch(sql, params)
        if not rows:
            return None
        return rows[0]

    def _exec(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        self._conn.execute(sql, params)

    def tree(self) -> list[dict[str, Any]]:
        rows = self._fetch(
            """
            SELECT id, name, parentid, iconid, seq
            FROM treeversions
            ORDER BY parentid NULLS FIRST, seq NULLS FIRST, name
            """
        )
        return [_tree(row) for row in rows]

    def node(self, node_id: int) -> dict[str, Any] | None:
        row = self._one(
            "SELECT id, name, parentid, iconid, seq FROM treeversions WHERE id = %s",
            (node_id,),
        )
        if row is None:
            return None
        return _tree(row)

    def insert_node(
        self,
        *,
        name: str,
        parent_id: int | None,
        icon_id: int,
        seq: int | None,
    ) -> dict[str, Any]:
        if icon_id not in CREATABLE_ICONS:
            raise ConfigError("invalid")
        if icon_id == ICON_VEHICLE and parent_id is not None:
            raise ConfigError("invalid")
        if icon_id != ICON_VEHICLE and parent_id is None:
            raise ConfigError("invalid")
        if parent_id is not None and self.node(parent_id) is None:
            raise ConfigError("not_found")
        row = self._one(
            """
            INSERT INTO treeversions (name, parentid, iconid)
            VALUES (%s, %s, %s)
            RETURNING id, name, parentid, iconid, seq
            """,
            (name, parent_id, icon_id),
        )
        if row is None:
            raise ConfigError("conflict")
        created = _tree(row)
        if seq is None:
            return created
        if seq < 1:
            raise ConfigError("invalid")
        # Same meaning as a move: seq is a 1-based sibling position.
        # spmovenodetoseq stores that position times 20.
        self._exec("SELECT spmovenodetoseq(%s, %s)", (created["id"], seq))
        placed = self.node(created["id"])
        if placed is None:
            raise ConfigError("not_found")
        return placed

    def update_node(
        self,
        node_id: int,
        *,
        name: str | None,
        seq: int | None,
    ) -> dict[str, Any]:
        if self.node(node_id) is None:
            raise ConfigError("not_found")
        if name is None and seq is None:
            raise ConfigError("invalid")
        if name is not None:
            self._exec("UPDATE treeversions SET name = %s WHERE id = %s", (name, node_id))
        if seq is not None:
            if seq < 1:
                raise ConfigError("invalid")
            self._exec("SELECT spmovenodetoseq(%s, %s)", (node_id, seq))
        updated = self.node(node_id)
        if updated is None:
            raise ConfigError("not_found")
        return updated

    def delete_node(self, node_id: int) -> None:
        node = self.node(node_id)
        if node is None:
            raise ConfigError("not_found")
        # spdelete walks children for icons 2-10 only. A vehicle has no
        # parentid foreign key, so deleting that row alone orphans the subtree.
        if node["icon_id"] == ICON_VEHICLE:
            self._exec("SELECT spdeletenode(%s)", (node_id,))
        self._exec("SELECT spdelete(%s)", (node_id,))

    def packet(self, node_id: int) -> dict[str, Any] | None:
        row = self._one(
            "SELECT packetid, packetname, isinput FROM spgetpacket(%s)",
            (node_id,),
        )
        if row is None or row["packetid"] is None:
            return None
        size = self._one(
            "SELECT vartypeid, description, decsize, encsize FROM spgetvartype(%s)",
            (node_id,),
        )
        dec_size = None if size is None else size["decsize"]
        enc_size = None if size is None else size["encsize"]
        var_type_id = None if size is None else size["vartypeid"]
        description = None if size is None else size["description"]
        return {
            "node_id": node_id,
            "packet_id": row["packetid"],
            "name": row["packetname"],
            "is_input": row["isinput"],
            "var_type_id": var_type_id,
            "description": description,
            "dec_size": dec_size,
            "enc_size": enc_size,
        }

    def set_packet(
        self,
        node_id: int,
        *,
        packet_id: int,
        name: str,
        is_input: bool,
    ) -> dict[str, Any]:
        node = self.node(node_id)
        if node is None:
            raise ConfigError("not_found")
        self._exec(
            "SELECT spsetpacket(%s, %s, %s, %s)",
            (node_id, packet_id, name, is_input),
        )
        if node["icon_id"] in (ICON_L2R, ICON_R2L, None):
            icon_id = ICON_L2R if is_input else ICON_R2L
            self._exec(
                "UPDATE treeversions SET name = %s, iconid = %s WHERE id = %s",
                (name, icon_id, node_id),
            )
        saved = self.packet(node_id)
        if saved is None:
            raise ConfigError("conflict")
        return saved

    def calc_sizes(self, node_id: int) -> list[dict[str, Any]]:
        if self.node(node_id) is None:
            raise ConfigError("not_found")
        self._exec("SELECT spcalcvartypesizes(%s)", (node_id,))
        rows = self._fetch(
            """
            SELECT id, name, scopeid, description, shortname, decsize, encsize
            FROM vartypes
            WHERE scopeid = %s
            ORDER BY id
            """,
            (node_id,),
        )
        return [_var_type(row) for row in rows]

    def var_types(self, scope_id: int) -> list[dict[str, Any]]:
        if self.node(scope_id) is None:
            raise ConfigError("not_found")
        rows = self._fetch(
            """
            SELECT id, name, scopeid, description, shortname, decsize, encsize
            FROM spvartypes(%s) AS t
            ORDER BY t.id
            """,
            (scope_id,),
        )
        return [_var_type(row) for row in rows]

    def insert_var_type(
        self,
        scope_id: int,
        *,
        name: str,
        description: str | None,
        short_name: str | None,
        enc_size: int | None,
        dec_size: int | None,
    ) -> dict[str, Any]:
        if self.node(scope_id) is None:
            raise ConfigError("not_found")
        row = self._one(
            """
            INSERT INTO vartypes (name, scopeid, description, shortname, encsize, decsize)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, name, scopeid, description, shortname, decsize, encsize
            """,
            (name, scope_id, description, short_name, enc_size, dec_size),
        )
        if row is None:
            raise ConfigError("conflict")
        return _var_type(row)

    def fields(self, var_type_id: int) -> list[dict[str, Any]]:
        if self._one("SELECT id FROM vartypes WHERE id = %s", (var_type_id,)) is None:
            raise ConfigError("not_found")
        rows = self._fetch(
            _FIELD_SELECT
            + " WHERE f.vartypeid = %s ORDER BY f.seq NULLS FIRST, f.name NULLS FIRST",
            (var_type_id,),
        )
        return [_field(row) for row in rows]

    def procedure_field_names(self, var_type_id: int) -> list[str]:
        """Names in ``spgetvartypefields`` order, used to check the grid query."""
        rows = self._fetch(
            "SELECT fieldname FROM spgetvartypefields(%s)",
            (var_type_id,),
        )
        names: list[str] = []
        for row in rows:
            name = row["fieldname"]
            if not isinstance(name, str):
                raise ConfigError("conflict")
            names.append(name)
        return names

    def insert_field(self, var_type_id: int, changes: dict[str, Any]) -> dict[str, Any]:
        if self._one("SELECT id FROM vartypes WHERE id = %s", (var_type_id,)) is None:
            raise ConfigError("not_found")
        row = self._one(
            """
            INSERT INTO fields (
                name, qty, typeid, initialvalue, seq, vartypeid, override,
                insequence, description, shortname, transformationid
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                changes["name"],
                changes["qty"],
                changes["type_id"],
                changes.get("initial_value"),
                changes.get("seq"),
                var_type_id,
                changes.get("override", False),
                changes.get("in_sequence", False),
                changes.get("description"),
                changes.get("short_name"),
                changes.get("transformation_id"),
            ),
        )
        if row is None:
            raise ConfigError("conflict")
        field_id = row["id"]
        if not isinstance(field_id, int):
            raise ConfigError("conflict")
        saved = self._field_by_id(field_id)
        if saved is None:
            raise ConfigError("conflict")
        return saved

    def update_field(self, field_id: int, changes: dict[str, Any]) -> dict[str, Any]:
        if self._field_by_id(field_id) is None:
            raise ConfigError("not_found")
        clause, params = _assignments(changes, _FIELD_COLUMNS)
        self._exec(f"UPDATE fields SET {clause} WHERE id = %s", (*params, field_id))
        saved = self._field_by_id(field_id)
        if saved is None:
            raise ConfigError("not_found")
        return saved

    def _field_by_id(self, field_id: int) -> dict[str, Any] | None:
        row = self._one(_FIELD_SELECT + " WHERE f.id = %s", (field_id,))
        if row is None:
            return None
        return _field(row)

    def transformations(self) -> list[dict[str, Any]]:
        rows = self._fetch("SELECT id, name, expression FROM transformations ORDER BY id")
        return [_transformation(row) for row in rows]

    def insert_transformation(self, *, name: str, expression: str) -> dict[str, Any]:
        row = self._one(
            """
            INSERT INTO transformations (name, expression)
            VALUES (%s, %s)
            RETURNING id, name, expression
            """,
            (name, expression),
        )
        if row is None:
            raise ConfigError("conflict")
        return _transformation(row)

    def devices(self) -> list[dict[str, Any]]:
        rows = self._fetch("SELECT id, name, smartnodeid, ipv4, port FROM devices ORDER BY id")
        return [_device(row) for row in rows]

    def insert_device(self, changes: dict[str, Any]) -> dict[str, Any]:
        smart_node_id = changes["smart_node_id"]
        node = self.node(smart_node_id) if isinstance(smart_node_id, int) else None
        if node is None or node["icon_id"] != ICON_SMART_NODE:
            raise ConfigError("not_found")
        row = self._one(
            """
            INSERT INTO devices (name, smartnodeid, ipv4, port)
            VALUES (%s, %s, %s, %s)
            RETURNING id, name, smartnodeid, ipv4, port
            """,
            (changes["name"], smart_node_id, changes["ipv4"], changes["port"]),
        )
        if row is None:
            raise ConfigError("conflict")
        return _device(row)

    def update_device(self, device_id: int, changes: dict[str, Any]) -> dict[str, Any]:
        if self._one("SELECT id FROM devices WHERE id = %s", (device_id,)) is None:
            raise ConfigError("not_found")
        if "smart_node_id" in changes:
            smart_node_id = changes["smart_node_id"]
            node = self.node(smart_node_id) if isinstance(smart_node_id, int) else None
            if node is None or node["icon_id"] != ICON_SMART_NODE:
                raise ConfigError("not_found")
        clause, params = _assignments(changes, _DEVICE_COLUMNS)
        row = self._one(
            f"""
            UPDATE devices SET {clause}
            WHERE id = %s
            RETURNING id, name, smartnodeid, ipv4, port
            """,
            (*params, device_id),
        )
        if row is None:
            raise ConfigError("not_found")
        return _device(row)

    def servers(self) -> list[dict[str, Any]]:
        rows = self._fetch(f"SELECT {_SERVER_PUBLIC} FROM servers ORDER BY id")
        return [_server(row) for row in rows]

    def server(self, server_id: int) -> dict[str, Any] | None:
        row = self._one(
            f"SELECT {_SERVER_PUBLIC} FROM servers WHERE id = %s",
            (server_id,),
        )
        if row is None:
            return None
        return _server(row)

    def insert_server(self, changes: dict[str, Any]) -> dict[str, Any]:
        password = changes["password"]
        if not isinstance(password, str) or password == "" or len(password) > 64:
            raise ConfigError("invalid")
        row = self._one(
            f"""
            INSERT INTO servers (
                name, winname, fullname, ipv4, port, opcservername,
                sqlserverinstance, databasename, username, password
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING {_SERVER_PUBLIC}
            """,
            (
                changes["name"],
                changes["win_name"],
                changes["full_name"],
                changes["ipv4"],
                changes["port"],
                changes["opc_server_name"],
                changes["sql_server_instance"],
                changes["database_name"],
                changes["username"],
                password,
            ),
        )
        if row is None:
            raise ConfigError("conflict")
        return _server(row)

    def update_server(self, server_id: int, changes: dict[str, Any]) -> dict[str, Any]:
        if self.server(server_id) is None:
            raise ConfigError("not_found")
        clause, params = _assignments(changes, _SERVER_COLUMNS)
        row = self._one(
            f"UPDATE servers SET {clause} WHERE id = %s RETURNING {_SERVER_PUBLIC}",
            (*params, server_id),
        )
        if row is None:
            raise ConfigError("not_found")
        return _server(row)

    def input_packet_sizes(self) -> list[dict[str, Any]]:
        rows = self._fetch("SELECT packetid, name, encsize FROM spgetinppacketsizes()")
        return [
            {"packet_id": row["packetid"], "name": row["name"], "enc_size": row["encsize"]}
            for row in rows
        ]

    def stream_packets(self) -> list[dict[str, Any]]:
        rows = self._fetch(
            """
            SELECT p.id, v.name, p.isinput, v.encsize
            FROM packets AS p
            INNER JOIN vartypes AS v ON p.vartypeid = v.id
            ORDER BY p.id
            """
        )
        return [
            {
                "packet_id": row["id"],
                "name": row["name"],
                "is_input": row["isinput"],
                "enc_size": row["encsize"],
            }
            for row in rows
        ]

    def tests(self) -> list[dict[str, Any]]:
        rows = self._fetch(
            """
            SELECT id, name, description, serverid, active, started, stopped, export
            FROM tests
            ORDER BY id
            """
        )
        return [_test(row) for row in rows]

    def insert_test(
        self,
        *,
        name: str,
        description: str | None,
        server_id: int,
    ) -> dict[str, Any]:
        if self.server(server_id) is None:
            raise ConfigError("not_found")
        row = self._one(
            """
            INSERT INTO tests (name, description, serverid, active, export)
            VALUES (%s, %s, %s, false, false)
            RETURNING id, name, description, serverid, active, started, stopped, export
            """,
            (name, description, server_id),
        )
        if row is None:
            raise ConfigError("conflict")
        return _test(row)

    def start_test(self, test_id: int) -> dict[str, Any]:
        if self._one("SELECT id FROM tests WHERE id = %s", (test_id,)) is None:
            raise ConfigError("not_found")
        self._exec("SELECT spteststart(%s)", (test_id,))
        row = self._one(
            """
            SELECT id, name, description, serverid, active, started, stopped, export
            FROM tests WHERE id = %s
            """,
            (test_id,),
        )
        if row is None:
            raise ConfigError("not_found")
        return _test(row)

    def stop_test(self, test_id: int) -> dict[str, Any]:
        if self._one("SELECT id FROM tests WHERE id = %s", (test_id,)) is None:
            raise ConfigError("not_found")
        self._exec("SELECT spteststop(%s)", (test_id,))
        row = self._one(
            """
            SELECT id, name, description, serverid, active, started, stopped, export
            FROM tests WHERE id = %s
            """,
            (test_id,),
        )
        if row is None:
            raise ConfigError("not_found")
        return _test(row)

    def jobs(self, test_id: int) -> list[dict[str, Any]]:
        if self._one("SELECT id FROM tests WHERE id = %s", (test_id,)) is None:
            raise ConfigError("not_found")
        rows = self._fetch(
            """
            SELECT testid, packetid, intfid, done, msg
            FROM jobs
            WHERE testid = %s
            ORDER BY packetid
            """,
            (test_id,),
        )
        return [_job(row) for row in rows]
