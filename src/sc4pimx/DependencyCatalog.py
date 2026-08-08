"""Client for optional SC4 dependency catalog lookups.

Lookups prefer the local SQLite copy of the catalog (:mod:`catalog_db`) and
fall back to the hosted API when it is absent, unreadable or out of step with
the schema we expect.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from . import catalog_db

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_IID_BATCH_SIZE = 25


@dataclass(frozen=True)
class CatalogLookupResult:
    status: str
    matches: list


class DependencyCatalogClient:
    def __init__(self, settings):
        self.enabled = bool(settings.get("Enabled", False))
        self.base_url = str(settings.get("BaseUrl", "")).strip().rstrip("/")
        try:
            self.timeout = max(1.0, float(settings.get("TimeoutSeconds", DEFAULT_TIMEOUT_SECONDS)))
        except (TypeError, ValueError):
            self.timeout = DEFAULT_TIMEOUT_SECONDS
        try:
            self.iid_batch_size = max(1, int(settings.get("IidBatchSize", DEFAULT_IID_BATCH_SIZE)))
        except (TypeError, ValueError):
            self.iid_batch_size = DEFAULT_IID_BATCH_SIZE
        # Defaults to False so callers constructing a client from a bare dict
        # never reach for the user's downloaded database; config.py holds the
        # real default, as it does for Enabled.
        self.use_local = bool(settings.get("UseLocalDatabase", False))
        self._local = None
        self._local_checked = False

    @property
    def local_available(self):
        return self._local_db() is not None

    @property
    def has_source(self):
        """Whether lookups can resolve at all, locally or online."""
        return bool(self.base_url) or self.local_available

    def _local_db(self):
        # Opened on first use so building a client (which the dialog does on
        # the GUI thread) never touches the filesystem.
        if not self.use_local:
            return None
        if not self._local_checked:
            self._local_checked = True
            self._local = catalog_db.open_database()
        return self._local

    def close(self):
        if self._local is not None:
            self._local.close()
            self._local = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

    def search_tgi(self, tgi):
        if not self.enabled or not tgi:
            return CatalogLookupResult("disabled", [])
        local = self._local_db()
        if local is not None:
            matches = local.search_tgi(tgi)
            if matches is not None:
                return CatalogLookupResult("ok", matches)
        if not self.base_url:
            return CatalogLookupResult("disabled", [])
        query = "%s/api/search?%s" % (
            self.base_url,
            urlencode({"tgi": "0x%08X, 0x%08X, 0x%08X" % tuple(tgi)}),
        )
        return self._fetch_items(query, "TGI %r" % (tgi,))

    def search_iid(self, iid):
        if not self.enabled or iid is None:
            return CatalogLookupResult("disabled", [])
        local = self._local_db()
        if local is not None:
            matches = local.search_iids([iid])
            if matches is not None:
                return CatalogLookupResult("ok", matches)
        if not self.base_url:
            return CatalogLookupResult("disabled", [])
        query = "%s/api/iid?%s" % (
            self.base_url,
            urlencode({"value": "0x%08X" % int(iid)}),
        )
        return self._fetch_items(query, "IID %r" % (iid,))

    def search_iids(self, iids):
        """Batched IID lookup, one result per requested instance id.

        Both back-ends return one flat match list, so results are re-split by
        the instance id in each match's TGI. Online, the /api/iid endpoint
        accepts a comma-separated `value` list, which keeps the request count
        down for a dialog full of missing dependencies.
        """
        unique_iids = []
        seen = set()
        for iid in iids:
            if iid is None:
                continue
            key = int(iid)
            if key not in seen:
                seen.add(key)
                unique_iids.append(key)
        if not unique_iids:
            return {}
        if not self.enabled:
            return {iid: CatalogLookupResult("disabled", []) for iid in unique_iids}

        local = self._local_db()
        if local is not None:
            matches = local.search_iids(unique_iids)
            if matches is not None:
                return _split_by_iid(unique_iids, matches, "ok")
        if not self.base_url:
            return {iid: CatalogLookupResult("disabled", []) for iid in unique_iids}

        results = {}
        for start in range(0, len(unique_iids), self.iid_batch_size):
            chunk = unique_iids[start:start + self.iid_batch_size]
            query = "%s/api/iid?%s" % (
                self.base_url,
                urlencode({"value": ", ".join("0x%08X" % iid for iid in chunk)}),
            )
            chunk_result = self._fetch_items(query, "IIDs %r" % (chunk,))
            if chunk_result.status == "error":
                for iid in chunk:
                    results[iid] = CatalogLookupResult("error", [])
                continue
            results.update(_split_by_iid(chunk, chunk_result.matches, chunk_result.status))
        return results

    def _fetch_items(self, query, describe):
        # One retry: the catalog is a hosted service that cold-starts, so the
        # first request after idle regularly exceeds a short timeout and would
        # otherwise mark every row "Offline" for the whole run.
        last_error = None
        for _attempt in range(2):
            try:
                with urlopen(query, timeout=self.timeout) as response:
                    data = json.loads(response.read().decode("utf-8"))
            except (OSError, URLError, ValueError, json.JSONDecodeError) as exc:
                last_error = exc
                continue
            value = _response_items(data)
            if value is None:
                return CatalogLookupResult("error", [])
            matches = [item for item in value if isinstance(item, dict)]
            return CatalogLookupResult("ok", matches)
        logger.warning("Dependency catalog lookup failed for %s: %s", describe, last_error)
        return CatalogLookupResult("error", [])


def format_catalog_match(match):
    package = str(match.get("Package") or "").strip()
    file_name = str(match.get("FileName") or "").strip()
    if package and file_name:
        return "catalog: %s (%s)" % (package, file_name)
    if package:
        return "catalog: %s" % package
    if file_name:
        return "catalog: %s" % file_name
    return ""


def _split_by_iid(iids, matches, status):
    """Group a flat match list back onto the instance ids that were asked for."""
    by_iid = {iid: [] for iid in iids}
    for match in matches:
        instance = _match_tgi_instance(match)
        if instance in by_iid:
            by_iid[instance].append(match)
    return {iid: CatalogLookupResult(status, by_iid[iid]) for iid in iids}


def _match_tgi_instance(match):
    text = str(match.get("TGI") or "")
    parts = [p.strip() for p in text.split(",")]
    if len(parts) < 3:
        return None
    try:
        return int(parts[2], 16)
    except (ValueError, TypeError):
        return None


def _response_items(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        value = data.get("value")
        if isinstance(value, list):
            return value
    return None
