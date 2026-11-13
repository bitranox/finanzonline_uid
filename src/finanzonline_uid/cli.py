"""CLI adapter wiring the behavior helpers into a rich-click interface.

Expose a stable command-line surface so tooling, documentation, and packaging
automation can be exercised while the richer logging helpers are being built.

Contents:
    * :data:`CLICK_CONTEXT_SETTINGS` - shared Click settings.
    * :func:`apply_traceback_preferences` - synchronises traceback configuration.
    * :func:`snapshot_traceback_state` / :func:`restore_traceback_state` - state management.
    * :class:`CliDependencies` / :func:`production_dependencies` - the composition seam:
      the collaborators the commands use, replaceable through Click's ``obj``.
    * :func:`cli` - root command group wiring global options.
    * :func:`main` - entry point for console scripts and ``python -m`` execution.

    With ``check --format json`` stdout carries exactly one JSON document: the
    result, or the error record of a failure the command reports (the stderr
    text and exit codes are the same as with ``--format human``). The
    ``--interactive`` prompt, the retry countdown and the "Result saved to"
    note go to stderr in that mode, so they never land in the parsed stream.

System Role:
    The CLI is the primary adapter for local development workflows; packaging
    targets register the console script defined in :mod:`finanzonline_uid.__init__conf__`.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable, Generator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Final, NamedTuple, NoReturn, Protocol

import lib_cli_exit_tools
import lib_log_rich.runtime
import rich_click as click
from click.core import ParameterSource
from click.exceptions import Abort, ClickException
from lib_cli_exit_tools.adapters.signals import SigIntInterrupt
from lib_layered_config import Config
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from . import __init__conf__, safe_console
from .adapters.cache import UidResultCache
from .adapters.finanzonline import FinanzOnlineQueryClient, FinanzOnlineSessionClient
from .adapters.notification import EmailNotificationAdapter
from .adapters.output import format_error_json, format_html, format_human, format_json
from .adapters.ratelimit import RateLimitStatus, RateLimitTracker
from .application.use_cases import CheckUidUseCase
from .behaviors import emit_greeting, noop_main, raise_intentional_failure
from .config import FinanzOnlineConfig, get_config, load_app_config, load_email_format, load_finanzonline_config, path_setting
from .config_deploy import deploy_configuration
from .config_show import display_config
from .domain.errors import (
    AuthenticationError,
    CheckErrorInfo,
    ConfigurationError,
    ErrorKind,
    QueryError,
    ServiceMaintenanceError,
    SessionError,
    UidCheckError,
)
from .domain.models import FinanzOnlineCredentials, UidCheckResult, sanitize_uid
from .domain.return_codes import CliExitCode, get_return_code_info, is_retryable
from .enums import DeployTarget, EmailFormat, FileFormat, NotificationKind, OutputFormat
from .i18n import _, setup_locale
from .logging_setup import init_logging
from .mail import EmailConfig, load_email_config
from .typed_click import argument, option, version_option

#: Shared Click context flags so help output stays consistent across commands.
CLICK_CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}
#: Character budget used when printing truncated tracebacks.
TRACEBACK_SUMMARY_LIMIT: Final[int] = 500
#: Character budget used when verbose tracebacks are enabled.
TRACEBACK_VERBOSE_LIMIT: Final[int] = 10_000
#: Pattern for ANSI escape codes (used for stripping colors from file output).
_ANSI_PATTERN: Final[re.Pattern[str]] = re.compile(r"\033\[[0-9;]*m")

logger = logging.getLogger(__name__)


class TracebackState(NamedTuple):
    """Traceback configuration of ``lib_cli_exit_tools`` captured for later restoration.

    Attributes:
        enabled: Whether full tracebacks are printed.
        force_color: Whether tracebacks are coloured even without a terminal.
    """

    enabled: bool
    force_color: bool


class ErrorCategory(NamedTuple):
    """How a UID check exception is reported: its category and the exit code.

    Attributes:
        kind: Category shown to the reader (its value is the display label).
        exit_code: CLI exit code for this category.
    """

    kind: ErrorKind
    exit_code: CliExitCode


#: Category per exception type. The lookup is by EXACT type, so a subclass
#: (ServiceMaintenanceError is a SessionError) needs its own row.
_ERROR_CATEGORIES: Final[Mapping[type[UidCheckError], ErrorCategory]] = MappingProxyType(
    {
        ConfigurationError: ErrorCategory(ErrorKind.CONFIGURATION, CliExitCode.CONFIG_ERROR),
        AuthenticationError: ErrorCategory(ErrorKind.AUTHENTICATION, CliExitCode.AUTH_ERROR),
        ServiceMaintenanceError: ErrorCategory(ErrorKind.SERVICE_MAINTENANCE, CliExitCode.QUERY_ERROR),
        SessionError: ErrorCategory(ErrorKind.SESSION, CliExitCode.QUERY_ERROR),
        QueryError: ErrorCategory(ErrorKind.QUERY, CliExitCode.QUERY_ERROR),
    }
)
#: Category for any other UidCheckError subclass.
_FALLBACK_ERROR_CATEGORY: Final[ErrorCategory] = ErrorCategory(ErrorKind.UID_CHECK, CliExitCode.QUERY_ERROR)


#: Callback the use case calls when the rate limit is exceeded.
RateLimitNotifier = Callable[[RateLimitStatus], None]


class UidChecker(Protocol):
    """What the ``check`` command needs from the UID check use case."""

    def execute(self, credentials: FinanzOnlineCredentials, uid_tn: str, target_uid: str) -> UidCheckResult:
        """Run one Level 2 UID check.

        Args:
            credentials: FinanzOnline credentials.
            uid_tn: The participant's own Austrian UID.
            target_uid: The UID to verify.

        Returns:
            The result FinanzOnline returned (or a cached one).
        """
        ...


class EmailSender(Protocol):
    """What the ``check`` command needs from the email notification adapter."""

    def send_result(self, result: UidCheckResult, recipients: list[str]) -> bool:
        """Send a check result; ``True`` when it was delivered."""
        ...

    def send_error(self, info: CheckErrorInfo, uid: str, recipients: list[str]) -> bool:
        """Send a check error; ``True`` when it was delivered."""
        ...

    def send_rate_limit_warning(self, status: RateLimitStatus, recipients: list[str]) -> bool:
        """Send a rate limit warning; ``True`` when it was delivered."""
        ...


class ConfigLoader(Protocol):
    """Loads the layered configuration for an optional profile."""

    def __call__(self, *, profile: str | None = None) -> Config:
        """Return the merged configuration of ``profile`` (None: no profile)."""
        ...


class ConfigDeployer(Protocol):
    """Writes the default configuration into the given layers."""

    def __call__(self, *, targets: Sequence[DeployTarget], force: bool = False, profile: str | None = None) -> list[Path]:
        """Deploy to ``targets`` and return the paths written."""
        ...


@dataclass(frozen=True, slots=True)
class CliDependencies:
    """Collaborators the commands reach configuration, FinanzOnline and mail through.

    This is the CLI's composition seam: :func:`production_dependencies` builds
    the real set in one place, and a caller (a test, an embedding tool) hands
    another set in as Click's ``obj``, for example
    ``CliRunner().invoke(cli, [...], obj=dependencies)``. Every field is
    required, so a replacement set cannot silently fall back to a real
    collaborator: :func:`dataclasses.replace` on the production set is the way
    to swap only some.

    Attributes:
        load_config: Loads the layered configuration (root command and
            ``config --profile``).
        load_finanzonline_config: Reads the ``[finanzonline]`` section.
        build_uid_checker: Builds the use case for one check attempt from the
            FinanzOnline settings and the rate limit callback.
        build_email_sender: Builds the email sender from the ``[email]`` settings
            and the email body format (``[finanzonline].email_format``).
        deploy_configuration: Writes the default configuration files.
    """

    load_config: ConfigLoader
    load_finanzonline_config: Callable[[Config], FinanzOnlineConfig]
    build_uid_checker: Callable[[FinanzOnlineConfig, RateLimitNotifier], UidChecker]
    build_email_sender: Callable[[EmailConfig, EmailFormat], EmailSender]
    deploy_configuration: ConfigDeployer


def production_dependencies() -> CliDependencies:
    """Return the collaborators the installed CLI runs with.

    Returns:
        The real configuration loaders, SOAP-backed use case, email adapter and
        configuration deployer.

    Example:
        >>> production_dependencies().load_finanzonline_config is load_finanzonline_config
        True
    """
    return CliDependencies(
        load_config=get_config,
        load_finanzonline_config=load_finanzonline_config,
        build_uid_checker=_build_uid_checker,
        build_email_sender=EmailNotificationAdapter,
        deploy_configuration=deploy_configuration,
    )


def _resolve_dependencies(obj: object) -> CliDependencies:
    """Pick the collaborators for this run from the ``obj`` Click was started with.

    Args:
        obj: Click's initial context object: None for a normal run, a
            :class:`CliDependencies` when the caller injects collaborators.

    Returns:
        The injected set, or the production set when none was given.

    Raises:
        TypeError: If ``obj`` is anything else; ignoring it would run the real
            collaborators where the caller meant to replace them.
    """
    if obj is None:
        return production_dependencies()
    if isinstance(obj, CliDependencies):
        return obj
    raise TypeError(f"the CLI's Click obj must be a CliDependencies or None, got {type(obj).__name__}")


@dataclass(frozen=True, slots=True)
class PreparedNotification:
    """An email sender ready to send, with the recipients it sends to.

    Attributes:
        adapter: Email sender built from the ``[email]`` configuration.
        recipients: Resolved, non-empty recipient list.
    """

    adapter: EmailSender
    recipients: list[str]


#: What a check produces: a result from FinanzOnline, or the error that ended it.
CheckOutcome = UidCheckResult | CheckErrorInfo


@dataclass(slots=True)
class CliContext:
    """Typed Click context object for passing state between commands.

    Replaces untyped dict access with typed field access.

    Attributes:
        config: Layered configuration loaded by the root command.
        dependencies: Collaborators the commands use.
        profile: Configuration profile given to the root command.
        traceback: Whether verbose tracebacks were requested.
    """

    config: Config
    dependencies: CliDependencies
    profile: str | None = None
    traceback: bool = False


@dataclass(frozen=True, slots=True)
class CheckInvocation:
    """What one ``check`` run carries through its helpers.

    Attributes:
        config: Layered configuration of this run.
        dependencies: Collaborators of this run.
        recipients: Recipients given with ``--recipient`` (may be empty).
        output_format: Console output format.
        send_notification: Whether result and error emails are sent.
    """

    config: Config
    dependencies: CliDependencies
    recipients: list[str]
    output_format: OutputFormat
    send_notification: bool


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text.

    Args:
        text: Text potentially containing ANSI color codes.

    Returns:
        Clean text without ANSI escape sequences.
    """
    return _ANSI_PATTERN.sub("", text)


def apply_traceback_preferences(enabled: bool) -> None:
    """Synchronise shared traceback flags with the requested preference.

    Args:
        enabled: ``True`` enables full tracebacks with colour.

    Example:
        >>> apply_traceback_preferences(True)
        >>> bool(lib_cli_exit_tools.config.traceback)
        True
    """
    lib_cli_exit_tools.config.traceback = bool(enabled)
    lib_cli_exit_tools.config.traceback_force_color = bool(enabled)


def snapshot_traceback_state() -> TracebackState:
    """Capture the current traceback configuration for later restoration.

    Returns:
        The current ``(enabled, force_color)`` state.
    """
    return TracebackState(
        enabled=bool(getattr(lib_cli_exit_tools.config, "traceback", False)),
        force_color=bool(getattr(lib_cli_exit_tools.config, "traceback_force_color", False)),
    )


def restore_traceback_state(state: TracebackState) -> None:
    """Reapply a previously captured traceback configuration.

    Args:
        state: State returned by :func:`snapshot_traceback_state`.
    """
    lib_cli_exit_tools.config.traceback = state.enabled
    lib_cli_exit_tools.config.traceback_force_color = state.force_color


def _store_cli_context(
    ctx: click.Context,
    *,
    traceback: bool,
    config: Config,
    dependencies: CliDependencies,
    profile: str | None = None,
) -> None:
    """Store CLI state in the Click context for subcommand access.

    Args:
        ctx: Click context associated with the current invocation.
        traceback: Whether verbose tracebacks were requested.
        config: Loaded layered configuration object for all subcommands.
        dependencies: Collaborators the subcommands use.
        profile: Optional configuration profile name.
    """
    ctx.obj = CliContext(config=config, dependencies=dependencies, profile=profile, traceback=traceback)


def _run_cli(argv: Sequence[str] | None) -> int:
    """Execute the CLI via lib_cli_exit_tools with exception handling.

    Args:
        argv: Optional sequence of CLI arguments. None uses sys.argv.

    Returns:
        Exit code produced by the command.
    """
    try:
        return lib_cli_exit_tools.run_cli(
            cli,
            argv=list(argv) if argv is not None else None,
            prog_name=__init__conf__.shell_command,
        )
    except BaseException as exc:  # noqa: BLE001 - top-level entry point must convert every failure to an exit code
        tracebacks_enabled = bool(getattr(lib_cli_exit_tools.config, "traceback", False))
        apply_traceback_preferences(tracebacks_enabled)
        length_limit = TRACEBACK_VERBOSE_LIMIT if tracebacks_enabled else TRACEBACK_SUMMARY_LIMIT
        lib_cli_exit_tools.print_exception_message(trace_back=tracebacks_enabled, length_limit=length_limit)
        return lib_cli_exit_tools.get_system_exit_code(exc)


@click.group(
    help=__init__conf__.title,
    context_settings=CLICK_CONTEXT_SETTINGS,
    invoke_without_command=True,
)
@version_option(
    version=__init__conf__.version,
    prog_name=__init__conf__.shell_command,
    message=f"{__init__conf__.shell_command} version {__init__conf__.version}",
)
@option(
    "--traceback/--no-traceback",
    is_flag=True,
    default=False,
    help=_("Show full Python traceback on errors"),
)
@option(
    "--profile",
    type=str,
    default=None,
    help=_("Load configuration from a named profile (e.g., 'production', 'test')"),
)
@click.pass_context
def cli(ctx: click.Context, traceback: bool, profile: str | None) -> None:
    """Root command storing global flags and syncing shared traceback state.

    Loads configuration once with the profile and stores it in the Click context
    for all subcommands to access. Mirrors the traceback flag into
    ``lib_cli_exit_tools.config`` so downstream helpers observe the preference.
    A :class:`CliDependencies` passed as Click's ``obj`` replaces the
    production collaborators for this run.
    """
    dependencies = _resolve_dependencies(ctx.obj)
    config = dependencies.load_config(profile=profile)
    app_config = load_app_config(config)
    setup_locale(app_config.language)
    init_logging(config)
    _store_cli_context(ctx, traceback=traceback, config=config, dependencies=dependencies, profile=profile)
    apply_traceback_preferences(traceback)

    if ctx.invoked_subcommand is None:
        # No subcommand: show help unless --traceback was explicitly passed
        source = ctx.get_parameter_source("traceback")
        if source not in (ParameterSource.DEFAULT, None):
            cli_main()
        else:
            safe_console.echo(ctx.get_help())


def cli_main() -> None:
    """Run the placeholder domain entry when callers opt into execution."""
    noop_main()


@cli.command("info", context_settings=CLICK_CONTEXT_SETTINGS)
def cli_info() -> None:
    """Print resolved metadata so users can inspect installation details."""
    with lib_log_rich.runtime.bind(job_id="cli-info", extra={"command": "info"}):
        logger.info("Displaying package information")
        __init__conf__.print_info()


@cli.command("hello", context_settings=CLICK_CONTEXT_SETTINGS)
def cli_hello() -> None:
    """Demonstrate the success path by emitting the canonical greeting."""
    with lib_log_rich.runtime.bind(job_id="cli-hello", extra={"command": "hello"}):
        logger.info("Executing hello command")
        emit_greeting()


@cli.command("fail", context_settings=CLICK_CONTEXT_SETTINGS)
def cli_fail() -> None:
    """Trigger the intentional failure helper to test error handling."""
    with lib_log_rich.runtime.bind(job_id="cli-fail", extra={"command": "fail"}):
        logger.warning("Executing intentional failure command")
        raise_intentional_failure()


@cli.command("config", context_settings=CLICK_CONTEXT_SETTINGS)
@option(
    "--format",
    type=click.Choice([f for f in OutputFormat], case_sensitive=False),
    default=OutputFormat.HUMAN,
    help=_("Output format (human-readable or JSON)"),
)
@option(
    "--section",
    type=str,
    default=None,
    help=_("Show only a specific configuration section (e.g., 'lib_log_rich')"),
)
@option(
    "--profile",
    type=str,
    default=None,
    help=_("Override profile from root command (e.g., 'production', 'test')"),
)
@click.pass_context
def cli_config(ctx: click.Context, format: OutputFormat, section: str | None, profile: str | None) -> None:
    """Display the current merged configuration from all sources.

    Shows configuration loaded from defaults, application/user config files,
    .env files, and environment variables.

    Precedence: defaults -> app -> host -> user -> dotenv -> env
    """
    # Use config from context; reload if profile override specified
    cli_ctx: CliContext = ctx.obj
    if profile:
        config = cli_ctx.dependencies.load_config(profile=profile)
        effective_profile = profile
    else:
        config = cli_ctx.config
        effective_profile = cli_ctx.profile

    # click.Choice over the enum members hands back the member itself (matched on
    # its name, case-insensitively), so ``format`` is already an OutputFormat.
    extra = {"command": "config", "format": format.value, "profile": effective_profile}
    with lib_log_rich.runtime.bind(job_id="cli-config", extra=extra):
        logger.info("Displaying configuration", extra={"format": format.value, "section": section, "profile": effective_profile})
        display_config(config, format=format, section=section)


def _display_deploy_result(deployed_paths: list[Path], effective_profile: str | None, *, force: bool = False) -> None:
    """Display deployment result to user."""
    if deployed_paths:
        profile_msg = f" ({_('profile')}: {effective_profile})" if effective_profile else ""
        safe_console.echo(f"\n{_('Configuration deployed successfully')}{profile_msg}:")
        for path in deployed_paths:
            safe_console.echo(f"  ✓ {path}")
    elif force:
        # Force was used but nothing deployed - content is identical
        safe_console.echo(f"\n{_('All configuration files are already up to date (content unchanged).')}")
    else:
        safe_console.echo(f"\n{_('No files were created (all target files already exist).')}")
        safe_console.echo(_("Use --force to overwrite existing configuration files."))


def _handle_deploy_error(exc: Exception) -> None:
    """Handle deployment errors with appropriate logging and messages."""
    if isinstance(exc, PermissionError):
        logger.error("Permission denied when deploying configuration", extra={"error": str(exc)})
        safe_console.echo(f"\n{_('Error')}: {_('Permission denied.')} {exc}", err=True)
        safe_console.echo(_("Hint: System-wide deployment (--target app/host) may require sudo."), err=True)
    else:
        logger.error("Failed to deploy configuration", extra={"error": str(exc), "error_type": type(exc).__name__})
        safe_console.echo(f"\n{_('Error')}: {_('Failed to deploy configuration:')} {exc}", err=True)
    raise SystemExit(1)


@cli.command("config-deploy", context_settings=CLICK_CONTEXT_SETTINGS)
@option(
    "--target",
    "targets",
    type=click.Choice([t for t in DeployTarget], case_sensitive=False),
    multiple=True,
    required=True,
    help=_("Target configuration layer(s) to deploy to (can specify multiple)"),
)
@option(
    "--force",
    is_flag=True,
    default=False,
    help=_("Overwrite existing configuration files"),
)
@option(
    "--profile",
    type=str,
    default=None,
    help=_("Override profile from root command (e.g., 'production', 'test')"),
)
@click.pass_context
def cli_config_deploy(ctx: click.Context, targets: tuple[DeployTarget, ...], force: bool, profile: str | None) -> None:
    """Deploy default configuration to system or user directories.

    Creates configuration files in platform-specific locations:

    \b
    - app:  System-wide application config (requires privileges)
    - host: System-wide host config (requires privileges)
    - user: User-specific config (~/.config on Linux)

    By default, existing files are not overwritten. Use --force to overwrite.
    """
    cli_ctx: CliContext = ctx.obj
    effective_profile = profile if profile else cli_ctx.profile
    target_strs = tuple(t.value for t in targets)
    extra = {"command": "config-deploy", "targets": target_strs, "force": force, "profile": effective_profile}

    with lib_log_rich.runtime.bind(job_id="cli-config-deploy", extra=extra):
        logger.info("Deploying configuration", extra={"targets": target_strs, "force": force, "profile": effective_profile})

        try:
            deployed_paths = cli_ctx.dependencies.deploy_configuration(targets=targets, force=force, profile=effective_profile)
            _display_deploy_result(deployed_paths, effective_profile, force=force)
        except Exception as exc:  # noqa: BLE001 - CLI command boundary converts any deploy failure to a clean message
            _handle_deploy_error(exc)


# =============================================================================
# UID Check Command
# =============================================================================


def _get_uid_check_error_info(exc: UidCheckError) -> CheckErrorInfo:
    """Get CheckErrorInfo for UidCheckError subclasses."""
    category = _ERROR_CATEGORIES.get(type(exc), _FALLBACK_ERROR_CATEGORY)
    return CheckErrorInfo(
        error_type=category.kind,
        message=exc.message,
        exit_code=category.exit_code,
        return_code=exc.return_code,
        retryable=exc.retryable,
        diagnostics=exc.diagnostics,
    )


def _get_error_info(exc: Exception) -> CheckErrorInfo:
    """Get CheckErrorInfo for an exception.

    Args:
        exc: The exception to get info for.

    Returns:
        CheckErrorInfo with error details.
    """
    if isinstance(exc, UidCheckError):
        return _get_uid_check_error_info(exc)
    if isinstance(exc, ValueError):
        return CheckErrorInfo(
            error_type=ErrorKind.VALIDATION,
            message=str(exc),
            exit_code=CliExitCode.CONFIG_ERROR,
        )
    return CheckErrorInfo(
        error_type=ErrorKind.UNEXPECTED,
        message=str(exc),
        exit_code=CliExitCode.QUERY_ERROR,
    )


def _emit_json_error(output_format: OutputFormat, info: CheckErrorInfo, uid: str) -> None:
    """Write the JSON error record to stdout when JSON output was requested.

    The human-readable error lines always go to stderr; a caller that asked
    for JSON parses stdout, so the failure has to reach it there as well.

    Args:
        output_format: Console output format of this run.
        info: The failure to report.
        uid: The UID being checked, or ``""`` when none was given.
    """
    if output_format == OutputFormat.JSON:
        safe_console.echo(format_error_json(info, uid))


def _refuse_check(message: str, *, output_format: OutputFormat, uid: str) -> NoReturn:
    """Refuse an invalid ``check`` invocation before anything is queried.

    Args:
        message: The translated refusal line printed to stderr.
        output_format: Console output format of this run.
        uid: The (sanitized) UID given, or ``""`` when none was given.

    Raises:
        SystemExit: Always, with the configuration error exit code.
    """
    safe_console.echo(message, err=True)
    # The record's message drops the "Error: " lead-in the stderr line carries,
    # because error_type already says it is an error; reusing the existing
    # translated line keeps every locale's wording without a new msgid.
    record_message = message.removeprefix(f"{_('Error')}: ")
    info = CheckErrorInfo(error_type=ErrorKind.VALIDATION, message=record_message, exit_code=CliExitCode.CONFIG_ERROR)
    _emit_json_error(output_format, info, uid)
    raise SystemExit(info.exit_code)


def _notes_to_stderr(output_format: OutputFormat) -> bool:
    """Whether progress text (prompt, countdown, file notes) goes to stderr.

    A JSON caller parses stdout as one document, so in that mode nothing but
    the document may reach it. The human format keeps these lines on stdout,
    where they have always been.

    Examples:
        >>> _notes_to_stderr(OutputFormat.JSON), _notes_to_stderr(OutputFormat.HUMAN)
        (True, False)
    """
    return output_format == OutputFormat.JSON


def _resolve_uid_input(uid: str | None, interactive: bool, *, output_format: OutputFormat) -> str:
    """Resolve UID from argument or interactive prompt.

    Applies sanitization to remove copy-paste artifacts (whitespace,
    non-printable characters) and normalizes to uppercase.

    Args:
        uid: UID argument from CLI (may be None).
        interactive: Whether to prompt interactively.
        output_format: Console output format: picks the prompt's stream and
            shapes the refusal record.

    Returns:
        The sanitized UID string (uppercase, no whitespace).

    Raises:
        SystemExit: If UID is required but not provided.

    Examples:
        >>> _resolve_uid_input("  DE 123 456 789  ", False, output_format=OutputFormat.HUMAN)
        'DE123456789'
    """
    if interactive:
        raw_uid = click.prompt(_("Enter EU VAT ID to verify"), type=str, err=_notes_to_stderr(output_format))
    elif uid is None:
        _refuse_check(_("Error: UID argument is required (or use --interactive)"), output_format=output_format, uid="")
    else:
        raw_uid = uid

    return sanitize_uid(raw_uid)


def _output_check_result(result: UidCheckResult, output_format: OutputFormat) -> None:
    """Output the check result in the requested format.

    Args:
        result: UidCheckResult to output.
        output_format: Console output format.
    """
    if output_format == OutputFormat.JSON:
        safe_console.echo(format_json(result))
    else:
        safe_console.echo(format_human(result))


def _render_result_file(result: UidCheckResult, file_format: FileFormat) -> str:
    """Render the content of a saved result file.

    Args:
        result: UidCheckResult to render.
        file_format: Format of the file.

    Returns:
        The file content; the text format has its colour codes stripped.
    """
    if file_format == FileFormat.JSON:
        return format_json(result)
    if file_format == FileFormat.HTML:
        return format_html(result)
    return _strip_ansi(format_human(result))


def _save_result_to_file(result: UidCheckResult, outputdir: Path, file_format: FileFormat, *, output_format: OutputFormat) -> None:
    """Save valid UID result to file in the output directory.

    Creates a file named <UID>_<YYYY-MM-DD>.<ext> with the result in the
    specified format. Only called for valid UIDs (return_code == 0).
    Overwrites existing file if present (one file per UID per day).
    Creates the output directory if it doesn't exist.

    On filesystem errors (permissions, disk full, etc.), logs a warning but
    does not raise - the UID check succeeded and should not be marked as failed.

    Args:
        result: UidCheckResult to save.
        outputdir: Directory to save the file in.
        file_format: Format of the file content; its value is also the extension.
        output_format: Console output format; picks the stream of the
            "Result saved to" note.
    """
    date_str = result.timestamp.strftime("%Y-%m-%d")
    filename = f"{result.uid}_{date_str}.{file_format.value}"
    filepath = outputdir / filename

    try:
        # Create directory if it doesn't exist
        outputdir.mkdir(parents=True, exist_ok=True)
        filepath.write_text(_render_result_file(result, file_format), encoding="utf-8")

        safe_console.echo(_("Result saved to: {filepath}").format(filepath=filepath), err=_notes_to_stderr(output_format))
    except OSError as exc:
        # Log warning but don't fail - the UID check itself succeeded
        warning_msg = _("Warning: Could not save result to {filepath}: {error}").format(filepath=filepath, error=exc)
        safe_console.echo(warning_msg, err=True)


def _emit_check_result(result: UidCheckResult, *, output_format: OutputFormat, outputdir: Path | None, file_format: FileFormat) -> None:
    """Print the check result and save it to a file when it is valid.

    Args:
        result: UidCheckResult to output.
        output_format: Console output format.
        outputdir: Directory to save valid results in, or None to skip saving.
        file_format: Format for the saved file.
    """
    _output_check_result(result, output_format)
    if outputdir and result.is_valid:
        _save_result_to_file(result, outputdir, file_format, output_format=output_format)


def _handle_check_error(
    error_info: CheckErrorInfo,
    *,
    run: CheckInvocation,
    fo_config: FinanzOnlineConfig | None,
    uid: str,
) -> NoReturn:
    """Handle check command errors with output and notification.

    Args:
        error_info: Consolidated error information.
        run: The check invocation (format, recipients, notification switch).
        fo_config: FinanzOnline configuration (may be None).
        uid: The UID being checked.

    Raises:
        SystemExit: Always raises with the specified exit code.
    """
    safe_console.echo(f"\n{error_info.error_type.value}: {error_info.message}", err=True)

    if error_info.return_code is not None:
        info = get_return_code_info(error_info.return_code)
        safe_console.echo(f"  {_('Return code:')} {error_info.return_code} ({info.meaning})", err=True)

    if error_info.retryable:
        safe_console.echo(f"  {_('This error may be temporary. Try again later.')}", err=True)

    _emit_json_error(run.output_format, error_info, uid)

    if run.send_notification:
        _send_error_notification(run, fo_config=fo_config, uid=uid, error_info=error_info)

    raise SystemExit(error_info.exit_code)


# =============================================================================
# Retry Loop with Animated Countdown
# =============================================================================


def _format_countdown(seconds_remaining: int, attempt: int, uid: str) -> Panel:
    """Format countdown display with UID and attempt info.

    Args:
        seconds_remaining: Seconds until next attempt.
        attempt: Current attempt number.
        uid: The UID being checked.

    Returns:
        Rich Panel with UID, countdown and attempt info.
    """
    minutes = seconds_remaining // 60
    secs = seconds_remaining % 60

    text = Text()
    text.append(_("Checking"), style="white")
    text.append(": ", style="white")
    text.append(uid, style="bold green")
    text.append("\n")
    text.append(_("Next attempt in"), style="white")
    text.append(": ", style="white")
    text.append(f"{minutes:02d}:{secs:02d}", style="bold cyan")
    text.append("\n")
    text.append(_("Attempts so far"), style="dim")
    text.append(": ", style="dim")
    text.append(str(attempt), style="bold yellow")
    text.append("\n\n")
    text.append(f"⚠ {_('Retries indefinitely')}", style="bold yellow")
    text.append("\n")
    text.append(_("Ctrl+C to stop"), style="dim")

    title = _("Retry Mode (unlimited)")
    return Panel(text, title=title, border_style="blue")


def _wait_with_countdown(seconds: float, attempt: int, uid: str, *, output_format: OutputFormat) -> bool:
    """Wait with animated countdown display.

    Args:
        seconds: Total seconds to wait.
        attempt: Current attempt number for display.
        uid: The UID being checked (displayed in countdown).
        output_format: Console output format; picks the countdown's stream.

    Returns:
        True if wait completed, False if interrupted by Ctrl+C.
    """
    end_time = time.time() + seconds
    # None keeps rich's global console (stdout), where the human format has
    # always drawn the countdown.
    console = Console(stderr=True) if _notes_to_stderr(output_format) else None

    try:
        with Live(_format_countdown(int(seconds), attempt, uid), console=console, refresh_per_second=1) as live:
            while True:
                remaining = int(end_time - time.time())
                if remaining <= 0:
                    return True
                live.update(_format_countdown(remaining, attempt, uid))
                time.sleep(0.5)
    except (SigIntInterrupt, KeyboardInterrupt):
        return False


def _echo_cancelled(attempt: int) -> None:
    """Tell the user the retry loop was cancelled after ``attempt`` attempts.

    Args:
        attempt: Number of attempts made before the cancellation.
    """
    safe_console.echo(f"\n{_('Cancelled by user after')} {attempt} {_('attempt(s)')}", err=True)


def _announce_retry(attempt: int, message: str, retry_minutes: float) -> None:
    """Report a failed attempt, and on the first one explain the retry mode.

    Args:
        attempt: Current attempt number.
        message: Why the attempt did not produce a final result.
        retry_minutes: Minutes between retry attempts.
    """
    safe_console.echo(f"\n{_('Attempt')} {attempt}: {message}", err=True)
    if attempt == 1:
        interval_display = f"{retry_minutes:g}"
        safe_console.echo(
            _("Retry mode: Will keep retrying every {minutes} min with no limit — only stops on success or Ctrl+C.").format(minutes=interval_display),
            err=True,
        )


def _wait_for_next_attempt(attempt: int, message: str, *, retry_minutes: float, uid: str, output_format: OutputFormat) -> bool:
    """Announce a retryable failure and count down to the next attempt.

    Args:
        attempt: Current attempt number.
        message: Why the attempt did not produce a final result.
        retry_minutes: Minutes between retry attempts.
        uid: The UID being checked (displayed in countdown).
        output_format: Console output format; picks the countdown's stream.

    Returns:
        True to retry, False if the user cancelled during the countdown
        (the cancellation has already been reported).
    """
    _announce_retry(attempt, message, retry_minutes)
    # Animated countdown (handles Ctrl+C internally)
    if _wait_with_countdown(retry_minutes * 60, attempt, uid, output_format=output_format):
        return True
    _echo_cancelled(attempt)
    return False


def _cancelled_outcome(last_result: UidCheckResult | None, last_error: CheckErrorInfo | None) -> CheckOutcome:
    """Pick what a Ctrl+C during an attempt returns from the retry loop.

    Args:
        last_result: Result of the most recent completed attempt, if any.
        last_error: Most recent retryable error, if any.

    Returns:
        The last error if one occurred, else the last result, else a
        cancellation error.
    """
    if last_error is not None:
        return last_error
    if last_result is not None:
        return last_result
    return _cancelled_error_info()


def _cancelled_error_info() -> CheckErrorInfo:
    """Return the error a check cancelled by the user ends with."""
    return CheckErrorInfo(
        error_type=ErrorKind.CANCELLED,
        message=_("Check cancelled by user"),
        exit_code=CliExitCode.QUERY_ERROR,
    )


def _execute_retry_loop(
    fo_config: FinanzOnlineConfig,
    uid: str,
    retry_minutes: float,
    run: CheckInvocation,
) -> CheckOutcome:
    """Execute UID check with retry loop.

    Uses lib_cli_exit_tools signal handling (SigIntInterrupt on Ctrl+C).
    Shows animated countdown between attempts.

    Args:
        fo_config: FinanzOnline configuration with credentials.
        uid: Target UID to verify.
        retry_minutes: Minutes between retry attempts.
        run: The check invocation (configuration, recipients, collaborators).

    Returns:
        The final result, or the error that ended the loop.
    """
    attempt = 0
    last_error: CheckErrorInfo | None = None

    last_result: UidCheckResult | None = None

    while True:
        attempt += 1
        logger.info("UID check attempt %d", attempt, extra={"uid": uid})

        try:
            result = _execute_uid_check(fo_config, uid, run)
            last_result = result

            # Check if result indicates success OR non-retryable error
            if result.is_valid or not is_retryable(result.return_code):
                return result  # Final result (success or non-retryable)

            # Retryable return code (e.g., 1511 Service Unavailable) - continue loop
            if not _wait_for_next_attempt(attempt, result.message, retry_minutes=retry_minutes, uid=uid, output_format=run.output_format):
                # User cancelled during wait - return last result
                return result

        except (SigIntInterrupt, KeyboardInterrupt):
            # User pressed Ctrl+C - clean exit
            _echo_cancelled(attempt)
            return _cancelled_outcome(last_result, last_error)

        except (ConfigurationError, AuthenticationError, ValueError) as exc:
            # Non-retryable errors - stop immediately
            return _get_error_info(exc)

        except (SessionError, QueryError) as exc:
            error_info = _get_error_info(exc)
            if not error_info.retryable:
                return error_info

            # Retryable error - show message and wait
            last_error = error_info
            if not _wait_for_next_attempt(attempt, error_info.message, retry_minutes=retry_minutes, uid=uid, output_format=run.output_format):
                # User cancelled during wait
                return last_error


def _outputdir_option(value: str | None) -> Path | None:
    """Turn the ``--outputdir`` text into a directory, None when it names none.

    The value goes through :func:`finanzonline_uid.config.path_setting`, the
    rule ``finanzonline.output_dir`` is read with, so an empty or
    whitespace-only argument means "not given" (the configured directory
    applies) instead of a directory named with spaces or the current one.

    Args:
        value: The option's text, or None when the option was not given.

    Returns:
        The directory, or None when the option names none.

    Examples:
        >>> _outputdir_option("   ") is None, _outputdir_option("") is None, _outputdir_option("out").name
        (True, True, 'out')
    """
    return None if value is None else path_setting(value)


def _outputdir_callback(_ctx: click.Context, _param: click.Parameter, value: str | None) -> Path | None:
    """Click callback of ``--outputdir``; see :func:`_outputdir_option`."""
    return _outputdir_option(value)


@cli.command("check", context_settings=CLICK_CONTEXT_SETTINGS)
@argument("uid", required=False)
@option(
    "--interactive",
    "-i",
    is_flag=True,
    default=False,
    help=_("Interactive mode: prompt for UID to check"),
)
@option(
    "--no-email",
    is_flag=True,
    default=False,
    help=_("Disable email notification (default: email enabled)"),
)
@option(
    "--format",
    "output_format",
    type=click.Choice(list(OutputFormat), case_sensitive=False),
    default=OutputFormat.HUMAN,
    help=_("Output format (default: human)"),
)
@option(
    "--recipient",
    "recipients",
    multiple=True,
    help=_("Email recipient (can specify multiple, uses config default if not specified)"),
)
@option(
    "--retryminutes",
    type=float,
    default=None,
    help=_("Retry interval in minutes until check succeeds or canceled (interactive mode only)"),
)
@option(
    "--outputdir",
    "-o",
    # Read as text, not path_type=Path: Path("") is Path("."), so a converted
    # value could no longer tell an empty argument from an explicit ".".
    type=click.Path(file_okay=False, dir_okay=True),
    default=None,
    callback=_outputdir_callback,
    help=_("Directory to save valid UID results as files (overrides config)"),
)
@option(
    "--outputformat",
    "file_format",
    type=click.Choice(list(FileFormat), case_sensitive=False),
    default=None,
    help=_("Output file format: json, txt, or html (default: html)"),
)
@click.pass_context
def cli_check(
    ctx: click.Context,
    uid: str | None,
    interactive: bool,
    no_email: bool,
    output_format: OutputFormat,
    recipients: tuple[str, ...],
    retryminutes: float | None,
    outputdir: Path | None,
    file_format: FileFormat | None,
) -> None:
    """Verify an EU VAT ID via FinanzOnline Level 2 query.

    Queries the Austrian BMF FinanzOnline webservice to verify the validity
    of the specified VAT identification number. Level 2 queries return the
    registered company name and address if the UID is valid.

    \b
    Exit Codes:
      0 - UID is valid
      1 - UID is invalid
      2 - Configuration error
      3 - Authentication error
      4 - Query error

    \b
    Examples:
      finanzonline-uid check DE123456789
      finanzonline-uid check FR12345678901 --format json
      finanzonline-uid check IT12345678901 --no-email
      finanzonline-uid check ES12345678A --recipient admin@example.com
      finanzonline-uid check --interactive
      finanzonline-uid check --interactive --retryminutes 5
    """
    # Click's own usage errors (an invalid --format value, an unknown option)
    # are raised while parsing, before this body runs, so the output format is
    # not known yet and they stay as Click reports them. The same holds for a
    # failure in the root command (loading the configuration).
    cli_ctx: CliContext = ctx.obj
    run = CheckInvocation(
        config=cli_ctx.config,
        dependencies=cli_ctx.dependencies,
        recipients=list(recipients),
        output_format=output_format,
        send_notification=not no_email,
    )
    subject = _CheckSubject()

    with _json_record_for_unreported_errors(output_format, subject):
        if retryminutes is not None and not interactive:
            subject.uid = sanitize_uid(uid) if uid is not None else ""
            _refuse_check(_("Error: --retryminutes requires --interactive mode"), output_format=output_format, uid=subject.uid)

        subject.uid = _resolve_uid_input(uid, interactive, output_format=output_format)
        extra = {"command": "check", "uid": subject.uid, "no_email": no_email, "format": output_format.value, "retryminutes": retryminutes}
        with lib_log_rich.runtime.bind(job_id="cli-check", extra=extra):
            _run_check(run, subject.uid, retry_minutes=retryminutes, outputdir=outputdir, file_format=file_format)


@dataclass(slots=True)
class _CheckSubject:
    """The UID a ``check`` run is about, once it is known (``""`` before)."""

    uid: str = ""


@contextmanager
def _json_record_for_unreported_errors(output_format: OutputFormat, subject: _CheckSubject) -> Generator[None, None, None]:
    """Give a failure ``check`` does not report itself its JSON record, then let it propagate.

    The errors ``check`` reports itself end in ``SystemExit`` with their record
    already written. What else escapes (a Ctrl+C outside the retry loop, an
    unexpected exception) is printed to stderr and mapped to an exit code by
    ``lib_cli_exit_tools``; re-raising unchanged keeps that text and that exit
    code, and only the stdout record is added.

    Args:
        output_format: Console output format of this run.
        subject: Holder of the UID being checked.

    Yields:
        Nothing; the body runs inside the guard.

    Raises:
        BaseException: Whatever the body raised, unchanged.
    """
    try:
        yield
    except ClickException:
        # Click formats and reports its own exceptions; they are usage errors.
        raise
    except (SigIntInterrupt, KeyboardInterrupt, Abort):
        # Abort is what click.prompt raises for Ctrl+C or end of input.
        _emit_json_error(output_format, _cancelled_error_info(), subject.uid)
        raise
    except Exception as exc:
        _emit_json_error(output_format, _get_error_info(exc), subject.uid)
        raise


def _run_check(
    run: CheckInvocation,
    uid: str,
    *,
    retry_minutes: float | None,
    outputdir: Path | None,
    file_format: FileFormat | None,
) -> NoReturn:
    """Check ``uid``, report the outcome and exit with its code.

    Args:
        run: The check invocation.
        uid: The sanitized UID to verify.
        retry_minutes: Minutes between retries, or None for a single attempt.
        outputdir: ``--outputdir`` (overrides the configured directory).
        file_format: ``--outputformat`` (overrides the configured format).

    Raises:
        SystemExit: Always, with the exit code of the outcome.
    """
    fo_config: FinanzOnlineConfig | None = None
    try:
        fo_config = run.dependencies.load_finanzonline_config(run.config)
        logger.info("FinanzOnline configuration loaded", extra={"uid_tn": fo_config.uid_tn})

        # Resolve output settings (CLI overrides config)
        effective_outputdir = outputdir or fo_config.output_dir
        effective_file_format = file_format or fo_config.output_format

        outcome: CheckOutcome
        if retry_minutes is None:
            # Single attempt mode: errors propagate to the handler below
            outcome = _execute_uid_check(fo_config, uid, run)
        else:
            # Retry mode - uses retry loop with countdown animation
            outcome = _execute_retry_loop(fo_config, uid, retry_minutes, run)

        if isinstance(outcome, CheckErrorInfo):
            # Error (cancelled or non-retryable)
            _handle_check_error(outcome, run=run, fo_config=fo_config, uid=uid)
        _emit_check_result(outcome, output_format=run.output_format, outputdir=effective_outputdir, file_format=effective_file_format)
        if run.send_notification:
            _send_check_notification(run, fo_config=fo_config, result=outcome)
        raise SystemExit(CliExitCode.SUCCESS if outcome.is_valid else CliExitCode.UID_INVALID)

    except (ConfigurationError, AuthenticationError, SessionError, QueryError, ValueError, UidCheckError) as exc:
        error_info = _get_error_info(exc)
        logger.error(error_info.error_type.value, extra={"error": str(exc)})
        if isinstance(exc, ConfigurationError):
            _show_config_help(exc.message)
        _handle_check_error(error_info, run=run, fo_config=fo_config, uid=uid)


def _create_cache(fo_config: FinanzOnlineConfig) -> UidResultCache | None:
    """Create cache adapter from configuration.

    Args:
        fo_config: FinanzOnline configuration with cache settings.

    Returns:
        UidResultCache if caching is enabled (cache_results_hours > 0), None otherwise.
    """
    if fo_config.cache_results_hours <= 0:
        return None

    if fo_config.cache_file is None:
        return None

    return UidResultCache(
        cache_file=fo_config.cache_file,
        cache_hours=fo_config.cache_results_hours,
    )


def _create_rate_limiter(fo_config: FinanzOnlineConfig) -> RateLimitTracker | None:
    """Create rate limit tracker from configuration.

    Args:
        fo_config: FinanzOnline configuration with rate limit settings.

    Returns:
        RateLimitTracker if enabled (ratelimit_queries > 0), None otherwise.
    """
    if fo_config.ratelimit_queries <= 0:
        return None

    if fo_config.ratelimit_file is None:
        return None

    return RateLimitTracker(
        ratelimit_file=fo_config.ratelimit_file,
        max_queries=fo_config.ratelimit_queries,
        window_hours=fo_config.ratelimit_hours,
    )


def _log_notification_result(success: bool, recipients: list[str], kind: NotificationKind) -> None:
    """Log the result of a notification attempt."""
    if success:
        logger.info("%s email sent", kind.value, extra={"recipients": recipients})
    else:
        logger.warning("%s email failed", kind.value)


def _create_rate_limit_notifier(run: CheckInvocation, fo_config: FinanzOnlineConfig) -> RateLimitNotifier:
    """Create a rate limit notification callback.

    Args:
        run: The check invocation (email settings, explicit recipients).
        fo_config: FinanzOnline configuration with default recipients.

    Returns:
        Callable that sends a rate limit warning email; it does nothing when
        no SMTP host or recipient is configured.
    """

    def notifier(status: RateLimitStatus) -> None:
        """Send rate limit warning email (non-fatal on failure)."""
        try:
            prepared = _prepare_notification(run, fo_config, NotificationKind.RATE_LIMIT_WARNING)
            if prepared is None:
                return
            success = prepared.adapter.send_rate_limit_warning(status, prepared.recipients)
            _log_notification_result(success, prepared.recipients, NotificationKind.RATE_LIMIT_WARNING)
        except Exception as e:  # noqa: BLE001 - notification send is non-fatal, must not abort the check
            logger.warning("Rate limit notification error (non-fatal): %s", e)

    return notifier


def _build_uid_checker(fo_config: FinanzOnlineConfig, rate_limit_notifier: RateLimitNotifier) -> CheckUidUseCase:
    """Build the production use case for one check attempt.

    Args:
        fo_config: FinanzOnline configuration (timeouts, cache, rate limit).
        rate_limit_notifier: Called when the rate limit is exceeded. The use
            case consults it only when rate limiting is enabled.

    Returns:
        The use case wired to the SOAP clients, cache and rate limiter.
    """
    return CheckUidUseCase(
        FinanzOnlineSessionClient(timeout=fo_config.session_timeout),
        FinanzOnlineQueryClient(timeout=fo_config.query_timeout),
        cache=_create_cache(fo_config),
        rate_limiter=_create_rate_limiter(fo_config),
        rate_limit_notifier=rate_limit_notifier,
    )


def _execute_uid_check(fo_config: FinanzOnlineConfig, uid: str, run: CheckInvocation) -> UidCheckResult:
    """Execute UID check via use case.

    Args:
        fo_config: FinanzOnline configuration with credentials.
        uid: Target UID to verify.
        run: The check invocation (collaborators, rate limit email settings).

    Returns:
        UidCheckResult from the use case.
    """
    checker = run.dependencies.build_uid_checker(fo_config, _create_rate_limit_notifier(run, fo_config))
    return checker.execute(credentials=fo_config.credentials, uid_tn=fo_config.uid_tn, target_uid=uid)


def _show_config_help(error_message: str) -> None:
    """Display configuration help for FinanzOnline credentials.

    Args:
        error_message: The configuration error message.
    """
    safe_console.echo(f"\n{_('Error')}: {error_message}", err=True)
    safe_console.echo(f"\n{_('Configure FinanzOnline credentials in your config file or via environment variables:')}", err=True)
    safe_console.echo(f"  FINANZONLINE_UID___FINANZONLINE__TID=... ({_('8-12 alphanumeric')})", err=True)
    safe_console.echo(f"  FINANZONLINE_UID___FINANZONLINE__BENID=... ({_('5-12 chars')})", err=True)
    safe_console.echo(f"  FINANZONLINE_UID___FINANZONLINE__PIN=... ({_('5-128 chars')})", err=True)
    safe_console.echo("  FINANZONLINE_UID___FINANZONLINE__UID_TN=ATU...", err=True)
    safe_console.echo(f"  FINANZONLINE_UID___FINANZONLINE__HERSTELLERID=... ({_('10-24 alphanumeric')})", err=True)


def _resolve_notification_recipients(
    explicit: list[str],
    email_config: EmailConfig,
    fo_config: FinanzOnlineConfig | None,
) -> list[str]:
    """Resolve final recipients: explicit > email config > fo_config."""
    if explicit:
        return explicit
    if email_config.default_recipients:
        return email_config.default_recipients
    if fo_config and fo_config.default_recipients:
        return fo_config.default_recipients
    return []


def _prepare_notification(
    run: CheckInvocation,
    fo_config: FinanzOnlineConfig | None,
    kind: NotificationKind,
) -> PreparedNotification | None:
    """Prepare email notification adapter and recipients.

    The ``[email]`` section is loaded here, per notification, on purpose: the
    callers wrap this call in their non-fatal handler, so an invalid email
    setting costs only the notification and never fails the check itself.

    Args:
        run: The check invocation (configuration, explicit recipients, sender factory).
        fo_config: FinanzOnline configuration (may be None).
        kind: Kind of notification, named in the log messages.

    Returns:
        The sender and its recipients if ready, None if skipped.
    """
    email_config = load_email_config(run.config)

    if not email_config.smtp_hosts:
        logger.warning("%s notification skipped: no SMTP hosts configured", kind.value)
        return None

    final_recipients = _resolve_notification_recipients(run.recipients, email_config, fo_config)
    if not final_recipients:
        logger.warning("%s notification skipped: no recipients configured", kind.value)
        return None

    email_format = _notification_email_format(run, fo_config)
    return PreparedNotification(adapter=run.dependencies.build_email_sender(email_config, email_format), recipients=final_recipients)


def _notification_email_format(run: CheckInvocation, fo_config: FinanzOnlineConfig | None) -> EmailFormat:
    """Return the email body format a notification of this run is sent in.

    Args:
        run: The check invocation (its configuration).
        fo_config: FinanzOnline configuration, or None when it failed to load.

    Returns:
        ``fo_config.email_format``; when the section failed to load (the error
        email of a missing-credentials run, say), the format read from the
        configuration on its own, so that email still honours the setting.
    """
    if fo_config is not None:
        return fo_config.email_format
    return load_email_format(run.config)


def _send_check_notification(run: CheckInvocation, *, fo_config: FinanzOnlineConfig, result: UidCheckResult) -> None:
    """Send email notification for check result (non-fatal on failure)."""
    try:
        prepared = _prepare_notification(run, fo_config, NotificationKind.RESULT)
        if prepared is None:
            return

        if prepared.adapter.send_result(result, prepared.recipients):
            logger.info("Email notification sent", extra={"recipients": prepared.recipients})
        else:
            logger.warning("Email notification failed")

    except Exception as e:  # noqa: BLE001 - notification send is non-fatal, must not abort the check
        logger.warning("Email notification error (non-fatal): %s", e)
        safe_console.echo(_("Warning: Email notification failed: {error}").format(error=e), err=True)


def _send_error_notification(
    run: CheckInvocation,
    *,
    fo_config: FinanzOnlineConfig | None,
    uid: str,
    error_info: CheckErrorInfo,
) -> None:
    """Send email notification for check error (non-fatal on failure)."""
    try:
        prepared = _prepare_notification(run, fo_config, NotificationKind.ERROR)
        if prepared is None:
            return

        success = prepared.adapter.send_error(error_info, uid, prepared.recipients)
        if success:
            logger.info("Error notification sent", extra={"recipients": prepared.recipients})
        else:
            logger.warning("Error notification failed")

    except Exception as e:  # noqa: BLE001 - notification send is non-fatal, must not abort the check
        logger.warning("Error notification error (non-fatal): %s", e)
        safe_console.echo(_("Warning: Error notification failed: {error}").format(error=e), err=True)


def main(argv: Sequence[str] | None = None, *, restore_traceback: bool = True) -> int:
    """Execute the CLI with error handling and return the exit code.

    Provides the single entry point used by console scripts and
    ``python -m`` execution so that behaviour stays identical across transports.

    Args:
        argv: Optional sequence of CLI arguments. None uses sys.argv.
        restore_traceback: Whether to restore prior traceback configuration after execution.

    Returns:
        Exit code reported by the CLI run.
    """
    previous_state = snapshot_traceback_state()
    try:
        return _run_cli(argv)
    finally:
        if restore_traceback:
            restore_traceback_state(previous_state)
        if lib_log_rich.runtime.is_initialised():
            _shutdown_logging()


def _shutdown_logging() -> None:
    """Stop the logging runtime without letting a teardown failure replace the command's result.

    An exception raised in ``main``'s ``finally`` would discard the exit code the
    command returned: a slow log sink (an unreachable Graylog) made a finished
    check end in a traceback instead. Logging is gone at this point, so the
    warning goes straight to stderr.
    """
    try:
        lib_log_rich.runtime.shutdown()
    except Exception as exc:  # noqa: BLE001 - teardown is best effort; the command's exit code must stand
        safe_console.echo(_("Warning: logging did not shut down cleanly, some log events may be lost: {error}").format(error=exc), err=True)


__all__ = [
    "CLICK_CONTEXT_SETTINGS",
    "TRACEBACK_SUMMARY_LIMIT",
    "TRACEBACK_VERBOSE_LIMIT",
    "CheckInvocation",
    "CheckOutcome",
    "CliContext",
    "CliDependencies",
    "ConfigDeployer",
    "ConfigLoader",
    "EmailSender",
    "ErrorCategory",
    "PreparedNotification",
    "RateLimitNotifier",
    "TracebackState",
    "UidChecker",
    "apply_traceback_preferences",
    "cli",
    "cli_check",
    "cli_config",
    "cli_config_deploy",
    "cli_fail",
    "cli_hello",
    "cli_info",
    "cli_main",
    "main",
    "production_dependencies",
    "restore_traceback_state",
    "snapshot_traceback_state",
]
