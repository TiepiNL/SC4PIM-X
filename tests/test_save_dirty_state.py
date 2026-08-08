from types import SimpleNamespace

from sc4pimx.SC4LotPreview import LotEditorWin
from sc4pimx.SC4PIMApp import NoteBookPanel


def test_mark_dirty_enables_save_and_marks_exemplar_modified():
    calls = []
    panel = NoteBookPanel.__new__(NoteBookPanel)
    panel.exemplar = SimpleNamespace(modified=False)
    panel.bSave = SimpleNamespace(Enable=lambda enabled: calls.append(enabled))

    panel.MarkDirty()

    assert panel.exemplar.modified is True
    assert calls == [True]


def test_lot_editor_save_button_delegates_to_the_parent_tab():
    calls = []
    editor = LotEditorWin.__new__(LotEditorWin)
    editor.descPage = SimpleNamespace(OnSaveTab=lambda event: calls.append(event))

    editor.OnSaveLot(None)

    assert calls == [None]


def test_lot_editor_refresh_marks_the_parent_tab_dirty():
    calls = []
    list_properties = SimpleNamespace(
        Freeze=lambda: calls.append("freeze"),
        DeleteAllItems=lambda: calls.append("delete"),
        Thaw=lambda: calls.append("thaw"),
    )
    desc_page = SimpleNamespace(
        listProperties=list_properties,
        FillTheList=lambda: calls.append("fill"),
        MarkDirty=lambda: calls.append("dirty"),
    )
    editor = LotEditorWin.__new__(LotEditorWin)
    editor.descPage = desc_page

    editor.UpdatePIM()

    assert calls == ["freeze", "delete", "fill", "thaw", "dirty"]
