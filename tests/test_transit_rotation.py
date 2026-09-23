import pytest

from sc4pimx import SC4TransitLotTools as tlt
from sc4pimx.SC4PathReader import SC4PathPoint, point_to_lot_2d
from sc4pimx.translation import LEXFacingEast, LEXFacingNorth, LEXFacingSouth, LEXFacingWest


class _CapturePrimitives:
    def __init__(self):
        self.positions = []

    def lines(self, positions, mvp, color=None, width=None):
        self.positions.extend(positions)


# Tile-local lot coordinates (+y South) of each edge midpoint.
EDGE_AT = {(8, 0): "N", (16, 8): "E", (8, 16): "S", (0, 8): "W"}
LABEL_TO_EDGE = {LEXFacingNorth: "N", LEXFacingEast: "E", LEXFacingSouth: "S", LEXFacingWest: "W"}


def _mask_north_edge(flag):
    primitives = _CapturePrimitives()
    tlt._draw_mask_edges(primitives, None, 0, 0, 0x02000000, flag, (1, 1, 1, 1), 1)
    # Each edge is drawn as centre -> inner -> edge; the last point is the edge.
    x, y = primitives.positions[-1]
    return EDGE_AT[(round(x), round(y))]


def _path_north_edge(flag):
    x, y = point_to_lot_2d(0, 0, flag, SC4PathPoint(0.0, 8.0, 0.0))
    return EDGE_AT[(round(x), round(y))]


@pytest.mark.parametrize("flag", range(4))
def test_mask_path_and_label_agree_on_local_north(flag):
    label = dict(tlt.ROTATION_CHOICES)[flag]
    assert _mask_north_edge(flag) == _path_north_edge(flag) == LABEL_TO_EDGE[label]


def test_rotation_turns_counter_clockwise():
    # Flag 2 is a half turn (SC4Tool, Maxis lots); 1/3 turn N -> W / N -> E,
    # as the flag-3 ramp paths only join up in game that way.
    assert [_path_north_edge(flag) for flag in range(4)] == ["N", "W", "S", "E"]
