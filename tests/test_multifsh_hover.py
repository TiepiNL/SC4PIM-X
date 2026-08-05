from types import SimpleNamespace

import sc4pimx.SC4LETools as le_tools
from sc4pimx.SC4LETools import LEAssetGrid, LEAssetItem, LEAssetThumbnailProvider


class DummyTextureEntry:
    fileName = "textures.dat"
    tgi = (2058686020, 159781726, 3)
    content = b"encoded"
    rawContent = b"raw"

    def read_file(self, *_args):
        return None


def test_multifsh_layers_are_cached_and_labelled(monkeypatch):
    entry = DummyTextureEntry()
    monkeypatch.setattr(
        le_tools.FSHConverter,
        "decodeFSH",
        lambda _content: (2, False, bytes((255, 0, 0, 0, 255, 0)), b"", (1, 1)),
    )
    provider = object.__new__(LEAssetThumbnailProvider)
    provider.texture_layers = {}
    provider.texture_layer_counts = {}
    provider.state_strips = {}

    item = LEAssetItem("base texture", "00000000", "textures.dat", None, entry)

    assert provider.TextureLayerCount(item) == 2
    assert provider.IsMultiFSH(item) is True
    assert provider.MultiLabel(item) == "Multi"
    assert entry.content is None
    assert entry.rawContent is None

    monkeypatch.setattr(le_tools, "BitmapFromPIL", lambda image: image)
    strip = provider.StateStrip(item)
    assert strip.size == (192, 96)

    grid = LEAssetGrid.__new__(LEAssetGrid)
    grid.thumbnail_provider = provider
    rows = grid._card_tooltip_rows(item)
    assert ("span", "Multi", True) in rows


def test_single_layer_texture_has_no_multifsh_label(monkeypatch):
    entry = DummyTextureEntry()
    monkeypatch.setattr(
        le_tools.FSHConverter,
        "decodeFSH",
        lambda _content: (1, False, bytes((255, 0, 0)), b"", (1, 1)),
    )
    provider = object.__new__(LEAssetThumbnailProvider)
    provider.texture_layers = {}
    provider.texture_layer_counts = {}
    provider.state_strips = {}
    item = LEAssetItem("overlay texture", "00000000", "textures.dat", None, entry)

    assert provider.IsMultiFSH(item) is False
    assert provider.MultiLabel(item) is None


def test_card_badge_uses_loader_metadata_without_decoding(monkeypatch):
    entry = DummyTextureEntry()
    entry.tgi = (2058686020, 159781726, 0x2003)
    provider = object.__new__(LEAssetThumbnailProvider)
    provider.texture_layers = {}
    provider.texture_layer_counts = {}
    provider.state_strips = {}
    item = LEAssetItem("base texture", "00000000", "textures.dat", None, entry)
    monkeypatch.setattr(
        le_tools.FSHConverter,
        "decodeFSH",
        lambda _content: (_ for _ in ()).throw(AssertionError("card paint decoded FSH")),
    )
    monkeypatch.setattr(
        le_tools.VirtualDat,
        "this",
        SimpleNamespace(textureLayerCounts={entry: 2}),
    )

    assert provider.MultiLabel(item, resolve=False) == "Multi"
    assert provider.TextureWealthLabel(item) == "$$"
