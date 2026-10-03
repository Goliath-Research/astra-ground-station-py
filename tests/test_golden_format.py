"""Validate the Win64 harness fixture contract.

Committed fixtures, once they exist, must match ``tests/golden/case.schema.json``.
A synthetic case in a temp directory locks the same rules.
"""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

GOLDEN_ROOT = Path(__file__).resolve().parent / "golden"
SCHEMA_PATH = GOLDEN_ROOT / "case.schema.json"

_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def _validator() -> Draft202012Validator:
    raw: Any = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise AssertionError("golden schema must be a JSON object")
    Draft202012Validator.check_schema(raw)
    return Draft202012Validator(raw)


def _sample_case() -> dict[str, Any]:
    return {
        "format_version": 1,
        "case_id": "empty_payload",
        "suite": "codec",
        "description": "Decode of a zero-length payload.",
        "harness": {
            "repo": "Goliath-Research/astra-ground-station",
            "git_sha": "0123456789abcdef0123456789abcdef01234567",
            "harness_version": "0.1.0",
            "built_at": "2026-01-15T12:00:00Z",
            "platform": "win64",
        },
        "inputs": [{"name": "frame", "path": "frame.bin", "sha256": _SHA256}],
        "expected": {"kind": "fields", "fields": {"payload_length": 0}},
    }


def _reject_floats(value: object, where: str) -> None:
    if value is None or isinstance(value, (str, int, bool)):
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


def _check_file(case_dir: Path, entry: dict[str, Any]) -> None:
    path = case_dir / str(entry["path"])
    if not path.is_file():
        raise AssertionError(f"missing fixture file {path.name}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != entry["sha256"]:
        raise AssertionError(f"sha256 mismatch for {path.name}")


def validate_case_dir(case_dir: Path, validator: Draft202012Validator) -> None:
    document_path = case_dir / "case.json"
    document: Any = json.loads(document_path.read_text(encoding="utf-8"))
    errors = sorted(validator.iter_errors(document), key=lambda err: list(err.absolute_path))
    if errors:
        raise AssertionError(errors[0].message)
    if not isinstance(document, dict):
        raise AssertionError("case.json must be an object")
    suite = case_dir.parent.name
    if document["suite"] != suite:
        raise AssertionError(f"{document_path} suite does not match directory {suite}")
    if document["case_id"] != case_dir.name:
        raise AssertionError(f"{document_path} case_id does not match directory name")
    for entry in document["inputs"]:
        _check_file(case_dir, entry)
    expected = document["expected"]
    if expected["kind"] == "fields":
        _reject_floats(expected["fields"], "expected.fields")
    else:
        _check_file(case_dir, expected["file"])


def test_schema_accepts_a_valid_case_and_rejects_a_float() -> None:
    validator = _validator()
    sample = _sample_case()
    assert list(validator.iter_errors(sample)) == []
    # JSON Schema still accepts a fractional number. The harness contract does not.
    sample["expected"]["fields"]["scale"] = 1.5
    assert list(validator.iter_errors(sample)) == []
    with pytest.raises(AssertionError, match="JSON float"):
        _reject_floats(sample["expected"]["fields"], "expected.fields")


def test_synthetic_case_directory(tmp_path: Path) -> None:
    case_dir = tmp_path / "codec" / "empty_payload"
    case_dir.mkdir(parents=True)
    (case_dir / "frame.bin").write_bytes(b"")
    (case_dir / "case.json").write_text(json.dumps(_sample_case()), encoding="utf-8")
    validate_case_dir(case_dir, _validator())


def test_sha256_mismatch_is_rejected(tmp_path: Path) -> None:
    case_dir = tmp_path / "codec" / "empty_payload"
    case_dir.mkdir(parents=True)
    (case_dir / "frame.bin").write_bytes(b"nope")
    (case_dir / "case.json").write_text(json.dumps(_sample_case()), encoding="utf-8")
    with pytest.raises(AssertionError, match="sha256"):
        validate_case_dir(case_dir, _validator())


def test_committed_fixtures_match_contract() -> None:
    validator = _validator()
    for document_path in sorted(GOLDEN_ROOT.rglob("case.json")):
        validate_case_dir(document_path.parent, validator)
