from types import SimpleNamespace

import sc4pimx.SC4LotPreview as preview
from sc4pimx.SC4LotPreview import LotEditorWin


def _editor(**attrs):
    editor = LotEditorWin.__new__(LotEditorWin)
    for key, value in attrs.items():
        setattr(editor, key, value)
    return editor


def test_gated_ambient_pass_clears_stale_actor_mesh():
    editor = _editor(
        _icon_render=False,
        _context_scene=object(),
        _context_ambient_mesh=object(),
        contextTraffic="off",
        contextPedestrians="off",
    )
    editor._is_layer_visible = lambda pane, layer: True

    editor.DrawCityContextAmbient()

    assert editor._context_ambient_mesh is None


def test_zoom_gated_ambient_pass_clears_stale_actor_mesh():
    editor = _editor(
        _icon_render=False,
        _context_scene=object(),
        _context_ambient_mesh=object(),
        contextTraffic="medium",
        contextPedestrians="medium",
        contextDetail="low",
        zoom3D=2,
    )
    editor._is_layer_visible = lambda pane, layer: True

    editor.DrawCityContextAmbient()

    assert editor._context_ambient_mesh is None


def test_pure_atc_viewer_casts_no_shadow():
    atc = preview.ATC(None, None)
    viewer = SimpleNamespace(viewingData=[atc])

    assert LotEditorWin._viewer_casts_shadow(viewer) is False


def test_mixed_state_viewer_still_enters_shadow_pass():
    atc = preview.ATC(None, None)
    viewer = SimpleNamespace(viewingData=[atc, object()])

    assert LotEditorWin._viewer_casts_shadow(viewer) is True
