from __future__ import annotations

import struct

import pytest

from kortravelgeo.exceptions import LoaderError
from kortravelgeo.loaders.building_shape_bundle import _key_set_from_buffer


def test_dbf_key_set_skips_deleted_records_and_counts_duplicates() -> None:
    data = _dbf_bytes(
        fields=(("SIG_CD", 5), ("ENT_MAN_NO", 5)),
        records=(
            (False, ("36110", "1")),
            (False, ("36110", "1")),
            (True, ("36110", "2")),
        ),
    )

    result = _key_set_from_buffer(data, ("SIG_CD", "ENT_MAN_NO"))

    assert result.stats.row_count == 2
    assert result.stats.distinct_count == 1
    assert result.stats.duplicate_count == 1


def test_dbf_key_set_rejects_missing_key_fields() -> None:
    data = _dbf_bytes(fields=(("SIG_CD", 5),), records=((False, ("36110",)),))

    with pytest.raises(LoaderError, match="missing DBF key fields"):
        _key_set_from_buffer(data, ("SIG_CD", "ENT_MAN_NO"))


def _dbf_bytes(
    *,
    fields: tuple[tuple[str, int], ...],
    records: tuple[tuple[bool, tuple[str, ...]], ...],
) -> bytes:
    header_length = 32 + 32 * len(fields) + 1
    record_length = 1 + sum(length for _, length in fields)
    header = bytearray(32)
    header[0] = 0x03
    header[4:8] = struct.pack("<I", len(records))
    header[8:10] = struct.pack("<H", header_length)
    header[10:12] = struct.pack("<H", record_length)

    descriptors = bytearray()
    for name, length in fields:
        descriptor = bytearray(32)
        descriptor[: len(name)] = name.encode("ascii")
        descriptor[11] = ord("C")
        descriptor[16] = length
        descriptors.extend(descriptor)

    body = bytearray()
    for deleted, values in records:
        body.extend(b"*" if deleted else b" ")
        for value, (_, length) in zip(values, fields, strict=True):
            body.extend(value.encode("ascii").ljust(length)[:length])

    return bytes(header + descriptors + b"\r" + body + b"\x1a")
