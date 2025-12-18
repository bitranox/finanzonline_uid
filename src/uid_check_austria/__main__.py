"""Module entry point ensuring SystemExit semantics match project standards.

Provide the ``python -m uid_check_austria`` path mandated by the
project's packaging guidelines. The wrapper delegates to
:func:`uid_check_austria.cli.main` so that module execution mirrors the
installed console script, including traceback handling and exit-code mapping.

Contents:
    * :func:`_open_cli_session` – wires ``cli_session`` with the agreed limits.
    * :func:`_command_to_run` / :func:`_command_name` – expose the command and label
      used by the module entry.
    * :func:`_module_main` – drives execution and returns the exit code.

System Role:
    Lives in the adapters layer. It bridges CPython's module execution entry point
    to the shared CLI helper while reusing the same ``cli_session`` orchestration
    documented in ``docs/systemdesign/module_reference.md``.
"""

from __future__ import annotations
import logging
from typing import Callable, ContextManager, Final

from lib_cli_exit_tools import cli_session
import lib_log_rich.runtime

import rich_click as click

from . import __init__conf__, cli

# Match the CLI defaults so truncation behaviour stays consistent across entry
# points regardless of whether users call the console script or ``python -m``.
#: Character budget for truncated tracebacks when running via module entry.
TRACEBACK_SUMMARY_LIMIT: Final[int] = cli.TRACEBACK_SUMMARY_LIMIT
#: Character budget for verbose tracebacks when running via module entry.
TRACEBACK_VERBOSE_LIMIT: Final[int] = cli.TRACEBACK_VERBOSE_LIMIT


CommandRunner = Callable[..., int]
logger = logging.getLogger(__name__)


def _open_cli_session() -> ContextManager[CommandRunner]:
    """Return the configured ``cli_session`` context manager.

    ``cli_session`` wires ``lib_cli_exit_tools`` with the tracing limits we
    want for module execution. Wrapping it keeps the configuration in a
    single place.

    Returns:
        Context manager that yields the callable responsible for invoking
        the Click command.
    """

    return cli_session(
        summary_limit=TRACEBACK_SUMMARY_LIMIT,
        verbose_limit=TRACEBACK_VERBOSE_LIMIT,
    )


def _command_to_run() -> click.Command:
    """Expose the click command that powers the module entry.

    Keeps the module entry explicit about which command is being executed
    while remaining easy to stub in tests.

    Returns:
        Reference to the root CLI command group.
    """

    return cli.cli


def _command_name() -> str:
    """Return the shell-friendly name announced by the session.

    ``lib_cli_exit_tools`` uses this value when presenting help and error
    messages; we centralise the derivation so tests can assert against it.

    Returns:
        Name of the console script as published through entry points.
    """

    return __init__conf__.shell_command


def _module_main() -> int:
    """Execute the CLI entry point and return a normalised exit code.

    Implements ``python -m uid_check_austria`` by delegating to the
    shared CLI composition while respecting the configured traceback
    budgets.

    Returns:
        Exit code reported by the CLI run.

    Side Effects:
        Logging initialization is deferred to cli() to support profile-specific
        configuration. Shuts down lib_log_rich runtime on exit only if it was
        initialized (e.g., --help exits before initialization).
    """
    try:
        with _open_cli_session() as run:
            return run(
                _command_to_run(),
                prog_name=_command_name(),
            )
    finally:
        if lib_log_rich.runtime.is_initialised():
            lib_log_rich.runtime.shutdown()


if __name__ == "__main__":
    raise SystemExit(_module_main())
