"""Hotspot profiler for SC4PIM-X startup (plugin scan through core-ready).

Runs the real wx app, cProfile-wraps everything from App.OnInit through
MainFrame._finish_startup, then dumps a .pstats file and prints top offenders
by cumulative and self time. Uses the user's real plugin folders (same config
as a normal launch) unless overridden via env vars below.

Usage:
    uv run python scripts/profile_startup.py [output.pstats]

Env:
    SC4PIM_SKIP_TEXTURE_IMAGES=1   skip texture image list build
    SC4PIM_SKIP_PROP_IMAGES=1      skip prop image list build
    SC4PIM_SKIP_MISSING_PICS=1     skip missing-thumbnail generation
"""
from __future__ import annotations

import cProfile
import os
import pstats
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sc4pimx import SC4PIMApp  # noqa: E402
from sc4pimx.paths import image_db_dir  # noqa: E402
from PIL import Image  # noqa: E402


def _ensure_image_db():
    """Mirror main()'s placeholder setup so startup doesn't hit missing files."""
    for large in (False, True):
        db = image_db_dir(large=large)
        db.mkdir(parents=True, exist_ok=True)
        size = (128, 128) if large else (64, 64)
        blank = Image.new("RGB", size, 8355711)
        for name in ("0xbadb57f1-0x00000000.jpg", "0x00000000-0x00000000.jpg"):
            path = db / name
            if not path.exists():
                blank.save(path)


def main() -> None:
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("startup.pstats")
    _ensure_image_db()

    profiler = cProfile.Profile()
    state = {"started": False, "start": 0.0}

    orig_start_startup = SC4PIMApp.MainFrame.StartStartup
    orig_finish_startup = SC4PIMApp.MainFrame._finish_startup

    def timed_start_startup(self):
        state["started"] = True
        state["start"] = time.perf_counter()
        profiler.enable()
        return orig_start_startup(self)

    def timed_finish_startup(self):
        result = orig_finish_startup(self)
        profiler.disable()
        elapsed = time.perf_counter() - state["start"]
        print(f"\nStartup wall time under profiler: {elapsed:.3f}s")
        profiler.dump_stats(str(out_path))
        print(f"Wrote {out_path}")

        stats = pstats.Stats(profiler)
        print("\n=== Top 25 by cumulative time ===")
        stats.sort_stats("cumulative").print_stats(25)
        print("\n=== Top 25 by self (tottime) ===")
        stats.sort_stats("tottime").print_stats(25)

        SC4PIMApp.wx.CallAfter(self.Close)
        return result

    SC4PIMApp.MainFrame.StartStartup = timed_start_startup
    SC4PIMApp.MainFrame._finish_startup = timed_finish_startup

    if os.environ.get("SC4PIM_PROFILE_SKIP_CONFIG_DIALOG"):
        # In-memory only: represents a normal relaunch where the user already
        # has folders configured, without touching the real config.toml.
        SC4PIMApp.config.should_show_file_configuration = lambda: False

    SC4PIMApp.configure_logging()
    prog = SC4PIMApp.App()
    prog.MainLoop()

    if not state["started"]:
        print("StartStartup never ran -- nothing profiled.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
