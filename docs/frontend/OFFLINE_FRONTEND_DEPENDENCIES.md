# Offline frontend dependencies

The machine-readable authority for exact filenames and SHA256 values is
`static/vendor/VENDOR_MANIFEST.json`. All assets are shipped in the application
artifact; none are installed or downloaded during production startup.

## Tailwind CSS

- Version: 3.4.17 (the former unversioned CDN URL redirected to this version at audit time)
- Purpose: knowledge-base layout, colors, spacing, responsive utilities, modal and state classes
- Original source: `https://cdn.tailwindcss.com/3.4.17`
- Local path: `static/vendor/tailwind/3.4.17/`
- License: MIT, retained as `LICENSE`
- Runtime file: `tailwind.min.css`
- Build source: `input.css`
- Runtime SHA256: `e49e4e41dd2dfdcea02024556e8f75cc33b5e1fe73c57f8d7ea8599775af11b0`

The CSS was compiled with the official 3.4.17 standalone binary using
`templates/kb_manager.html` and `static/js/kb_manager.js` as content. The binary
is not part of the deployment and is not needed at runtime.

## Chart.js

- Version: 4.5.1 (confirmed by bundle header and root `package.json`)
- Purpose: analytics charts
- Original source: `https://www.npmjs.com/package/chart.js/v/4.5.1`
- Local path: `static/vendor/chart.js/4.5.1/`
- License: MIT, retained as `LICENSE.md`
- Required file: `chart.umd.js`
- SHA256: `84d0e233daba702b8f77d669d8c137cad36d441a10f200b6f2d3ab553bdfcf6b`

Only the source-map trailer was removed; executable code is unchanged. The
source map is not shipped because it is not needed at runtime.

## Inter

- Artifact revision: Google Fonts `/s/inter/v20/`
- Requested weights: 300, 400, 500, 600, 700, 800
- Purpose: primary Latin UI typography
- Original stylesheet: `https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap`
- Local path: `static/vendor/google-fonts/`
- License: SIL Open Font License 1.1, retained as `INTER-OFL.txt`
- Required files: shared `fonts.css` plus seven `UcC73...woff2` Unicode subsets listed in the manifest
- Local stylesheet SHA256: `0dd3fbb2d20841755445a3490c7b40463b76bec528ff7231f6cf5e35ad08c07b`

## JetBrains Mono

- Artifact revision: Google Fonts `/s/jetbrainsmono/v24/`
- Requested weights: 400, 500
- Purpose: monospace UI typography
- Original stylesheet: same Google Fonts CSS2 request above
- Local path: `static/vendor/google-fonts/`
- License: SIL Open Font License 1.1, retained as `JETBRAINS-MONO-OFL.txt`
- Required files: shared `fonts.css` plus six `tDbv2...woff2` Unicode subsets listed in the manifest
- Local stylesheet SHA256: `0dd3fbb2d20841755445a3490c7b40463b76bec528ff7231f6cf5e35ad08c07b`

Inter does not supply Persian glyphs; existing browser fallback behavior remains
for Persian text on the general dashboard. Vazirmatn below contains Persian and
Arabic glyphs for the Persian knowledge-base UI.

## Vazirmatn

- Version: 33.003
- Purpose: Persian/Arabic knowledge-base typography
- Original source: `https://github.com/rastikerdar/vazirmatn/tree/v33.003`
- Former broken URL: `https://cdn.jsdelivr.net/gh/rastikerdar/vazirmatn@v33.0.0/Vazirmatn-font-face.css`
- Local path: `static/vendor/vazirmatn/33.003/`
- License: SIL Open Font License 1.1, retained as `OFL.txt`
- Required files: `vazirmatn.css` and Thin through Black WOFF2 weights under `fonts/webfonts/`
- Stylesheet SHA256: `09eda7d9fd0b1c98b5df31d7c866151449c91cd6d4b6d23a5f0b17536ccc7d70`

The old `v33.0.0` tag is not a published artifact. Version 33.003 is the real
compatible v33 release and fixes the previous permanent font CSS 404.

## Integrity verification

Run:

```bash
/root/miniconda3/envs/faq/bin/python3.12 -m unittest -v tests.test_offline_frontend
```

The manifest test verifies every listed SHA256 and rejects unmanifested files in
`static/vendor/`.
