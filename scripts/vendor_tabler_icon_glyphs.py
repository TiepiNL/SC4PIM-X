"""Vendor the full Tabler Icons outline set for the New Submenu icon-template
picker (SC4NewSubmenuDlg / SC4IconMakerDlg.TemplateIconDialog).

This is deliberately separate from ``assets/vendor/tabler-icons/svg`` --
that directory is curated (only the icons SC4PIM-X's own UI buttons use, see
its UPSTREAM.md) and stays small. The icon-template picker needs to search
across the whole set, so it gets its own directory instead of bloating the
curated one.

Usage: point --source at a checked-out tabler-icons release (the
`icons/outline` folder of a tagged archive, e.g. the one under
`.agents/tabler-icons-<version>/icons/outline` in this workspace) and run:

    py scripts/vendor_tabler_icon_glyphs.py --source .agents/tabler-icons-3.44.0

Strips each SVG's leading upstream `<!-- tags/category/... -->` comment block
(metadata SC4PIM-X doesn't use) to keep the vendored footprint down, then
copies the LICENSE and (re)writes UPSTREAM.md.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

_COMMENT_RE = re.compile(rb"\A\s*<!--.*?-->\s*", re.DOTALL)

_UPSTREAM_TEMPLATE = """# Tabler Icons (full outline set)

- Version: {version}
- Upstream: https://github.com/tabler/tabler-icons
- License: MIT; see `LICENSE`

Full outline icon set, vendored for the New Submenu icon-template picker
(`SC4IconMakerDlg.TemplateIconDialog`), which lets an author compose a
submenu icon from up to 4 glyphs. This is separate from
`assets/vendor/tabler-icons/svg`, which stays curated to only the icons
SC4PIM-X's own UI buttons use -- see that directory's UPSTREAM.md.

Regenerate with `scripts/vendor_tabler_icon_glyphs.py --source <release dir>`.
Each SVG has its upstream metadata comment (tags/category/version/unicode)
stripped; only the `<svg>...</svg>` markup is kept.
"""


def strip_comment(data: bytes) -> bytes:
    return _COMMENT_RE.sub(b"", data, count=1).strip() + b"\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="Path to an extracted tabler-icons release directory")
    parser.add_argument("--dest", default=None, help="Destination vendor directory (default: assets/vendor/tabler-icons-full)")
    parser.add_argument("--version", default=None, help="Version string for UPSTREAM.md (default: inferred from --source name)")
    args = parser.parse_args()

    source_root = Path(args.source)
    outline_dir = source_root / "icons" / "outline"
    if not outline_dir.is_dir():
        outline_dir = source_root
    if not outline_dir.is_dir():
        print("No icons/outline directory found under %s" % source_root, file=sys.stderr)
        return 1

    repo_root = Path(__file__).resolve().parents[1]
    dest_root = Path(args.dest) if args.dest else repo_root / "assets" / "vendor" / "tabler-icons-full"
    dest_svg = dest_root / "svg"
    dest_svg.mkdir(parents=True, exist_ok=True)

    count = 0
    for svg_path in sorted(outline_dir.glob("*.svg")):
        data = strip_comment(svg_path.read_bytes())
        (dest_svg / svg_path.name).write_bytes(data)
        count += 1
    print("Vendored %d icons into %s" % (count, dest_svg))

    license_path = source_root / "LICENSE"
    if license_path.exists():
        shutil.copyfile(license_path, dest_root / "LICENSE")

    version = args.version or source_root.name.replace("tabler-icons-", "")
    (dest_root / "UPSTREAM.md").write_text(_UPSTREAM_TEMPLATE.format(version=version), encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
