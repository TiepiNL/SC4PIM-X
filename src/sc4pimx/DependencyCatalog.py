"""Client for optional SC4 dependency catalog lookups."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 15.0


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

    def search_tgi(self, tgi):
        if not self.enabled or not self.base_url or not tgi:
            return CatalogLookupResult("disabled", [])
        query = "%s/api/search?%s" % (
            self.base_url,
            urlencode({"tgi": "0x%08X, 0x%08X, 0x%08X" % tuple(tgi)}),
        )
        return self._fetch_items(query, "TGI %r" % (tgi,))

    def search_iid(self, iid):
        if not self.enabled or not self.base_url or iid is None:
            return CatalogLookupResult("disabled", [])
        query = "%s/api/iid?%s" % (
            self.base_url,
            urlencode({"value": "0x%08X" % int(iid)}),
        )
        return self._fetch_items(query, "IID %r" % (iid,))

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


def _response_items(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        value = data.get("value")
        if isinstance(value, list):
            return value
    return None
