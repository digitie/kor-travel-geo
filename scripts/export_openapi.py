#!/usr/bin/env python
"""Export the FastAPI OpenAPI schema used by the admin UI type generator."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from kortravelgeo.api.app import create_app  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "openapi.json",
        help="OpenAPI JSON output path.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the output file is missing or differs from the generated schema.",
    )
    args = parser.parse_args(argv)

    output = args.output if args.output.is_absolute() else ROOT / args.output
    content = json.dumps(create_app().openapi(), ensure_ascii=False, indent=2, sort_keys=True)
    content = f"{content}\n"
    if args.check:
        if not output.exists():
            print(f"OpenAPI file is missing: {output}", file=sys.stderr)
            return 1
        existing = output.read_text(encoding="utf-8")
        if existing != content:
            print(f"OpenAPI file is stale: {output}", file=sys.stderr)
            print("Run: python scripts/export_openapi.py", file=sys.stderr)
            return 1
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
