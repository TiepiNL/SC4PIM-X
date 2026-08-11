from types import SimpleNamespace

import pytest

from sc4pimx.SC4MenuScanner import (
    BUILDING_EXEMPLAR_TYPE,
    CATEGORY_BUILDING,
    CATEGORY_FLORA,
    KIND_MENU,
    KIND_ORPHAN,
    KIND_ROOT,
    PNG_ICON_TYPE,
    PROP_BUILDING_SUBMENUS,
    PROP_EXEMPLAR_NAME,
    PROP_EXEMPLAR_PATCH_TARGETS,
    PROP_ITEM_BUTTON_ID,
    PROP_ITEM_ICON,
    PROP_ITEM_ORDER,
    PROP_ITEM_SUBMENU_PARENT_ID,
    SOURCE_BUILTIN,
    SOURCE_SCANNED,
    SUBMENU_BUTTON_KIND,
    VIA_EXEMPLAR,
    VIA_PATCH,
    MenuEntry,
    build_menu_tree,
    builtin_menus,
    invalidate_menu_cache,
    menu_entries,
    menu_icon_entry,
    menu_icon_png,
    menu_members,
    menu_options,
    menu_path,
    scan_menus,
)

RCI = "SubMenuROOTRCI"
PARKS = "SubMenuROOTPark"


class FakeExemplar:
    def __init__(self, props, tgi=None, file_name=None):
        self.props = dict(props)
        self.entry = SimpleNamespace(tgi=tgi, fileName=file_name, exemplar=self) if tgi else None

    def GetProp(self, key):
        return self.props.get(key)


def _entry(tgi, exemplar=None, file_name="plugin.dat"):
    return SimpleNamespace(tgi=tgi, exemplar=exemplar, fileName=file_name)


class FakeDat:
    def __init__(self, options=None, groups=None, all_entries=(), categories=None, cohorts=()):
        prop_def = SimpleNamespace(Options=dict(options or {}), OptionGroups=dict(groups or {}))
        self.properties = {PROP_BUILDING_SUBMENUS: prop_def}
        self.allEntries = list(all_entries)
        self.categories = categories or {}
        self.cohorts = list(cohorts)

    def getEntry(self, t, g, i):
        for entry in self.allEntries:
            if tuple(entry.tgi) == (t, g, i):
                return entry
        return None


def _category(descriptors):
    return SimpleNamespace(descriptors=list(descriptors))


def _descriptor(name, exemplar):
    return SimpleNamespace(name=name, exemplar=exemplar)


def _menu_button(value, parent, name, order=0, iid=None):
    tgi = (BUILDING_EXEMPLAR_TYPE, 0x1234, iid if iid is not None else value)
    exemplar = FakeExemplar({
        0x10: [SUBMENU_BUTTON_KIND],
        PROP_ITEM_BUTTON_ID: [value],
        PROP_ITEM_SUBMENU_PARENT_ID: [parent],
        PROP_ITEM_ORDER: [order],
        PROP_EXEMPLAR_NAME: [name],
    }, tgi=tgi)
    return _entry(tgi, exemplar)


# -- discovery ---------------------------------------------------------------


def test_builtin_menus_carry_their_root_group():
    dat = FakeDat(options={0xAAAA0001: "Ploppable Residential"}, groups={0xAAAA0001: RCI})

    entries = builtin_menus(dat)

    assert entries[0xAAAA0001].label == "Ploppable Residential"
    assert entries[0xAAAA0001].root_group == RCI
    assert entries[0xAAAA0001].source == SOURCE_BUILTIN
    assert entries[0xAAAA0001].parent_id is None


def test_scan_menus_finds_button_exemplars_and_caches():
    dat = FakeDat(all_entries=[_menu_button(0xB0000001, 0xAAAA0001, "Fountains", order=5)])

    menus = scan_menus(dat)

    assert menus[0xB0000001].label == "Fountains"
    assert menus[0xB0000001].parent_id == 0xAAAA0001
    assert menus[0xB0000001].item_order == 5
    assert menus[0xB0000001].file_name == "plugin.dat"

    dat.allEntries.append(_menu_button(0xB0000002, 0xAAAA0001, "Statues"))
    assert 0xB0000002 not in scan_menus(dat)
    assert 0xB0000002 in scan_menus(dat, force=True)


def test_scan_menus_skips_non_menu_exemplars():
    plain = FakeExemplar({PROP_EXEMPLAR_NAME: ["Some Building"]}, tgi=(BUILDING_EXEMPLAR_TYPE, 1, 2))
    item = FakeExemplar({
        0x10: [2],
        PROP_ITEM_SUBMENU_PARENT_ID: [0xAAAA0001],
        PROP_ITEM_BUTTON_ID: [0xB0000001],
    }, tgi=(BUILDING_EXEMPLAR_TYPE, 1, 3))
    dat = FakeDat(all_entries=[
        _entry(plain.entry.tgi, plain),
        _entry(item.entry.tgi, item),
        _entry((0x1234, 1, 2), None),
    ])

    assert scan_menus(dat) == {}


def test_menu_entries_merge_keeps_curated_label_and_scanned_parent():
    dat = FakeDat(
        options={0xAAAA0001: "Parks (curated)"},
        groups={0xAAAA0001: PARKS},
        all_entries=[_menu_button(0xAAAA0001, 0x00000003, "Parks (in plugin)", order=7)],
    )

    entry = menu_entries(dat)[0xAAAA0001]

    assert entry.label == "Parks (curated)"
    assert entry.source == SOURCE_BUILTIN
    assert entry.root_group == PARKS
    assert entry.parent_id == 0x00000003
    assert entry.item_order == 7


def test_menu_options_covers_both_sources():
    dat = FakeDat(
        options={0xAAAA0001: "Curated"},
        all_entries=[_menu_button(0xB0000001, 0xAAAA0001, "Scanned")],
    )

    assert menu_options(dat) == {0xAAAA0001: "Curated", 0xB0000001: "Scanned"}
    assert menu_entries(dat)[0xB0000001].source == SOURCE_SCANNED


def test_invalidate_menu_cache_forces_a_rescan():
    dat = FakeDat(all_entries=[_menu_button(0xB0000001, 0xAAAA0001, "First")])
    assert set(menu_options(dat)) == {0xB0000001}

    dat.allEntries.append(_menu_button(0xB0000002, 0xAAAA0001, "Second"))
    assert set(menu_options(dat)) == {0xB0000001}

    invalidate_menu_cache(dat)
    assert set(menu_options(dat)) == {0xB0000001, 0xB0000002}


# -- tree --------------------------------------------------------------------


def test_tree_nests_scanned_menus_under_their_known_parent():
    dat = FakeDat(
        options={0xAAAA0001: "Parks"},
        groups={0xAAAA0001: PARKS},
        all_entries=[_menu_button(0xB0000001, 0xAAAA0001, "Fountains")],
    )

    roots = build_menu_tree(menu_entries(dat))

    assert [node.kind for node in roots] == [KIND_ROOT]
    assert roots[0].label == "Parks"
    parks = roots[0].children[0]
    assert parks.kind == KIND_MENU and parks.value == 0xAAAA0001
    assert [child.value for child in parks.children] == [0xB0000001]


def test_tree_buckets_menus_whose_parent_is_a_game_toolbar_button():
    dat = FakeDat(all_entries=[
        _menu_button(0xB0000001, 0x4A22EA06, "Trees"),
        _menu_button(0xB0000002, 0x4A22EA06, "Rocks"),
    ])

    roots = build_menu_tree(menu_entries(dat), orphan_label="Game menu %s")

    assert len(roots) == 1
    assert roots[0].kind == KIND_ORPHAN
    assert roots[0].label == "Game menu 0x4A22EA06"
    assert {child.value for child in roots[0].children} == {0xB0000001, 0xB0000002}


def test_tree_orders_children_by_item_order_then_label():
    dat = FakeDat(
        options={0xAAAA0001: "Parks"},
        groups={0xAAAA0001: PARKS},
        all_entries=[
            _menu_button(0xB0000003, 0xAAAA0001, "Zebra", order=1),
            _menu_button(0xB0000001, 0xAAAA0001, "Beta", order=9),
            _menu_button(0xB0000002, 0xAAAA0001, "Alpha", order=1),
        ],
    )

    parks = build_menu_tree(menu_entries(dat))[0].children[0]

    assert [child.label for child in parks.children] == ["Alpha", "Zebra", "Beta"]


def test_tree_survives_a_parent_cycle():
    dat = FakeDat(all_entries=[
        _menu_button(0xB0000001, 0xB0000002, "One"),
        _menu_button(0xB0000002, 0xB0000001, "Two"),
    ])

    roots = build_menu_tree(menu_entries(dat))

    # Neither menu can be a root, so the pair only shows up as each other's
    # child; the point of the test is that building the tree terminates.
    assert roots == []


def test_menu_path_walks_up_to_the_root_group():
    dat = FakeDat(
        options={0xAAAA0001: "Parks"},
        groups={0xAAAA0001: PARKS},
        all_entries=[
            _menu_button(0xB0000001, 0xAAAA0001, "Fountains"),
            _menu_button(0xB0000002, 0xB0000001, "Small Fountains"),
        ],
    )

    entries = menu_entries(dat)

    assert menu_path(entries, 0xB0000002) == "Parks > Fountains > Small Fountains"
    assert menu_path(entries, 0xDEADBEEF) == "0xDEADBEEF"


def test_menu_path_does_not_repeat_a_toolbar_named_like_its_menu():
    dat = FakeDat(options={0xAAAA0001: "Parks", 0xAAAA0002: "Ploppable Residential"},
                  groups={0xAAAA0001: PARKS, 0xAAAA0002: RCI})

    entries = menu_entries(dat)

    assert menu_path(entries, 0xAAAA0001) == "Parks"
    assert menu_path(entries, 0xAAAA0002) == "RCI > Ploppable Residential"


# -- membership --------------------------------------------------------------


def _dat_with_items():
    tower = FakeExemplar({PROP_BUILDING_SUBMENUS: [0xAAAA0001, 0xAAAA0002]},
                         tgi=(BUILDING_EXEMPLAR_TYPE, 0x10, 0x100))
    shed = FakeExemplar({PROP_BUILDING_SUBMENUS: [0xAAAA0001]},
                        tgi=(BUILDING_EXEMPLAR_TYPE, 0x10, 0x101))
    palm = FakeExemplar({PROP_ITEM_SUBMENU_PARENT_ID: [0xAAAA0001]},
                        tgi=(BUILDING_EXEMPLAR_TYPE, 0x10, 0x200))
    return FakeDat(
        options={0xAAAA0001: "Parks", 0xAAAA0002: "Landmarks"},
        categories={
            CATEGORY_BUILDING: _category([_descriptor("Tower", tower), _descriptor("Shed", shed)]),
            CATEGORY_FLORA: _category([_descriptor("Palm", palm)]),
        },
    )


def test_menu_members_reads_buildings_and_flora():
    members = menu_members(_dat_with_items())

    assert [(m.name, m.kind, m.via) for m in members[0xAAAA0001]] == [
        ("Shed", "building", VIA_EXEMPLAR),
        ("Tower", "building", VIA_EXEMPLAR),
        ("Palm", "flora", VIA_EXEMPLAR),
    ]
    assert [m.name for m in members[0xAAAA0002]] == ["Tower"]


def test_menu_members_includes_patch_cohorts_and_resolves_names():
    dat = _dat_with_items()
    cohort = FakeExemplar({
        PROP_EXEMPLAR_PATCH_TARGETS: [0x10, 0x101, 0x10, 0x999],
        PROP_BUILDING_SUBMENUS: [0xAAAA0002],
    })
    dat.cohorts.append(SimpleNamespace(tgi=(0x05342861, 1, 1), exemplar=cohort))

    members = menu_members(dat)
    patched = {m.name: m for m in members[0xAAAA0002] if m.via == VIA_PATCH}

    assert set(patched) == {"Shed", "0x00000010-0x00000999"}
    assert patched["Shed"].descriptor is not None
    assert patched["0x00000010-0x00000999"].descriptor is None


def test_menu_members_does_not_double_list_an_already_assigned_item():
    dat = _dat_with_items()
    cohort = FakeExemplar({
        PROP_EXEMPLAR_PATCH_TARGETS: [0x10, 0x100],
        PROP_BUILDING_SUBMENUS: [0xAAAA0001],
    })
    dat.cohorts.append(SimpleNamespace(tgi=(0x05342861, 1, 1), exemplar=cohort))

    assert [m.name for m in menu_members(dat)[0xAAAA0001]] == ["Shed", "Tower", "Palm"]


def test_menu_members_ignores_cohorts_that_are_not_submenu_patches():
    dat = _dat_with_items()
    dat.cohorts.append(SimpleNamespace(
        tgi=(0x05342861, 1, 1),
        exemplar=FakeExemplar({PROP_EXEMPLAR_PATCH_TARGETS: [0x10, 0x100]}),
    ))

    assert len(menu_members(dat)[0xAAAA0001]) == 3


# -- icons -------------------------------------------------------------------


def _icon_entry(group, instance, content=b"PNGDATA"):
    entry = SimpleNamespace(tgi=(PNG_ICON_TYPE, group, instance), content=content,
                            fileName="icons.dat", rawContent=content)
    entry.read_file = lambda *_args, **_kwargs: False
    return entry


def test_menu_icon_entry_prefers_the_buttons_own_group():
    mine = _icon_entry(0x1234, 0x600D, b"MINE")
    theirs = _icon_entry(0x9999, 0x600D, b"THEIRS")
    dat = FakeDat(all_entries=[theirs, mine])
    entry = MenuEntry(value=0xB1, label="X", parent_id=None, item_order=0, root_group=None,
                      source=SOURCE_SCANNED, tgi=(BUILDING_EXEMPLAR_TYPE, 0x1234, 0xB1),
                      icon_id=0x600D)

    assert menu_icon_entry(dat, entry) is mine


def test_menu_icon_entry_falls_back_to_any_group_with_that_instance():
    theirs = _icon_entry(0x9999, 0x600D, b"THEIRS")
    dat = FakeDat(all_entries=[theirs])
    entry = MenuEntry(value=0xB1, label="X", parent_id=None, item_order=0, root_group=None,
                      source=SOURCE_SCANNED, tgi=(BUILDING_EXEMPLAR_TYPE, 0x1234, 0xB1),
                      icon_id=0x600D)

    assert menu_icon_entry(dat, entry) is theirs
    assert menu_icon_png(dat, entry) == b"THEIRS"


def test_menu_icon_entry_uses_the_button_id_when_no_icon_prop_is_set():
    icon = _icon_entry(0x1234, 0xB1)
    dat = FakeDat(all_entries=[icon])
    entry = MenuEntry(value=0xB1, label="X", parent_id=None, item_order=0, root_group=None,
                      source=SOURCE_SCANNED, tgi=(BUILDING_EXEMPLAR_TYPE, 0x1234, 0xB1))

    assert menu_icon_entry(dat, entry) is icon


def test_menu_icon_png_reads_an_entry_whose_content_was_never_loaded():
    entry = SimpleNamespace(tgi=(PNG_ICON_TYPE, 0x1234, 0xB1), fileName="icons.dat", rawContent=None)

    def read_file(*_args, **_kwargs):
        entry.content = b"LOADED"
        return True

    entry.read_file = read_file
    dat = FakeDat(all_entries=[entry])
    menu = MenuEntry(value=0xB1, label="X", parent_id=None, item_order=0, root_group=None,
                     source=SOURCE_SCANNED, tgi=(BUILDING_EXEMPLAR_TYPE, 0x1234, 0xB1))

    assert menu_icon_png(dat, menu) == b"LOADED"


def test_menu_icon_png_is_none_when_no_icon_exists():
    dat = FakeDat()
    menu = MenuEntry(value=0xB1, label="X", parent_id=None, item_order=0, root_group=None,
                     source=SOURCE_SCANNED, tgi=(BUILDING_EXEMPLAR_TYPE, 0x1234, 0xB1))

    assert menu_icon_entry(dat, menu) is None
    assert menu_icon_png(dat, menu) is None


def test_scanned_menus_record_their_icon_id():
    button = _menu_button(0xB0000001, 0xAAAA0001, "Fountains")
    button.exemplar.props[PROP_ITEM_ICON] = [0x600D]
    dat = FakeDat(all_entries=[button])

    assert scan_menus(dat)[0xB0000001].icon_id == 0x600D
    assert menu_entries(dat)[0xB0000001].icon_id == 0x600D


# -- shared widget helper ----------------------------------------------------


@pytest.mark.parametrize("raw,expected", [
    ("0xAABBCCDD", 0xAABBCCDD),
    ("0xAABBCCDD  Parks > Fountains", 0xAABBCCDD),
    ("  0x1  ", 1),
    ("Parks", None),
    ("", None),
    ("0xZZ", None),
    ("0x1FFFFFFFF", None),
])
def test_parse_menu_id(raw, expected):
    from sc4pimx.SC4SubmenuWidgets import parse_menu_id

    assert parse_menu_id(raw) == expected


# -- publishing freshly written entries --------------------------------------


def test_publish_new_entries_registers_cohorts_and_drops_caches():
    from sc4pimx import SC4PIMApp

    added = []
    dat = SimpleNamespace(cohorts=[], _submenu_cache={"entries": {"stale": True}})
    dat.addEntries = lambda entries, dlg, standard, force: added.extend(entries)
    cohort = SimpleNamespace(tgi=(0x05342861, 1, 2))
    exemplar = SimpleNamespace(tgi=(BUILDING_EXEMPLAR_TYPE, 1, 2))

    SC4PIMApp._publish_new_entries(dat, [cohort, exemplar])

    assert added == [cohort, exemplar]
    assert dat.cohorts == [cohort]
    assert dat._submenu_cache == {}
