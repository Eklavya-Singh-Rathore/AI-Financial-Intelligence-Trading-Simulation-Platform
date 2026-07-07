# Vendored third-party code — Kronos

- **Source:** https://github.com/shiyu-coder/Kronos (branch `master`)
- **License:** MIT — see `LICENSE` (Copyright (c) 2025 ShiYu)
- **Vendored:** 2026-07-07
- **Why vendored:** the Kronos runtime classes (`KronosTokenizer`, `Kronos`,
  `KronosPredictor`) are not published on PyPI; only the model *weights* are on
  the Hugging Face Hub (`NeoQuasar/Kronos-*`). The Python source must be copied
  in to load and run those weights.

## Files (verbatim upstream `model/` package)

- `model/__init__.py`
- `model/kronos.py`
- `model/module.py`

## Local modifications

Exactly one, in `model/kronos.py`: the upstream
`sys.path.append("../"); from model.module import *` was replaced with the
package-relative `from .module import *` so the code imports correctly as
`app.ml.kronos_src.model` (no dependency on `model/` being a top-level package
on `sys.path`). No functional/model logic was changed.

## Updating

Re-download the three files from the upstream `model/` directory and re-apply
the single relative-import change above.
