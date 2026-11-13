"""Building blocks shared by the FinanzOnline SOAP clients.

Purpose
-------
The session client and the UID query client parse zeep replies, build zeep
transports and mask credentials the same way. One definition here keeps the
two clients from drifting apart.

Contents
--------
* :data:`SoapText` - Pydantic field type for an optional SOAP string
* :class:`MalformedSoapResponseError` - A reply that does not fit its record
* :func:`describe_validation_error` - ``<field>: <reason>`` rendering of a refusal
* :class:`TransportFactory` - Typed facade over zeep's ``Transport`` constructor
* :func:`mask_credential` - Show only the ends of a credential or session id

System Role
-----------
Adapters layer - internal to :mod:`finanzonline_uid.adapters.finanzonline`.
"""

from __future__ import annotations

from typing import Annotated, Final, Protocol

from pydantic import BeforeValidator, ValidationError
from zeep.transports import Transport

__all__ = [
    "MalformedSoapResponseError",
    "SoapText",
    "TransportFactory",
    "describe_validation_error",
    "mask_credential",
]


def _none_to_empty(value: object) -> object:
    """Map an absent optional SOAP string (zeep gives None) to the empty string.

    Examples:
        >>> _none_to_empty(None)
        ''
        >>> _none_to_empty("ACME")
        'ACME'
    """
    return "" if value is None else value


# minOccurs="0" string elements arrive as None when BMF omits them.
SoapText = Annotated[str, BeforeValidator(_none_to_empty)]
"""Pydantic field type for an optional SOAP string: None (omitted) reads as ""."""


class MalformedSoapResponseError(Exception):
    """A SOAP reply whose fields do not fit the record it is parsed into.

    The message names each offending field and the reason, never the raw
    input: a reply can carry a session id or company data.
    """


# Pydantic reports a refusal of the whole input (a None reply, a reply of the
# wrong kind) with an empty location; this names it instead of an empty field.
# The parentheses keep it from reading as a SOAP element name.
_WHOLE_REPLY: Final[str] = "(whole reply)"


def _describe_location(location: tuple[int | str, ...]) -> str:
    """Render a validation error location as a dotted field path.

    Examples:
        >>> _describe_location(("rc",))
        'rc'
        >>> _describe_location(())
        '(whole reply)'
    """
    if not location:
        return _WHOLE_REPLY
    return ".".join(str(part) for part in location)


def describe_validation_error(error: ValidationError) -> str:
    """Render each validation failure as ``<field>: <reason>``.

    Args:
        error: The refusal raised while parsing a reply.

    Returns:
        One ``<field>: <reason>`` item per failure, joined by ``"; "``. A
        refusal of the whole reply names ``(whole reply)`` as its field.

    Examples:
        >>> from pydantic import BaseModel
        >>> class Reply(BaseModel, from_attributes=True):
        ...     rc: int
        >>> try:
        ...     Reply.model_validate({"rc": "x"})
        ... except ValidationError as exc:
        ...     describe_validation_error(exc)
        'rc: Input should be a valid integer, unable to parse string as an integer'
        >>> try:
        ...     Reply.model_validate(None)
        ... except ValidationError as exc:
        ...     describe_validation_error(exc)
        '(whole reply): Input should be a valid dictionary or object to extract fields from'
    """
    return "; ".join(f"{_describe_location(item['loc'])}: {item['msg']}" for item in error.errors())


class TransportFactory(Protocol):
    """zeep's ``Transport`` constructor as the clients call it.

    zeep leaves the parameters unannotated, so pyright infers ``int`` from the
    default ``timeout=300``; requests (which receives the value) takes seconds as
    a float.
    """

    def __call__(self, *, timeout: float, operation_timeout: float) -> Transport:
        """Build a transport with load and operation timeouts in seconds."""
        ...


def mask_credential(value: str, visible_chars: int = 4) -> str:
    """Mask a credential or session id, showing only the first/last few characters.

    Args:
        value: The sensitive value to mask.
        visible_chars: Number of characters to show at start and end.

    Returns:
        Masked string like "abc...xyz", or one "*" per character for a value
        too short to show both ends without revealing all of it.

    Examples:
        >>> mask_credential("SESSION123456")
        'SESS...3456'
        >>> mask_credential("12345678")
        '********'
        >>> mask_credential("")
        ''
    """
    if len(value) <= visible_chars * 2:
        return "*" * len(value)
    return f"{value[:visible_chars]}...{value[-visible_chars:]}"
