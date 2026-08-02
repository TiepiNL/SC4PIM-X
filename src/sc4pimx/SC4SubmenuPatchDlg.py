"""Add-to-Submenu-via-patch dialog: assigns existing Building/Flora exemplars
to a submenu through a standalone Cohort patch instead of editing them.

Presentation-only, same split as SC4NewSubmenuDlg / SC4BuildingSubmenuPicker:
this module returns a :class:`SubmenuPatchResult`; ``SC4PIMApp.OnPatchIntoSubmenu``
builds and writes the actual Cohort entries.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import wx
import wx.lib.agw.ultimatelistctrl as ULC

from .SC4MenuScanner import (
    CATEGORY_BUILDING,
    CATEGORY_FLORA,
    menu_entries,
    menu_members,
    menu_path,
)
from .SC4OccupantGroupPicker import _centre_on_top_level, _monospace_font
from .SC4SubmenuWidgets import ParentMenuCombo
from .TablerIcons import dialog_button, set_button_icon
from .translation import *  # noqa: F401,F403

_SEARCH_LIMIT = 200


@dataclass(frozen=True)
class PatchTarget:
    kind: str  # "building" or "flora"
    exemplar: object
    name: str

    @property
    def tgi(self):
        return tuple(self.exemplar.entry.tgi)


@dataclass(frozen=True)
class SubmenuPatchResult:
    targets: list
    parent_id: int


def _search_candidates(virtual_dat, query, limit=_SEARCH_LIMIT):
    query = query.strip().lower()
    if not query:
        return []
    results = []

    def scan(category_id, kind):
        category = virtual_dat.categories.get(category_id)
        if category is None:
            return
        for desc in category.descriptors:
            if query in desc.name.lower():
                results.append(PatchTarget(kind, desc.exemplar, desc.name))
                if len(results) >= limit:
                    return

    scan(CATEGORY_BUILDING, "building")
    if len(results) < limit:
        scan(CATEGORY_FLORA, "flora")
    return results[:limit]


class SubmenuPatchDialog(wx.Dialog):
    def __init__(self, parent, virtual_dat, seed_target=None, title=None, parent_id=None):
        wx.Dialog.__init__(
            self, parent, -1, title or LEXSubmenuPatchDialogTitle,
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self.virtual_dat = virtual_dat
        self._targets = {}  # tgi -> PatchTarget
        self._checked = set()  # tgis
        self._order = []

        search_row = wx.BoxSizer(wx.HORIZONTAL)
        self.searchCtrl = wx.SearchCtrl(self, -1, style=wx.TE_PROCESS_ENTER)
        self.searchCtrl.SetDescriptiveText(LEXSubmenuPatchSearchHint)
        search_row.Add(self.searchCtrl, 1, wx.RIGHT | wx.EXPAND, 6)
        self.searchButton = wx.Button(self, -1, LEXSubmenuPatchSearch)
        set_button_icon(self.searchButton, "zoom-in")
        search_row.Add(self.searchButton, 0)

        self.list = ULC.UltimateListCtrl(
            self, -1,
            agwStyle=ULC.ULC_REPORT | ULC.ULC_HRULES | ULC.ULC_SHOW_TOOLTIPS | ULC.ULC_SINGLE_SEL,
        )
        self.list.InsertColumn(0, LEXSubmenuPatchColSelected, width=76)
        self.list.InsertColumn(1, LEXSubmenuPatchColKind, width=90)
        self.list.InsertColumn(2, LEXSubmenuPatchColName, width=280)
        self.list.InsertColumn(3, LEXSubmenuPatchColStatus, width=140)
        self.list.SetMinSize((640, 260))
        self._mono = _monospace_font(self.list.GetFont())

        parent_row = wx.BoxSizer(wx.HORIZONTAL)
        parent_row.Add(wx.StaticText(self, label=LEXNewSubmenuParentLabel), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        self.parentCombo = ParentMenuCombo(self, virtual_dat, selected=parent_id)
        parent_row.Add(self.parentCombo, 1, wx.EXPAND)

        self.parentInfo = wx.StaticText(self, -1, "", style=wx.ST_ELLIPSIZE_END)

        buttons = wx.StdDialogButtonSizer()
        ok_button = dialog_button(self, wx.ID_OK)
        ok_button.SetDefault()
        cancel_button = dialog_button(self, wx.ID_CANCEL)
        buttons.AddButton(ok_button)
        buttons.AddButton(cancel_button)
        buttons.Realize()
        ok_button.Bind(wx.EVT_BUTTON, self._on_ok)

        root = wx.BoxSizer(wx.VERTICAL)
        root.Add(search_row, 0, wx.EXPAND | wx.ALL, 8)
        root.Add(self.list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
        root.Add(parent_row, 0, wx.EXPAND | wx.ALL, 8)
        root.Add(self.parentInfo, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        root.Add(buttons, 0, wx.EXPAND | wx.ALL, 8)
        self.SetSizerAndFit(root)
        self.SetMinSize((680, 460))
        self.CentreOnParent()

        self.searchButton.Bind(wx.EVT_BUTTON, self._on_search)
        self.searchCtrl.Bind(wx.EVT_TEXT_ENTER, self._on_search)
        self.parentCombo.Bind(wx.EVT_COMBOBOX, self._on_parent_changed)
        self.parentCombo.Bind(wx.EVT_TEXT, self._on_parent_changed)
        self.list.Bind(ULC.EVT_LIST_ITEM_CHECKED, self._on_item_checked)

        if seed_target is not None:
            self._add_target(seed_target, checked=True)
        self._on_parent_changed(None)

    # -- current menu contents ---------------------------------------------

    def _current_member_tgis(self):
        """TGIs already in the selected menu, so we neither duplicate nor hide them."""
        parent_id = self.parentCombo.GetMenuId()
        if parent_id is None:
            return set()
        return {member.tgi for member in menu_members(self.virtual_dat).get(parent_id, ())}

    def _on_parent_changed(self, event):
        parent_id = self.parentCombo.GetMenuId()
        if parent_id is None:
            self.parentInfo.SetLabel(LEXNewSubmenuInvalidParent)
        else:
            entries = menu_entries(self.virtual_dat)
            count = len(menu_members(self.virtual_dat).get(parent_id, ()))
            self.parentInfo.SetLabel(LEXSubmenuPatchParentInfo % (
                menu_path(entries, parent_id), count,
            ))
        self._refresh()
        if event is not None:
            event.Skip()

    # -- candidate list -----------------------------------------------------

    def _add_target(self, target: PatchTarget, checked=False):
        self._targets[target.tgi] = target
        if checked:
            self._checked.add(target.tgi)

    def _on_search(self, event):
        query = self.searchCtrl.GetValue().strip()
        found = _search_candidates(self.virtual_dat, query)
        for target in found:
            self._add_target(target)
        self._refresh()
        if query and not found:
            self.parentInfo.SetLabel(LEXSubmenuPatchNoMatches % query)
        event.Skip()

    def _refresh(self):
        existing = self._current_member_tgis()
        self.list.Freeze()
        try:
            self.list.DeleteAllItems()
            self._order = sorted(self._targets.values(), key=lambda t: (t.kind, t.name.lower()))
            for idx, target in enumerate(self._order):
                info = ULC.UltimateListItem()
                info._itemId = idx
                info._mask = ULC.ULC_MASK_TEXT | ULC.ULC_MASK_KIND
                info._text = ""
                info._kind = 1
                self.list._mainWin.InsertItem(info)
                self.list.SetStringItem(idx, 1, target.kind.title())
                self.list.SetStringItem(idx, 2, target.name)
                self.list.SetStringItem(
                    idx, 3, LEXSubmenuPatchStatusPresent if target.tgi in existing else "")
                item = ULC.CreateListItem(idx, 0)
                item = self.list._mainWin.GetItem(item, 0)
                self.list._mainWin.CheckItem(item, target.tgi in self._checked)
        finally:
            self.list.Thaw()

    def _on_item_checked(self, event):
        idx = event.GetIndex()
        if 0 <= idx < len(self._order):
            target = self._order[idx]
            if self.list.IsItemChecked(idx):
                self._checked.add(target.tgi)
            else:
                self._checked.discard(target.tgi)
        event.Skip()

    # -- commit -------------------------------------------------------------

    def _on_ok(self, event):
        parent_id = self.parentCombo.GetMenuId()
        if parent_id is None:
            wx.MessageBox(LEXNewSubmenuInvalidParent, LEXSubmenuPatchDialogTitle, wx.OK | wx.ICON_ERROR, self)
            return
        existing = self._current_member_tgis()
        selected = [t for t in self._targets.values() if t.tgi in self._checked]
        pending = [t for t in selected if t.tgi not in existing]
        if not selected:
            wx.MessageBox(LEXSubmenuPatchNoTargets, LEXSubmenuPatchDialogTitle, wx.OK | wx.ICON_ERROR, self)
            return
        if not pending:
            wx.MessageBox(LEXSubmenuPatchAllPresent, LEXSubmenuPatchDialogTitle,
                          wx.OK | wx.ICON_INFORMATION, self)
            return
        self._result = SubmenuPatchResult(targets=pending, parent_id=parent_id)
        self.EndModal(wx.ID_OK)

    def GetResult(self) -> Optional[SubmenuPatchResult]:
        return getattr(self, "_result", None)


def open_submenu_patch_dialog(parent, virtual_dat, seed_target=None, title=None, parent_id=None):
    dlg = SubmenuPatchDialog(parent, virtual_dat, seed_target=seed_target, title=title,
                             parent_id=parent_id)
    try:
        _centre_on_top_level(dlg, parent)
        if dlg.ShowModal() == wx.ID_OK:
            return dlg.GetResult()
        return None
    finally:
        dlg.Destroy()
