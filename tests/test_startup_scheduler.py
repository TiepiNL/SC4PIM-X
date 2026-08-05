from types import SimpleNamespace

from sc4pimx import SC4LETools, SC4PIMApp


def _frame(steps):
    return SimpleNamespace(
        _startup_steps=iter(steps),
        _startup_timer=object(),
        _advance_startup=lambda: None,
        _finish_startup=lambda: None,
        startupPanel=SimpleNamespace(StopPulse=lambda: None, SetStatus=lambda *_args: None),
        configureMenuItem=SimpleNamespace(Enable=lambda _enabled: None),
    )


def test_advance_startup_consumes_cheap_batches_in_one_slice(monkeypatch):
    finished = []
    scheduled = []
    frame = _frame((None, None, None))
    frame._finish_startup = lambda: finished.append(True)
    monkeypatch.setattr(SC4PIMApp.time, "perf_counter", lambda: 0.0)
    monkeypatch.setattr(SC4PIMApp.wx, "CallAfter", lambda callback: scheduled.append(callback))

    SC4PIMApp.MainFrame._advance_startup(frame)

    assert finished == [True]
    assert scheduled == []
    assert frame._startup_steps is None
    assert frame._startup_timer is None


def test_advance_startup_queues_continuation_when_budget_expires(monkeypatch):
    scheduled = []
    frame = _frame((None, None, None))
    times = iter((0.0, 0.004, 0.011))
    monkeypatch.setattr(SC4PIMApp.time, "perf_counter", lambda: next(times))
    monkeypatch.setattr(SC4PIMApp.wx, "CallAfter", lambda callback: scheduled.append(callback))

    SC4PIMApp.MainFrame._advance_startup(frame)

    assert len(scheduled) == 1
    assert frame._startup_steps is not None
    assert frame._startup_timer is None


def test_advance_startup_preserves_failure_handling(monkeypatch):
    stopped = []
    statuses = []
    enabled = []

    def fail():
        raise RuntimeError("broken finalization")
        yield

    frame = _frame(fail())
    frame.startupPanel = SimpleNamespace(
        StopPulse=lambda: stopped.append(True),
        SetStatus=lambda *args: statuses.append(args),
    )
    frame.configureMenuItem = SimpleNamespace(Enable=lambda value: enabled.append(value))
    monkeypatch.setattr(SC4PIMApp.time, "perf_counter", lambda: 0.0)

    SC4PIMApp.MainFrame._advance_startup(frame)

    assert stopped == [True]
    assert statuses == [(SC4PIMApp.startupFailed, SC4PIMApp.startupLogDetails)]
    assert enabled == [True]
    assert frame._startup_steps is None
    assert frame._startup_timer is None


def test_thumbnail_drain_queues_continuation_without_fixed_delay(monkeypatch):
    scheduled = []
    provider = SimpleNamespace(
        _queue=["first", "second"],
        _queue_item={"first": 1, "second": 2},
        _queue_cb={},
        _draining=True,
        _drain=lambda: None,
        cache={},
        _build_bitmap=lambda item: "bitmap-%d" % item,
        _build_placeholder=lambda _label: "placeholder",
    )
    times = iter((0.0, 0.011))
    monkeypatch.setattr(SC4LETools.time, "perf_counter", lambda: next(times))
    monkeypatch.setattr(SC4LETools.wx, "CallAfter", lambda callback: scheduled.append(callback))

    SC4LETools.LEAssetThumbnailProvider._drain(provider)

    assert provider.cache == {"second": "bitmap-2"}
    assert provider._queue == ["first"]
    assert provider._draining is True
    assert len(scheduled) == 1
