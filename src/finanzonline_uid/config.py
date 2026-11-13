"""Configuration management using lib_layered_config.

Provides a centralized configuration loader that merges defaults, application
configs, host configs, user configs, .env files, and environment variables
following a deterministic precedence order.

Contents:
    * :func:`get_config` - loads configuration with lib_layered_config
    * :func:`get_default_config_path` - returns path to bundled default config
    * :func:`read_config_section` - one raw section, ready for a section model
    * :func:`text_setting` - a text setting's value, digits restored from an int
    * :func:`empty_text_list` - typed empty-list factory for list-of-text fields
    * :func:`load_app_config` - loads the general application settings
    * :func:`load_finanzonline_config` - loads FinanzOnline credentials and settings

    Configuration identifiers (vendor, app, slug) are imported from
    :mod:`finanzonline_uid.__init__conf__` as LAYEREDCONF_* constants.

System Role:
    Acts as the configuration adapter layer, bridging lib_layered_config with the
    application's runtime needs while keeping domain logic decoupled from
    configuration mechanics. Each section is parsed once into a Pydantic section
    model (:class:`AppSection`, :class:`FinanzOnlineSection`); the rest of the
    application only sees the typed results.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, cast

from lib_layered_config import Config, read_config
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError, field_validator
from pydantic_core import PydanticCustomError, PydanticUseDefault

from . import __init__conf__
from .domain.errors import ConfigurationError
from .domain.models import FinanzOnlineCredentials
from .enums import ConfigSection, EmailFormat, FileFormat, Language
from .i18n import DEFAULT_LANGUAGE

# =============================================================================
# Configuration Parsing Helpers (shared with mail.py and logging_setup.py)
# =============================================================================


def number_or_default(raw: object) -> float:
    """Return a numeric config value as float, else make the field use its default.

    Meant for a ``mode="before"`` field validator: raising
    :class:`pydantic_core.PydanticUseDefault` keeps each field's own default in
    one place (the field declaration) instead of repeating it at every call.

    Args:
        raw: Raw config value.

    Returns:
        The value as float when it is an int or a float.

    Raises:
        PydanticUseDefault: For any other value, so the field default applies.

    Examples:
        >>> number_or_default(45)
        45.0
    """
    if isinstance(raw, (int, float)):
        return float(raw)
    raise PydanticUseDefault


def parse_string_list(raw: object) -> list[str]:
    """Parse a string list from config, handling JSON strings from .env files.

    Args:
        raw: Raw config value (list or JSON string).

    Returns:
        List of strings, empty list if parsing fails.

    Examples:
        >>> parse_string_list('["a@example.com", ""]')
        ['a@example.com']
        >>> parse_string_list("not-a-list")
        []
    """
    if isinstance(raw, list):
        return [str(item) for item in cast(list[object], raw) if item]

    if isinstance(raw, str) and raw.startswith("["):
        try:
            parsed: object = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return [str(item) for item in cast(list[object], parsed) if item]

    return []


def text_setting(raw: object) -> str | None:
    """Return a text setting's value as text, or None when it is not text.

    lib_layered_config reads an unquoted all-digit value as an int whenever the
    number reads back as the same text, so ``str()`` restores exactly what was
    written. A bool stays "not text" so ``true`` never becomes the text ``True``.

    Args:
        raw: Raw config value.

    Returns:
        The text, the digits of an int, or None for any other type.

    Examples:
        >>> text_setting("dir"), text_setting(2024), text_setting(True)
        ('dir', '2024', None)
    """
    if isinstance(raw, str):
        return raw
    if isinstance(raw, int) and not isinstance(raw, bool):
        return str(raw)
    return None


def _get_cache_dir() -> Path:
    """Get platform-specific cache directory.

    Returns:
        Path to cache directory:
        - Linux: ~/.cache/finanzonline-uid/
        - macOS: ~/Library/Caches/finanzonline-uid/
        - Windows: %LOCALAPPDATA%/finanzonline-uid/
    """
    home = Path.home()

    if sys.platform == "darwin":
        return home / "Library" / "Caches" / "finanzonline-uid"
    if sys.platform == "win32":
        local_app_data = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        return local_app_data / "finanzonline-uid"
    # Linux and other POSIX systems - use XDG cache directory
    xdg_cache = Path(os.environ.get("XDG_CACHE_HOME", home / ".cache"))
    return xdg_cache / "finanzonline-uid"


def _get_default_cache_path() -> Path:
    """Get platform-specific default cache file path.

    Returns:
        Path to default cache file location:
        - Linux: ~/.cache/finanzonline-uid/uid_cache.json
        - macOS: ~/Library/Caches/finanzonline-uid/uid_cache.json
        - Windows: %LOCALAPPDATA%/finanzonline-uid/uid_cache.json
    """
    return _get_cache_dir() / "uid_cache.json"


def _get_default_ratelimit_path() -> Path:
    """Get platform-specific default rate limit file path.

    Returns:
        Path to default rate limit file location:
        - Linux: ~/.cache/finanzonline-uid/rate_limits.json
        - macOS: ~/Library/Caches/finanzonline-uid/rate_limits.json
        - Windows: %LOCALAPPDATA%/finanzonline-uid/rate_limits.json
    """
    return _get_cache_dir() / "rate_limits.json"


def _normalize_path(path_str: str) -> Path:
    """Normalize path string to handle both Windows and Linux-style paths.

    Allows using forward slashes in config files even for Windows UNC paths.
    For example, `//server/share/path` is converted to `\\\\server\\share\\path`
    on Windows.

    Args:
        path_str: Path string (may use forward or back slashes).

    Returns:
        Normalized Path object appropriate for the current platform.

    Example:
        >>> # On Windows, Linux-style UNC paths are converted
        >>> _normalize_path("//server/share/dir")  # doctest: +SKIP
        WindowsPath('//server/share/dir')
    """
    path_str = path_str.strip()

    # On Windows, convert Linux-style UNC paths (//server/share) to Windows-style
    if sys.platform == "win32" and path_str.startswith("//"):
        path_str = path_str.replace("/", "\\")

    return Path(path_str).expanduser()


def empty_text_list() -> list[str]:
    """Return a new empty list of text for a ``default_factory``.

    A bare ``list`` factory infers ``list[Unknown]`` under pyright strict.

    Returns:
        An empty ``list[str]``.

    Examples:
        >>> empty_text_list()
        []
    """
    return []


def read_config_section(config: Config, section: ConfigSection) -> Mapping[str, object]:
    """Return one top-level configuration section as raw data for a section model.

    A section that is missing, or that is not a table (a scalar set through an
    environment variable, say), reads as empty so every setting in it falls back
    to its default rather than failing the whole command.

    Args:
        config: Loaded layered configuration.
        section: The section to read.

    Returns:
        The section's raw key/value pairs, empty when absent or not a table.

    Examples:
        >>> read_config_section(Config({"email": "x"}, {}), ConfigSection.EMAIL)
        {}
    """
    raw: object = config.get(section.value, default=None)
    if isinstance(raw, Mapping):
        return cast(Mapping[str, object], raw)
    return {}


def get_default_config_path() -> Path:
    """Return the path to the bundled default configuration file.

    The default configuration ships with the package and needs to be
    locatable at runtime regardless of how the package is installed.
    Uses __file__ to locate the defaultconfig.toml file relative to this
    module.

    Returns:
        Absolute path to defaultconfig.toml.

    Example:
        >>> path = get_default_config_path()
        >>> path.name
        'defaultconfig.toml'
        >>> path.exists()
        True
    """
    return Path(__file__).parent / "defaultconfig.toml"


# Not cached: the result also depends on the environment variables and, through
# .env discovery, on the current directory, neither of which a cache key on
# ``profile``/``start_dir`` sees. A CLI run loads the configuration once, so a
# cache would only return stale results to library callers and save nothing.
def get_config(*, profile: str | None = None, start_dir: str | None = None) -> Config:
    """Load layered configuration with application defaults.

    Centralizes configuration loading so all entry points use the same
    precedence rules and default values without duplicating the discovery
    logic.

    Loads configuration from multiple sources in precedence order:
    defaults -> app -> host -> user -> dotenv -> env

    The vendor, app, and slug identifiers determine platform-specific paths:
    - Linux: Uses XDG directories with slug
    - macOS: Uses Library/Application Support with vendor/app
    - Windows: Uses ProgramData/AppData with vendor/app

    When a profile is specified, configuration is loaded from profile-specific
    subdirectories (e.g., ~/.config/slug/profile/<name>/config.toml).

    Args:
        profile: Optional profile name for environment isolation. When specified,
            a ``profile/<name>/`` subdirectory is inserted into all configuration
            paths. Valid names: alphanumeric, hyphens, underscores. Examples:
            'test', 'production', 'staging-v2'. Defaults to None (no profile).
        start_dir: Optional directory that seeds .env discovery. Defaults to current
            working directory when None.

    Returns:
        Immutable configuration object with provenance tracking.

    Note:
        Every call reads all layers again, so a changed environment variable,
        current directory or configuration file is seen by the next call.

    Example:
        >>> config = get_config()
        >>> isinstance(config.as_dict(), dict)
        True
        >>> config.get("nonexistent", default="fallback")
        'fallback'

        >>> # Load production profile
        >>> prod_config = get_config(profile="production")  # doctest: +SKIP

    See Also:
        lib_layered_config.read_config: Underlying configuration loader.
    """
    return read_config(
        vendor=__init__conf__.LAYEREDCONF_VENDOR,
        app=__init__conf__.LAYEREDCONF_APP,
        slug=__init__conf__.LAYEREDCONF_SLUG,
        profile=profile,
        default_file=get_default_config_path(),
        start_dir=start_dir,
    )


class AppSection(BaseModel):
    """The ``[app]`` section as read from the layered configuration.

    Attributes:
        language: Interface language. An empty value means the default; an
            unsupported one falls back to the default, so a typo never stops the
            command. It falls back silently: the CLI reads this section before
            logging is initialised, and a log record emitted then would go out
            unformatted through ``logging.lastResort``.

    Examples:
        >>> AppSection.model_validate({"language": " DE "}).language
        <Language.DE: 'de'>
        >>> AppSection.model_validate({}).language
        <Language.EN: 'en'>
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    language: Language = DEFAULT_LANGUAGE

    @field_validator("language", mode="before")
    @classmethod
    def _supported_language(cls, raw: object) -> Language:
        if isinstance(raw, Language):
            return raw
        if not raw:
            return DEFAULT_LANGUAGE
        try:
            return Language(str(raw).lower().strip())
        except ValueError:
            return DEFAULT_LANGUAGE


@dataclass(frozen=True, slots=True)
class AppConfig:
    """General application configuration.

    Attributes:
        language: Language for user-facing messages.
    """

    language: Language = DEFAULT_LANGUAGE


def load_app_config(config: Config) -> AppConfig:
    """Load application configuration from layered config.

    Args:
        config: Loaded layered configuration object.

    Returns:
        AppConfig with language setting.

    Example:
        >>> load_app_config(Config({"app": {"language": "fr"}}, {})).language
        <Language.FR: 'fr'>
    """
    section = AppSection.model_validate(dict(read_config_section(config, ConfigSection.APP)))
    return AppConfig(language=section.language)


def _credential_text(raw: object) -> str:
    """Return a credential value as text, empty when it is falsy (reported as missing)."""
    return str(raw) if raw else ""


def path_setting(raw: object) -> Path | None:
    """Return a path setting as a Path, or None when it names no path.

    Text that is empty or only whitespace names no path: it would otherwise
    normalise to ``Path(".")``, the current directory. Surrounding whitespace
    of a real path is stripped by :func:`_normalize_path`, the same for every
    path setting, because a stray space around a path in a TOML or ``.env``
    file is far likelier than a directory whose name starts or ends with one.
    ``check --outputdir`` reads its value through this function too, so the
    option and ``finanzonline.output_dir`` cannot disagree about a blank value.

    Examples:
        >>> path_setting("") is None, path_setting(" \t ") is None, str(path_setting(4711))
        (True, True, '4711')
    """
    if isinstance(raw, Path):
        return raw
    text = text_setting(raw)
    return _normalize_path(text) if text and text.strip() else None


#: Email body format used when ``[finanzonline].email_format`` names none.
_DEFAULT_EMAIL_FORMAT = EmailFormat.HTML


def _email_format_or_default(raw: object) -> EmailFormat:
    """Return the email format a setting names, else make the field use its default.

    Case and surrounding whitespace are ignored. Anything else (an unknown
    name, a number, a list) raises :class:`pydantic_core.PydanticUseDefault`,
    so the field falls back to HTML instead of refusing the whole section.

    Examples:
        >>> _email_format_or_default(" Plain ")
        <EmailFormat.PLAIN: 'plain'>
    """
    if isinstance(raw, EmailFormat):
        return raw
    if isinstance(raw, str):
        try:
            return EmailFormat(raw.lower().strip())
        except ValueError:
            raise PydanticUseDefault from None
    raise PydanticUseDefault


#: The ``email_format`` setting as every section model reads it. One annotated
#: type, so the full section and the error-mail fallback cannot parse it apart.
_EmailFormatSetting = Annotated[EmailFormat, BeforeValidator(_email_format_or_default)]


class _EmailFormatSection(BaseModel):
    """The one ``[finanzonline]`` key the error email needs, read on its own.

    Every other key is ignored, so a section that :class:`FinanzOnlineSection`
    refuses (or whose credentials are missing) still yields its email format.

    Examples:
        >>> _EmailFormatSection.model_validate({"email_format": "pdf", "output_dir": True}).email_format
        <EmailFormat.HTML: 'html'>
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    email_format: _EmailFormatSetting = _DEFAULT_EMAIL_FORMAT


def load_email_format(config: Config) -> EmailFormat:
    """Read ``[finanzonline].email_format`` on its own, falling back to HTML.

    The error email of a run whose ``[finanzonline]`` section could not be
    loaded (missing credentials, say) has no :class:`FinanzOnlineConfig` to
    take the format from; reading the one key here keeps that email in the
    format the user configured. It never raises: an unusable value means the
    default, as it does for :class:`FinanzOnlineSection`, because both read the
    key through the same annotated type.

    Args:
        config: Loaded layered configuration.

    Returns:
        The configured email body format, HTML when none is configured.

    Examples:
        >>> load_email_format(Config({"finanzonline": {"email_format": "BOTH"}}, {}))
        <EmailFormat.BOTH: 'both'>
        >>> load_email_format(Config({"finanzonline": {"email_format": 1}}, {}))
        <EmailFormat.HTML: 'html'>
        >>> load_email_format(Config({}, {}))
        <EmailFormat.HTML: 'html'>
    """
    section = _EmailFormatSection.model_validate(dict(read_config_section(config, ConfigSection.FINANZONLINE)))
    return section.email_format


class FinanzOnlineSection(BaseModel):
    """The ``[finanzonline]`` section as read from the layered configuration.

    Every validator but one coerces or falls back to the field default. The
    exception is ``output_dir``: a value that names no path (``true``, a list)
    is refused, because falling back would quietly stop writing result files.
    :func:`load_finanzonline_config` turns that refusal into a
    :class:`ConfigurationError` and raises the other refusals (missing
    credentials, invalid credentials, an own UID without ``ATU``) in the order
    and with the text callers already depend on.

    Examples:
        >>> section = FinanzOnlineSection.model_validate({"tid": 123456789, "session_timeout": "slow", "output_format": "TXT"})
        >>> section.tid, section.session_timeout, section.output_format
        ('123456789', 30.0, <FileFormat.TXT: 'txt'>)
        >>> section.missing_required()
        ['finanzonline.benid', 'finanzonline.pin', 'finanzonline.uid_tn', 'finanzonline.herstellerid']
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    tid: str = ""
    benid: str = ""
    # repr=False keeps the PIN out of any log line or traceback that renders the section.
    pin: str = Field(default="", repr=False)
    uid_tn: str = ""
    herstellerid: str = ""
    session_timeout: float = 30.0
    query_timeout: float = 30.0
    default_recipients: list[str] = Field(default_factory=empty_text_list)
    email_format: _EmailFormatSetting = _DEFAULT_EMAIL_FORMAT
    cache_results_hours: float = 48.0
    cache_file: Path = Field(default_factory=_get_default_cache_path)
    ratelimit_queries: int = 50
    ratelimit_hours: float = 24.0
    ratelimit_file: Path = Field(default_factory=_get_default_ratelimit_path)
    output_dir: Path | None = None
    output_format: FileFormat = FileFormat.HTML

    @field_validator("tid", "benid", "pin", "uid_tn", "herstellerid", mode="before")
    @classmethod
    def _credential(cls, raw: object) -> str:
        return _credential_text(raw)

    @field_validator("session_timeout", "query_timeout", "cache_results_hours", "ratelimit_hours", mode="before")
    @classmethod
    def _number(cls, raw: object) -> float:
        return number_or_default(raw)

    @field_validator("ratelimit_queries", mode="before")
    @classmethod
    def _count(cls, raw: object) -> int:
        return int(number_or_default(raw))

    @field_validator("default_recipients", mode="before")
    @classmethod
    def _recipients(cls, raw: object) -> list[str]:
        return parse_string_list(raw)

    @field_validator("cache_file", "ratelimit_file", mode="before")
    @classmethod
    def _state_file(cls, raw: object) -> Path:
        # A blank path means "not configured", so the platform default applies.
        path = path_setting(raw)
        if path is None:
            raise PydanticUseDefault
        return path

    @field_validator("output_dir", mode="before")
    @classmethod
    def _output_dir(cls, raw: object) -> Path | None:
        if raw is None or isinstance(raw, Path):
            return raw
        if not raw:
            # Every falsy value ("", false, 0, an empty list or table) meant "off" in
            # the release; 0 must not turn into a directory named "0".
            return None
        if text_setting(raw) is None:
            # Refused rather than defaulted: the default (None) switches result files off,
            # so a mistyped value would silently stop writing them.
            raise PydanticCustomError(
                "path_type",
                "must be a directory path given as text, got {type_name}",
                {"type_name": type(raw).__name__},
            )
        # Whitespace-only text is "off" like an empty value; it must not become Path(".").
        return path_setting(raw)

    @field_validator("output_format", mode="before")
    @classmethod
    def _output_format(cls, raw: object) -> FileFormat:
        if isinstance(raw, FileFormat):
            return raw
        try:
            return FileFormat(str(raw).lower())
        except ValueError:
            raise PydanticUseDefault from None

    def missing_required(self) -> list[str]:
        """Return the dotted names of the required settings that are empty, in report order."""
        required = (
            ("tid", self.tid),
            ("benid", self.benid),
            ("pin", self.pin),
            ("uid_tn", self.uid_tn),
            ("herstellerid", self.herstellerid),
        )
        return [f"finanzonline.{name}" for name, value in required if not value]


@dataclass(frozen=True, slots=True)
class FinanzOnlineConfig:
    """Configuration for FinanzOnline connection.

    Attributes:
        credentials: Authentication credentials (tid, benid, pin).
        uid_tn: Own Austrian UID (must start with ATU).
        session_timeout: Timeout for session operations in seconds.
        query_timeout: Timeout for query operations in seconds.
        default_recipients: Default email recipients for notifications.
        email_format: Email body format (html, text, or both).
        cache_results_hours: Hours to cache valid results (0 = disabled).
        cache_file: Path to the cache JSON file.
        ratelimit_queries: Maximum API queries allowed in window (0 = disabled).
        ratelimit_hours: Sliding window duration in hours for rate limiting.
        ratelimit_file: Path to the rate limit tracking JSON file.
        output_dir: Directory to save valid UID results as files.
        output_format: Format for saved files.
    """

    credentials: FinanzOnlineCredentials
    uid_tn: str
    session_timeout: float = 30.0
    query_timeout: float = 30.0
    default_recipients: list[str] | None = None
    email_format: EmailFormat = _DEFAULT_EMAIL_FORMAT
    cache_results_hours: float = 48.0
    cache_file: Path | None = None
    ratelimit_queries: int = 50
    ratelimit_hours: float = 24.0
    ratelimit_file: Path | None = None
    output_dir: Path | None = None
    output_format: FileFormat = FileFormat.HTML


def _refusal_text(section: ConfigSection, error: ValidationError) -> str:
    """Render a section model's refusal as ``<section>.<field>: <reason>`` lines.

    Built from ``error.errors()`` rather than ``str(error)``, which would hand the
    user Pydantic's internals (error type codes, documentation URLs).

    Examples:
        >>> try:
        ...     FinanzOnlineSection.model_validate({"output_dir": True})
        ... except ValidationError as exc:
        ...     print(_refusal_text(ConfigSection.FINANZONLINE, exc))
        finanzonline.output_dir: must be a directory path given as text, got bool
    """
    return "; ".join(f"{section.value}.{'.'.join(str(part) for part in detail['loc'])}: {detail['msg']}" for detail in error.errors())


def load_finanzonline_config(config: Config) -> FinanzOnlineConfig:
    """Load FinanzOnline configuration from layered config.

    Args:
        config: Loaded layered configuration object.

    Returns:
        FinanzOnlineConfig with validated credentials and settings.

    Raises:
        ConfigurationError: If required configuration values are missing or invalid,
            or a setting has a type it cannot be read from (``output_dir = true``).

    Example:
        >>> load_finanzonline_config(Config({"finanzonline": {"output_dir": ["x"]}}, {}))
        Traceback (most recent call last):
        ...
        finanzonline_uid.domain.errors.ConfigurationError: Invalid FinanzOnline configuration: finanzonline.output_dir: must be a directory path given as text, got list
    """
    try:
        section = FinanzOnlineSection.model_validate(dict(read_config_section(config, ConfigSection.FINANZONLINE)))
    except ValidationError as exc:
        raise ConfigurationError(f"Invalid FinanzOnline configuration: {_refusal_text(ConfigSection.FINANZONLINE, exc)}") from None

    missing = section.missing_required()
    if missing:
        raise ConfigurationError(f"Missing required FinanzOnline configuration: {', '.join(missing)}. Configure via config file or environment variables.")

    # Create credentials (validation happens in __post_init__)
    try:
        credentials = FinanzOnlineCredentials(
            tid=section.tid,
            benid=section.benid,
            pin=section.pin,
            herstellerid=section.herstellerid,
        )
    except ValueError as e:
        raise ConfigurationError(f"Invalid credentials: {e}") from e

    # Checked after the credentials, as before: a config with both faults reports the credentials first.
    if not section.uid_tn.upper().startswith("ATU"):
        raise ConfigurationError(f"finanzonline.uid_tn must start with 'ATU', got: {section.uid_tn}")

    return FinanzOnlineConfig(
        credentials=credentials,
        uid_tn=section.uid_tn,
        session_timeout=section.session_timeout,
        query_timeout=section.query_timeout,
        default_recipients=list(section.default_recipients) or None,
        email_format=section.email_format,
        cache_results_hours=section.cache_results_hours,
        cache_file=section.cache_file,
        ratelimit_queries=section.ratelimit_queries,
        ratelimit_hours=section.ratelimit_hours,
        ratelimit_file=section.ratelimit_file,
        output_dir=section.output_dir,
        output_format=section.output_format,
    )


__all__ = [
    "AppConfig",
    "AppSection",
    "FinanzOnlineConfig",
    "FinanzOnlineSection",
    "empty_text_list",
    "get_config",
    "get_default_config_path",
    "load_app_config",
    "load_email_format",
    "load_finanzonline_config",
    "number_or_default",
    "parse_string_list",
    "path_setting",
    "read_config_section",
    "text_setting",
]
