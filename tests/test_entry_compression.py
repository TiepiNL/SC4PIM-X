"""Compression state chosen on save."""
import struct

from sc4pimx.SC4DatTools import SC4Entry


def _entry(body):
    entry = SC4Entry(struct.pack('<IIIII', 0x6534284A, 0x07BDDF1C, 0xC4B12012,
                                 0, len(body)), 0, None)
    entry.content = entry.rawContent = body
    return entry


# Compressible, and small enough to hit the opportunistic size threshold.
SMALL_BODY = (b"EQZT1###\r\nParentCohort=Key:{0x00000000,0x00000000,0x00000000}\r\n"
              + b"PropCount=0x00000001\r\n" * 24)


def test_small_entry_still_compresses_when_explicitly_asked():
    assert len(SMALL_BODY) <= 600
    entry = _entry(SMALL_BODY)
    entry.compressOnSave = True

    entry.Maj()

    assert entry.compressed is True
    assert entry.filesize < len(SMALL_BODY)


def test_small_entry_stays_compressed_across_an_edit():
    entry = _entry(SMALL_BODY)
    entry.compressed = True

    entry.Maj()

    assert entry.compressed is True


def test_compress_on_save_off_leaves_the_entry_uncompressed():
    entry = _entry(SMALL_BODY)
    entry.compressed = True
    entry.compressOnSave = False

    entry.Maj()

    assert entry.compressed is False
    assert entry.filesize == len(SMALL_BODY)
