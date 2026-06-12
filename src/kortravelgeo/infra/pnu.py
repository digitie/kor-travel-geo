"""PNU helpers owned by the storage layer."""

from __future__ import annotations

from kortravelgeo.exceptions import InvalidInputError


def pnu_land_type_from_mntn_yn(mntn_yn: str | None) -> str | None:
    """Map juso ``mntn_yn`` to the 11th PNU land-type digit.

    Source values are ``0`` for ordinary land and ``1`` for mountain. Standard
    PNU uses ``1`` for ordinary land and ``2`` for mountain.
    """

    if mntn_yn is None:
        return None
    stripped = mntn_yn.strip()
    if stripped == "0":
        return "1"
    if stripped == "1":
        return "2"
    msg = "mntn_yn must be '0' or '1'"
    raise InvalidInputError(msg)


def build_pnu(
    *,
    bjd_cd: str | None,
    mntn_yn: str | None,
    lnbr_mnnm: int | str | None,
    lnbr_slno: int | str | None = 0,
) -> str | None:
    """Build a 19-digit PNU or return ``None`` when required lot fields are absent."""

    if not bjd_cd or lnbr_mnnm is None or lnbr_mnnm == "":
        return None
    land_type = pnu_land_type_from_mntn_yn(mntn_yn)
    if land_type is None:
        return None
    bjd = bjd_cd.strip()
    if len(bjd) != 10 or not bjd.isdigit():
        msg = "bjd_cd must be a 10-digit string"
        raise InvalidInputError(msg)
    main_no = int(lnbr_mnnm)
    sub_no = int(lnbr_slno or 0)
    if main_no < 0 or sub_no < 0:
        msg = "lot numbers must be non-negative"
        raise InvalidInputError(msg)
    return f"{bjd}{land_type}{main_no:04d}{sub_no:04d}"
