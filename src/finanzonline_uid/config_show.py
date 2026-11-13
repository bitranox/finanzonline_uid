"""Configuration display functionality for CLI config command.

Provides the business logic for displaying merged configuration from all
sources in human-readable or JSON format. Keeps CLI layer thin by handling
all formatting and display logic here.

Contents:
    * :func:`display_config` - displays configuration in requested format

System Role:
    Lives in the behaviors layer. The CLI command delegates to this module for
    all configuration display logic, keeping presentation concerns separate from
    command-line argument parsing.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import cast

from lib_layered_config import Config

from . import safe_console
from .adapters.output import format_command_error_json
from .domain.errors import ErrorKind
from .enums import OutputFormat


def display_config(
    config: Config,
    *,
    format: OutputFormat = OutputFormat.HUMAN,
    section: str | None = None,
) -> None:
    """Display the provided configuration in the requested format.

    Users need visibility into the effective configuration loaded from
    defaults, app configs, host configs, user configs, .env files, and
    environment variables. Outputs the provided Config object in the
    requested format.

    Args:
        config: Already-loaded layered configuration object to display.
        format: Output format: OutputFormat.HUMAN for TOML-like display or
            OutputFormat.JSON for JSON. Defaults to OutputFormat.HUMAN.
        section: Optional section name to display only that section. When None,
            displays all configuration.

    Side Effects:
        Writes formatted configuration to stdout via safe_console.echo().
        Raises SystemExit(1) if requested section doesn't exist; with
        ``OutputFormat.JSON`` that failure also writes one JSON error record
        to stdout (the stderr line and the exit code are the same).

    Note:
        The human-readable format mimics TOML syntax for consistency with the
        configuration file format. JSON format provides machine-readable output
        suitable for parsing by other tools.

    Example:
        >>> from finanzonline_uid.config import get_config
        >>> config = get_config()  # doctest: +SKIP
        >>> display_config(config)  # doctest: +SKIP
        [lib_log_rich]
          service = "finanzonline_uid"
          environment = "prod"

        >>> display_config(config, format=OutputFormat.JSON)  # doctest: +SKIP
        {
          "lib_log_rich": {
            "service": "finanzonline_uid",
            "environment": "prod"
          }
        }
    """

    # Output in requested format
    if format == OutputFormat.JSON:
        _display_json(config, section)
    else:
        _display_human(config, section)


def _require_section(config: Config, section: str, *, format: OutputFormat) -> object:
    """Return a section's data, exiting with status 1 when it is missing or empty.

    The refusal line always goes to stderr. A JSON caller parses stdout, so
    with ``OutputFormat.JSON`` the refusal reaches it there as an error record
    as well; the human format leaves stdout empty, as it always has.

    Args:
        config: Loaded layered configuration.
        section: Name of the section to look up.
        format: Output format of this run.

    Returns:
        The section's data (never empty): a table, or a scalar set at top level.

    Raises:
        SystemExit: With code 1 if the section does not exist or is empty.
    """
    section_data: object = config.get(section, default={})
    if not section_data:
        message = f"Section '{section}' not found or empty"
        safe_console.echo(message, err=True)
        if format == OutputFormat.JSON:
            # A section the configuration does not hold is a bad --section
            # argument, the category check uses for its own argument refusals.
            safe_console.echo(format_command_error_json(ErrorKind.VALIDATION, message))
        raise SystemExit(1)
    return section_data


def _display_json(config: Config, section: str | None) -> None:
    """Write the whole configuration, or one section, as JSON.

    Args:
        config: Loaded layered configuration.
        section: Optional section to restrict the output to.
    """
    if section:
        # Show specific section as JSON
        section_data = _require_section(config, section, format=OutputFormat.JSON)
        safe_console.echo(json.dumps({section: section_data}, indent=2))
    else:
        # Use lib_layered_config's built-in to_json method
        safe_console.echo(config.to_json(indent=2))


def _display_human(config: Config, section: str | None) -> None:
    """Write the whole configuration, or one section, in TOML-like form.

    Args:
        config: Loaded layered configuration.
        section: Optional section to restrict the output to.
    """
    if section:
        # Show specific section
        section_data = _require_section(config, section, format=OutputFormat.HUMAN)
        safe_console.echo(f"\n[{section}]")
        _echo_section_body(section_data)
    else:
        _display_all_human(config)


def _display_all_human(config: Config) -> None:
    """Write every configuration section in TOML-like form.

    Args:
        config: Loaded layered configuration.
    """
    data: Mapping[str, object] = config.as_dict()
    for section_name, section_data in data.items():
        safe_console.echo(f"\n[{section_name}]")
        _echo_section_body(section_data)


def _echo_section_body(section_data: object) -> None:
    """Write a section's entries, or its value when it is a top-level scalar.

    Args:
        section_data: The section's data as the configuration holds it.
    """
    if isinstance(section_data, Mapping):
        _echo_entries(cast(Mapping[str, object], section_data).items())
    else:
        safe_console.echo(f"  {section_data}")


def _echo_entries(entries: Iterable[tuple[str, object]]) -> None:
    """Write one ``key = value`` line per entry, indented under its section.

    Args:
        entries: Key/value pairs of one section.
    """
    for key, value in entries:
        safe_console.echo(f"  {key} = {_format_value(value)}")


def _format_value(value: object) -> str:
    """Render a configuration value the way a TOML file would show it.

    Args:
        value: The value to render.

    Returns:
        JSON for lists and dicts, a double-quoted string for strings, and the
        plain value otherwise.

    Examples:
        >>> _format_value("prod")
        '"prod"'
        >>> _format_value([1, 2])
        '[1, 2]'
        >>> _format_value(3)
        '3'
    """
    if isinstance(value, (list, dict)):
        return json.dumps(value)
    if isinstance(value, str):
        return f'"{value}"'
    return f"{value}"


__all__ = [
    "display_config",
]
