# Handoff — SC4PIM-X lot-preview feature (`ImageDBLots`)

> Scratch handoff note for continuing this feature in a fresh agent session
> (e.g. on Windows, where the app + real Plugins + a GPU/GL context live).
> **Delete this file before opening the PR.** It is intentionally at the repo
> root (not gitignored) so it travels with the `feat/lot-imagedb-preview` branch.

## Repo / branch / PR

- Repo: `SC4PIM-X`. Branch: **`feat/lot-imagedb-preview`** (already pushed).
- `origin` = your fork `TiepiNL/SC4PIM-X`; `upstream` = `caspervg/SC4PIM-X`.
- PR target: **upstream `main`** (branch on the fork, PR to upstream).

## Goal

Add lot previews for **LotConfigurations** exemplars. Today the app's lower-left
preview slot shows a rendered thumbnail for **Building** exemplars but an empty
grey box for **lots**. Prerender and cache **8 views per lot** — sides
{S, E, N, W} × {Day, Night} — into a new on-disk cache, and show the default view
in the app. Treat this as a **standalone SC4PIM-X feature** (do not couple it to
any other project).

## Locked decisions

1. **Alpha, not baked background.** Render each view **with transparency** (lot on
   a transparent ground); the **app composites the grey background** at display
   time (matching how models render on a grey square). Store **PNG** (the model
   ImageDB uses JPG; lots get their own PNG + alpha cache).
2. **High quality.** Images must read clearly in a browser modal (a future use is
   replacing the low-quality lot pictures on Simtropolis / SC4Evermore). Target
   ~**512×512**, MSAA + sRGB per the `[Rendering]` config.
3. **Filenames** follow the building viewer's existing S/E/N/W + Day/Night
   dropdown, abbreviated to single letters:
   `0x{GID}-0x{IID}-{S|E|N|W}-{D|N}.png` (e.g. `0xa8fbd372-0xe6b9b2a7-S-D.png`).
   Key on **GID+IID** — IID alone is not unique across groups (a building and its
   lot can share an IID under different GIDs; verified).
4. **SC4PIM-X first.** No coupling to any downstream consumer.
5. **Eager generation.** Render **all 8** views up front (finalize-time /
   background), not lazily on first display, so the cache is complete and reusable
   even for lots never opened in the editor.

## Verified integration points (grep these symbols)

- **`paths.py`** (wx-free): `image_db_dir()` / `image_db_path()` (`GID-IID.jpg`);
  `sc4path_thumb_dir()` → `ImageDBPaths` sibling. **Add** `image_db_lots_dir()`
  → `user_data_dir()/ImageDBLots` + a filename helper. (Windows: under
  `%APPDATA%\sc4pimx\`.)
- **`SC4VirtualDat.py` → `VirtualDat.FinalizeIncremental()`**: the
  `missing_pictures` collect-then-render pattern (batched, yielding). **Add** a
  parallel "missing lot images" pass over LotConfigurations exemplars
  (ExemplarType `0x10` == 16).
- **Offscreen render:** `SC4Renderer.RenderTarget` ("for previews and
  thumbnails", `read_rgb()` → `glReadPixels`). Compose the lot via
  `LotEditorWin.Display(exemplar, virtualDAT, bForIcon=True)` — the
  `_icon_render` flag suppresses the procedural city context, giving a clean
  lot-only frame. Proof of the `Display → on_draw ×2 → Save` sequence:
  `SC4PIMApp._render_conversion_icon` and `NoteBookPanel.OnCreatePlopLot`. The
  generator should render into an **offscreen `RenderTarget`**, not
  `frame.Show()`.
- **Road-access default side:** `REQUIRED_ROADS_PROP = 0x4A4A88F0` ("LotConfig
  Required Roads"), a Uint8 **bitmask**: bit0 = Left (EDGE_XMIN), bit1 = Behind
  (EDGE_ZMIN), bit2 = Right (EDGE_XMAX), bit3 = Front (EDGE_ZMAX), in lot-local
  pre-rotation tile space. `road_edges_from_flags()` lives in `SC4CityContext`
  (wx-free); `LotEditorWin._road_edge_records()` already reads prop
  `1246398704`. Rep-3 orientation is **S=0, W=1, N=2, E=3**; the 4 views map to
  `rotation3D` 0..3. The **default view** = the rotation that puts the **first
  set required-road bit** at the front; corner lots (2 bits) take the first.
- **Day / Night:** `LotEditorWin.nightMode` / `previewMinutes` / lighting
  profiles + `s3DTexturesHolder.SetNightMode()` and `night_state_for(exemplar)`.
- **UI slot:** `StartupPreviewPanel` (lower-left). Load a cached image mirroring
  `EnsureStandardModelImage`; composite the grey background under the alpha PNG
  for a selected LotConfig exemplar.

## Cache layout

```
%APPDATA%\sc4pimx\ImageDBLots\        (Windows; user_data_dir()/ImageDBLots)
  0x{GID}-0x{IID}-{S|E|N|W}-{D|N}.png
```

- 8 files per lot. Side letter = the compass edge facing the viewer (rep-3
  orientation S/W/N/E mapped to the rotation index).
- Consider a generator-**version tag** so a render change invalidates the cache
  automatically (the SC4Path thumbnail cache already suffixes size — mirror that
  idea).

## Increment 1 first (wx-free, TDD, can be done anywhere)

These import **no wx**, so they build and test without a working wxPython:

1. `paths.image_db_lots_dir()` + the filename helper (`S/E/N/W`, `D/N`).
2. `required_road_default_rotation(flags: int) -> int` in the wx-free
   `SC4CityContext` module (decodes `0x4A4A88F0`; corner lots → first set bit).
3. A new pytest file covering both (mirror `tests/test_city_context.py` style —
   note it imports `SC4LotPreview` only lazily inside the GL tests, so wx-free
   tests collect and run fine).

## Then (GL / UI — validate on Windows)

- `render_lot_view(exemplar, virtualDAT, rotation, night) -> PIL.Image` (RGBA)
  via `RenderTarget`, reusing `LotEditorWin` composition.
- The finalize generation pass (all 8 per missing lot; batched/yielding/
  resumable — only render missing files).
- UI: show the default-side Day preview (grey bg composited) in
  `StartupPreviewPanel` for a selected LotConfig exemplar.
- Config toggles (enable / size / regenerate) alongside `[Rendering]`.

## Environment & conventions

- SC4PIM-X uses **uv + pyproject** (`requires-python >=3.11,<3.14`). Dev tools
  are **black, ruff, mypy, pytest** (`[dependency-groups].dev`). Follow **those**
  conventions — not any other project's task runner / recipes.
- `uv sync` **fails on Linux/WSL**: `wxPython==4.3.0a16068+96cb1d0c` is pinned
  from the `wxpython-snapshots` index, which has no Linux wheel for this
  Python/platform, so uv tries to build wxWidgets from source (needs
  `pkg-config` + `libgtk-3-dev` + image libs). On **Windows** the snapshot wheel
  installs and `uv sync` works. For wx-free increment 1 on Linux, use a lean
  side venv instead of a full sync:
  `uv venv --python 3.11 .venv-headless && uv pip install --python .venv-headless pytest numpy pillow`.

## Risks / open items

- **Volume/perf:** ~16,933 LotConfigs × 8 ≈ 135k renders on a full first run —
  heavy but background/incremental/resumable. Needs progress UI + cancel;
  consider a setting or an explicit "generate now" action.
- **Alpha correctness** at lot edges (base-texture tiles are opaque; alpha means
  "outside the lot footprint" — confirm the footprint mask matches lot size in
  tiles).
- **Camera/zoom framing** so all four rotations frame the lot comparably.
- **Cache invalidation** on generator/version change.

## Validation

Run the app on the Windows SC4 install (real Plugins + GPU). Confirm 8 PNGs per
lot appear under `%APPDATA%\sc4pimx\ImageDBLots\`, and the lower-left slot shows
the lot preview. Good test lots (from the downstream whitelist): AIG Tower
`0xa8fbd372:0xc6bb6905`, Silberturm `0xa8fbd372:0x160a0edc`.

## Full design reference

The complete design (with the downstream consumption plan) lives in the
`sc4-tile` repo at `tmp/known-building-tiles-plan.md`, sections **§17** (this
SC4PIM-X feature) and **§18** (downstream consumption). Not needed to build the
SC4PIM-X feature, but it explains the "why".
