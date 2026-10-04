# Astra ground station (Python / Mojo)

Private port of David Izada Rodriguez's Astra ground-station software. The
legacy Delphi application and the migration plan live in a separate
repository:

- Legacy code and database scripts: [Goliath-Research/astra-ground-station](https://github.com/Goliath-Research/astra-ground-station)
- Migration plan (source of truth): [MIGRATION.md](https://github.com/Goliath-Research/astra-ground-station/blob/main/MIGRATION.md)
- Copy in this repo: [docs/MIGRATION.md](docs/MIGRATION.md). The legacy copy wins if they disagree.

Python is the language for services, tools, and I/O. Mojo is reserved for
`pack_records` / `unpack_records` if a profile says the Python packer is hot.
PostgreSQL replaces SQL Server. OPC UA (asyncua), inside the bridge process,
replaces OPC DA and NI shared variables. LabVIEW subscribes to tags the
bridge publishes.

The bit packer is a pure-Python reference in `astra.codec`. It does not
import Mojo. `TransformOutput` and the OPC `1e-7` substitution follow
`docs/CODEC_SPEC.md` (transcribed from astra-ground-station PR #6). `pack`
does not apply either step. The default IRIG106 minor frame is the 349-byte
database layout in `docs/CODEC_DB_ANSWERS.md`. The TMoIP decoder reassembles
`packet_stream` and forwards `id || body` to the configured bridge port.
The exporter still raises `NotImplementedError`.
The web app is FastAPI and answers `GET /health` only.

## License

Licensed under the MIT License. Copyright 2026 Goliath Research. See
[LICENSE](LICENSE).

The GitHub repository stays private. MIT covers people who have a copy of
the code. It does not publish the repository.

## Layout

```
docs/MIGRATION.md          copy of the legacy plan; the legacy file wins
docs/CODEC_SPEC.md         codec rules transcribed from legacy PR #6
docs/CODEC_DB_ANSWERS.md   codec answers from the migrated config database
tests/data/codec_vectors.json  29 golden vectors from that same spec
tests/data/irig106_fixture.json  real IRIG106 layout and six byte vectors
database/schema/           01_schema.sql then 03_programmability.sql
deploy/systemd/            bridge, tmoip, exporter, web
fixtures/oracle/           Win64 harness output (empty until phase 0)
fixtures/live/             later captures from the Linux host
mojo/                      Mojo smoke packer; Python does not import it
src/astra/
  codec/                   pure-Python bit packer and TransformOutput
  binlog/                  LOG-T*-I*.DAT layout (phase 1)
  db/                      psycopg access to config and testlog
  settings.py              ASTRA_BRIDGE_PORT and ASTRA_STAGE_COUNT
  bridge/                  UDP, DAT, test poll, embedded OPC UA
  tmoip/                   minor-frame reassembly
  exporter/                Jobs to testlog tables
  opcua/                   asyncua server library used by the bridge
  web/                     configurator and test manager
  cli/                     generate, device, tm_encoder
```

The import package is `astra`, as in the migration plan. The distribution
name remains `astra-ground-station`.

## Processes

| How it is started | Replaces |
| --- | --- |
| `python -m astra.bridge` | `AstraBridgeServer` and the desktop twin |
| `python -m astra.tmoip` | `AstraTMoIP` and the desktop twin |
| `python -m astra.exporter` | `AstraLogExporter` and the desktop twin |
| `python -m astra.web` | Configurator and test manager, as a FastAPI app |
| `python -m astra.cli.generate` | `AstraGenerator` |
| `python -m astra.cli.device` | `AstraDevice` |
| `python -m astra.cli.tm_encoder` | `AstraTMEncoder`, headless |

Unit files are under `deploy/systemd/`. See `deploy/README.md`.

## Porting order

`docs/MIGRATION.md` §6. Phase 0 is the Win64 oracle harness (that program
stays in the legacy repo) and loading this schema when a later phase needs
the database. The schema is loaded now so CI can execute the functions. Phase
1 is the codec, transforms, and `.DAT` files. Do not start with the
configurator UI.

## Python and dependencies

CPython 3.12, Ubuntu 24.04's default `python3` on amd64 and arm64.
`requires-python` is `>=3.12`. CI pins 3.12.

| Piece | Choice |
| --- | --- |
| Build | hatchling, `src/` layout |
| HTTP | FastAPI and uvicorn. SQLAlchemy is not a dependency until the web app has CRUD |
| UDP | stdlib `asyncio` when the bridge is ported |
| PostgreSQL | psycopg 3 with the `binary` extra. Schema changes after this baseline are planned for Alembic; the verified scripts are applied with `psql` |
| OPC UA | asyncua 2.x, imported by `astra.opcua` |
| Tests | pytest, Hypothesis, pytest-asyncio |
| Oracle JSON | jsonschema and types-jsonschema, dev-only |
| Lint and types | Ruff, mypy strict |
| Mojo | container `modular/max-nvidia-base:26.6.0` (Mojo 1.1.0); not imported by the service |

Not installed, on purpose: PySide6 (optional desktop fallback), openpyxl
(only if an XLSX consumer is named), and the Chapter 10 C tree (not on the
live path). Nothing in this stack is a paid product.

## Development setup

Same steps on Ubuntu 24.04 x86_64 and ARM64.

```bash
sudo apt update
sudo apt install -y python3.12 python3.12-venv
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

PostgreSQL 16, with ICU (Ubuntu's package has it):

```bash
sudo apt install -y postgresql postgresql-client
sudo -u postgres createuser --pwprompt astra
sudo -u postgres createdb --owner=astra astra
export DATABASE_URL=postgresql://astra:CHANGE_ME@127.0.0.1:5432/astra
python -m astra.db.schema_loader
pytest
```

`02_data.sql` is not loaded. See `database/README.md`.

Mojo is optional and free to use. The compiler comes from Modular's
published container, which has both amd64 and arm64. See `mojo/README.md`.
The image entrypoint is `max serve`, so the command below replaces it.

```bash
docker run --rm --entrypoint bash \
  -v "$PWD":/work -w /work \
  modular/max-nvidia-base:26.6.0@sha256:53a1f0b502e67f400b0bc3c4575fde73f84d468ea03b977eaad2ef6fcd303c31 \
  -lc 'mojo --version && mkdir -p mojo/build && mojo build mojo/bitpack.mojo -o mojo/build/bitpack && ./mojo/build/bitpack && mojo run -I mojo mojo/test_bitpack.mojo'
```

## Tests

```bash
source .venv/bin/activate
ruff check src tests
ruff format --check src tests
mypy
pytest
```

`tests/test_postgres.py` skips when `DATABASE_URL` is unset. With it set, the
test loads `01_schema.sql` and `03_programmability.sql` if the functions are
not already there, then checks schemas, collations, and
`config.spcalcvartypesizes` / `testlog.spimportvalues`.

Oracle fixtures are described in `fixtures/README.md`.

## Continuous integration

`.github/workflows/ci.yml`:

- **python** on `ubuntu-24.04` and `ubuntu-24.04-arm`: PostgreSQL 16, schema
  load, Ruff, mypy, pytest
- **mojo** on both runners: `docker run` Modular's
  `modular/max-nvidia-base:26.6.0` image (manifest list
  `sha256:53a1f0b502e67f400b0bc3c4575fde73f84d468ea03b977eaad2ef6fcd303c31`,
  Mojo 1.1.0, linux/amd64 and linux/arm64). The job runs `mojo --version`,
  builds `mojo/bitpack.mojo`, and runs `mojo/test_bitpack.mojo`. A container
  or compile failure fails CI. CI does not install Mojo with pip

## Still open

`ASTRA_BRIDGE_PORT` defaults to the legacy literal 2357. `ASTRA_STAGE_COUNT`
defaults to 2. Both are set in `deploy/astra.env.example`. Exporter jobs are
keyed by `(test id, packet id)`; `intf_id` is a generated UUID.

Unresolved questions are in `docs/MIGRATION.md` §7 (EntityDAC hardware editor,
decoder counters, LabVIEW cutover owner, Mojo license for a client install).
Codec questions the database cannot answer are in `docs/CODEC_SPEC.md`.
