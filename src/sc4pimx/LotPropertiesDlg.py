"""Lot Properties dialog: the classic Lot Editor "Lot" tab (size, road access,
foundation, elevation tolerance), opened from inside the 3D Lot Editor.
"""

import logging

import wx
from PIL import Image

from .SC4CityContext import ROAD_FLAG_EDGES, road_edges_from_flags
from .SC4Data import CreateAPropFromString
from .SC4DataFunctions import LOT_CONFIG_PROPERTY_FIRST, LOT_CONFIG_PROPERTY_LAST
from .SC4DatTools import CreateAProp, Prop, SC4Exemplar
from .SC4LETools import BitmapFromPIL
from .SC4StructuredPropertyEditors import _option_items, edit_structured_property
from .TablerIcons import dialog_button_sizer, icon_toggle_button
from .translation import *  # noqa: F401,F403
from . import FSHConverter

logger = logging.getLogger(__name__)

LOT_SIZE_PROP = 0x88EDC790
REQUIRED_ROADS_PROP = 0x4A4A88F0
MAX_SLOPE_BEFORE_FOUNDATION_PROP = 0x88EDC792
FOUNDATION_PROP = 0x88FCD877
RETAINING_WALL_PROP = 0x88EDC798
MAX_SLOPE_ALLOWED_PROP = 0xE99B068C
MIN_SLOPE_ALLOWED_PROP = 0x699B08A4
GROWTH_STAGE_PROP = 0x27812837

_LOT_OBJECT_RANGE = range(LOT_CONFIG_PROPERTY_FIRST, LOT_CONFIG_PROPERTY_LAST + 1)

# Confirmed against the base game's SimCity_1.dat/SimCity_2.dat (Ghidra's
# 0x891B0E1A group turned out to be retaining-wall-only; foundations use a
# different group -- verified directly against real exemplars/FSH entries):
#   - Foundation exemplar (0x88FCD877 value) carries FoundationSideTextures
#     (0x68FCFF37, 5 IIDs, one per zoom level) when texture-based, absent
#     when procedural; textures live at (0x7AB50E44, 0x1ABE787D, iid).
#   - Retaining-wall exemplar (0x88EDC798 value) carries
#     RetainingWallPropertyWallTextures (0x295961F2, 5 IIDs); textures live
#     at (0x7AB50E44, 0x891B0E1A, iid). Always texture-based, no procedural
#     case observed.
_WALL_TEXTURE_TYPE = 0x7AB50E44
_FOUNDATION_TEXTURE_GROUP = 0x1ABE787D
_FOUNDATION_SIDE_TEXTURES_PROP = 0x68FCFF37
_RETAINING_WALL_TEXTURE_GROUP = 0x891B0E1A
_RETAINING_WALL_TEXTURES_PROP = 0x295961F2

_THUMB_SIZE = 64
_EXEMPLAR_TYPE = 0x6534284A
# Empirically confirmed against the base game's SimCity_1.dat (not
# documented anywhere): Maxis's foundation/retaining-wall "system"
# exemplars all live under this one group.
_LOT_SYSTEM_GROUP = 0xC977C536


def _parse_exemplar(entry, virtual_dat):
    entry.read_file(None, True, True)
    exemplar = SC4Exemplar(entry, virtual_dat)
    entry.rawContent = None
    entry.content = None
    return exemplar


def _find_exemplar_by_iid(virtual_dat, iid):
    """Locate an arbitrary exemplar by IID, regardless of its group.

    ``SC4PIMApp.UpdateEntry`` frees ``entry.exemplar`` right after startup
    for any exemplar whose Exemplar Type isn't Building/Lot/Prop/Flora/
    Foundation -- retaining walls are one of the types that gets freed --
    so it can't be relied on here. Re-parse on demand instead: matching by
    bare instance ID is a cheap tuple compare over already-loaded entries
    (no I/O for the misses), so one pass stays fast even with 100k+ entries
    loaded; results are cached per session.
    """
    if not iid:
        return None
    cache = virtual_dat.__dict__.setdefault("_lot_properties_exemplar_cache", {})
    if iid in cache:
        return cache[iid]
    exemplar = None
    for entry in virtual_dat.allEntries:
        if entry.tgi[0] == _EXEMPLAR_TYPE and entry.tgi[2] == iid:
            existing = getattr(entry, "exemplar", None)
            try:
                exemplar = existing if existing is not None else _parse_exemplar(entry, virtual_dat)
            except Exception:
                logger.exception("Failed to parse exemplar 0x%08X for Lot Properties preview", iid)
                continue
            break
    cache[iid] = exemplar
    return exemplar


def _list_retaining_wall_options(virtual_dat):
    """[(iid, name), ...] for retaining-wall exemplars, name-sorted.

    Scoped to Maxis's system group (_LOT_SYSTEM_GROUP) so this stays a
    cheap one-time scan instead of reparsing every one of the 100k+ loaded
    entries -- covers the base game and any plugin that reuses the same
    group. A custom retaining wall authored under a different group won't
    show up here, but still works via the dropdown's "Custom..." entry.
    """
    options = getattr(virtual_dat, "_retaining_wall_options_cache", None)
    if options is not None:
        return options
    options = []
    for entry in virtual_dat.allEntries:
        if entry.tgi[0] != _EXEMPLAR_TYPE or entry.tgi[1] != _LOT_SYSTEM_GROUP:
            continue
        try:
            existing = getattr(entry, "exemplar", None)
            exemplar = existing if existing is not None else _parse_exemplar(entry, virtual_dat)
            if not exemplar.GetProp(_RETAINING_WALL_TEXTURES_PROP):
                continue
            name = exemplar.GetProp(0x20)
        except Exception:
            logger.exception("Failed to inspect exemplar 0x%08X for retaining-wall list", entry.tgi[2])
            continue
        options.append((entry.tgi[2], name[0] if name else "0x%08X" % entry.tgi[2]))
    options.sort(key=lambda item: item[1].casefold())
    virtual_dat._retaining_wall_options_cache = options
    return options


def _blank_thumb_bitmap(size=_THUMB_SIZE):
    """A neutral placeholder bitmap -- a bare wx.Bitmap(w, h) is uninitialized
    (often solid black on Windows), not an empty/transparent image."""
    bitmap = wx.Bitmap(size, size)
    dc = wx.MemoryDC(bitmap)
    dc.SetBackground(wx.Brush(wx.SystemSettings.GetColour(wx.SYS_COLOUR_BTNFACE)))
    dc.Clear()
    dc.SelectObject(wx.NullBitmap)
    return bitmap


def _wall_texture_preview_bitmap(virtual_dat, exemplar_iid, texture_prop_id, texture_group, size=_THUMB_SIZE):
    """(wx.Bitmap or None, is_procedural) for a foundation/retaining-wall IID.

    None with is_procedural=True means confirmed procedural (no texture to
    show); None with is_procedural=False means the lookup itself failed
    (unknown exemplar, missing texture entry, bad FSH) -- both are shown as
    "no preview available" rather than an error.
    """
    exemplar = _find_exemplar_by_iid(virtual_dat, exemplar_iid)
    if exemplar is None:
        return None, False
    textures = exemplar.GetProp(texture_prop_id)
    if not textures:
        return None, True
    # 5 IIDs, one per zoom level, lowest-resolution first -- reverse to try
    # the highest-resolution (closest zoom) one first, falling back to
    # progressively lower resolutions if a slot is missing.
    for tex_iid in reversed(textures):
        entry = virtual_dat.getEntry(_WALL_TEXTURE_TYPE, texture_group, tex_iid)
        if entry is None:
            continue
        try:
            entry.read_file(None, True, True)
            _layers, _alpha, img, _alpha_data, wh = FSHConverter.decodeFSH(entry.content)
            pil = Image.frombytes("RGB", wh, img).convert("RGB").resize((size, size), Image.BICUBIC)
            return BitmapFromPIL(pil), False
        except Exception:
            logger.exception("Failed to decode wall texture preview 0x%08X", tex_iid)
            continue
        finally:
            entry.content = None
            entry.rawContent = None
    return None, False


class LotPropertiesDialog(wx.Dialog):
    """Size / Corners / Foundation / Elevation Change / Growth Stage."""

    def __init__(self, parent, exemplar, virtual_dat):
        super().__init__(parent, title=lotPropertiesDialogTitle, style=wx.DEFAULT_DIALOG_STYLE)
        self._exemplar = exemplar
        self._virtual_dat = virtual_dat
        self._changed_props = {}
        self.size_changed = False
        self.retaining_wall_touched = False

        root = wx.BoxSizer(wx.VERTICAL)
        root.Add(self._build_size_box(), 0, wx.EXPAND | wx.ALL, 8)
        root.Add(self._build_corners_box(), 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        root.Add(self._build_foundation_box(), 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        root.Add(self._build_elevation_box(), 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        root.Add(self._build_growth_stage_row(), 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        buttons = dialog_button_sizer(self)
        ok_button = self.FindWindowById(wx.ID_OK)
        if ok_button is not None:
            ok_button.Bind(wx.EVT_BUTTON, self._on_ok)
        root.Add(buttons, 0, wx.EXPAND | wx.ALL, 8)

        self.SetSizerAndFit(root)
        self.CentreOnParent()

    # -- section builders ------------------------------------------------

    def _build_size_box(self):
        box = wx.StaticBoxSizer(wx.StaticBox(self, label=lotPropertiesSizeLabel), wx.HORIZONTAL)
        size = self._exemplar.GetProp(LOT_SIZE_PROP) or (1, 1)
        w, h = int(size[0]), int(size[1])
        choices = [str(v) for v in range(1, 32)]
        box.Add(wx.StaticText(box.GetStaticBox(), label=lotPropertiesWidthLabel), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)
        self._width_ctrl = wx.ComboBox(
            box.GetStaticBox(), value=str(w), style=wx.CB_DROPDOWN | wx.CB_READONLY, choices=choices,
        )
        box.Add(self._width_ctrl, 0, wx.LEFT | wx.RIGHT, 6)
        box.Add(wx.StaticText(box.GetStaticBox(), label=lotPropertiesDepthLabel), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 12)
        self._depth_ctrl = wx.ComboBox(
            box.GetStaticBox(), value=str(h), style=wx.CB_DROPDOWN | wx.CB_READONLY, choices=choices,
        )
        box.Add(self._depth_ctrl, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        return box

    def _build_corners_box(self):
        box = wx.StaticBoxSizer(wx.StaticBox(self, label=lotPropertiesCornersLabel), wx.HORIZONTAL)
        parent = box.GetStaticBox()
        flags_prop = self._exemplar.GetProp(REQUIRED_ROADS_PROP)
        flags = int(flags_prop[0]) if flags_prop else 0
        edges = road_edges_from_flags(flags)
        # icon, tooltip per edge; laid out as a N/W/E/S-style cross (Behind at
        # top, Front at bottom, matching how the property's own edges are
        # named -- see SC4CityContext's road-edge docstring). border-top/
        # bottom/left/right read as "this side has a border (road)", the
        # same convention as a spreadsheet/word-processor border picker.
        specs = {
            "zmin": ("border-top", lotPropertiesCornerBehind),
            "xmin": ("border-left", lotPropertiesCornerLeft),
            "xmax": ("border-right", lotPropertiesCornerRight),
            "zmax": ("border-bottom", lotPropertiesCornerFront),
        }
        self._corner_toggles = {}
        for edge, (icon, tooltip) in specs.items():
            toggle = icon_toggle_button(parent, icon, tooltip)
            toggle.SetValue(edge in edges)
            self._corner_toggles[edge] = toggle

        cross = wx.GridSizer(3, 3, 2, 2)
        for edge in (None, "zmin", None, "xmin", None, "xmax", None, "zmax", None):
            if edge is None:
                cross.Add((0, 0))
            else:
                cross.Add(self._corner_toggles[edge], 0, wx.ALIGN_CENTER)
        box.Add(cross, 0, wx.ALIGN_CENTER | wx.ALL, 6)
        return box

    def _build_foundation_box(self):
        box = wx.StaticBoxSizer(wx.StaticBox(self, label=lotPropertiesFoundationLabel), wx.VERTICAL)
        parent = box.GetStaticBox()
        grid = wx.FlexGridSizer(cols=2, vgap=6, hgap=8)
        grid.AddGrowableCol(1)

        threshold = self._exemplar.GetProp(MAX_SLOPE_BEFORE_FOUNDATION_PROP)
        threshold_value = float(threshold[0]) if threshold else 5.0
        grid.Add(wx.StaticText(parent, label=lotPropertiesThresholdLabel), 0, wx.ALIGN_CENTER_VERTICAL)
        self._threshold_ctrl = wx.TextCtrl(parent, value="%.2f" % threshold_value)
        grid.Add(self._threshold_ctrl, 0, wx.EXPAND)

        grid.Add(wx.StaticText(parent, label=lotPropertiesLotFoundationLabel), 0, wx.ALIGN_CENTER_VERTICAL)
        foundation_row = wx.BoxSizer(wx.HORIZONTAL)
        self._foundation_choice = wx.Choice(parent)
        self._foundation_items = []
        prop_def = self._virtual_dat.properties.get(FOUNDATION_PROP)
        current_foundation = self._exemplar.GetProp(FOUNDATION_PROP)
        current_foundation_iid = int(current_foundation[0]) if current_foundation else None
        selection = 0
        if prop_def is not None:
            for index, (value, name) in enumerate(_option_items(prop_def)):
                self._foundation_items.append(value)
                self._foundation_choice.Append(name)
                if value == current_foundation_iid:
                    selection = index
        if self._foundation_items:
            self._foundation_choice.SetSelection(selection)
        else:
            self._foundation_choice.Disable()
        foundation_row.Add(self._foundation_choice, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        self._foundation_thumb = wx.StaticBitmap(parent, size=(_THUMB_SIZE, _THUMB_SIZE))
        foundation_row.Add(self._foundation_thumb, 0)
        grid.Add(foundation_row, 1, wx.EXPAND)

        grid.Add(wx.StaticText(parent, label=""))
        self._foundation_preview_note = wx.StaticText(parent, label="")
        self._foundation_preview_note.SetForegroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT))
        grid.Add(self._foundation_preview_note, 1, wx.EXPAND)

        grid.Add(wx.StaticText(parent, label=lotPropertiesRetainingWallLabel), 0, wx.ALIGN_CENTER_VERTICAL)
        wall_row = wx.BoxSizer(wx.HORIZONTAL)
        self._wall_choice = wx.Choice(parent)
        self._wall_items = []
        wall_row.Add(self._wall_choice, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        self._wall_thumb = wx.StaticBitmap(parent, size=(_THUMB_SIZE, _THUMB_SIZE))
        wall_row.Add(self._wall_thumb, 0)
        grid.Add(wall_row, 1, wx.EXPAND)

        box.Add(grid, 0, wx.EXPAND | wx.ALL, 6)
        self._populate_wall_choice()
        self._wall_choice.Bind(wx.EVT_CHOICE, self._on_wall_choice)
        self._foundation_choice.Bind(wx.EVT_CHOICE, self._on_foundation_changed)
        self._update_foundation_preview()
        return box

    def _build_elevation_box(self):
        box = wx.StaticBoxSizer(wx.StaticBox(self, label=lotPropertiesElevationLabel), wx.HORIZONTAL)
        parent = box.GetStaticBox()
        lot_max = self._exemplar.GetProp(MAX_SLOPE_ALLOWED_PROP)
        lot_min = self._exemplar.GetProp(MIN_SLOPE_ALLOWED_PROP)
        max_value = float(lot_max[0]) if lot_max else 90.0
        min_value = float(lot_min[0]) if lot_min else 0.0
        box.Add(wx.StaticText(parent, label=lotPropertiesLotMaxLabel), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)
        self._lot_max_ctrl = wx.TextCtrl(parent, value="%.2f" % max_value)
        box.Add(self._lot_max_ctrl, 0, wx.LEFT | wx.RIGHT, 6)
        box.Add(wx.StaticText(parent, label=lotPropertiesLotMinLabel), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 12)
        self._lot_min_ctrl = wx.TextCtrl(parent, value="%.2f" % min_value)
        box.Add(self._lot_min_ctrl, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        return box

    def _build_growth_stage_row(self):
        row = wx.BoxSizer(wx.HORIZONTAL)
        stage = self._exemplar.GetProp(GROWTH_STAGE_PROP)
        stage_text = str(int(stage[0])) if stage else "?"
        row.Add(wx.StaticText(self, label=lotPropertiesGrowthStageLabel), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        row.Add(wx.StaticText(self, label=stage_text), 0, wx.ALIGN_CENTER_VERTICAL)
        return row

    # -- foundation preview -----------------------------------------------

    def _on_foundation_changed(self, event):
        self._update_foundation_preview()
        event.Skip()

    def _update_foundation_preview(self):
        if not self._foundation_items:
            return
        selection = self._foundation_choice.GetSelection()
        if selection == wx.NOT_FOUND:
            return
        foundation_iid = self._foundation_items[selection]
        bitmap, is_procedural = _wall_texture_preview_bitmap(
            self._virtual_dat, foundation_iid, _FOUNDATION_SIDE_TEXTURES_PROP, _FOUNDATION_TEXTURE_GROUP,
        )
        if bitmap is not None:
            self._foundation_thumb.SetBitmap(bitmap)
            self._foundation_preview_note.SetLabel("")
        else:
            self._foundation_thumb.SetBitmap(_blank_thumb_bitmap())
            self._foundation_preview_note.SetLabel(
                lotPropertiesLotFoundationProcedural if is_procedural else ""
            )
        self.Layout()

    # -- retaining wall: picker over loaded exemplars, "Custom..." escape
    # hatch for a value that isn't among them (missing dependency, or one
    # not yet indexed). Writes self._exemplar immediately, same as the raw
    # editor it wraps -- see _on_ok for why that's fine here.

    def _populate_wall_choice(self):
        self._wall_choice.Clear()
        self._wall_items = []
        current = self._exemplar.GetProp(RETAINING_WALL_PROP)
        current_iid = int(current[0]) if current else None
        found_current = False
        for iid, name in _list_retaining_wall_options(self._virtual_dat):
            self._wall_items.append(iid)
            self._wall_choice.Append(name)
            if iid == current_iid:
                found_current = True
        if current_iid is not None and not found_current:
            self._wall_items.insert(0, current_iid)
            current_exemplar = _find_exemplar_by_iid(self._virtual_dat, current_iid)
            current_name = current_exemplar.GetProp(0x20) if current_exemplar is not None else None
            label = (
                "%s (0x%08X)" % (current_name[0], current_iid)
                if current_name
                else lotPropertiesRetainingWallCurrentUnknown % current_iid
            )
            self._wall_choice.Insert(label, 0)
        self._wall_items.append(None)
        self._wall_choice.Append(lotPropertiesRetainingWallCustom)
        if current_iid is not None and current_iid in self._wall_items:
            self._wall_choice.SetSelection(self._wall_items.index(current_iid))
        elif self._wall_items:
            self._wall_choice.SetSelection(0)
        self._update_wall_preview()

    def _update_wall_preview(self):
        selection = self._wall_choice.GetSelection()
        iid = self._wall_items[selection] if selection != wx.NOT_FOUND else None
        bitmap = None
        if iid is not None:
            bitmap, _is_procedural = _wall_texture_preview_bitmap(
                self._virtual_dat, iid, _RETAINING_WALL_TEXTURES_PROP, _RETAINING_WALL_TEXTURE_GROUP,
            )
        self._wall_thumb.SetBitmap(bitmap if bitmap is not None else _blank_thumb_bitmap())
        self.Layout()

    def _on_wall_choice(self, event):
        selection = self._wall_choice.GetSelection()
        if selection == wx.NOT_FOUND:
            return
        iid = self._wall_items[selection]
        if iid is None:
            self._edit_retaining_wall_raw()
            return
        prop_def = self._virtual_dat.properties.get(RETAINING_WALL_PROP)
        if prop_def is not None:
            self._exemplar.AddTextProp(CreateAProp(prop_def, (iid,)))
            self._exemplar.modified = True
            self.retaining_wall_touched = True
        self._update_wall_preview()

    def _edit_retaining_wall_raw(self):
        prop_def = self._virtual_dat.properties.get(RETAINING_WALL_PROP)
        if prop_def is None:
            return
        prop = next((p for p in self._exemplar.props if p.id == RETAINING_WALL_PROP), None)
        if prop is None:
            current = self._exemplar.GetProp(RETAINING_WALL_PROP) or (0,)
            self._exemplar.AddTextProp(CreateAProp(prop_def, tuple(current)))
            prop = next(p for p in self._exemplar.props if p.id == RETAINING_WALL_PROP)
        new_value = edit_structured_property(self, lotPropertiesRetainingWallLabel, prop, prop_def)
        if new_value is not None:
            new_prop_str = CreateAPropFromString(prop_def, new_value)
            new_prop = Prop(new_prop_str, False, self._exemplar)
            self._exemplar.props[self._exemplar.props.index(prop)] = new_prop
            self._exemplar.modified = True
            self.retaining_wall_touched = True
        # Re-sync either way: the dropdown was left on "Custom..." even on
        # cancel, so put the selection back on whatever is actually current.
        self._populate_wall_choice()

    # -- commit ------------------------------------------------------------

    def _on_ok(self, event):
        width = int(self._width_ctrl.GetValue())
        depth = int(self._depth_ctrl.GetValue())
        current_size = self._exemplar.GetProp(LOT_SIZE_PROP) or (width, depth)
        if (width, depth) != tuple(int(v) for v in current_size):
            blocked = self._describe_out_of_bounds(width, depth)
            if blocked:
                wx.MessageBox(
                    lotPropertiesShrinkBlockedMessage % (blocked, width, depth),
                    lotPropertiesShrinkBlockedTitle, wx.OK | wx.ICON_WARNING, self,
                )
                return
            self._changed_props[LOT_SIZE_PROP] = (width, depth)
            self.size_changed = True

        try:
            threshold = float(self._threshold_ctrl.GetValue())
            lot_max = float(self._lot_max_ctrl.GetValue())
            lot_min = float(self._lot_min_ctrl.GetValue())
        except ValueError:
            wx.MessageBox(lotPropertiesInvalidNumber, lotPropertiesDialogTitle, wx.OK | wx.ICON_ERROR, self)
            return

        self._maybe_set(MAX_SLOPE_BEFORE_FOUNDATION_PROP, (threshold,))
        self._maybe_set(MAX_SLOPE_ALLOWED_PROP, (lot_max,))
        self._maybe_set(MIN_SLOPE_ALLOWED_PROP, (lot_min,))

        flags = 0
        for bit, edge in ROAD_FLAG_EDGES:
            if self._corner_toggles[edge].GetValue():
                flags |= bit
        self._maybe_set(REQUIRED_ROADS_PROP, (flags,))

        if self._foundation_items:
            selection = self._foundation_choice.GetSelection()
            if selection != wx.NOT_FOUND:
                self._maybe_set(FOUNDATION_PROP, (self._foundation_items[selection],))

        self.EndModal(wx.ID_OK)

    def _maybe_set(self, prop_id, values):
        current = self._exemplar.GetProp(prop_id)
        if current is not None and tuple(current) == tuple(values):
            return
        self._changed_props[prop_id] = values

    def _describe_out_of_bounds(self, width, depth):
        # Local import: LotObjectExceedsBounds lives in SC4LotPreview, which
        # imports this dialog -- import here, not at module scope, to avoid
        # a circular import at load time.
        from .SC4LotPreview import LotObjectExceedsBounds

        counts = {}
        for lcp in _LOT_OBJECT_RANGE:
            values = self._exemplar.GetProp(lcp)
            if values is None:
                break
            if LotObjectExceedsBounds(values, width, depth):
                counts[values[0]] = counts.get(values[0], 0) + 1
        if not counts:
            return None
        labels = {
            0: lotPropertiesCountBuilding, 1: lotPropertiesCountProp, 2: lotPropertiesCountTexture,
            4: lotPropertiesCountFlora, 5: lotPropertiesCountWaterLand, 6: lotPropertiesCountWaterLand,
            7: lotPropertiesCountTransit,
        }
        parts = [
            (labels.get(kind, "%d item(s)") % count) for kind, count in sorted(counts.items())
        ]
        return ", ".join(parts)

    def get_changes(self):
        """dict[prop_id, values_tuple] of everything touched, minus size."""
        return dict(self._changed_props)
