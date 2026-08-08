import json

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
