"""Compare T-041 detail-dong and zone shape bundles."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from kraddr.geo.loaders.extra_shape_layers import (
    compare_detail_dong_shape_bundle,
    compare_zone_shape_bundle,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare detail-dong/zone shape bundles with electronic map layers.",
    )
    parser.add_argument("--detail-dong-zip", type=Path, help="건물군 내 상세주소 동 도형 ZIP")
    parser.add_argument("--zone-zip", type=Path, help="구역의 도형 ZIP")
    parser.add_argument(
        "--electronic-map-sido",
        type=Path,
        required=True,
        help="도로명주소 전자지도 시도 디렉터리",
    )
    parser.add_argument("--indent", type=int, default=2)
    args = parser.parse_args()

    result: dict[str, object] = {}
    if args.detail_dong_zip:
        result["detail_dong"] = asdict(
            compare_detail_dong_shape_bundle(args.detail_dong_zip, args.electronic_map_sido)
        )
    if args.zone_zip:
        result["zone"] = asdict(compare_zone_shape_bundle(args.zone_zip, args.electronic_map_sido))
    if not result:
        parser.error("at least one of --detail-dong-zip or --zone-zip is required")

    print(json.dumps(result, ensure_ascii=False, indent=args.indent))


if __name__ == "__main__":
    main()
