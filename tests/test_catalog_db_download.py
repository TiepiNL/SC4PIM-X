import threading
from urllib.error import HTTPError, URLError

import pytest

from sc4pimx import catalog_db

from test_catalog_db import build_catalog


class FakeResponse:
    def __init__(self, data, headers=None):
        self.data = data
        self.headers = headers if headers is not None else {"Content-Length": str(len(data))}
        self._pos = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, size=-1):
        if size is None or size < 0:
            size = len(self.data) - self._pos
        chunk = self.data[self._pos:self._pos + size]
        self._pos += len(chunk)
        return chunk


@pytest.fixture
def payload(tmp_path):
    """Bytes of a real (miniature) catalog database."""
    return build_catalog(tmp_path / "source.db").read_bytes()


@pytest.fixture
def target(tmp_path, monkeypatch):
    db_path = tmp_path / "Catalog.db"
    monkeypatch.setattr(catalog_db, "catalog_db_path", lambda: db_path)
    monkeypatch.setattr(catalog_db, "_MIN_PLAUSIBLE_BYTES", 0)
    monkeypatch.setattr(catalog_db, "ensure_user_data_dir", lambda: tmp_path)
    catalog_db.clear_download_failure()
    yield db_path
    catalog_db.clear_download_failure()


def test_download_writes_database_and_reports_progress(target, payload, monkeypatch):
    monkeypatch.setattr(catalog_db, "_CHUNK_BYTES", 512)
    monkeypatch.setattr(catalog_db, "urlopen", lambda request, timeout: FakeResponse(payload))
    seen = []

    status = catalog_db.download_database(
        "https://example.test/Catalog.db",
        progress=lambda phase, done, total: seen.append((phase, done, total)),
    )

    assert status == "ok"
    # Not byte-equal to the payload: indexes are added before promotion.
    assert target.stat().st_size >= len(payload)
    assert not catalog_db.part_path().exists()

    downloads = [entry for entry in seen if entry[0] == "download"]
    assert [entry[1] for entry in downloads] == sorted(entry[1] for entry in downloads)
    assert downloads[-1][1] == len(payload)
    assert all(entry[2] == len(payload) for entry in downloads)
    assert ("index", 0, 0) in seen


def test_downloaded_database_is_queryable(target, payload, monkeypatch):
    monkeypatch.setattr(catalog_db, "urlopen", lambda request, timeout: FakeResponse(payload))

    assert catalog_db.download_database("https://example.test/Catalog.db") == "ok"

    with catalog_db.open_database() as db:
        assert db.search_iids([0x10F5333F])


def test_cancel_leaves_existing_database_untouched(target, payload, monkeypatch):
    target.write_bytes(b"existing database")
    monkeypatch.setattr(catalog_db, "_CHUNK_BYTES", 64)
    monkeypatch.setattr(catalog_db, "urlopen", lambda request, timeout: FakeResponse(payload))
    cancel = threading.Event()

    status = catalog_db.download_database(
        "https://example.test/Catalog.db",
        progress=lambda phase, done, total: cancel.set(),
        cancel=cancel,
    )

    assert status == "cancelled"
    assert target.read_bytes() == b"existing database"
    assert not catalog_db.part_path().exists()


def test_network_error_preserves_existing_database(target, monkeypatch):
    target.write_bytes(b"existing database")

    def failing_urlopen(request, timeout):
        raise URLError("no route to host")

    monkeypatch.setattr(catalog_db, "urlopen", failing_urlopen)

    assert catalog_db.download_database("https://example.test/Catalog.db") == "error"
    assert target.read_bytes() == b"existing database"
    # An offline user should not be asked again on the next lookup run.
    assert catalog_db.refresh_reason({"UseLocalDatabase": True}) == ""


def test_not_modified_bumps_mtime_without_downloading(target, monkeypatch):
    build_catalog(target)
    import os
    os.utime(target, (0, 0))
    original = target.stat().st_mtime

    def not_modified(request, timeout):
        assert request.get_header("If-modified-since")
        raise HTTPError("https://example.test/Catalog.db", 304, "Not Modified", {}, None)

    monkeypatch.setattr(catalog_db, "urlopen", not_modified)

    assert catalog_db.download_database("https://example.test/Catalog.db") == "unchanged"
    assert target.stat().st_mtime > original


def test_implausible_size_is_rejected(target, monkeypatch):
    monkeypatch.setattr(catalog_db, "_MIN_PLAUSIBLE_BYTES", 1024)
    monkeypatch.setattr(
        catalog_db, "urlopen",
        lambda request, timeout: FakeResponse(b"<html>404</html>"),
    )

    assert catalog_db.download_database("https://example.test/Catalog.db") == "error"
    assert not target.exists()


def test_non_catalog_payload_is_rejected(target, monkeypatch):
    monkeypatch.setattr(
        catalog_db, "urlopen",
        lambda request, timeout: FakeResponse(b"not a database at all"),
    )

    assert catalog_db.download_database("https://example.test/Catalog.db") == "error"
    assert not target.exists()
    assert not catalog_db.staging_path().exists()


def test_concurrent_download_reports_busy(target, payload, monkeypatch):
    monkeypatch.setattr(catalog_db, "urlopen", lambda request, timeout: FakeResponse(payload))
    catalog_db._download_lock.acquire()
    try:
        assert catalog_db.download_database("https://example.test/Catalog.db") == "busy"
    finally:
        catalog_db._download_lock.release()
