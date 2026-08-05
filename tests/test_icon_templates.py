"""Icon generator maths. Glyph rendering needs a wx display, so every case
here uses an empty glyph list and only exercises backgrounds and layout."""

import pytest

from sc4pimx.SC4IconMakerDlg import (
    ICON_PRESETS,
    ICON_STYLE_CIRCLE,
    ICON_STYLE_FOLDER,
    ICON_STYLE_GRADIENT,
    ICON_STYLE_PLATE,
    ICON_STYLE_SOLID,
    ICON_STYLES,
    LAYER_GLYPH,
    LAYER_TEXT,
    MAX_TEMPLATE_GLYPHS,
    IconLayer,
    TemplateIconSettings,
    compose_template_icon,
    default_accent_colour,
    generate_template_icon_source,
    glyph_layers,
    glyph_layout,
    render_icon,
)

BLUE = (66, 133, 199)


@pytest.mark.parametrize("style", ICON_STYLES)
def test_every_style_renders_a_44px_rgb_icon(style):
    image = generate_template_icon_source(BLUE, style=style)

    assert image.size == (44, 44)
    assert image.mode == "RGB"


def test_solid_style_is_the_flat_colour():
    image = generate_template_icon_source(BLUE, style=ICON_STYLE_SOLID)

    assert image.getpixel((0, 0)) == BLUE
    assert image.getpixel((43, 43)) == BLUE


def test_gradient_runs_from_the_colour_to_the_accent():
    image = generate_template_icon_source(BLUE, style=ICON_STYLE_GRADIENT, accent=(0, 0, 0))

    assert image.getpixel((22, 0)) == BLUE
    assert image.getpixel((22, 43)) == (0, 0, 0)
    assert image.getpixel((22, 22))[2] < BLUE[2]


def test_circle_keeps_the_backdrop_in_the_corners():
    image = generate_template_icon_source(BLUE, style=ICON_STYLE_CIRCLE, accent=(10, 20, 30))

    assert image.getpixel((0, 0)) == (10, 20, 30)
    assert image.getpixel((22, 22)) == BLUE


def test_plate_style_lightens_the_top_half():
    image = generate_template_icon_source(BLUE, style=ICON_STYLE_PLATE)

    assert image.getpixel((22, 2))[2] > image.getpixel((22, 40))[2]


def test_border_draws_a_contrasting_outline():
    plain = generate_template_icon_source(BLUE, style=ICON_STYLE_SOLID)
    bordered = generate_template_icon_source(BLUE, style=ICON_STYLE_SOLID, border=True)

    assert plain.getpixel((0, 0)) == BLUE
    assert bordered.getpixel((0, 0)) != BLUE
    assert bordered.getpixel((22, 22)) == BLUE


def test_default_accent_is_a_darker_shade():
    accent = default_accent_colour(BLUE)

    assert accent == tuple(int(c * 0.55) for c in BLUE)
    assert all(a < b for a, b in zip(accent, BLUE))


def test_unknown_style_falls_back_to_the_folder_look():
    assert (generate_template_icon_source(BLUE, style="nonsense").tobytes()
            == generate_template_icon_source(BLUE, style=ICON_STYLE_FOLDER).tobytes())


@pytest.mark.parametrize("count,expected", [(1, 1), (2, 2), (3, 3), (4, 4), (7, 4), (0, 1)])
def test_glyph_layout_positions_match_the_glyph_count(count, expected):
    positions, _size = glyph_layout(count, 44)

    assert len(positions) == expected


def test_glyph_layout_scale_is_clamped_to_the_icon():
    _positions, small = glyph_layout(1, 44, 0.01)
    _positions, large = glyph_layout(1, 44, 99)

    assert 6 <= small < large <= 44


def test_glyph_scale_grows_the_glyph_box():
    _positions, normal = glyph_layout(2, 44, 1.0)
    _positions, bigger = glyph_layout(2, 44, 1.8)

    assert bigger > normal


def test_compose_without_glyphs_is_just_the_background():
    composed = compose_template_icon((), BLUE, style=ICON_STYLE_SOLID)

    assert composed.size == (44, 44)
    assert composed.getpixel((22, 22)) == BLUE


def test_compose_ignores_empty_glyph_slots():
    composed = compose_template_icon((None, "", None), BLUE, style=ICON_STYLE_SOLID)

    assert composed.getpixel((22, 22)) == BLUE


def test_settings_round_trip_through_render():
    settings = TemplateIconSettings(colour=BLUE, style=ICON_STYLE_SOLID, border=False)

    assert settings.render(size=64).size == (64, 64)
    assert settings.layers == ()
    assert MAX_TEMPLATE_GLYPHS == 4


# -- layers ------------------------------------------------------------------


def test_glyph_layers_places_each_icon_and_shrinks_them():
    layers = glyph_layers(("trees", "home", "bus"))

    assert [layer.kind for layer in layers] == [LAYER_GLYPH] * 3
    assert [layer.value for layer in layers] == ["trees", "home", "bus"]
    assert {(layer.x, layer.y) for layer in layers} == {(0.5, 0.28), (0.28, 0.72), (0.72, 0.72)}
    assert all(layer.scale < 1.0 for layer in layers)


def test_glyph_layers_caps_at_four_and_drops_blanks():
    assert len(glyph_layers(("a", "b", "c", "d", "e"))) == MAX_TEMPLATE_GLYPHS
    assert glyph_layers((None, "")) == ()


def test_single_glyph_layer_is_centred_at_full_scale():
    (layer,) = glyph_layers(("trees",))

    assert (layer.x, layer.y, layer.scale) == (0.5, 0.5, 1.0)


def test_layer_moved_clamps_into_the_icon():
    layer = IconLayer(kind=LAYER_TEXT, value="Park")

    assert layer.moved(1.4, -0.2).x == 1.0
    assert layer.moved(1.4, -0.2).y == 0.0
    assert layer.moved(0.25, 0.75).x == 0.25


def test_layer_label_survives_an_empty_value():
    assert IconLayer(kind=LAYER_TEXT, value="").label == '""'
    assert IconLayer(kind=LAYER_GLYPH, value="").label == "?"
    assert IconLayer(kind=LAYER_TEXT, value="Park").label == "Park"


def test_render_icon_reports_no_box_for_an_unrenderable_layer():
    image, boxes = render_icon((IconLayer(kind=LAYER_GLYPH, value="definitely-not-an-icon"),),
                               BLUE, style=ICON_STYLE_SOLID)

    assert boxes == [None]
    assert image.getpixel((22, 22)) == BLUE


def test_render_icon_without_layers_returns_an_empty_box_list():
    image, boxes = render_icon((), BLUE, style=ICON_STYLE_SOLID)

    assert boxes == []
    assert image.size == (44, 44)


def test_every_preset_names_a_real_style():
    assert all(preset[1] in ICON_STYLES for preset in ICON_PRESETS)
    assert len({preset[0] for preset in ICON_PRESETS}) == len(ICON_PRESETS)
