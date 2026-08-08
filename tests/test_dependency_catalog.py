import json

import pytest

from sc4pimx import DependencyCatalog
from sc4pimx.DependencyCatalog import DEFAULT_TIMEOUT_SECONDS, DependencyCatalogClient, format_catalog_match


class FakeResponse:
    def __init__(self, data):
        self.data = json.dumps(data).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.data


def test_catalog_client_searches_tgi(monkeypatch):
    requested = []

    def fake_urlopen(url, timeout):
        requested.append((url, timeout))
        return FakeResponse({
            "value": [{
                "Package": "bsc:mega-props-sg-vol01",
                "FileName": "BSC MEGA Props - SG Vol01 v4.dat",
            }],
            "Count": 1,
        })

    monkeypatch.setattr(DependencyCatalog, "urlopen", fake_urlopen)
    client = DependencyCatalogClient({
        "Enabled": True,
        "BaseUrl": "http://localhost:3000/",
        "TimeoutSeconds": 2,
    })

    result = client.search_tgi((0x6534284A, 0xCF94DBB8, 0x10F5333F))

    assert result.status == "ok"
    assert result.matches[0]["Package"] == "bsc:mega-props-sg-vol01"
    assert requested[0][0].startswith("http://localhost:3000/api/search?")
    assert requested[0][1] == 2.0


def test_catalog_client_default_timeout_is_longer():
    client = DependencyCatalogClient({
        "Enabled": True,
        "BaseUrl": "http://localhost:3000",
    })

    assert client.timeout == DEFAULT_TIMEOUT_SECONDS
    assert client.timeout == 15.0


def test_catalog_client_disabled_does_not_request(monkeypatch):
    def fake_urlopen(url, timeout):
        raise AssertionError("urlopen should not be called")

    monkeypatch.setattr(DependencyCatalog, "urlopen", fake_urlopen)
    client = DependencyCatalogClient({"Enabled": False, "BaseUrl": "http://localhost:3000"})

    result = client.search_iid(0x10F5333F)
    assert result.status == "disabled"
    assert result.matches == []


def test_catalog_client_accepts_bare_list_response(monkeypatch):
    def fake_urlopen(url, timeout):
        return FakeResponse([{
            "Package": "bsc:textures-vol02",
            "FileName": "BSC Textures Vol02.dat",
        }])

    monkeypatch.setattr(DependencyCatalog, "urlopen", fake_urlopen)
    client = DependencyCatalogClient({
        "Enabled": True,
        "BaseUrl": "http://localhost:3000",
    })

    result = client.search_tgi((0x7AB50E44, 0x0986135E, 0x35042000))

    assert result.status == "ok"
    assert result.matches[0]["Package"] == "bsc:textures-vol02"


def test_catalog_client_retries_once_after_timeout(monkeypatch):
    calls = []

    def fake_urlopen(url, timeout):
        calls.append(url)
        if len(calls) == 1:
            raise TimeoutError("timed out")
        return FakeResponse([{"Package": "peg:247-mod"}])

    monkeypatch.setattr(DependencyCatalog, "urlopen", fake_urlopen)
    client = DependencyCatalogClient({"Enabled": True, "BaseUrl": "http://localhost:3000"})

    result = client.search_iid(0x2A7CCDA2)

    assert result.status == "ok"
    assert result.matches[0]["Package"] == "peg:247-mod"
    assert len(calls) == 2


def test_catalog_client_reports_error_after_two_failures(monkeypatch):
    calls = []

    def fake_urlopen(url, timeout):
        calls.append(url)
        raise TimeoutError("timed out")

    monkeypatch.setattr(DependencyCatalog, "urlopen", fake_urlopen)
    client = DependencyCatalogClient({"Enabled": True, "BaseUrl": "http://localhost:3000"})

    result = client.search_tgi((0x6534284A, 0xC977C536, 0x2A7CCDA2))

    assert result.status == "error"
    assert result.matches == []
    assert len(calls) == 2


def test_find_exemplar_entry_by_iid_searches_all_groups():
    from types import SimpleNamespace

    from sc4pimx.DependenciesDlg import DependenciesDlg

    system_group_prop = SimpleNamespace(tgi=(1697917002, 0xC977C536, 0x2A7CCDA2), fileName="peg247.dat")
    other = SimpleNamespace(tgi=(2058686020, 159781726, 0x2A7CCDA2), fileName="tex.dat")
    dlg = DependenciesDlg.__new__(DependenciesDlg)
    dlg.virtualDAT = SimpleNamespace(allEntries=[other, system_group_prop])

    assert dlg._find_exemplar_entry_by_iid(0x2A7CCDA2) is system_group_prop
    assert dlg._find_exemplar_entry_by_iid(0x12345678) is None


def test_format_catalog_match():
    assert format_catalog_match({
        "Package": "bsc:mega-props-sg-vol01",
        "FileName": "BSC MEGA Props - SG Vol01 v4.dat",
    }) == "catalog: bsc:mega-props-sg-vol01 (BSC MEGA Props - SG Vol01 v4.dat)"


def test_search_iids_batches_and_splits_by_tgi_instance(monkeypatch):
    requested = []

    def fake_urlopen(url, timeout):
        requested.append(url)
        return FakeResponse([
            {"Package": "bsc:mega-props-sg-vol01", "TGI": "0x6534284a, 0xcf94dbb8, 0x10f5333f"},
            {"Package": "peg:247-mod", "TGI": "0x6534284a, 0xc977c536, 0x2a7ccda2"},
        ])

    monkeypatch.setattr(DependencyCatalog, "urlopen", fake_urlopen)
    client = DependencyCatalogClient({
        "Enabled": True,
        "BaseUrl": "http://localhost:3000",
        "IidBatchSize": 25,
    })

    results = client.search_iids([0x10F5333F, 0x2A7CCDA2, 0x2A7CCDA2, 0xDEADBEEF])

    assert len(requested) == 1
    assert results[0x10F5333F].matches[0]["Package"] == "bsc:mega-props-sg-vol01"
    assert results[0x2A7CCDA2].matches[0]["Package"] == "peg:247-mod"
    assert results[0xDEADBEEF].matches == []


def test_search_iids_chunks_by_batch_size(monkeypatch):
    requested = []

    def fake_urlopen(url, timeout):
        requested.append(url)
        return FakeResponse([])

    monkeypatch.setattr(DependencyCatalog, "urlopen", fake_urlopen)
    client = DependencyCatalogClient({
        "Enabled": True,
        "BaseUrl": "http://localhost:3000",
        "IidBatchSize": 2,
    })

    results = client.search_iids([1, 2, 3, 4, 5])

    assert len(requested) == 3
    assert set(results.keys()) == {1, 2, 3, 4, 5}


class FakeLocalDatabase:
    """Stands in for catalog_db.LocalCatalogDatabase."""

    def __init__(self, tgi_matches=None, iid_matches=None):
        self.tgi_matches = tgi_matches
        self.iid_matches = iid_matches
        self.iid_calls = []

    def search_tgi(self, tgi):
        return self.tgi_matches

    def search_iids(self, iids):
        self.iid_calls.append(list(iids))
        return self.iid_matches

    def close(self):
        pass


@pytest.fixture
def no_urlopen(monkeypatch):
    def fail(url, timeout):
        raise AssertionError("the online catalog should not be used")

    monkeypatch.setattr(DependencyCatalog, "urlopen", fail)


def local_client(monkeypatch, database, **settings):
    monkeypatch.setattr(DependencyCatalog.catalog_db, "open_database", lambda: database)
    base = {"Enabled": True, "BaseUrl": "http://localhost:3000", "UseLocalDatabase": True}
    base.update(settings)
    return DependencyCatalogClient(base)


def test_local_database_is_used_instead_of_the_api(monkeypatch, no_urlopen):
    database = FakeLocalDatabase(tgi_matches=[{"Package": "bsc:mega-props-sg-vol01"}])
    client = local_client(monkeypatch, database)

    result = client.search_tgi((0x6534284A, 0xCF94DBB8, 0x10F5333F))

    assert result.status == "ok"
    assert result.matches[0]["Package"] == "bsc:mega-props-sg-vol01"


def test_local_database_is_ignored_when_disabled(monkeypatch):
    requested = []

    def fake_urlopen(url, timeout):
        requested.append(url)
        return FakeResponse([{"Package": "from-api"}])

    monkeypatch.setattr(DependencyCatalog, "urlopen", fake_urlopen)
    database = FakeLocalDatabase(tgi_matches=[{"Package": "from-local"}])
    client = local_client(monkeypatch, database, UseLocalDatabase=False)

    result = client.search_tgi((0x6534284A, 0xCF94DBB8, 0x10F5333F))

    assert result.matches[0]["Package"] == "from-api"
    assert len(requested) == 1


def test_failed_local_query_falls_back_to_the_api(monkeypatch):
    def fake_urlopen(url, timeout):
        return FakeResponse([{"Package": "from-api"}])

    monkeypatch.setattr(DependencyCatalog, "urlopen", fake_urlopen)
    # None means the local query could not run at all.
    client = local_client(monkeypatch, FakeLocalDatabase(tgi_matches=None))

    result = client.search_tgi((0x6534284A, 0xCF94DBB8, 0x10F5333F))

    assert result.status == "ok"
    assert result.matches[0]["Package"] == "from-api"


def test_empty_local_result_is_authoritative(monkeypatch, no_urlopen):
    client = local_client(monkeypatch, FakeLocalDatabase(tgi_matches=[]))

    result = client.search_tgi((0x6534284A, 0xCF94DBB8, 0x10F5333F))

    assert result.status == "ok"
    assert result.matches == []


def test_local_database_works_without_a_base_url(monkeypatch, no_urlopen):
    database = FakeLocalDatabase(tgi_matches=[{"Package": "from-local"}])
    client = local_client(monkeypatch, database, BaseUrl="")

    assert client.has_source
    assert client.search_tgi((0x6534284A, 0xCF94DBB8, 0x10F5333F)).matches


def test_without_a_base_url_or_local_database_lookups_are_disabled(monkeypatch, no_urlopen):
    client = local_client(monkeypatch, None, BaseUrl="")

    assert not client.has_source
    assert client.search_tgi((0x6534284A, 0xCF94DBB8, 0x10F5333F)).status == "disabled"
    assert client.search_iids([0x10F5333F])[0x10F5333F].status == "disabled"


def test_local_search_iids_splits_matches_in_one_query(monkeypatch, no_urlopen):
    database = FakeLocalDatabase(iid_matches=[
        {"Package": "bsc:mega-props-sg-vol01", "TGI": "0x6534284a, 0xcf94dbb8, 0x10f5333f"},
        {"Package": "peg:247-mod", "TGI": "0x6534284a, 0xc977c536, 0x2a7ccda2"},
    ])
    client = local_client(monkeypatch, database, IidBatchSize=1)

    results = client.search_iids([0x10F5333F, 0x2A7CCDA2, 0xDEADBEEF])

    # One query regardless of IidBatchSize -- that limit is an HTTP concern.
    assert database.iid_calls == [[0x10F5333F, 0x2A7CCDA2, 0xDEADBEEF]]
    assert results[0x10F5333F].matches[0]["Package"] == "bsc:mega-props-sg-vol01"
    assert results[0x2A7CCDA2].matches[0]["Package"] == "peg:247-mod"
    assert results[0xDEADBEEF].matches == []
