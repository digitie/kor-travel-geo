"""Source filename helpers shared by upload-set bookkeeping.

The legacy auto-detection / upload-SET discovery + plan surface (``guess_source_kind``,
``discover_load_sources``, ``build_full_load_source_set_plan``, ...) was removed in
T-201; category selection is now explicit (see ``core/source_categories.py`` and the
``/v1/admin/source-file-categories`` catalog endpoint). Only the ``yyyymm`` filename
inference helper survives because the upload-set registry still pre-fills an inferred
month as a *suggestion* for the operator to confirm.
"""

from __future__ import annotations

import re
from pathlib import Path

_YYYYMM_RE = re.compile(r"(20\d{2})(0[1-9]|1[0-2])")
_YYMM_RE = re.compile(r"(?<!\d)(\d{2})(0[1-9]|1[0-2])(?!\d)")


def infer_yyyymm(path: Path) -> str | None:
    recent_parts = path.parts[-4:]
    for part in reversed(recent_parts):
        match = _YYYYMM_RE.search(part)
        if match:
            return "".join(match.groups())
    for part in reversed(recent_parts):
        match = _YYMM_RE.search(part)
        if match:
            year, month = match.groups()
            return f"20{year}{month}"
    return None
