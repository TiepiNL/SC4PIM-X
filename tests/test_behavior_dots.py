from types import SimpleNamespace

from sc4pimx.SC4LETools import BEHAVIOR_DOT_COLOURS, LEAssetGrid


def _rows(props):
    exemplar = SimpleNamespace(GetProp=lambda pid: props.get(pid))
    item = SimpleNamespace(kind="prop", source=SimpleNamespace(exemplar=exemplar))
    grid = LEAssetGrid.__new__(LEAssetGrid)
    return grid._prop_behavior_rows(item)


def test_tooltip_lists_each_behavior_with_its_dot_colour():
    rows = _rows({
        0x49C9C93C: (1,),
        0x4A149631: (7, 19),
        0xCA7515CC: (3, 1),
        0x4A751AD5: (40,),
    })

    dot_rows = [row for row in rows if row[0] == "dot"]
    assert [row[1] for row in dot_rows] == [
        BEHAVIOR_DOT_COLOURS["day_night"],
        BEHAVIOR_DOT_COLOURS["timed"],
        BEHAVIOR_DOT_COLOURS["seasonal"],
        BEHAVIOR_DOT_COLOURS["chance"],
    ]


def test_static_prop_has_no_dot_rows():
    rows = _rows({})

    assert [row for row in rows if row[0] == "dot"] == []
