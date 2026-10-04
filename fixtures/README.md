# Fixtures

There are no legacy `.DAT` captures, packet captures, or exported test tables.
`docs/MIGRATION.md` §6 is the source for how this tree is filled. The copy in
the legacy repository wins if the two migration documents ever differ.

## `fixtures/oracle/`

A Win64 console harness, built in the legacy repository against the Delphi
codec, writes this directory. It does not need `AstraConfig`. Regenerate the
files only from a Win64 build. A Win32 build is the wrong oracle.

Nothing is checked in yet. `tests/test_oracle_format.py` validates every
`*.json` file here against `fixtures/oracle.schema.json`.

Three kinds of JSON, one file per case:

| `kind` | What the harness recorded |
| --- | --- |
| `pack` | `layout`, `values`, and `packed_hex` (lowercase hex of the payload bytes) for `SavePacket` / `LoadPacket`. Cover type ids 1–14, a `u12` that starts at bit offset 4, arrays, a nested record, and `ovr_` bits. |
| `transform` | `transform_id` 1–14 and `float64_hex`, the exact 8-byte little-endian IEEE-754 result of `TransformOutput`, not a decimal. Also record the OPC substitution of a Single/Double zero with `1e-7` when that case is the one being captured. |
| `dat` | `dat_file` and `sha256` of a sibling `.DAT` written through `TAstraBinLogFile`. Header magic `0x1A2B`, check `0xE5C4`, 20-byte little-endian header, then an OLE `TDateTime` (`1899-12-30`, naive local time) and `RecSize` payload bytes. |

Fractional `values` are decimal strings, not JSON floats. Multi-byte payload
integers are little-endian. Do not put secrets or production rows in a fixture.

`fixtures/live/` is for pcaps and `.DAT` files captured on the Linux host
after the first real vehicle test. It is empty on purpose. The bench path
is `python -m astra.cli.device` into `LocalRecorder`, which writes a `.DAT`
under a temporary directory and replays it in `tests/test_bridge_capture.py`.
Do not check in a synthetic capture as if it were that vehicle test.
