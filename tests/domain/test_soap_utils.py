# pyright: reportPrivateUsage=false
"""Tests for SOAP response extraction and HTML detection utilities."""

from __future__ import annotations

import pytest

from finanzonline_uid.domain.soap_utils import (
    extract_text_from_html_error,
    is_html_response_error,
    is_zeep_parsing_error,
)


@pytest.mark.os_agnostic
class TestIsHtmlResponseError:
    """Detect HTML-instead-of-XML errors from maintenance pages."""

    def test_detects_tag_mismatch(self) -> None:
        """XML tag mismatch with HTML elements is detected."""
        exc = ValueError("Invalid XML content received (Opening and ending tag mismatch: link line 10 and head, line 11, column 8)")
        assert is_html_response_error(exc) is True

    def test_detects_html_tag(self) -> None:
        """Presence of <html in error message is detected."""
        exc = ValueError("Unexpected element <html at line 1")
        assert is_html_response_error(exc) is True

    def test_detects_body_tag(self) -> None:
        """Presence of <body in error message is detected."""
        exc = ValueError("Unexpected element <body at line 5")
        assert is_html_response_error(exc) is True

    def test_detects_doctype(self) -> None:
        """Presence of <!DOCTYPE in error message is detected."""
        exc = ValueError("Unexpected element <!DOCTYPE html>")
        assert is_html_response_error(exc) is True

    def test_ignores_regular_xml_error(self) -> None:
        """Regular XML errors are not flagged as HTML."""
        exc = ValueError("Invalid XML: missing closing tag for element foo")
        assert is_html_response_error(exc) is False

    def test_ignores_unrelated_error(self) -> None:
        """Unrelated exceptions are not flagged as HTML."""
        exc = RuntimeError("Connection timeout")
        assert is_html_response_error(exc) is False

    def test_case_insensitive(self) -> None:
        """Detection is case-insensitive."""
        exc = ValueError("TAG MISMATCH: HEAD and BODY")
        assert is_html_response_error(exc) is True


@pytest.mark.os_agnostic
class TestExtractTextFromHtmlError:
    """Extract readable text from HTML-in-XML errors."""

    def test_returns_generic_message_for_plain_error(self) -> None:
        """Falls back to generic message when no HTML is in the error."""
        exc = ValueError("tag mismatch")
        result = extract_text_from_html_error(exc)
        assert "maintenance page" in result

    def test_extracts_text_from_html_in_message(self) -> None:
        """Strips HTML tags and returns readable text."""
        exc = ValueError(
            "<html><head><title>Wartung</title></head>"
            "<body><h1>FinanzOnline ist nicht erreichbar</h1>"
            "<p>Wartungsarbeiten am 01.04.2026 von 15:30 bis 18:00</p></body></html>"
        )
        result = extract_text_from_html_error(exc)
        assert "FinanzOnline maintenance:" in result
        assert "Wartung" in result
        assert "15:30" in result
        assert "<html>" not in result

    def test_extracts_from_chained_cause(self) -> None:
        """Checks __cause__ chain for HTML content."""
        inner = ValueError("<html><body><h1>Wartung</h1><p>Service offline bis 18:00</p></body></html>")
        outer = RuntimeError("XML parsing failed")
        outer.__cause__ = inner
        result = extract_text_from_html_error(outer)
        assert "FinanzOnline maintenance:" in result
        assert "Wartung" in result


@pytest.mark.os_agnostic
class TestIsZeepParsingError:
    """Detect transient zeep response-parsing errors."""

    def test_detects_name_cannot_be_none(self) -> None:
        """Real-world TypeError from zeep Element.__init__ is detected."""
        exc = TypeError("name cannot be None", object)
        assert is_zeep_parsing_error(exc) is True

    def test_detects_zeep_class_in_message(self) -> None:
        """Reference to zeep Element class in exception text is detected."""
        exc = RuntimeError("Failed: zeep.xsd.elements.element.Element resolution failed")
        assert is_zeep_parsing_error(exc) is True

    def test_ignores_unrelated_typeerror(self) -> None:
        """Generic TypeErrors are not flagged."""
        exc = TypeError("unsupported operand type(s)")
        assert is_zeep_parsing_error(exc) is False

    def test_ignores_html_error(self) -> None:
        """HTML/maintenance errors are handled separately, not flagged here."""
        exc = ValueError("Opening and ending tag mismatch: link line 10 and head")
        assert is_zeep_parsing_error(exc) is False

    def test_case_insensitive(self) -> None:
        """Detection is case-insensitive."""
        exc = TypeError("Name Cannot Be None")
        assert is_zeep_parsing_error(exc) is True
