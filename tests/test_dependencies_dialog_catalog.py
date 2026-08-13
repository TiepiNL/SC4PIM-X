from sc4pimx.DependenciesDlg import (
    DependencyRow,
    dependency_package_buckets,
    dependency_plain_text,
    filter_catalog_matches,
    found_catalog_status,
    identification_catalog_status,
    is_ignored_sound_iid,
    is_builtin_game_file,
    is_placeholder_ltext_key,
    is_tool_asset_file,
    lookup_catalog,
    minimize_catalog_packages,
    minimize_choices,
    minimize_override_sources,
    package_bucket_display_text,
    row_display_label,
)
from sc4pimx.DependencyCatalog import CatalogLookupResult


class FakeCatalogClient:
    def __init__(self, tgi_result, iid_result):
        self.tgi_result = tgi_result
        self.iid_result = iid_result
        self.tgi_requests = []
        self.iid_requests = []

    def search_tgi(self, tgi):
        self.tgi_requests.append(tgi)
        return self.tgi_result

    def search_iid(self, iid):
        self.iid_requests.append(iid)
        return self.iid_result


def test_found_catalog_lookup_uses_exact_tgi_only():
    client = FakeCatalogClient(
        CatalogLookupResult("ok", []),
        CatalogLookupResult("ok", [{"Package": "should-not-use"}]),
    )

    status, matches, reason = lookup_catalog(
        client,
        tgi=(0x6534284A, 0x5AD0E817, 0x12345678),
        iid=0x12345678,
        catalog_category="Model",
        allow_iid_fallback=False,
    )

    assert status == "ok"
    assert matches == []
    assert reason == ""
    assert client.tgi_requests == [(0x6534284A, 0x5AD0E817, 0x12345678)]
    assert client.iid_requests == []


def test_builtin_game_files_are_not_catalog_pending():
    assert is_builtin_game_file(r"C:\Games\SimCity 4\SimCity_1.dat")
    assert is_builtin_game_file("sound.dat")
    assert is_builtin_game_file("SimCityLocale.dat")
    assert is_builtin_game_file("EP1.dat")
    assert not is_builtin_game_file("EP.dat")
    assert is_builtin_game_file("merged.dat")
    assert is_builtin_game_file("cohorts.dat")
    assert not is_builtin_game_file("BSC MEGA Props - SG Vol01.dat")
    assert not is_builtin_game_file("simcity_6.dat")

    status = found_catalog_status(
        "simcity_3.dat",
        (0x6534284A, 0x5AD0E817, 0x12345678),
        catalog_enabled=True,
        catalog_base_url="https://catalog.example",
    )

    assert status == "built_in"


def test_missing_catalog_lookup_falls_back_to_group_filtered_iid_match():
    client = FakeCatalogClient(
        CatalogLookupResult("ok", []),
        CatalogLookupResult("ok", [
            {
                "Package": "wrong-group",
                "TGI": "0x6534284A, 0x00000000, 0x12345678",
                "Category": "Model",
            },
            {
                "Package": "right-group",
                "TGI": "0x6534284A, 0x5AD0E817, 0x12345678",
                "Category": "Model",
            },
        ]),
    )

    status, matches, reason = lookup_catalog(
        client,
        tgi=(0x6534284A, 0x5AD0E817, 0x12345678),
        iid=0x12345678,
        catalog_category="Model",
    )

    assert status == "ok"
    assert reason == "iid_fallback"
    assert [match["Package"] for match in matches] == ["right-group"]


def test_filter_catalog_matches_keeps_uncategorized_fallbacks():
    matches = [
        {"Package": "uncategorized"},
        {"Package": "texture", "Category": "Texture"},
        {"Package": "prop", "Category": "Prop"},
    ]

    filtered = filter_catalog_matches(matches, "Texture")

    assert [match["Package"] for match in filtered] == ["uncategorized", "texture"]


def test_dependency_buckets_group_missing_and_installed_catalog_packages():
    match = {
        "Package": "bsc:mega-props-sg-vol01",
        "FileName": "BSC MEGA Props - SG Vol01.dat",
        "Websites": "https://example.test/sg",
        "TGI": "0x6534284A, 0x5AD0E817, 0x12345678",
    }
    rows = [
        DependencyRow(
            id=1,
            status="found",
            kind="Prop",
            name="SG Prop",
            key="0x6534284A-0x5AD0E817-0x12345678",
            source="BSC MEGA Props - SG Vol01.dat",
            referenced_by="Props: SG Prop",
            catalog_status="checked",
            catalog_matches=[match],
            catalog_match_reason="exact_tgi",
        ),
        DependencyRow(
            id=2,
            status="missing",
            kind="Model",
            name="",
            key="0x6534284A-0x5AD0E817-0x12345678",
            source="not found",
            referenced_by="Props: SG Prop",
            catalog_status="checked",
            catalog_matches=[match],
            catalog_match_reason="iid_fallback",
        ),
    ]

    buckets = dependency_package_buckets(rows)

    bucket = buckets["bsc:mega-props-sg-vol01"]
    assert bucket["found_count"] == 1
    assert bucket["missing_count"] == 1
    assert package_bucket_display_text(bucket) == "bsc:mega-props-sg-vol01\nBSC MEGA Props - SG Vol01.dat"


def test_known_missing_maxis_sound_is_ignored():
    assert is_ignored_sound_iid(0x8A8B7DD1)
    assert is_ignored_sound_iid("0x8A8B7DD1")
    assert not is_ignored_sound_iid(0x8A8B7DD2)


def test_placeholder_ltext_key_is_skipped():
    assert is_placeholder_ltext_key((0, 0, 0))
    assert not is_placeholder_ltext_key((0x2026960B, 0, 0))
    assert not is_placeholder_ltext_key(None)


def test_catalog_lookup_can_be_disabled_for_specific_tgis():
    row = DependencyRow(
        id=1,
        status="missing",
        kind="Model",
        name="",
        key="0x6534284A-0x5AD0E817-0x12345678",
        source="not found",
        referenced_by="Props: Known Prop",
        tgi=(0x6534284A, 0x5AD0E817, 0x12345678),
        catalog_lookup=False,
    )

    assert identification_catalog_status(row, True, "https://catalog.example") == "not_applicable"


def test_dependency_label_uses_typed_id_when_name_is_unknown_or_generic():
    prop_row = DependencyRow(
        id=1,
        status="missing",
        kind="Prop",
        name="",
        key="0x12345678",
        source="not found",
        referenced_by="Props",
        catalog_name="Prop",
    )
    texture_row = DependencyRow(
        id=2,
        status="missing",
        kind="Texture",
        name="Texture",
        key="0x7AB50E44",
        source="not found",
        referenced_by="Textures",
    )
    model_row = DependencyRow(
        id=3,
        status="missing",
        kind="Model",
        name="",
        key="0x6534284A-0x5AD0E817-0x89ABCDEF",
        source="not found",
        referenced_by="Props: Known Prop",
    )
    named_prop_row = DependencyRow(
        id=4,
        status="found",
        kind="Prop",
        name="Prop: Fire Occupant",
        key="0x87654321",
        source="plugin.dat",
        referenced_by="Props",
    )

    assert row_display_label(prop_row) == "Props: 0x12345678"
    assert row_display_label(texture_row) == "Textures: 0x7AB50E44"
    assert row_display_label(model_row) == "Models: 0x6534284A-0x5AD0E817-0x89ABCDEF"
    assert row_display_label(named_prop_row) == "Prop: Fire Occupant"


def test_catalog_status_accepts_a_local_database_without_a_base_url():
    row = DependencyRow(
        id=1,
        status="missing",
        kind="Prop",
        name="",
        key="0x12345678",
        source="not found",
        referenced_by="Props",
        iid=0x12345678,
    )

    assert identification_catalog_status(row, True, "", catalog_local=True) == "pending"
    assert identification_catalog_status(row, True, "", catalog_local=False) == "disabled"
    assert found_catalog_status("plugin.dat", (1, 2, 3), True, "", catalog_local=True) == "pending"
    assert found_catalog_status("plugin.dat", (1, 2, 3), True, "", catalog_local=False) == "disabled"
    # A built-in game file is still never looked up.
    assert found_catalog_status("simcity_1.dat", (1, 2, 3), True, "", catalog_local=True) == "built_in"


def _found(row_id, source, candidates, matches=None):
    return DependencyRow(
        id=row_id,
        status="found",
        kind="Prop",
        name="",
        key="0x%08X" % row_id,
        source=source,
        referenced_by="Props",
        candidates=list(candidates),
        catalog_matches=list(matches or []),
    )


def test_override_is_credited_to_the_file_the_lot_already_needs():
    jes = "BSC MEGA Props - JES Vol01 v2.dat"
    misc = "BSC MEGA Props - MISC Vol02 v4.dat"
    # The model only ships in JES Vol01; the props ship in both and currently
    # get credited to MISC Vol02 purely because it loads later.
    model = _found(1, jes, [jes])
    prop_a = _found(2, misc, [jes, misc])
    prop_b = _found(3, misc, [jes, misc])

    required = minimize_override_sources([model, prop_a, prop_b])

    assert prop_a.source == jes
    assert prop_b.source == jes
    assert required == {jes}


def test_ambiguous_rows_settle_on_one_shared_file():
    peg = "PEG-SUPER-TEXTURES.dat"
    bsc = "BSC Textures Vol01.dat"
    rows = [_found(1, bsc, [peg, bsc]), _found(2, bsc, [peg, bsc])]

    required = minimize_override_sources(rows)

    assert required == {peg}
    assert [row.source for row in rows] == [peg, peg]


def test_single_candidate_rows_keep_their_own_file():
    rows = [_found(1, "a.dat", ["a.dat"]), _found(2, "b.dat", ["b.dat"])]

    assert minimize_override_sources(rows) == {"a.dat", "b.dat"}
    assert [row.source for row in rows] == ["a.dat", "b.dat"]


def test_catalog_packages_prefer_the_local_file_then_the_shared_package():
    pinned = _found(1, "vol01.dat", ["vol01.dat"], [
        {"Package": "misc-vol02", "FileName": "vol02.dat"},
        {"Package": "jes-vol01", "FileName": "vol01.dat"},
    ])
    ambiguous = _found(2, "shared.dat", ["shared.dat"], [
        {"Package": "misc-vol02", "FileName": "vol02.dat"},
        {"Package": "jes-vol01", "FileName": "other.dat"},
    ])

    minimize_catalog_packages([pinned, ambiguous])

    assert pinned.catalog_matches[0]["Package"] == "jes-vol01"
    assert ambiguous.catalog_matches[0]["Package"] == "jes-vol01"


def test_minimize_choices_leaves_rows_without_candidates_alone():
    chosen, required = minimize_choices([[], ["only.dat"]])

    assert chosen == ["", "only.dat"]
    assert required == {"only.dat"}


def test_details_panel_copies_as_plain_text():
    row = _found(1, "vol01.dat", ["vol01.dat", "vol02.dat"], [
        {"Package": "jes-vol01", "FileName": "vol01.dat", "Websites": "https://example.org/x"},
    ])

    text = dependency_plain_text(["b.dat", "A.dat"], [row], selected=row)

    assert text.splitlines() == [
        "# Loaded files providing Props: 0x00000001",
        "vol01.dat (listed as the dependency)",
        "vol02.dat",
        "",
        "# Files contributing to this lot",
        "A.dat",
        "b.dat",
        "",
        "# Packages to list",
        "jes-vol01 - vol01.dat - https://example.org/x",
    ]


def test_plain_text_is_empty_without_content():
    assert dependency_plain_text([], []) == ""


def test_bundled_cohorts_file_is_never_a_dependency():
    assert is_tool_asset_file(r"C:\Program Files\SC4PIM\assets\dbpf\cohorts.dat")
    assert is_tool_asset_file("Cohorts.dat")
    assert not is_tool_asset_file("simcity_1.dat")
    assert not is_tool_asset_file("BSC MEGA Props - JES Vol01 v2.dat")


def test_maxis_files_beat_a_plugin_that_overrides_them():
    plugin = "Some Plugin.dat"
    # The plugin is pinned by a row it alone provides, so without an explicit
    # rule the shared texture would follow it instead of staying vanilla.
    pinned = _found(1, plugin, [plugin])
    overridden = _found(2, plugin, ["simcity_1.dat", plugin])

    required = minimize_override_sources([pinned, overridden])

    assert overridden.source == "simcity_1.dat"
    assert required == {plugin}
