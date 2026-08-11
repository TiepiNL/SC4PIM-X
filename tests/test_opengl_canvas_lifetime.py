import weakref

from sc4pimx.SC4OpenGL import MyCanvasBase


def test_queued_animation_does_not_call_a_destroying_canvas():
    class FakeCanvas:
        def __init__(self):
            self._destroying = True
            self.called = False

        def _on_animation_frame(self):
            self.called = True

    canvas = FakeCanvas()

    MyCanvasBase._dispatch_animation_frame(weakref.ref(canvas))

    assert not canvas.called


def test_queued_animation_handles_native_deletion_race():
    class FakeCanvas:
        def __init__(self):
            self._destroying = False
            self._frame_call = object()

        def _on_animation_frame(self):
            raise RuntimeError("wrapped C/C++ object has been deleted")

    canvas = FakeCanvas()

    MyCanvasBase._dispatch_animation_frame(weakref.ref(canvas))

    assert canvas._destroying
    assert canvas._frame_call is None


def test_destroy_marks_canvas_dead_before_stopping_queued_frame():
    class FakeFrameCall:
        def __init__(self, canvas):
            self.canvas = canvas
            self.stopped = False

        def Stop(self):
            assert self.canvas._destroying
            self.stopped = True

    class FakeEvent:
        def __init__(self, canvas):
            self.canvas = canvas
            self.skipped = False

        def GetEventObject(self):
            return self.canvas

        def Skip(self):
            self.skipped = True

    class FakeCanvas:
        pass

    canvas = FakeCanvas()
    canvas._destroying = False
    canvas.renderer = None
    frame_call = FakeFrameCall(canvas)
    canvas._frame_call = frame_call
    event = FakeEvent(canvas)

    MyCanvasBase.on_destroy(canvas, event)

    assert canvas._destroying
    assert canvas._frame_call is None
    assert frame_call.stopped
    assert event.skipped
