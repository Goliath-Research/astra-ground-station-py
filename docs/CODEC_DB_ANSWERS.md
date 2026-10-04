# Astra codec: answers from the migrated legacy database

Host names and IP addresses from `config.servers` and `config.devices` were removed before this copy was committed. Username and password values were never included. The OPC DA ProgID and the port numbers are kept as legacy reference. The decoder's loopback forward address is unchanged.


Source: `/workspace/astra/db-migration/postgres/01_schema.sql`, `02_data.sql`, `03_programmability.sql`, loaded unchanged into a throwaway PostgreSQL 17 cluster (`initdb` under `/tmp`, port 55432, ICU, trust auth, unix socket only). All three files loaded with `psql -v ON_ERROR_STOP=1`: exit 0, nothing on stderr. Afterwards `search_path = config, testlog, public`. The cluster has since been stopped and deleted. The migration files were not modified. Nothing was committed or pushed.

Generated on 2026-10-03 (ET). Companion files: `/workspace/astra/irig106_fixture.json` (the same fixture as Appendix A, as a file).

## 0. Corrections to the premises in the brief

* **Lines ~4480-4536 of `02_data.sql` are `config.treeversions` rows** `(id, name, parentid, iconid, seq)`. `(6562,'TMencoder',4,5,40)` is a smart node (IconID 5) under Stage 1 / Version 0 / Release 1 (node 4). `(6563,'IRIG106',6562,7,NULL)` is a packet node with **IconID 7 = R2L/output packet**. Stage 2 has the same pair: `(6595,'TMencoder',6571,5,40)` and `(6596,'IRIG106',6595,7,NULL)`.
* **Rows 421 and 453 are `config.vartypes` rows, not interface rows.** The columns are `(id, name, scopeid, description, shortname, decsize, encsize)`. So `(421,'IRIG106',6563,NULL,NULL,412,349)` means VarType 421, scope node 6563, **DecSize = 412 bytes and EncSize = 349 bytes**. Neither 412 nor 349 is a vartype id. Row 453 is the same for node 6596. (`config.interfaces` rows 421/453 do exist, but they belong to the unrelated signal-design table: `fuelPump_te_c` and `eCompHeater_b`.)
* **The minor frame has 6 top-level fields, not 3:** `fap` (record FAP), `fsp`, `sf_id`, `row_id`, `range_variables`, `packet_stream`. The Pascal reads only three of them by name.
* **The record threshold in SQL is `TypeID >= 100`** (`GetVarTypesInTopologicalOrder`). The Delphi `GetIsRecord` uses `> 100`. No field uses TypeID 100, so the difference doesn't matter in this data.
* **`config.vartypes` also defines `u24` (15) and `i24` (16)**, with EncSize 24 and DecSize 32. `TVehicleDataTypes` stops at 14. No field row uses 15 or 16 (`SELECT typeid, count(*) FROM config.fields WHERE typeid<100 GROUP BY 1` returns only 1,2,3,4,5,7,8,9,11,13).
* **Size units:** for primitive types (scope 1), `vartypes.encsize`/`decsize` are **bits**. For record types they are **bytes**: `spCalcVarTypeSizes` sums in bits while it walks the types in topological order, then sets `decsize = decsize/8` (integer division) and `encsize = CEILING(encsize/8.0)` for every record in the node.

## Key tables used

| Table | Columns that matter |
|---|---|
| `config.treeversions` | `id, name, parentid, iconid, seq`. IconID: 1 vehicle, 2 stage, 3 version, 4 release, 5 smart node, 6 L2R packet, 7 R2L packet, 8 hardware, 9/10 boards |
| `config.packets` | `id, isinput, vartypeid, nodeid`. `isinput=t` is L2R (IconID 6) and `f` is R2L (IconID 7) for all 14 rows |
| `config.vartypes` | `id, name, scopeid (=owning tree node), decsize, encsize` |
| `config.fields` | `id, name, qty, typeid, initialvalue, seq, vartypeid, override, insequence, description, shortname, connectionid, transformationid` |
| `config.transformations` | `id, name, expression` |
| `config.servers`, `config.devices` | server/device addresses and ports |

## 1. The IRIG106 packet: exact field list

Lookups: `spGetNodeID('Stage 1','TMencoder','IRIG106')` returns 6563 and `('Stage 2',…)` returns 6596. `spGetVarType(6563)` returns `421, IRIG106, decsize 412, encsize 349`. `spGetVarType(6596)` returns `453, IRIG106, 412, 349`. `config.packets` has `1061 | isinput f | vartype 421 | node 6563` and `1062 | f | 453 | 6596`.

SQL (the same order `spGetVarTypeFields` uses):
```sql
SELECT f.vartypeid, v.name, f.id, f.seq, f.name, f.typeid, t.name, t.encsize, t.decsize, f.qty, f.override,
       f.insequence, f.transformationid, f.initialvalue, f.connectionid, f.shortname, f.description
FROM config.fields f JOIN config.vartypes v ON v.id=f.vartypeid JOIN config.vartypes t ON t.id=f.typeid
WHERE f.vartypeid IN (421,422,423,424,453,454,455,456)
ORDER BY f.vartypeid, f.seq NULLS FIRST, f.name;
```

### Top-level rows (VarType 421 = Stage 1, VarType 453 = Stage 2)

| Seq | Name | TypeID / type | Bits per element | Qty | Ovr | TransformationID | Field.ID S1 / S2 | Description |
|---:|---|---|---:|---:|---|---|---|---|
| 1 | `fap` | 422 / 454 = record **FAP** | 160 (20 B) | 1 | f | NULL | 3241 / 3643 | – |
| 2 | `fsp` | 5 u32 | 32 | 1 | f | NULL | 3244 / 3646 | Frame Sync Pattern |
| 3 | `sf_id` | 2 u8 | 8 | 1 | f | NULL | 3245 / 3647 | SubFrame ID (shortname SFID) |
| 4 | `row_id` | 5 **u32** | 32 | 1 | f | NULL | 3246 / 3648 | Sequential row ID for detecting dropped packets |
| 5 | `range_variables` | 2 u8 | 8 | **120** | f | NULL | 3247 / 3649 | Critical variables exposed to the range (but already part of our telemetry) |
| 6 | `packet_stream` | 2 u8 | 8 | **200** | f | NULL | 3248 / 3650 | Stream of "interface" packets (Id + Payload) |

### Nested records

**FAP** (VarType 422 / 454, "Frame Aligned (AE) Packet Format", stored EncSize 20 B, DecSize 83 B):

| Seq | Name | Type | Qty | Bits | Description |
|---:|---|---|---:|---:|---|
| 1 | type | u8 | 1 | 8 | 4 - AE Packet Full, 5 - AE Packet Partial |
| 2 | seq_counter | bool | 13 | 13 | Continuously increments with each packet. Wraps when full |
| 3 | bytes_in_packet | bool | 11 | 11 | Number of bytes contained in the entire packet |
| 4 | zeroes12 | bool | 12 | 12 | |
| 5 | IRIG_time_status | record ITS (424/456) | 1 | 8 | |
| 6 | frame_sync_status | record FSS (423/455) | 1 | 12 | |
| 7 | milliseconds_in_the_day | u32 | 1 | 32 | Binary Milliseconds Since Midnight of the current day |
| 8 | Subframe_id | bool | 10 | 10 | Frame ID of payload frame |
| 9 | words_per_minor_frame | u16 | 1 | 16 | Number of words in a minor frame |
| 10 | bits_per_word | bool | 6 | 6 | Number per bits in the frame |
| 11 | bitrate | u32 | 1 | 32 | Input bit rate of PCM stream |

Multi-bit counters in FAP are modelled as **arrays of 1-bit bools** (13, 11, 12, 10, 6), not as u13/u11 integers.

**FSS** (423 / 455, "Frame Sync Status", 2 B): 12 single bools in this order: Reserved1, Reserved2, Reserved3, MFL (MF Lock), MFC (MF Check), MFS (MF Search), FSP (Frame Sync Polarity, shortname "false - normal"), Flywheel, Idle, Lock, Check, Search.

**ITS** (424 / 456, "IRIG Time Status", 1 B): `IRIG_present` bool ×1, `Reserved` bool ×7.

Every IRIG106/FAP/FSS/ITS row has Override = false, TransformationID = NULL, InitialValue = NULL, ConnectionID = NULL and InSequence = false.

### Flattened wire layout (as `LoadFields` builds it; no `ovr_` bits)

| # | Flattened leaf | Type (id) | Bits | Qty | Total bits | Bit offset | Byte offset | Ovr | TransformationID | Field.ID S1 / S2 |
|---:|---|---|---:|---:|---:|---:|---:|---|---|---|
| 1 | `fap_type` | u8 (2) | 8 | 1 | 8 | 0 | 0 | N | NULL | 3215 / 3620 |
| 2 | `fap_seq_counter` | bool (1) | 1 | 13 | 13 | 8 | 1 | N | NULL | 3216 / 3621 |
| 3 | `fap_bytes_in_packet` | bool (1) | 1 | 11 | 11 | 21 | 2 +5b | N | NULL | 3242 / 3644 |
| 4 | `fap_zeroes12` | bool (1) | 1 | 12 | 12 | 32 | 4 | N | NULL | 3243 / 3645 |
| 5 | `fap_IRIG_time_status_IRIG_present` | bool (1) | 1 | 1 | 1 | 44 | 5 +4b | N | NULL | 3234 / 3639 |
| 6 | `fap_IRIG_time_status_Reserved` | bool (1) | 1 | 7 | 7 | 45 | 5 +5b | N | NULL | 3235 / 3640 |
| 7 | `fap_frame_sync_status_Reserved1` | bool (1) | 1 | 1 | 1 | 52 | 6 +4b | N | NULL | 3218 / 3623 |
| 8 | `fap_frame_sync_status_Reserved2` | bool (1) | 1 | 1 | 1 | 53 | 6 +5b | N | NULL | 3219 / 3624 |
| 9 | `fap_frame_sync_status_Reserved3` | bool (1) | 1 | 1 | 1 | 54 | 6 +6b | N | NULL | 3220 / 3625 |
| 10 | `fap_frame_sync_status_MFL` | bool (1) | 1 | 1 | 1 | 55 | 6 +7b | N | NULL | 3221 / 3626 |
| 11 | `fap_frame_sync_status_MFC` | bool (1) | 1 | 1 | 1 | 56 | 7 | N | NULL | 3222 / 3627 |
| 12 | `fap_frame_sync_status_MFS` | bool (1) | 1 | 1 | 1 | 57 | 7 +1b | N | NULL | 3223 / 3628 |
| 13 | `fap_frame_sync_status_FSP` | bool (1) | 1 | 1 | 1 | 58 | 7 +2b | N | NULL | 3224 / 3629 |
| 14 | `fap_frame_sync_status_Flywheel` | bool (1) | 1 | 1 | 1 | 59 | 7 +3b | N | NULL | 3225 / 3630 |
| 15 | `fap_frame_sync_status_Idle` | bool (1) | 1 | 1 | 1 | 60 | 7 +4b | N | NULL | 3226 / 3631 |
| 16 | `fap_frame_sync_status_Lock` | bool (1) | 1 | 1 | 1 | 61 | 7 +5b | N | NULL | 3227 / 3632 |
| 17 | `fap_frame_sync_status_Check` | bool (1) | 1 | 1 | 1 | 62 | 7 +6b | N | NULL | 3228 / 3633 |
| 18 | `fap_frame_sync_status_Search` | bool (1) | 1 | 1 | 1 | 63 | 7 +7b | N | NULL | 3229 / 3634 |
| 19 | `fap_milliseconds_in_the_day` | u32 (5) | 32 | 1 | 32 | 64 | 8 | N | NULL | 3217 / 3622 |
| 20 | `fap_Subframe_id` | bool (1) | 1 | 10 | 10 | 96 | 12 | N | NULL | 3231 / 3636 |
| 21 | `fap_words_per_minor_frame` | u16 (4) | 16 | 1 | 16 | 106 | 13 +2b | N | NULL | 3232 / 3637 |
| 22 | `fap_bits_per_word` | bool (1) | 1 | 6 | 6 | 122 | 15 +2b | N | NULL | 3238 / 3642 |
| 23 | `fap_bitrate` | u32 (5) | 32 | 1 | 32 | 128 | 16 | N | NULL | 3233 / 3638 |
| 24 | `fsp` | u32 (5) | 32 | 1 | 32 | 160 | 20 | N | NULL | 3244 / 3646 |
| 25 | `sf_id` | u8 (2) | 8 | 1 | 8 | 192 | 24 | N | NULL | 3245 / 3647 |
| 26 | `row_id` | u32 (5) | 32 | 1 | 32 | 200 | 25 | N | NULL | 3246 / 3648 |
| 27 | `range_variables` | u8 (2) | 8 | 120 | 960 | 232 | 29 | N | NULL | 3247 / 3649 |
| 28 | `packet_stream` | u8 (2) | 8 | 200 | 1600 | 1192 | 149 | N | NULL | 3248 / 3650 |

Total: **28 leaves, 399 elements, 2792 bits = 349 bytes exactly** (no pad bits). Everything after `fap` is byte-aligned: `fsp` at byte 20, `sf_id` at byte 24, `row_id` at bytes 25-28 (unaligned u32), `range_variables` at bytes 29-148, `packet_stream` at bytes 149-348.

**Stage 1 vs Stage 2:** I compared the flattened layouts programmatically (names, types, qty, ovr, transform, offsets). They are **identical**. Only the row ids differ: VarTypes 421-424 vs 453-456, Field.IDs 32xx vs 36xx, Packets.ID 1061 vs 1062.

**DB sizes:**

| VarType | EncSize (bytes) | DecSize (bytes) | Recomputed from bits |
|---|---:|---:|---|
| IRIG106 421 / 453 | **349** | **412** | enc 2792 bits → 349; dec 3296 → 412 ✓ |
| FAP 422 / 454 | 20 | 83 | 160 bits; dec 664 ✓ |
| FSS 423 / 455 | 2 | 12 | 12 bits; dec 96 ✓ |
| ITS 424 / 456 | 1 | 8 | 8 bits; dec 64 ✓ |

**Packets that can ride inside `packet_stream`.** The encoder fills `tblPackets` from `spGetInpPacketSizes`, which is every IconID-7 packet with a non-NULL EncSize. It has **no stage filter and no ORDER BY**. `SELECT * FROM config.spgetinppacketsizes()` on the data as stored:

| PacketID | Name | EncSize (B) | Bytes in stream (4-byte id + EncSize) |
|---:|---|---:|---:|
| 2 | R2L (Stage 1 eMaster) | 753 | 757 → 4 minor frames on its own |
| 6 | PSTR2L | 51 | 55 |
| 107 | PSTR2LD | 51 | 55 |
| 1060 | TMstats1 | 48 | 52 |
| 1061 | IRIG106 (Stage 1) | 349 | 353 |
| 1062 | IRIG106 (Stage 2) | 349 | 353 |
| 1063 | TMstats2 | 48 | 52 |

Stage 2 R2L (102) and EngineR2L (11) are missing because their stored EncSize is NULL. After `spCalcVarTypeSizes` runs on every packet node (tested inside a rolled-back transaction), the list grows to 9 rows and adds `11 EngineR2L 132` and `102 R2L 753`. If all 9 had Send set, the stream would be 2,570 bytes, which is 13 minor frames (1,677 bytes = 9 frames with the 7 stored rows). The decoder drops `sf_id > 16`, so the ceiling is 16 × 200 = 3,200 bytes per major frame.

Note that the spec vectors' fixture uses `row_id = i32`. The DB says **u32** (TypeID 5). On the wire it's the same 32 bits; only sign interpretation changes once Sequence ≥ 2^31.

## 2. Override on record rows (TypeID > 100) and size mismatches

**No field row with TypeID > 100 (or ≥ 100) has Override set.**
```sql
SELECT count(*) FILTER (WHERE typeid>100 AND override)  AS rec_ovr_gt100,   -- 0
       count(*) FILTER (WHERE typeid>=100 AND override) AS rec_ovr_ge100,   -- 0
       count(*) FILTER (WHERE typeid>100)               AS rec_rows,        -- 67
       count(*) FILTER (WHERE override)                 AS all_ovr_rows,    -- 186
       count(*) FILTER (WHERE override AND typeid<100)  AS leaf_ovr_rows    -- 186
FROM config.fields;
```
| is_record | override | rows |
|---|---|---:|
| f | f | 798 |
| f | t | 186 |
| t | f | 67 |

All 186 Override rows are leaves, so the case where "SQL counts it but `LoadFieldOvrs` does not emit it" never occurs in this data. There are no `qty` NULL/0/negative values, no dangling TypeIDs, and no record that references a type from another scope (all checked with SQL).

Arrays of records (record row with Qty > 1) appear in 21 rows. For example: L2R.engO ×5, L2R.paramsE ×5, L2R.checkParamsE ×5, R2L.engI/engO/ctlE/derE/boardE ×5, PSTL2R.pump ×2, PSTR2L(D).pump/pumpEsc ×2, and the Stage 2 copies. None of them has Override.

**Method.** For every packet and every record var type, I flattened the leaves exactly as `LoadFields` does (Seq NULLS FIRST, Name; arrays of records expanded to `name_i`). Then:
* **packed bits** = Σ(leaf bits × Qty), using the `TVehicleDataTypes` widths, plus 1 per leaf with Ovr;
* **SQL-sim** = a re-implementation of `spCalcVarTypeSizes` in bits (record-row Override would add a bit here);
* both are compared with the stored `vartypes.encsize`.

I also ran the real function on every packet node inside `BEGIN … ROLLBACK`:
```sql
BEGIN;
CREATE TEMP TABLE before AS SELECT id, decsize, encsize FROM config.vartypes;
SELECT config.spcalcvartypesizes(p.nodeid) FROM config.packets p ORDER BY p.id;
SELECT v.id, v.name, b.decsize, v.decsize, b.encsize, v.encsize FROM config.vartypes v JOIN before b USING (id)
 WHERE b.decsize IS DISTINCT FROM v.decsize OR b.encsize IS DISTINCT FROM v.encsize;
ROLLBACK;
```
That changed only the 32 rows whose sizes were NULL (409-420, 433-452). Every stored non-NULL size was unchanged, and every recomputed value equals my simulation.

### Every packet

| Packets.ID | VarType | Name | Dir | Leaves | Leaf bits | Ovr leaves | Packed bits | ceil→bytes | SQL-sim bytes | Stored EncSize | Stored DecSize | Match |
|---:|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 100 | L2R | L2R | 247 | 4895 | 148 | 5043 | 631 | 631 | 631 | 850 | yes |
| 2 | 107 | R2L | R2L | 512 | 6017 | 0 | 6017 | 753 | 753 | 753 | 1086 | yes |
| 5 | 376 | PSTL2R | L2R | 29 | 674 | 11 | 685 | 86 | 86 | 86 | 101 | yes |
| 6 | 253 | PSTR2L | R2L | 40 | 401 | 0 | 401 | 51 | 51 | 51 | 69 | yes |
| 7 | 387 | PSTL2RSeq | L2R | 11 | 7520 | 1 | 7521 | 941 | 941 | 941 | 941 | yes |
| 10 | 409 | EngineL2R | L2R | 94 | 2167 | 12 | 2179 | 273 | 273 | NULL | NULL | stored NULL (never calculated); recalculated = 273 ✓ |
| 11 | 414 | EngineR2L | R2L | 86 | 1038 | 14 | 1052 | 132 | 132 | NULL | NULL | stored NULL (never calculated); recalculated = 132 ✓ |
| 101 | 433 | L2R | L2R | 247 | 4895 | 148 | 5043 | 631 | 631 | NULL | NULL | stored NULL (never calculated); recalculated = 631 ✓ |
| 102 | 442 | R2L | R2L | 512 | 6017 | 0 | 6017 | 753 | 753 | NULL | NULL | stored NULL (never calculated); recalculated = 753 ✓ |
| 107 | 425 | PSTR2LD | R2L | 40 | 401 | 0 | 401 | 51 | 51 | 51 | 69 | yes |
| 1060 | 432 | TMstats1 | R2L | 12 | 384 | 0 | 384 | 48 | 48 | 48 | 48 | yes |
| 1061 | 421 | IRIG106 | R2L | 28 | 2792 | 0 | 2792 | 349 | 349 | 349 | 412 | yes |
| 1062 | 453 | IRIG106 | R2L | 28 | 2792 | 0 | 2792 | 349 | 349 | 349 | 412 | yes |
| 1063 | 458 | TMstats2 | R2L | 12 | 384 | 0 | 384 | 48 | 48 | 48 | 48 | yes |

**Mismatches: none.** For every packet with a stored EncSize, ceil(packed bits / 8) equals the stored EncSize, and the SQL simulation agrees. Two anomalies, neither a codec mismatch:
* **Stored sizes are NULL** for Orion B Engine (`EngineL2R` 10 / `EngineR2L` 11, VarTypes 409-420) and Stage 2 eMaster (`L2R` 101 / `R2L` 102, VarTypes 433-452). `TAstraVarPacket.SetNodeID` calls `CalcVarTypeSizes` before `GetVarType`, so the bridge fills them in at run time. The TM encoder's `spGetInpPacketSizes` reads stored values and therefore doesn't see 11 or 102 until something has run the size calc.
* **R2L packets with ovr bits:** `EngineR2L` has 14 Ovr leaves (engO ×12 + ctlE ×2). Every other R2L packet has 0. The eMaster L2R has 148 Ovr leaves, so 148 `ovr_` bits follow the 4895 data bits (5043 bits → 631 B).

Every non-packet record type also matches. Here packed bits are for the record on its own; Ovr bits of nested leaves are counted inside the record, as the SQL does:

| VarType | Name | Scope node | Packed bits | Bytes | SQL-sim bytes | Stored EncSize |
|---:|---|---:|---:|---:|---:|---:|
| 102 | seq | 6 | 17 | 3 | 3 | 3 |
| 103 | stageO | 6 | 82 | 11 | 11 | 11 |
| 104 | engO | 6 | 90 | 12 | 12 | 12 |
| 105 | params | 6 | 785 | 99 | 99 | 99 |
| 106 | checkParams | 6 | 679 | 85 | 85 | 85 |
| 108 | seq | 7 | 157 | 20 | 20 | 20 |
| 109 | derS | 7 | 512 | 64 | 64 | 64 |
| 110 | boardS | 7 | 11 | 2 | 2 | 2 |
| 111 | stageI | 7 | 540 | 68 | 68 | 68 |
| 112 | stageO | 7 | 41 | 6 | 6 | 6 |
| 113 | engI | 7 | 508 | 64 | 64 | 64 |
| 114 | engO | 7 | 76 | 10 | 10 | 10 |
| 246 | paramsE | 6 | 132 | 17 | 17 | 17 |
| 247 | PidParams | 6 | 129 | 17 | 17 | 17 |
| 249 | ctlE | 7 | 84 | 11 | 11 | 11 |
| 250 | derE | 7 | 256 | 32 | 32 | 32 |
| 251 | boardE | 7 | 8 | 1 | 1 | 1 |
| 252 | checkParamsE | 6 | 448 | 56 | 56 | 56 |
| 377 | pump | 6522 | 238 | 30 | 30 | 30 |
| 378 | params | 6522 | 78 | 10 | 10 | 10 |
| 379 | PidParams | 6522 | 129 | 17 | 17 | 17 |
| 382 | seq | 6371 | 34 | 5 | 5 | 5 |
| 383 | board | 6371 | 1 | 1 | 1 | 1 |
| 384 | io | 6371 | 13 | 2 | 2 | 2 |
| 385 | pump | 6371 | 74 | 10 | 10 | 10 |
| 386 | pumpEsc | 6371 | 86 | 11 | 11 | 11 |
| 388 | paramsOverride | 6371 | 1 | 1 | 1 | 1 |
| 410 | seq | 6551 | 17 | 3 | 3 | NULL |
| 411 | engO | 6551 | 86 | 11 | 11 | NULL |
| 412 | params | 6551 | 948 | 119 | 119 | NULL |
| 413 | checkParams | 6551 | 1127 | 141 | 141 | NULL |
| 415 | seq | 6552 | 77 | 10 | 10 | NULL |
| 416 | ctlE | 6552 | 86 | 11 | 11 | NULL |
| 417 | derE | 6552 | 256 | 32 | 32 | NULL |
| 418 | boardE | 6552 | 7 | 1 | 1 | NULL |
| 419 | engI | 6552 | 508 | 64 | 64 | NULL |
| 420 | engO | 6552 | 86 | 11 | 11 | NULL |
| 422 | FAP | 6563 | 160 | 20 | 20 | 20 |
| 423 | FSS | 6563 | 12 | 2 | 2 | 2 |
| 424 | ITS | 6563 | 8 | 1 | 1 | 1 |
| 426 | seq | 6565 | 34 | 5 | 5 | 5 |
| 427 | board | 6565 | 1 | 1 | 1 | 1 |
| 428 | io | 6565 | 13 | 2 | 2 | 2 |
| 429 | pump | 6565 | 74 | 10 | 10 | 10 |
| 430 | pumpEsc | 6565 | 86 | 11 | 11 | 11 |
| 431 | paramsOverride | 6565 | 1 | 1 | 1 | 1 |
| 434 | seq | 6573 | 17 | 3 | 3 | NULL |
| 435 | stageO | 6573 | 82 | 11 | 11 | NULL |
| 436 | engO | 6573 | 90 | 12 | 12 | NULL |
| 437 | params | 6573 | 785 | 99 | 99 | NULL |
| 438 | checkParams | 6573 | 679 | 85 | 85 | NULL |
| 439 | paramsE | 6573 | 132 | 17 | 17 | NULL |
| 440 | PidParams | 6573 | 129 | 17 | 17 | NULL |
| 441 | checkParamsE | 6573 | 448 | 56 | 56 | NULL |
| 443 | seq | 6574 | 157 | 20 | 20 | NULL |
| 444 | derS | 6574 | 512 | 64 | 64 | NULL |
| 445 | boardS | 6574 | 11 | 2 | 2 | NULL |
| 446 | stageI | 6574 | 540 | 68 | 68 | NULL |
| 447 | stageO | 6574 | 41 | 6 | 6 | NULL |
| 448 | engI | 6574 | 508 | 64 | 64 | NULL |
| 449 | engO | 6574 | 76 | 10 | 10 | NULL |
| 450 | ctlE | 6574 | 84 | 11 | 11 | NULL |
| 451 | derE | 6574 | 256 | 32 | 32 | NULL |
| 452 | boardE | 6574 | 8 | 1 | 1 | NULL |
| 454 | FAP | 6596 | 160 | 20 | 20 | 20 |
| 455 | FSS | 6596 | 12 | 2 | 2 | 2 |
| 456 | ITS | 6596 | 8 | 1 | 1 | 1 |

## 3. Min / max / range / clamp information

**There isn't any in the database.** No table has a min, max, range, limit, clamp, scale or offset column:
```sql
SELECT table_name, column_name FROM information_schema.columns
WHERE table_schema='config' AND column_name ~* '(rate|send|min|max|range|clamp|limit|scale|offset|unit|freq|period|hz|port|stage)';
-- only: areas.stage_id, devices.port, frequencies.frequency, irig_interfaces.frequency_id, servers.port,
--       stage.stage/stage_order, tests.export, plus view columns derived from those
```
A field row carries only `name, qty, typeid, initialvalue, seq, vartypeid, override, insequence, description, shortname, connectionid, transformationid`. `config.signal_data_types` (ids 3-16: bool…i32q16) holds names only, and its ids are **not** the VarType ids (for example i32q16 is 16 there and 12 in vartypes). `config.interfaces` has `data_type_id, array_length, override, insequence, order` and no limits. The DB has no CHECK constraints (README). So it can't tell you whether the rocket clamps, wraps or rejects, and the legacy wrap-on-store behaviour (spec §4) is the only rule available.

Things that look relevant but aren't codec limits:
* **`range_variables` (IRIG106, u8×120)** refers to the *test range* ("Critical variables exposed to the range"), not a value range.
* **L2R `checkParams` / `checkParamsE`** fields such as `chamberPress1_max_p_psig`, `ignPress_min_p_psig`, `fuelPumpBatVolt_max_vo_v` (f32) are **payload parameters** the ground sends to the rocket for its sequence checks. They are values, not codec constraints. `PidParams.iLimit_xs` is a PID integrator limit, also payload.
* **`fields.initialvalue`** holds 22 distinct non-NULL values, all in L2R scope 6 (`params`, `checkParams`). Examples: `heaterHigh_te_cU8 = 40`, `parkerStepSustDuty_r_uQ8 = 255`, `ignPress_end_t = 10.45`, and calibration coefficient arrays such as `tempK_s_u` f32×4 = `-249.5, 0.1987, -0.00000747, 0.0000000445` (= transformation 1) and `press250K_s_u` f32×2 = `-62.5, 0.07631` (= transformation 2). The packer doesn't use InitialValue: `BuildEmptyPacket` zeroes everything. Only `TAstraOpc` (`AstraOpcClient1.pas` 134-149) writes those values to the OPC tags once at start-up.
* **Q-named L2R integers carry small values that would overflow if Q-scaled.** `params_heaterHigh_te_cU8`, `params_presser*_p_psigU8`, `params_heReguHigh_p_psigU8` are i32q8, and `params_parkerStepSustDuty_r_uQ8` is u8q8. The bridge logged L2R tables `testlog.l2r_4` and `l2r_10` show them constant at heaterHigh = 40, presserFuelHigh = 40, heReguHigh = 70, parkerStepSustDuty = 255, which are the InitialValues. So the legacy packed 40, not 40×256. A u8q8 value of 255 is at the top of its u8 range, so any port that applied the Q8 scale, or added 1, would wrap.


## 4. Engineering units: TransformationID by direction

```sql
SELECT count(*) FILTER (WHERE transformationid=0), count(*) FILTER (WHERE transformationid IS NULL),
       count(*) FILTER (WHERE transformationid>0) FROM config.fields;      -- 0 | 898 | 153
```
I mapped each transformed row to the packets that reach its var type through record nesting, using `config.packets.isinput`. IconID 6/7 agrees with `isinput` for all 14 packets.

**Result: no L2R (LabVIEW→rocket) field has a TransformationID.** All 153 transformed rows are in R2L packets. None of the 5 L2R packets (1, 5, 7, 10, 101) has a transformed leaf. So on the send path the legacy never needed `TransformInput`, and the absence of a call is consistent with the data. The open question in the spec ("would legacy pack engineering units raw?") is moot for transform-tagged fields. It remains open only for the Q-named L2R integers and the f32 parameters discussed in §3, which have no TransformationID at all.

| Dir | Packet (ID, smart node) | Transformed rows | Flattened leaves with transform | Transform ids (row count) |
|---|---|---:|---:|---|
| R2L | 2 `R2L` (Stage 1 eMaster, node 7) | 73 | 217 | 1×41, 2×5, 3×7, 4×4, 5×2, 6×2, 9×2, 10×2, 11×2, 12×2, 13×2, 14×2 |
| R2L | 102 `R2L` (Stage 2 eMaster, node 6574) | 73 | 217 | same as packet 2 |
| R2L | 6 `PSTR2L` (PumpSimpleTester, node 6371) | 7 | 12 | 9, 10, 11, 12, 13, 14×2 |
| R2L | 107 PSTR2LD, 11 EngineR2L, 1060/1063 TMstats, 1061/1062 IRIG106 | 0 | 0 | – |
| L2R | 1 L2R, 101 L2R, 5 PSTL2R, 7 PSTL2RSeq, 10 EngineL2R | **0** | **0** | – |

Which fields are transformed (Stage 1 VarTypes; Stage 2 VarTypes 442/443/446/448 are identical):
* `R2L.t_ms` (107) and `R2L.seq.t_ms` (108): u32 → T14 Milliseconds. `PSTR2L.t_ms` / `seq.t_ms`: T14.
* `stageI` (111), all u12: every `*_te_u12` → T1 Temperature. `fuelTank_p`, `oxiTank_p`, `fuelPumpInlet_p`, `oxiPumpInlet_p`, `heRegu2_p` → T2 Press 250k. `fuelIgniter_p`, `oxiIgniter_p`, `heRegu1_p`, `heTank_p` → T4 Press 10k. `cPower_vo`, `intPower_vo` → T5. `cPower_cu`, `intPower_cu` → T6.
* `engI` (113, ×5 per engine): `*_te_u12` → T1. `chamberA_p`, `chamberB_p`, `fuelInjector_p`, `oxiInjector_p`, `fuelPumpOutlet_p`, `oxiPumpOutlet_p`, `igniter_p` (u12) → T3 Press 1k. `fuel/oxiPump_cu_aE1` (i16) → T9, `_duty_r_u16` (u16) → T10, `_te_c` (i16) → T11, `_vo_vE1` (u16) → T12, `_w_rpmEm1` (u16) → T13.
* `PSTR2L.pumpEsc` (386, ×2): `cu_aE1` T9, `duty_r_u16` T10, `te_c` T11, `vo_vE1` T12, `w_rpmEm1` T13. The PSTR2LD copy (430) has **no** transforms, which differs from PSTR2L.
* T7 Ignition and T8 dpfv are defined but not used by any field.

The logged data agrees that the transform runs on receive. In `testlog.r2l_2`, `stagei_fueltank_te_u12 = -249.5` (T1 at x = 0) and `stagei_heregu1_p_u12 = -2500` (T4 at x = 0). `t_ms` is in seconds, for example 66718.874 (T14). `testlog.r2l_1032` ("Test for Memory Leaks", desktop) instead logs raw values (`t_ms` 176942533, temperatures 0), so that build didn't transform.

`config.transformations` (all 14 rows):

| id | name | expression |
|---:|---|---|
| 1 | Temperature | `-249.5 + x*(0.1987 + x*(-7.47E-6 + 4.45E-8*x))` |
| 2 | Press 250k | `-62.5 + 0.07631*x` |
| 3 | Press 1k | `-250 + 0.3053*x` |
| 4 | Press 10k | `-2500 + 3.053*x` |
| 5 | Battery Voltage | `0 + 0.008057*x` |
| 6 | Battery Current | `0 + 0.007727*x` |
| 7 | Ignition | `0 + 0.0031746*x` |
| 8 | dpfv | `-4.1086 + 0.00498*x` |
| 9 | SC cu | `0.1*x` |
| 10 | SC r | `100.0 * x / 1023` |
| 11 | SC te | `1.0 * x` |
| 12 | SC vo | `0.1 * x` |
| 13 | SC rpm | `10.0 * x` |
| 14 | Milliseconds | `0.001 * x` |

The DB `expression` strings match the `TransformOutput` table in the spec (§10). The expressions are stored as text, and the Delphi hard-codes them by id; it doesn't parse the column.


## 5. OPC server name(s) and ports (`config.servers`, `config.devices`)

Host names and IP addresses from these tables were removed before this copy was committed. Credential columns exist (`servers.username` and `servers.password`, varchar(64), NOT NULL, a plain-text password). Their values were not selected and are not in this file. `02_data.sql` stays out of git because it contains that password.

```sql
SELECT id, port, opcservername, databasename FROM config.servers;
-- username / password deliberately not selected; winname, fullname, ipv4 omitted here
```

There is one `config.servers` row. All 50 `config.tests` rows use that server. `servers.port` is `NOT NULL DEFAULT 2357`, and the stored port is **2357**. The OPC DA ProgID is **`National Instruments.Variable Engine.1`**. That name is a legacy reference only; this port publishes OPC UA. The database name column is AstraConfig.

`config.devices` is the bridge's peers (`port NOT NULL DEFAULT 2357`). Six device rows: five use port 2357 and one, named `Virtual local`, uses **2345**. No device row points at a TMencoder, a TMdecoder, Stage 2 eMaster, or Orion B Engine. Those smart nodes have no address in the DB. There are no other server or port columns (views such as `view_interfacespertest.port` just re-expose `devices.port`).

## 6. Packet rates, Send flags and the IRIG rate

**`tblPacketsRate` / `tblPacketsSend` are not stored in the database.** No table or column named rate/send exists, and `packetsrate` matches nothing in any of the six SQL files. In `_AstraTMEncoder.pas` / `.dfm`, `tblPackets` is a `TFDMemTable` (in-memory). `FormCreate` (lines 124-142) fills it from `spGetInpPacketSizes` with **`Send := false` and `Rate := 0` for every row**. The operator edits them in the grid, and they're never saved. So the DB holds no real per-packet rates for the encoder.

What does exist:
* **IRIG/encoder base rate:** `speRate` in `_AstraTMEncoder.dfm` defaults to **100** (Hz; `Timer1.Interval = round(1000/100) = 10 ms`). The code comment says "200 Hz, for example", and the spec vectors use 200. Neither value is in the DB.
* **`config.frequencies`**: 1 = **200** "Fundamental loop frequency", 2 = **1** "One hz (useful)", 3 = **10** "slow", 4 = **400** "IRIG frame frequency".
* **`config.irig_interfaces`** (185 rows, all `interface_id = 7` = interface_list "A1S1Tester1_ir2l — Remote to Local for A1S1Tester1 - tm - irig") assigns a frequency per **signal**: 102 signals at 200 Hz, 57 at 1 Hz, 23 at 10 Hz, 3 at 400 Hz (`t_ms`, `v_b`, `rows_n`). This is the signal-design table (names/grouping). It has no FK to `packets`/`fields`, and the encoder doesn't read it. It's the only stored "rate" data, and it's per signal, not per packet.
* **Rate-rule consequences with the defaults:** Rate = 0 makes `Sequence*0 mod speRate = 0` true, so a packet with Send ticked and Rate left at 0 goes in **every** major frame. Rate = speRate (100) is also every frame. At speRate 100, rate 10 is every 10th frame and rate 1 is every 100th. If an operator meant 400 Hz IRIG with 200 Hz packets, they'd set speRate = 400 and Rate = 200, which gives every 2nd frame.
* The candidate rows for Send are the 7 from `spGetInpPacketSizes` in §1, or 9 after a size recalculation. They include the IRIG106 packets themselves and TMstats1/2, because the procedure only filters on IconID 7.


## 7. Other things in the DB that bear on the codec

* **Stage count = 2 for the TM path.** `treeversions` IconID-2 nodes are `Stage 1` (2), `Stage 2` (6569), `Orion A` (6367, PumpSimpleTester) and `Orion B` (6524, Engine). Only Stage 1 and Stage 2 have `TMencoder` / `TMdecoder` smart nodes (6562/6566 and 6595/6602), so `spGetNodeID('Stage %d','TMencoder','IRIG106')` resolves for stages 1 and 2 only. Each stage has exactly one `Version 0 / Release 1`.
* **`config.stage` is something else.** Its rows are `S1Tester1` (id 1, order 100), `S2Tester1` (2, 200) and `S1EngineTester1` (4, 150): harness/pinout stages used by `areas.stage_id` and the pinout views. They aren't codec stages.
* **Stage 2 is only partly set up:** its eMaster L2R/R2L have NULL stored sizes and no `devices` row. Its layouts match Stage 1 exactly (flattened compare: L2R 100 = 433 with 247 leaves, R2L 107 = 442 with 512 leaves, same types/qty/ovr/transforms).
* **Port 2357 throughout:** `servers.port = 2357` (default 2357) and `devices.port` defaults to 2357 (5 of 6 rows; "Virtual local" uses 2345). In source (not in the DB), the TM encoder listens on `speLocalPort = 2357` and sends to `2357 + stage` (2358 / 2359; the dfm default is 2358), and the decoder forwards extracted packets to `127.0.0.1:2357`. The DB has no column for the encoder/decoder ports.
* **Minor-frame ids:** the DB `Packets.ID` values for IRIG106 are **1061 (Stage 1) / 1062 (Stage 2)**. The decoder's own minor-frame log id is the formula `100*(stage-1)+106` = 106 / 206, which isn't a DB id. The decoder's stats packets are `TMstats1` 1060 (node 6568) / `TMstats2` 1063 (node 6601): 12 × u32 = 48 B (`TimerTick`, `FirstRowID`, `LastRowID`, `LastSubFrameID`, `TotalMajorFrames`, `ReceivedMajorFrames`, `TotalRawFrames`, `ReceivedMinorFrames`, `RejectedMinorFrames`, `DroppedMinorFrames`, `MaxMinorFrameID`, `AvgFramesByRow`).
* **All 14 packet ids are positive int32** (1, 2, 5, 6, 7, 10, 11, 101, 102, 107, 1060-1063), so the decoder's `PacketID > 0` test passes for all of them.
* **Field order depends on the collation for 702 of 1,051 rows.** These rows (32 var types, mostly stageO/engI/stageI/checkParams) have `seq IS NULL`, so their order is `ORDER BY name` under SQL Server `SQL_Latin1_General_CP1_CI_AS`. A Python port that sorts names with plain `sorted()` (codepoint order, case-sensitive, `_` after uppercase letters) will get a **different bit layout** than the legacy for those records. Use the ICU `und-u-ka-noignore` order from the migration, or read the order from `spgetvartypefields`. The IRIG106/FAP/FSS/ITS rows all have Seq, so they aren't affected.
* `insequence` is false on every row; the codec ignores it anyway. `connectionid` is hardware mapping only.
* **Type widths:** the DB `vartypes.encsize` for ids 1-14 matches `TVehicleDataTypes`. The DB also defines u24/i24 (15/16), which no field uses and the Delphi can't encode.
* `PSTR2L` (6) and `PSTR2LD` (107) have identical layouts except that PSTR2LD has no TransformationIDs.


## Appendix A: ready-to-use fixture for the real IRIG106 layout

The same content is in `/workspace/astra/irig106_fixture.json`. The format follows `spec/codec_vectors.json`: `layout` entries `{name,type_id,type,bits,qty,override}` with flattened leaf names, LSB-first, little-endian. A packer that reproduces all 28 packing vectors in `codec_vectors.json` produced the expected hex. Vectors:

* `irig106_stage1_tmstats1_seq0`: one minor frame carrying TMstats1 (id 1060 → `24040000` at byte 149, then 48 + 148 zero bytes), `sf_id=1`, `row_id=1`.
* `irig106_stage1_r2l_frame_{1..4}_of_4`: R2L (id 2, EncSize 753) spread over 4 minor frames (200/200/200/157 stream bytes).
* `irig106_bit_position_probe`: every leaf non-zero, to pin down offsets inside FAP (bool arrays given element-wise).

Python constant for the layout:

```python
IRIG106_LAYOUT = [
    dict(name='fap_type'                                , type_id=2, type='u8'   , bits= 8, qty=  1, override=False),
    dict(name='fap_seq_counter'                         , type_id=1, type='bool' , bits= 1, qty= 13, override=False),
    dict(name='fap_bytes_in_packet'                     , type_id=1, type='bool' , bits= 1, qty= 11, override=False),
    dict(name='fap_zeroes12'                            , type_id=1, type='bool' , bits= 1, qty= 12, override=False),
    dict(name='fap_IRIG_time_status_IRIG_present'       , type_id=1, type='bool' , bits= 1, qty=  1, override=False),
    dict(name='fap_IRIG_time_status_Reserved'           , type_id=1, type='bool' , bits= 1, qty=  7, override=False),
    dict(name='fap_frame_sync_status_Reserved1'         , type_id=1, type='bool' , bits= 1, qty=  1, override=False),
    dict(name='fap_frame_sync_status_Reserved2'         , type_id=1, type='bool' , bits= 1, qty=  1, override=False),
    dict(name='fap_frame_sync_status_Reserved3'         , type_id=1, type='bool' , bits= 1, qty=  1, override=False),
    dict(name='fap_frame_sync_status_MFL'               , type_id=1, type='bool' , bits= 1, qty=  1, override=False),
    dict(name='fap_frame_sync_status_MFC'               , type_id=1, type='bool' , bits= 1, qty=  1, override=False),
    dict(name='fap_frame_sync_status_MFS'               , type_id=1, type='bool' , bits= 1, qty=  1, override=False),
    dict(name='fap_frame_sync_status_FSP'               , type_id=1, type='bool' , bits= 1, qty=  1, override=False),
    dict(name='fap_frame_sync_status_Flywheel'          , type_id=1, type='bool' , bits= 1, qty=  1, override=False),
    dict(name='fap_frame_sync_status_Idle'              , type_id=1, type='bool' , bits= 1, qty=  1, override=False),
    dict(name='fap_frame_sync_status_Lock'              , type_id=1, type='bool' , bits= 1, qty=  1, override=False),
    dict(name='fap_frame_sync_status_Check'             , type_id=1, type='bool' , bits= 1, qty=  1, override=False),
    dict(name='fap_frame_sync_status_Search'            , type_id=1, type='bool' , bits= 1, qty=  1, override=False),
    dict(name='fap_milliseconds_in_the_day'             , type_id=5, type='u32'  , bits=32, qty=  1, override=False),
    dict(name='fap_Subframe_id'                         , type_id=1, type='bool' , bits= 1, qty= 10, override=False),
    dict(name='fap_words_per_minor_frame'               , type_id=4, type='u16'  , bits=16, qty=  1, override=False),
    dict(name='fap_bits_per_word'                       , type_id=1, type='bool' , bits= 1, qty=  6, override=False),
    dict(name='fap_bitrate'                             , type_id=5, type='u32'  , bits=32, qty=  1, override=False),
    dict(name='fsp'                                     , type_id=5, type='u32'  , bits=32, qty=  1, override=False),
    dict(name='sf_id'                                   , type_id=2, type='u8'   , bits= 8, qty=  1, override=False),
    dict(name='row_id'                                  , type_id=5, type='u32'  , bits=32, qty=  1, override=False),
    dict(name='range_variables'                         , type_id=2, type='u8'   , bits= 8, qty=120, override=False),
    dict(name='packet_stream'                           , type_id=2, type='u8'   , bits= 8, qty=200, override=False),
]  # 28 leaves, 2792 bits = 349 bytes; DB EncSize 349, DecSize 412; VarType 421 (Stage 1) / 453 (Stage 2)
IRIG106_PACKET_IDS = {1: 1061, 2: 1062}   # config.packets.id
IRIG106_NODE_IDS   = {1: 6563, 2: 6596}   # config.treeversions.id (parent TMencoder 6562 / 6595)
IRIG106_OFFSETS = {'sf_id': 24, 'row_id': 25, 'range_variables': 29, 'packet_stream': 149}  # byte offsets
PACKET_STREAM_LEN = 200; RANGE_VARIABLES_LEN = 120
```

Full JSON fixture:

```json
{
 "description": "Real IRIG106 minor-frame layout from the migrated AstraConfig DB (config.vartypes 421 [Stage 1, node 6563] and 453 [Stage 2, node 6596]; identical apart from row ids). Leaves flattened exactly as TAstraVarPacket.LoadFields does (spGetVarTypeFields order: Seq NULLS FIRST, Name; nested record leaves prefixed parent_). No leaf has Override, so no ovr_ bits. Packed with LSB-first bit order, little-endian, same rules as spec/codec_vectors.json (the packer used reproduces all 28 packing vectors there).",
 "bit_order": "lsb_first_within_each_byte",
 "byte_order": "little_endian",
 "source": {
  "db": "AstraConfig (postgres migration, schema config)",
  "vartype_ids": {"stage1": 421, "stage2": 453},
  "packet_ids": {"stage1": 1061, "stage2": 1062},
  "node_ids": {"stage1": 6563, "stage2": 6596},
  "smart_node_ids": {"stage1_TMencoder": 6562, "stage2_TMencoder": 6595},
  "db_encsize_bytes": 349,
  "db_decsize_bytes": 412,
  "packed_bits": 2792,
  "nested_vartypes": {
   "FAP": {"stage1": 422, "stage2": 454, "enc_bytes": 20, "bits": 160},
   "FSS": {"stage1": 423, "stage2": 455, "enc_bytes": 2, "bits": 12},
   "ITS": {"stage1": 424, "stage2": 456, "enc_bytes": 1, "bits": 8}
  }
 },
 "key_fields": {
  "sf_id": {"type": "u8", "type_id": 2, "bit_offset": 192, "byte_offset": 24},
  "row_id": {"type": "u32", "type_id": 5, "bit_offset": 200, "byte_offset": 25},
  "packet_stream": {"type": "u8", "type_id": 2, "qty": 200, "bit_offset": 1192, "byte_offset": 149}
 },
 "layouts": {
  "irig106_real": [
   {"name": "fap_type", "type_id": 2, "type": "u8", "bits": 8, "qty": 1, "override": false},
   {"name": "fap_seq_counter", "type_id": 1, "type": "bool", "bits": 1, "qty": 13, "override": false},
   {"name": "fap_bytes_in_packet", "type_id": 1, "type": "bool", "bits": 1, "qty": 11, "override": false},
   {"name": "fap_zeroes12", "type_id": 1, "type": "bool", "bits": 1, "qty": 12, "override": false},
   {"name": "fap_IRIG_time_status_IRIG_present", "type_id": 1, "type": "bool", "bits": 1, "qty": 1, "override": false},
   {"name": "fap_IRIG_time_status_Reserved", "type_id": 1, "type": "bool", "bits": 1, "qty": 7, "override": false},
   {"name": "fap_frame_sync_status_Reserved1", "type_id": 1, "type": "bool", "bits": 1, "qty": 1, "override": false},
   {"name": "fap_frame_sync_status_Reserved2", "type_id": 1, "type": "bool", "bits": 1, "qty": 1, "override": false},
   {"name": "fap_frame_sync_status_Reserved3", "type_id": 1, "type": "bool", "bits": 1, "qty": 1, "override": false},
   {"name": "fap_frame_sync_status_MFL", "type_id": 1, "type": "bool", "bits": 1, "qty": 1, "override": false},
   {"name": "fap_frame_sync_status_MFC", "type_id": 1, "type": "bool", "bits": 1, "qty": 1, "override": false},
   {"name": "fap_frame_sync_status_MFS", "type_id": 1, "type": "bool", "bits": 1, "qty": 1, "override": false},
   {"name": "fap_frame_sync_status_FSP", "type_id": 1, "type": "bool", "bits": 1, "qty": 1, "override": false},
   {"name": "fap_frame_sync_status_Flywheel", "type_id": 1, "type": "bool", "bits": 1, "qty": 1, "override": false},
   {"name": "fap_frame_sync_status_Idle", "type_id": 1, "type": "bool", "bits": 1, "qty": 1, "override": false},
   {"name": "fap_frame_sync_status_Lock", "type_id": 1, "type": "bool", "bits": 1, "qty": 1, "override": false},
   {"name": "fap_frame_sync_status_Check", "type_id": 1, "type": "bool", "bits": 1, "qty": 1, "override": false},
   {"name": "fap_frame_sync_status_Search", "type_id": 1, "type": "bool", "bits": 1, "qty": 1, "override": false},
   {"name": "fap_milliseconds_in_the_day", "type_id": 5, "type": "u32", "bits": 32, "qty": 1, "override": false},
   {"name": "fap_Subframe_id", "type_id": 1, "type": "bool", "bits": 1, "qty": 10, "override": false},
   {"name": "fap_words_per_minor_frame", "type_id": 4, "type": "u16", "bits": 16, "qty": 1, "override": false},
   {"name": "fap_bits_per_word", "type_id": 1, "type": "bool", "bits": 1, "qty": 6, "override": false},
   {"name": "fap_bitrate", "type_id": 5, "type": "u32", "bits": 32, "qty": 1, "override": false},
   {"name": "fsp", "type_id": 5, "type": "u32", "bits": 32, "qty": 1, "override": false},
   {"name": "sf_id", "type_id": 2, "type": "u8", "bits": 8, "qty": 1, "override": false},
   {"name": "row_id", "type_id": 5, "type": "u32", "bits": 32, "qty": 1, "override": false},
   {"name": "range_variables", "type_id": 2, "type": "u8", "bits": 8, "qty": 120, "override": false},
   {"name": "packet_stream", "type_id": 2, "type": "u8", "bits": 8, "qty": 200, "override": false}
  ]
 },
 "layout_detail_stage1": [
  {"name": "fap_type", "type_id": 2, "type": "u8", "bits": 8, "qty": 1, "override": false, "transformation_id": null, "bit_offset": 0, "db_field_id": 3215},
  {"name": "fap_seq_counter", "type_id": 1, "type": "bool", "bits": 1, "qty": 13, "override": false, "transformation_id": null, "bit_offset": 8, "db_field_id": 3216},
  {"name": "fap_bytes_in_packet", "type_id": 1, "type": "bool", "bits": 1, "qty": 11, "override": false, "transformation_id": null, "bit_offset": 21, "db_field_id": 3242},
  {"name": "fap_zeroes12", "type_id": 1, "type": "bool", "bits": 1, "qty": 12, "override": false, "transformation_id": null, "bit_offset": 32, "db_field_id": 3243},
  {"name": "fap_IRIG_time_status_IRIG_present", "type_id": 1, "type": "bool", "bits": 1, "qty": 1, "override": false, "transformation_id": null, "bit_offset": 44, "db_field_id": 3234},
  {"name": "fap_IRIG_time_status_Reserved", "type_id": 1, "type": "bool", "bits": 1, "qty": 7, "override": false, "transformation_id": null, "bit_offset": 45, "db_field_id": 3235},
  {"name": "fap_frame_sync_status_Reserved1", "type_id": 1, "type": "bool", "bits": 1, "qty": 1, "override": false, "transformation_id": null, "bit_offset": 52, "db_field_id": 3218},
  {"name": "fap_frame_sync_status_Reserved2", "type_id": 1, "type": "bool", "bits": 1, "qty": 1, "override": false, "transformation_id": null, "bit_offset": 53, "db_field_id": 3219},
  {"name": "fap_frame_sync_status_Reserved3", "type_id": 1, "type": "bool", "bits": 1, "qty": 1, "override": false, "transformation_id": null, "bit_offset": 54, "db_field_id": 3220},
  {"name": "fap_frame_sync_status_MFL", "type_id": 1, "type": "bool", "bits": 1, "qty": 1, "override": false, "transformation_id": null, "bit_offset": 55, "db_field_id": 3221},
  {"name": "fap_frame_sync_status_MFC", "type_id": 1, "type": "bool", "bits": 1, "qty": 1, "override": false, "transformation_id": null, "bit_offset": 56, "db_field_id": 3222},
  {"name": "fap_frame_sync_status_MFS", "type_id": 1, "type": "bool", "bits": 1, "qty": 1, "override": false, "transformation_id": null, "bit_offset": 57, "db_field_id": 3223},
  {"name": "fap_frame_sync_status_FSP", "type_id": 1, "type": "bool", "bits": 1, "qty": 1, "override": false, "transformation_id": null, "bit_offset": 58, "db_field_id": 3224},
  {"name": "fap_frame_sync_status_Flywheel", "type_id": 1, "type": "bool", "bits": 1, "qty": 1, "override": false, "transformation_id": null, "bit_offset": 59, "db_field_id": 3225},
  {"name": "fap_frame_sync_status_Idle", "type_id": 1, "type": "bool", "bits": 1, "qty": 1, "override": false, "transformation_id": null, "bit_offset": 60, "db_field_id": 3226},
  {"name": "fap_frame_sync_status_Lock", "type_id": 1, "type": "bool", "bits": 1, "qty": 1, "override": false, "transformation_id": null, "bit_offset": 61, "db_field_id": 3227},
  {"name": "fap_frame_sync_status_Check", "type_id": 1, "type": "bool", "bits": 1, "qty": 1, "override": false, "transformation_id": null, "bit_offset": 62, "db_field_id": 3228},
  {"name": "fap_frame_sync_status_Search", "type_id": 1, "type": "bool", "bits": 1, "qty": 1, "override": false, "transformation_id": null, "bit_offset": 63, "db_field_id": 3229},
  {"name": "fap_milliseconds_in_the_day", "type_id": 5, "type": "u32", "bits": 32, "qty": 1, "override": false, "transformation_id": null, "bit_offset": 64, "db_field_id": 3217},
  {"name": "fap_Subframe_id", "type_id": 1, "type": "bool", "bits": 1, "qty": 10, "override": false, "transformation_id": null, "bit_offset": 96, "db_field_id": 3231},
  {"name": "fap_words_per_minor_frame", "type_id": 4, "type": "u16", "bits": 16, "qty": 1, "override": false, "transformation_id": null, "bit_offset": 106, "db_field_id": 3232},
  {"name": "fap_bits_per_word", "type_id": 1, "type": "bool", "bits": 1, "qty": 6, "override": false, "transformation_id": null, "bit_offset": 122, "db_field_id": 3238},
  {"name": "fap_bitrate", "type_id": 5, "type": "u32", "bits": 32, "qty": 1, "override": false, "transformation_id": null, "bit_offset": 128, "db_field_id": 3233},
  {"name": "fsp", "type_id": 5, "type": "u32", "bits": 32, "qty": 1, "override": false, "transformation_id": null, "bit_offset": 160, "db_field_id": 3244},
  {"name": "sf_id", "type_id": 2, "type": "u8", "bits": 8, "qty": 1, "override": false, "transformation_id": null, "bit_offset": 192, "db_field_id": 3245},
  {"name": "row_id", "type_id": 5, "type": "u32", "bits": 32, "qty": 1, "override": false, "transformation_id": null, "bit_offset": 200, "db_field_id": 3246},
  {"name": "range_variables", "type_id": 2, "type": "u8", "bits": 8, "qty": 120, "override": false, "transformation_id": null, "bit_offset": 232, "db_field_id": 3247},
  {"name": "packet_stream", "type_id": 2, "type": "u8", "bits": 8, "qty": 200, "override": false, "transformation_id": null, "bit_offset": 1192, "db_field_id": 3248}
 ],
 "layout_detail_stage2_field_ids": [3620, 3621, 3644, 3645, 3639, 3640, 3623, 3624, 3625, 3626, 3627, 3628, 3629, 3630, 3631, 3632, 3633, 3634, 3622, 3636, 3637, 3642, 3638, 3646, 3647, 3648, 3649, 3650],
 "vectors": [
  {
   "id": "irig106_stage1_tmstats1_seq0",
   "description": "Stage 1 TM encoder, only TMstats1 (Packets.ID 1060, EncSize 48 bytes) has Send=True. Sequence was 0, so the packet is included; Sequence becomes 1, SubFrameID 1. packet_stream = int32 LE 1060 + 48 zero payload bytes + 148 zero fill. Every other field is 0 (BuildEmptyPacket).",
   "layout_ref": "irig106_real",
   "values": {
    "sf_id": 1,
    "row_id": 1,
    "packet_stream": [36, 4, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
   },
   "bit_length": 2792,
   "byte_length": 349,
   "expected_hex": "00000000000000000000000000000000000000000000000001010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000002404000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000",
   "send_packets": [
    {"packet_id": 1060, "name": "TMstats1", "enc_size_bytes": 48}
   ],
   "irig_rate_hz": 100,
   "sequence_before_increment": 0
  },
  {
   "id": "irig106_stage1_r2l_frame_1_of_4",
   "description": "Stage 1 TM encoder, only R2L (Packets.ID 2, EncSize 753) has Send=True. Stream = 4 + 753 = 757 bytes -> 4 minor frames (200,200,200,157). This is frame 1: sf_id=1, row_id=1, 200 stream bytes then zero fill.",
   "layout_ref": "irig106_real",
   "values": {
    "sf_id": 1,
    "row_id": 1,
    "packet_stream": [2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
   },
   "bit_length": 2792,
   "byte_length": 349,
   "expected_hex": "00000000000000000000000000000000000000000000000001010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000",
   "send_packets": [
    {"packet_id": 2, "name": "R2L", "enc_size_bytes": 753}
   ],
   "stream_bytes_in_frame": 200
  },
  {
   "id": "irig106_stage1_r2l_frame_2_of_4",
   "description": "Stage 1 TM encoder, only R2L (Packets.ID 2, EncSize 753) has Send=True. Stream = 4 + 753 = 757 bytes -> 4 minor frames (200,200,200,157). This is frame 2: sf_id=2, row_id=1, 200 stream bytes then zero fill.",
   "layout_ref": "irig106_real",
   "values": {
    "sf_id": 2,
    "row_id": 1,
    "packet_stream": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
   },
   "bit_length": 2792,
   "byte_length": 349,
   "expected_hex": "00000000000000000000000000000000000000000000000002010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000",
   "send_packets": [
    {"packet_id": 2, "name": "R2L", "enc_size_bytes": 753}
   ],
   "stream_bytes_in_frame": 200
  },
  {
   "id": "irig106_stage1_r2l_frame_3_of_4",
   "description": "Stage 1 TM encoder, only R2L (Packets.ID 2, EncSize 753) has Send=True. Stream = 4 + 753 = 757 bytes -> 4 minor frames (200,200,200,157). This is frame 3: sf_id=3, row_id=1, 200 stream bytes then zero fill.",
   "layout_ref": "irig106_real",
   "values": {
    "sf_id": 3,
    "row_id": 1,
    "packet_stream": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
   },
   "bit_length": 2792,
   "byte_length": 349,
   "expected_hex": "00000000000000000000000000000000000000000000000003010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000",
   "send_packets": [
    {"packet_id": 2, "name": "R2L", "enc_size_bytes": 753}
   ],
   "stream_bytes_in_frame": 200
  },
  {
   "id": "irig106_stage1_r2l_frame_4_of_4",
   "description": "Stage 1 TM encoder, only R2L (Packets.ID 2, EncSize 753) has Send=True. Stream = 4 + 753 = 757 bytes -> 4 minor frames (200,200,200,157). This is frame 4: sf_id=4, row_id=1, 157 stream bytes then zero fill.",
   "layout_ref": "irig106_real",
   "values": {
    "sf_id": 4,
    "row_id": 1,
    "packet_stream": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
   },
   "bit_length": 2792,
   "byte_length": 349,
   "expected_hex": "00000000000000000000000000000000000000000000000004010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000",
   "send_packets": [
    {"packet_id": 2, "name": "R2L", "enc_size_bytes": 753}
   ],
   "stream_bytes_in_frame": 157
  },
  {
   "id": "irig106_bit_position_probe",
   "description": "Every leaf non-zero, to check bit offsets. Bool arrays are given element-wise; element j is streamed j-th (LSB-first), so a bool[13] counter value V is elements [bit0..bit12] of V only if the firmware uses that convention (the DB does not say). fsp uses the IRIG-106 32-bit sync pattern 0xFE6B2840 as a value; the DB has no default for it.",
   "layout_ref": "irig106_real",
   "values": {
    "fap_type": 4,
    "fap_seq_counter": [false, false, true, true, true, true, false, true, false, true, false, true, true],
    "fap_bytes_in_packet": [true, false, true, true, true, false, true, false, true, false, false],
    "fap_zeroes12": [false, false, false, false, false, false, false, false, false, false, false, false],
    "fap_IRIG_time_status_IRIG_present": true,
    "fap_IRIG_time_status_Reserved": [false, false, false, false, false, false, false],
    "fap_frame_sync_status_Reserved1": false,
    "fap_frame_sync_status_Reserved2": false,
    "fap_frame_sync_status_Reserved3": false,
    "fap_frame_sync_status_MFL": true,
    "fap_frame_sync_status_MFC": false,
    "fap_frame_sync_status_MFS": true,
    "fap_frame_sync_status_FSP": false,
    "fap_frame_sync_status_Flywheel": true,
    "fap_frame_sync_status_Idle": false,
    "fap_frame_sync_status_Lock": true,
    "fap_frame_sync_status_Check": true,
    "fap_frame_sync_status_Search": false,
    "fap_milliseconds_in_the_day": 16909060,
    "fap_Subframe_id": [true, false, true, false, false, false, false, false, false, false],
    "fap_words_per_minor_frame": 4660,
    "fap_bits_per_word": [false, false, false, false, true, false],
    "fap_bitrate": 10000000,
    "fsp": 4268435520,
    "sf_id": 3,
    "row_id": 2309737967,
    "range_variables": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119],
    "packet_stream": [255, 254, 253, 252, 251, 250, 249, 248, 247, 246, 245, 244, 243, 242, 241, 240, 239, 238, 237, 236, 235, 234, 233, 232, 231, 230, 229, 228, 227, 226, 225, 224, 223, 222, 221, 220, 219, 218, 217, 216, 215, 214, 213, 212, 211, 210, 209, 208, 207, 206, 205, 204, 203, 202, 201, 200, 199, 198, 197, 196, 195, 194, 193, 192, 191, 190, 189, 188, 187, 186, 185, 184, 183, 182, 181, 180, 179, 178, 177, 176, 175, 174, 173, 172, 171, 170, 169, 168, 167, 166, 165, 164, 163, 162, 161, 160, 159, 158, 157, 156, 155, 154, 153, 152, 151, 150, 149, 148, 147, 146, 145, 144, 143, 142, 141, 140, 139, 138, 137, 136, 135, 134, 133, 132, 131, 130, 129, 128, 127, 126, 125, 124, 123, 122, 121, 120, 119, 118, 117, 116, 115, 114, 113, 112, 111, 110, 109, 108, 107, 106, 105, 104, 103, 102, 101, 100, 99, 98, 97, 96, 95, 94, 93, 92, 91, 90, 89, 88, 87, 86, 85, 84, 83, 82, 81, 80, 79, 78, 77, 76, 75, 74, 73, 72, 71, 70, 69, 68, 67, 66, 65, 64, 63, 62, 61, 60, 59, 58, 57, 56]
   },
   "bit_length": 2792,
   "byte_length": 349,
   "expected_hex": "04bcba2b0010806a0403020105d048408096980040286bfe03efcdab89000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f202122232425262728292a2b2c2d2e2f303132333435363738393a3b3c3d3e3f404142434445464748494a4b4c4d4e4f505152535455565758595a5b5c5d5e5f606162636465666768696a6b6c6d6e6f7071727374757677fffefdfcfbfaf9f8f7f6f5f4f3f2f1f0efeeedecebeae9e8e7e6e5e4e3e2e1e0dfdedddcdbdad9d8d7d6d5d4d3d2d1d0cfcecdcccbcac9c8c7c6c5c4c3c2c1c0bfbebdbcbbbab9b8b7b6b5b4b3b2b1b0afaeadacabaaa9a8a7a6a5a4a3a2a1a09f9e9d9c9b9a999897969594939291908f8e8d8c8b8a898887868584838281807f7e7d7c7b7a797877767574737271706f6e6d6c6b6a696867666564636261605f5e5d5c5b5a595857565554535251504f4e4d4c4b4a494847464544434241403f3e3d3c3b3a3938"
  }
 ]
}
```
## Appendix B: how it was run

```bash
sudo apt-get install -y postgresql-17          # server binaries (client 17 was already present)
/usr/lib/postgresql/17/bin/initdb -D /tmp/astra_pg -U postgres --auth=trust -E UTF8 --locale-provider=icu --icu-locale=und
/usr/lib/postgresql/17/bin/pg_ctl -D /tmp/astra_pg -o "-p 55432 -k /tmp -c listen_addresses=''" start
createdb -h /tmp -p 55432 -U postgres astra
for f in 01_schema.sql 02_data.sql 03_programmability.sql; do psql -h /tmp -p 55432 -U postgres -d astra -v ON_ERROR_STOP=1 -f postgres/$f; done
# exports: \copy of config.fields (with row_number() OVER (PARTITION BY vartypeid ORDER BY seq NULLS FIRST, name NULLS FIRST)),
#          config.vartypes, config.packets (+ tree node / smart node), config.treeversions  -> CSV
# analysis: Python flattening = LoadFields/LoadFieldOvrs; SQL-sim = spCalcVarTypeSizes in bits; compared to stored sizes
pg_ctl -D /tmp/astra_pg stop; rm -rf /tmp/astra_pg   # cleanup
```
Other SQL used is shown inline in each section.
