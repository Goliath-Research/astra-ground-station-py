# Astra codec spec

Transcribed from astra-ground-station `docs/CODEC_SPEC.md` (PR #6). That
document was traced from the Delphi sources. The line numbers below are the
ones given with that transcription. The 29 golden vectors are in
`tests/data/codec_vectors.json`, transcribed from
`docs/codec_vectors.json` in the same PR.

## Bit packing

`TBitStream.SaveBit` (`AstraCommon/AstraVarPacket.pas` 301-319) writes
least-significant bit first inside each byte. Multi-byte values are
little-endian. `TAstraVarPacket.SavePacket` (1042-1092) zeroes the buffer,
then concatenates fields with no padding between them (the `Qty` loop is
1062-1066). The final byte is zero-padded. An exception in `SavePacket` is
only logged (1083-1087). There is no checksum, CRC, or `0xEB25` sync on the
live path.

`TVehicleDataType.SaveValue` (487-640) stores the in-memory value.
`SaveSingle` / `SaveDouble` (598-630) are IEEE-754, including NaN. Q types
are not scaled: an `i32q8` of 256 is the integer 256. `IsValidValue`
(185-188) turns null into 0. Out-of-range integers keep the low bits of the
destination width (`{$R+}` is not enabled): 300 as `u8` is `2c`. A
non-numeric value raises; the exception class is not named in the source.

`u12` `0x0ABC` (2748) packs as `bc0a`. The same value after a true bool
packs as `7915`.

## Fields, arrays, overrides

`LoadFields` (703-790) walks the configurator tree. `LoadField` (727-749)
emits one leaf. A nested record (`TypeID > 100`) is flattened in field order
and is not byte-aligned. An array of records is expanded (781-783) into
leaves `name_0_a`, `name_1_a`, and so on, packed back to back.

`LoadFieldOvrs` (792-822) then appends one 1-bit bool `ovr_<leaf>` at the
end of that whole flattened list, for each leaf with `Ovr` set, in leaf
order. An array leaf (`Qty > 1`) gets one bit, not one per element. A record
node is not in the leaf list, so `Override` on a record row is not emitted.
Those bits still sit at the very end when the leaves came from an array of
records.

`BuildEmptyPacket` (980-1001) allocates the zeroed buffer `SavePacket` fills.

## UDP framing and `t_ms`

`AstraCommon/AstraNetPacket.pas`: `GetIdPayload` (64-70) and `SetIdPayload`
(92-98) are a signed int32 little-endian packet id plus the packed payload.
`GetDeviceT_MS` (110-117) reads the first four payload bytes as a signed
int32. It does not look up a field.

The bridge accept check uses that same four-byte read and drops the datagram
when the value is less than or equal to the device's last `t_ms` (signed
compare). The order is: known interface id, `len(payload)` equals the
interface packet size, peer IP matches the device row, then `t_ms` strictly
increased.

## Transforms and OPC

`TransformOutput` (1130-1156) is binary64, applied on receive before the
`1e-7` step, and is not called from `SavePacket`. The id-1 polynomial is the
Horner form `-249.5 + x*(0.1987 + x*(-7.47E-6 + 4.45E-8*x))`.

| Id | Result |
| --- | --- |
| 1 | `-249.5 + x*(0.1987 + x*(-7.47e-6 + 4.45e-8*x))` |
| 2 | `-62.5 + 0.07631*x` |
| 3 | `-250 + 0.3053*x` |
| 4 | `-2500 + 3.053*x` |
| 5 | `0.008057*x` |
| 6 | `0.007727*x` |
| 7 | `0.0031746*x` |
| 8 | `-4.1086 + 0.00498*x` |
| 9 | `0.1*x` |
| 10 | `100*x/1023` |
| 11 | `x` |
| 12 | `0.1*x` |
| 13 | `10*x` |
| 14 | `0.001*x` |
| other | `x` |

Samples `(id, x, y, y_f64_le_hex)`, none of which take the OPC substitution:
`(1, 1000.0, -13.77000000000001, 10d7a3703d8a2bc0)`,
`(1, 0.0, -249.5, 0000000000306fc0)`,
`(2, 1000.0, 13.810000000000002, 2085eb51b89e2b40)`,
`(10, 1023.0, 100.0, 0000000000005940)`,
`(11, 5.0, 5.0, 0000000000001440)`,
`(14, 2500.0, 2.5, 0000000000000440)`.

`TransformInput` (1102-1128), the id-1 cube-root inverse, is never called.
L2R packs OPC values as they arrive. The migrated database has no
`TransformationID` on any L2R field, so the send path never inverse-transforms
engineering units. See `docs/CODEC_DB_ANSWERS.md`.

`AstraInpPopper.SyncWrite` (95-120) runs `TransformOutput`, then if the OPC
type is `Single` or `Double` and `v == 0` exactly, sets `v = 1e-7`
(100-116). NaN is not replaced. `GetOpcType` (1188-1197) returns `Double`
when `TransformationID > 0`, otherwise the type's OPC name, and
`Array of ...` when `Qty > 1`. The substitution therefore applies to scalar
`f32`, scalar `f64`, and any scalar with a non-zero transform. It does not
apply to arrays or to untransformed integers, and it is not written back
into the packet.

## Minor frame

The minor frame is a normal Astra packet named IRIG106. The default layout
is the migrated config database, and it is the same for Stage 1 and Stage 2:
`fap` (nested FAP, 160 bits), `fsp` u32, `sf_id` u8, `row_id` u32,
`range_variables` u8[120], `packet_stream` u8[200]. That is 28 leaves, 2792
bits, and 349 bytes, with no pad. The codec reads `sf_id`, `row_id`, and
`packet_stream` by name. The other fields pass through. Offsets and the
packets that can ride in `packet_stream` are in `docs/CODEC_DB_ANSWERS.md`.

The transcribed vectors in this file use the smaller fixture `sf_id: u8`,
`row_id: i32`, `packet_stream: u8[4]`. That fixture is not the default. It
is packed with `SavePacket`. The bytes inside `packet_stream` come from
the encoder's `PacketStream` buffer.

`AstraTMEncoder/_AstraTMEncoder.pas` `BuildPacketStream` (168-210): before
`Sequence` increments, a packet is included when
`(Sequence = 0) or (Sequence * PacketRate mod IRIGRate = 0)`. A rate of 0 is
always included. An IRIG rate of 0 is a divide by zero. At IRIG rate 200,
for rates `{0, 1, 10, 100, 200}`:

| Sequence | Included rates |
| --- | --- |
| 0 | 0, 1, 10, 100, 200 |
| 1 | 0, 200 |
| 2 | 0, 100, 200 |
| 20 | 0, 10, 100, 200 |
| 200 | 0, 1, 10, 100, 200 |

For each included packet the encoder appends a 4-byte signed little-endian
id and `EncSize` zero bytes. Only the id is moved. If `PacketStream` still
has bytes, `BuildPacketStream` only does `Inc(SubFrameID)` and returns.
Otherwise it builds a new stream, then `Inc(Sequence)` (208), and
`SubFrameID` becomes 1. `Sequence` is set to 0 at line 145. That new build
is the next major frame: `row_id` increments, except on the first build,
which keeps the starting row. `PushStream` opens a major frame only when
`row_id` increases, so the restarted `SubFrameID` of 1 has to arrive on a
new row. The two fixture frames share row 1 because the second call only
does `Inc(SubFrameID)`.

`Timer1Timer` (212-276) copies `min(len(stream), len(packet_stream))` bytes
into the field, zero-fills the rest, deletes the copied prefix (236-250),
and sends the packed IRIG106 packet with no id prefix (272) to listen port
`2357 + stage` (294-296). The port is `ASTRA_BRIDGE_PORT + stage`.

## Decoder

`AstraTMoIP/AstraDecoder.pas`:

- `TAstraStageDecoder.Create` (138) sets `FPacketID = 100 * (stage - 1) + 106`.
  The decoder logs the raw minor-frame datagram under that id (reads
  260-262, `IdUDPServerUDPRead` 275-279).
- `IdUDPServerUDPRead` drops a frame when `row_id < last_row_id`, or
  `row_id > estimated_row_id + 10`, or `sf_id > 16`.
- `PushStream` (304-347) starts a new major frame when `row_id` is 0 (the
  initial last row) or greater than the last accepted row. A minor frame is
  consumed only when `sf_id = last + 1`. After a gap, the remaining
  subframes of that row are ignored until the next row.
- `StartNewPacket` (378-408) reads a signed int32 id and accepts it only
  when `id > 0` and the id is a known input packet. The pending size is
  `EncSize + 4`.
- `PushBufferToPacket` (349-376) fills that many bytes across minor frames.
- `SendAndClearPacket` (410-414) UDP-sends the `id || body` bytes unchanged
  to `127.0.0.1` on the configured bridge port (the Delphi literal is 2357).

## What the database does not settle

The other questions the Delphi source left open are answered in
`docs/CODEC_DB_ANSWERS.md`.

- Whether rocket firmware clamps, wraps, or rejects out-of-range values
  before sending. The database has no min, max, or CHECK constraint.
  `range_variables` is the test range, not a value range. The codec keeps
  the low bits (300 as u8 is `2c`).
- The exception class for a non-numeric value. The codec raises `CodecError`.
- Chapter 10 checksums, sync, and TMATS. They are present in unused files
  and are never checked on the live path.
