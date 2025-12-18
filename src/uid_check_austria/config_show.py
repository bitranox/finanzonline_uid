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
from typing import Any, cast

import click
from lib_layered_config import Config

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
        Writes formatted configuration to stdout via click.echo().
        Raises SystemExit(1) if requested section doesn't exist.

    Note:
        The human-readable format mimics TOML syntax for consistency with the
        configuration file format. JSON format provides machine-readable output
        suitable for parsing by other tools.

    Example:
        >>> from uid_check_austria.config import get_config
        >>> config = get_config()  # doctest: +SKIP
        >>> display_config(config)  # doctest: +SKIP
        [lib_log_rich]
          service = "uid_check_austria"
          environment = "prod"

        >>> display_config(config, format=OutputFormat.JSON)  # doctest: +SKIP
        {
          "lib_log_rich": {
            "service": "uid_check_austria",
            "environment": "prod"
          }
        }
    """

    # Output in requested format
    if format == OutputFormat.JSON:
        if section:
            # Show specific section as JSON
            section_data = config.get(section, default={})
            if section_data:
                click.echo(json.dumps({section: section_data}, indent=2))
            else:
                click.echo(f"Section '{section}' not found or empty", err=True)
                raise SystemExit(1)
        else:
            # Use lib_layered_config's built-in to_json method
            click.echo(config.to_json(indent=2))
    else:
        # Human-readable format using lib_layered_config's as_dict
        if section:
            # Show specific section
            section_data = config.get(section, default={})
            if section_data:
                click.echo(f"\n[{section}]")
                for key, value in section_data.items():
                    if isinstance(value, (list, dict)):
                        click.echo(f"  {key} = {json.dumps(value)}")
                    elif isinstance(value, str):
                        click.echo(f'  {key} = "{value}"')
                    else:
                        click.echo(f"  {key} = {value}")
            else:
                click.echo(f"Section '{section}' not found or empty", err=True)
                raise SystemExit(1)
        else:
            # Show all configuration
            data: dict[str, Any] = config.as_dict()
            for section_name in data:
                section_data: Any = data[section_name]
                click.echo(f"\n[{section_name}]")
                if isinstance(section_data, dict):
                    dict_data = cast(dict[str, Any], section_data)
                    for key, value in dict_data.items():
                        if isinstance(value, (list, dict)):
                            click.echo(f"  {key} = {json.dumps(value)}")
                        elif isinstance(value, str):
                            click.echo(f'  {key} = "{value}"')
                        else:
                            click.echo(f"  {key} = {value}")
                else:
                    click.echo(f"  {section_data}")


__all__ = [
    "display_config",
]
