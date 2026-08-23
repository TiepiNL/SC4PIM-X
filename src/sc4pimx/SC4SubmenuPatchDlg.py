"""Shared submenu-assignment dialog for direct exemplar edits and patch cohorts."""

from __future__ import annotations

from dataclasses import dataclass
import os
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
MODE_EXEMPLAR = "exemplar"
MODE_PATCH = "patch"


@dataclass(frozen=True)
class PatchTarget:
    kind: str  # "building" or "flora"
    exemplar: object
    name: str

    @property
    def tgi(self):
        return tuple(self.exemplar.entry.tgi)


@dataclass(frozen=True)
class SubmenuAssignmentResult:
    targets: list
    parent_id: int
    mode: str
    create_backups: bool = False


# Compatibility for callers/tests that imported the old result name.
SubmenuPatchResult = SubmenuAssignmentResult


def _search_candidates(virtual_dat, query, limit=_SEARCH_LIMIT, mode=MODE_PATCH):
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
    if mode == MODE_PATCH and len(results) < limit:
        scan(CATEGORY_FLORA, "flora")
    return results[:limit]


class SubmenuAssignmentDialog(wx.Dialog):
    def __init__(self, parent, virtual_dat, seed_target=None, title=None, parent_id=None,
                 mode=MODE_PATCH):
        self.mode = mode
        if mode not in (MODE_EXEMPLAR, MODE_PATCH):
            raise ValueError("Unknown submenu assignment mode: %s" % mode)
        default_title = (LEXSubmenuExemplarBatchDialogTitle if mode == MODE_EXEMPLAR
                         else LEXSubmenuPatchDialogTitle)
        wx.Dialog.__init__(
            self, parent, -1, title or default_title,
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
        self.selectAllButton = wx.Button(self, -1, LEXSubmenuPatchSelectAll)
        search_row.Add(self.selectAllButton, 0, wx.LEFT, 6)
        self.clearAllButton = wx.Button(self, -1, LEXSubmenuPatchClearAll)
        search_row.Add(self.clearAllButton, 0, wx.LEFT, 6)

        self.list = ULC.UltimateListCtrl(
            self, -1,
            agwStyle=ULC.ULC_REPORT | ULC.ULC_HRULES | ULC.ULC_SHOW_TOOLTIPS | ULC.ULC_SINGLE_SEL,
        )
        self.list.InsertColumn(0, LEXSubmenuPatchColSelected, width=76)
        self.list.InsertColumn(1, LEXSubmenuPatchColKind, width=90)
        self.list.InsertColumn(2, LEXSubmenuPatchColName, width=230)
        self.list.InsertColumn(3, LEXSubmenuAssignmentColPackage, width=230)
        self.list.InsertColumn(4, LEXSubmenuPatchColStatus, width=150)
        self.list.SetMinSize((820, 260))
        self._mono = _monospace_font(self.list.GetFont())

        parent_row = wx.BoxSizer(wx.HORIZONTAL)
        parent_row.Add(wx.StaticText(self, label=LEXNewSubmenuParentLabel), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        self.parentCombo = ParentMenuCombo(self, virtual_dat, selected=parent_id)
        parent_row.Add(self.parentCombo, 1, wx.EXPAND)

        self.parentInfo = wx.StaticText(self, -1, "", style=wx.ST_ELLIPSIZE_END)
        self.backupCheck = None
        if mode == MODE_EXEMPLAR:
            self.backupCheck = wx.CheckBox(self, -1, LEXSubmenuExemplarCreateBackups)
            self.backupCheck.SetValue(True)

        buttons = wx.StdDialogButtonSizer()
        ok_button = dialog_button(self, wx.ID_OK)
        ok_button.SetLabel(LEXSubmenuExemplarUpdateButton if mode == MODE_EXEMPLAR
                           else LEXSubmenuPatchCreateButton)
        ok_button.SetDefault()
        cancel_button = dialog_button(self, wx.ID_CANCEL)
        buttons.AddButton(ok_button)
        buttons.AddButton(cancel_button)
        buttons.Realize()
        ok_button.Bind(wx.EVT_BUTTON, self._on_ok)

        root = wx.BoxSizer(wx.VERTICAL)
        help_label = LEXSubmenuExemplarBatchHelp if mode == MODE_EXEMPLAR else LEXSubmenuPatchHelp
        help_text = wx.StaticText(self, -1, help_label)
        help_text.Wrap(800)
        root.Add(help_text, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 8)
        root.Add(search_row, 0, wx.EXPAND | wx.ALL, 8)
        root.Add(self.list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
        root.Add(parent_row, 0, wx.EXPAND | wx.ALL, 8)
        root.Add(self.parentInfo, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        if self.backupCheck is not None:
            root.Add(self.backupCheck, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        root.Add(buttons, 0, wx.EXPAND | wx.ALL, 8)
        self.SetSizerAndFit(root)
        self.SetMinSize((860, 500))
        self.CentreOnParent()

        self.searchButton.Bind(wx.EVT_BUTTON, self._on_search)
        self.searchCtrl.Bind(wx.EVT_TEXT_ENTER, self._on_search)
        self.selectAllButton.Bind(wx.EVT_BUTTON, lambda e: self._set_all_checked(True))
        self.clearAllButton.Bind(wx.EVT_BUTTON, lambda e: self._set_all_checked(False))
        self.parentCombo.Bind(wx.EVT_COMBOBOX, self._on_parent_changed)
        self.parentCombo.Bind(wx.EVT_TEXT, self._on_parent_changed)
        self.list.Bind(ULC.EVT_LIST_ITEM_CHECKED, self._on_item_checked)

        if seed_target is not None:
            self._add_target(seed_target, checked=True)
        self._on_parent_changed(None)

    # -- current menu contents ---------------------------------------------

    def _current_member_sources(self):
        parent_id = self.parentCombo.GetMenuId()
        if parent_id is None:
            return {}
        sources = {}
        for member in menu_members(self.virtual_dat).get(parent_id, ()):
            sources.setdefault(member.tgi, set()).add(member.via)
        return sources

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
        found = _search_candidates(self.virtual_dat, query, mode=self.mode)
        for target in found:
            self._add_target(target)
        self._refresh()
        if query and not found:
            self.parentInfo.SetLabel(LEXSubmenuPatchNoMatches % query)
        event.Skip()

    def _refresh(self):
        existing = self._current_member_sources()
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
                self.list.SetStringItem(idx, 3, os.path.basename(target.exemplar.entry.fileName or ""))
                sources = existing.get(target.tgi, set())
                direct = "exemplar" in sources
                patch = "patch" in sources
                if direct and patch:
                    status = LEXSubmenuStatusAssignedBoth
                elif direct:
                    status = LEXSubmenuStatusAssignedExemplar
                elif patch:
                    status = LEXSubmenuStatusAssignedPatch
                else:
                    status = ""
                if self.mode == MODE_EXEMPLAR:
                    path = target.exemplar.entry.fileName
                    if not path or not os.path.isfile(path) or not os.access(path, os.W_OK):
                        status = LEXSubmenuStatusCannotModify
                self.list.SetStringItem(idx, 4, status)
                item = ULC.CreateListItem(idx, 0)
                item = self.list._mainWin.GetItem(item, 0)
                self.list._mainWin.CheckItem(item, target.tgi in self._checked)
        finally:
            self.list.Thaw()

    def _set_all_checked(self, checked):
        if checked:
            self._checked.update(t.tgi for t in self._order)
        else:
            self._checked.clear()
        self._refresh()

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
        existing = self._current_member_sources()
        selected = [t for t in self._targets.values() if t.tgi in self._checked]
        if self.mode == MODE_EXEMPLAR:
            pending = [t for t in selected if "exemplar" not in existing.get(t.tgi, ())]
        else:
            pending = [t for t in selected if t.tgi not in existing]
        if not selected:
            wx.MessageBox(LEXSubmenuPatchNoTargets, LEXSubmenuPatchDialogTitle, wx.OK | wx.ICON_ERROR, self)
            return
        if not pending:
            wx.MessageBox(LEXSubmenuPatchAllPresent, LEXSubmenuPatchDialogTitle,
                          wx.OK | wx.ICON_INFORMATION, self)
            return
        self._result = SubmenuAssignmentResult(
            targets=pending,
            parent_id=parent_id,
            mode=self.mode,
            create_backups=bool(self.backupCheck and self.backupCheck.GetValue()),
        )
        self.EndModal(wx.ID_OK)

    def GetResult(self) -> Optional[SubmenuAssignmentResult]:
        return getattr(self, "_result", None)


SubmenuPatchDialog = SubmenuAssignmentDialog


def open_submenu_assignment_dialog(parent, virtual_dat, seed_target=None, title=None,
                                   parent_id=None, mode=MODE_PATCH):
    dlg = SubmenuAssignmentDialog(parent, virtual_dat, seed_target=seed_target, title=title,
                                  parent_id=parent_id, mode=mode)
    try:
        _centre_on_top_level(dlg, parent)
        if dlg.ShowModal() == wx.ID_OK:
            return dlg.GetResult()
        return None
    finally:
        dlg.Destroy()


def open_submenu_patch_dialog(parent, virtual_dat, seed_target=None, title=None, parent_id=None):
    return open_submenu_assignment_dialog(
        parent, virtual_dat, seed_target=seed_target, title=title,
        parent_id=parent_id, mode=MODE_PATCH,
    )
