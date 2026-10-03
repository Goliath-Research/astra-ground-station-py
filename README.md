# Astra ground station (Python / Mojo)

Private port of David Izada Rodriguez's Astra ground-station software. The
legacy application is Delphi, ran in production on Win64, and lives in a
separate repository:

- Legacy code, migration plan, and database scripts: [Goliath-Research/astra-ground-station](https://github.com/Goliath-Research/astra-ground-station)
- Migration plan: [MIGRATION.md](https://github.com/Goliath-Research/astra-ground-station/blob/main/MIGRATION.md)

This repository is the Linux port. It does not contain the Delphi sources.
If this layout and `MIGRATION.md` disagree, `MIGRATION.md` is the source of
truth.

Python is the main language. Mojo is accepted for performance-critical parts
(free to use is enough). Plain Python, or the existing C code via cffi, are
the fallbacks. The Python package runs without Mojo installed.

Targets are Ubuntu on x86_64 and ARM64. OPC UA ([asyncua](https://github.com/FreeOpcUa/opcua-asyncio))
replaces OPC DA and NI shared variables; LabVIEW will subscribe to tags the
bridge publishes. PostgreSQL replaces MSSQL, with schemas `config` and
`testlog`, lowercase unquoted identifiers, and procedures translated as
PL/pgSQL functions.

No business logic is ported yet. The service processes idle until a signal.
The codec, telemetry decoder, and telemetry encoder raise or stay unused on
purpose.

## License

No license has been chosen. This repository is private. All rights reserved.
Do not copy, redistribute, or treat it as open source. There is no `LICENSE`
file until one is chosen.

## Layout

```
deploy/                         systemd units, sysusers snippet, env example
database/schema/                future PL/pgSQL scripts (no data dumps)
mojo/                           optional Mojo placeholder and build notes
src/astra_ground_station/
  bridge/                       OPC UA service (astra-bridge)
  codec/                        frame codec library (not ported)
  db/                           PostgreSQL access and schema loader
  exporter/                     export library (not ported)
  native.py                     backend selection; Python only today
  telemetry/                    decoder, encoder, and astra-telemetry
  web/                          web UI placeholder (astra-web)
tests/golden/                   fixtures the Win64 harness will emit
tests/                          one smoke test per package, plus fixture and db tests
```

Three systemd services: the bridge, telemetry, and the web app. The codec,
exporter, and database layer are libraries. Unit files are templates under
`deploy/systemd/`; see `deploy/README.md`.

## Python version

CPython 3.12. It is the default `python3` on Ubuntu 24.04 for both amd64 and
arm64, so a ground-station host does not need a PPA or a custom build.
`requires-python` is `>=3.12`. CI pins 3.12, the same interpreter as the
production OS image. Wheels for `psycopg-binary`, Ruff, and mypy exist for
CPython 3.12 on x86_64 and aarch64. asyncua 2.x is pure Python. Mojo's Python
interoperability range includes 3.12.

## Dependencies

| Piece | Choice |
| --- | --- |
| Build | hatchling, `src/` layout |
| OPC UA | `asyncua` 2.x |
| PostgreSQL | `psycopg` 3 with the `binary` extra, so CI and hosts do not compile `libpq` bindings |
| Tests | pytest, Hypothesis, pytest-asyncio (ready for later asyncua tests) |
| Fixtures | jsonschema plus `types-jsonschema`, dev-only, checks `tests/golden/case.schema.json` |
| Lint | Ruff |
| Types | mypy in strict mode |

Nothing in this stack is commercial or paid.

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

PostgreSQL, when you want the schema job locally:

```bash
sudo apt install -y postgresql postgresql-client
sudo -u postgres createuser --pwprompt astra
sudo -u postgres createdb --owner=astra astra
export DATABASE_URL=postgresql://astra:CHANGE_ME@127.0.0.1:5432/astra
python -m astra_ground_station.db.schema_loader
pytest tests/test_postgres.py
```

`database/schema/` is empty until the ported scripts are copied from the
legacy repo. Do not commit `02_data.sql` or other dumps. See
`database/README.md`.

Mojo is optional. See `mojo/README.md`.

```bash
python -m pip install 'mojo>=1.1,<1.2'
mkdir -p mojo/build
mojo build mojo/placeholder.mojo -o mojo/build/placeholder
./mojo/build/placeholder
```

## Tests

```bash
source .venv/bin/activate
ruff check src tests
ruff format --check src tests
mypy
pytest
```

`pytest` skips `tests/test_postgres.py` when `DATABASE_URL` is unset. Golden
fixtures are described in `tests/golden/README.md`. The Win64 harness that
produces them belongs in the legacy repository; this repo only consumes the
files. There is no `.DAT` archive. Further confidence comes from round-trip
and property tests, and later from simulated devices.

## Continuous integration

`.github/workflows/ci.yml` runs on pull requests and on pushes to `main`:

- **python** on `ubuntu-24.04` and `ubuntu-24.04-arm`: Ruff, mypy, pytest
- **postgres** on `ubuntu-24.04`: PostgreSQL 16 service container, schema
  loader, `tests/test_postgres.py`
- **mojo** on both runners: install the stable Mojo SDK and build
  `mojo/placeholder.mojo`. If the SDK cannot be installed or will not start
  on that architecture, the build step is skipped and the job does not fail.
  A compile or run failure after a successful install fails the job.

## Open decisions

- Confirm the three services (bridge, telemetry, web) against `MIGRATION.md`.
  The exporter is a library in this scaffold, not its own unit.
- Web framework is undecided. None is installed.
- The OPC UA tag dictionary LabVIEW will subscribe to is not defined.
- PostgreSQL 16 matches Ubuntu 24.04. Say if production should track a
  different major version.
- License: still unlicensed and private.
- Which hot paths move to Mojo, and which stay on Python or cffi, is later
  work. `ASTRA_NATIVE_BACKEND=mojo` is rejected until a binding exists.
