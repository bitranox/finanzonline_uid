"""``[finanzonline].email_format`` decides the body parts of the result and error emails ``check`` sends.

Each run goes through the whole CLI: the real configuration readers, the real
:class:`EmailNotificationAdapter` and btx_lib_mail's message composition. Only the use case
and the SMTP wire are replaced, through Click's ``obj``
(:class:`finanzonline_uid.cli.CliDependencies`) and the adapter's ``transport`` seam, so the
assertions read the MIME parts of the message that would have been sent.
"""

from __future__ import annotations

import dataclasses
import email
from datetime import datetime, timezone
from typing import Any

import pytest
from click.testing import CliRunner, Result
from lib_layered_config import Config

from conftest import RecordingTransport
from finanzonline_uid import cli as cli_mod
from finanzonline_uid.adapters.notification import EmailNotificationAdapter
from finanzonline_uid.config import FinanzOnlineConfig
from finanzonline_uid.domain.errors import QueryError
from finanzonline_uid.domain.models import FinanzOnlineCredentials, UidCheckResult
from finanzonline_uid.enums import EmailFormat
from finanzonline_uid.mail import EmailConfig

#: Body parts each configured format produces, as the leaf MIME types of the message.
_PARTS: dict[str | None, list[str]] = {
    None: ["text/html"],
    "html": ["text/html"],
    "plain": ["text/plain"],
    "both": ["text/plain", "text/html"],
}

_CREDENTIALS: dict[str, Any] = {
    "tid": "123456789",
    "benid": "TESTUSER",
    "pin": "testpin",
    "uid_tn": "ATU12345678",
    "herstellerid": "ATU12345678",
}


class _Checker:
    """A use case returning (or raising) one fixed outcome."""

    def __init__(self, outcome: UidCheckResult | Exception) -> None:
        self._outcome = outcome

    def execute(self, credentials: FinanzOnlineCredentials, uid_tn: str, target_uid: str) -> UidCheckResult:
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


def _valid_result() -> UidCheckResult:
    return UidCheckResult(uid="DE123456789", return_code=0, message="UID is valid", timestamp=datetime(2026, 1, 2, tzinfo=timezone.utc))


def _config_data(email_format: str | None, *, credentials: bool = True) -> dict[str, Any]:
    """A configuration with mail set up, the given email_format and cache and rate limit off."""
    finanzonline: dict[str, Any] = {"cache_results_hours": 0, "ratelimit_queries": 0}
    if credentials:
        finanzonline.update(_CREDENTIALS)
    if email_format is not None:
        finanzonline["email_format"] = email_format
    return {
        "finanzonline": finanzonline,
        "email": {"smtp_hosts": ["smtp.example.com"], "from_address": "alerts@example.com", "default_recipients": ["ops@example.com"]},
    }


def _run(config_data: dict[str, Any], outcome: UidCheckResult | Exception, transport: RecordingTransport) -> Result:
    """Run ``check DE123456789`` with the real config readers and email adapter."""

    def load_config(*, profile: str | None = None) -> Config:
        return Config(config_data, {})

    def build_uid_checker(_fo_config: FinanzOnlineConfig, _notifier: cli_mod.RateLimitNotifier) -> cli_mod.UidChecker:
        return _Checker(outcome)

    def build_email_sender(email_config: EmailConfig, email_format: EmailFormat) -> cli_mod.EmailSender:
        return EmailNotificationAdapter(email_config, email_format, transport=transport)

    deps = dataclasses.replace(
        cli_mod.production_dependencies(),
        load_config=load_config,
        build_uid_checker=build_uid_checker,
        build_email_sender=build_email_sender,
    )
    return CliRunner().invoke(cli_mod.cli, ["check", "DE123456789"], obj=deps)


def _sent_parts(transport: RecordingTransport) -> list[str]:
    """The leaf MIME types of the one message sent."""
    assert len(transport.deliveries) == 1
    message = email.message_from_string(transport.deliveries[0]["raw"])
    return [part.get_content_type() for part in message.walk() if not part.is_multipart()]


@pytest.mark.os_agnostic
@pytest.mark.parametrize("configured", list(_PARTS), ids=lambda value: f"email_format={value}")
def test_result_email_is_sent_in_the_configured_format(configured: str | None) -> None:
    transport = RecordingTransport()

    result = _run(_config_data(configured), _valid_result(), transport)

    assert result.exit_code == 0
    assert _sent_parts(transport) == _PARTS[configured]


@pytest.mark.os_agnostic
@pytest.mark.parametrize("configured", list(_PARTS), ids=lambda value: f"email_format={value}")
def test_error_email_is_sent_in_the_configured_format(configured: str | None) -> None:
    transport = RecordingTransport()

    result = _run(_config_data(configured), QueryError("Service down", return_code=-2), transport)

    assert result.exit_code == 4
    assert _sent_parts(transport) == _PARTS[configured]


@pytest.mark.os_agnostic
@pytest.mark.parametrize("configured", list(_PARTS), ids=lambda value: f"email_format={value}")
def test_configuration_error_email_is_sent_in_the_configured_format(configured: str | None) -> None:
    """With the credentials missing, [finanzonline] does not load, and the error email still honours the format."""
    transport = RecordingTransport()

    result = _run(_config_data(configured, credentials=False), _valid_result(), transport)

    assert result.exit_code == 2
    assert _sent_parts(transport) == _PARTS[configured]
