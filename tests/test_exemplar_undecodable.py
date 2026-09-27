import logging
from types import SimpleNamespace

from sc4pimx.SC4DatTools import SC4Exemplar


def _entry(content):
    return SimpleNamespace(
        content=content, tgi=(1697917002, 0x2A3B4C5D, 0x0BADF00D),
        fileName="plugins/broken.dat", virtual_dat=None)


def test_undecodable_body_logs_file_and_tgi(caplog):
    with caplog.at_level(logging.WARNING, logger="sc4pimx.SC4DatTools"):
        exemplar = SC4Exemplar(_entry(b"NOPE" + b"\x00" * 24), None)

    message = caplog.text
    assert "plugins/broken.dat" in message
    assert "0x2A3B4C5D" in message
    # An unparsed body must still answer GetProp instead of raising.
    assert exemplar.link is None
    assert exemplar.GetProp(16) is None


def test_empty_body_does_not_raise(caplog):
    with caplog.at_level(logging.WARNING, logger="sc4pimx.SC4DatTools"):
        exemplar = SC4Exemplar(_entry(b""), None)

    assert exemplar.GetProp(16) is None
    assert "plugins/broken.dat" in caplog.text
