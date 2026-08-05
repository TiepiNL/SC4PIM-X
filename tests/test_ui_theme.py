from types import SimpleNamespace

from sc4pimx import SC4PIMApp, TablerIcons, UITheme


def test_select_uses_dark_variant(monkeypatch):
    monkeypatch.setattr(UITheme, "is_dark", lambda: True)

    colour = UITheme.select((1, 2, 3), (4, 5, 6))

    assert colour.Get()[:3] == (4, 5, 6)


def test_select_uses_light_variant(monkeypatch):
    monkeypatch.setattr(UITheme, "is_dark", lambda: False)

    colour = UITheme.select((1, 2, 3), (4, 5, 6))

    assert colour.Get()[:3] == (1, 2, 3)


def test_icon_colour_uses_native_button_text(monkeypatch):
    monkeypatch.setattr(
        UITheme.wx,
        "SystemSettings",
        SimpleNamespace(GetColour=lambda index: UITheme.wx.Colour(10, 20, 30)),
    )

    assert UITheme.icon_colour() == "#0A141E"


def test_default_tabler_icon_uses_current_appearance_colour(monkeypatch):
    calls = []
    monkeypatch.setattr(TablerIcons, "icon_colour", lambda: "#ABCDEF")
    monkeypatch.setattr(
        TablerIcons,
        "_icon_bundle",
        lambda name, size, colour: calls.append((name, size, colour)) or "bundle",
    )

    assert TablerIcons.icon_bundle("check", 16) == "bundle"
    assert calls == [("check", 16, "#ABCDEF")]


def test_app_enables_system_appearance_before_creating_frame(monkeypatch):
    calls = []
    frame = SimpleNamespace(Show=lambda: calls.append("show"), StartStartup=lambda: None)
    app = SimpleNamespace(
        SetAppearance=lambda appearance: calls.append(("appearance", appearance))
        or SC4PIMApp.wx.App.AppearanceResult.Ok,
        SetTopWindow=lambda value: calls.append(("top", value)),
    )
    monkeypatch.setattr(SC4PIMApp.UITheme, "appearance_mode", lambda: "system")
    monkeypatch.setattr(SC4PIMApp, "MainFrame", lambda: calls.append("frame") or frame)
    monkeypatch.setattr(SC4PIMApp.wx, "CallAfter", lambda callback: calls.append(("after", callback)))

    assert SC4PIMApp.App.OnInit(app) is True
    assert calls[0] == ("appearance", SC4PIMApp.wx.App.Appearance.System)
    assert calls[1] == "frame"


def test_app_enables_dark_appearance_when_overridden(monkeypatch):
    calls = []
    frame = SimpleNamespace(Show=lambda: calls.append("show"), StartStartup=lambda: None)
    app = SimpleNamespace(
        SetAppearance=lambda appearance: calls.append(("appearance", appearance))
        or SC4PIMApp.wx.App.AppearanceResult.Ok,
        SetTopWindow=lambda value: calls.append(("top", value)),
    )
    monkeypatch.setattr(SC4PIMApp.UITheme, "appearance_mode", lambda: "dark")
    monkeypatch.setattr(SC4PIMApp, "MainFrame", lambda: calls.append("frame") or frame)
    monkeypatch.setattr(SC4PIMApp.wx, "CallAfter", lambda callback: calls.append(("after", callback)))

    assert SC4PIMApp.App.OnInit(app) is True
    assert calls[0] == ("appearance", SC4PIMApp.wx.App.Appearance.Dark)


def test_appearance_mode_defaults_to_system(monkeypatch):
    monkeypatch.setattr(UITheme.config, "load_settings", lambda: {})

    assert UITheme.appearance_mode() == "system"


def test_appearance_mode_reads_override(monkeypatch):
    monkeypatch.setattr(UITheme.config, "load_settings", lambda: {"Appearance": "Dark"})

    assert UITheme.appearance_mode() == "dark"


def test_is_dark_honours_light_override(monkeypatch):
    monkeypatch.setattr(UITheme, "appearance_mode", lambda: "light")

    assert UITheme.is_dark() is False


def test_is_dark_honours_dark_override(monkeypatch):
    monkeypatch.setattr(UITheme, "appearance_mode", lambda: "dark")

    assert UITheme.is_dark() is True


def test_property_table_dark_colours_are_muted(monkeypatch):
    monkeypatch.setattr(UITheme, "is_dark", lambda: True)

    colours = UITheme.property_table_colours()

    assert set(colours) == {
        "metadata",
        "invalid",
        "family_header",
        "family_value",
        "inherited_header",
        "inherited_value",
        "ltext_header",
        "ltext_value",
    }
    assert all(colour.GetLuminance() < 0.38 for colour in colours.values())


def test_alternating_list_colours_have_dark_variants(monkeypatch):
    monkeypatch.setattr(UITheme, "is_dark", lambda: True)

    odd, even = UITheme.alternating_list_colours()

    assert odd.Get()[:3] == (57, 49, 36)
    assert even.Get()[:3] == (32, 48, 54)
