from types import SimpleNamespace

import wx

from sc4pimx.SC4SubmenuTreeDlg import SubmenuTreeDialog


class FakeEvent:
    def __init__(self, event_object=None):
        self.event_object = event_object
        self.skipped = False

    def GetEventObject(self):
        return self.event_object

    def Skip(self):
        self.skipped = True


def test_selection_callback_does_not_query_tree_during_rebuild():
    def unexpected_call(*_args):
        raise AssertionError("selection state was queried during tree rebuild")

    dialog = SimpleNamespace(
        _closing=False,
        _rebuilding=True,
        _selected_data=unexpected_call,
        _update_details=unexpected_call,
    )
    event = FakeEvent()

    SubmenuTreeDialog._on_selection(dialog, event)

    assert event.skipped


def test_dialog_teardown_unbinds_native_tree_callbacks():
    class FakeTree:
        def __init__(self):
            self.unbound = []

        def Unbind(self, event_type):
            self.unbound.append(event_type)

    tree = FakeTree()
    dialog = SimpleNamespace(_closing=False, tree=tree)

    SubmenuTreeDialog._deactivate_tree_events(dialog)

    assert dialog._closing
    assert tree.unbound == [
        wx.EVT_TREE_SEL_CHANGED,
        wx.EVT_TREE_ITEM_ACTIVATED,
        wx.EVT_TREE_ITEM_RIGHT_CLICK,
    ]
