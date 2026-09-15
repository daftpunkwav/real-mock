"""DB-split tests for realmock.platform.services.db_split.

Covers: missing-source short-circuit, table copying with unknown-table
  warnings, existing-table skips, and legacy migration branches.
Conventions: tmp SQLite files only; PLATFORM_ROOT stubbed via monkeypatch.
"""

from __future__ import annotations

import sqlite3


class TestDbSplit:
    def _src(self, tmp_path, tables_sql, rows=None):
        src = tmp_path / "app.db"
        conn = sqlite3.connect(str(src))
        for sql in tables_sql:
            conn.execute(sql)
        for sql, params in rows or []:
            conn.execute(sql, params)
        conn.commit()
        conn.close()
        return src

    def test_missing_src_returns_false(self, tmp_path) -> None:
        from realmock.platform.services.db_split import split_app_db

        assert split_app_db(tmp_path / "nope.db", tmp_path / "a.db", tmp_path / "s.db") is False

    def test_copy_tables_and_unknown_warn(self, tmp_path, caplog) -> None:
        from realmock.platform.services.db_split import split_app_db

        src = self._src(
            tmp_path,
            ["CREATE TABLE user_profiles (id INTEGER PRIMARY KEY, name TEXT)", "CREATE TABLE interview_sessions (id INTEGER PRIMARY KEY)", "CREATE TABLE mystery (id INTEGER PRIMARY KEY)"],
            [("INSERT INTO user_profiles (id, name) VALUES (?, ?)", (1, "n")), ("INSERT INTO interview_sessions (id) VALUES (?)", (5,))],
        )
        api_p = tmp_path / "out" / "api.db"
        ses_p = tmp_path / "out" / "sessions.db"
        with caplog.at_level("WARNING"):
            assert split_app_db(src, api_p, ses_p) is True
        assert any("mystery" in r.message for r in caplog.records)
        assert sqlite3.connect(str(api_p)).execute("SELECT name FROM user_profiles").fetchone()[0] == "n"
        assert sqlite3.connect(str(ses_p)).execute("SELECT id FROM interview_sessions").fetchone()[0] == 5

    def test_copy_skips_existing_and_empty_sql(self, tmp_path) -> None:
        import realmock.platform.services.db_split as ds

        src = self._src(tmp_path, ["CREATE TABLE user_profiles (id INTEGER PRIMARY KEY)"])
        api_p = tmp_path / "api2.db"
        ses_p = tmp_path / "ses2.db"
        # pre-create destination table so _copy_table hits existing-branch
        dst = sqlite3.connect(str(api_p))
        dst.execute("CREATE TABLE user_profiles (id INTEGER PRIMARY KEY)")
        dst.commit()
        dst.close()
        assert ds.split_app_db(src, api_p, ses_p) is True
        # missing sql branch: table listed but no ddl
        s = sqlite3.connect(str(src))
        d = sqlite3.connect(str(api_p))
        ds._copy_table(s, d, "no_such_table_xyz")
        s.close()
        d.close()

    def test_maybe_migrate_branches(self, tmp_path, monkeypatch) -> None:
        import realmock.platform.services.db_split as ds

        # both exist -> early return (layout is PLATFORM_ROOT/data/*.db)
        d = tmp_path / "d1"
        (d / "data").mkdir(parents=True)
        (d / "data" / "api.db").write_bytes(b"x")
        (d / "data" / "sessions.db").write_bytes(b"x")
        (d / "data" / "app.db").write_bytes(b"x")
        monkeypatch.setattr(ds, "PLATFORM_ROOT", d)
        # app.db is not a valid sqlite file but both outputs exist so no-op
        ds.maybe_migrate_legacy_app_db()
        # no legacy file -> no-op
        d2 = tmp_path / "d2"
        (d2 / "data").mkdir(parents=True)
        monkeypatch.setattr(ds, "PLATFORM_ROOT", d2)
        ds.maybe_migrate_legacy_app_db()
        # happy path
        src = self._src(tmp_path, ["CREATE TABLE user_profiles (id INTEGER PRIMARY KEY)"])
        (d2 / "data" / "app.db").write_bytes(src.read_bytes())
        ds.maybe_migrate_legacy_app_db()
        assert (d2 / "data" / "api.db").is_file()
        # exception path swallowed
        monkeypatch.setattr(ds, "split_app_db", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
        (d2 / "data" / "api.db").unlink()
        (d2 / "data" / "sessions.db").unlink(missing_ok=True)
        ds.maybe_migrate_legacy_app_db()
