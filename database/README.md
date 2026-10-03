# Database

PostgreSQL replaces SQL Server. One database holds schema `config`
(AstraConfig) and schema `testlog` (AstraTestLog). Identifiers are lowercase
and unquoted. Stored procedures are PL/pgSQL functions called as
`SELECT * FROM config.spx(...)`.

These two files are the verified scripts from the legacy repository's
`database/postgres/` directory, copied here verbatim:

| File | Contents |
| --- | --- |
| `schema/01_schema.sql` | Schemas, ICU collations `config.mssql_order` and `testlog.mssql_order`, tables, keys. This includes the historical `testlog` wide-table definitions (`l2r_*`, `r2l_*`) with no rows |
| `schema/03_programmability.sql` | Views, functions, and the trigger |

The loader applies `database/schema/*.sql` in lexical order, so `01` runs
before `03`. `02_data.sql` is not in this repository. `.gitignore` ignores it,
and the loader refuses the filename. The programmability script's header says
to run it after `02_data.sql`. Its statements are `CREATE`s; they apply on an
empty database. Row data stays outside git because it contains
`Servers.Password`.

`01_schema.sql` creates ICU collations (`provider = icu`, locale
`und-u-ka-noignore`) so field order matches SQL Server for equal `Seq`
values. The server must be built with ICU. PostgreSQL 16 on Ubuntu 24.04 and
the `postgres:16` image both are. A glibc locale such as `en_US.UTF-8` would
reorder those fields and change packet layout.

Load:

```bash
export DATABASE_URL=postgresql://astra:CHANGE_ME@127.0.0.1:5432/astra
astra-load-schema
```

CI on `ubuntu-24.04` and `ubuntu-24.04-arm` starts PostgreSQL 16, runs that
loader, then `pytest`. `tests/test_postgres.py` requires `config` and
`testlog`, both `mssql_order` collations, `config.spcalcvartypesizes`, and
`testlog.spimportvalues`.

Alembic is the planned tool for changes after this baseline. These scripts
are the baseline, applied by `psql`, not generated as an Alembic revision.
