"""Submenu Tree: one window that shows the whole Submenus-DLL menu hierarchy.

Read-only browsing plus the actions that belong to a place in the tree --
create a child submenu under the selected menu, patch items into it, or open a
member item's property page. The model lives in :mod:`SC4MenuScanner`; this
module only renders it and forwards the actions the host frame supplies.

Modeless on purpose: the tree is a reference view you keep open next to the
main window while editing, and its actions open their own modal dialogs on top.
"""

from __future__ import annotations

import io
from typing import Callable, Optional

import wx
from PIL import Image

from .SC4MenuScanner import (
    KIND_MENU,
    KIND_ORPHAN,
    KIND_ROOT,
    SOURCE_BUILTIN,
    VIA_PATCH,
    build_menu_tree,
    invalidate_menu_cache,
    menu_entries,
    menu_icon_png,
    menu_members,
    menu_path,
)
from .SC4OccupantGroupPicker import _centre_on_top_level, _monospace_font
from .TablerIcons import icon_bitmap, icon_button, set_button_icon
from .translation import *  # noqa: F401,F403

_TREE_ICON_SIZE = 16


class SubmenuTreeActions:
    """What the host frame lets the tree do, beyond looking at things."""

    def __init__(
        self,
        new_submenu: Optional[Callable[[Optional[int]], None]] = None,
        add_items: Optional[Callable[[Optional[int]], None]] = None,
        open_descriptor: Optional[Callable[[object], None]] = None,
        open_menu: Optional[Callable[[tuple], None]] = None,
        change_icon: Optional[Callable[[object], bool]] = None,
    ):
        self.new_submenu = new_submenu
        self.add_items = add_items
        self.open_descriptor = open_descriptor
        self.open_menu = open_menu
        self.change_icon = change_icon


class SubmenuTreeDialog(wx.Dialog):
    def __init__(self, parent, virtual_dat, actions: Optional[SubmenuTreeActions] = None, title=None):
        wx.Dialog.__init__(
            self, parent, -1, title or LEXSubmenuTreeTitle,
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self.virtual_dat = virtual_dat
        self.actions = actions or SubmenuTreeActions()
        self._entries = {}
        self._members = {}
        # Tearing the tree down deletes its items one by one, and each deletion
        # fires EVT_TREE_SEL_CHANGED at a control whose C++ side is already
        # gone. Nothing selection-related may run once this is set.
        self._closing = False

        top = wx.BoxSizer(wx.HORIZONTAL)
        self.search = wx.SearchCtrl(self, -1, style=wx.TE_PROCESS_ENTER)
        self.search.SetDescriptiveText(LEXSubmenuTreeSearchHint)
        self.search.ShowCancelButton(True)
        top.Add(self.search, 1, wx.EXPAND | wx.RIGHT, 6)
        self.showItems = wx.CheckBox(self, -1, LEXSubmenuTreeShowItems)
        self.showItems.SetValue(True)
        top.Add(self.showItems, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        self.bExpand = icon_button(self, "fold-down", LEXSubmenuTreeExpandAll)
        top.Add(self.bExpand, 0, wx.RIGHT, 2)
        self.bCollapse = icon_button(self, "fold-up", LEXSubmenuTreeCollapseAll)
        top.Add(self.bCollapse, 0, wx.RIGHT, 6)
        self.refreshButton = wx.Button(self, -1, LEXSubmenuTreeRefresh)
        set_button_icon(self.refreshButton, "rotate-clockwise-2")
        top.Add(self.refreshButton, 0)

        self.tree = wx.TreeCtrl(
            self, -1,
            style=wx.TR_HAS_BUTTONS | wx.TR_HIDE_ROOT | wx.TR_LINES_AT_ROOT | wx.TR_ROW_LINES,
        )
        self.tree.SetMinSize((520, 380))

        self.details = wx.StaticText(self, -1, LEXSubmenuTreeDetailNone, style=wx.ST_ELLIPSIZE_END)
        self.details.SetFont(_monospace_font(self.details.GetFont()))
        self.countText = wx.StaticText(self, -1, "")

        actions_row = wx.BoxSizer(wx.HORIZONTAL)
        self.newButton = wx.Button(self, -1, LEXSubmenuTreeNewChild)
        set_button_icon(self.newButton, "plus")
        self.addButton = wx.Button(self, -1, LEXSubmenuTreeAddItems)
        set_button_icon(self.addButton, "list")
        self.iconButton = wx.Button(self, -1, LEXSubmenuIconMenuItem)
        set_button_icon(self.iconButton, "photo")
        self.openButton = wx.Button(self, -1, LEXSubmenuTreeOpenItem)
        set_button_icon(self.openButton, "folder-open")
        self.copyButton = wx.Button(self, -1, LEXSubmenuTreeCopyId)
        set_button_icon(self.copyButton, "copy")
        for button in (self.newButton, self.addButton, self.iconButton, self.openButton, self.copyButton):
            actions_row.Add(button, 0, wx.RIGHT, 6)
        actions_row.AddStretchSpacer(1)
        closeButton = wx.Button(self, wx.ID_CLOSE, LEXSubmenuTreeClose)
        actions_row.Add(closeButton, 0)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(top, 0, wx.EXPAND | wx.ALL, 8)
        sizer.Add(self.tree, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
        sizer.Add(self.countText, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 8)
        sizer.Add(self.details, 0, wx.EXPAND | wx.ALL, 8)
        sizer.Add(actions_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        self.SetSizerAndFit(sizer)
        self.SetMinSize((640, 560))

        self.search.Bind(wx.EVT_TEXT, self._on_filter)
        self.search.Bind(wx.EVT_SEARCHCTRL_CANCEL_BTN, self._on_search_cancel)
        self.showItems.Bind(wx.EVT_CHECKBOX, self._on_filter)
        self.bExpand.Bind(wx.EVT_BUTTON, lambda _evt: self.tree.ExpandAll())
        self.bCollapse.Bind(wx.EVT_BUTTON, self._on_collapse_all)
        self.refreshButton.Bind(wx.EVT_BUTTON, self._on_refresh)
        self.tree.Bind(wx.EVT_TREE_SEL_CHANGED, self._on_selection)
        self.tree.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self._on_activated)
        self.tree.Bind(wx.EVT_TREE_ITEM_RIGHT_CLICK, self._on_right_click)
        self.newButton.Bind(wx.EVT_BUTTON, self._on_new_submenu)
        self.addButton.Bind(wx.EVT_BUTTON, self._on_add_items)
        self.iconButton.Bind(wx.EVT_BUTTON, self._on_change_icon)
        self.openButton.Bind(wx.EVT_BUTTON, self._on_open_item)
        self.copyButton.Bind(wx.EVT_BUTTON, self._on_copy_id)
        closeButton.Bind(wx.EVT_BUTTON, lambda _evt: self.Close())
        self.Bind(wx.EVT_CLOSE, self._on_close)

        self.Reload()

    def _on_close(self, event):
        self._closing = True
        event.Skip()

    # -- data ---------------------------------------------------------------

    def Reload(self, force: bool = False) -> None:
        """Rebuild model and tree. ``force`` rescans the plugins folder."""
        busy = wx.BusyCursor()
        try:
            if force:
                invalidate_menu_cache(self.virtual_dat)
            self._entries = menu_entries(self.virtual_dat, force=force)
            self._members = menu_members(self.virtual_dat, force=force)
            self._load_icons()
        finally:
            del busy
        self._rebuild()

    def _load_icons(self):
        """Tree image list: each submenu's own game icon where one exists.

        Rebuilt only on Reload -- filtering re-inserts items but never changes
        which icon a menu has.
        """
        images = wx.ImageList(_TREE_ICON_SIZE, _TREE_ICON_SIZE)
        self._icon_root = images.Add(icon_bitmap("folder-open", _TREE_ICON_SIZE))
        self._icon_menu = images.Add(icon_bitmap("list", _TREE_ICON_SIZE))
        self._icon_building = images.Add(icon_bitmap("building-community", _TREE_ICON_SIZE))
        self._icon_flora = images.Add(icon_bitmap("trees", _TREE_ICON_SIZE))
        self._menu_icons = {}
        for value, entry in self._entries.items():
            if not entry.tgi:
                continue
            png = menu_icon_png(self.virtual_dat, entry)
            if not png:
                continue
            try:
                with Image.open(io.BytesIO(png)) as source:
                    cell = source.convert("RGB").crop(
                        (0, 0, min(44, source.width), min(44, source.height)))
                    thumb = cell.resize((_TREE_ICON_SIZE, _TREE_ICON_SIZE), Image.LANCZOS)
            except Exception:
                continue
            wx_image = wx.Image(_TREE_ICON_SIZE, _TREE_ICON_SIZE)
            wx_image.SetData(thumb.tobytes())
            self._menu_icons[value] = images.Add(wx_image.ConvertToBitmap())
        self.tree.AssignImageList(images)

    def _matches(self, text: str) -> bool:
        needle = self.search.GetValue().strip().lower()
        if not needle:
            return True
        return needle.replace("0x", "") in text.lower().replace("0x", "")

    def _menu_label(self, entry) -> str:
        count = len(self._members.get(entry.value, ()))
        label = "%s  %s" % (entry.hex, entry.label)
        if count:
            label += "  (%d)" % count
        return label

    def _member_label(self, member) -> str:
        kind = LEXSubmenuTreeKindFlora if member.kind == "flora" else LEXSubmenuTreeKindBuilding
        if member.via == VIA_PATCH:
            kind = "%s, %s" % (kind, LEXSubmenuTreeViaPatch)
        return "%s  [%s]" % (member.name, kind)

    def _rebuild(self) -> None:
        show_items = self.showItems.GetValue()
        searching = bool(self.search.GetValue().strip())
        roots = build_menu_tree(self._entries, ungrouped_label=LEXSubmenuTreeUngrouped,
                                orphan_label=LEXSubmenuTreeOrphan)
        self.tree.Freeze()
        try:
            self.tree.DeleteAllItems()
            root_id = self.tree.AddRoot("")
            self._menu_count = 0
            self._item_count = 0
            for node in roots:
                self._add_node(root_id, node, show_items)
            if not self.tree.GetChildrenCount(root_id, False):
                self.tree.AppendItem(root_id, LEXSubmenuTreeEmpty)
            if searching:
                self.tree.ExpandAll()
            else:
                child, cookie = self.tree.GetFirstChild(root_id)
                while child.IsOk():
                    self.tree.Expand(child)
                    child, cookie = self.tree.GetNextChild(root_id, cookie)
        finally:
            self.tree.Thaw()
        self.countText.SetLabel(LEXSubmenuTreeCount % (self._menu_count, self._item_count))
        self._update_details(None)

    def _add_node(self, parent_id, node, show_items):
        """Insert ``node`` (and its subtree) unless the filter excludes it all."""
        if node.kind == KIND_MENU:
            entry = node.entry
            label = self._menu_label(entry)
            self_match = self._matches("%s %s" % (entry.hex, entry.label))
            image = self._menu_icons.get(entry.value, self._icon_menu)
        else:
            label = node.label
            self_match = self._matches(node.label)
            image = self._icon_root

        members = []
        if show_items and node.kind == KIND_MENU:
            members = [m for m in self._members.get(node.entry.value, ())
                       if self_match or self._matches(m.name)]

        item_id = self.tree.AppendItem(parent_id, label, image)
        self.tree.SetItemData(item_id, (node.kind, node.entry))
        if node.kind == KIND_MENU:
            self._menu_count += 1
        elif node.kind in (KIND_ROOT, KIND_ORPHAN):
            self.tree.SetItemBold(item_id, True)

        kept = 0
        for child in node.children:
            kept += 1 if self._add_node(item_id, child, show_items) else 0
        for member in members:
            member_image = self._icon_flora if member.kind == "flora" else self._icon_building
            member_id = self.tree.AppendItem(item_id, self._member_label(member), member_image)
            self.tree.SetItemData(member_id, ("member", member))
            self._item_count += 1
            kept += 1

        if kept or self_match:
            return True
        self.tree.Delete(item_id)
        if node.kind == KIND_MENU:
            self._menu_count -= 1
        return False

    # -- selection ----------------------------------------------------------

    def _selected_data(self):
        if self._closing:
            return None, None
        # _closing only catches this dialog's own Close()/Destroy() path.
        # On Windows the native tree control can still fire a selection
        # event off a TreeCtrl whose C++ side is already gone (e.g. the
        # owning frame is torn down while this modeless dialog is still
        # open), so the call itself must be guarded too.
        try:
            item = self.tree.GetSelection()
            if not item.IsOk():
                return None, None
            data = self.tree.GetItemData(item)
        except RuntimeError:
            return None, None
        if not data:
            return None, None
        return data

    def _selected_menu_id(self) -> Optional[int]:
        """Button ID to act on: the selected menu, or a selected item's menu."""
        if self._closing:
            return None
        try:
            item = self.tree.GetSelection()
            while item.IsOk():
                data = self.tree.GetItemData(item)
                if data and data[0] == KIND_MENU:
                    return data[1].value
                item = self.tree.GetItemParent(item)
        except RuntimeError:
            return None
        return None

    def _on_selection(self, event):
        if self._closing:
            return
        kind, payload = self._selected_data()
        self._update_details((kind, payload) if kind else None)
        event.Skip()

    def _update_details(self, selection) -> None:
        has_menu = False
        if selection is None:
            self.details.SetLabel(LEXSubmenuTreeDetailNone)
        else:
            kind, payload = selection
            if kind == KIND_MENU:
                has_menu = True
                source = LEXSubmenuTreeSourceBuiltin if payload.source == SOURCE_BUILTIN else (
                    payload.file_name or LEXSubmenuTreeSourceScanned)
                parent = ("0x%08X" % payload.parent_id) if payload.parent_id else "-"
                self.details.SetLabel(LEXSubmenuTreeDetailMenu % (
                    menu_path(self._entries, payload.value), payload.hex, parent,
                    payload.item_order, len(self._members.get(payload.value, ())), source,
                ))
            elif kind == "member":
                self.details.SetLabel(LEXSubmenuTreeDetailItem % (
                    payload.name, "0x%08X, 0x%08X, 0x%08X" % payload.tgi,
                    LEXSubmenuTreeViaPatch if payload.via == VIA_PATCH else LEXSubmenuTreeViaExemplar,
                ))
            else:
                self.details.SetLabel(payload.label if payload is not None else LEXSubmenuTreeDetailNone)
        menu_id = self._selected_menu_id()
        self.newButton.Enable(self.actions.new_submenu is not None)
        self.addButton.Enable(self.actions.add_items is not None and menu_id is not None)
        self.iconButton.Enable(self._icon_editable() is not None)
        self.openButton.Enable(self._openable() is not None)
        self.copyButton.Enable(has_menu)

    def _icon_editable(self):
        """The selected menu, if its icon lives in an editable plugin file."""
        if self.actions.change_icon is None:
            return None
        kind, payload = self._selected_data()
        if kind == KIND_MENU and payload.tgi:
            return payload
        return None

    def _openable(self):
        """What "Open Exemplar" would act on: a member item, or a menu button.

        Curated menus that were not found on disk have no exemplar to open.
        """
        kind, payload = self._selected_data()
        if kind == "member" and payload.descriptor is not None and self.actions.open_descriptor:
            return ("member", payload)
        if kind == KIND_MENU and payload.tgi and self.actions.open_menu:
            return (KIND_MENU, payload)
        return None

    # -- events -------------------------------------------------------------

    def _on_filter(self, event):
        self._rebuild()
        event.Skip()

    def _on_search_cancel(self, event):
        self.search.SetValue("")
        self._rebuild()
        event.Skip()

    def _on_collapse_all(self, event):
        root_id = self.tree.GetRootItem()
        if root_id.IsOk():
            child, cookie = self.tree.GetFirstChild(root_id)
            while child.IsOk():
                self.tree.CollapseAllChildren(child)
                child, cookie = self.tree.GetNextChild(root_id, cookie)
        event.Skip()

    def _on_refresh(self, event):
        self.Reload(force=True)
        event.Skip()

    def _on_activated(self, event):
        kind, _payload = self._selected_data()
        if kind == "member":
            self._on_open_item(event)
        else:
            item = event.GetItem()
            if item.IsOk():
                self.tree.Toggle(item)
        event.Skip()

    def _on_right_click(self, event):
        self.tree.SelectItem(event.GetItem())
        menu = wx.Menu()
        ids = {}
        for label, handler, enabled in (
            (LEXSubmenuTreeNewChild, self._on_new_submenu, self.actions.new_submenu is not None),
            (LEXSubmenuTreeAddItems, self._on_add_items,
             self.actions.add_items is not None and self._selected_menu_id() is not None),
            (LEXSubmenuIconMenuItem, self._on_change_icon, self._icon_editable() is not None),
            (LEXSubmenuTreeOpenItem, self._on_open_item, self.openButton.IsEnabled()),
            (LEXSubmenuTreeCopyId, self._on_copy_id, self.copyButton.IsEnabled()),
        ):
            item_id = wx.NewIdRef()
            item = menu.Append(item_id, label)
            item.Enable(bool(enabled))
            ids[int(item_id)] = handler
            self.Bind(wx.EVT_MENU, handler, id=item_id)
        self.PopupMenu(menu)
        menu.Destroy()

    def _on_new_submenu(self, event):
        if self.actions.new_submenu is not None:
            self.actions.new_submenu(self._selected_menu_id())
            self.Reload(force=True)
        if hasattr(event, "Skip"):
            event.Skip()

    def _on_add_items(self, event):
        menu_id = self._selected_menu_id()
        if self.actions.add_items is not None and menu_id is not None:
            self.actions.add_items(menu_id)
            self.Reload(force=True)
        if hasattr(event, "Skip"):
            event.Skip()

    def _on_change_icon(self, event):
        menu = self._icon_editable()
        if menu is not None and self.actions.change_icon(menu):
            self.Reload(force=True)
        if hasattr(event, "Skip"):
            event.Skip()

    def _on_open_item(self, event):
        target = self._openable()
        if target is not None:
            kind, payload = target
            if kind == "member":
                self.actions.open_descriptor(payload.descriptor)
            else:
                self.actions.open_menu(payload.tgi)
        if hasattr(event, "Skip"):
            event.Skip()

    def _on_copy_id(self, event):
        kind, payload = self._selected_data()
        if kind == KIND_MENU and wx.TheClipboard.Open():
            try:
                wx.TheClipboard.SetData(wx.TextDataObject(payload.hex))
            finally:
                wx.TheClipboard.Close()
        if hasattr(event, "Skip"):
            event.Skip()


def open_submenu_tree(parent, virtual_dat, actions: Optional[SubmenuTreeActions] = None):
    """Show the tree, reusing the window if it is already open on ``parent``."""
    existing = getattr(parent, "_submenu_tree_dialog", None)
    if existing:
        try:
            existing.Reload(force=True)
            existing.Raise()
            return existing
        except RuntimeError:  # the C++ side is gone
            pass
    dlg = SubmenuTreeDialog(parent, virtual_dat, actions=actions)
    try:
        parent._submenu_tree_dialog = dlg
    except AttributeError:
        pass

    def _forget(event):
        # Bound after the dialog's own EVT_CLOSE handler, so this one runs
        # first: set the flag here too or the selection events the imminent
        # Destroy() fires would still reach a half-dead tree.
        dlg._closing = True
        try:
            if getattr(parent, "_submenu_tree_dialog", None) is dlg:
                parent._submenu_tree_dialog = None
        except AttributeError:
            pass
        event.Skip()
        dlg.Destroy()

    dlg.Bind(wx.EVT_CLOSE, _forget)
    _centre_on_top_level(dlg, parent)
    dlg.Show()
    return dlg
