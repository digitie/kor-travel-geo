from __future__ import annotations

from scripts.export_openapi import main


def test_export_openapi_writes_and_checks_schema(tmp_path) -> None:
    output = tmp_path / "openapi.json"

    assert main(["--output", str(output)]) == 0
    assert output.exists()
    assert main(["--output", str(output), "--check"]) == 0

