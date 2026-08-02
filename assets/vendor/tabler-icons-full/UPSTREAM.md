# Tabler Icons (full outline set)

- Version: 3.44.0
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
