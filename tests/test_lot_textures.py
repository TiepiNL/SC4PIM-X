from types import SimpleNamespace

import pytest

import sc4pimx.LotTextures as lot_textures
from sc4pimx.LotTextures import (
    LOT_TEXTURE_GROUP,
    LOT_TEXTURE_TYPE,
    PREVIEW_ZOOM,
    load_lot_texture,
    lot_texture_is_overlay,
)
from sc4pimx.SC4LotPreview import LotEditorWin

TEX_ID = 0xF89049B0
OPAQUE = b"opaque"
ALPHA = b"alpha"


class FakeEntry:
    fileName = "textures.dat"

    def __init__(self, iid, content):
        self.tgi = (LOT_TEXTURE_TYPE, LOT_TEXTURE_GROUP, iid)
        self.content = content
        self.rawContent = content


def fake_dat(zooms):
    """``zooms`` maps zoom level -> OPAQUE/ALPHA; absent levels are missing."""
    entries = {
        (LOT_TEXTURE_TYPE, LOT_TEXTURE_GROUP, TEX_ID + z): FakeEntry(TEX_ID + z, c)
        for z, c in zooms.items()
    }
    return SimpleNamespace(getEntry=lambda t, g, i: entries.get((t, g, i)))


@pytest.fixture
def decoded(monkeypatch):
    calls = []

    def decode(content):
        calls.append(content)
        size = (2, 2)
        alpha = bytes([255, 255, 255, 200 if content == ALPHA else 255])
        return 1, content == ALPHA, bytes(12), alpha, size

    monkeypatch.setattr(lot_textures.FSHConverter, "decodeFSH", decode)
    return calls


def test_alpha_at_a_later_zoom_makes_the_whole_texture_an_overlay(decoded):
    dat = fake_dat({0: OPAQUE, 1: ALPHA, 2: ALPHA, 3: ALPHA, 4: ALPHA})

    texture = load_lot_texture(dat, TEX_ID)

    assert texture.is_overlay is True
    assert len(texture.zooms) == 5


def test_opaque_at_every_zoom_is_a_base(decoded):
    dat = fake_dat({z: OPAQUE for z in range(5)})

    assert load_lot_texture(dat, TEX_ID).is_overlay is False
    assert lot_texture_is_overlay(dat, TEX_ID) is False


def test_overlay_check_stops_at_first_zoom_with_alpha_and_is_cached(decoded):
    dat = fake_dat({0: OPAQUE, 1: ALPHA, 2: OPAQUE, 3: OPAQUE, 4: OPAQUE})

    assert lot_texture_is_overlay(dat, TEX_ID) is True
    assert decoded == [OPAQUE, ALPHA]
    assert lot_texture_is_overlay(dat, TEX_ID) is True
    assert len(decoded) == 2


def test_editor_builds_every_zoom_as_rgba_for_mixed_alpha_texture(decoded):
    dat = fake_dat({0: OPAQUE, 1: ALPHA, 2: ALPHA, 3: ALPHA, 4: ALPHA})
    editor = SimpleNamespace(
        virtualDAT=dat,
        lotBaseTextures=[],
        lotOverTextures=[],
        Img2OGL=lambda im, alpha: (im.mode, alpha),
    )

    bBase, textures = LotEditorWin.GetTextures(editor, TEX_ID)

    assert bBase is False
    assert textures == [("RGBA", True)] * 5
    assert editor.lotOverTextures == [TEX_ID + PREVIEW_ZOOM]
    assert editor.lotBaseTextures == []
    # The asset picker reuses the editor's decision.
    assert lot_texture_is_overlay(dat, TEX_ID) is True


def test_missing_zoom_uses_closest_lower_zoom(decoded):
    dat = fake_dat({0: OPAQUE, 1: OPAQUE, 2: ALPHA, 4: OPAQUE})

    texture = load_lot_texture(dat, TEX_ID)

    assert texture.substitutes == {3: 2}
    assert texture.zooms[3] is texture.zooms[2]
    assert texture.is_overlay is True


def test_missing_lowest_zoom_uses_closest_higher_zoom(decoded):
    dat = fake_dat({2: OPAQUE, 3: OPAQUE, 4: OPAQUE})

    texture = load_lot_texture(dat, TEX_ID)

    assert texture.substitutes == {0: 2, 1: 2}
    assert texture.zooms[0] is texture.zooms[2]


def test_texture_without_any_zoom_is_missing(decoded):
    assert load_lot_texture(fake_dat({}), TEX_ID) is None


def test_editor_warns_about_stand_in_zooms(decoded, caplog):
    dat = fake_dat({0: OPAQUE, 1: OPAQUE, 2: OPAQUE, 4: OPAQUE})
    editor = SimpleNamespace(
        virtualDAT=dat,
        lotBaseTextures=[],
        lotOverTextures=[],
        Img2OGL=lambda im, alpha: (im.mode, alpha),
    )

    bBase, textures = LotEditorWin.GetTextures(editor, TEX_ID)

    assert bBase is True
    assert len(textures) == 5
    assert "0xF89049B0 is missing zoom level(s) 4; using 3 instead" in caplog.text


def test_object_that_fails_to_cache_is_not_added_to_the_lot(monkeypatch):
    import sc4pimx.SC4LotPreview as lot_preview

    added = []

    def fail(values):
        raise AttributeError("'bool' object has no attribute 'split'")

    editor = SimpleNamespace(
        exemplar=SimpleNamespace(
            GetProp=lambda prop_id: [2, 2] if prop_id == 0x88EDC790 else None,
            AddTextProp=added.append,
        ),
        virtualDAT=SimpleNamespace(properties={0x88EDC900: "prop"}),
        _push_undo=lambda: None,
        PreCacheObject=fail,
    )
    monkeypatch.setattr(lot_preview, "CreateAProp", lambda prop, values: values)

    with pytest.raises(AttributeError):
        LotEditorWin.PlaceConstraint(editor, 0, 0, 5)

    assert added == []
