"""Tests for output formatters.

Tests cover human-readable and JSON formatting of UID check results.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import pytest

from finanzonline_uid.adapters.formatting import format_result_html
from finanzonline_uid.adapters.formatting.html_templates import (
    RESULT_STATUS_COLORS,
    RESULT_STATUS_LABELS,
    SEVERITY_COLORS,
    ResultStatus,
    classify_result,
    result_status_label,
)
from finanzonline_uid.adapters.output.formatters import (
    SEVERITY_ANSI_COLORS,
    STATUS_ANSI_COLORS,
    format_error_human,
    format_error_json,
    format_human,
    format_json,
)
from finanzonline_uid.domain.errors import CheckErrorInfo, ErrorKind
from finanzonline_uid.domain.models import Address, DiagnosticField, Diagnostics, SoapOperation, UidCheckResult
from finanzonline_uid.domain.return_codes import CliExitCode, Severity


def _info(
    kind: ErrorKind,
    message: str,
    *,
    return_code: int | None = None,
    retryable: bool = False,
    diagnostics: Diagnostics | None = None,
) -> CheckErrorInfo:
    """Build the error record the formatters take, with a fixed exit code."""
    return CheckErrorInfo(
        error_type=kind,
        message=message,
        exit_code=CliExitCode.QUERY_ERROR,
        return_code=return_code,
        retryable=retryable,
        diagnostics=diagnostics,
    )


@pytest.fixture
def valid_result() -> UidCheckResult:
    """Valid UID check result fixture."""
    return UidCheckResult(
        uid="DE123456789",
        return_code=0,
        message="UID is valid",
        name="Test Company GmbH",
        address=Address(line1="Test Company GmbH", line2="Street 1", line3="12345 City"),
        timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def invalid_result() -> UidCheckResult:
    """Invalid UID check result fixture."""
    return UidCheckResult(
        uid="XX123456789",
        return_code=1,
        message="UID is invalid",
        timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def error_result() -> UidCheckResult:
    """Error UID check result fixture."""
    return UidCheckResult(
        uid="DE123456789",
        return_code=1513,
        message="Rate limit exceeded",
        timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )


class TestFormatHuman:
    """Tests for format_human function."""

    def test_contains_uid(self, valid_result: UidCheckResult) -> None:
        """Should include UID in output."""
        output = format_human(valid_result)
        assert "DE123456789" in output

    def test_contains_status_valid(self, valid_result: UidCheckResult) -> None:
        """Should show VALID status for return code 0."""
        output = format_human(valid_result)
        assert "VALID" in output

    def test_contains_status_invalid(self, invalid_result: UidCheckResult) -> None:
        """Should show INVALID status for return code 1."""
        output = format_human(invalid_result)
        assert "INVALID" in output

    def test_contains_return_code(self, valid_result: UidCheckResult) -> None:
        """Should include return code."""
        output = format_human(valid_result)
        assert "Return Code: 0" in output

    def test_contains_message(self, valid_result: UidCheckResult) -> None:
        """Should include message."""
        output = format_human(valid_result)
        assert "UID is valid" in output

    def test_contains_timestamp(self, valid_result: UidCheckResult) -> None:
        """Should include timestamp in local time format."""
        output = format_human(valid_result)
        # Verify timestamp is present (exact time varies by timezone)
        assert "Timestamp:" in output
        # UTC suffix should not be present (now using local time)
        assert "UTC" not in output

    def test_contains_company_info_when_valid(self, valid_result: UidCheckResult) -> None:
        """Should include company info for valid results."""
        output = format_human(valid_result)
        assert "Test Company GmbH" in output
        assert "Street 1" in output
        assert "12345 City" in output

    def test_no_company_info_when_invalid(self, invalid_result: UidCheckResult) -> None:
        """Should not include company section for invalid results."""
        output = format_human(invalid_result)
        assert "Company Information" not in output

    def test_contains_severity(self, error_result: UidCheckResult) -> None:
        """Should include severity."""
        output = format_human(error_result)
        assert "WARNING" in output

    def test_contains_retryable(self, error_result: UidCheckResult) -> None:
        """Should indicate retryable status."""
        output = format_human(error_result)
        assert "Retryable:" in output
        assert "Yes" in output


class TestFormatJson:
    """Tests for format_json function."""

    def test_valid_json(self, valid_result: UidCheckResult) -> None:
        """Should produce valid JSON."""
        output = format_json(valid_result)
        data = json.loads(output)
        assert isinstance(data, dict)

    def test_contains_uid(self, valid_result: UidCheckResult) -> None:
        """Should include uid field."""
        output = format_json(valid_result)
        data = json.loads(output)
        assert data["uid"] == "DE123456789"

    def test_contains_is_valid(self, valid_result: UidCheckResult) -> None:
        """Should include is_valid field."""
        output = format_json(valid_result)
        data = json.loads(output)
        assert data["is_valid"] is True

    def test_invalid_is_valid_false(self, invalid_result: UidCheckResult) -> None:
        """Should set is_valid false for invalid results."""
        output = format_json(invalid_result)
        data = json.loads(output)
        assert data["is_valid"] is False

    def test_contains_return_code(self, valid_result: UidCheckResult) -> None:
        """Should include return_code field."""
        output = format_json(valid_result)
        data = json.loads(output)
        assert data["return_code"] == 0

    def test_contains_message(self, valid_result: UidCheckResult) -> None:
        """Should include message field."""
        output = format_json(valid_result)
        data = json.loads(output)
        assert data["message"] == "UID is valid"

    def test_contains_severity(self, valid_result: UidCheckResult) -> None:
        """Should include severity field."""
        output = format_json(valid_result)
        data = json.loads(output)
        assert data["severity"] == "success"

    def test_contains_retryable(self, error_result: UidCheckResult) -> None:
        """Should include retryable field."""
        output = format_json(error_result)
        data = json.loads(output)
        assert data["retryable"] is True

    def test_contains_timestamp(self, valid_result: UidCheckResult) -> None:
        """Should include ISO format timestamp."""
        output = format_json(valid_result)
        data = json.loads(output)
        assert data["timestamp"] == "2025-01-01T12:00:00+00:00"

    def test_contains_company_info_when_valid(self, valid_result: UidCheckResult) -> None:
        """Should include company object for valid results."""
        output = format_json(valid_result)
        data = json.loads(output)
        assert "company" in data
        assert data["company"]["name"] == "Test Company GmbH"
        assert "address" in data["company"]
        assert data["company"]["address"]["lines"] == ["Test Company GmbH", "Street 1", "12345 City"]

    def test_no_company_info_when_invalid(self, invalid_result: UidCheckResult) -> None:
        """Should not include company for invalid results."""
        output = format_json(invalid_result)
        data = json.loads(output)
        assert "company" not in data


# ============================================================================
# Error formatters
# ============================================================================


class TestFormatErrorHuman:
    """Tests for format_error_human function."""

    def test_contains_uid(self) -> None:
        """Should include UID in output."""
        output = format_error_human(
            _info(ErrorKind.SESSION, "Connection timed out"),
            "DE123456789",
        )
        assert "DE123456789" in output

    def test_contains_error_type(self) -> None:
        """Should include error type."""
        output = format_error_human(
            _info(ErrorKind.AUTHENTICATION, "Invalid credentials"),
            "DE123456789",
        )
        assert "Authentication Error" in output

    def test_contains_error_message(self) -> None:
        """Should include error message."""
        output = format_error_human(
            _info(ErrorKind.SESSION, "Connection timed out"),
            "DE123456789",
        )
        assert "Connection timed out" in output

    def test_contains_error_status(self) -> None:
        """Should show ERROR status."""
        output = format_error_human(
            _info(ErrorKind.SESSION, "Error"),
            "DE123456789",
        )
        assert "ERROR" in output

    def test_contains_return_code_when_provided(self) -> None:
        """Should include return code when provided."""
        output = format_error_human(
            _info(ErrorKind.QUERY, "Service unavailable", return_code=1511),
            "DE123456789",
        )
        assert "1511" in output
        assert "Meaning:" in output

    def test_contains_retryable_yes(self) -> None:
        """Should show retryable status as Yes."""
        output = format_error_human(
            _info(ErrorKind.SESSION, "Error", retryable=True),
            "DE123456789",
        )
        assert "Yes" in output

    def test_contains_retryable_no(self) -> None:
        """Should show retryable status as No."""
        output = format_error_human(
            _info(ErrorKind.AUTHENTICATION, "Error", retryable=False),
            "DE123456789",
        )
        assert "No" in output

    def test_contains_timestamp(self) -> None:
        """Should include timestamp."""
        output = format_error_human(
            _info(ErrorKind.UNEXPECTED, "Error"),
            "DE123456789",
        )
        assert "Timestamp:" in output


class TestFormatErrorJson:
    """Tests for format_error_json function."""

    def test_valid_json(self) -> None:
        """Should produce valid JSON."""
        output = format_error_json(
            _info(ErrorKind.SESSION, "Connection failed"),
            "DE123456789",
        )
        data = json.loads(output)
        assert isinstance(data, dict)

    def test_contains_uid(self) -> None:
        """Should include uid field."""
        output = format_error_json(
            _info(ErrorKind.UNEXPECTED, "Failed"),
            "DE123456789",
        )
        data = json.loads(output)
        assert data["uid"] == "DE123456789"

    def test_is_valid_false(self) -> None:
        """Should set is_valid to false."""
        output = format_error_json(
            _info(ErrorKind.UNEXPECTED, "Failed"),
            "DE123456789",
        )
        data = json.loads(output)
        assert data["is_valid"] is False

    def test_error_flag_true(self) -> None:
        """Should set error flag to true."""
        output = format_error_json(
            _info(ErrorKind.UNEXPECTED, "Failed"),
            "DE123456789",
        )
        data = json.loads(output)
        assert data["error"] is True

    def test_contains_error_type(self) -> None:
        """Should include error_type field."""
        output = format_error_json(
            _info(ErrorKind.AUTHENTICATION, "Failed"),
            "DE123456789",
        )
        data = json.loads(output)
        assert data["error_type"] == "Authentication Error"

    def test_contains_message(self) -> None:
        """Should include message field."""
        output = format_error_json(
            _info(ErrorKind.UNEXPECTED, "Connection timed out"),
            "DE123456789",
        )
        data = json.loads(output)
        assert data["message"] == "Connection timed out"

    def test_contains_return_code_when_provided(self) -> None:
        """Should include return_code when provided."""
        output = format_error_json(
            _info(ErrorKind.QUERY, "Unavailable", return_code=1511),
            "DE123456789",
        )
        data = json.loads(output)
        assert data["return_code"] == 1511
        assert "meaning" in data
        assert "severity" in data

    def test_no_return_code_when_not_provided(self) -> None:
        """Should not include return_code when not provided."""
        output = format_error_json(
            _info(ErrorKind.UNEXPECTED, "Failed"),
            "DE123456789",
        )
        data = json.loads(output)
        assert "return_code" not in data

    def test_contains_retryable(self) -> None:
        """Should include retryable field."""
        output = format_error_json(
            _info(ErrorKind.UNEXPECTED, "Failed", retryable=True),
            "DE123456789",
        )
        data = json.loads(output)
        assert data["retryable"] is True

    def test_contains_timestamp(self) -> None:
        """Should include ISO format timestamp."""
        output = format_error_json(
            _info(ErrorKind.UNEXPECTED, "Failed"),
            "DE123456789",
        )
        data = json.loads(output)
        assert "timestamp" in data
        assert "T" in data["timestamp"]  # ISO format


# ============================================================================
# Wire pins: the JSON output must stay byte-identical across refactors.
# The expected texts were produced by the formatter before it was rebuilt on
# output models; a change here is a change of the CLI's JSON contract.
# ============================================================================

_TIMESTAMP_VALUE = re.compile(r'"timestamp": "([^"]+)"')


def _without_timestamp(output: str) -> str:
    """Replace the wall-clock timestamp of an error JSON, after checking its form."""
    match = _TIMESTAMP_VALUE.search(output)
    assert match is not None
    stamp = datetime.fromisoformat(match.group(1))
    assert stamp.utcoffset() is not None and stamp.utcoffset() == timezone.utc.utcoffset(None)
    assert match.group(1).endswith("+00:00")
    return _TIMESTAMP_VALUE.sub('"timestamp": "<TS>"', output)


_FULL_DIAGNOSTICS = Diagnostics(
    operation=SoapOperation.UID_QUERY,
    tid="123***789",
    benid="TE***",
    pin="se***n",
    uid_tn="ATU1",
    target_uid="DE1",
    session_id="S1",
    return_code="1513",
    response_message="Too many <q>",
    error_detail="x & y",
)


class TestJsonWirePins:
    """Byte-exact pins of the result and error JSON."""

    def test_result_with_company(self) -> None:
        """A result with name and address keeps every key, order and nesting."""
        result = UidCheckResult(
            uid="DE123456789",
            return_code=0,
            message="UID is valid",
            name="Test & Co <GmbH>",
            address=Address(line1="Test Co", line2="Street 1", line3="12345 City"),
            timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        )
        expected = r"""{
  "uid": "DE123456789",
  "is_valid": true,
  "return_code": 0,
  "message": "UID is valid",
  "severity": "success",
  "retryable": false,
  "timestamp": "2025-01-01T12:00:00+00:00",
  "company": {
    "name": "Test & Co <GmbH>",
    "address": {
      "lines": [
        "Test Co",
        "Street 1",
        "12345 City"
      ],
      "text": "Test Co\nStreet 1\n12345 City"
    }
  }
}"""
        assert format_json(result) == expected

    def test_result_without_company_omits_the_key(self) -> None:
        """A result with no company data has no company key at all."""
        result = UidCheckResult(
            uid="XX1",
            return_code=1,
            message="UID is invalid",
            timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        )
        expected = """{
  "uid": "XX1",
  "is_valid": false,
  "return_code": 1,
  "message": "UID is invalid",
  "severity": "warning",
  "retryable": false,
  "timestamp": "2025-01-01T12:00:00+00:00"
}"""
        assert format_json(result) == expected

    def test_company_with_name_only_omits_address(self) -> None:
        """An absent address is left out of the company object, never null."""
        result = UidCheckResult(
            uid="ATU1",
            return_code=0,
            message="ok",
            name="Only Name",
            timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        )
        assert json.loads(format_json(result))["company"] == {"name": "Only Name"}

    def test_company_with_address_only_omits_name(self) -> None:
        """An empty name is left out of the company object, never an empty string."""
        result = UidCheckResult(
            uid="ATU1",
            return_code=0,
            message="ok",
            address=Address(line1="Street 1"),
            timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        )
        assert json.loads(format_json(result))["company"] == {"address": {"lines": ["Street 1"], "text": "Street 1"}}

    def test_error_without_return_code(self) -> None:
        """An error without return code or diagnostics carries only the base keys."""
        output = format_error_json(_info(ErrorKind.AUTHENTICATION, "Login failed"), "DE1")
        expected = """{
  "uid": "DE1",
  "is_valid": false,
  "error": true,
  "error_type": "Authentication Error",
  "message": "Login failed",
  "retryable": false,
  "timestamp": "<TS>"
}"""
        assert _without_timestamp(output) == expected

    def test_error_with_return_code_and_all_diagnostics(self) -> None:
        """Return-code keys follow the timestamp; diagnostics keys keep display order."""
        info = _info(ErrorKind.QUERY, "boom", return_code=1511, retryable=True, diagnostics=_FULL_DIAGNOSTICS)
        expected = """{
  "uid": "DE4",
  "is_valid": false,
  "error": true,
  "error_type": "Query Error",
  "message": "boom",
  "retryable": true,
  "timestamp": "<TS>",
  "return_code": 1511,
  "meaning": "Service unavailable",
  "severity": "critical",
  "diagnostics": {
    "operation": "uidAbfrage",
    "tid": "123***789",
    "benid": "TE***",
    "pin": "se***n",
    "uid_tn": "ATU1",
    "target_uid": "DE1",
    "session_id": "S1",
    "return_code": "1513",
    "response_message": "Too many <q>",
    "error_detail": "x & y"
  }
}"""
        assert _without_timestamp(format_error_json(info, "DE4")) == expected

    def test_error_with_raw_response(self) -> None:
        """The raw SOAP response is the last diagnostics key."""
        diagnostics = Diagnostics(operation=SoapOperation.LOGIN, raw_response="<xml a='1'>&</xml>")
        output = format_error_json(_info(ErrorKind.SESSION, "raw", diagnostics=diagnostics), "DE5")
        expected = """{
  "uid": "DE5",
  "is_valid": false,
  "error": true,
  "error_type": "Session Error",
  "message": "raw",
  "retryable": false,
  "timestamp": "<TS>",
  "diagnostics": {
    "operation": "login",
    "raw_response": "<xml a='1'>&</xml>"
  }
}"""
        assert _without_timestamp(output) == expected

    def test_error_with_raw_response_only(self) -> None:
        """Diagnostics holding only a raw response still print the diagnostics object."""
        diagnostics = Diagnostics(raw_response="<r/>")
        output = format_error_json(_info(ErrorKind.UNEXPECTED, "raw", diagnostics=diagnostics), "DE5")
        assert json.loads(output)["diagnostics"] == {"raw_response": "<r/>"}

    def test_error_with_empty_diagnostics_omits_the_key(self) -> None:
        """Empty diagnostics leave the diagnostics key out, never an empty object."""
        output = format_error_json(_info(ErrorKind.VALIDATION, "v", diagnostics=Diagnostics()), "DE6")
        assert "diagnostics" not in json.loads(output)

    def test_diagnostics_keys_are_the_diagnostic_field_values(self) -> None:
        """Every DiagnosticField reaches the JSON under its value, then raw_response."""
        diagnostics = Diagnostics(
            operation=SoapOperation.LOGOUT,
            tid="t",
            benid="b",
            pin="p",
            uid_tn="u",
            target_uid="g",
            session_id="s",
            return_code="r",
            response_message="m",
            error_detail="e",
            raw_response="x",
        )
        output = format_error_json(_info(ErrorKind.SESSION, "m", diagnostics=diagnostics), "DE1")
        keys = list(json.loads(output)["diagnostics"])
        assert keys == [field.value for field in DiagnosticField] + ["raw_response"]

    def test_error_with_every_diagnostics_field_populated(self) -> None:
        """Every diagnostics field, raw_response included, at its byte-exact place and escaping."""
        diagnostics = Diagnostics(
            operation=SoapOperation.LOGOUT,
            tid="t",
            benid="b",
            pin="p",
            uid_tn="u",
            target_uid="g",
            session_id="s",
            return_code="r",
            response_message="m",
            error_detail="e",
            raw_response='<x a="1">' + chr(0xE4) + "</x>",
        )
        output = format_error_json(_info(ErrorKind.SESSION, "m", diagnostics=diagnostics), "DE1")
        expected = r"""{
  "uid": "DE1",
  "is_valid": false,
  "error": true,
  "error_type": "Session Error",
  "message": "m",
  "retryable": false,
  "timestamp": "<TS>",
  "diagnostics": {
    "operation": "logout",
    "tid": "t",
    "benid": "b",
    "pin": "p",
    "uid_tn": "u",
    "target_uid": "g",
    "session_id": "s",
    "return_code": "r",
    "response_message": "m",
    "error_detail": "e",
    "raw_response": "<x a=\"1\">\u00e4</x>"
  }
}"""
        assert _without_timestamp(output) == expected

    def test_error_with_empty_diagnostics_bytes(self) -> None:
        """Empty diagnostics give exactly the bytes of an error without any diagnostics."""
        output = format_error_json(_info(ErrorKind.SESSION, "m", diagnostics=Diagnostics()), "DE1")
        expected = """{
  "uid": "DE1",
  "is_valid": false,
  "error": true,
  "error_type": "Session Error",
  "message": "m",
  "retryable": false,
  "timestamp": "<TS>"
}"""
        assert _without_timestamp(output) == expected

    @pytest.mark.parametrize("kind", list(ErrorKind))
    def test_error_type_is_the_kind_label(self, kind: ErrorKind) -> None:
        """error_type carries the ErrorKind value, the same label the console shows."""
        output = format_error_json(_info(kind, "m"), "DE1")
        assert json.loads(output)["error_type"] == kind.value
        assert f'"error_type": "{kind.value}"' in output


class TestErrorHumanEnums:
    """Enum members reach the console as their values, never as Class.MEMBER."""

    def test_error_type_and_severity_are_values(self) -> None:
        """The error kind and the severity print as plain labels."""
        output = format_error_human(_info(ErrorKind.SERVICE_MAINTENANCE, "m", return_code=-2), "DE1")
        assert "Service Maintenance" in output
        assert "WARNING" in output
        assert "ErrorKind." not in output
        assert "Severity." not in output

    def test_diagnostics_use_field_labels(self) -> None:
        """Each diagnostics line is headed by its DiagnosticField label."""
        output = format_error_human(_info(ErrorKind.QUERY, "m", diagnostics=_FULL_DIAGNOSTICS), "DE1")
        for field in DiagnosticField:
            assert f"\n{field.label}: " in output
        assert "Raw SOAP Response" not in output

    def test_raw_response_section(self) -> None:
        """A raw response gets its own section after the diagnostics."""
        diagnostics = Diagnostics(operation=SoapOperation.LOGIN, raw_response="<r/>")
        output = format_error_human(_info(ErrorKind.SESSION, "m", diagnostics=diagnostics), "DE1")
        assert output.endswith("Raw SOAP Response\x1b[0m\n------------------------------\n<r/>")


def test_severity_ansi_colors_cover_every_severity() -> None:
    """The console colour table has exactly one entry per Severity."""
    assert set(SEVERITY_ANSI_COLORS) == set(Severity)


def test_status_ansi_colors_cover_every_status() -> None:
    """The console status colour table has exactly one entry per ResultStatus."""
    assert set(STATUS_ANSI_COLORS) == set(ResultStatus)


def _console_status_line(return_code: int) -> str:
    """Return the Status line of the human output for a return code."""
    result = UidCheckResult(
        uid="DE1",
        return_code=return_code,
        message="m",
        timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )
    lines = [line for line in format_human(result).splitlines() if line.startswith("Status:")]
    assert len(lines) == 1
    return lines[0]


_HTML_BADGE = re.compile(r'border-radius: 4px; font-weight: bold;">([^<]+)</span>')


class TestConsoleStatus:
    """The console status follows classify_result, like the HTML and email output."""

    @pytest.mark.parametrize(
        ("return_code", "expected"),
        [
            # Valid, invalid and plain errors keep the exact bytes printed before.
            (0, "Status:      \x1b[32m\x1b[1mVALID\x1b[0m"),
            (1, "Status:      \x1b[31m\x1b[1mINVALID\x1b[0m"),
            (-4, "Status:      \x1b[33m\x1b[1mERROR\x1b[0m"),
            (9999, "Status:      \x1b[33m\x1b[1mERROR\x1b[0m"),
            # These printed ERROR before while HTML and email said otherwise.
            (1513, "Status:      \x1b[33m\x1b[1mRATE LIMITED\x1b[0m"),
            (1514, "Status:      \x1b[33m\x1b[1mRATE LIMITED\x1b[0m"),
            (1511, "Status:      \x1b[33m\x1b[1mUNAVAILABLE\x1b[0m"),
            (1512, "Status:      \x1b[33m\x1b[1mUNAVAILABLE\x1b[0m"),
            (-2, "Status:      \x1b[33m\x1b[1mUNAVAILABLE\x1b[0m"),
        ],
    )
    def test_status_line_bytes(self, return_code: int, expected: str) -> None:
        """Each return code prints its status label in its colour."""
        assert _console_status_line(return_code) == expected

    @pytest.mark.parametrize("return_code", [0, 1, -2, -4, 1511, 1512, 1513, 1514, 9999])
    def test_console_label_matches_html_badge(self, return_code: int) -> None:
        """The console prints the same status label as the HTML badge for the same code."""
        result = UidCheckResult(
            uid="DE1",
            return_code=return_code,
            message="m",
            timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        )
        badge = _HTML_BADGE.search(format_result_html(result))
        assert badge is not None
        assert f"\x1b[1m{badge.group(1)}\x1b[0m" in _console_status_line(return_code)


class TestStatusAndSeverityTables:
    """The enum-keyed lookup tables of the HTML templates cover their whole enum."""

    def test_status_labels_cover_every_status(self) -> None:
        """Every ResultStatus has a label."""
        assert set(RESULT_STATUS_LABELS) == set(ResultStatus)

    def test_status_colors_cover_every_status(self) -> None:
        """Every ResultStatus has a badge colour."""
        assert set(RESULT_STATUS_COLORS) == set(ResultStatus)

    def test_severity_colors_cover_every_severity(self) -> None:
        """Every Severity has an HTML colour."""
        assert set(SEVERITY_COLORS) == set(Severity)

    @pytest.mark.parametrize(
        ("return_code", "status", "label", "color"),
        [
            (0, ResultStatus.VALID, "VALID", "#28a745"),
            (1, ResultStatus.INVALID, "INVALID", "#dc3545"),
            (1511, ResultStatus.UNAVAILABLE, "UNAVAILABLE", "#6c757d"),
            (1512, ResultStatus.UNAVAILABLE, "UNAVAILABLE", "#6c757d"),
            (-2, ResultStatus.UNAVAILABLE, "UNAVAILABLE", "#6c757d"),
            (1513, ResultStatus.RATE_LIMITED, "RATE LIMITED", "#ffc107"),
            (1514, ResultStatus.RATE_LIMITED, "RATE LIMITED", "#ffc107"),
            (-4, ResultStatus.ERROR, "ERROR", "#dc3545"),
            (9999, ResultStatus.ERROR, "ERROR", "#dc3545"),
        ],
    )
    def test_classification_label_and_color(self, return_code: int, status: ResultStatus, label: str, color: str) -> None:
        """A return code maps to one status, shown with the same label and colour as before."""
        assert classify_result(return_code) == status
        assert result_status_label(status) == label
        assert RESULT_STATUS_COLORS[status] == color

    def test_html_result_shows_status_badge_and_severity(self) -> None:
        """The HTML result carries the badge colour, label and upper-case severity value."""
        result = UidCheckResult(
            uid="DE1",
            return_code=1513,
            message="m",
            timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        )
        output = format_result_html(result)
        assert 'background-color: #ffc107; color: white; padding: 4px 12px; border-radius: 4px; font-weight: bold;">RATE LIMITED</span>' in output
        assert '<span style="color: #ffc107; font-weight: bold;">WARNING</span>' in output
        assert "Severity." not in output
