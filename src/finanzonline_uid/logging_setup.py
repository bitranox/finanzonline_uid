"""Centralized logging initialization for all entry points.

Provides a single source of truth for lib_log_rich runtime configuration,
eliminating duplication between module entry (__main__.py) and console script
(cli.py) while ensuring initialization happens exactly once.

Contents:
    * :func:`init_logging` - idempotent logging initialization with layered config.
    * :func:`build_runtime_config` - constructs RuntimeConfig from layered sources.

System Role:
    Lives in the adapters/platform layer. All entry points (module execution,
    console scripts, tests) delegate to this module for logging setup, ensuring
    consistent runtime behavior across invocation paths.

Configuration:
    All logging settings are read via lib_layered_config from the [lib_log_rich]
    section. This provides a consistent configuration experience where all settings
    use the same naming convention:

    .env file format:
        LIB_LOG_RICH__CONSOLE_LEVEL=DEBUG
        LIB_LOG_RICH__PAYLOAD_LIMITS__MESSAGE_MAX_CHARS=8192

    Environment variable format (with app prefix):
        FINANZONLINE_UID___LIB_LOG_RICH__CONSOLE_LEVEL=DEBUG

    Note: lib_log_rich's native LOG_* variables are NOT used to avoid
    inconsistency with the lib_layered_config naming convention.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum

import lib_log_rich.runtime
from lib_layered_config import Config

from . import __init__conf__
from .config import read_config_section, text_setting
from .enums import ConfigSection


class _RuntimeName(str, Enum):
    """The two required RuntimeConfig names this module supplies a default for."""

    SERVICE = "service"
    ENVIRONMENT = "environment"

    @property
    def default(self) -> str:
        """The name used when the section does not set it."""
        return __init__conf__.name if self == _RuntimeName.SERVICE else "prod"


def _name_setting(section: Mapping[str, object], name: _RuntimeName) -> str | None:
    """Return a logging name setting as text, or None when its value is not text.

    lib_layered_config reads an unquoted all-digit value as an int, and RuntimeConfig accepts
    text only; the conversion is lossless, so the digits restore what the operator wrote.
    An absent setting gives the default.

    Examples:
        >>> _name_setting({"service": 4711}, _RuntimeName.SERVICE), _name_setting({}, _RuntimeName.ENVIRONMENT)
        ('4711', 'prod')
        >>> _name_setting({"service": True}, _RuntimeName.SERVICE) is None
        True
    """
    if name.value not in section:
        return name.default
    return text_setting(section[name.value])


def build_runtime_config(config: Config) -> lib_log_rich.runtime.RuntimeConfig:
    """Build RuntimeConfig from a Config object.

    Centralizes the mapping from lib_layered_config to lib_log_rich
    RuntimeConfig. Extracts the [lib_log_rich] section from the provided
    configuration and applies defaults for required parameters.

    Args:
        config: Already-loaded layered configuration object.

    Returns:
        Fully configured runtime settings ready for lib_log_rich.init().

    Note:
        Configuration is read from the [lib_log_rich] section. All parameters
        documented in defaultconfig.toml can be specified. Unspecified values
        use lib_log_rich's built-in defaults. The service and environment
        parameters default to package metadata when not configured.
    """
    section = read_config_section(config, ConfigSection.LIB_LOG_RICH)
    # The section is passed through key by key: RuntimeConfig is itself a Pydantic model and is
    # the boundary that validates every lib_log_rich setting, so this module only supplies the
    # two required names it has defaults for. A name that is not text keeps its raw value, so
    # RuntimeConfig refuses it with the operator's own value in the message.
    settings: dict[str, object] = dict(section)
    for name in _RuntimeName:
        text = _name_setting(section, name)
        if text is not None:
            settings[name.value] = text
    return lib_log_rich.runtime.RuntimeConfig.model_validate(settings)


def init_logging(config: Config) -> None:
    """Initialize lib_log_rich runtime with the provided configuration.

    All entry points need logging configured, but the runtime should only
    be initialized once regardless of how many times this function is called.
    Configuration is read exclusively from lib_layered_config, providing a
    consistent naming convention across all settings.

    Args:
        config: Already-loaded layered configuration object containing logging
            settings in the [lib_log_rich] section.

    Side Effects:
        May initialize the global lib_log_rich runtime on first invocation.
        Subsequent calls have no effect.

    Note:
        This function is safe to call multiple times. The first call
        initializes the runtime; subsequent calls check the initialization
        state and return immediately if already initialized.

        All logging configuration uses lib_layered_config naming:
        - .env: LIB_LOG_RICH__CONSOLE_LEVEL=DEBUG
        - env var: FINANZONLINE_UID___LIB_LOG_RICH__CONSOLE_LEVEL=DEBUG
    """
    if not lib_log_rich.runtime.is_initialised():
        runtime_config = build_runtime_config(config)
        lib_log_rich.runtime.init(runtime_config)
        lib_log_rich.runtime.attach_std_logging()


__all__ = [
    "build_runtime_config",
    "init_logging",
]
