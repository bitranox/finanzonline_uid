"""CLI adapter wiring the behavior helpers into a rich-click interface.

Expose a stable command-line surface so tooling, documentation, and packaging
automation can be exercised while the richer logging helpers are being built.

Contents:
    * :data:`CLICK_CONTEXT_SETTINGS` – shared Click settings.
    * :func:`apply_traceback_preferences` – synchronises traceback configuration.
    * :func:`snapshot_traceback_state` / :func:`restore_traceback_state` – state management.
    * :func:`cli` – root command group wiring global options.
    * :func:`main` – entry point for console scripts and ``python -m`` execution.

System Role:
    The CLI is the primary adapter for local development workflows; packaging
    targets register the console script defined in :mod:`finanzonline_uid.__init__conf__`.
"""

from __future__ import annotations

import logging
from typing import Any, Final, Optional, Sequence, Tuple

import rich_click as click
from lib_layered_config import Config

import lib_cli_exit_tools
import lib_log_rich.runtime
from click.core import ParameterSource

from . import __init__conf__
from .adapters.finanzonline import FinanzOnlineQueryClient, FinanzOnlineSessionClient
from .adapters.cache import UidResultCache
from .adapters.notification import EmailNotificationAdapter
from .adapters.ratelimit import RateLimitTracker
from .adapters.output import format_human, format_json
from .application.use_cases import CheckUidUseCase
from .behaviors import emit_greeting, noop_main, raise_intentional_failure
from .config import FinanzOnlineConfig, get_config, load_app_config, load_finanzonline_config
from .i18n import _, setup_locale
from .config_deploy import deploy_configuration
from .config_show import display_config
from .domain.errors import AuthenticationError, CheckErrorInfo, ConfigurationError, QueryError, SessionError, UidCheckError
from .domain.return_codes import CliExitCode, get_return_code_info
from .enums import DeployTarget, OutputFormat
from .logging_setup import init_logging
from .mail import EmailConfig, load_email_config_from_dict

#: Shared Click context flags so help output stays consistent across commands.
CLICK_CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}  # noqa: C408
#: Character budget used when printing truncated tracebacks.
TRACEBACK_SUMMARY_LIMIT: Final[int] = 500
#: Character budget used when verbose tracebacks are enabled.
TRACEBACK_VERBOSE_LIMIT: Final[int] = 10_000
TracebackState = Tuple[bool, bool]

logger = logging.getLogger(__name__)


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
        Tuple of ``(traceback_enabled, force_color)``.
    """
    return (
        bool(getattr(lib_cli_exit_tools.config, "traceback", False)),
        bool(getattr(lib_cli_exit_tools.config, "traceback_force_color", False)),
    )


def restore_traceback_state(state: TracebackState) -> None:
    """Reapply a previously captured traceback configuration.

    Args:
        state: Tuple returned by :func:`snapshot_traceback_state`.
    """
    lib_cli_exit_tools.config.traceback = bool(state[0])
    lib_cli_exit_tools.config.traceback_force_color = bool(state[1])


def _store_cli_context(
    ctx: click.Context,
    *,
    traceback: bool,
    config: Config,
    profile: Optional[str] = None,
) -> None:
    """Store CLI state in the Click context for subcommand access.

    Args:
        ctx: Click context associated with the current invocation.
        traceback: Whether verbose tracebacks were requested.
        config: Loaded layered configuration object for all subcommands.
        profile: Optional configuration profile name.
    """
    ctx.ensure_object(dict)
    ctx.obj["traceback"] = traceback
    ctx.obj["config"] = config
    ctx.obj["profile"] = profile


def _run_cli(argv: Optional[Sequence[str]]) -> int:
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
    except BaseException as exc:  # noqa: BLE001 - handled by shared printers
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
@click.version_option(
    version=__init__conf__.version,
    prog_name=__init__conf__.shell_command,
    message=f"{__init__conf__.shell_command} version {__init__conf__.version}",
)
@click.option(
    "--traceback/--no-traceback",
    is_flag=True,
    default=False,
    help=_("Show full Python traceback on errors"),
)
@click.option(
    "--profile",
    type=str,
    default=None,
    help=_("Load configuration from a named profile (e.g., 'production', 'test')"),
)
@click.pass_context
def cli(ctx: click.Context, traceback: bool, profile: Optional[str]) -> None:
    """Root command storing global flags and syncing shared traceback state.

    Loads configuration once with the profile and stores it in the Click context
    for all subcommands to access. Mirrors the traceback flag into
    ``lib_cli_exit_tools.config`` so downstream helpers observe the preference.

    Example:
        >>> from click.testing import CliRunner
        >>> runner = CliRunner()
        >>> result = runner.invoke(cli, ["hello"])
        >>> result.exit_code
        0
        >>> "Hello World" in result.output
        True
    """
    config = get_config(profile=profile)
    app_config = load_app_config(config)
    setup_locale(app_config.language)
    init_logging(config)
    _store_cli_context(ctx, traceback=traceback, config=config, profile=profile)
    apply_traceback_preferences(traceback)

    if ctx.invoked_subcommand is None:
        # No subcommand: show help unless --traceback was explicitly passed
        source = ctx.get_parameter_source("traceback")
        if source not in (ParameterSource.DEFAULT, None):
            cli_main()
        else:
            click.echo(ctx.get_help())


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
@click.option(
    "--format",
    type=click.Choice([f.value for f in OutputFormat], case_sensitive=False),
    default=OutputFormat.HUMAN.value,
    help=_("Output format (human-readable or JSON)"),
)
@click.option(
    "--section",
    type=str,
    default=None,
    help=_("Show only a specific configuration section (e.g., 'lib_log_rich')"),
)
@click.option(
    "--profile",
    type=str,
    default=None,
    help=_("Override profile from root command (e.g., 'production', 'test')"),
)
@click.pass_context
def cli_config(ctx: click.Context, format: str, section: Optional[str], profile: Optional[str]) -> None:
    """Display the current merged configuration from all sources.

    Shows configuration loaded from defaults, application/user config files,
    .env files, and environment variables.

    Precedence: defaults -> app -> host -> user -> dotenv -> env
    """
    # Use config from context; reload if profile override specified
    if profile:
        config = get_config(profile=profile)
        effective_profile = profile
    else:
        config = ctx.obj["config"]
        effective_profile = ctx.obj.get("profile")

    output_format = OutputFormat(format.lower())
    extra = {"command": "config", "format": output_format.value, "profile": effective_profile}
    with lib_log_rich.runtime.bind(job_id="cli-config", extra=extra):
        logger.info("Displaying configuration", extra={"format": output_format.value, "section": section, "profile": effective_profile})
        display_config(config, format=output_format, section=section)


def _display_deploy_result(deployed_paths: list[Any], effective_profile: str | None) -> None:
    """Display deployment result to user."""
    if deployed_paths:
        profile_msg = f" ({_('profile')}: {effective_profile})" if effective_profile else ""
        click.echo(f"\n{_('Configuration deployed successfully')}{profile_msg}:")
        for path in deployed_paths:
            click.echo(f"  ✓ {path}")
    else:
        click.echo(f"\n{_('No files were created (all target files already exist).')}")
        click.echo(_("Use --force to overwrite existing configuration files."))


def _handle_deploy_error(exc: Exception) -> None:
    """Handle deployment errors with appropriate logging and messages."""
    if isinstance(exc, PermissionError):
        logger.error("Permission denied when deploying configuration", extra={"error": str(exc)})
        click.echo(f"\n{_('Error')}: {_('Permission denied.')} {exc}", err=True)
        click.echo(_("Hint: System-wide deployment (--target app/host) may require sudo."), err=True)
    else:
        logger.error("Failed to deploy configuration", extra={"error": str(exc), "error_type": type(exc).__name__})
        click.echo(f"\n{_('Error')}: {_('Failed to deploy configuration:')} {exc}", err=True)
    raise SystemExit(1)


@cli.command("config-deploy", context_settings=CLICK_CONTEXT_SETTINGS)
@click.option(
    "--target",
    "targets",
    type=click.Choice([t.value for t in DeployTarget], case_sensitive=False),
    multiple=True,
    required=True,
    help=_("Target configuration layer(s) to deploy to (can specify multiple)"),
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help=_("Overwrite existing configuration files"),
)
@click.option(
    "--profile",
    type=str,
    default=None,
    help=_("Override profile from root command (e.g., 'production', 'test')"),
)
@click.pass_context
def cli_config_deploy(ctx: click.Context, targets: tuple[str, ...], force: bool, profile: Optional[str]) -> None:
    r"""Deploy default configuration to system or user directories.

    Creates configuration files in platform-specific locations:

    \b
    - app:  System-wide application config (requires privileges)
    - host: System-wide host config (requires privileges)
    - user: User-specific config (~/.config on Linux)

    By default, existing files are not overwritten. Use --force to overwrite.
    """
    effective_profile = profile if profile else ctx.obj.get("profile")
    deploy_targets = tuple(DeployTarget(t.lower()) for t in targets)
    target_values = tuple(t.value for t in deploy_targets)
    extra = {"command": "config-deploy", "targets": target_values, "force": force, "profile": effective_profile}

    with lib_log_rich.runtime.bind(job_id="cli-config-deploy", extra=extra):
        logger.info("Deploying configuration", extra={"targets": target_values, "force": force, "profile": effective_profile})

        try:
            deployed_paths = deploy_configuration(targets=deploy_targets, force=force, profile=effective_profile)
            _display_deploy_result(deployed_paths, effective_profile)
        except Exception as exc:
            _handle_deploy_error(exc)


# =============================================================================
# UID Check Command
# =============================================================================


def _get_uid_check_error_info(exc: UidCheckError) -> CheckErrorInfo:
    """Get CheckErrorInfo for UidCheckError subclasses."""
    error_type_map: dict[type[UidCheckError], tuple[str, CliExitCode]] = {
        ConfigurationError: ("Configuration Error", CliExitCode.CONFIG_ERROR),
        AuthenticationError: ("Authentication Error", CliExitCode.AUTH_ERROR),
        SessionError: ("Session Error", CliExitCode.QUERY_ERROR),
        QueryError: ("Query Error", CliExitCode.QUERY_ERROR),
    }
    exc_type = type(exc)
    error_type, exit_code = error_type_map.get(exc_type, ("UID Check Error", CliExitCode.QUERY_ERROR))
    return CheckErrorInfo(
        error_type=error_type,
        message=exc.message,
        exit_code=exit_code,
        return_code=getattr(exc, "return_code", None),
        retryable=getattr(exc, "retryable", False),
        diagnostics=getattr(exc, "diagnostics", None),
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
            error_type="Validation Error",
            message=str(exc),
            exit_code=CliExitCode.CONFIG_ERROR,
        )
    return CheckErrorInfo(
        error_type="Unexpected Error",
        message=str(exc),
        exit_code=CliExitCode.QUERY_ERROR,
    )


def _resolve_uid_input(uid: str | None, interactive: bool) -> str:
    """Resolve UID from argument or interactive prompt.

    Args:
        uid: UID argument from CLI (may be None).
        interactive: Whether to prompt interactively.

    Returns:
        The resolved UID string.

    Raises:
        SystemExit: If UID is required but not provided.
    """
    if interactive:
        return click.prompt(_("Enter EU VAT ID to verify"), type=str)

    if uid is None:
        click.echo(_("Error: UID argument is required (or use --interactive)"), err=True)
        raise SystemExit(CliExitCode.CONFIG_ERROR)

    return uid


def _output_check_result(result: Any, output_format: str) -> None:
    """Output the check result in the requested format.

    Args:
        result: UidCheckResult to output.
        output_format: Format string ("json" or "human").
    """
    if OutputFormat(output_format.lower()) == OutputFormat.JSON:
        click.echo(format_json(result))
    else:
        click.echo(format_human(result))


def _handle_check_error(
    error_info: CheckErrorInfo,
    *,
    send_notification: bool,
    config: Config,
    fo_config: FinanzOnlineConfig | None,
    uid: str,
    recipients: list[str],
) -> None:
    """Handle check command errors with output and notification.

    Args:
        error_info: Consolidated error information.
        send_notification: Whether to send email notification.
        config: Application configuration.
        fo_config: FinanzOnline configuration (may be None).
        uid: The UID being checked.
        recipients: Email recipients.

    Raises:
        SystemExit: Always raises with the specified exit code.
    """
    click.echo(f"\n{error_info.error_type}: {error_info.message}", err=True)

    if error_info.return_code is not None:
        info = get_return_code_info(error_info.return_code)
        click.echo(f"  {_('Return code:')} {error_info.return_code} ({info.meaning})", err=True)

    if error_info.retryable:
        click.echo(f"  {_('This error may be temporary. Try again later.')}", err=True)

    if send_notification:
        _send_error_notification(
            config=config,
            fo_config=fo_config,
            uid=uid,
            error_info=error_info,
            recipients=recipients,
        )

    raise SystemExit(error_info.exit_code)


@cli.command("check", context_settings=CLICK_CONTEXT_SETTINGS)
@click.argument("uid", required=False)
@click.option(
    "--interactive",
    "-i",
    is_flag=True,
    default=False,
    help=_("Interactive mode: prompt for UID to check"),
)
@click.option(
    "--no-email",
    is_flag=True,
    default=False,
    help=_("Disable email notification (default: email enabled)"),
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["human", "json"], case_sensitive=False),
    default="human",
    help=_("Output format (default: human)"),
)
@click.option(
    "--recipient",
    "recipients",
    multiple=True,
    help=_("Email recipient (can specify multiple, uses config default if not specified)"),
)
@click.pass_context
def cli_check(
    ctx: click.Context,
    uid: str | None,
    interactive: bool,
    no_email: bool,
    output_format: str,
    recipients: tuple[str, ...],
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
    """
    resolved_uid = _resolve_uid_input(uid, interactive)
    config: Config = ctx.obj["config"]
    recipients_list = list(recipients)
    fo_config: FinanzOnlineConfig | None = None

    extra = {"command": "check", "uid": resolved_uid, "no_email": no_email, "format": output_format}

    with lib_log_rich.runtime.bind(job_id="cli-check", extra=extra):
        try:
            fo_config = load_finanzonline_config(config)
            logger.info("FinanzOnline configuration loaded", extra={"uid_tn": fo_config.uid_tn})

            result = _execute_uid_check(fo_config, resolved_uid, config=config, recipients=recipients_list)
            _output_check_result(result, output_format)

            if not no_email:
                _send_check_notification(config=config, fo_config=fo_config, result=result, recipients=recipients_list)

            raise SystemExit(CliExitCode.UID_VALID if result.is_valid else CliExitCode.UID_INVALID)

        except (ConfigurationError, AuthenticationError, SessionError, QueryError, ValueError, UidCheckError) as exc:
            error_info = _get_error_info(exc)
            logger.error(error_info.error_type, extra={"error": str(exc)})
            if isinstance(exc, ConfigurationError):
                _show_config_help(exc.message)
            _handle_check_error(
                error_info,
                send_notification=not no_email,
                config=config,
                fo_config=fo_config,
                uid=resolved_uid,
                recipients=recipients_list,
            )


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


def _log_notification_result(success: bool, recipients: list[str], notification_type: str) -> None:
    """Log the result of a notification attempt."""
    if success:
        logger.info("%s email sent", notification_type, extra={"recipients": recipients})
    else:
        logger.warning("%s email failed", notification_type)


def _create_rate_limit_notifier(
    config: Config,
    fo_config: FinanzOnlineConfig,
    recipients: list[str],
) -> Any:
    """Create a rate limit notification callback.

    Args:
        config: Application configuration with email settings.
        fo_config: FinanzOnline configuration with default recipients.
        recipients: Explicit recipients list.

    Returns:
        Callable that sends rate limit warning email, or None if not configured.
    """
    from .adapters.ratelimit import RateLimitStatus

    def notifier(status: RateLimitStatus) -> None:
        """Send rate limit warning email (non-fatal on failure)."""
        try:
            prepared = _prepare_notification(config, fo_config, recipients, "Rate limit warning")
            if not prepared:
                return
            adapter, final_recipients = prepared
            success = adapter.send_rate_limit_warning(status, final_recipients)
            _log_notification_result(success, final_recipients, "Rate limit warning")
        except Exception as e:
            logger.warning("Rate limit notification error (non-fatal): %s", e)

    return notifier


def _execute_uid_check(
    fo_config: FinanzOnlineConfig,
    uid: str,
    config: Config | None = None,
    recipients: list[str] | None = None,
) -> Any:
    """Execute UID check via use case.

    Args:
        fo_config: FinanzOnline configuration with credentials.
        uid: Target UID to verify.
        config: Application configuration (for rate limit notifier).
        recipients: Email recipients (for rate limit notifier).

    Returns:
        UidCheckResult from the use case.
    """
    session_client = FinanzOnlineSessionClient(timeout=fo_config.session_timeout)
    query_client = FinanzOnlineQueryClient(timeout=fo_config.query_timeout)
    cache = _create_cache(fo_config)
    rate_limiter = _create_rate_limiter(fo_config)

    # Create rate limit notifier if config is available
    rate_limit_notifier = None
    if config is not None and rate_limiter is not None:
        rate_limit_notifier = _create_rate_limit_notifier(config, fo_config, recipients or [])

    use_case = CheckUidUseCase(
        session_client,
        query_client,
        cache=cache,
        rate_limiter=rate_limiter,
        rate_limit_notifier=rate_limit_notifier,
    )
    return use_case.execute(credentials=fo_config.credentials, uid_tn=fo_config.uid_tn, target_uid=uid)


def _show_config_help(error_message: str) -> None:
    """Display configuration help for FinanzOnline credentials.

    Args:
        error_message: The configuration error message.
    """
    click.echo(f"\n{_('Error')}: {error_message}", err=True)
    click.echo(f"\n{_('Configure FinanzOnline credentials in your config file or via environment variables:')}", err=True)
    click.echo(f"  FINANZONLINE_UID___FINANZONLINE__TID=... ({_('8-12 alphanumeric')})", err=True)
    click.echo(f"  FINANZONLINE_UID___FINANZONLINE__BENID=... ({_('5-12 chars')})", err=True)
    click.echo(f"  FINANZONLINE_UID___FINANZONLINE__PIN=... ({_('5-128 chars')})", err=True)
    click.echo("  FINANZONLINE_UID___FINANZONLINE__UID_TN=ATU...", err=True)
    click.echo(f"  FINANZONLINE_UID___FINANZONLINE__HERSTELLERID=... ({_('10-24 alphanumeric')})", err=True)


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
    config: Config,
    fo_config: FinanzOnlineConfig | None,
    recipients: list[str],
    notification_type: str,
) -> tuple[EmailNotificationAdapter, list[str]] | None:
    """Prepare email notification adapter and recipients.

    Args:
        config: Application configuration.
        fo_config: FinanzOnline configuration (may be None).
        recipients: Explicit recipients list.
        notification_type: Type for logging (e.g., "Email", "Error").

    Returns:
        Tuple of (adapter, final_recipients) if ready, None if skipped.
    """
    email_config = load_email_config_from_dict(config.as_dict())

    if not email_config.smtp_hosts:
        logger.warning("%s notification skipped: no SMTP hosts configured", notification_type)
        return None

    final_recipients = _resolve_notification_recipients(recipients, email_config, fo_config)
    if not final_recipients:
        logger.warning("%s notification skipped: no recipients configured", notification_type)
        return None

    return EmailNotificationAdapter(email_config), final_recipients


def _send_check_notification(
    config: Config,
    fo_config: FinanzOnlineConfig,
    result: Any,
    recipients: list[str],
) -> None:
    """Send email notification for check result (non-fatal on failure)."""
    try:
        prepared = _prepare_notification(config, fo_config, recipients, "Email")
        if not prepared:
            return

        adapter, final_recipients = prepared
        if adapter.send_result(result, final_recipients):
            logger.info("Email notification sent", extra={"recipients": final_recipients})
        else:
            logger.warning("Email notification failed")

    except Exception as e:
        logger.warning("Email notification error (non-fatal): %s", e)


def _send_error_notification(
    config: Config,
    fo_config: FinanzOnlineConfig | None,
    uid: str,
    error_info: CheckErrorInfo,
    recipients: list[str],
) -> None:
    """Send email notification for check error (non-fatal on failure)."""
    try:
        prepared = _prepare_notification(config, fo_config, recipients, "Error")
        if not prepared:
            return

        adapter, final_recipients = prepared
        success = adapter.send_error(
            error_type=error_info.error_type,
            error_message=error_info.message,
            uid=uid,
            recipients=final_recipients,
            return_code=error_info.return_code,
            retryable=error_info.retryable,
            diagnostics=error_info.diagnostics,
        )
        if success:
            logger.info("Error notification sent", extra={"recipients": final_recipients})
        else:
            logger.warning("Error notification failed")

    except Exception as e:
        logger.warning("Error notification error (non-fatal): %s", e)


def main(argv: Optional[Sequence[str]] = None, *, restore_traceback: bool = True) -> int:
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
            lib_log_rich.runtime.shutdown()
