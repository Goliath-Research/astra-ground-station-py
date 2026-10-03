# Database

PostgreSQL replaces MSSQL. Ubuntu 24.04 ships PostgreSQL 16, and CI uses the
`postgres:16` image. Confirm that major version before production install if
a newer server is preferred.

Two schemas:

- `config` — ground-station configuration
- `testlog` — test and telemetry logs

Conventions, matching the migration off MSSQL:

- Unquoted lowercase identifiers. PostgreSQL folds unquoted names to
  lowercase; quoted mixed-case names from SQL Server must not be carried
  over.
- Stored procedures become PL/pgSQL functions.
- Scripts live in `database/schema/` and are applied in lexical order. Name
  them `001_config.sql`, `002_testlog.sql`, and so on.
- `CREATE SCHEMA IF NOT EXISTS` so the loader can be re-run.

The scripts themselves are not in this repository yet. They are being ported
in the legacy repo
([Goliath-Research/astra-ground-station](https://github.com/Goliath-Research/astra-ground-station),
`database/`, pull request 3). Copy the schema scripts here when they are
ready. Do not copy data.

`02_data.sql` and other dumps (`*.dump`, `*.bak`, `*.bacpac`) are gitignored.
The loader refuses a file named `02_data.sql` if one is present on disk.

## Apply

`psql` (package `postgresql-client`) is required only when `database/schema/`
contains `*.sql` files. With an empty directory the loader only checks that
the server accepts connections.

```bash
export DATABASE_URL=postgresql://astra:CHANGE_ME@127.0.0.1:5432/astra
astra-load-schema
# equivalent: python -m astra_ground_station.db.schema_loader
```

`ASTRA_SCHEMA_DIR` overrides the default `./database/schema`.

CI starts a fresh PostgreSQL 16 container, runs the loader, and then runs
`tests/test_postgres.py`. With an empty `database/schema/` that test only
checks connectivity. Once any `*.sql` file is applied, the test requires
both `config` and `testlog` to exist.
