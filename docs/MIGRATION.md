Source of truth: the legacy repository copy at https://github.com/Goliath-Research/astra-ground-station/blob/main/MIGRATION.md

# Migration plan: Astra ground station to Python, Mojo, and PostgreSQL

This is a plan only. It does not change the Delphi code. The Python and Mojo port lives in a separate private repository: https://github.com/Goliath-Research/astra-ground-station-py.

The repository is the 2017–2018 PC side of Astra’s vehicle-test setup (David Izada Rodriguez, RAD Studio 10.2 Tokyo). It moves data between the vehicle network and a LabVIEW application that is not in this repo. The rocket firmware (ChibiOS, lwIP, SPI/I2C board drivers, Simulink-generated control code) is also not in this repo. `Ground Station Software.docx` describes the PC architecture that this code actually implements.

Target constraints used below:

- Python is the language for services, tools, and I/O.
- Mojo is an accepted choice for the few loops where a native implementation is worth having. It is free to use. This plan does not argue for replacing it with an open-source compiler.
- PostgreSQL replaces Microsoft SQL Server.
- Nothing in the new stack is a paid product: no RAD Studio, DevExpress, Devart EntityDAC, dOPC, FireDAC, CodeSite, FastReport, NI Variable Engine, or SQL Server.
- The new services run on Linux, probably Ubuntu, on x86_64 and possibly ARM64 (aarch64). LabVIEW stays where it is and talks OPC UA. Details are in §5.

Decisions already made (2026-10-03):

- LabVIEW will move off NI shared variables onto OPC UA tags published by the bridge.
- Production Delphi was built for Win64. Numeric golden values follow that build (SSE2 `float64`, not 80-bit Win32 `Extended`).
- There are no saved `.DAT` files, packet captures, or `AstraTestLog` dumps. §6 says how to get confidence without them.
- The bridge UDP port is configuration (`ASTRA_BRIDGE_PORT`, or the same key in `/etc/astra/astra.env`). The legacy literal 2357 is only the default.
- Stage count is configuration (`ASTRA_STAGE_COUNT`, default 2). The rocket started with two stages.
- `Jobs.PacketID`, with `TestID`, is the job key. `IntfID` is a generated UUID.

## What the running system actually does

```
vehicle UDP  --->  AstraBridgeServer  --->  OPC DA server (NI Variable Engine)
                      |                         ^
                      | binary DAT logs         | LabVIEW shared variables
                      v                         |
                 AstraLogExporter  --->  SQL Server (AstraTestLog)

TMoIP device ---> UDP 2357+stage ---> AstraTMoIP
                                         |  reassembly
                                         +--> UDP 127.0.0.1:2357 (the bridge)
```

Three protocols show up in the sources. They are not interchangeable.

1. **Vehicle UDP (R2L / L2R).** This is the ground link. An Indy `TIdUDPServer` receives datagrams and an `TIdUDPClient` sends them. A datagram is a little-endian 32-bit packet id plus a bit-packed payload (`AstraCommon/AstraNetPacket.pas`, `AstraCommon/AstraVarPacket.pas`). The design document calls the rocket-to-PC direction R2L and the PC-to-rocket direction L2R. There is no COM-port stack, no SLIP framing, and no UART tunnel in this repository. On the rocket, sensors sit on SPI and I2C; those buses stop at the vehicle. What arrives here is already a UDP datagram. `AstraTMoIP/src` has an IRIG 106 UART data type (`0x50`) only as an unused constant in the Chapter 10 library.

2. **Telemetry over IP.** `AstraTMoIP/AstraDecoder.pas` listens on UDP port `2357 + stage` (stage 1 → 2358, stage 2 → 2359). Each datagram is one minor frame whose layout is the database packet named `IRIG106` on smart node `TMencoder` (fields `sf_id`, `row_id`, `packet_stream`). The decoder pulls Astra packets back out of `packet_stream` and forwards them to `127.0.0.1:2357`. It does **not** call the C library under `AstraTMoIP/src`.

3. **OPC DA.** `AstraCommon/AstraInpPopper.pas` and `AstraOutPusher.pas` are dOPC clients (`dOPCCOM`, `dOPCDA`). They connect to the server name stored on the `Servers` row (the older client default is `National Instruments.Variable Engine.1`) on `localhost`, and they read and write items at `\\.\Astra{PacketName}\{field}`. LabVIEW sees those items as shared network variables. The bridge is a client of that server, not the server itself.

Configuration lives in SQL Server database `AstraConfig`. Exported test rows live in `AstraTestLog`. Both are reached through FireDAC’s MSSQL driver. The connection string is built at startup from `AstraConfiguration.INI` (`[Database]`, keys `Server`, `Database`, `UserName`, `Password`), defaulting the database to `AstraConfig` and the user to `sa` (`AstraCommon/AstraDataModule.pas`). The design-time connection in `AstraDataModule.dfm` still points at `opc.astraspace.com` with password `CHANGE_ME`.

## 1. Project inventory

Twenty-one `.dpr` projects. Thirteen are in `Astra.groupproj`. Eight are queue experiments under `TaskManager`. `TaskManager/GoliathTests.groupproj` is named in `README.md` and is not in the tree. `Astra.groupproj` points every project at a `Y:\` drive and misspells the test-manager path as `Y:\AstraTesttManager\`.

Line counts are source lines in `.pas` / `.dpr` (and `.dfm` where the form is the bulk of the work). They were counted from this tree.

### Shared code, not a project

| Folder | Size | Role | Dependencies |
|---|---|---|---|
| `AstraCommon` | 19 units, ~4,500 lines, plus `AstraDataModule.dfm` (~1,800 lines of FireDAC components) | Packet codec, UDP device, OPC client, binary log, FireDAC data module, logger | FireDAC MSSQL, Indy (`IdGlobal` byte buffers), dOPC, Spring4D dictionaries, `ActiveX` (`CoInitialize`), optional CodeSite |
| `TaskManager` (units at the folder root) | ~1,500 lines: `GenericQueue.pas` 517, `Task.pas` 365, `TextLogger.pas` 233, `TimerTask.pas` 103, `GenericPusher.pas`, `GenericPopper.pas`, `Timer.pas` | Threads, queues, 100 ms poll tasks | `Windows`: `WaitForMultipleObjects`, `CreateWaitableTimer` / `SetWaitableTimer`, `CreateFile`, the `0x406D1388` thread-name exception. Spring4D collections in the queue |

`Task.pas` is a Win32 event loop. Every bridge thread, log writer, and OPC popper is a `TTask` waiting on kernel handles. That model does not need to be copied. `asyncio` tasks replace it.

### Applications in `Astra.groupproj`

| Project | What it does | Rough size | Main dependencies |
|---|---|---|---|
| `AstraBridgeServer` | Windows service. `BridgeMonitor` polls `Tests` every 100 ms, starts `TAstraBridge` for `min(ID)` where `Active = 1`, and on stop runs `EXEC spTestExport`. The bridge loads devices and interfaces from stored procedures, listens on `Servers.Port`, checks source IP, payload length, and a 4-byte `t_ms` at the start of the payload, writes `LOG-T{test}-I{intf}.DAT`, and pushes values to OPC. | ~710 Pascal lines, small service dfm | VCL service (`Vcl.SvcMgr`), Indy UDP, dOPC, FireDAC, `AstraCommon`, `TaskManager` |
| `AstraBridgeServerDesktop` | Same bridge with a form instead of a service. | desktop `.dpr` only | same, VCL form |
| `AstraTMoIP` | Windows service. Builds `TAstraDecoder`, which always starts stage 1 and stage 2 decoders. | service shell is tiny; `AstraDecoder.pas` is 479 lines | Indy UDP, FireDAC, `AstraVarPacket`, `TaskManager`. No C code linked |
| `AstraTMoIPDesktop` | Same decoder with a form. | desktop shell | same |
| `AstraTMEncoder` | VCL simulator. Loads `spGetInpPacketSizes`, and on a timer (base rate often 200 Hz in the comments) packs selected packets into the `IRIG106` minor frame at `Sequence * packetRate mod irigRate = 0`. Sends the encoded frame to `2357 + stage`. Can drop a configured percent of frames. Also displays UDP it receives. | 339 Pascal lines, ~500-line dfm | VCL, DevExpress grid/skins (`cxGrid`, `dxSkins*`), Indy, FireDAC, `AstraVarPacket` |
| `AstraLogExporter` | Windows service. `JobMonitor` polls `Jobs` every 100 ms (`SELECT TOP 1 … WHERE Done = 0`), rewrites the connection string from `AstraConfig` to `AstraTestLog`, and runs `TBinLogExporter`. | ~490 Pascal lines | `Vcl.SvcMgr`, FireDAC, `AstraBinLogFile`, `AstraVarPacket` |
| `AstraLogExporterDesktop` | Same exporter with a form. | desktop shell | same |
| `AstraConfigurator` | The tool operators actually use. Tree of vehicle → stage → version → release → smart node → packet. Edits fields, link types, connectors, pin-to-variable mappings, devices, servers, tests. Exports a Simulink CSV, a mapping CSV, and LabVIEW/NI shared-variable CSVs (`ExportAsTags`). Grid export also offers CSV, TXT, HTML, XML, XLS, XLSX via DevExpress `cxGridExportLink`. | ~1,820 Pascal lines, ~4,950 dfm lines (`Main.dfm` alone is ~3,000) | VCL, DevExpress (grids, bars, skins, `dxDBTreeView`, print/export packages), FireDAC, `AstraDataModule` |
| `AstraGenerator` | Console. Looks up a node with `spGetNodeID` and writes the interface CSV. The guard is `ParamCount <> 3` while the error text lists four arguments and the body reads `ParamStr(4)`. The saved debugger command line is `eMaster R2L c:\Astra\R2L-Simulink.CSV`. | 42 lines | FireDAC, `AstraDataModule` |
| `AstraTestManager` | Starts and stops tests (`spTestStart`, `spTestStop`), lists actors and interfaces, waits until `Jobs.Done` is set, shows the exported table, writes CSV. | ~340 Pascal lines, ~740 dfm lines | VCL, DevExpress grids, FireDAC. `frx24` (FastReport) is on the package list and is not referenced by any unit |
| `AstraDevice` | VCL UDP peer for bench tests. On a timer, sends a buffer whose first 4 bytes are `t_ms`, optionally prefixed with the packet id. Prints what it receives. | ~180 Pascal lines, ~375-line dfm | VCL, DevExpress editors/skins, Indy. Does not open the database |
| `AstraConfigurationManager` | VCL editor for a **different** hardware model (boards, stacks, stars, devices, sensors, actuators, links) mapped with Devart EntityDAC. The forms are thin; `DataModel.*.pas` is generated. | ~9,200 Pascal lines, of which ~8,300 are generated (`DataModel.Classes.pas` 3,160, `MetaData` 2,651, `Linq` 2,242, `Context` 243). `Main.dfm` is ~10,900 lines | VCL, DevExpress, EntityDAC, the design-time package `EntityDac`. Not used by the bridge |
| `dclDataModel` | Design-time package that registers `TDataContext` on the EntityDAC palette. `requires designide, EntityDac`. | package + the generated units | RAD Studio IDE only |

### `TaskManager` experiments

These are harnesses for the queue, not ground-station features. Leave them behind once the Python services have their own tests.

| Project | Size (pas+dfm lines) | What it exercises |
|---|---|---|
| `QueueTest1` | ~300 | `TTimeSyncQueuePopControl` |
| `QueueTest2` (`TaskTest.dpr`) | ~410 | task start/stop |
| `QueueTest3`, `QueueTest4` | ~300 each | queue variants; the time-sync control is commented out |
| `L2R_1`, `L2R_2` | ~340 each | OPC read → outbound UDP, hard-coded item `\\.\AstraL2R\…` |
| `R2L_1` | ~500 | UDP read → OPC write of `\\.\AstraR2L\t_ms` |
| `R2L2R` | ~200 | both directions on one form |

`L2R_*` and `R2L_1` link dOPC and call `CoInitialize`. They are early prototypes of `AstraCommon`’s pusher and popper.

### Third-party C: `AstraTMoIP/src`

44 C/C++/header files, 16,200 lines. Irig106.org IRIG 106 Chapter 10 (BSD-style license in the file headers; the notice forbids using the Irig106.org name to endorse a derived product). Includes Chapter 10 packet I/O (`irig106ch10.c`), TMATS, PCM, analog, time, 1553, UART, Ethernet, CAN, ARINC 429, video, and a network-stream mode (`I106_READ_NET_STREAM` in the matching Delphi translation).

Nothing in any `.dpr` compiles or links these files. `AstraTMoIP/IRIG106.pas` (302 lines) and `IRIG106Ch10.pas` (230 lines) are unfinished Delphi translations of the Chapter 10 header. No unit `uses` them. `IRIG106.pas` only accepts data type Ethernet format 0 and then stops. The live decoder never consults a Chapter 10 sync word (`0xEB25`).

## 2. Proposed replacement for each project

One Python package, three long-running processes, one web app, two small CLIs. Suggested layout:

```
astra/
  codec/        # field layout, bit pack/unpack, transforms, OPC/SQL type names
  binlog/       # LOG-T*-I*.DAT reader and writer
  db/           # psycopg access to config and test-log databases
  bridge/       # UDP <-> tags, DAT logging, test lifecycle
  tmoip/        # minor-frame reassembly
  exporter/     # Jobs -> PostgreSQL tables
  opcua/        # embedded OPC UA server
  web/          # configurator + test manager
  cli/          # generator, device simulator, tm-encoder
```

Libraries, all free:

| Concern | Library |
|---|---|
| Services, HTTP, CSV download | `fastapi` + `uvicorn` |
| UDP | stdlib `asyncio.DatagramProtocol` |
| PostgreSQL | `psycopg` 3. SQLAlchemy 2 only inside the web app’s CRUD. The bridge and exporter should use SQL text, the same way FireDAC does |
| Schema migrations on top of `database/postgres/` | `alembic` |
| OPC UA server embedded in the bridge | `asyncua` |
| Chapter 10 C, if it is ever called | `cffi` against a shared library built from `AstraTMoIP/src` |
| Bit packer, once profiled | a Mojo module called from Python (see §3) |
| Tests | `pytest` |
| NI CSV / Simulink CSV / our own CSV | stdlib `csv` |
| XLSX, only if someone still imports the grid export | `openpyxl` |
| Operator UI | the web app. `PySide6` (LGPL, dynamic linking, no fee) is the fallback if a screen must run with no browser |

Do not port a `.dfm`. `AstraConfigurator/Main.dfm` and `AstraConfigurationManager/Main.dfm` are DevExpress layout. Rebuild the workflows.

### Per project

| Delphi | Python replacement |
|---|---|
| `AstraCommon` codec (`AstraNetPacket`, `AstraVarPacket`, `TBitStream`, the 14 `TVehicleDataTypes`, `TransformOutput`) | `astra.codec`. Keep the type table in one module so pack, OPC node type, and `CREATE TABLE` cannot drift. Mojo only for `pack` / `unpack` if a profile says to (see §3) |
| `AstraCommon` binary log | `astra.binlog`. Magic `0x1A2B`, check `0xE5C4`, version, test id, interface id, record size, then records of OLE `TDateTime` (8-byte little-endian double, local `Now`) plus `RecSize` payload bytes. Filename `LOG-T{test}-I{intf}.DAT` |
| `AstraCommon` data module | `astra.db`. One connection helper reading the same INI keys, then environment variables once the services move off `sa`. Replace the 30 stored-procedure calls with SQL functions. Do not generate an EntityDAC-style class per table |
| `AstraCommon` OPC units (`AstraInpPopper`, `AstraOutPusher`, `AstraOpcClient*`, `AstraOpcThread`) | `astra.opcua`, an `asyncua` **server** inside the bridge process. David has confirmed LabVIEW will drop NI shared variables and subscribe to these tags. Tag path `Astra{PacketName}/{field}`. `asyncua` is pure Python, so this is the same code on x86_64 and ARM64 |
| `TaskManager` root units | Not a port. `asyncio.Queue` and `asyncio` tasks. The 100 ms `TTimerTask` loops become `asyncio.sleep(0.1)` polls, or `LISTEN/NOTIFY` later if the polling is annoying |
| `AstraBridgeServer` and `AstraBridgeServerDesktop` | `python -m astra.bridge`, one process, systemd unit. Desktop and service targets collapse. Poll `tests` for `active`, bind `ASTRA_BRIDGE_PORT` (default 2357, the Delphi literal; not a fixed field value), run the same accept/reject rules, write DAT files, update OPC UA nodes |
| `AstraTMoIP` and `AstraTMoIPDesktop` | `python -m astra.tmoip`. Same reassembly as `TAstraStageDecoder`. Listen on `ASTRA_BRIDGE_PORT + stage` for stages `1 .. ASTRA_STAGE_COUNT` (default 2) and forward reassembled datagrams to that same bridge port. The Delphi code hard-coded `127.0.0.1:2357` and always constructed stages 1 and 2 |
| `AstraTMEncoder` | `python -m astra.cli.tm_encoder`. Headless loop first, so it can generate fixtures. A page in the web app can wrap it later. DevExpress grid goes away |
| `AstraLogExporter` and desktop | `python -m astra.exporter`, systemd. Same job poll, `CREATE TABLE` from the field list, bulk insert with `psycopg` |
| `AstraConfigurator` | Web app: the version tree, field editor, pin mapping, device/server/test screens, and the three exports that matter (Simulink CSV from `spGetInterface`, mapping CSV from `spGetMappingWithOrders`, tag CSV). Skip the DevExpress HTML/XML/XLS buttons unless a consumer is named. PDF of the wiring list is the browser print dialog |
| `AstraGenerator` | `python -m astra.cli.generate STAGE NODE INTERFACE FILE.csv`, with an argument count that matches the four parameters the body already tries to read |
| `AstraTestManager` | Pages on the same web app: start/stop, job status, paged view of `{packet}_{test}`, CSV download. The hardcoded query `select * from AstraTestLog.dbo.L2R_1` in `qryIntfData` is a design-time leftover; the real screen must take the table name from the packet |
| `AstraDevice` | `python -m astra.cli.device --packet-id --size --rate --host --port`. A bench tool, not a service |
| `AstraConfigurationManager` + `dclDataModel` | No direct port of EntityDAC or the design-time package. The v3 hardware editor is a separate decision (§7). If it is still wanted, it is a handful of CRUD screens. The schema in `database/` is the Configurator schema, not those EntityDAC tables |
| `TaskManager/QueueTest*`, `L2R_*`, `R2L_*`, `R2L2R` | Do not port. Their behavior is already inside `AstraCommon` |
| `AstraTMoIP/src`, `IRIG106.pas`, `IRIG106Ch10.pas` | Do not rewrite. Keep the C tree in place for a later `cffi` build. Delete nothing in this planning step. The Delphi stubs are unused |

### Wire format the codec has to match

`TVehicleDataTypes` in `AstraVarPacket.pas` is the contract. Bit order is little-endian, LSB first inside the byte (`TBitStream` comment and `SaveBit`). Nested records are `TypeID > 100`: they flatten to `prefix_field` or `prefix_index_field`. After the real fields, each field with `Override` set grows a trailing 1-bit `ovr_{name}`.

| Id | Name | Bits in the payload | In-memory width | OPC type | SQL type emitted by `ExportAsSqlCreateScript` |
|---|---|---|---|---|---|
| 1 | `bool` | 1 | bool | Boolean | `bit` |
| 2 | `u8` | 8 | byte | UInt8 | `tinyint` |
| 3 | `u12` | 12 | word | UInt16 | `smallint` |
| 4 | `u16` | 16 | word | UInt16 | `int` |
| 5 | `u32` | 32 | longword | UInt32 | `bigint` |
| 6 | `i8` | 8 | shortint | Int8 | `smallint` |
| 7 | `i16` | 16 | smallint | Int16 | `smallint` |
| 8 | `i32` | 32 | longint | Int32 | `bigint` |
| 9 | `f32` | 32 | single | Single | `float` |
| 10 | `f64` | 64 | double | Double | `float` |
| 11 | `i32q8` | 32 | integer | Int32 | `int` |
| 12 | `i32q16` | 32 | integer | Int32 | `int` |
| 13 | `u8q8` | 8 | byte | UInt8 | `tinyint` |
| 14 | `u16q16` | 16 | word | UInt16 | `smallint` |

`u12` is why this is a bit packer and not `struct.unpack`. The Q types are **not** shifted in `LoadValue` / `SaveValue`. They travel as raw integers. Scaling, when it happens, is `TransformationID`.

`TransformOutput` (ids 1–14, polynomials in `AstraVarPacket.pas`, including the cube-root curve `g` and its inverse cubic `f`) runs on the way **to** OPC. `TransformInput` is never called. L2R values are written into the outbound payload as received. A transformed field’s OPC type and SQL type become `Double` / `float`. A Single or Double OPC write of exactly 0 is replaced with `1e-7` before `SyncWrite` (`AstraInpPopper.SyncWrite`). Preserve that until a LabVIEW owner says zero is safe.

UDP accept rules in `TAstraBridge.IdUDPServerUDPRead`, in order: known packet id, payload length equal to `TAstraVarPacket.Size` (the byte `EncSize` from `spGetVarType`, after `spCalcVarTypeSizes`), peer IP equal to the device row, then the first 4 payload bytes as a little-endian int32 strictly greater than `Device.LastT_MS`. That last check assumes the `t_ms` convention; it does not look at the field table. Rejected packets are dropped with a CodeSite warning and are not logged.

R2L vs L2R is inverted relative to the English word “input”. In `TAstraBridge.CreateIntfs`, `IsInput = false` builds `TAstraInpIntf` (UDP → OPC) and `IsInput = true` builds `TAstraOutIntf` (OPC → UDP). Keep that polarity.

When the bridge stops a test it calls `spTestExport`. The exporter then creates `{PacketName}_{TestID}`, with `t_ms` as the primary key when that is the first field, otherwise an `IDENTITY` column named `ID`.

## 3. What is performance-sensitive, and where Mojo fits

The rates written down in `AstraTMEncoder` are a 200 Hz minor-frame clock and R2L packets at 100, 10, or 1 Hz. Payloads are one interface: a few dozen fields, hundreds of bytes, not a software radio. The Delphi decoder hardcodes two stages; the port reads `ASTRA_STAGE_COUNT` (default 2). The bridge’s OPC group update rate for L2R is 1000 ms. The test and job polls are 100 ms.

That is not a throughput problem for Python. It is a correctness problem (bit packing, reassembly, transforms).

| Path | Cost in this code | Recommendation |
|---|---|---|
| Bit pack / unpack of one packet (`TBitStream`, including `u12` and `ovr_` bits) | A bit-at-a-time Delphi loop. A direct Python `for bit in bits` port would be the slow version. Packing each field with integer shifts into a `bytearray` is already C speed underneath, and at 100–200 packets/s it will not show up | **Python first.** Move `pack` / `unpack` into Mojo only if a profile of the exporter (a whole test, not one packet) or a future higher rate says the Python function is hot. The Mojo function should take a flat layout of `(bit_width, kind)` plus a bytes buffer, and return bytes or a list of ints/floats. It should not open the database |
| `TransformOutput` id 1 (cube roots) | One scalar formula per transformed field | Python `math`. Mojo does not help a handful of scalar calls |
| UDP send/receive | Kernel and the Indy callback, not the codec | stdlib `asyncio`. Mojo’s I/O is the wrong tool here |
| Minor-frame reassembly (`PushBufferToPacket`, leftover bytes, drop until next `row_id`) | Byte copies and a dictionary of packet id → encoded size | Python `bytearray`. This is the logic most likely to be ported wrong; keep it readable |
| DAT logging | One buffered write per packet | Python buffered file. Same layout as `TAstraBinLogFile` |
| Bulk export of a long test | The only loop that runs flat out: read DAT, unpack, insert | Python unpack is the right default. If a multi-hour test is slow, this is the Mojo candidate: unpack a batch of records in one call, then `psycopg` `COPY` or `executemany`. The database insert will dominate unless the packer was ported as a per-bit Python loop |
| Chapter 10 library (16,200 lines of C) | Not on the live path | **Keep the C.** A Mojo rewrite would re-implement TMATS, PCM, 1553, and checksums that already exist and are not called. If a future tool opens a real `.ch10` file, build `libirig106.so` and call it with `cffi`. Mojo is a poor fit there because the artifact to preserve is the existing C, not a numeric kernel |
| OPC, SQL, the web app, tree editing | Waiting on the network | Python |

**Calling Mojo from Python.** Put the packer in its own Mojo package with a tiny surface (`unpack_records`, `pack_records`). Call it through the Python interop of the Mojo compiler in the pinned container (see §5): Python imports the Mojo module and calls those two functions. The import details have moved between Mojo releases and should be whatever that pin documents. Build that package on each deployment architecture. An x86_64 `.so` does not run on ARM64. Modular’s current requirements include Linux aarch64 (Ubuntu 22.04+, glibc 2.34+, Neoverse N1 / Graviton2 class or newer); §5 says what to do if the test-stand board is older than that, or if that pin’s Python import is missing on aarch64.

**Fallback, only if that import cannot be shipped inside the service for the pinned SDK:** compile the same Mojo sources to a shared library with a C ABI and load that library with `cffi`. The function signatures stay the ones above. This is a packaging fallback.

**Fallback if a pinned Mojo SDK cannot produce a callable library on the deployment machine at all:** a short C implementation of the same packer, also loaded with `cffi`. Numba is the other free option for a numeric loop, and it is a worse fit than C here because the layout is bit widths and mixed ints/floats, not an array of one dtype. Do not start with either fallback. The Python integer-shift packer is enough until a measurement says otherwise.

Do not put sockets, `asyncua`, or `psycopg` in Mojo.

## 4. Database: SQL Server to PostgreSQL

### What is and is not in the repo

`AstraConfigurationManager/DataModel.sql` is a Devart Entity Developer script dated 2017-04-21, aimed at SQL Server 2016. It creates 12 tables and then stops:

`StarDevices`, `BoardStacks`, `VarTypes`, `Objs`, `Stars`, `Devices`, `Boards`, `Stacks`, `Sensors`, `Actuators`, `Links`, `StackStars`.

No stored procedures, no views, no indexes beyond the primary and foreign keys, no seed data. The script is not runnable top to bottom: `StarDevices` is created before `Stars` and `Devices`, which it references. `Database Initialization.sql` inserts into `VarTypes.ValListID` and `AstraClasses`, columns and tables this script does not define.

`DataModel.Mapping.xml` is a later EntityDAC model and does not match that script. Its tables include `AstraMetas`, `AstraObjs`, `AstraClasses`, `AstraVars`, `BoardVars`, `BoardObjVars`, `ProcBlocks`, `ProcBlockVars`, `ValLists`, `ValListValues`, `VarMappings`, `StackBoards`, `StarStacks`, `DeviceStars`, `VarUses`. Inheritance is class-table (`Devices.ID` → `AstraMetas.ID`), with `IDENTITY` on `AstraMetas` and `AstraObjs`. `Boards` has `IsMaster bit` and `MainID`. `VarTypes` has `ValListID`. None of this is what the bridge queries.

The running schema is the one FireDAC uses, and it is **not** either of those files. Both databases were in the SQL Server backups: `AstraConfig.bak` (2017-07-05) and `AstraTestLog.bak` (2017-04-12). The verified scripts are under `database/`:

- `database/README.md` documents the mapping, the procedure translation, and the 2026-10-03 check against SQL Server 2022 and PostgreSQL 16.
- `database/mssql/01_schema.sql` and `database/mssql/03_programmability.sql` are the T-SQL schema and the original views, functions, procedures, and trigger.
- `database/postgres/01_schema.sql` and `database/postgres/03_programmability.sql` are PostgreSQL schemas `config` (AstraConfig) and `testlog` (AstraTestLog), plus the PL/pgSQL functions.

`mssql/02_data.sql`, `postgres/02_data.sql`, and the `.bak` files stay outside the repository. `.gitignore` ignores `database/**/02_data.sql` and `*.bak`. The data scripts contain a plain-text `Servers.Password`.

The backups hold the Configurator schema (`TreeVersions`, `Fields`, `VarTypes`, and the rest below), not the EntityDAC tables in `DataModel.sql` / `DataModel.Mapping.xml`. From the scripts and from `AstraDataModule.dfm`, `AstraDataModule.pas`, `JobMonitor.pas`, `BridgeMonitor.pas`, and `TestsManager.pas`, the bridge and the tools call these objects in `AstraConfig`:

Tables touched directly: `TreeVersions`, `Fields`, `VarTypes`, `Connections`, `LinkTypes`, `Connectors`, `Transformations`, `Devices`, `Servers`, `Tests`, `Actors`, `Jobs`, `MsgLog`, plus the view or table `FieldsOnScope` inside the connections query.

Stored procedures: `spVarTypes`, `spCleanTypes`, `spGetPacket`, `spSetPacket`, `spDuplicate`, `spDelete`, `spGetInterface`, `spGetNodeID`, `spGetVarType`, `spGetVarTypeFields`, `spCalcVarTypeSizes`, `spGetHardwareTree`, `spGetHardwareNode`, `spMappingExists`, `spAddMapping`, `spDelMapping`, `spGetMappingByConnection`, `spGetMappingByField`, `spGetMappingWithOrders`, `spMoveNodeToSeq`, `spMoveField`, `spTestStart`, `spTestStop`, `spTestInterfaces`, `spTestExport`, `spGetServer`, `spGetDevice`, `spGetIntf`, `spGetDevices`, `spGetIntfs`, `spGetNodeByPacket`, `spGetInpPacketSizes`.

Several of those are the product. `spDuplicate`, `spDelete`, `spMoveNodeToSeq`, `spMoveField`, `spCalcVarTypeSizes`, and `spTestExport` hold tree and sizing rules that cannot be reconstructed from the Pascal. Their bodies are in `database/mssql/03_programmability.sql` and, translated, in `database/postgres/03_programmability.sql`. `spGetVarType` returns `EncSize` in **bytes**; field `EncSize` from `spGetVarTypeFields` is in **bits**. The UDP length check uses the byte value.

`AstraTestLog` (`testlog`) holds one table per exported interface, named `{PacketName}_{TestID}`, created at runtime by `ExportAsSqlCreateScript`. The backup contains 16 of those wide tables (`L2R_*` and `R2L_*`). `qryIntfData` is hard-wired to `AstraTestLog.dbo.L2R_1`.

`Jobs` has both columns. The primary key is `(TestID, PacketID)`. The migrated `IntfID` column is a nullable integer. `JobMonitor` filters `PacketID`. `TestsManager` filters `IntfID`. Both queries name real columns. **Resolved:** `PacketID` is the real key. `IntfID` is a generated UUID, not the key the exporter selects on. The loaded `config.jobs.intfid` column stays `integer` until a later migration widens it.

### Type and dialect mapping that is visible now

| SQL Server, as used here | PostgreSQL | Why it matters in this code |
|---|---|---|
| `int` | `integer` | Ids, ports, sizes |
| `varchar(n)` | `varchar(n)` | Names. Delphi `TStringField` against `varchar`, not `nvarchar`, except `Connectors.Description`, which is `TWideStringField` |
| `bit` | `boolean` | `Tests.Active`, `Override`, `InSequence`, `IsInput`, `Jobs.Done`, EntityDAC `IsMaster` / `IsPublic`. CSV export writes booleans as `0`/`1` (`ExportDataSetToCSV`) |
| `IDENTITY` / `TFDAutoIncField` | `GENERATED BY DEFAULT AS IDENTITY` | `Fields.ID`, `Tests.ID`, `Devices.ID`, log-table `ID` when the first field is not `t_ms`. Scripts that insert explicit ids (the `AstraClasses` seed) need `OVERRIDING SYSTEM VALUE` or a default-only identity |
| `tinyint` | `smallint` | `u8` / `u8q8` log columns. PostgreSQL has no `tinyint`. Check `0..255` in the exporter |
| `smallint` | `smallint` | `u12` values fit (`0..4095`). The column is signed; the packer is unsigned |
| `bigint` | `bigint` | Chosen in the Delphi map for `u32` and `i32` because SQL Server `int` is signed and cannot hold every `uint32` |
| `float` (default `float(53)`) | `double precision` | Both `f32` and `f64` log columns, and every transformed field. A `real` column would not match. `f32` and `f64` become indistinguishable once stored |
| `TSQLTimeStamp` on `Tests.Started` / `Stopped` | `timestamp` without time zone | FireDAC mapped these as `datetime`, not `datetimeoffset`. No time zone is stored |
| `TDateTime` inside DAT files | not a SQL type; convert with the OLE epoch `1899-12-30` | Local time from Delphi `Now`, not UTC |
| Three-part names `AstraConfig.dbo.X`, `AstraTestLog.dbo.X` | schema `config` and schema `testlog`, `search_path` set per service | Every stored-proc name and `UpdateOptions.UpdateTableName` is three-part. The scripts use `testlog`, not a schema named `log` |
| `SELECT TOP 1` | `ORDER BY … LIMIT 1` | `JobMonitor` has no `ORDER BY`, so “first” job is undefined. Pick an explicit order when porting, and record it |
| `EXEC sp @p` and output parameters (`@NodeID` read back after `ExecProc`) | `CREATE FUNCTION … RETURNS` or procedures with `INOUT` | `spGetNodeID`, `spGetPacket`, `spGetVarType`, `spMappingExists` are OUT-param APIs |
| `GO` | drop it | client batch separator |
| `bit NOT NULL` defaults `'0'` / `'1'` in the EntityDAC model | `boolean NOT NULL DEFAULT false` | only relevant if that model is the one in the backup |
| Case-insensitive identifiers | fold to lower case, unquoted | SQL Server’s default collation hid this |

`Servers` stores `SqlServerInstance`, `DatabaseName`, `UserName`, and `Password` in clear text, and `OpcServerName`, `WinName`, `FullName`. The exporter clones the FireDAC string and does a textual replace of `AstraConfig` with `AstraTestLog`. On PostgreSQL there is one server and two schemas (`config` and `testlog`). Those columns should shrink to a schema/database name. Do not copy production passwords into a seed script. The INI default user is `sa`; the new role should be a normal login with rights on `config` and `testlog` only. The plain-text `Servers.Password` is why `02_data.sql` stays outside git.

`MsgLog` inserts are built with `Format('INSERT … VALUES(''%s'', %d)', …)` in `AstraLogger.pas`. Use bound parameters in the port. That is a bug fix, not a behavior change.

`spCalcVarTypeSizes` stays the authority for payload length. Its body is in `database/postgres/03_programmability.sql`. Guessing the byte length as `ceil(sum(bits)/8)` is probably right and is not safe to assume: override bits and nested records are included, and any padding the procedure adds is invisible from the Pascal alone.

Tree icons that the queries depend on: `IconID` 5 is a smart node (`tblDevices` filter and `qrySmartNodes`), 6 and 7 are the two packet directions (`6 + ord(not IsInput)`), and 8, 9, 10 are hardware nodes excluded from the version tree.

### Getting onto PostgreSQL

1. Load `database/postgres/01_schema.sql`, then `database/postgres/03_programmability.sql`, into one database. See `database/README.md` for collation, identity, and the call-shape changes. Load `02_data.sql` only from the copy kept outside git.
2. The T-SQL procedures are already PostgreSQL functions. Call them as `SELECT * FROM config.spx(...)`. `spGetDevice`'s input parameter is `deviceid`. `spGetServer`'s second `ID`/`Name` pair is `id_1`/`name_1`. Known original bugs are listed in `database/README.md`.
3. Point the Python services at PostgreSQL. Keep SQL Server only as the reference for procedure results and exporter row diffs during the port. The `database/mssql/` scripts rebuild that reference.
4. Retire SQL Server when a synthetic test run through the new exporter matches the rows produced by the Win64 Delphi exporter fed the same generated `.DAT` (§6). There is no historical `.DAT` or packet capture to replay. The `AstraTestLog` rows from the backup are in `02_data.sql`, outside git; they are not a captured export of a live test.

## 5. Windows-only dependencies, and the Linux replacements

| Windows piece | Where | Linux replacement |
|---|---|---|
| OPC DA / COM (`dOPC`, `CoInitialize`, `ActiveX`) | Bridge popper/pusher, the `L2R`/`R2L` experiments, default server `National Instruments.Variable Engine.1` | An `asyncua` server inside the bridge. Confirmed: LabVIEW will subscribe to OPC UA tags from this process. OPC DA is not hosted anywhere in the new system |
| NI shared-variable CSV (`ExportAsTags`: `Name,Type,VarType,Network,…`) | Configurator “Export to LabVIEW” | Stop treating this as the interface LabVIEW imports. The bridge publishes `Astra{PacketName}/{field}` itself. Keep the old CSV generator only if the LabVIEW owner asks for it during the cutover (still open, §7 question 12). Item ids today look like `\\.\Astra{PacketName}\{field}` |
| `Vcl.SvcMgr` services for bridge, TMoIP, exporter | three `ServiceMain.pas` units | systemd units, one process each. The desktop twins (`*Desktop.dpr`) are the same code with a form; one Linux process with a log file replaces both |
| VCL + DevExpress skins, grids, bars, tree, `cxGridExportLink` | Configurator, Test Manager, Configuration Manager, Device, TM Encoder | Web UI. CSV via the stdlib. XLSX via `openpyxl` only if required. No DevExpress print engine: the wiring report is an HTML page |
| FastReport (`frx24` on the package list) | not referenced from any `.pas` | nothing to replace |
| EntityDAC + `dclDataModel` + design-time `Y:\` paths | Configuration Manager | not part of the Linux runtime |
| FireDAC MSSQL, `TFDPhysMSSQLDriverLink`, three-part names | every database process | `psycopg` |
| Indy UDP | bridge, decoder, encoder, device | `asyncio` datagram endpoints |
| `WaitForMultipleObjects`, waitable timers, `CreateFile` in `TextLogger` | `Task.pas`, `Timer.pas`, `TextLogger.pas` | `asyncio`, `threading` only if a blocking library forces it, ordinary files for logs |
| Delphi `TDateTime` and the Win64 FPU | DAT timestamps; `power()` in transformation 1 | `struct.unpack('<d')` and the OLE epoch. Production was Win64, so intermediates are SSE2 `float64`, the same width as Python `float` and IEEE-754 binary64 on both Linux architectures. Golden transform outputs come from a Win64 harness (§6), not from a Win32 build |
| CodeSite (`USE_CODESITE`) | optional traces | stdlib `logging` |
| Clear-text SQL passwords, `sa`, `CHANGE_ME` | INI and `Servers.Password` | a dedicated PostgreSQL role, password in the environment or a root-only file, not in the database and not in git |

LabVIEW remains a separate application and will be an OPC UA client of the bridge. The ground-station processes run on Linux. The bridge UDP port is `ASTRA_BRIDGE_PORT` (default 2357, the legacy literal). TMoIP listens on that port plus the stage number. Stage count is `ASTRA_STAGE_COUNT` (default 2).

### Linux on x86_64 and ARM64

The intended host is Ubuntu (22.04 LTS or 24.04 LTS; both have glibc newer than 2.34). Build and test both `x86_64` and `aarch64`. Ubuntu’s ARM64 userland is little-endian. `aarch64_be` is not a target.

**Wheels and pure-Python packages.**

| Package | On Ubuntu ARM64 |
|---|---|
| `asyncua` | Pure Python. `pip install` it on either architecture. No compiled extension on the OPC path |
| `psycopg` 3 | Use `psycopg[binary]`. The project publishes `manylinux` wheels for `aarch64` as well as `x86_64`. Do not compile `psycopg` from source on the test stand unless that wheel is actually missing for the pinned version |
| `PySide6` | Qt publishes `aarch64` manylinux wheels (glibc 2.28+, so Ubuntu 22.04+ is in range). This is only the optional desktop UI. The services and the web app do not import it, so an ARM64 service image should not depend on it |
| FastAPI, uvicorn, pytest, the stdlib `asyncio` UDP stack | Pure Python or universal wheels. Same lockfile on both architectures, installed fresh on each runner so a wheel tag cannot be skipped by copying a `venv` |

**Mojo compiler.** Local builds and CI use Modular’s published container `modular/max-nvidia-base:26.6.0` (manifest list `sha256:53a1f0b502e67f400b0bc3c4575fde73f84d468ea03b977eaad2ef6fcd303c31`). That image contains Mojo compiler 1.1.0 and publishes both `linux/amd64` and `linux/arm64`, so the same pin runs on both GitHub runners. Do not `pip install` Mojo and do not build the compiler. The image entrypoint is `max serve`; a local `docker run` overrides it with `bash` (see `mojo/README.md`). The service still does not import Mojo. If a later Python binding is missing on one architecture, that architecture stays on the Python integer-shift packer or the C ABI `cffi` fallback from §3. Boards below the SDK’s CPU baseline (a Raspberry Pi 4 / Cortex-A72 is the usual case; the published host requirement is Neoverse N1 / Graviton2 class or newer) run the Python or C packer.

**Endianness and alignment that must not leak into the port.** Win64 and Ubuntu aarch64 are both little-endian, so a port that happens to use host byte order will pass on both and still be the wrong shape of code. The Delphi codec does not document endianness at the UDP boundary; it copies host memory:

- `TAstraNetPacket.GetIdPayload` / `SetIdPayload` `Move` a Delphi `integer` (4 bytes). On Win64 that is little-endian. The port writes and reads it with `struct.pack('<i', …)` / `struct.unpack('<i', …)`, or `int.to_bytes(4, 'little')`. Never `sys.byteorder`, never `struct.pack('i', …)` (native), never a Mojo or C `Int32` stored with a host store that is not specified as little-endian.
- `GetDeviceT_MS` copies the first 4 payload bytes into an `integer` the same way. Same `'<i'` rule. It does not consult the field table.
- `TBitStream` walks bits LSB-first inside each byte. Multi-byte values are first stored in a native variable (`word`, `LongWord`, `SmallInt`, `single`, `double` in `LoadValue` / `SaveValue`) and those in-memory bytes are then streamed. On Win64 that memory is little-endian, so the payload is the little-endian two’s-complement or IEEE-754 layout, LSB first, including a `u12` that shares bytes with the next field. Implement this as shifts into a byte buffer (`bit 0` of the value goes to the next LSB of the next byte). Do not `memcpy` a host `uint16_t`, `uint32_t`, or `double` into the payload. That memcpy is endian-correct on these two hosts and wrong as soon as anyone builds the C or Mojo packer for a big-endian target, and it is how a vectorized Mojo path would silently change `u12` boundaries.
- `f32` and `f64` bit patterns are IEEE-754 little-endian (`struct.pack('<f', …)` and `'<d'`). Transformation 1 runs in `float64` to match Win64. Do not compute it in `float32` on one architecture.
- `TAstraBinLogFile.TBinLogFileHeader` is `word, word, integer, integer, integer, integer` (magic `0x1A2B`, check `0xE5C4`, version, test id, interface id, record size). At Delphi’s default alignment that is 20 bytes with no padding: each field is already naturally aligned. The record body is an 8-byte little-endian OLE `TDateTime` (`'<d'`, epoch 1899-12-30) plus `RecSize` payload bytes. Read and write the file with `struct` format `'<HHIIIId'` for header-plus-timestamp, not with a C `struct` cast and not with native alignment (`@`). AAPCS64 and the Win64 ABI happen to lay this particular struct out the same way; depending on that is how a later field addition gets different padding on the two compilers. ARM64 also faults some unaligned SIMD and atomic accesses. Keep the packer on scalar shifts; do not vector-load a payload at a bit offset.
- Zero the payload before packing. `SavePacket` `FillChar`s the buffer and `SaveBit` ORs bits in. A leftover `1` bit survives if the buffer is not cleared.

The check that this held: the same synthetic pack on the x86_64 CI runner and the ARM64 CI runner produces the same bytes, and both match the Win64 Delphi oracle below.

**CI.** One workflow, two runners:

- `ubuntu-24.04` (x86_64)
- `ubuntu-24.04-arm` (GitHub-hosted ARM64). If that runner is not enabled for the repository, use a self-hosted Ubuntu ARM64 machine. `qemu-user` is acceptable for the pure codec and DAT tests and is not acceptable as the only place the UDP loopback and OPC UA tests run.

Both jobs install the lockfile, run the same `pytest` suite (codec properties, oracle fixtures, binlog, localhost device → bridge → `asyncua` client, encoder → decoder), and start PostgreSQL the same way. A separate Mojo job on each runner pulls `modular/max-nvidia-base:26.6.0` and runs `mojo --version`, `mojo build` of `mojo/bitpack.mojo`, and `mojo run` of `mojo/test_bitpack.mojo` inside that container. The image has an arm64 variant, so the ARM64 job is not skipped. A container, compile, or smoke-test failure fails CI. The Python suite does not require Mojo. Cache keys include the architecture. Do not copy `venv` or `*.so` artifacts from x86_64 onto ARM64.

## 6. Porting order and how to check it

Each phase is releasable and testable without the later ones. Do not start with the configurator UI. The codec and the bridge are the product; the forms are editors for the database the codec reads.

There is nothing in the archive to replay. No `.DAT` files, no pcaps, no exported test tables. Confidence comes from a Win64 Delphi oracle run on synthetic inputs while RAD Studio can still build, from property tests of the packer, from a simulated vehicle and telemetry source on localhost, and from captures taken on the new host once a real test happens. Every one of those tests runs on x86_64 and on ARM64 (§5).

### What “matches the old behavior” means without a capture

1. **A Win64 oracle harness, not a search for old logs.** Add a console program, Win64 only, that compiles the existing codec units and writes fixtures. It does not need `AstraConfig`. `SetNodeID` is the method that hits SQL; `TVehicleDataType.SaveValue` / `LoadValue`, `TBitStream`, and `TransformOutput` do not. `TAstraVarPacket.SavePacket` does need `FPacket` already allocated, and that allocation is private and normally done by `SetNodeID`. Give the oracle a `{$IFDEF CODEC_ORACLE}` method that sets the buffer length, compile that program as Win64, and leave the ifdef out of `Astra.groupproj`. The harness then:

   - Builds synthetic layouts in code: every type id 1–14, a `u12` that begins at bit offset 4, arrays (`Qty > 1`), a nested record (`TypeID > 100`) flattened the way `LoadFields` flattens, and `ovr_` bits appended the way `LoadFieldOvrs` appends them.
   - Picks values inside each type’s range, including `0`, the max unsigned value, a negative `i32`, a quiet `f64`, and the inputs used for transformations 1–14.
   - Calls `SavePacket` / `LoadPacket` and writes `fixtures/oracle/*.json` (layout, values, packed hex) plus a `.DAT` written through `TAstraBinLogFile` (`Open2Write` / `Write` do not query SQL). Magic, check, 20-byte header, OLE timestamp, payload.
   - Prints `TransformOutput` for ids 1–14 as the exact `float64` hex (`%.17g` is not enough; dump the 8 bytes). Also records the OPC substitution `0 → 1e-7` for Single/Double, which lives in `AstraInpPopper.SyncWrite` rather than in the transform.

   Check those fixtures in. They are the byte-level contract. Regenerate them only from a Win64 build. A Win32 build is the wrong oracle: production was x64, and Win32 `Extended` intermediates would disagree with Python on transformation 1.

2. **Property and round-trip tests, no Delphi required.** On every CI architecture, for random layouts and in-range values: `unpack(pack(values)) == values`, packing is deterministic, and the hex from the x86_64 job equals the hex from the ARM64 job. Include a leading run of `bool` or `u12` so a later `f64` starts off a byte boundary. This catches an endian or alignment leak even when the oracle fixtures are few.

3. **A simulated vehicle and a simulated telemetry source.** `astra.cli.device` sends synthetic R2L datagrams (4-byte little-endian id, payload, `t_ms` in the first 4 payload bytes, stepping by the timer interval the way `AstraDevice` does). `astra.cli.tm_encoder` builds minor frames with the same rate rule as `_AstraTMEncoder` (`Sequence * packetRate mod irigRate = 0`, zero-fill of `packet_stream`, optional drops). Point both at localhost. The integration test is device → bridge → `asyncua` client, and encoder → TMoIP decoder → bridge, with assertions on which datagrams were accepted, the DAT payload bytes, and the OPC UA values. No NIC, no rocket, no NI server.

4. **Captures from here on.** The first time the Linux bridge sees real vehicle traffic, save `tcpdump -w` of the UDP ports and the `.DAT` files the new process writes. Review one test by hand against the OPC UA values, then store those files under `fixtures/live/` and replay them in CI. That corpus grows forward. It does not exist today, and the port does not wait on it.

The stored procedures are already in `database/` (§4). They are not required to prove the codec. `02_data.sql` and the `.bak` files stay outside git.

### Phase 0 — oracle fixtures

- Write and run the Win64 harness above. Commit `fixtures/oracle/`.
- Load `database/postgres/` when a later phase needs a database. Use `02_data.sql` only from the copy kept outside the repo. That work is parallel, not a gate on phase 1.

### Phase 1 — codec, transforms, DAT files

No database process yet. Layouts in the unit tests are the JSON from the harness, plus generated layouts for the property tests.

Tests, on both architectures:

- Round-trip every type id 1–14, the unaligned `u12`, arrays, a nested record, and `ovr_` bits.
- Byte-compare `pack` against the harness hex for the same values.
- `TransformOutput` matches the harness `float64` bits. Ids 2–14 are rational and should match at 0 ULP. Id 1 uses `power` and `sqrt`; compare exact bits first. If Delphi’s `System.Math.Power` and Python `math.pow` differ, record the harness hex as the expected value and keep the tolerance explicit in the test, in ULP, rather than loosening the formula.
- A `.DAT` from the harness reads back with the same header fields, timestamps, and payloads. A `.DAT` written by Python on x86_64 reads back on ARM64 and the other way around.

### Phase 2 — the read procedures the bridge needs

Port the read-only procedures listed in §4, including `spCalcVarTypeSizes` (`database/postgres/03_programmability.sql`). Compare Python results to SQL Server, rebuilt from `database/mssql/`, for each smart node used in the synthetic test: packet id, byte size, field list, device IP and port, input flag. Phase 1 does not wait on that database; its layouts come from the harness.

### Phase 3 — bridge

`asyncio` UDP server, DAT writer, OPC UA server, test poll.

Tests:

- The device simulator sends a scripted R2L sequence. The bridge writes a DAT whose payloads equal the sent payloads, and an `asyncua` client reads `TransformOutput` of those payloads, including `1e-7` for a zero float.
- One datagram each for wrong size, wrong source IP, and non-increasing `t_ms`. None of them appear in the DAT.
- An OPC UA write on an `IsInput` interface produces the outbound datagram `pack` built for those values, with no `TransformInput`.
- Run this on x86_64 and ARM64. The DAT payload bytes match across the two runs; timestamps are local and are not compared across hosts.

### Phase 4 — TMoIP decoder and encoder

Port `TAstraStageDecoder` and the encoder’s `BuildPacketStream` / timer together. The encoder is the source of frames; there is no captured stream to copy.

Tests:

- For a fixed sequence, rate, and packet list, the encoder’s minor-frame bytes match a Win64 harness that runs the same loop, or, if that harness is not worth linking Indy for, match a second implementation of the rate rule checked against the first few frames dumped from the Win64 `AstraTMEncoder` once the database exists. The rule itself (`Sequence * rate mod irigRate = 0`, zero fill) is tested in Python without that dump.
- The decoder, fed those frames, emits the original packet ids and payloads.
- A skipped `sf_id` does not emit a packet from the rest of that major frame. Match current behavior, including the quirks in §7, and put the quirk in the test name so it is a choice rather than an accident.
- A scripted drop pattern (the encoder’s drop percentage, fixed seed) produces the same counters on both architectures. `FDroppedMinorFrames` stays 0, because the Delphi code never increments it.

### Phase 5 — exporter

Feed a harness-generated `.DAT` through the Python exporter into PostgreSQL and, while SQL Server is still up, through the Win64 `TBinLogExporter` into a scratch database. Diff the rows. `t_ms` as primary key versus `IDENTITY` follows the first-field rule. Transformed columns are `double precision`. Bulk insert goes through `COPY`. After SQL Server is gone, the oracle is the harness values plus `TransformOutput`, not a leftover `AstraTestLog` table.

### Phase 6 — web app

Done. The operator app is `python -m astra.web`. It covers the configurator tree (add, rename, move, duplicate, delete), packet save and size calculation, var types and fields (nested records, description, short name, initial value, in-sequence, and transformation), pin mappings, devices, write-only server passwords, in-memory Send/Rate, and the three exports. Test manager pages start and stop a test, list jobs, and page or download the finished log. The generator CLI is `python -m astra.cli.generate`.

CSV from `ExportDataSetToCSV` uses `;` and quotes. Booleans are `0`/`1`. Lines end with CRLF.

Deliberate deviations:

- Hardware icons 8–10, areas, boards, connectors, and print hardware stay in phase 8 (`AstraConfigurationManager`). The mapping screen lists pins that already exist. It does not edit that tree. Question 2 is still open.
- The LabVIEW export is the OPC UA node list the bridge publishes (`Astra{PacketName}/{field}`), not the NI shared-variable CSV. Question 12 is still open.
- DevExpress HTML, XML, XLS, and XLSX grid exports are not ported. A browser print of the mappings table is the wiring list.
- There is no Win64 CSV golden in git, and no restored production database. The Simulink and mapping writers are checked against the `ExportDataSetToCSV` rules on a synthetic node, not against a file the Win64 configurator produced.
- Deleting a vehicle removes that row only. Child rows stay, with the old parent id. Icons 2–10 still delete their subtree.
- A transformation can be added and attached to a field. The page does not edit or delete an existing expression.
- Send and Rate live in the web process. They are not columns on `packets`. A restart clears them.

### Phase 7 — device simulator and live capture

The simulator from phase 3 stays as the bench tool. After the first real test on the Ubuntu host, archive the pcap and the DAT files (the live-capture step at the start of this section) and add them to the replay tests on both architectures.

### Phase 8 — decide on the EntityDAC hardware editor

Only after phases 1–6. The scripts in `database/` are the Configurator schema. They do not contain the EntityDAC v3 tables. If those tables were never what a vehicle was built from (question 2), do not port `AstraConfigurationManager`.

The Chapter 10 C library stays unbuilt unless a real Chapter 10 file appears later. If it does, the test is `cffi` decode versus the upstream `irig106` tools on that file, on both architectures, not a rewrite.

## 7. Risks and open questions

Risks that are visible from this tree:

- **Use `database/`, not `DataModel.sql`.** `DataModel.sql`, `DataModel.Mapping.xml`, and the FireDAC queries are three different models. The operational schema and procedures are in `database/`. Row data and the `.bak` files are not in git. Porting the 12-table script would produce a database the bridge cannot run on.
- **Behavior lives in the stored procedures.** Sizing, tree duplicate/delete, and “test stopped → jobs” are in `database/mssql/03_programmability.sql` and `database/postgres/03_programmability.sql`. A Python rewrite of those rules from guesswork will drift.
- **The LabVIEW edit is outside this repo.** The destination is settled: OPC UA tags published by the bridge, not NI shared variables. Someone still has to retarget the VIs. Who that is, and whether the old shared-variable CSV is needed for one release, is question 12.
- **`TransformInput` is dead code.** Commands toward the vehicle are not converted back from engineering units. The migrated database has no `TransformationID` on any L2R field, so the send path packs raw values. See `docs/CODEC_DB_ANSWERS.md`.
- **Decoder and bridge share one configured port.** Delphi sent to a literal `127.0.0.1:2357` while the bridge listened on `Servers.Port`. The port reads `ASTRA_BRIDGE_PORT` for both, default 2357.
- **Stage count is configuration.** `TAstraDecoder.Create` constructs `TAstraStageDecoder.Create(1)` and `Create(2)`. The rocket started with two stages, so `ASTRA_STAGE_COUNT` defaults to 2. Packet ids for the logged minor frames are `100 * (stage - 1) + 106`.
- **Two decoder counters do not do what the comments say.** `FDroppedMinorFrames` is never incremented. `FAvgFramesByRow` is `ReceivedMajorFrames / ReceivedMinorFrames`, which is the reciprocal of “minor frames per major frame”. Stats packets will carry those values. Match them or fix them on purpose.
- **A skipped subframe is dropped by doing nothing**, not by the path the comment describes. After a gap, later subframes of that major frame are ignored because `sf_id` must equal `last + 1`.
- **Job identity is `(TestID, PacketID)`.** `IntfID` is a generated UUID. The Pascal also filtered `Jobs` on `IntfID`; the exporter does not.
- **`u12`, nested records, and `ovr_` bits are easy to drop.** There is no flight capture to notice. The Win64 oracle harness and the unaligned property tests in §6 are what catch it.
- **Transformation 1 is a Win64 `float64` formula.** Production was x64, so Python’s IEEE-754 binary64 is the right width on both Linux architectures. The remaining risk is `System.Math.Power` versus `math.pow`, which the harness hex comparison measures. Do not generate those goldens from a Win32 build.
- **DAT timestamps are local OLE dates.** A Linux host in UTC will not match a Windows host in US Pacific unless the converter treats the stored value as naive local time.
- **`AstraGenerator`’s argument check is off by one.** The port should implement the four-argument usage the error string describes, not the `ParamCount <> 3` guard.
- **Secrets.** `sa`, `CHANGE_ME`, design-time host `opc.astraspace.com`, and `Servers.Password`. None of that should be copied into PostgreSQL seed data or the new repo.
- **Mojo’s Python import is SDK-specific.** The compiler pin is the multi-arch container in §5 (`modular/max-nvidia-base:26.6.0`, Mojo 1.1.0), not a pip install. If that pin’s Python import cannot be shipped on one architecture, that architecture uses the Python or C ABI packer (§3, §5). The codec’s behavior does not depend on Mojo. An ARM board older than Neoverse N1 is outside the SDK’s stated host CPU.
- **Mojo’s license allows free use; it is not an open-source license.** Confirm the community terms still cover shipping a ground-station service to the client before the packer is linked into a release build. The Python service runs without it until then.
- **Chapter 10 is a trap.** It looks like the telemetry stack and it is 16,200 lines. The running telemetry stack is `AstraDecoder.pas` plus a database row named `IRIG106`.

Open questions for David:

1. **Resolved.** Both `AstraConfig` and `AstraTestLog` were in the backups. Schema and programmability scripts are in `database/`. The `02_data.sql` scripts and the `.bak` files stay outside git.
2. Is the EntityDAC model in `DataModel.Mapping.xml` (boards / stacks / stars / proc blocks) what any vehicle was built from, or was the live tool always `AstraConfigurator` plus `TreeVersions`?
3. **Resolved.** LabVIEW will move from NI shared variables to OPC UA tags published by the bridge.
4. **Resolved.** The bridge port is configuration (`ASTRA_BRIDGE_PORT`, environment variable or `/etc/astra/astra.env`). The legacy literal 2357 is the default, and it is the stored `servers.port`. The OPC DA ProgID on that row is `National Instruments.Variable Engine.1`, kept as a legacy reference; the published endpoint is `ASTRA_OPCUA_ENDPOINT`. See `docs/CODEC_DB_ANSWERS.md`.
5. **Resolved.** The rocket started with two stages. Stage count is `ASTRA_STAGE_COUNT`, default 2, not the two constructors in `TAstraDecoder.Create`.
6. **Resolved for tagged fields.** No L2R field has a `TransformationID`, so `TransformInput` has nothing to invert on the send path. The codec packs L2R values raw. See `docs/CODEC_DB_ANSWERS.md`.
7. Is there a serial-over-UDP or UART gateway that lived outside this repo? Nothing here implements one. The ground link is the R2L/L2R datagram plus the TMoIP minor-frame port.
8. **Resolved.** There are no captured `.DAT` files, pcaps, or exported test tables. Regression uses the Win64 oracle harness, property tests, the simulated vehicle, and captures taken from now on (§6).
9. Should `FDroppedMinorFrames` and `FAvgFramesByRow` be corrected, or must old stats packets stay comparable?
10. **Resolved.** `Jobs.PacketID` is the real key, together with `TestID`. `IntfID` is a generated UUID.
11. **Resolved.** Production was built for x64 (Win64). Golden numeric values, including transformation 1, follow Win64 `float64` behavior.
12. Who owns the LabVIEW change that retargets the VIs to the bridge’s OPC UA tags, and does the client still need the NI shared-variable CSV during the cutover? The destination itself is settled (question 3).
13. Should the v3 hardware editor (`AstraConfigurationManager`) be dropped?
14. **Resolved.** The services run on Linux, probably Ubuntu, on x86_64 and possibly ARM64. LabVIEW is an OPC UA client of the bridge. Wheel, Mojo SDK, endianness, and CI consequences are in §5.
15. **Compiler pin resolved.** Local builds and CI use `modular/max-nvidia-base:26.6.0` (manifest list `sha256:53a1f0b502e67f400b0bc3c4575fde73f84d468ea03b977eaad2ef6fcd303c31`), which ships Mojo 1.1.0 for linux/amd64 and linux/arm64. Still open: does the community license cover deploying a Mojo packer inside the service at the client site? The Python service runs without Mojo until that is confirmed.
