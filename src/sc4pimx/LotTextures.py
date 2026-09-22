"""Lot texture loading and base/overlay classification.

A lot texture is five FSH entries (type 0x7AB50E44, group 0x0986135E), one
per zoom level at IIDs ``tex_id + 0`` (zoom 1, lowest resolution) through
``tex_id + 4`` (zoom 5).

Whether a texture is a base or an overlay is decided once for the texture as
a whole: it is an overlay when any pixel at any zoom level is not fully
opaque. FSHConverter detects alpha per image and DXT compression can leave a
few translucent pixels at only some zoom levels, so deciding per image (or
from a single zoom level) let the editor and the asset picker disagree and
could mix opaque and translucent images within one texture.

The texture format is deliberately not used: Maxis overlays use DXT1 (1-bit
alpha) at zoom 5, and fully opaque DXT3 bases exist.
"""
import threading
from typing import List, NamedTuple, Optional

from . import FSHConverter
from .SC4DatTools import snapshot_entry_content

LOT_TEXTURE_TYPE = 0x7AB50E44
LOT_TEXTURE_GROUP = 0x0986135E
ZOOM_LEVELS = 5
# Zoom level whose image represents the texture in the asset picker and the
# lot tree (IID ``tex_id + 3``).
PREVIEW_ZOOM = 3

_cache_lock = threading.Lock()


class LotTextureZoom(NamedTuple):
    """One decoded zoom level: raw RGB and alpha bytes of the first layer."""

    size: tuple
    img: bytes
    alpha: bytes
    has_alpha: bool


class LotTexture(NamedTuple):
    is_overlay: bool
    zooms: List[LotTextureZoom]


def _zoom_entry(virtual_dat, tex_id, zoom):
    return virtual_dat.getEntry(LOT_TEXTURE_TYPE, LOT_TEXTURE_GROUP, tex_id + zoom)


def _decode_zoom(entry):
    content = snapshot_entry_content(entry)
    if content is None:
        raise IOError("Cannot read lot texture 0x%08X" % entry.tgi[2])
    _layers, has_alpha, img, alpha, size = FSHConverter.decodeFSH(content)
    return LotTextureZoom(size, img, alpha, has_alpha)


def _overlay_cache(virtual_dat):
    cache = getattr(virtual_dat, "lotTextureOverlay", None)
    if cache is None:
        cache = virtual_dat.lotTextureOverlay = {}
    return cache


def _remember(virtual_dat, tex_id, is_overlay):
    with _cache_lock:
        _overlay_cache(virtual_dat)[tex_id] = is_overlay


def load_lot_texture(virtual_dat, tex_id) -> Optional[LotTexture]:
    """Decode every zoom level of lot texture ``tex_id`` and classify it.

    Returns ``None`` when a zoom level is missing.
    """
    zooms = []
    for zoom in range(ZOOM_LEVELS):
        entry = _zoom_entry(virtual_dat, tex_id, zoom)
        if entry is None:
            return None
        zooms.append(_decode_zoom(entry))
    is_overlay = any(z.has_alpha for z in zooms)
    _remember(virtual_dat, tex_id, is_overlay)
    return LotTexture(is_overlay, zooms)


def lot_texture_is_overlay(virtual_dat, tex_id) -> bool:
    """Whether lot texture ``tex_id`` is an overlay (see module docstring).

    Stops decoding at the first zoom level with alpha, so most overlays only
    cost their smallest image. Safe to call from worker threads.
    """
    with _cache_lock:
        cached = _overlay_cache(virtual_dat).get(tex_id)
    if cached is not None:
        return cached
    is_overlay = False
    for zoom in range(ZOOM_LEVELS):
        entry = _zoom_entry(virtual_dat, tex_id, zoom)
        if entry is not None and _decode_zoom(entry).has_alpha:
            is_overlay = True
            break
    _remember(virtual_dat, tex_id, is_overlay)
    return is_overlay


def clear_lot_texture_cache(virtual_dat):
    with _cache_lock:
        _overlay_cache(virtual_dat).clear()
