#!/usr/bin/env python
"""Compare road-address building bundle layers with electronic-map layers."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from kortravelgeo.loaders.building_shape_bundle import compare_building_shape_bundle


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-zip", type=Path, required=True)
    parser.add_argument("--electronic-map-sido", type=Path, required=True)
    parser.add_argument("--indent", type=int, default=2)
    args = parser.parse_args()
    comparison = compare_building_shape_bundle(
        args.bundle_zip,
        args.electronic_map_sido,
    )
    print(json.dumps(asdict(comparison), ensure_ascii=False, indent=args.indent))


if __name__ == "__main__":
    main()
