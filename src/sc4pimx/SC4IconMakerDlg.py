"""Icon maker dialog for creating SC4 building icons."""
import random
from dataclasses import dataclass, replace
from functools import lru_cache

import wx
import wx.lib.filebrowsebutton as filebrowse
from PIL import Image, ImageColor, ImageDraw, ImageOps
from PIL.Image import Resampling

from .paths import asset_path
from .TablerIcons import dialog_button, dialog_button_sizer, set_button_icon
from .translation import *  # noqa: F401,F403


def compose_lot_icon(image):
    """Composite a picture into the 176x44 four-state SC4 building icon.

    The picture is resized to 44x44, tiled into the four icon states, then
    composited with the shipped icon template through its mask.
    """
    image = image.convert('RGB').resize((44, 44), Resampling.BICUBIC)
    template = Image.open(asset_path('templates', 'IconTpl.png'))
    mask = Image.open(asset_path('templates', 'IconMaskTpl.png')).convert('L')
    icon = Image.new('RGBA', (44 * 4, 44))
    for cell in range(4):
        icon.paste(image, (44 * cell, 0))
    return Image.composite(icon, template, mask)


# Built-in submenu icon placeholders: generated procedurally (a folder-tab
# glyph in a few stock colours) so a submenu can get a usable icon without
# requiring the user to supply an image. Fed through compose_lot_icon just
# like any user-picked picture.
SUBMENU_ICON_TEMPLATES = (
    ('folder_blue', (66, 133, 199)),
    ('folder_green', (76, 163, 90)),
    ('folder_orange', (219, 138, 45)),
    ('folder_purple', (140, 90, 199)),
    ('folder_red', (196, 68, 68)),
    ('folder_grey', (120, 120, 120)),
)

# Background shapes the template icon can be built on. The value is the key
# used everywhere; the label comes from the language file at display time.
ICON_STYLE_FOLDER = 'folder'
ICON_STYLE_SOLID = 'solid'
ICON_STYLE_GRADIENT = 'gradient'
ICON_STYLE_DIAGONAL = 'diagonal'
ICON_STYLE_RADIAL = 'radial'
ICON_STYLE_CIRCLE = 'circle'
ICON_STYLE_RING = 'ring'
ICON_STYLE_ROUNDED = 'rounded'
ICON_STYLE_PLATE = 'plate'
ICON_STYLE_BEVEL = 'bevel'
ICON_STYLE_STRIPES = 'stripes'
ICON_STYLE_BANNER = 'banner'
ICON_STYLES = (
    ICON_STYLE_FOLDER,
    ICON_STYLE_SOLID,
    ICON_STYLE_GRADIENT,
    ICON_STYLE_DIAGONAL,
    ICON_STYLE_RADIAL,
    ICON_STYLE_CIRCLE,
    ICON_STYLE_RING,
    ICON_STYLE_ROUNDED,
    ICON_STYLE_PLATE,
    ICON_STYLE_BEVEL,
    ICON_STYLE_STRIPES,
    ICON_STYLE_BANNER,
)

# Whole recipes, not just shapes: picking one fills in style and both colours.
# Keep the order in sync with LEXTemplateIconPresetNames.
ICON_PRESETS = (
    ('parks', ICON_STYLE_CIRCLE, (76, 163, 90), None),
    ('transit', ICON_STYLE_PLATE, (52, 108, 168), None),
    ('utility', ICON_STYLE_BEVEL, (219, 138, 45), None),
    ('civic', ICON_STYLE_ROUNDED, (140, 90, 199), None),
    ('landmark', ICON_STYLE_RADIAL, (196, 68, 68), (90, 20, 20)),
    ('industry', ICON_STYLE_STRIPES, (120, 120, 120), (86, 86, 86)),
    ('folder', ICON_STYLE_FOLDER, (66, 133, 199), None),
    ('night', ICON_STYLE_RING, (232, 232, 232), (32, 36, 48)),
    ('banner', ICON_STYLE_BANNER, (44, 128, 120), None),
)

LAYER_GLYPH = 'glyph'
LAYER_TEXT = 'text'
MAX_TEMPLATE_GLYPHS = 4
MAX_ICON_LAYERS = 8


def _shade(colour, factor):
    return tuple(min(255, int(c * factor)) for c in colour[:3])


def _blend(start, end, position):
    return tuple(int(a + (b - a) * position) for a, b in zip(start[:3], end[:3]))


def default_accent_colour(colour):
    """The second colour a gradient/backdrop uses when the caller gives none."""
    return _shade(colour, 0.55)


def _draw_folder(draw, colour, size):
    tab_w, tab_h = int(size * 0.45), int(size * 0.14)
    draw.rectangle((int(size * 0.08), int(size * 0.2), size - int(size * 0.08), size - int(size * 0.14)),
                   fill=_shade(colour, 0.85))
    draw.rectangle((int(size * 0.1), int(size * 0.12), int(size * 0.1) + tab_w, int(size * 0.12) + tab_h),
                   fill=_shade(colour, 0.85))


def generate_template_icon_source(colour, size=44, style=ICON_STYLE_FOLDER, accent=None, border=False):
    """A single flat ``size`` x ``size`` background for a template icon.

    Returns the source picture (not yet run through compose_lot_icon), so
    callers can preview it and only composite the final pick.
    """
    colour = tuple(colour[:3])
    accent = tuple(accent[:3]) if accent else default_accent_colour(colour)

    if style == ICON_STYLE_GRADIENT:
        image = Image.new('RGB', (size, size), colour)
        draw = ImageDraw.Draw(image)
        for y in range(size):
            draw.line(((0, y), (size, y)), fill=_blend(colour, accent, y / max(1, size - 1)))
    elif style == ICON_STYLE_DIAGONAL:
        image = Image.new('RGB', (size, size), colour)
        draw = ImageDraw.Draw(image)
        span = max(1, 2 * size - 2)
        for offset in range(2 * size):
            draw.line(((offset, 0), (0, offset)), fill=_blend(colour, accent, offset / span))
    elif style == ICON_STYLE_RADIAL:
        image = Image.new('RGB', (size, size), accent)
        draw = ImageDraw.Draw(image)
        steps = max(1, size // 2)
        for step in range(steps, 0, -1):
            inset = (steps - step) * (size / 2 / steps)
            draw.ellipse((inset, inset, size - inset - 1, size - inset - 1),
                         fill=_blend(accent, colour, step / steps))
    elif style == ICON_STYLE_CIRCLE:
        image = Image.new('RGB', (size, size), accent)
        draw = ImageDraw.Draw(image)
        inset = int(size * 0.06)
        draw.ellipse((inset, inset, size - inset - 1, size - inset - 1), fill=colour)
    elif style == ICON_STYLE_RING:
        image = Image.new('RGB', (size, size), accent)
        draw = ImageDraw.Draw(image)
        inset = int(size * 0.1)
        draw.ellipse((inset, inset, size - inset - 1, size - inset - 1),
                     outline=colour, width=max(2, int(size * 0.09)))
    elif style == ICON_STYLE_BEVEL:
        image = Image.new('RGB', (size, size), colour)
        draw = ImageDraw.Draw(image)
        edge = max(2, int(size * 0.09))
        draw.polygon([(0, 0), (size, 0), (size - edge, edge), (edge, edge),
                      (edge, size - edge), (0, size)], fill=_shade(colour, 1.3))
        draw.polygon([(size, size), (0, size), (edge, size - edge), (size - edge, size - edge),
                      (size - edge, edge), (size, 0)], fill=_shade(colour, 0.7))
    elif style == ICON_STYLE_STRIPES:
        image = Image.new('RGB', (size, size), colour)
        draw = ImageDraw.Draw(image)
        step = max(3, int(size * 0.14))
        for offset in range(-size, 2 * size, step * 2):
            draw.polygon([(offset, 0), (offset + step, 0),
                          (offset + step - size, size), (offset - size, size)], fill=accent)
    elif style == ICON_STYLE_BANNER:
        image = Image.new('RGB', (size, size), colour)
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, int(size * 0.68), size, size), fill=accent)
    elif style == ICON_STYLE_ROUNDED:
        image = Image.new('RGB', (size, size), accent)
        draw = ImageDraw.Draw(image)
        inset = int(size * 0.08)
        draw.rounded_rectangle((inset, inset, size - inset - 1, size - inset - 1),
                               radius=max(2, int(size * 0.22)), fill=colour)
    elif style == ICON_STYLE_PLATE:
        # Flat colour with a lighter top half, the look most Maxis menu icons
        # have: readable behind a glyph without pulling the eye like a gradient.
        image = Image.new('RGB', (size, size), colour)
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, size, int(size * 0.45)), fill=_shade(colour, 1.18))
    elif style == ICON_STYLE_SOLID:
        image = Image.new('RGB', (size, size), colour)
        draw = ImageDraw.Draw(image)
    else:
        image = Image.new('RGB', (size, size), colour)
        draw = ImageDraw.Draw(image)
        _draw_folder(draw, colour, size)

    if border:
        width = max(1, int(size / 22))
        draw.rectangle((0, 0, size - 1, size - 1), outline=_contrast_colour(colour), width=width)
    return image


_GLYPH_DIR = asset_path('vendor', 'tabler-icons-full', 'svg')


@lru_cache(maxsize=1)
def list_tabler_icon_names():
    """Every icon stem in the full vendored Tabler set, for the template picker's search.

    Deliberately not the curated ``vendor/tabler-icons/svg`` set the rest of
    the app's buttons use (see that directory's UPSTREAM.md) -- this picker
    needs the whole icon library to search across, so it gets its own copy
    via ``scripts/vendor_tabler_icon_glyphs.py``.
    """
    return tuple(sorted(p.stem for p in _GLYPH_DIR.glob('*.svg')))


@lru_cache(maxsize=4096)
def _glyph_bundle(name, size, colour):
    path = _GLYPH_DIR / (name + '.svg')
    colour_bytes = str(colour).encode('ascii')
    svg = path.read_bytes().replace(b'currentColor', colour_bytes)
    bundle = wx.BitmapBundle.FromSVG(svg, wx.Size(int(size), int(size)))
    if not bundle.IsOk():
        raise ValueError('Unable to load Tabler icon: %s' % path)
    return bundle


def _contrast_colour(colour):
    r, g, b = colour[:3]
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return "#FFFFFF" if luminance < 140 else "#1A1A1A"


def _wx_bitmap_to_pil(bitmap):
    wx_image = bitmap.ConvertToImage()
    size = (wx_image.GetWidth(), wx_image.GetHeight())
    img = Image.frombytes('RGB', size, bytes(wx_image.GetData())).convert('RGBA')
    if wx_image.HasAlpha():
        img.putalpha(Image.frombytes('L', size, bytes(wx_image.GetAlpha())))
    return img


# Glyph layout (centre as a fraction of the icon size) and glyph scale, keyed
# by how many icons are placed -- 1 centred, 2 side by side, 3 in a triangle,
# 4 in a grid.
_GLYPH_LAYOUTS = {
    1: [(0.5, 0.5)],
    2: [(0.28, 0.5), (0.72, 0.5)],
    3: [(0.5, 0.28), (0.28, 0.72), (0.72, 0.72)],
    4: [(0.28, 0.28), (0.72, 0.28), (0.28, 0.72), (0.72, 0.72)],
}
_GLYPH_SCALE = {1: 0.5, 2: 0.34, 3: 0.3, 4: 0.26}


def glyph_layout(count, size, scale=1.0):
    """(positions, glyph_size) for ``count`` glyphs on a ``size`` px icon.

    Used to seed the default placement of freshly added glyph layers, and by
    the flat ``compose_template_icon`` shorthand.
    """
    count = max(1, min(count, MAX_TEMPLATE_GLYPHS))
    positions = _GLYPH_LAYOUTS[count]
    base = _GLYPH_SCALE[count] * max(0.25, min(float(scale), 2.5))
    glyph_size = max(6, min(int(size * base), size))
    return positions, glyph_size


@dataclass(frozen=True)
class IconLayer:
    """One movable thing on an icon: a Tabler glyph or a run of text.

    ``x``/``y`` are the layer centre as a fraction of the icon, so a layout
    survives being rendered at preview scale and at the real 44 px size.
    ``colour`` of None means "whatever reads on this background".
    """

    kind: str = LAYER_GLYPH
    value: str = ''
    colour: tuple = None
    x: float = 0.5
    y: float = 0.5
    scale: float = 1.0
    font: str = None
    bold: bool = False
    italic: bool = False

    @property
    def label(self):
        return self.value or ('?' if self.kind == LAYER_GLYPH else '""')

    def moved(self, x, y):
        return replace(self, x=min(1.0, max(0.0, x)), y=min(1.0, max(0.0, y)))


def glyph_layers(icon_names, scale=1.0):
    """Default-placed glyph layers for a plain list of icon names."""
    names = [n for n in icon_names if n][:MAX_TEMPLATE_GLYPHS]
    if not names:
        return ()
    positions, _size = glyph_layout(len(names), 44, scale)
    factor = _GLYPH_SCALE[len(names)] / _GLYPH_SCALE[1] * scale
    return tuple(
        IconLayer(kind=LAYER_GLYPH, value=name, x=fx, y=fy, scale=factor)
        for name, (fx, fy) in zip(names, positions)
    )


def _ink_for(layer_colour, background_colour):
    if layer_colour is None:
        return _contrast_colour(background_colour)
    return '#%02X%02X%02X' % tuple(layer_colour[:3])


def _wx_font(layer, pixel_size):
    return wx.Font(
        wx.FontInfo(max(4, int(pixel_size)))
        .FaceName(layer.font or '')
        .Bold(bool(layer.bold))
        .Italic(bool(layer.italic))
    )


def _text_layer_image(layer, pixel_size, ink):
    """Render text to a tight RGBA image using the installed system fonts.

    Drawn as black-on-white through a plain DC and turned into an alpha mask,
    rather than relying on a transparent DC: alpha-capable device contexts
    behave differently per platform, a greyscale mask does not, and it keeps
    the antialiasing.
    """
    text = layer.value or ''
    if not text.strip():
        return None
    font = _wx_font(layer, pixel_size)
    measure = wx.MemoryDC()
    measure.SetFont(font)
    width, height = measure.GetTextExtent(text)
    measure.SelectObject(wx.NullBitmap)
    if width <= 0 or height <= 0:
        return None

    bitmap = wx.Bitmap(width, height)
    dc = wx.MemoryDC(bitmap)
    dc.SetBackground(wx.Brush(wx.Colour(255, 255, 255)))
    dc.Clear()
    dc.SetFont(font)
    dc.SetTextForeground(wx.Colour(0, 0, 0))
    dc.DrawText(text, 0, 0)
    dc.SelectObject(wx.NullBitmap)

    mask = ImageOps.invert(_wx_bitmap_to_pil(bitmap).convert('L'))
    rgb = ImageColor.getrgb(ink)
    image = Image.new('RGBA', (width, height), rgb + (0,))
    image.putalpha(mask)
    return image


def _layer_image(layer, size, background_colour):
    """The RGBA picture for one layer, already at its final pixel size."""
    ink = _ink_for(layer.colour, background_colour)
    scale = max(0.1, min(float(layer.scale), 3.0))
    if layer.kind == LAYER_TEXT:
        return _text_layer_image(layer, size * 0.45 * scale, ink)
    glyph_size = max(6, min(int(size * _GLYPH_SCALE[1] * scale), size * 3))
    try:
        bundle = _glyph_bundle(layer.value, glyph_size, ink)
    except Exception:
        return None
    return _wx_bitmap_to_pil(bundle.GetBitmap(wx.Size(glyph_size, glyph_size)))


def render_icon(layers, colour, size=44, style=ICON_STYLE_FOLDER, accent=None, border=False):
    """``(image, boxes)`` -- the composed icon plus each layer's pixel bounds.

    The boxes are what makes the preview draggable: the dialog hit-tests them
    instead of guessing where a glyph ended up.
    """
    base = generate_template_icon_source(colour, size, style=style, accent=accent,
                                         border=border).convert('RGBA')
    boxes = []
    for index, layer in enumerate(layers or ()):
        image = _layer_image(layer, size, colour)
        if image is None:
            boxes.append(None)
            continue
        width, height = image.size
        x = int(size * layer.x - width / 2)
        y = int(size * layer.y - height / 2)
        base.alpha_composite(image, (x, y))
        boxes.append((index, x, y, x + width, y + height))
    return base.convert('RGB'), boxes


def compose_icon(layers, colour, size=44, style=ICON_STYLE_FOLDER, accent=None, border=False):
    return render_icon(layers, colour, size, style=style, accent=accent, border=border)[0]


def compose_template_icon(icon_names, colour, size=44, style=ICON_STYLE_FOLDER, accent=None,
                          glyph_colour=None, glyph_scale=1.0, border=False):
    """Background in ``colour`` plus up to 4 default-placed Tabler glyphs.

    The flat shorthand for callers that do not care about layer placement;
    everything it does is a ``render_icon`` call with generated layers.
    """
    layers = tuple(
        replace(layer, colour=glyph_colour)
        for layer in glyph_layers(icon_names, glyph_scale)
    )
    return compose_icon(layers, colour, size, style=style, accent=accent, border=border)


@dataclass(frozen=True)
class TemplateIconSettings:
    """Everything the generator needs, so an icon can be re-edited later."""

    layers: tuple = ()
    colour: tuple = (66, 133, 199)
    accent: tuple = None
    style: str = ICON_STYLE_FOLDER
    border: bool = False

    def render(self, size=44):
        return compose_icon(self.layers, self.colour, size, style=self.style,
                            accent=self.accent, border=self.border)

    @classmethod
    def from_icons(cls, icon_names, colour=(66, 133, 199), **kwargs):
        return cls(layers=glyph_layers(icon_names), colour=colour, **kwargs)


class IconPreviewCanvas(wx.Panel):
    """Zoomed icon preview whose layers can be dragged into place."""

    def __init__(self, parent, scale=5, on_move=None, on_select=None):
        wx.Panel.__init__(self, parent, -1, size=(44 * scale, 44 * scale), style=wx.BORDER_SIMPLE)
        self.scale = scale
        self.on_move = on_move
        self.on_select = on_select
        self._bitmap = None
        self._boxes = []
        self._selected = -1
        self._drag = None
        self.SetMinSize((44 * scale, 44 * scale))
        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_LEFT_DOWN, self._on_down)
        self.Bind(wx.EVT_LEFT_UP, self._on_up)
        self.Bind(wx.EVT_MOTION, self._on_motion)
        self.Bind(wx.EVT_MOUSE_CAPTURE_LOST, lambda _evt: self._end_drag())

    def SetIcon(self, image, boxes, selected=-1):
        big = image.resize((44 * self.scale, 44 * self.scale), Resampling.NEAREST)
        self._bitmap = _pil_to_bitmap(big)
        self._boxes = [box for box in boxes if box is not None]
        self._selected = selected
        self.Refresh()

    def _on_paint(self, _event):
        dc = wx.PaintDC(self)
        if self._bitmap is None:
            return
        dc.DrawBitmap(self._bitmap, 0, 0)
        for index, x0, y0, x1, y1 in self._boxes:
            if index != self._selected:
                continue
            dc.SetPen(wx.Pen(wx.Colour(255, 255, 255), 1, wx.PENSTYLE_SHORT_DASH))
            dc.SetBrush(wx.TRANSPARENT_BRUSH)
            dc.DrawRectangle(x0 * self.scale, y0 * self.scale,
                             (x1 - x0) * self.scale, (y1 - y0) * self.scale)

    def _hit(self, position):
        x = position.x / self.scale
        y = position.y / self.scale
        for index, x0, y0, x1, y1 in reversed(self._boxes):
            if x0 <= x <= x1 and y0 <= y <= y1:
                return index
        return -1

    def _on_down(self, event):
        index = self._hit(event.GetPosition())
        if index < 0:
            return
        self._selected = index
        self._drag = index
        if not self.HasCapture():
            self.CaptureMouse()
        if self.on_select:
            self.on_select(index)
        self.Refresh()

    def _on_motion(self, event):
        if self._drag is None or not event.Dragging():
            return
        position = event.GetPosition()
        if self.on_move:
            self.on_move(self._drag,
                         position.x / (44.0 * self.scale),
                         position.y / (44.0 * self.scale))

    def _on_up(self, _event):
        self._end_drag()

    def _end_drag(self):
        self._drag = None
        if self.HasCapture():
            self.ReleaseMouse()


@lru_cache(maxsize=1)
def _installed_font_names():
    """Face names wx can render with, for the text layer's font dropdown.

    '@'-prefixed faces are the vertical-writing CJK variants Windows lists;
    they render sideways and are never what someone picking a menu-icon font
    is after.
    """
    try:
        faces = [name for name in wx.FontEnumerator.GetFacenames() if not name.startswith('@')]
    except Exception:
        faces = []
    return tuple(sorted(set(faces)))


@lru_cache(maxsize=1)
def _default_font_name():
    available = _installed_font_names()
    for preferred in ('Arial', 'Segoe UI', 'Tahoma', 'Verdana', 'DejaVu Sans'):
        if preferred in available:
            return preferred
    if available:
        return available[0]
    return None


@lru_cache(maxsize=1)
def _starter_gallery_names():
    """The app's own curated Tabler subset, shown before the user searches."""
    curated = asset_path('vendor', 'tabler-icons', 'svg')
    available = set(list_tabler_icon_names())
    if not curated.is_dir():
        return tuple(sorted(available)[:120])
    return tuple(sorted(p.stem for p in curated.glob('*.svg') if p.stem in available))


def _pil_to_bitmap(image):
    image = image.convert('RGB')
    wx_image = wx.Image(image.size[0], image.size[1])
    wx_image.SetData(image.tobytes())
    return wx_image.ConvertToBitmap()


class TemplateIconDialog(wx.Dialog):
    """A small icon editor: a background, plus movable glyph and text layers."""

    _GALLERY_ICON_SIZE = 28
    _GALLERY_LIMIT = 150

    def __init__(self, parent, initial_colour=(66, 133, 199), settings=None):
        wx.Dialog.__init__(
            self, parent, -1, LEXTemplateIconDialogTitle,
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        settings = settings or TemplateIconSettings(colour=tuple(initial_colour))
        self._names = list_tabler_icon_names()
        self._layers = list(settings.layers)
        self._selected = 0 if self._layers else -1
        self._gallery_names = []
        self._updating = False

        columns = wx.BoxSizer(wx.HORIZONTAL)
        columns.Add(self._build_gallery(), 1, wx.EXPAND | wx.ALL, 8)
        columns.Add(self._build_canvas(settings), 0, wx.EXPAND | wx.TOP | wx.BOTTOM, 8)
        columns.Add(self._build_layers(), 0, wx.EXPAND | wx.ALL, 8)

        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(columns, 1, wx.EXPAND)
        outer.Add(dialog_button_sizer(self), 0, wx.EXPAND | wx.ALL, 10)
        self.SetSizerAndFit(outer)
        self.SetMinSize((1040, 640))
        self.CentreOnParent()

        self._refresh_gallery()
        self._refresh_layer_list()
        self._update_preview()

    # -- construction -------------------------------------------------------

    def _build_gallery(self):
        column = wx.BoxSizer(wx.VERTICAL)
        self.search = wx.SearchCtrl(self, -1, style=wx.TE_PROCESS_ENTER)
        self.search.SetDescriptiveText(LEXTemplateIconSearchHint)
        self.search.ShowCancelButton(True)
        column.Add(self.search, 0, wx.EXPAND | wx.BOTTOM, 6)

        self.gallery = wx.ListCtrl(self, -1, style=wx.LC_ICON | wx.LC_SINGLE_SEL | wx.LC_AUTOARRANGE)
        self.gallery.SetMinSize((300, 380))
        column.Add(self.gallery, 1, wx.EXPAND)

        self.galleryStatus = wx.StaticText(self, -1, "")
        column.Add(self.galleryStatus, 0, wx.TOP, 4)

        add_row = wx.BoxSizer(wx.HORIZONTAL)
        self.addGlyphButton = wx.Button(self, -1, LEXTemplateIconAddIcon)
        set_button_icon(self.addGlyphButton, "plus")
        add_row.Add(self.addGlyphButton, 0, wx.RIGHT, 4)
        self.addTextButton = wx.Button(self, -1, LEXTemplateIconAddText)
        add_row.Add(self.addTextButton, 0)
        column.Add(add_row, 0, wx.TOP, 6)

        self.search.Bind(wx.EVT_TEXT, lambda _evt: self._refresh_gallery())
        self.search.Bind(wx.EVT_SEARCHCTRL_CANCEL_BTN, self._on_search_cancel)
        self.gallery.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _evt: self._add_glyph_layer())
        self.addGlyphButton.Bind(wx.EVT_BUTTON, lambda _evt: self._add_glyph_layer())
        self.addTextButton.Bind(wx.EVT_BUTTON, lambda _evt: self._add_text_layer())
        return column

    def _build_canvas(self, settings):
        column = wx.BoxSizer(wx.VERTICAL)
        self.canvas = IconPreviewCanvas(self, scale=6, on_move=self._on_layer_dragged,
                                        on_select=self._on_canvas_select)
        column.Add(self.canvas, 0, wx.ALIGN_CENTER_HORIZONTAL)
        column.Add(wx.StaticText(self, -1, LEXTemplateIconDragHint), 0,
                   wx.ALIGN_CENTER_HORIZONTAL | wx.TOP, 4)
        self.stripPreview = wx.StaticBitmap(self, size=(44 * 4, 44))
        column.Add(self.stripPreview, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.TOP, 8)

        grid = wx.FlexGridSizer(cols=2, vgap=6, hgap=8)
        grid.AddGrowableCol(1)

        grid.Add(wx.StaticText(self, label=LEXTemplateIconPresetLabel), 0, wx.ALIGN_CENTER_VERTICAL)
        self.presetChoice = wx.Choice(self, -1, choices=[LEXTemplateIconPickPreset] + list(LEXTemplateIconPresetNames))
        self.presetChoice.SetSelection(0)
        grid.Add(self.presetChoice, 1, wx.EXPAND)

        grid.Add(wx.StaticText(self, label=LEXTemplateIconStyleLabel), 0, wx.ALIGN_CENTER_VERTICAL)
        self.styleChoice = wx.Choice(self, -1, choices=list(LEXTemplateIconStyleNames))
        self.styleChoice.SetSelection(ICON_STYLES.index(settings.style) if settings.style in ICON_STYLES else 0)
        grid.Add(self.styleChoice, 1, wx.EXPAND)

        grid.Add(wx.StaticText(self, label=LEXTemplateIconColourLabel), 0, wx.ALIGN_CENTER_VERTICAL)
        self.colourPicker = wx.ColourPickerCtrl(self, -1, wx.Colour(*settings.colour))
        grid.Add(self.colourPicker, 1, wx.EXPAND)

        grid.Add(wx.StaticText(self, label=LEXTemplateIconAccentLabel), 0, wx.ALIGN_CENTER_VERTICAL)
        accent_row = wx.BoxSizer(wx.HORIZONTAL)
        self.accentAuto = wx.CheckBox(self, -1, LEXTemplateIconAuto)
        self.accentAuto.SetValue(settings.accent is None)
        accent_row.Add(self.accentAuto, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        self.accentPicker = wx.ColourPickerCtrl(
            self, -1, wx.Colour(*(settings.accent or default_accent_colour(settings.colour))))
        accent_row.Add(self.accentPicker, 1, wx.EXPAND)
        grid.Add(accent_row, 1, wx.EXPAND)

        grid.AddSpacer(0)
        self.borderCheck = wx.CheckBox(self, -1, LEXTemplateIconBorder)
        self.borderCheck.SetValue(bool(settings.border))
        grid.Add(self.borderCheck, 0)
        column.Add(grid, 0, wx.EXPAND | wx.TOP, 10)

        swatches = wx.BoxSizer(wx.HORIZONTAL)
        for _name, colour in SUBMENU_ICON_TEMPLATES:
            button = wx.Button(self, -1, size=(24, 22))
            button.SetBackgroundColour(wx.Colour(*colour))
            button.SetToolTip(LEXTemplateIconSwatchTip)
            button.Bind(wx.EVT_BUTTON, lambda _evt, c=colour: self._apply_colour(c))
            swatches.Add(button, 0, wx.RIGHT, 2)
        self.randomButton = wx.Button(self, -1, LEXTemplateIconRandomize)
        set_button_icon(self.randomButton, "wand")
        swatches.Add(self.randomButton, 0, wx.LEFT, 8)
        column.Add(swatches, 0, wx.TOP, 8)

        self.presetChoice.Bind(wx.EVT_CHOICE, self._on_preset)
        self.styleChoice.Bind(wx.EVT_CHOICE, lambda _evt: self._update_preview())
        self.colourPicker.Bind(wx.EVT_COLOURPICKER_CHANGED, lambda _evt: self._on_colour_changed())
        self.accentPicker.Bind(wx.EVT_COLOURPICKER_CHANGED, lambda _evt: self._on_accent_edited())
        self.accentAuto.Bind(wx.EVT_CHECKBOX, lambda _evt: self._update_preview())
        self.borderCheck.Bind(wx.EVT_CHECKBOX, lambda _evt: self._update_preview())
        self.randomButton.Bind(wx.EVT_BUTTON, lambda _evt: self._randomize())
        return column

    def _build_layers(self):
        column = wx.BoxSizer(wx.VERTICAL)
        column.Add(wx.StaticText(self, label=LEXTemplateIconLayersLabel), 0, wx.BOTTOM, 2)
        self.layerList = wx.ListBox(self, -1, size=(240, 120))
        column.Add(self.layerList, 0, wx.EXPAND)

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        self.removeButton = wx.Button(self, -1, LEXTemplateIconRemove)
        self.upButton = wx.Button(self, -1, "▲", size=(34, -1))
        self.downButton = wx.Button(self, -1, "▼", size=(34, -1))
        self.clearButton = wx.Button(self, -1, LEXTemplateIconClear)
        for button in (self.removeButton, self.upButton, self.downButton, self.clearButton):
            buttons.Add(button, 0, wx.RIGHT, 4)
        column.Add(buttons, 0, wx.TOP | wx.BOTTOM, 4)

        box = wx.StaticBoxSizer(wx.StaticBox(self, label=LEXTemplateIconLayerLabel), wx.VERTICAL)
        host = box.GetStaticBox()
        grid = wx.FlexGridSizer(cols=2, vgap=6, hgap=8)
        grid.AddGrowableCol(1)

        grid.Add(wx.StaticText(host, label=LEXTemplateIconTextLabel), 0, wx.ALIGN_CENTER_VERTICAL)
        self.textCtrl = wx.TextCtrl(host, -1, "")
        grid.Add(self.textCtrl, 1, wx.EXPAND)

        grid.Add(wx.StaticText(host, label=LEXTemplateIconFontLabel), 0, wx.ALIGN_CENTER_VERTICAL)
        self.fontChoice = wx.ComboBox(host, -1, choices=list(_installed_font_names()), style=wx.CB_DROPDOWN)
        grid.Add(self.fontChoice, 1, wx.EXPAND)

        grid.AddSpacer(0)
        emphasis = wx.BoxSizer(wx.HORIZONTAL)
        self.boldCheck = wx.CheckBox(host, -1, LEXTemplateIconBold)
        self.italicCheck = wx.CheckBox(host, -1, LEXTemplateIconItalic)
        emphasis.Add(self.boldCheck, 0, wx.RIGHT, 8)
        emphasis.Add(self.italicCheck, 0)
        grid.Add(emphasis, 0)

        grid.Add(wx.StaticText(host, label=LEXTemplateIconLayerColourLabel), 0, wx.ALIGN_CENTER_VERTICAL)
        colour_row = wx.BoxSizer(wx.HORIZONTAL)
        self.layerColourAuto = wx.CheckBox(host, -1, LEXTemplateIconAuto)
        self.layerColourAuto.SetValue(True)
        colour_row.Add(self.layerColourAuto, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        self.layerColourPicker = wx.ColourPickerCtrl(host, -1, wx.Colour(255, 255, 255))
        colour_row.Add(self.layerColourPicker, 1, wx.EXPAND)
        grid.Add(colour_row, 1, wx.EXPAND)

        grid.Add(wx.StaticText(host, label=LEXTemplateIconScaleLabel), 0, wx.ALIGN_CENTER_VERTICAL)
        self.scaleSlider = wx.Slider(host, -1, 100, 15, 300)
        grid.Add(self.scaleSlider, 1, wx.EXPAND)

        grid.Add(wx.StaticText(host, label=LEXTemplateIconPositionLabel), 0, wx.ALIGN_CENTER_VERTICAL)
        position_row = wx.BoxSizer(wx.HORIZONTAL)
        self.xSpin = wx.SpinCtrl(host, -1, min=0, max=100, initial=50, size=(64, -1))
        self.ySpin = wx.SpinCtrl(host, -1, min=0, max=100, initial=50, size=(64, -1))
        position_row.Add(self.xSpin, 0, wx.RIGHT, 4)
        position_row.Add(self.ySpin, 0, wx.RIGHT, 8)
        self.centreButton = wx.Button(host, -1, LEXTemplateIconCentre)
        position_row.Add(self.centreButton, 0)
        grid.Add(position_row, 1, wx.EXPAND)

        box.Add(grid, 0, wx.EXPAND | wx.ALL, 6)
        column.Add(box, 0, wx.EXPAND | wx.TOP, 4)
        self.arrangeButton = wx.Button(self, -1, LEXTemplateIconArrange)
        column.Add(self.arrangeButton, 0, wx.TOP, 8)

        self.layerList.Bind(wx.EVT_LISTBOX, self._on_layer_selected)
        self.removeButton.Bind(wx.EVT_BUTTON, lambda _evt: self._remove_layer())
        self.upButton.Bind(wx.EVT_BUTTON, lambda _evt: self._move_layer(-1))
        self.downButton.Bind(wx.EVT_BUTTON, lambda _evt: self._move_layer(1))
        self.clearButton.Bind(wx.EVT_BUTTON, lambda _evt: self._clear_layers())
        self.textCtrl.Bind(wx.EVT_TEXT, lambda _evt: self._apply_layer_edit())
        self.fontChoice.Bind(wx.EVT_COMBOBOX, lambda _evt: self._apply_layer_edit())
        self.fontChoice.Bind(wx.EVT_TEXT, lambda _evt: self._apply_layer_edit())
        self.boldCheck.Bind(wx.EVT_CHECKBOX, lambda _evt: self._apply_layer_edit())
        self.italicCheck.Bind(wx.EVT_CHECKBOX, lambda _evt: self._apply_layer_edit())
        self.layerColourAuto.Bind(wx.EVT_CHECKBOX, lambda _evt: self._apply_layer_edit())
        self.layerColourPicker.Bind(wx.EVT_COLOURPICKER_CHANGED, self._on_layer_colour_picked)
        self.scaleSlider.Bind(wx.EVT_SLIDER, lambda _evt: self._apply_layer_edit())
        self.xSpin.Bind(wx.EVT_SPINCTRL, lambda _evt: self._apply_layer_edit())
        self.ySpin.Bind(wx.EVT_SPINCTRL, lambda _evt: self._apply_layer_edit())
        self.centreButton.Bind(wx.EVT_BUTTON, lambda _evt: self._centre_layer())
        self.arrangeButton.Bind(wx.EVT_BUTTON, lambda _evt: self._auto_arrange())
        return column

    # -- gallery ------------------------------------------------------------

    def _on_search_cancel(self, event):
        self.search.SetValue("")
        self._refresh_gallery()
        event.Skip()

    def _refresh_gallery(self):
        query = self.search.GetValue().strip().lower().replace(" ", "-")
        if query:
            matches = [n for n in self._names if query in n]
            total = len(matches)
            matches = matches[:self._GALLERY_LIMIT]
        else:
            matches = list(_starter_gallery_names())
            total = len(matches)
        self._gallery_names = matches

        size = self._GALLERY_ICON_SIZE
        ink = self._gallery_ink()
        images = wx.ImageList(size, size, True)
        wx.BeginBusyCursor()
        self.gallery.Freeze()
        try:
            self.gallery.ClearAll()
            for name in matches:
                try:
                    images.Add(_glyph_bundle(name, size, ink).GetBitmap(wx.Size(size, size)))
                except Exception:
                    images.Add(wx.Bitmap(size, size))
            self.gallery.AssignImageList(images, wx.IMAGE_LIST_NORMAL)
            for index, name in enumerate(matches):
                self.gallery.InsertItem(index, name, index)
        finally:
            self.gallery.Thaw()
            wx.EndBusyCursor()
        if query and total > len(matches):
            self.galleryStatus.SetLabel(LEXTemplateIconMatchesTruncated % (len(matches), total))
        else:
            self.galleryStatus.SetLabel(LEXTemplateIconMatches % len(matches))

    def _gallery_ink(self):
        colour = wx.SystemSettings.GetColour(wx.SYS_COLOUR_LISTBOXTEXT)
        return '#%02X%02X%02X' % (colour.Red(), colour.Green(), colour.Blue())

    def _selected_gallery_name(self):
        index = self.gallery.GetFirstSelected()
        if index == wx.NOT_FOUND or index >= len(self._gallery_names):
            return None
        return self._gallery_names[index]

    # -- layers -------------------------------------------------------------

    def _add_layer(self, layer):
        if len(self._layers) >= MAX_ICON_LAYERS:
            wx.MessageBox(LEXTemplateIconLayersFull % MAX_ICON_LAYERS, LEXTemplateIconDialogTitle,
                          wx.OK | wx.ICON_INFORMATION, self)
            return
        self._layers.append(layer)
        self._selected = len(self._layers) - 1
        self._refresh_layer_list()
        self._update_preview()

    def _add_glyph_layer(self):
        name = self._selected_gallery_name()
        if name is None:
            wx.MessageBox(LEXTemplateIconPickIconFirst, LEXTemplateIconDialogTitle,
                          wx.OK | wx.ICON_INFORMATION, self)
            return
        # Drop the new glyph on the free slot of the stock grid for the count
        # it brings the icon to, so glyphs do not pile up on the centre.
        # Layers already placed by hand stay where they are; "Auto-arrange"
        # is there for when the user wants the whole grid re-flowed.
        count = min(sum(1 for layer in self._layers if layer.kind == LAYER_GLYPH) + 1,
                    MAX_TEMPLATE_GLYPHS)
        positions = _GLYPH_LAYOUTS[count]
        fx, fy = positions[count - 1]
        self._add_layer(IconLayer(kind=LAYER_GLYPH, value=name, x=fx, y=fy,
                                  scale=_GLYPH_SCALE[count] / _GLYPH_SCALE[1]))

    def _add_text_layer(self):
        self._add_layer(IconLayer(kind=LAYER_TEXT, value=LEXTemplateIconNewText,
                                  font=_default_font_name(), scale=0.8, y=0.75))

    def _remove_layer(self):
        if not (0 <= self._selected < len(self._layers)):
            return
        del self._layers[self._selected]
        self._selected = min(self._selected, len(self._layers) - 1)
        self._refresh_layer_list()
        self._update_preview()

    def _move_layer(self, delta):
        index = self._selected
        target = index + delta
        if not (0 <= index < len(self._layers)) or not (0 <= target < len(self._layers)):
            return
        self._layers[index], self._layers[target] = self._layers[target], self._layers[index]
        self._selected = target
        self._refresh_layer_list()
        self._update_preview()

    def _clear_layers(self):
        self._layers = []
        self._selected = -1
        self._refresh_layer_list()
        self._update_preview()

    def _auto_arrange(self):
        """Spread the glyph layers back over the stock 1/2/3/4 grid."""
        glyphs = [i for i, layer in enumerate(self._layers) if layer.kind == LAYER_GLYPH]
        if not glyphs:
            return
        positions, _size = glyph_layout(len(glyphs), 44)
        factor = _GLYPH_SCALE[min(len(glyphs), MAX_TEMPLATE_GLYPHS)] / _GLYPH_SCALE[1]
        for slot, index in enumerate(glyphs[:len(positions)]):
            fx, fy = positions[slot]
            self._layers[index] = replace(self._layers[index], x=fx, y=fy, scale=factor)
        self._refresh_layer_list()
        self._update_preview()

    def _centre_layer(self):
        if 0 <= self._selected < len(self._layers):
            self._layers[self._selected] = self._layers[self._selected].moved(0.5, 0.5)
            self._sync_layer_editor()
            self._update_preview()

    def _refresh_layer_list(self):
        labels = []
        for layer in self._layers:
            prefix = LEXTemplateIconTextTag if layer.kind == LAYER_TEXT else LEXTemplateIconIconTag
            labels.append("%s  %s" % (prefix, layer.label))
        self.layerList.Set(labels)
        if 0 <= self._selected < len(labels):
            self.layerList.SetSelection(self._selected)
        for button in (self.removeButton, self.upButton, self.downButton, self.clearButton):
            button.Enable(bool(self._layers))
        self._sync_layer_editor()

    def _current_layer(self):
        if 0 <= self._selected < len(self._layers):
            return self._layers[self._selected]
        return None

    def _sync_layer_editor(self):
        """Push the selected layer into the editor without echoing events back."""
        layer = self._current_layer()
        self._updating = True
        try:
            is_text = layer is not None and layer.kind == LAYER_TEXT
            for control in (self.textCtrl, self.fontChoice, self.boldCheck, self.italicCheck):
                control.Enable(is_text)
            for control in (self.layerColourAuto, self.layerColourPicker, self.scaleSlider,
                            self.xSpin, self.ySpin, self.centreButton):
                control.Enable(layer is not None)
            if layer is None:
                self.textCtrl.SetValue("")
                return
            # Disabled for glyph layers, but still shows the icon name there.
            self.textCtrl.SetValue(layer.value)
            self.fontChoice.SetValue(layer.font or "")
            self.boldCheck.SetValue(bool(layer.bold))
            self.italicCheck.SetValue(bool(layer.italic))
            self.layerColourAuto.SetValue(layer.colour is None)
            if layer.colour is not None:
                self.layerColourPicker.SetColour(wx.Colour(*layer.colour))
            self.scaleSlider.SetValue(int(round(layer.scale * 100)))
            self.xSpin.SetValue(int(round(layer.x * 100)))
            self.ySpin.SetValue(int(round(layer.y * 100)))
        finally:
            self._updating = False

    def _on_layer_selected(self, event):
        self._selected = self.layerList.GetSelection()
        self._sync_layer_editor()
        self._update_preview()
        event.Skip()

    def _on_canvas_select(self, index):
        self._selected = index
        self.layerList.SetSelection(index)
        self._sync_layer_editor()

    def _on_layer_dragged(self, index, x, y):
        if 0 <= index < len(self._layers):
            self._layers[index] = self._layers[index].moved(x, y)
            self._selected = index
            self._sync_layer_editor()
            self._update_preview()

    def _on_layer_colour_picked(self, event):
        self.layerColourAuto.SetValue(False)
        self._apply_layer_edit()
        event.Skip()

    def _apply_layer_edit(self):
        if self._updating:
            return
        layer = self._current_layer()
        if layer is None:
            return
        colour = None if self.layerColourAuto.GetValue() else self._colour_of(self.layerColourPicker)
        updated = replace(
            layer,
            value=self.textCtrl.GetValue() if layer.kind == LAYER_TEXT else layer.value,
            font=(self.fontChoice.GetValue() or None) if layer.kind == LAYER_TEXT else layer.font,
            bold=self.boldCheck.GetValue() if layer.kind == LAYER_TEXT else layer.bold,
            italic=self.italicCheck.GetValue() if layer.kind == LAYER_TEXT else layer.italic,
            colour=colour,
            scale=self.scaleSlider.GetValue() / 100.0,
            x=self.xSpin.GetValue() / 100.0,
            y=self.ySpin.GetValue() / 100.0,
        )
        self._layers[self._selected] = updated
        label_changed = updated.label != layer.label
        if label_changed:
            selection = self._selected
            self._refresh_layer_list()
            self._selected = selection
        self._update_preview()

    # -- background ---------------------------------------------------------

    def _colour_of(self, picker):
        colour = picker.GetColour()
        return (colour.Red(), colour.Green(), colour.Blue())

    def _apply_colour(self, colour):
        self.colourPicker.SetColour(wx.Colour(*colour))
        self._on_colour_changed()

    def _on_colour_changed(self):
        if self.accentAuto.GetValue():
            self.accentPicker.SetColour(wx.Colour(*default_accent_colour(self._colour_of(self.colourPicker))))
        self._update_preview()

    def _on_accent_edited(self):
        self.accentAuto.SetValue(False)
        self._update_preview()

    def _on_preset(self, event):
        index = self.presetChoice.GetSelection() - 1
        if 0 <= index < len(ICON_PRESETS):
            _name, style, colour, accent = ICON_PRESETS[index]
            self.styleChoice.SetSelection(ICON_STYLES.index(style))
            self.colourPicker.SetColour(wx.Colour(*colour))
            self.accentAuto.SetValue(accent is None)
            self.accentPicker.SetColour(wx.Colour(*(accent or default_accent_colour(colour))))
            self._update_preview()
        event.Skip()

    def _randomize(self):
        colour = tuple(random.randint(40, 215) for _ in range(3))
        self.styleChoice.SetSelection(random.randrange(len(ICON_STYLES)))
        self.presetChoice.SetSelection(0)
        self._apply_colour(colour)

    # -- result -------------------------------------------------------------

    def GetSettings(self):
        return TemplateIconSettings(
            layers=tuple(self._layers),
            colour=self._colour_of(self.colourPicker),
            accent=None if self.accentAuto.GetValue() else self._colour_of(self.accentPicker),
            style=ICON_STYLES[max(0, self.styleChoice.GetSelection())],
            border=self.borderCheck.GetValue(),
        )

    def _update_preview(self):
        settings = self.GetSettings()
        image, boxes = render_icon(settings.layers, settings.colour, style=settings.style,
                                   accent=settings.accent, border=settings.border)
        self._composed = image
        self.canvas.SetIcon(image, boxes, self._selected)
        self.stripPreview.SetBitmap(_pil_to_bitmap(compose_lot_icon(image)))

    def GetImage(self):
        return getattr(self, "_composed", None)

def open_template_icon_dialog(parent, initial_colour=(66, 133, 199), settings=None):
    """Run the generator. Returns ``(image, settings)``, or ``(None, None)``."""
    dlg = TemplateIconDialog(parent, initial_colour=initial_colour, settings=settings)
    try:
        if dlg.ShowModal() == wx.ID_OK:
            return dlg.GetImage(), dlg.GetSettings()
        return None, None
    finally:
        dlg.Destroy()


class IconDlg(wx.Dialog):

    def __init__(self, parent, img):
        wx.Dialog.__init__(self, parent, -1, IconDlgTitle, size=wx.Size(456, 157), style=wx.CAPTION)
        box_sizer1 = wx.BoxSizer(wx.VERTICAL)
        file_browse = filebrowse.FileBrowseButton(self, -1, changeCallback=self.fbb_callback, labelText=IconDlgPicture,
                                                  buttonText=IconDlgBrowse)
        box_sizer1.Add(file_browse, 0, wx.EXPAND, 5)
        self.bitmap1 = wx.StaticBitmap(self, wx.ID_ANY,
                                       wx.BitmapBundle(wx.Bitmap(str(asset_path('templates', 'IconTpl.png')))))
        box_sizer1.Add(self.bitmap1, 0, wx.ALL | wx.ALIGN_CENTER_HORIZONTAL, 5)
        static_line1 = wx.StaticLine(self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_HORIZONTAL)
        box_sizer1.Add(static_line1, 0, wx.ALL | wx.EXPAND, 5)
        sdb_sizer1 = wx.StdDialogButtonSizer()
        sdb_sizer1_ok = dialog_button(self, wx.ID_OK)
        sdb_sizer1.AddButton(sdb_sizer1_ok)
        sdb_sizer1_cancel = dialog_button(self, wx.ID_CANCEL)
        sdb_sizer1.AddButton(sdb_sizer1_cancel)
        sdb_sizer1.Realize()
        box_sizer1.Add(sdb_sizer1, 0, wx.EXPAND, 5)
        self.SetSizer(box_sizer1)
        self.Layout()
        self.image = img
        if img is not None:
            self.replace_img(img)
        return

    def replace_img(self, icon_image):
        wx_image = wx.Image(44 * 4, 44)
        wx_image.SetData(icon_image.convert('RGB').tobytes())
        self.bitmap1.SetBitmap(wx_image.ConvertToBitmap())

    def fbb_callback(self, event):
        try:
            image = Image.open(event.GetString())
        except Exception:
            return

        icon_image = compose_lot_icon(image)
        self.image = icon_image
        self.replace_img(icon_image)
