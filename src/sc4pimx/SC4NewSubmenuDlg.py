"""New Submenu dialog: collects the fields needed to author a brand-new
Submenus-DLL button exemplar (name, description, parent menu, icon, button
ID, item order).

This module is presentation-only -- it hands back a :class:`NewSubmenuResult`
and does no DBPF I/O itself. The caller (``SC4PIMApp.OnNewSubmenu``) owns
allocating the button ID's TGIs and writing the exemplar/LTEXT/icon entries,
the same split ``SC4BuildingSubmenuPicker`` uses between picking and writing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import wx
from PIL import Image

from .SC4IconMakerDlg import (
    SUBMENU_ICON_TEMPLATES,
    compose_lot_icon,
    generate_template_icon_source,
    open_template_icon_dialog,
)
from .SC4OccupantGroupPicker import _centre_on_top_level
from .SC4SubmenuWidgets import ParentMenuCombo
from .TablerIcons import dialog_button_sizer, set_button_icon
from .translation import *  # noqa: F401,F403

_ICON_PREVIEW_SIZE = 44


@dataclass(frozen=True)
class NewSubmenuResult:
    name: str
    description: str
    parent_id: int
    icon_image: Image.Image
    button_id: int
    item_order: int


class IconSourcePanel(wx.Panel):
    """Preview plus the three ways to source a submenu icon.

    Shared by the New Submenu dialog and the Change Icon dialog so both offer
    the same choices and remember the icon generator's settings between visits.
    """

    def __init__(self, parent, source_icon=None, initial_image=None, source_label=None):
        wx.Panel.__init__(self, parent, -1)
        self._source_icon = source_icon
        self._icon_image = None  # composed 176x44
        self._template_settings = None

        box = wx.StaticBoxSizer(wx.StaticBox(self, label=LEXNewSubmenuIconLabel), wx.HORIZONTAL)
        host = box.GetStaticBox()
        self.iconPreview = wx.StaticBitmap(host, size=(_ICON_PREVIEW_SIZE, _ICON_PREVIEW_SIZE))
        box.Add(self.iconPreview, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 6)

        buttons = wx.BoxSizer(wx.VERTICAL)
        self.templateButton = wx.Button(host, -1, LEXNewSubmenuTemplate)
        set_button_icon(self.templateButton, "wand")
        buttons.Add(self.templateButton, 0, wx.BOTTOM | wx.EXPAND, 4)
        self.chooseImageButton = wx.Button(host, -1, LEXNewSubmenuChooseImage)
        set_button_icon(self.chooseImageButton, "photo")
        buttons.Add(self.chooseImageButton, 0, wx.BOTTOM | wx.EXPAND, 4)
        self.fromLotButton = wx.Button(host, -1, source_label or LEXNewSubmenuFromSourceLot)
        self.fromLotButton.Enable(source_icon is not None)
        buttons.Add(self.fromLotButton, 0, wx.EXPAND)
        box.Add(buttons, 1, wx.ALL | wx.EXPAND, 6)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(box, 1, wx.EXPAND)
        self.SetSizer(sizer)

        self.templateButton.Bind(wx.EVT_BUTTON, self._on_template)
        self.chooseImageButton.Bind(wx.EVT_BUTTON, self._on_choose_image)
        self.fromLotButton.Bind(wx.EVT_BUTTON, self._on_from_lot)

        if initial_image is not None:
            self.SetComposedImage(initial_image)
        elif source_icon is not None:
            self.SetSourceImage(source_icon)
        else:
            self.SetSourceImage(generate_template_icon_source(SUBMENU_ICON_TEMPLATES[0][1]))

    # -- state --------------------------------------------------------------

    def SetSourceImage(self, source_image: Image.Image) -> None:
        """Take a plain picture, composite it into the four-state icon."""
        self.SetComposedImage(compose_lot_icon(source_image))

    def SetComposedImage(self, composed: Image.Image) -> None:
        self._icon_image = composed
        preview = composed.crop((0, 0, 44, 44)).convert("RGB")
        wx_image = wx.Image(preview.size[0], preview.size[1])
        wx_image.SetData(preview.tobytes())
        self.iconPreview.SetBitmap(wx_image.ConvertToBitmap())

    def GetImage(self) -> Optional[Image.Image]:
        return self._icon_image

    # -- sources ------------------------------------------------------------

    def _on_choose_image(self, event: wx.Event) -> None:
        with wx.FileDialog(
            self, LEXNewSubmenuChooseImage, wildcard="Images|*.png;*.jpg;*.jpeg;*.bmp",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        ) as file_dlg:
            if file_dlg.ShowModal() != wx.ID_OK:
                return
            try:
                image = Image.open(file_dlg.GetPath())
            except Exception:
                wx.MessageBox(LEXNewSubmenuImageLoadFailed, LEXNewSubmenuDialogTitle,
                              wx.OK | wx.ICON_ERROR, self)
                return
        self.SetSourceImage(image)
        event.Skip()

    def _on_from_lot(self, event: wx.Event) -> None:
        if self._source_icon is not None:
            self.SetSourceImage(self._source_icon)
        event.Skip()

    def _on_template(self, event: wx.Event) -> None:
        image, settings = open_template_icon_dialog(
            self, initial_colour=SUBMENU_ICON_TEMPLATES[0][1], settings=self._template_settings,
        )
        if image is not None:
            self._template_settings = settings
            self.SetSourceImage(image)
        event.Skip()


class NewSubmenuDialog(wx.Dialog):
    def __init__(
        self,
        parent: wx.Window,
        virtual_dat,
        suggested_button_id: int,
        iid_provider: Callable[[], int],
        source_icon: Optional[Image.Image] = None,
        title: Optional[str] = None,
        parent_id: Optional[int] = None,
    ):
        wx.Dialog.__init__(
            self, parent, -1, title or LEXNewSubmenuDialogTitle,
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self.virtual_dat = virtual_dat
        self.iid_provider = iid_provider

        grid = wx.FlexGridSizer(cols=2, vgap=8, hgap=8)
        grid.AddGrowableCol(1)

        grid.Add(wx.StaticText(self, label=LEXNewSubmenuNameLabel), 0, wx.ALIGN_CENTER_VERTICAL)
        self.nameCtrl = wx.TextCtrl(self, -1, "")
        grid.Add(self.nameCtrl, 1, wx.EXPAND)

        grid.Add(wx.StaticText(self, label=LEXNewSubmenuDescriptionLabel), 0, wx.ALIGN_CENTER_VERTICAL)
        self.descriptionCtrl = wx.TextCtrl(self, -1, "")
        grid.Add(self.descriptionCtrl, 1, wx.EXPAND)

        grid.Add(wx.StaticText(self, label=LEXNewSubmenuParentLabel), 0, wx.ALIGN_CENTER_VERTICAL)
        self.parentCombo = ParentMenuCombo(self, virtual_dat, selected=parent_id)
        grid.Add(self.parentCombo, 1, wx.EXPAND)

        grid.Add(wx.StaticText(self, label=LEXNewSubmenuButtonIdLabel), 0, wx.ALIGN_CENTER_VERTICAL)
        id_row = wx.BoxSizer(wx.HORIZONTAL)
        self.buttonIdCtrl = wx.TextCtrl(self, -1, "0x%08X" % (int(suggested_button_id) & 0xFFFFFFFF))
        id_row.Add(self.buttonIdCtrl, 1, wx.RIGHT, 6)
        self.randomizeButton = wx.Button(self, -1, LEXNewSubmenuRandomize)
        set_button_icon(self.randomizeButton, "wand")
        id_row.Add(self.randomizeButton, 0)
        grid.Add(id_row, 1, wx.EXPAND)

        grid.Add(wx.StaticText(self, label=LEXNewSubmenuOrderLabel), 0, wx.ALIGN_CENTER_VERTICAL)
        self.orderCtrl = wx.SpinCtrl(self, -1, min=-2147483648, max=2147483647, initial=0)
        grid.Add(self.orderCtrl, 0)

        self.iconPanel = IconSourcePanel(self, source_icon=source_icon)

        buttons = dialog_button_sizer(self)
        ok_button = self.FindWindowById(wx.ID_OK)
        if ok_button is not None:
            ok_button.Bind(wx.EVT_BUTTON, self._on_ok)

        root = wx.BoxSizer(wx.VERTICAL)
        root.Add(grid, 0, wx.EXPAND | wx.ALL, 10)
        root.Add(self.iconPanel, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        root.Add(buttons, 0, wx.EXPAND | wx.ALL, 10)
        self.SetSizerAndFit(root)
        self.SetMinSize((420, self.GetSize().height))
        self.CentreOnParent()

        self.randomizeButton.Bind(wx.EVT_BUTTON, self._on_randomize)

    # -- id --------------------------------------------------------------

    def _on_randomize(self, event: wx.Event) -> None:
        try:
            new_id = int(self.iid_provider()) & 0xFFFFFFFF
        except Exception:
            return
        self.buttonIdCtrl.SetValue("0x%08X" % new_id)
        event.Skip()

    # -- commit ------------------------------------------------------------

    def _parse_button_id(self):
        raw = self.buttonIdCtrl.GetValue().strip()
        try:
            if not raw.lower().startswith("0x"):
                raise ValueError
            value = int(raw, 16)
            if value <= 0 or value > 0xFFFFFFFF:
                raise ValueError
        except ValueError:
            return None
        return value

    def _on_ok(self, event: wx.Event) -> None:
        name = self.nameCtrl.GetValue().strip()
        if not name:
            wx.MessageBox(LEXNewSubmenuNameRequired, LEXNewSubmenuDialogTitle, wx.OK | wx.ICON_ERROR, self)
            return
        button_id = self._parse_button_id()
        if button_id is None:
            wx.MessageBox(LEXNewSubmenuInvalidButtonId, LEXNewSubmenuDialogTitle, wx.OK | wx.ICON_ERROR, self)
            return
        parent_id = self.parentCombo.GetMenuId()
        if parent_id is None:
            wx.MessageBox(LEXNewSubmenuInvalidParent, LEXNewSubmenuDialogTitle, wx.OK | wx.ICON_ERROR, self)
            return
        icon_image = self.iconPanel.GetImage()
        if icon_image is None:
            wx.MessageBox(LEXNewSubmenuNoIcon, LEXNewSubmenuDialogTitle, wx.OK | wx.ICON_ERROR, self)
            return
        self._result = NewSubmenuResult(
            name=name,
            description=self.descriptionCtrl.GetValue().strip(),
            parent_id=parent_id,
            icon_image=icon_image,
            button_id=button_id,
            item_order=int(self.orderCtrl.GetValue()),
        )
        self.EndModal(wx.ID_OK)

    def GetResult(self) -> Optional[NewSubmenuResult]:
        return getattr(self, "_result", None)


class SubmenuIconDialog(wx.Dialog):
    """Replace the icon of a submenu that already exists."""

    def __init__(self, parent, menu_label, current_image=None, title=None):
        wx.Dialog.__init__(self, parent, -1, title or LEXSubmenuIconDialogTitle,
                           style=wx.DEFAULT_DIALOG_STYLE)
        heading = wx.StaticText(self, -1, LEXSubmenuIconFor % menu_label)
        self.iconPanel = IconSourcePanel(
            self, source_icon=None, initial_image=current_image,
            source_label=LEXSubmenuIconRestore,
        )
        if current_image is not None:
            # "From this lot" has no meaning here; reuse the third button to
            # put the icon back the way it was.
            self._original = current_image
            self.iconPanel.fromLotButton.Enable(True)
            self.iconPanel.fromLotButton.Bind(wx.EVT_BUTTON, self._on_restore)

        buttons = dialog_button_sizer(self)
        root = wx.BoxSizer(wx.VERTICAL)
        root.Add(heading, 0, wx.ALL, 10)
        root.Add(self.iconPanel, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        root.Add(buttons, 0, wx.EXPAND | wx.ALL, 10)
        self.SetSizerAndFit(root)
        self.CentreOnParent()

    def _on_restore(self, event):
        self.iconPanel.SetComposedImage(self._original)
        event.Skip()

    def GetImage(self):
        return self.iconPanel.GetImage()


def open_submenu_icon_dialog(parent, menu_label, current_image=None, title=None):
    dlg = SubmenuIconDialog(parent, menu_label, current_image=current_image, title=title)
    try:
        _centre_on_top_level(dlg, parent)
        if dlg.ShowModal() == wx.ID_OK:
            return dlg.GetImage()
        return None
    finally:
        dlg.Destroy()


def open_new_submenu_dialog(
    parent: wx.Window,
    virtual_dat,
    suggested_button_id: int,
    iid_provider: Callable[[], int],
    source_icon: Optional[Image.Image] = None,
    title: Optional[str] = None,
    parent_id: Optional[int] = None,
) -> Optional[NewSubmenuResult]:
    dlg = NewSubmenuDialog(
        parent, virtual_dat, suggested_button_id, iid_provider,
        source_icon=source_icon, title=title, parent_id=parent_id,
    )
    try:
        _centre_on_top_level(dlg, parent)
        if dlg.ShowModal() == wx.ID_OK:
            return dlg.GetResult()
        return None
    finally:
        dlg.Destroy()
