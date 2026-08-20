"""WriteADat must preserve entries it doesn't touch."""
import struct

from sc4pimx.SC4DatTools import DatFile, WriteADat, SC4Entry


def _entry(tgi, body, order):
    entry = SC4Entry(struct.pack('<IIIII', tgi[0], tgi[1], tgi[2], 0, len(body)),
                     order, None)
    entry.content = entry.rawContent = body
    return entry


def _build(path, bodies):
    entries = [_entry(tgi, body, i) for i, (tgi, body) in enumerate(bodies)]
    for entry in entries:
        entry.fileName = str(path)
    WriteADat(str(path), entries, None, False)


# An exemplar (eagerly read on load) followed by a PNG (never eagerly read, so
# its rawContent is still None at write time -- the case that used to corrupt).
EXEMPLAR = (0x6534284A, 0x07BDDF1C, 0xC4B12012)
PNG = (0x856DDBAC, 0x6A386D26, 0xC4B12012)


def test_untouched_entry_survives_a_rewrite_that_shifts_its_offset(tmp_path):
    package = tmp_path / "lot.SC4Lot"
    icon = bytes(range(256)) * 8
    _build(package, [(EXEMPLAR, b"EQZT1###\r\n" + b"x" * 700), (PNG, icon)])

    entries = list(DatFile(str(package), None, False).entries)
    png = next(e for e in entries if e.tgi == PNG)
    exemplar = next(e for e in entries if e.tgi == EXEMPLAR)
    assert png.rawContent is None, "PNG should not be loaded yet"

    # Grow the exemplar, so every entry after it moves in the new file.
    exemplar.read_file(None, True, True)
    exemplar.content = exemplar.content + b"padding\r\n" * 20
    exemplar.Maj()
    WriteADat(str(package), entries, None, False)

    written = next(e for e in DatFile(str(package), None, False).entries
                   if e.tgi == PNG)
    written.read_file(None, True, False)
    assert written.rawContent == icon
