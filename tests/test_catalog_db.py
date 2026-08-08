import sqlite3

import pytest

from sc4pimx import catalog_db

SG_TGI = "0x6534284a, 0xcf94dbb8, 0x10f5333f"
PEG_TGI = "0x6534284a, 0xc977c536, 0x2a7ccda2"


def build_catalog(path, tgi_rows=(("0x6534284a, 0xcf94dbb8, 0x10f5333f", 1, "SG_Prop_PickupTruck_Small03"),)):
    """Minimal stand-in for the upstream Catalog.db schema."""
    conn = sqlite3.connect(str(path))
    conn.executescript("""
        CREATE TABLE Packages (Id INTEGER PRIMARY KEY, Name TEXT, Subfolder TEXT, Websites TEXT, Author TEXT);
        CREATE TABLE Files (Id INTEGER PRIMARY KEY, Name TEXT);
        CREATE TABLE PackageFiles (PackageId INTEGER, FileId INTEGER);
        CREATE TABLE TGIs (Id INTEGER PRIMARY KEY, FileId INTEGER, TGI TEXT, Category INTEGER, Name TEXT);
        CREATE TABLE TGICategories (Id INTEGER PRIMARY KEY, Name TEXT);
        INSERT INTO Packages VALUES (1, 'bsc:mega-props-sg-vol01', '100-props-textures', 'https://example.test/sg', 'SG');
        INSERT INTO Files VALUES (1, 'BSC MEGA Props - SG Vol01 v4.dat');
        INSERT INTO PackageFiles VALUES (1, 1);
        INSERT INTO TGICategories VALUES (1, 'Prop');
    """)
    conn.executemany("INSERT INTO TGIs (FileId, TGI, Category, Name) VALUES (1, ?, ?, ?)", tgi_rows)
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def catalog(tmp_path, monkeypatch):
    db_path = build_catalog(tmp_path / "Catalog.db")
    monkeypatch.setattr(catalog_db, "catalog_db_path", lambda: db_path)
    monkeypatch.setattr(catalog_db, "_MIN_PLAUSIBLE_BYTES", 0)
    return db_path


def test_search_tgi_returns_api_shaped_keys(catalog):
    with catalog_db.open_database() as db:
        matches = db.search_tgi((0x6534284A, 0xCF94DBB8, 0x10F5333F))

    assert len(matches) == 1
    assert set(matches[0]) == {
        "Package", "TGI", "Category", "ExemplarName",
        "FileName", "Subfolder", "Websites", "Author",
    }
    assert matches[0]["Package"] == "bsc:mega-props-sg-vol01"
    assert matches[0]["Category"] == "Prop"
    assert matches[0]["FileName"] == "BSC MEGA Props - SG Vol01 v4.dat"


def test_search_tgi_normalises_uppercase_input(catalog):
    # The catalog stores TGIs lowercase; SC4PIM formats them uppercase.
    assert catalog_db.format_tgi_text((0x6534284A, 0xCF94DBB8, 0x10F5333F)) == SG_TGI
    with catalog_db.open_database() as db:
        assert db.search_tgi((0x6534284A, 0xCF94DBB8, 0x10F5333F))
        assert db.search_tgi((0x6534284A, 0x00000000, 0x10F5333F)) == []


def test_search_iids_matches_last_eight_characters(tmp_path, monkeypatch):
    db_path = build_catalog(tmp_path / "Catalog.db", [
        (SG_TGI, 1, "SG_Prop_PickupTruck_Small03"),
        (PEG_TGI, 1, "Effect_SmallFountainB"),
    ])
    monkeypatch.setattr(catalog_db, "catalog_db_path", lambda: db_path)

    with catalog_db.open_database() as db:
        matches = db.search_iids([0x10F5333F, 0x2A7CCDA2, 0xDEADBEEF])

    assert {match["TGI"] for match in matches} == {SG_TGI, PEG_TGI}


def test_search_iids_with_no_matches_returns_empty(catalog):
    with catalog_db.open_database() as db:
        assert db.search_iids([0xDEADBEEF]) == []
        assert db.search_iids([]) == []


def test_open_database_returns_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(catalog_db, "catalog_db_path", lambda: tmp_path / "absent.db")
    assert catalog_db.open_database() is None


def test_open_database_returns_none_on_corrupt_file(tmp_path, monkeypatch):
    db_path = tmp_path / "Catalog.db"
    db_path.write_bytes(b"not a database")
    monkeypatch.setattr(catalog_db, "catalog_db_path", lambda: db_path)

    assert catalog_db.open_database() is None


def test_open_database_returns_none_on_missing_table(tmp_path, monkeypatch):
    db_path = build_catalog(tmp_path / "Catalog.db")
    conn = sqlite3.connect(str(db_path))
    conn.execute("DROP TABLE TGICategories")
    conn.commit()
    conn.close()
    monkeypatch.setattr(catalog_db, "catalog_db_path", lambda: db_path)

    assert catalog_db.open_database() is None


def test_wildcard_tgi_rows_are_accepted(tmp_path, monkeypatch):
    # The real catalog stores a "#" wildcard in the type field of ~1500 rows;
    # rejecting those as malformed would disable the database entirely.
    db_path = build_catalog(tmp_path / "Catalog.db", [
        ("#, 0x96a006b0, 0x000001ca", 1, "Family entry"),
        (SG_TGI, 1, "SG_Prop_PickupTruck_Small03"),
    ])
    monkeypatch.setattr(catalog_db, "catalog_db_path", lambda: db_path)

    with catalog_db.open_database() as db:
        assert db is not None
        assert db.search_iids([0x000001CA])[0]["ExemplarName"] == "Family entry"


def test_open_database_returns_none_on_unexpected_tgi_format(tmp_path, monkeypatch):
    # Upstream changing the TGI text format would otherwise look like every
    # row simply having no match.
    db_path = build_catalog(tmp_path / "Catalog.db", [("6534284A/CF94DBB8/10F5333F", 1, "x")])
    monkeypatch.setattr(catalog_db, "catalog_db_path", lambda: db_path)

    assert catalog_db.open_database() is None


def test_queries_still_work_when_indexing_fails(catalog):
    original = catalog_db.sqlite3.connect

    def failing_connect(*args, **kwargs):
        raise sqlite3.OperationalError("attempt to write a readonly database")

    catalog_db.sqlite3.connect = failing_connect
    try:
        catalog_db._build_indexes(catalog)
    finally:
        catalog_db.sqlite3.connect = original

    with catalog_db.open_database() as db:
        assert db.search_tgi((0x6534284A, 0xCF94DBB8, 0x10F5333F))


def test_build_indexes_speeds_up_lookups_without_changing_results(catalog):
    with catalog_db.open_database() as db:
        before = db.search_iids([0x10F5333F])
    catalog_db._build_indexes(catalog)
    with catalog_db.open_database() as db:
        after = db.search_iids([0x10F5333F])

    assert before == after


def test_promote_staged_moves_new_over_db(catalog):
    catalog_db.staging_path().write_bytes(b"fresh")

    assert catalog_db.promote_staged() is True
    assert catalog.read_bytes() == b"fresh"
    assert not catalog_db.staging_path().exists()
    assert catalog_db.promote_staged() is False


def test_refresh_reason(catalog, monkeypatch):
    settings = {"UseLocalDatabase": True, "RefreshIntervalDays": 14}
    monkeypatch.setattr(catalog_db, "database_age_days", lambda: 1.0)
    assert catalog_db.refresh_reason(settings) == ""

    monkeypatch.setattr(catalog_db, "database_age_days", lambda: 20.0)
    assert catalog_db.refresh_reason(settings) == "stale"

    assert catalog_db.refresh_reason({"UseLocalDatabase": False}) == ""
    assert catalog_db.refresh_reason(
        {"UseLocalDatabase": True, "RefreshIntervalDays": 0}) == ""


def test_refresh_reason_missing_and_cooldown(tmp_path, monkeypatch):
    monkeypatch.setattr(catalog_db, "catalog_db_path", lambda: tmp_path / "absent.db")
    settings = {"UseLocalDatabase": True}

    assert catalog_db.refresh_reason(settings) == "missing"

    # A staged download counts as present: it is promoted on the next open.
    catalog_db.staging_path().write_bytes(b"x")
    assert catalog_db.refresh_reason(settings) == ""
    catalog_db.staging_path().unlink()

    catalog_db.note_download_failure()
    try:
        assert catalog_db.refresh_reason(settings) == ""
    finally:
        catalog_db.clear_download_failure()
    assert catalog_db.refresh_reason(settings) == "missing"
