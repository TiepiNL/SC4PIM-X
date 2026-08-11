from types import SimpleNamespace

from sc4pimx.SC4DatTools import CreateAProp
from sc4pimx.SC4PIMApp import _new_populated_exemplar_entry


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
