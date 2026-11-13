"""Tests for the building blocks both FinanzOnline SOAP clients share."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from finanzonline_uid.adapters.finanzonline._soap_common import SoapText, describe_validation_error, mask_credential


class _Reply(BaseModel):
    rc: int
    msg: SoapText = ""


@pytest.mark.os_agnostic
class TestMaskCredential:
    """Only the ends of a long value show; a short one is fully starred."""

    @pytest.mark.parametrize(
        ("value", "masked"),
        [
            ("", ""),
            ("a", "*"),
            ("1234567", "*******"),
            ("12345678", "********"),
            ("123456789", "1234...6789"),
            ("SESSION123456", "SESS...3456"),
        ],
    )
    def test_default_visible_chars(self, value: str, masked: str) -> None:
        assert mask_credential(value) == masked

    def test_custom_visible_chars(self) -> None:
        assert mask_credential("abcdefg", 2) == "ab...fg"


@pytest.mark.os_agnostic
class TestSoapText:
    """An omitted SOAP string (None from zeep) reads as the empty string."""

    def test_none_reads_as_empty(self) -> None:
        assert _Reply.model_validate({"rc": 0, "msg": None}).msg == ""

    def test_text_is_kept(self) -> None:
        assert _Reply.model_validate({"rc": 0, "msg": "ok"}).msg == "ok"


@pytest.mark.os_agnostic
class TestDescribeValidationError:
    """Each failure renders as field and reason, never the input value."""

    def test_names_every_failing_field_without_the_input(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            _Reply.model_validate({"rc": "SECRET-SESSION", "msg": 7})
        described = describe_validation_error(exc_info.value)
        assert described.startswith("rc: ")
        assert "; msg: " in described
        assert "SECRET-SESSION" not in described

    def test_refusal_of_the_whole_input_names_the_whole_reply(self) -> None:
        """An empty location (a None reply) names the whole reply, not an empty field."""
        with pytest.raises(ValidationError) as exc_info:
            _Reply.model_validate(None)
        described = describe_validation_error(exc_info.value)
        assert described.startswith("(whole reply): ")
        assert not described.startswith(": ")
