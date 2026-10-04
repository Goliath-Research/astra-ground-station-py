# Astra hardware fixture (real board / pin data)

`real_boards.json` is a credential-free extract of the real Astra ground-station hardware
tables from the migrated AstraConfig database (PostgreSQL schema `config`, built from the SQL Server
2016 backup `AstraConfig.bak`, 2017-07-05). Source: `db-migration/postgres/02_data.sql`.
Only the tables listed below were extracted (scratch PostgreSQL load of those INSERT blocks only).
**No `Servers` rows, user names, passwords or connection strings are included**, and none of the
extracted tables has a credential-like column.

The JSON has one key per table (a list of row objects keyed by the PostgreSQL column names,
ordered by `id`) and a `_meta` key with source info, `row_counts` and the ordered `columns` of each table.
`double precision` columns (`connectors."conn part no"`, `links.c1_first_pin`, `links.c2_first_pin`) come out as JSON numbers.

## Tables and row counts

### Access-era pinout model (harness designer)
| table | rows | what it is |
|---|---|---|
| `stage` | 3 | Harness / tester stage: `S1Tester1` (id 1), `S2Tester1` (id 2), `S1EngineTester1` (id 4) |
| `area_list` | 4 | Vehicle areas: `P` Payload/Interstage, `I` Intertank, `C` Engine common area, `E` Engine module |
| `areas` | 10 | Area instances per stage (`area_multiple` = how many copies, e.g. 5 engine modules on S1Tester1; `ordering`) |
| `board` | 8 | Board connector on the smart node: `M`, `A1`, `A2`, `V1`, `V2`, `S1`, `S2`, `P` (`"order"` = display order) |
| `links` | 340 | One wire/link: board connector + pin (`c1_first_pin`, `c1_type_id`) to harness-side connector + pin (`c2_first_pin`, `c2_type_id`), link type, area, name |
| `names` | 357 | Link names: `link_description`, `short_name` (often with `(j)` placeholder), `internal_name`; 148 are referenced by `links` (the rest are also referenced by the signal `interfaces` table, not included) |
| `link_type` | 4 | `C` Comm, `I` Input, `O` Output, `P` Power |
| `connectors` | 28 | Molex connector housings: part number, circuits, rows, gender, description |
| `connector_gender` | 2 | `Plug`, `Receptacle` |
| `vendors` | 1 | `Molex` |

### Configurator hardware tree (Astra Configurator)
| table | rows | what it is |
|---|---|---|
| `treeversions` | 88 | Configuration tree: Vehicle > Stage 1 / Stage 2 / Orion A / Orion B > Version > Release > node (eMaster, Engine, PumpSimpleTester, TMencoder, TMdecoder) > L2R / R2L / Hardware > area (P/I/C/E, `iconid` 9) > board (M/A1/A2/V1/V2/S1/S2, `iconid` 10). `seq` = display order |
| `connections` | 324 | Pin assignments on a configurator board node: `boardid` (treeversions board node), `firstpin`, `linktypeid`, `connectorid`, `description`, `shortname` |
| `linktypes` | 4 | `C` Comm, `I` Input, `O` Output, `P` Power (configurator copy of `link_type`) |

## Joins
Access pinout model (all FKs verified, no orphans):
- `areas.stage_id -> stage.id`
- `areas.area_id -> area_list.id`
- `links.area_id -> areas.id` (so a link's stage = `links -> areas -> stage`)
- `links.board_id -> board.id`
- `links.names_id -> names.id`
- `links.link_type_id -> link_type.id`
- `links.c1_type_id -> connectors.id` (board-side connector: 7 = 40-circuit Pico-Clasp on M/A1/A2/V1/V2, 1 or 2 on the P power board, NULL on S1/S2), `links.c2_type_id -> connectors.id` (harness-side connector; may be NULL)
- `connectors.gender_id -> connector_gender.id`, `connectors.vendor_id -> vendors.id`

Configurator model:
- `treeversions.parentid -> treeversions.id` (tree)
- `connections.boardid -> treeversions.id` (a board node, `iconid` = 10; its parent is the area node, `iconid` = 9, under a `Hardware` node)
- `connections.linktypeid -> linktypes.id`
- `connections.connectorid -> connectors.id` (no FK in the schema, but every non-null value resolves; NULL for the S1/S2 boards, whose pins are 80-85)

Example: links per stage/area/board:
```sql
SELECT s.stage, al.area_name, b.board_connector, l.c1_first_pin, n.short_name, lt.link_type
FROM links l
JOIN areas a ON a.id = l.area_id
JOIN stage s ON s.id = a.stage_id
JOIN area_list al ON al.id = a.area_id
JOIN board b ON b.id = l.board_id
JOIN names n ON n.id = l.names_id
JOIN link_type lt ON lt.id = l.link_type_id
ORDER BY s.stage_order, a.ordering, b."order", l.c1_first_pin;
```

## Shape of the data (for test assertions)
- Links per stage: S1Tester1 153 (areas P, I, C [two area rows, ids 1 and 11], E), S2Tester1 132 (P, I, C, E), S1EngineTester1 55 (E only); total 340.
- Configurator hardware boards with connections: Stage 1 eMaster (tree ids 6333-6350), Stage 2 eMaster (6577-6594), Orion B Engine (6555-6560). 36 board nodes have pins.
- The `areas` row id 11 (area C, stage S1Tester1) duplicates id 1 and holds 2 links; keep it in mind when asserting unique (stage, area) pairs.

## Not included (on purpose)
- `servers` (contains credentials), `tests`, `devices` (IP addresses), `parts`/`partlists`/`locations` (inventory), `msglog`, `jobs`.
- Signal/packet layer: `interfaces`, `interfacerowtolink`, `grouping`, `interface_list`, `signal_data_types`, `irig_interfaces`, `frequencies`, `fields`, `vartypes`, `packets`, `mappings`, `transformations`. Extract those separately if the codec/OPC UA tests need real packet layouts.
- `mm` (0 rows).
