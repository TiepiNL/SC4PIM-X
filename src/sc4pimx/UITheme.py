"""Small appearance helpers for application-owned wx controls.

Native controls should normally keep their default colours so wxWidgets can
theme them. These helpers are for SVG art and owner-drawn surfaces which do
not receive native appearance colours automatically.
"""

from __future__ import annotations

import wx

from . import config

APPEARANCE_MODES = ("system", "light", "dark")
_appearance_mode_cache: str | None = None
_dark_state_cache: tuple[str, bool] | None = None


def appearance_mode() -> str:
    """Return the configured appearance override, or 'system' if unset/invalid."""
    global _appearance_mode_cache
    if _appearance_mode_cache is None:
        mode = str(config.load_settings().get("Appearance", "system")).lower()
        _appearance_mode_cache = mode if mode in APPEARANCE_MODES else "system"
    return _appearance_mode_cache


def reset_appearance_cache() -> None:
    """Clear cached appearance state, primarily for tests and app reinitialization."""
    global _appearance_mode_cache, _dark_state_cache
    _appearance_mode_cache = None
    _dark_state_cache = None


def is_dark() -> bool:
    """Return whether the app should currently render with a dark appearance.

    Honours a user-configured override before falling back to the OS setting.
    """
    global _dark_state_cache
    mode = appearance_mode()
    if _dark_state_cache is not None and _dark_state_cache[0] == mode:
        return _dark_state_cache[1]
    if mode == "dark":
        result = True
    elif mode == "light":
        result = False
    else:
        result = bool(wx.SystemSettings.GetAppearance().IsDark())
    _dark_state_cache = (mode, result)
    return result


def select(light: tuple[int, int, int], dark: tuple[int, int, int]) -> wx.Colour:
    """Create an appearance-appropriate colour from light and dark RGB values."""
    return wx.Colour(*(dark if is_dark() else light))


def as_html(colour: wx.Colour) -> str:
    """Return a wx colour as an SVG/HTML ``#RRGGBB`` value."""
    return "#%02X%02X%02X" % (colour.Red(), colour.Green(), colour.Blue())


def icon_colour() -> str:
    """Return the current native button-text colour for monochrome UI icons."""
    return as_html(wx.SystemSettings.GetColour(wx.SYS_COLOUR_BTNTEXT))


def asset_card_colours(selected: bool) -> tuple[wx.Colour, wx.Colour, wx.Colour]:
    """Return background, border and text colours for an asset-browser card."""
    if selected:
        return (
            wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHT),
            wx.SystemSettings.GetColour(wx.SYS_COLOUR_HOTLIGHT),
            wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHTTEXT),
        )
    return (
        wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW),
        select((209, 214, 219), (75, 80, 86)),
        wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT),
    )


def alternating_list_colours() -> tuple[wx.Colour, wx.Colour]:
    """Return the two tinted backgrounds used by virtual exemplar lists."""
    return (
        select((255, 228, 181), (57, 49, 36)),
        select((173, 216, 230), (32, 48, 54)),
    )


def property_table_colours() -> dict[str, wx.Colour]:
    """Return semantic row colours for the exemplar property table.

    The light colours preserve the established SC4PIM palette. Dark variants
    are deliberately muted so the native light text remains legible.
    """
    return {
        "metadata": select((205, 190, 112), (70, 63, 31)),
        "invalid": select((200, 99, 71), (105, 46, 38)),
        "family_header": select((160, 190, 220), (40, 64, 86)),
        "family_value": select((213, 239, 255), (32, 53, 68)),
        "inherited_header": select((190, 190, 190), (67, 70, 74)),
        "inherited_value": select((255, 239, 213), (68, 56, 42)),
        "ltext_header": select((113, 255, 139), (31, 91, 49)),
        "ltext_value": select((213, 255, 239), (32, 72, 55)),
    }
