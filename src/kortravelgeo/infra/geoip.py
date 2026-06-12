"""GeoIP country lookup and Korea-only gate decisions."""

from __future__ import annotations

import importlib
import logging
from collections import OrderedDict
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network, ip_address
from pathlib import Path
from typing import Any, Literal, Protocol, cast

from kortravelgeo.settings import Settings

_LOGGER = logging.getLogger(__name__)

IPAddress = IPv4Address | IPv6Address
IPNetwork = IPv4Network | IPv6Network
GeoIpGateMode = Literal["strict", "permissive", "off"]
GeoIpAction = Literal["allow", "deny"]


class GeoIpCountryReader(Protocol):
    def country_code(self, ip: str) -> str | None: ...


@dataclass(frozen=True, slots=True)
class GeoIpDecision:
    action: GeoIpAction
    reason: str
    client_ip: str
    country_code: str | None = None

    @property
    def allowed(self) -> bool:
        return self.action == "allow"


class MaxMindCountryReader:
    """Tiny adapter around MaxMind GeoLite2 Country mmdb files."""

    def __init__(self, db_path: Path) -> None:
        maxminddb = importlib.import_module("maxminddb")
        self._reader = maxminddb.open_database(str(db_path))
        self._cache: OrderedDict[str, str | None] = OrderedDict()

    def country_code(self, ip: str) -> str | None:
        if ip in self._cache:
            self._cache.move_to_end(ip)
            return self._cache[ip]
        result = cast("dict[str, Any] | None", self._reader.get(ip))
        if not result:
            return self._remember(ip, None)
        country = result.get("country")
        if not isinstance(country, dict):
            return self._remember(ip, None)
        code = country.get("iso_code")
        return self._remember(ip, str(code).upper() if code else None)

    def _remember(self, ip: str, code: str | None) -> str | None:
        self._cache[ip] = code
        self._cache.move_to_end(ip)
        if len(self._cache) > 10_000:
            self._cache.popitem(last=False)
        return code


def build_geoip_reader(settings: Settings) -> GeoIpCountryReader | None:
    if settings.geoip_gate_mode == "off":
        return None
    if settings.geoip_db_path is None or not settings.geoip_db_path.exists():
        return None
    try:
        return MaxMindCountryReader(settings.geoip_db_path)
    except Exception:
        _LOGGER.exception("failed to open GeoIP country database")
        return None


def classify_ip(
    raw_ip: str | None,
    *,
    reader: GeoIpCountryReader | None,
    mode: GeoIpGateMode,
    allow_cidrs: tuple[IPNetwork, ...] = (),
    deny_cidrs: tuple[IPNetwork, ...] = (),
) -> GeoIpDecision:
    client_ip = raw_ip or ""
    if mode == "off":
        return GeoIpDecision("allow", "gate_off", client_ip)

    ip = _parse_ip(raw_ip)
    if ip is None:
        return GeoIpDecision("deny", "invalid_client_ip", client_ip)

    normalized = str(ip)
    if _in_networks(ip, deny_cidrs):
        return GeoIpDecision("deny", "denylist", normalized)
    if _in_networks(ip, allow_cidrs):
        return GeoIpDecision("allow", "allowlist", normalized)
    if _is_internal_ip(ip):
        return GeoIpDecision("allow", "internal_ip", normalized)

    country_code: str | None = None
    lookup_failed = False
    if reader is not None:
        try:
            country_code = reader.country_code(normalized)
        except Exception:
            lookup_failed = True
            _LOGGER.exception("GeoIP country lookup failed")

    if country_code == "KR":
        return GeoIpDecision("allow", "kr_public_ip", normalized, country_code=country_code)
    if mode == "permissive":
        reason = "permissive_geoip_unavailable" if country_code is None else "permissive_non_kr"
        return GeoIpDecision("allow", reason, normalized, country_code=country_code)
    if reader is None:
        return GeoIpDecision("deny", "geoip_db_unavailable", normalized)
    if lookup_failed:
        return GeoIpDecision("deny", "geoip_lookup_failed", normalized)
    return GeoIpDecision("deny", "non_kr_public_ip", normalized, country_code=country_code)


def client_ip_from_forwarded(
    peer_host: str,
    x_forwarded_for: str | None,
    trusted_proxies: tuple[IPNetwork, ...],
) -> str:
    peer_ip = _parse_ip(peer_host)
    if peer_ip is None or not _in_networks(peer_ip, trusted_proxies):
        return peer_host
    if not x_forwarded_for:
        return str(peer_ip)

    chain = [part.strip() for part in x_forwarded_for.split(",") if part.strip()]
    chain.append(str(peer_ip))
    for raw in reversed(chain):
        ip = _parse_ip(raw)
        if ip is not None and not _in_networks(ip, trusted_proxies):
            return str(ip)
    return str(peer_ip)


def is_open_path(path: str, open_paths: tuple[str, ...]) -> bool:
    for open_path in open_paths:
        normalized = open_path.rstrip("/") or "/"
        if path == normalized or path.startswith(f"{normalized}/"):
            return True
    return False


def _parse_ip(raw_ip: str | None) -> IPAddress | None:
    if raw_ip is None:
        return None
    value = raw_ip.strip()
    if value.startswith("["):
        bracket_end = value.find("]")
        if bracket_end > 1:
            value = value[1:bracket_end]
    elif value.count(":") == 1:
        host, port = value.rsplit(":", 1)
        if port.isdigit():
            value = host
    try:
        return ip_address(value)
    except ValueError:
        return None


def _in_networks(ip: IPAddress, networks: tuple[IPNetwork, ...]) -> bool:
    return any(ip in network for network in networks)


def _is_internal_ip(ip: IPAddress) -> bool:
    return ip.is_loopback or ip.is_private or ip.is_link_local
