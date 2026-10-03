# Golden fixtures

There are no legacy `.DAT` captures. Numeric and byte-level agreement with
the Delphi application comes from a Win64 harness that lives in the legacy
repository, [Goliath-Research/astra-ground-station](https://github.com/Goliath-Research/astra-ground-station).
That harness builds against the Delphi code. This repository only stores its
output.

No fixtures are checked in yet. `tests/test_golden_format.py` validates every
`case.json` under this directory against `case.schema.json`, checks SHA-256
digests, and rejects JSON floats in decoded fields.

## Layout

```
tests/golden/<suite>/<case_id>/case.json
tests/golden/<suite>/<case_id>/<file>
```

`<suite>` is one of `codec`, `telemetry_decoder`, `telemetry_encoder`, or
`exporter`. `<case_id>` matches `[a-z0-9_]+` and must equal `case_id` inside
the JSON. Adding a suite means updating the enum in `case.schema.json`.

Binary inputs and expected byte strings are sibling files of `case.json`.
Paths are a single filename: no directories, no `..`.

## case.json

`format_version` is `1`.

```json
{
  "format_version": 1,
  "case_id": "empty_payload",
  "suite": "codec",
  "description": "Delphi codec decode of a zero-length payload frame.",
  "harness": {
    "repo": "Goliath-Research/astra-ground-station",
    "git_sha": "0123456789abcdef0123456789abcdef01234567",
    "harness_version": "0.1.0",
    "built_at": "2026-01-15T12:00:00Z",
    "platform": "win64"
  },
  "inputs": [
    {
      "name": "frame",
      "path": "frame.bin",
      "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    }
  ],
  "expected": {
    "kind": "fields",
    "fields": { "payload_length": 0 }
  }
}
```

`harness.git_sha` is the full 40-character commit of the legacy repo that
produced the file. `harness.platform` is always `win64`. `built_at` is UTC
`YYYY-MM-DDTHH:MM:SSZ`.

`expected.kind` is either:

- `fields` — JSON object of values the Delphi code exposes after decode or
  after a round trip. Future tests compare these exactly.
- `bytes` — a `file` object, same shape as an input, whose bytes are what
  the Delphi encoder emitted.

## Values

- Multi-byte integers inside `.bin` files are little-endian, matching the
  Win64 Delphi code. The JSON does not restate endianness per field.
- Integers in `fields` are JSON integers.
- Fractional quantities are decimal strings (`"12.50"`), not JSON floats.
  JSON numbers with a fraction are rejected so a parser cannot change them.
- Booleans and `null` are allowed. Timestamps are UTC ISO-8601 strings.
- Do not put secrets, credentials, or rows from production logs in a fixture.
  `02_data.sql` is not a fixture source.

## Other checks

Property tests (Hypothesis) and simulated devices cover behavior that has no
Delphi oracle yet. A fixture is the oracle for one case, not a replacement
for those tests.
