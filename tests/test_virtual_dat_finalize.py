import logging
from types import SimpleNamespace

import pytest

from sc4pimx import SC4VirtualDat


def test_finalize_incremental_yields_between_entry_batches(monkeypatch):
    monkeypatch.setattr(SC4VirtualDat, "FinalizeCategory", lambda _root: None)

    updated = []
    virtual_dat = SC4VirtualDat.VirtualDat.__new__(SC4VirtualDat.VirtualDat)
    virtual_dat.allEntries = [
        SimpleNamespace(tgi=(87304289, 0, index), bStandard=False)
        for index in range(5)
    ]
    virtual_dat.tree = SimpleNamespace(
        UpdateEntry=lambda entry, *_args: updated.append(entry)
    )
    virtual_dat.rootCategory = object()
    virtual_dat.standardModels = []
    virtual_dat.otherModels = []
    virtual_dat.atcs = []
    virtual_dat.allTextures = []

    statuses = []
    dialog = SimpleNamespace(
        SetStatus=lambda text, detail="": statuses.append((text, detail))
    )

    yields = list(virtual_dat.FinalizeIncremental(dialog, batch_size=2))

    assert len(yields) == 3
    assert virtual_dat.cohorts == virtual_dat.allEntries
    assert updated == virtual_dat.allEntries
    assert statuses[-1] == ("Building resource index...", "4 / 5 entries")
    assert virtual_dat.missing_pictures == []
    assert virtual_dat.missing_atc_pictures == []


def test_finalize_incremental_skips_io_error(monkeypatch):
    """One unreadable entry must not abort startup finalization.

    Regression test for deep (>MAX_PATH) plugin files on a process
    without Win32 long-path support: the cold scan skips the file, and
    a warm start served from dat_cache.sqlite must skip the entry the
    same way instead of letting FileNotFoundError escape
    FinalizeIncremental -> UpdateEntry -> SC4Entry.read_file.
    """
    monkeypatch.setattr(SC4VirtualDat, "FinalizeCategory", lambda _root: None)

    bad = SimpleNamespace(
        tgi=(87304289, 0, 1), bStandard=False, fileName="deep.dat")
    good_cohort = SimpleNamespace(
        tgi=(87304289, 0, 2), bStandard=False, fileName="good.dat")
    good_other = SimpleNamespace(
        tgi=(1697917002, 0, 3), bStandard=False, fileName="good2.dat")

    updated = []

    def _update(entry, *_args):
        if entry is bad:
            raise FileNotFoundError("deep.dat")
        updated.append(entry)

    virtual_dat = SC4VirtualDat.VirtualDat.__new__(SC4VirtualDat.VirtualDat)
    virtual_dat.allEntries = [bad, good_cohort, good_other]
    virtual_dat.tree = SimpleNamespace(UpdateEntry=_update)
    virtual_dat.rootCategory = object()
    virtual_dat.standardModels = []
    virtual_dat.otherModels = []
    virtual_dat.atcs = []
    virtual_dat.allTextures = []

    dialog = SimpleNamespace(SetStatus=lambda text, detail="": None)

    list(virtual_dat.FinalizeIncremental(dialog, batch_size=0))

    assert updated == [good_cohort, good_other]
    # Structural indexes are preserved; only per-entry derivation is skipped.
    assert virtual_dat.cohorts == [bad, good_cohort]
    assert virtual_dat.missing_pictures == []
    assert virtual_dat.missing_atc_pictures == []


def test_finalize_incremental_propagates_non_io_error(monkeypatch):
    monkeypatch.setattr(SC4VirtualDat, "FinalizeCategory", lambda _root: None)

    entry = SimpleNamespace(
        tgi=(87304289, 0, 1), bStandard=False, fileName="broken.dat")

    def _update(*_args):
        raise KeyError("category")

    virtual_dat = SC4VirtualDat.VirtualDat.__new__(SC4VirtualDat.VirtualDat)
    virtual_dat.allEntries = [entry]
    virtual_dat.tree = SimpleNamespace(UpdateEntry=_update)
    virtual_dat.rootCategory = object()
    virtual_dat.standardModels = []
    virtual_dat.otherModels = []
    virtual_dat.atcs = []
    virtual_dat.allTextures = []

    with pytest.raises(KeyError, match="category"):
        list(virtual_dat.FinalizeIncremental(None, batch_size=0))


@pytest.mark.parametrize(
    "tgi",
    [
        (87304289, 0, 1),
        (1697917002, 0, 2),
    ],
    ids=["cohort", "exemplar"],
)
def test_update_entry_skips_unreadable_source_on_oserror(caplog, tgi):
    """The production UpdateEntry guards both lazy exemplar reads."""
    from sc4pimx import SC4PIMApp

    caplog.set_level(logging.WARNING)

    entry = SimpleNamespace(tgi=tgi, fileName="deep.dat")
    entry.read_file = lambda *a, **k: (_ for _ in ()).throw(OSError("deep.dat"))

    SC4PIMApp.MyTreeCtrl.UpdateEntry(
        SimpleNamespace(), entry, SimpleNamespace(), False, None)

    assert 'exemplar' not in entry.__dict__
    assert 'Skipping unreadable entry' in caplog.text
    assert str(tgi[0]) in caplog.text


def test_cached_unreadable_file_cannot_shadow_readable_provider(
        monkeypatch, tmp_path):
    """Cache hits are opened before any of their TGIs enter the indexes."""
    tgi = (87304289, 0, 1)
    readable_path = tmp_path / "readable.dat"
    readable_path.write_bytes(b"DBPF")
    unreadable_path = tmp_path / "missing.dat"

    readable = SimpleNamespace(tgi=tgi, fileName=str(readable_path))
    unreadable = SimpleNamespace(tgi=tgi, fileName=str(unreadable_path))
    cached = {
        str(readable_path): [readable],
        str(unreadable_path): [unreadable],
    }

    class _Cache:
        def lookup(self, path):
            return cached[path]

        def stats(self):
            return 2, 0, 0

        def close(self):
            pass

    monkeypatch.setattr(
        SC4VirtualDat.DatFileCache,
        "open_default",
        lambda stat_cache=None: _Cache(),
    )

    virtual_dat = SC4VirtualDat.VirtualDat.__new__(SC4VirtualDat.VirtualDat)
    virtual_dat._scan_stat_cache = {}
    virtual_dat.allEntries = []
    virtual_dat.TGIIndex = {}
    virtual_dat.shadowed = {}

    virtual_dat.load_files_parallel([
        (str(readable_path), False),
        (str(unreadable_path), False),
    ])

    assert virtual_dat.allEntries == [readable]
    assert virtual_dat.getEntry(*tgi) is readable
    assert virtual_dat.shadowed == {}


def test_finalize_incremental_logs_file_and_tgi_on_failure(monkeypatch, caplog):
    monkeypatch.setattr(SC4VirtualDat, "FinalizeCategory", lambda _root: None)

    entry = SimpleNamespace(
        tgi=(1697917002, 0x2A3B4C5D, 0x0BADF00D), bStandard=False,
        fileName="plugins/broken.dat")

    def _update(*_args):
        raise KeyError("category")

    virtual_dat = SC4VirtualDat.VirtualDat.__new__(SC4VirtualDat.VirtualDat)
    virtual_dat.allEntries = [entry]
    virtual_dat.tree = SimpleNamespace(UpdateEntry=_update)
    virtual_dat.rootCategory = object()
    virtual_dat.standardModels = []
    virtual_dat.otherModels = []
    virtual_dat.atcs = []
    virtual_dat.allTextures = []

    with caplog.at_level(logging.WARNING, logger="sc4pimx.SC4VirtualDat"):
        with pytest.raises(KeyError):
            list(virtual_dat.FinalizeIncremental(None, batch_size=0))

    message = caplog.text
    assert "plugins/broken.dat" in message
    assert "0x2A3B4C5D" in message
    assert "0x0BADF00D" in message
