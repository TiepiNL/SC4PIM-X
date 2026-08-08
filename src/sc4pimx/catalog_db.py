"""Local SQLite copy of the SC4 Prop & Texture Catalog.

The catalog project (github.com/noah-severyn/SC4PropTextureCatalog, MIT) ships
its dataset as one ~23 MB SQLite file, so lookups can run here instead of one
HTTP round-trip per resource. :mod:`DependencyCatalog` keeps the API as a
fallback.

``TGIs.TGI`` is lowercase text, ``"0x6534284a, 0xcf94dbb8, 0x10f5333f"`` --
everything else in SC4PIM formats TGIs uppercase, so parameters are lowercased
before binding.

Downloads land as ``.part``, are validated and indexed there, renamed to
``.new``, then promoted over ``Catalog.db``. Windows cannot rename onto an open
SQLite file, so promotion retries from :func:`open_database`. Indexing happens
before promotion because ``os.replace`` carries the source mtime and staleness
is derived from it.
"""

import logging
import os
import re
import sqlite3
import threading
import time
from email.utils import formatdate
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .paths import catalog_db_path, ensure_user_data_dir

logger = logging.getLogger(__name__)

DEFAULT_DATABASE_URL = (
    "https://raw.githubusercontent.com/noah-severyn/SC4PropTextureCatalog"
    "/main/SC4PropTextureCatalogAPI/data/Catalog.db"
)
DEFAULT_REFRESH_INTERVAL_DAYS = 14
DEFAULT_DOWNLOAD_TIMEOUT_SECONDS = 60.0

_CHUNK_BYTES = 256 * 1024
# Rejects a redirect or error page being installed as the database.
_MIN_PLAUSIBLE_BYTES = 1 * 1024 * 1024
_MAX_PLAUSIBLE_BYTES = 200 * 1024 * 1024
# Stay under SQLITE_MAX_VARIABLE_NUMBER, which was 999 before SQLite 3.32.
_SQL_PARAM_CHUNK = 500
# Without this an offline user gets a download attempt on every lookup run.
FAILURE_COOLDOWN_SECONDS = 3600.0

REQUIRED_TABLES = ("Packages", "PackageFiles", "Files", "TGIs", "TGICategories")
# Any of the three fields may be "#", the catalog's wildcard -- in practice the
# type of a family or patch entry.
_TGI_TEXT_RE = re.compile(r"^(0x[0-9a-f]{8}|#), (0x[0-9a-f]{8}|#), (0x[0-9a-f]{8}|#)$")
_PROBE_SAMPLE = 25

_SELECT = """
SELECT Packages.Name      AS Package,
       TGIs.TGI           AS TGI,
       TGICategories.Name AS Category,
       TGIs.Name          AS ExemplarName,
       Files.Name         AS FileName,
       Packages.Subfolder AS Subfolder,
       Packages.Websites  AS Websites,
       Packages.Author    AS Author
FROM TGIs
JOIN Files        ON Files.Id = TGIs.FileId
JOIN PackageFiles ON PackageFiles.FileId = Files.Id
JOIN Packages     ON Packages.Id = PackageFiles.PackageId
LEFT JOIN TGICategories ON TGICategories.Id = TGIs.Category
"""

_download_lock = threading.Lock()
_failed_until = 0.0


# --- paths and staleness (pure stat calls, safe on the GUI thread) ---

def database_path() -> Path:
    return catalog_db_path()


def staging_path() -> Path:
    return database_path().with_suffix(".db.new")


def part_path() -> Path:
    return database_path().with_suffix(".db.part")


def database_exists() -> bool:
    return database_path().is_file()


def _mtime(path: Path):
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def database_age_days():
    mtime = _mtime(database_path())
    if mtime is None:
        return None
    return max(0.0, (time.time() - mtime) / 86400.0)


def promote_staged() -> bool:
    """Move a completed download over the live database, if one is waiting."""
    staged = staging_path()
    if not staged.is_file():
        return False
    try:
        os.replace(staged, database_path())
    except OSError as exc:
        # Held open by a running lookup; the next call retries.
        logger.debug("Catalog database still in use, promotion deferred: %s", exc)
        return False
    logger.info("Catalog database updated from %s", staged.name)
    return True


def note_download_failure() -> None:
    global _failed_until
    _failed_until = time.monotonic() + FAILURE_COOLDOWN_SECONDS


def clear_download_failure() -> None:
    global _failed_until
    _failed_until = 0.0


def refresh_reason(settings) -> str:
    """Why the database should be downloaded: '', 'missing' or 'stale'."""
    if not settings.get("UseLocalDatabase", False):
        return ""
    if time.monotonic() < _failed_until:
        return ""
    if not database_exists():
        # A staged download is promoted on the next open, so it counts.
        return "" if staging_path().is_file() else "missing"
    try:
        interval = float(settings.get("RefreshIntervalDays", DEFAULT_REFRESH_INTERVAL_DAYS))
    except (TypeError, ValueError):
        interval = DEFAULT_REFRESH_INTERVAL_DAYS
    if interval <= 0:
        return ""
    age = database_age_days()
    return "stale" if age is not None and age > interval else ""


# --- query ---

def format_tgi_text(tgi) -> str:
    return "0x%08x, 0x%08x, 0x%08x" % tuple(int(part) & 0xFFFFFFFF for part in tgi)


def format_iid_key(iid) -> str:
    """Instance ID as ``substr(TGIs.TGI, -8)`` yields it."""
    return "%08x" % (int(iid) & 0xFFFFFFFF)


class LocalCatalogDatabase:
    """Read-only handle on the downloaded catalog.

    Queries return None instead of raising, which callers read as "fall back to
    the online API". The handle marks itself dead after the first failure so a
    broken file costs one failed query, not one per row.
    """

    def __init__(self, db_path):
        self.db_path = str(db_path)
        self._conn = None
        self._lock = threading.Lock()
        self._dead = False

    def open(self):
        try:
            # mode=ro avoids -wal/-shm sidecars and mtime changes, which
            # staleness depends on.
            self._conn = sqlite3.connect(
                "file:%s?mode=ro" % self.db_path.replace("?", "%3f").replace("#", "%23"),
                uri=True,
                check_same_thread=False,
                timeout=5.0,
            )
        except sqlite3.DatabaseError as exc:
            logger.warning("Could not open catalog database %s: %s", self.db_path, exc)
            return None
        self._conn.row_factory = sqlite3.Row
        for pragma in ("query_only=1", "cache_size=-32000", "mmap_size=268435456"):
            try:
                self._conn.execute("PRAGMA %s" % pragma)
            except sqlite3.DatabaseError:
                logger.debug("Could not set PRAGMA %s on the catalog database", pragma)
        if not self._probe():
            self.close()
            return None
        return self

    def _probe(self) -> bool:
        try:
            names = {
                row[0] for row in self._conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            missing = [table for table in REQUIRED_TABLES if table not in names]
            if missing:
                logger.warning("Catalog database is missing table(s): %s", ", ".join(missing))
                return False
            self._conn.execute(_SELECT + " WHERE TGIs.TGI = ? LIMIT 1", ("",)).fetchall()
            sample = [
                str(row[0] or "") for row in
                self._conn.execute("SELECT TGI FROM TGIs LIMIT ?", (_PROBE_SAMPLE,))
            ]
        except sqlite3.DatabaseError as exc:
            logger.warning("Catalog database failed validation: %s", exc)
            return False
        if not sample:
            logger.warning("Catalog database contains no TGIs")
            return False
        if not any(_TGI_TEXT_RE.match(text) for text in sample):
            # A format change upstream would otherwise look like "no matches".
            logger.warning("Catalog database TGI format not recognised: %r", sample[0])
            return False
        return True

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except sqlite3.DatabaseError:
                pass
            self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

    def _query(self, sql, params):
        if self._dead or self._conn is None:
            return None
        try:
            with self._lock:
                return [dict(row) for row in self._conn.execute(sql, params)]
        except sqlite3.DatabaseError as exc:
            logger.warning("Catalog database query failed, using the online catalog: %s", exc)
            self._dead = True
            return None

    def search_tgi(self, tgi):
        return self._query(_SELECT + " WHERE TGIs.TGI = ? LIMIT 2000", (format_tgi_text(tgi),))

    def search_iids(self, iids):
        keys = [format_iid_key(iid) for iid in iids]
        if not keys:
            return []
        matches = []
        for start in range(0, len(keys), _SQL_PARAM_CHUNK):
            chunk = keys[start:start + _SQL_PARAM_CHUNK]
            sql = "%s WHERE substr(TGIs.TGI, -8) IN (%s)" % (
                _SELECT, ", ".join("?" * len(chunk)),
            )
            rows = self._query(sql, chunk)
            if rows is None:
                return None
            matches.extend(rows)
        return matches


def open_database(path=None):
    """Open the local catalog, promoting a staged download first.

    None means "no usable local catalog", not an error.
    """
    if path is None:
        promote_staged()
        path = database_path()
    if not Path(path).is_file():
        return None
    return LocalCatalogDatabase(path).open()


# --- download ---

class DownloadCancelled(Exception):
    pass


def _build_indexes(path, progress=None) -> None:
    """Index the download so lookups do not scan every TGI.

    Best-effort: without these the queries return the same rows, just slower.
    ANALYZE matters too -- without statistics the planner ignores the
    expression index.
    """
    if progress is not None:
        progress("index", 0, 0)
    conn = None
    try:
        conn = sqlite3.connect(str(path))
        existing = {str(row[1]) for row in conn.execute("PRAGMA index_list(TGIs)")}
        statements = [
            "CREATE INDEX IF NOT EXISTS idx_sc4pimx_tgi_iid ON TGIs(substr(TGI, -8))",
            "CREATE INDEX IF NOT EXISTS idx_sc4pimx_pkgfiles_file ON PackageFiles(FileId)",
        ]
        if not any("tgi" in name.lower() for name in existing):
            statements.append("CREATE INDEX IF NOT EXISTS idx_sc4pimx_tgi_full ON TGIs(TGI)")
        for statement in statements:
            conn.execute(statement)
        conn.execute("ANALYZE")
        conn.commit()
    except sqlite3.DatabaseError as exc:
        logger.warning("Could not index the catalog database (lookups will be slower): %s", exc)
    finally:
        if conn is not None:
            try:
                conn.close()
            except sqlite3.DatabaseError:
                pass


def _validate_download(path) -> bool:
    try:
        size = path.stat().st_size
    except OSError:
        return False
    if size < _MIN_PLAUSIBLE_BYTES:
        logger.warning("Downloaded catalog database is implausibly small (%d bytes)", size)
        return False
    db = LocalCatalogDatabase(path).open()
    if db is None:
        return False
    db.close()
    return True


def download_database(url=None, timeout=DEFAULT_DOWNLOAD_TIMEOUT_SECONDS,
                      progress=None, cancel=None) -> str:
    """Fetch the catalog database into the per-user data directory.

    Returns "ok", "unchanged", "cancelled", "error" or "busy"; never raises.
    *progress* is called as ``progress(phase, done, total)`` with phase
    "download" or "index". *cancel* is an Event polled between chunks. An
    existing database is left untouched unless a new one validates.
    """
    if url is None:
        url = DEFAULT_DATABASE_URL
    if not _download_lock.acquire(blocking=False):
        return "busy"
    target, part, staged = database_path(), part_path(), staging_path()
    try:
        ensure_user_data_dir()
        request = Request(url, headers={"User-Agent": "SC4PIM-X"})
        current_mtime = _mtime(target)
        if current_mtime is not None:
            request.add_header("If-Modified-Since", formatdate(current_mtime, usegmt=True))
        try:
            with urlopen(request, timeout=timeout) as response:
                try:
                    total = int(response.headers.get("Content-Length") or 0)
                except (TypeError, ValueError):
                    total = 0
                if total and not (_MIN_PLAUSIBLE_BYTES <= total <= _MAX_PLAUSIBLE_BYTES):
                    logger.warning("Refusing catalog download of implausible size %d", total)
                    return "error"
                done = 0
                with open(part, "wb") as handle:
                    while True:
                        if cancel is not None and cancel.is_set():
                            raise DownloadCancelled
                        chunk = response.read(_CHUNK_BYTES)
                        if not chunk:
                            break
                        handle.write(chunk)
                        done += len(chunk)
                        if progress is not None:
                            progress("download", done, total)
        except HTTPError as exc:
            if exc.code == 304:
                # Unchanged upstream; restart the staleness clock.
                try:
                    os.utime(target, None)
                except OSError:
                    pass
                return "unchanged"
            logger.warning("Catalog database download failed: %s", exc)
            note_download_failure()
            return "error"
        except DownloadCancelled:
            return "cancelled"
        except (OSError, URLError) as exc:
            logger.warning("Catalog database download failed: %s", exc)
            note_download_failure()
            return "error"

        if not _validate_download(part):
            note_download_failure()
            return "error"
        _build_indexes(part, progress)
        try:
            os.replace(part, staged)
        except OSError as exc:
            logger.warning("Could not stage the downloaded catalog database: %s", exc)
            note_download_failure()
            return "error"
        clear_download_failure()
        promote_staged()
        return "ok"
    finally:
        try:
            if part.exists():
                part.unlink()
        except OSError:
            pass
        _download_lock.release()
