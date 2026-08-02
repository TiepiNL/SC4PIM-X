"""Shared wx bits for the submenu features.

The parent-menu dropdown appears in the New Submenu dialog, the Add-to-Submenu
patch dialog and the tree viewer, and all three used to build their own combo
plus their own "parse whatever the user typed" fallback. One widget keeps the
choice list, the ordering and the hand-typed-hex escape hatch identical
everywhere.
"""

from __future__ import annotations

from typing import Optional

import wx

from .SC4MenuScanner import menu_entries, menu_path


def parse_menu_id(raw: str) -> Optional[int]:
    """A button ID out of ``0x1234ABCD`` or ``0x1234ABCD  Some Label``."""
    raw = (raw or "").strip()
    if not raw:
        return None
    head = raw.split()[0]
    if not head.lower().startswith("0x"):
        return None
    try:
        value = int(head, 16)
    except ValueError:
        return None
    if value < 0 or value > 0xFFFFFFFF:
        return None
    return value


class ParentMenuCombo(wx.ComboBox):
    """Editable dropdown of every known submenu, ordered by tree path.

    Editable on purpose: a menu the scanner cannot see (a binary-format button
    exemplar, or one the user has not installed yet) can still be targeted by
    typing its hex button ID.
    """

    def __init__(self, parent, virtual_dat, selected: Optional[int] = None, **kwargs):
        wx.ComboBox.__init__(self, parent, -1, style=wx.CB_DROPDOWN, **kwargs)
        self.virtual_dat = virtual_dat
        self._entries = {}
        self.Reload(selected=selected)

    def Reload(self, selected: Optional[int] = None, force: bool = False) -> None:
        if selected is None:
            selected = self.GetMenuId()
        self._entries = menu_entries(self.virtual_dat, force=force)
        rows = [
            ("0x%08X  %s" % (value, menu_path(self._entries, value)), value)
            for value in self._entries
        ]
        rows.sort(key=lambda row: row[0].split("  ", 1)[-1].lower())
        self.Freeze()
        try:
            self.Clear()
            for label, value in rows:
                self.Append(label, value)
        finally:
            self.Thaw()
        if not self.SetMenuId(selected) and self.GetCount():
            self.SetSelection(0)

    def SetMenuId(self, value: Optional[int]) -> bool:
        if value is None:
            return False
        for index in range(self.GetCount()):
            if self.GetClientData(index) == value:
                self.SetSelection(index)
                return True
        self.SetValue("0x%08X" % (int(value) & 0xFFFFFFFF))
        return True

    def GetMenuId(self) -> Optional[int]:
        raw = self.GetValue().strip()
        selection = self.GetSelection()
        if selection != wx.NOT_FOUND and self.GetString(selection) == raw:
            return int(self.GetClientData(selection))
        return parse_menu_id(raw)
