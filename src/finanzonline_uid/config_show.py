"""Configuration display functionality for CLI config command.

Provides the business logic for displaying merged configuration from all
sources in human-readable or JSON format. Keeps CLI layer thin by handling
all formatting and display logic here.

Contents:
    * :func:`display_config` – displays configuration in requested format

System Role:
    Lives in the behaviors layer. The CLI command delegates to this module for
    all configuration display logic, keeping presentation concerns separate from
    command-line argument parsing.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any, cast

from lib_layered_config import Config

from . import safe_console
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
        Raises SystemExit(1) if requested section doesn't exist.

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


def _require_section(config: Config, section: str) -> Any:
    """Return a section's data, exiting with status 1 when it is missing or empty.

    Args:
        config: Loaded layered configuration.
        section: Name of the section to look up.

    Returns:
        The section's data (never empty).

    Raises:
        SystemExit: With code 1 if the section does not exist or is empty.
    """
    section_data = config.get(section, default={})
    if not section_data:
        safe_console.echo(f"Section '{section}' not found or empty", err=True)
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
        section_data = _require_section(config, section)
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
        section_data = _require_section(config, section)
        safe_console.echo(f"\n[{section}]")
        _echo_entries(section_data.items())
    else:
        _display_all_human(config)


def _display_all_human(config: Config) -> None:
    """Write every configuration section in TOML-like form.

    Args:
        config: Loaded layered configuration.
    """
    data: dict[str, Any] = config.as_dict()
    for section_name, section_data in data.items():
        safe_console.echo(f"\n[{section_name}]")
        if isinstance(section_data, dict):
            dict_data = cast(dict[str, Any], section_data)
            _echo_entries(dict_data.items())
        else:
            safe_console.echo(f"  {section_data}")


def _echo_entries(entries: Iterable[tuple[str, Any]]) -> None:
    """Write one ``key = value`` line per entry, indented under its section.

    Args:
        entries: Key/value pairs of one section.
    """
    for key, value in entries:
        safe_console.echo(f"  {key} = {_format_value(value)}")


def _format_value(value: Any) -> str:
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
