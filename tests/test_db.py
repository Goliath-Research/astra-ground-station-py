from pathlib import Path

import pytest

from astra_ground_station.db.connection import database_url_from_env
from astra_ground_station.db.errors import DatabaseConfigError, SchemaLoadError
from astra_ground_station.db.schema_loader import default_schema_dir, list_schema_files


def test_database_url_requires_postgres_and_hides_the_value() -> None:
    with pytest.raises(DatabaseConfigError, match="not set"):
        database_url_from_env({})
    with pytest.raises(DatabaseConfigError, match="postgresql://") as exc:
        database_url_from_env({"DATABASE_URL": "mysql://user:secret-token@localhost/db"})
    assert "secret-token" not in str(exc.value)


def test_database_url_accepts_postgres_schemes() -> None:
    assert database_url_from_env({"DATABASE_URL": "postgresql://localhost/astra"}) == (
        "postgresql://localhost/astra"
    )
    assert database_url_from_env({"DATABASE_URL": "postgres://localhost/astra"}) == (
        "postgres://localhost/astra"
    )


def test_list_schema_files_sorts_sql_and_refuses_data_dumps(tmp_path: Path) -> None:
    (tmp_path / "020_extra.sql").write_text("-- extra\n", encoding="utf-8")
    (tmp_path / "010_config.sql").write_text("-- config\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("ignore", encoding="utf-8")
    assert [path.name for path in list_schema_files(tmp_path)] == [
        "010_config.sql",
        "020_extra.sql",
    ]
    (tmp_path / "02_data.sql").write_text("-- dump\n", encoding="utf-8")
    with pytest.raises(SchemaLoadError, match="02_data.sql"):
        list_schema_files(tmp_path)


def test_default_schema_dir_follows_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ASTRA_SCHEMA_DIR", str(tmp_path))
    assert default_schema_dir() == tmp_path
