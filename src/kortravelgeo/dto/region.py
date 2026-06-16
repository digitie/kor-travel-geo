"""Region hint DTOs for narrowing local address queries."""

from __future__ import annotations

import re

from pydantic import Field, field_validator, model_validator

from .common import FrozenModel

_SIG_CD_RE = re.compile(r"^\d{2}(\d{3})?$")
_BJD_CD_RE = re.compile(r"^\d{8}(\d{2})?$")
REGION_HINT_MISMATCH_MESSAGE = "bjd_cd must start with sig_cd when both hints are provided"


def validate_region_hint_consistency(sig_cd: str | None, bjd_cd: str | None) -> None:
    """Reject contradictory administrative-code hints before SQL lookup."""

    if sig_cd is None or bjd_cd is None:
        return
    if not bjd_cd.startswith(sig_cd):
        raise ValueError(REGION_HINT_MISMATCH_MESSAGE)


class RegionHint(FrozenModel):
    """Optional administrative-code hint used to narrow local SQL search space."""

    sig_cd: str | None = Field(
        default=None,
        description="2-digit sido prefix or 5-digit sigungu code.",
    )
    bjd_cd: str | None = Field(
        default=None,
        description="8-digit legal dong prefix or 10-digit legal dong code.",
    )

    @field_validator("sig_cd")
    @classmethod
    def validate_sig_cd(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not _SIG_CD_RE.fullmatch(text):
            msg = "sig_cd must be a 2-digit sido prefix or 5-digit sigungu code"
            raise ValueError(msg)
        return text

    @field_validator("bjd_cd")
    @classmethod
    def validate_bjd_cd(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not _BJD_CD_RE.fullmatch(text):
            msg = "bjd_cd must be an 8-digit legal dong prefix or 10-digit legal dong code"
            raise ValueError(msg)
        return text

    @model_validator(mode="after")
    def validate_hint_consistency(self) -> RegionHint:
        validate_region_hint_consistency(self.sig_cd, self.bjd_cd)
        return self

    @property
    def is_empty(self) -> bool:
        return self.sig_cd is None and self.bjd_cd is None

    def sql_params(self) -> dict[str, str | None]:
        """Return bind params shared by repository SQL region filters."""

        sig_cd_filter = self.sig_cd if self.sig_cd and len(self.sig_cd) == 5 else None
        sig_cd_prefix = f"{self.sig_cd}%" if self.sig_cd and len(self.sig_cd) == 2 else None
        bjd_cd_filter = self.bjd_cd if self.bjd_cd and len(self.bjd_cd) == 10 else None
        bjd_cd_prefix = f"{self.bjd_cd}%" if self.bjd_cd and len(self.bjd_cd) == 8 else None
        return {
            "sig_cd_filter": sig_cd_filter,
            "sig_cd_prefix": sig_cd_prefix,
            "bjd_cd_filter": bjd_cd_filter,
            "bjd_cd_prefix": bjd_cd_prefix,
        }


EMPTY_REGION_PARAMS: dict[str, str | None] = {
    "sig_cd_filter": None,
    "sig_cd_prefix": None,
    "bjd_cd_filter": None,
    "bjd_cd_prefix": None,
}


def region_params(region_hint: RegionHint | None) -> dict[str, str | None]:
    """Normalize an optional hint into SQL bind parameters."""

    if region_hint is None or region_hint.is_empty:
        return dict(EMPTY_REGION_PARAMS)
    return region_hint.sql_params()
