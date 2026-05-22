"""PNU construction helpers."""

from __future__ import annotations


def pnu_land_type_from_mntn_yn(raw_mntn_yn: object) -> str:
    """Map road-address mountain flag values to the standard PNU land type code.

    Road-address source data uses ``0`` for normal land and ``1`` for mountain land.
    The 11th digit of a standard PNU uses ``1`` for normal land and ``2`` for
    mountain land, so the source flag must never be concatenated directly.
    """

    text = str(raw_mntn_yn).strip()
    if text == "0":
        return "1"
    if text == "1":
        return "2"
    msg = "mntn_yn must be '0' for normal land or '1' for mountain land"
    raise ValueError(msg)


def _normalize_lot_number(value: object, *, field_name: str, allow_zero: bool) -> str:
    text = str(value).strip()
    if not text.isdigit():
        msg = f"{field_name} must contain only digits"
        raise ValueError(msg)

    number = int(text)
    lower_bound = 0 if allow_zero else 1
    if number < lower_bound or number > 9999:
        msg = f"{field_name} must be between {lower_bound} and 9999"
        raise ValueError(msg)
    return f"{number:04d}"


def build_pnu(
    *,
    bjd_cd: str,
    raw_mntn_yn: object,
    lnbr_mnnm: object,
    lnbr_slno: object = 0,
) -> str:
    """Build a 19-digit standard PNU from source parcel fields."""

    legal_dong_code = bjd_cd.strip()
    if len(legal_dong_code) != 10 or not legal_dong_code.isdigit():
        msg = "bjd_cd must be a 10-digit legal dong code"
        raise ValueError(msg)

    return (
        legal_dong_code
        + pnu_land_type_from_mntn_yn(raw_mntn_yn)
        + _normalize_lot_number(lnbr_mnnm, field_name="lnbr_mnnm", allow_zero=False)
        + _normalize_lot_number(lnbr_slno, field_name="lnbr_slno", allow_zero=True)
    )
