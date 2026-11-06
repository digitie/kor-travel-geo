"""Mask secret query-parameter values in the API process logs.

uvicorn's access log writes the full request target, query string included, so a public API
key sent as ``?key=...`` would land in the container log in clear text. The same shape shows up
in uvicorn's error log (WebSocket request lines, tracebacks of ``httpx.HTTPStatusError`` whose
message embeds the provider URL with ``serviceKey``/``confmKey``) and in httpx's own
``HTTP Request: GET <url>`` INFO line.

:func:`install_log_redaction` attaches one filter to those loggers. It is called from
``create_app()``, which uvicorn imports *after* it has applied its logging config (CLI and
``uvicorn.run`` alike), and logging config never removes logger filters, so the filter holds
for the shipped ``uvicorn kortravelgeo.api.app:app`` start command.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from urllib.parse import unquote_plus

MASK = "***"

# Normalised (lower-case, ``-``/``_`` removed) parameter names ending in one of these are
# secret: key, apikey/api_key, servicekey/serviceKey, confmKey, token, access_token, secret,
# client_secret, password ...
_SECRET_NAME_SUFFIXES = ("key", "token", "secret", "password", "passwd")

# Two passes. The first splits like Starlette (``parse_qsl`` splits on ``&`` only), so a value
# containing ``;``, a tab or quotes is masked whole: ``?key=AB;CD`` authenticates as ``AB;CD``.
# The second also treats ``;`` as a separator, catching ``;token=...`` hidden inside another
# parameter's value. A value ends at ``&``, a space or a line break; everything else (``;``,
# quotes, ``#``) is over-masked rather than cut short.
_STARLETTE_PARAM_RE = re.compile(r"(?P<head>[?&](?P<name>[^?&=\s]+)=)(?P<value>[^& \r\n]*)")
_SEMICOLON_PARAM_RE = re.compile(r"(?P<head>[?&;](?P<name>[^?&;=\s]+)=)(?P<value>[^&; \r\n]*)")

_REDACTED_LOGGERS = ("uvicorn.access", "uvicorn.error", "httpx")
# httpx logs every request URL at INFO, httpcore its connection chatter at DEBUG.
_QUIET_LOGGERS = ("httpx", "httpcore")


def redact_secret_query_params(text: str) -> str:
    """Return ``text`` with the values of secret-looking query parameters replaced by ``***``.

    The parameter name and every other parameter are kept. Names are percent-decoded and
    compared case-insensitively, as Starlette would read them.
    """

    if "=" not in text:
        return text
    return _SEMICOLON_PARAM_RE.sub(_mask_match, _STARLETTE_PARAM_RE.sub(_mask_match, text))


def _mask_match(match: re.Match[str]) -> str:
    if _is_secret_name(match["name"]):
        return match["head"] + MASK
    return match[0]


def _is_secret_name(name: str) -> bool:
    normalized = unquote_plus(name).lower().replace("_", "").replace("-", "")
    return normalized.endswith(_SECRET_NAME_SUFFIXES)


def _redact_arg(value: object) -> object:
    if isinstance(value, str):
        return redact_secret_query_params(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    # e.g. ``httpx.URL`` in httpx's request line. Only replace the object when masking changed
    # its text, so ``%r``/``%d`` formatting of unrelated arguments is untouched.
    try:
        text = str(value)
    except Exception:
        return value
    redacted = redact_secret_query_params(text)
    return value if redacted == text else redacted


class SecretQueryParamFilter(logging.Filter):
    """Mask secret query values in a record's message, arguments and traceback text.

    The argument tuple keeps its shape: uvicorn's ``AccessFormatter`` unpacks it positionally.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _redact_arg(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(_redact_arg(arg) for arg in record.args)
        elif isinstance(record.args, Mapping):
            record.args = {key: _redact_arg(arg) for key, arg in record.args.items()}
        if record.exc_info and not record.exc_text:
            # Formatter.format() reuses a cached exc_text, so the masked text is what is written.
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            masked = redact_secret_query_params(record.exc_text)
            if masked != record.exc_text:
                record.exc_text = masked
                # Formatters that rebuild the traceback from exc_info (JSON/rich) would undo it.
                record.exc_info = None
        if record.stack_info:
            record.stack_info = redact_secret_query_params(record.stack_info)
        return True


_FILTER = SecretQueryParamFilter()


def install_log_redaction() -> None:
    """Attach the masking filter to the uvicorn/httpx loggers. Safe to call repeatedly."""

    for name in _REDACTED_LOGGERS:
        logging.getLogger(name).addFilter(_FILTER)
    for name in _QUIET_LOGGERS:
        logger = logging.getLogger(name)
        # Keep a level an operator set through --log-config; the filter still masks httpx.
        if logger.level == logging.NOTSET:
            logger.setLevel(logging.WARNING)
