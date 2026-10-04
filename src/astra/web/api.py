"""JSON routes for the configurator and the test manager.

Send and Rate are not columns. The Delphi packet grid kept them in a
memory table that started at Send false and Rate 0 and was never saved.
This process does the same: ``PUT /api/stream/{packet_id}`` updates a
table on the app, and a restart clears it.

Hardware icons 8, 9, and 10 are not created. That editor is phase 8.
"""

from __future__ import annotations

import json
import logging
import secrets
from collections.abc import Iterator
from typing import Annotated, Any, assert_never

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.responses import Response

from astra.db.config_repo import ConfigRepo
from astra.db.connection import connect
from astra.db.errors import ConfigCode, ConfigError, DatabaseConfigError
from astra.opcua import tag_path
from astra.web.csv_text import csv_document
from astra.web.parse import (
    as_bool,
    as_int,
    as_opt_int,
    as_opt_str,
    as_password,
    as_str,
    object_body,
    reject_unknown,
    require_fields,
)
from astra.web.settings import WebSettings

_log = logging.getLogger("astra.web")

router = APIRouter(prefix="/api")

_TREE_KEYS = frozenset({"name", "parent_id", "icon_id", "seq"})
_PACKET_KEYS = frozenset({"packet_id", "name", "is_input"})
_VAR_TYPE_KEYS = frozenset({"name", "description", "short_name", "enc_size", "dec_size"})
_FIELD_KEYS = frozenset(
    {
        "name",
        "qty",
        "type_id",
        "initial_value",
        "seq",
        "override",
        "in_sequence",
        "description",
        "short_name",
        "transformation_id",
    }
)
_DEVICE_KEYS = frozenset({"name", "smart_node_id", "ipv4", "port"})
_SERVER_KEYS = frozenset(
    {
        "name",
        "win_name",
        "full_name",
        "ipv4",
        "port",
        "opc_server_name",
        "sql_server_instance",
        "database_name",
        "username",
        "password",
    }
)
_TEST_KEYS = frozenset({"name", "description", "server_id"})
_STREAM_KEYS = frozenset({"send", "rate"})

_INTERFACE_COLUMNS = (
    "varorder",
    "recordname",
    "recorddescription",
    "fieldname",
    "arraylen",
    "typename",
    "fielddescription",
    "override",
    "insequence",
)
_MAPPING_COLUMNS = (
    "fieldid",
    "connectionid",
    "fieldorder",
    "connectionorder",
    "area",
    "board",
    "firstpin",
    "interface",
    "record",
    "qty",
    "field",
    "shortname",
    "description",
)


def http_status(code: ConfigCode) -> int:
    """Map a config error code to an HTTP status."""
    if code == "invalid":
        return 400
    if code == "not_found":
        return 404
    if code == "conflict":
        return 409
    assert_never(code)


def require_operator(request: Request) -> None:
    """Reject ``/api`` calls unless ``ASTRA_WEB_TOKEN`` matches.

    ``GET /health`` does not use this dependency. A missing or short token
    fails closed. The header value is not copied into the response.
    """
    settings: WebSettings = request.app.state.web_settings
    if settings.token is None:
        detail = settings.token_error or "ASTRA_WEB_TOKEN is not set"
        raise HTTPException(status_code=503, detail=detail)
    header = request.headers.get("authorization")
    if header is None or not _bearer_matches(settings.token, header):
        raise HTTPException(status_code=401, detail="unauthorized")


def _bearer_matches(expected: str, header: str) -> bool:
    prefix = "Bearer "
    if not header.startswith(prefix):
        return False
    presented = header[len(prefix) :]
    return secrets.compare_digest(presented, expected)


def get_repo(request: Request) -> Iterator[ConfigRepo]:
    """Authorize, then open one transaction and commit when it succeeds."""
    require_operator(request)
    settings: WebSettings = request.app.state.web_settings
    if settings.database_url is None:
        detail = settings.database_error or "database is not configured"
        raise HTTPException(status_code=503, detail=detail)
    try:
        conn = connect(settings.database_url)
    except DatabaseConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    repo = ConfigRepo(conn)
    try:
        yield repo
        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    except ConfigError as exc:
        conn.rollback()
        raise HTTPException(status_code=http_status(exc.code), detail=exc.code) from None
    except psycopg.errors.ForeignKeyViolation:
        conn.rollback()
        raise HTTPException(status_code=409, detail="conflict") from None
    except psycopg.errors.UniqueViolation:
        conn.rollback()
        raise HTTPException(status_code=409, detail="conflict") from None
    except psycopg.Error:
        conn.rollback()
        raise HTTPException(status_code=500, detail="database error") from None
    finally:
        conn.close()


async def _body(request: Request) -> dict[str, Any]:
    try:
        payload: Any = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="invalid") from None
    try:
        return object_body(payload)
    except ConfigError as exc:
        raise HTTPException(status_code=http_status(exc.code), detail=exc.code) from None


def _saved(kind: str, item_id: int) -> None:
    _log.info("%s %s saved", kind, item_id)


Repo = Annotated[ConfigRepo, Depends(get_repo)]


@router.get("/tree")
def list_tree(repo: Repo) -> list[dict[str, Any]]:
    return repo.tree()


@router.post("/tree", status_code=201)
async def create_tree(
    request: Request,
    repo: Repo,
) -> dict[str, Any]:
    body = await _body(request)
    reject_unknown(body, _TREE_KEYS)
    require_fields(body, frozenset({"name", "icon_id"}))
    parent_id = as_opt_int(body["parent_id"]) if "parent_id" in body else None
    seq = as_opt_int(body["seq"], minimum=1) if "seq" in body else None
    return repo.insert_node(
        name=as_str(body["name"], 50),
        parent_id=parent_id,
        icon_id=as_int(body["icon_id"]),
        seq=seq,
    )


@router.patch("/tree/{node_id}")
async def patch_tree(
    node_id: int,
    request: Request,
    repo: Repo,
) -> dict[str, Any]:
    body = await _body(request)
    reject_unknown(body, frozenset({"name", "seq"}))
    if not body:
        raise ConfigError("invalid")
    name = as_str(body["name"], 50) if "name" in body else None
    seq = as_int(body["seq"], minimum=1) if "seq" in body else None
    return repo.update_node(node_id, name=name, seq=seq)


@router.delete("/tree/{node_id}", status_code=204)
def remove_tree(node_id: int, repo: Repo) -> Response:
    repo.delete_node(node_id)
    return Response(status_code=204)


@router.post("/tree/{node_id}/duplicate", status_code=201)
def duplicate_tree(node_id: int, repo: Repo) -> dict[str, Any]:
    return repo.duplicate_node(node_id)


@router.get("/nodes/{node_id}/mappings")
def list_mappings(node_id: int, repo: Repo) -> list[dict[str, Any]]:
    return repo.mappings(node_id)


@router.post("/mappings")
async def create_mapping(request: Request, repo: Repo) -> dict[str, Any]:
    body = await _body(request)
    reject_unknown(body, frozenset({"field_id", "connection_id"}))
    require_fields(body, frozenset({"field_id", "connection_id"}))
    return repo.add_mapping(
        field_id=as_int(body["field_id"], minimum=1),
        connection_id=as_int(body["connection_id"], minimum=1),
    )


@router.delete("/mappings/{field_id}")
def remove_mapping(field_id: int, repo: Repo) -> dict[str, Any]:
    return repo.delete_mapping(field_id)


def _csv_response(document: str, filename: str) -> Response:
    return Response(
        content=document,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/nodes/{node_id}/exports/simulink")
def export_simulink(node_id: int, repo: Repo) -> Response:
    """Simulink interface CSV from ``spgetinterface``."""
    return _csv_response(
        csv_document(_INTERFACE_COLUMNS, repo.interface_rows(node_id)),
        "simulink.csv",
    )


@router.get("/nodes/{node_id}/exports/mapping")
def export_mapping(node_id: int, repo: Repo) -> Response:
    """Mapping CSV from ``spgetmappingwithorders``."""
    return _csv_response(
        csv_document(_MAPPING_COLUMNS, repo.mapping_rows(node_id)),
        "mapping.csv",
    )


@router.get("/nodes/{node_id}/exports/opcua")
def export_opcua(node_id: int, repo: Repo) -> Response:
    """OPC UA node list the bridge publishes, one ``Astra{packet}/{field}`` per line."""
    packet = repo.packet(node_id)
    if packet is None or not isinstance(packet["name"], str):
        raise ConfigError("not_found")
    names = [
        row["fieldname"]
        for row in repo.interface_rows(node_id)
        if isinstance(row["fieldname"], str)
    ]
    lines = [tag_path(packet["name"], name) for name in names]
    body = "\n".join(lines)
    if lines:
        body += "\n"
    return Response(
        content=body,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="opcua-nodes.txt"'},
    )


@router.get("/nodes/{node_id}/packet")
def get_packet(node_id: int, repo: Repo) -> dict[str, Any]:
    found = repo.packet(node_id)
    if found is None:
        raise ConfigError("not_found")
    return found


@router.put("/nodes/{node_id}/packet")
async def put_packet(
    node_id: int,
    request: Request,
    repo: Repo,
) -> dict[str, Any]:
    body = await _body(request)
    reject_unknown(body, _PACKET_KEYS)
    require_fields(body, _PACKET_KEYS)
    saved = repo.set_packet(
        node_id,
        packet_id=as_int(body["packet_id"], minimum=1),
        name=as_str(body["name"], 50),
        is_input=as_bool(body["is_input"]),
    )
    saved_id = saved["packet_id"]
    if isinstance(saved_id, int):
        _saved("packet", saved_id)
    return saved


@router.post("/nodes/{node_id}/sizes")
def post_sizes(node_id: int, repo: Repo) -> list[dict[str, Any]]:
    return repo.calc_sizes(node_id)


@router.get("/scopes/{scope_id}/vartypes")
def list_var_types(scope_id: int, repo: Repo) -> list[dict[str, Any]]:
    return repo.var_types(scope_id)


@router.post("/scopes/{scope_id}/vartypes", status_code=201)
async def create_var_type(
    scope_id: int,
    request: Request,
    repo: Repo,
) -> dict[str, Any]:
    body = await _body(request)
    reject_unknown(body, _VAR_TYPE_KEYS)
    require_fields(body, frozenset({"name"}))
    return repo.insert_var_type(
        scope_id,
        name=as_str(body["name"], 50),
        description=as_opt_str(body["description"], 128) if "description" in body else None,
        short_name=as_opt_str(body["short_name"], 16) if "short_name" in body else None,
        enc_size=as_opt_int(body["enc_size"], minimum=0) if "enc_size" in body else None,
        dec_size=as_opt_int(body["dec_size"], minimum=0) if "dec_size" in body else None,
    )


@router.get("/vartypes/{var_type_id}/fields")
def list_fields(var_type_id: int, repo: Repo) -> list[dict[str, Any]]:
    return repo.fields(var_type_id)


@router.post("/vartypes/{var_type_id}/fields", status_code=201)
async def create_field(
    var_type_id: int,
    request: Request,
    repo: Repo,
) -> dict[str, Any]:
    body = await _body(request)
    reject_unknown(body, _FIELD_KEYS)
    require_fields(body, frozenset({"name", "type_id"}))
    changes: dict[str, Any] = {
        "name": as_str(body["name"], 50),
        "type_id": as_int(body["type_id"], minimum=1),
        "qty": as_int(body["qty"], minimum=1) if "qty" in body else 1,
    }
    if "initial_value" in body:
        changes["initial_value"] = as_opt_str(body["initial_value"], 128)
    if "seq" in body:
        changes["seq"] = as_opt_int(body["seq"])
    if "override" in body:
        changes["override"] = as_bool(body["override"])
    if "in_sequence" in body:
        changes["in_sequence"] = as_bool(body["in_sequence"])
    if "description" in body:
        changes["description"] = as_opt_str(body["description"], 128)
    if "short_name" in body:
        changes["short_name"] = as_opt_str(body["short_name"], 16)
    if "transformation_id" in body:
        changes["transformation_id"] = as_opt_int(body["transformation_id"], minimum=1)
    return repo.insert_field(var_type_id, changes)


@router.patch("/fields/{field_id}")
async def patch_field(
    field_id: int,
    request: Request,
    repo: Repo,
) -> dict[str, Any]:
    body = await _body(request)
    reject_unknown(body, _FIELD_KEYS)
    if not body:
        raise ConfigError("invalid")
    changes: dict[str, Any] = {}
    if "name" in body:
        changes["name"] = as_str(body["name"], 50)
    if "qty" in body:
        changes["qty"] = as_int(body["qty"], minimum=1)
    if "type_id" in body:
        changes["type_id"] = as_int(body["type_id"], minimum=1)
    if "initial_value" in body:
        changes["initial_value"] = as_opt_str(body["initial_value"], 128)
    if "seq" in body:
        changes["seq"] = as_opt_int(body["seq"])
    if "override" in body:
        changes["override"] = as_bool(body["override"])
    if "in_sequence" in body:
        changes["in_sequence"] = as_bool(body["in_sequence"])
    if "description" in body:
        changes["description"] = as_opt_str(body["description"], 128)
    if "short_name" in body:
        changes["short_name"] = as_opt_str(body["short_name"], 16)
    if "transformation_id" in body:
        changes["transformation_id"] = as_opt_int(body["transformation_id"], minimum=1)
    return repo.update_field(field_id, changes)


@router.get("/transformations")
def list_transformations(repo: Repo) -> list[dict[str, Any]]:
    return repo.transformations()


@router.post("/transformations", status_code=201)
async def create_transformation(
    request: Request,
    repo: Repo,
) -> dict[str, Any]:
    body = await _body(request)
    reject_unknown(body, frozenset({"name", "expression"}))
    require_fields(body, frozenset({"name", "expression"}))
    return repo.insert_transformation(
        name=as_str(body["name"], 50),
        expression=as_str(body["expression"], 128),
    )


@router.get("/devices")
def list_devices(repo: Repo) -> list[dict[str, Any]]:
    return repo.devices()


@router.post("/devices", status_code=201)
async def create_device(
    request: Request,
    repo: Repo,
) -> dict[str, Any]:
    body = await _body(request)
    reject_unknown(body, _DEVICE_KEYS)
    require_fields(body, frozenset({"name", "smart_node_id", "ipv4"}))
    return repo.insert_device(
        {
            "name": as_str(body["name"], 64),
            "smart_node_id": as_int(body["smart_node_id"], minimum=1),
            "ipv4": as_str(body["ipv4"], 15),
            "port": as_int(body["port"], minimum=1, maximum=65535) if "port" in body else 2357,
        }
    )


@router.patch("/devices/{device_id}")
async def patch_device(
    device_id: int,
    request: Request,
    repo: Repo,
) -> dict[str, Any]:
    body = await _body(request)
    reject_unknown(body, _DEVICE_KEYS)
    if not body:
        raise ConfigError("invalid")
    changes: dict[str, Any] = {}
    if "name" in body:
        changes["name"] = as_str(body["name"], 64)
    if "smart_node_id" in body:
        changes["smart_node_id"] = as_int(body["smart_node_id"], minimum=1)
    if "ipv4" in body:
        changes["ipv4"] = as_str(body["ipv4"], 15)
    if "port" in body:
        changes["port"] = as_int(body["port"], minimum=1, maximum=65535)
    return repo.update_device(device_id, changes)


@router.get("/servers")
def list_servers(repo: Repo) -> list[dict[str, Any]]:
    return repo.servers()


@router.post("/servers", status_code=201)
async def create_server(
    request: Request,
    repo: Repo,
) -> dict[str, Any]:
    body = await _body(request)
    reject_unknown(body, _SERVER_KEYS)
    require_fields(body, _SERVER_KEYS - {"port"})
    saved = repo.insert_server(
        {
            "name": as_str(body["name"], 50),
            "win_name": as_str(body["win_name"], 64),
            "full_name": as_str(body["full_name"], 128),
            "ipv4": as_str(body["ipv4"], 15),
            "port": as_int(body["port"], minimum=1, maximum=65535) if "port" in body else 2357,
            "opc_server_name": as_str(body["opc_server_name"], 128),
            "sql_server_instance": as_str(body["sql_server_instance"], 128),
            "database_name": as_str(body["database_name"], 64),
            "username": as_str(body["username"], 64),
            "password": as_password(body["password"]),
        }
    )
    server_id = saved["id"]
    if isinstance(server_id, int):
        _saved("server", server_id)
    return saved


@router.patch("/servers/{server_id}")
async def patch_server(
    server_id: int,
    request: Request,
    repo: Repo,
) -> dict[str, Any]:
    body = await _body(request)
    reject_unknown(body, _SERVER_KEYS)
    if not body:
        raise ConfigError("invalid")
    changes: dict[str, Any] = {}
    if "name" in body:
        changes["name"] = as_str(body["name"], 50)
    if "win_name" in body:
        changes["win_name"] = as_str(body["win_name"], 64)
    if "full_name" in body:
        changes["full_name"] = as_str(body["full_name"], 128)
    if "ipv4" in body:
        changes["ipv4"] = as_str(body["ipv4"], 15)
    if "port" in body:
        changes["port"] = as_int(body["port"], minimum=1, maximum=65535)
    if "opc_server_name" in body:
        changes["opc_server_name"] = as_str(body["opc_server_name"], 128)
    if "sql_server_instance" in body:
        changes["sql_server_instance"] = as_str(body["sql_server_instance"], 128)
    if "database_name" in body:
        changes["database_name"] = as_str(body["database_name"], 64)
    if "username" in body:
        changes["username"] = as_str(body["username"], 64)
    if "password" in body:
        changes["password"] = as_password(body["password"])
    saved = repo.update_server(server_id, changes)
    _saved("server", server_id)
    return saved


@router.get("/packets/input-sizes")
def list_input_sizes(repo: Repo) -> list[dict[str, Any]]:
    return repo.input_packet_sizes()


@router.get("/stream")
def list_stream(
    request: Request,
    repo: Repo,
) -> list[dict[str, Any]]:
    table: dict[int, tuple[bool, int]] = request.app.state.stream
    rows: list[dict[str, Any]] = []
    for packet in repo.stream_packets():
        packet_id = packet["packet_id"]
        if not isinstance(packet_id, int):
            continue
        send, rate = table.get(packet_id, (False, 0))
        rows.append({**packet, "send": send, "rate": rate})
    return rows


@router.put("/stream/{packet_id}")
async def put_stream(
    packet_id: int,
    request: Request,
    repo: Repo,
) -> dict[str, Any]:
    body = await _body(request)
    reject_unknown(body, _STREAM_KEYS)
    require_fields(body, _STREAM_KEYS)
    known = {row["packet_id"] for row in repo.stream_packets()}
    if packet_id not in known:
        raise ConfigError("not_found")
    send = as_bool(body["send"])
    rate = as_int(body["rate"], minimum=0)
    table: dict[int, tuple[bool, int]] = request.app.state.stream
    table[packet_id] = (send, rate)
    _saved("stream", packet_id)
    return {"packet_id": packet_id, "send": send, "rate": rate}


@router.get("/tests")
def list_tests(repo: Repo) -> list[dict[str, Any]]:
    return repo.tests()


@router.post("/tests", status_code=201)
async def create_test(
    request: Request,
    repo: Repo,
) -> dict[str, Any]:
    body = await _body(request)
    reject_unknown(body, _TEST_KEYS)
    require_fields(body, frozenset({"name", "server_id"}))
    return repo.insert_test(
        name=as_str(body["name"], 64),
        description=as_opt_str(body["description"], 256) if "description" in body else None,
        server_id=as_int(body["server_id"], minimum=1),
    )


@router.post("/tests/{test_id}/start")
def start_test(test_id: int, repo: Repo) -> dict[str, Any]:
    return repo.start_test(test_id)


@router.post("/tests/{test_id}/stop")
def stop_test(test_id: int, repo: Repo) -> dict[str, Any]:
    return repo.stop_test(test_id)


@router.get("/tests/{test_id}/jobs")
def list_jobs(test_id: int, repo: Repo) -> list[dict[str, Any]]:
    return repo.jobs(test_id)


@router.get("/tests/{test_id}/packets/{packet_id}/log")
def get_test_log(
    test_id: int,
    packet_id: int,
    repo: Repo,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Page a finished job's ``testlog`` table. A job that is not done is a conflict."""
    if limit < 1 or limit > 200 or offset < 0:
        raise ConfigError("invalid")
    return repo.log_page(test_id, packet_id, limit=limit, offset=offset)


@router.get("/tests/{test_id}/packets/{packet_id}/log.csv")
def get_test_log_csv(test_id: int, packet_id: int, repo: Repo) -> Response:
    """CSV of a finished job. Same `;` quoting as the configurator exports."""
    table, columns, rows = repo.log_csv(test_id, packet_id)
    return _csv_response(csv_document(tuple(columns), rows), f"{table}.csv")
