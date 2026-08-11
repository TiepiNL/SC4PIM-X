from types import SimpleNamespace

from sc4pimx.SC4DatTools import CreateAProp
from sc4pimx.SC4PIMApp import (
    _execute_exemplar_submenu_updates,
    _new_exemplar_patch_entry,
    _new_populated_exemplar_entry,
    _new_submenu_button_entry,
    _plan_exemplar_submenu_updates,
    _write_entries_atomic,
)
from sc4pimx.SC4MenuScanner import EXEMPLAR_PATCH_GROUP, SUBMENU_BUTTON_GROUP
from sc4pimx.SC4SubmenuPatchDlg import PatchTarget


def _property(prop_id, name, count):
    return SimpleNamespace(ID=prop_id, Name=name, Type="Uint32", Count=count)


def test_populated_submenu_exemplar_is_normalized_to_binary():
    prop = _property(0x8A2602CA, "Item Submenu Parent ID", 1)
    virtual_dat = SimpleNamespace(properties={prop.ID: prop})

    entry = _new_populated_exemplar_entry(
        (0x6534284A, 0x11111111, 0x22222222),
        "submenu.SC4Desc",
        virtual_dat,
        [CreateAProp(prop, (0xAC706063,))],
    )

    assert entry.rawContent.startswith(b"EQZT1###")
    assert b"Uint32:0:{0xac706063}" in entry.rawContent
    assert b"Uint32:0:(0xac706063)" not in entry.rawContent
    assert entry.exemplar.GetProp(prop.ID) == [0xAC706063]


def test_submenu_button_entry_uses_mayor_mode_button_group(tmp_path):
    prop = _property(0x8A2602CA, "Item Submenu Parent ID", 1)
    virtual_dat = SimpleNamespace(properties={prop.ID: prop})
    package = tmp_path / "submenu.SC4Desc"

    entry = _new_submenu_button_entry(
        0x22222222,
        str(package),
        virtual_dat,
        [CreateAProp(prop, (0xCE21DBEB,))],
    )

    assert entry.tgi == (0x6534284A, SUBMENU_BUTTON_GROUP, 0x22222222)
    _write_entries_atomic(str(package), [entry])
    assert package.is_file()


def test_populated_submenu_patch_cohort_is_normalized_to_binary():
    targets = _property(0x0062E78A, "Exemplar Patch Targets", 2)
    submenu = _property(0xAA1DD399, "Building Submenus", 1)
    virtual_dat = SimpleNamespace(properties={targets.ID: targets, submenu.ID: submenu})

    entry = _new_populated_exemplar_entry(
        (0x05342861, 0x11111111, 0x22222222),
        "patch.SC4Desc",
        virtual_dat,
        [
            CreateAProp(targets, (0x8A3858D8, 0x03280000)),
            CreateAProp(submenu, (0xAC706063,)),
        ],
        cohort=True,
    )

    assert entry.rawContent.startswith(b"CQZB1###")
    assert entry.exemplar.GetProp(targets.ID) == [0x8A3858D8, 0x03280000]
    assert entry.exemplar.GetProp(submenu.ID) == [0xAC706063]


def test_exemplar_patch_entry_uses_resource_loading_hooks_group(tmp_path):
    targets = _property(0x0062E78A, "Exemplar Patch Targets", 2)
    submenu = _property(0xAA1DD399, "Building Submenus", 1)
    virtual_dat = SimpleNamespace(properties={targets.ID: targets, submenu.ID: submenu})
    package = tmp_path / "patch.SC4Desc"

    entry = _new_exemplar_patch_entry(
        0x22222222,
        str(package),
        virtual_dat,
        [
            CreateAProp(targets, (0x8A3858D8, 0x03280000)),
            CreateAProp(submenu, (0xAC706063,)),
        ],
    )

    assert entry.tgi == (0x05342861, EXEMPLAR_PATCH_GROUP, 0x22222222)
    assert entry.rawContent.startswith(b"CQZB1###")
    _write_entries_atomic(str(package), [entry])
    assert package.is_file()


def test_direct_batch_update_preserves_membership_and_creates_backup(tmp_path):
    submenu = _property(0xAA1DD399, "Building Submenus", 1)
    virtual_dat = SimpleNamespace(properties={submenu.ID: submenu})
    package = tmp_path / "buildings.SC4Desc"
    entry = _new_populated_exemplar_entry(
        (0x6534284A, 0x11111111, 0x22222222),
        str(package),
        virtual_dat,
        [CreateAProp(submenu, (0xAAAA0001,))],
    )
    _write_entries_atomic(str(package), [entry])
    virtual_dat.GetAllEntriesFromFile = lambda path: [entry] if path == str(package) else []
    virtual_dat._submenu_cache = {"stale": True}
    target = PatchTarget("building", entry.exemplar, "Test building")

    packages, skipped = _plan_exemplar_submenu_updates([target], 0xAAAA0002)
    updated, failures, backups = _execute_exemplar_submenu_updates(
        virtual_dat, packages, 0xAAAA0002, create_backups=True,
    )

    assert skipped == []
    assert updated == [target]
    assert failures == []
    assert entry.exemplar.GetProp(submenu.ID) == [0xAAAA0001, 0xAAAA0002]
    assert backups == [str(package) + ".bak"]
    assert (tmp_path / "buildings.SC4Desc.bak").is_file()
    assert virtual_dat._submenu_cache == {}


def test_direct_batch_plan_skips_existing_and_non_building_targets(tmp_path):
    package = tmp_path / "items.SC4Desc"
    package.write_bytes(b"DBPF")
    exemplar = SimpleNamespace(
        entry=SimpleNamespace(tgi=(0x6534284A, 1, 2), fileName=str(package)),
        GetProp=lambda prop_id: [0xAAAA0001] if prop_id == 0xAA1DD399 else None,
    )
    building = PatchTarget("building", exemplar, "Building")
    flora = PatchTarget("flora", exemplar, "Flora")

    packages, skipped = _plan_exemplar_submenu_updates([building, flora], 0xAAAA0001)

    assert packages == {}
    assert [(target.name, reason) for target, reason in skipped] == [
        ("Building", "present"),
        ("Flora", "unsupported"),
    ]
