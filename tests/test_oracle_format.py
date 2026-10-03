"""Validate Win64 oracle fixtures once the harness starts committing them."""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

ORACLE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "oracle"
SCHEMA_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "oracle.schema.json"


def _validator() -> Draft202012Validator:
    raw: Any = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise AssertionError("oracle schema must be a JSON object")
    Draft202012Validator.check_schema(raw)
    return Draft202012Validator(raw)


def _harness() -> dict[str, str]:
    return {
        "repo": "Goliath-Research/astra-ground-station",
        "git_sha": "0123456789abcdef0123456789abcdef01234567",
        "platform": "win64",
    }


def _reject_floats(value: object, where: str) -> None:
    if value is None or isinstance(value, (str, int)):
        return
    if isinstance(value, float):
        raise AssertionError(f"{where} must be a decimal string, not a JSON float")
    if isinstance(value, list):
        for index, item in enumerate(value):
            _reject_floats(item, f"{where}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise AssertionError(f"{where} has a non-string key")
            _reject_floats(item, f"{where}.{key}")
        return
    raise AssertionError(f"{where} has an unsupported value")


def _validate_document(
    document: dict[str, Any],
    directory: Path,
    validator: Draft202012Validator,
) -> None:
    errors = sorted(validator.iter_errors(document), key=lambda err: list(err.absolute_path))
    if errors:
        raise AssertionError(errors[0].message)
    if document["kind"] == "pack":
        _reject_floats(document["values"], "values")
    if document["kind"] == "dat":
        path = directory / str(document["dat_file"])
        if not path.is_file():
            raise AssertionError(f"missing DAT file {path.name}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != document["sha256"]:
            raise AssertionError(f"sha256 mismatch for {path.name}")


def test_schema_accepts_pack_transform_and_dat(tmp_path: Path) -> None:
    validator = _validator()
    pack = {
        "format_version": 1,
        "case_id": "bool_zero",
        "kind": "pack",
        "description": "bool false packs as a cleared bit.",
        "harness": _harness(),
        "layout": [{"name": "flag", "type_id": 1}],
        "values": [False],
        "packed_hex": "00",
    }
    assert list(validator.iter_errors(pack)) == []
    transform = {
        "format_version": 1,
        "case_id": "transform_1_zero",
        "kind": "transform",
        "description": "TransformOutput id 1 at zero.",
        "harness": _harness(),
        "transform_id": 1,
        "float64_hex": "0000000000000000",
    }
    assert list(validator.iter_errors(transform)) == []
    dat_path = tmp_path / "sample.dat"
    payload = b""
    dat_path.write_bytes(payload)
    dat = {
        "format_version": 1,
        "case_id": "empty_dat",
        "kind": "dat",
        "description": "Harness DAT with an empty body.",
        "harness": _harness(),
        "dat_file": "sample.dat",
        "sha256": hashlib.sha256(payload).hexdigest(),
    }
    assert list(validator.iter_errors(dat)) == []
    _validate_document(dat, tmp_path, validator)
    pack["values"] = [1.5]
    assert list(validator.iter_errors(pack)) == []
    with pytest.raises(AssertionError, match="JSON float"):
        _reject_floats(pack["values"], "values")


def test_committed_oracle_files_match_contract() -> None:
    validator = _validator()
    for path in sorted(ORACLE_ROOT.glob("*.json")):
        document: Any = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise AssertionError(f"{path.name} must be a JSON object")
        _validate_document(document, path.parent, validator)
