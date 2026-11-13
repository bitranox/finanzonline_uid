"""Domain enums for configuration and output formatting.

Provides type-safe enumeration values for output formats, deployment targets,
and other fixed string values used throughout the application.

Contents:
    * :class:`OutputFormat` - Output format options for config display
    * :class:`DeployTarget` - Configuration deployment target layers
    * :class:`EmailFormat` - Email body format options
    * :class:`FileFormat` - File format for saved check results
    * :class:`Language` - Supported interface languages
    * :class:`NotificationKind` - Kind of notification email being sent
    * :class:`ConfigSection` - Top-level sections of the layered configuration

System Role:
    Acts as the single source of truth for fixed string values, eliminating
    magic strings and enabling type-safe comparisons throughout the codebase.
"""

from __future__ import annotations

from enum import Enum


class OutputFormat(str, Enum):
    """Output format options for configuration display.

    Defines valid output format choices for the config command.
    Inherits from str to allow direct string comparison and Click integration.

    Attributes:
        HUMAN: Human-readable TOML-like output format.
        JSON: Machine-readable JSON output format.

    Example:
        >>> OutputFormat.HUMAN == "human"
        True
        >>> OutputFormat.JSON == "json"
        True
    """

    HUMAN = "human"
    JSON = "json"


class DeployTarget(str, Enum):
    """Configuration deployment target layers.

    Defines valid target layers for configuration file deployment.
    Inherits from str to allow direct string comparison and Click integration.

    Attributes:
        APP: System-wide application configuration (requires privileges).
        HOST: System-wide host-specific configuration (requires privileges).
        USER: User-specific configuration (~/.config on Linux).

    Example:
        >>> DeployTarget.USER == "user"
        True
        >>> DeployTarget.APP == "app"
        True
    """

    APP = "app"
    HOST = "host"
    USER = "user"


class EmailFormat(str, Enum):
    """Email body format options for notifications.

    Defines which format(s) to include in notification emails.
    Inherits from str to allow direct string comparison and config parsing.

    Attributes:
        HTML: Send HTML body only (default).
        PLAIN: Send plain text body only.
        BOTH: Send both HTML and plain text (multipart/alternative).

    Example:
        >>> EmailFormat.HTML == "html"
        True
        >>> EmailFormat.PLAIN == "plain"
        True
    """

    HTML = "html"
    PLAIN = "plain"
    BOTH = "both"


class FileFormat(str, Enum):
    """File format for check results saved with ``--outputdir``.

    The value is also the file extension.

    Example:
        >>> FileFormat.TXT.value
        'txt'
    """

    JSON = "json"
    TXT = "txt"
    HTML = "html"


class Language(str, Enum):
    """Interface language; the value is the gettext locale code.

    Example:
        >>> Language("de") is Language.DE
        True
    """

    EN = "en"
    DE = "de"
    ES = "es"
    FR = "fr"
    RU = "ru"


class NotificationKind(str, Enum):
    """Kind of notification email, as named in log messages.

    Example:
        >>> NotificationKind.RATE_LIMIT_WARNING.value
        'Rate limit warning'
    """

    RESULT = "Email"
    ERROR = "Error"
    RATE_LIMIT_WARNING = "Rate limit warning"


class ConfigSection(str, Enum):
    """Top-level section of the layered configuration; the value is the section name.

    Example:
        >>> ConfigSection.LIB_LOG_RICH.value
        'lib_log_rich'
    """

    APP = "app"
    FINANZONLINE = "finanzonline"
    EMAIL = "email"
    LIB_LOG_RICH = "lib_log_rich"


__all__ = [
    "ConfigSection",
    "DeployTarget",
    "EmailFormat",
    "FileFormat",
    "Language",
    "NotificationKind",
    "OutputFormat",
]
