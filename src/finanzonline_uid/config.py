"""Configuration management using lib_layered_config.

Provides a centralized configuration loader that merges defaults, application
configs, host configs, user configs, .env files, and environment variables
following a deterministic precedence order.

Contents:
    * :func:`get_config` – loads configuration with lib_layered_config
    * :func:`get_default_config_path` – returns path to bundled default config
    * :func:`load_finanzonline_config` – loads FinanzOnline credentials and settings

    Configuration identifiers (vendor, app, slug) are imported from
    :mod:`finanzonline_uid.__init__conf__` as LAYEREDCONF_* constants.

System Role:
    Acts as the configuration adapter layer, bridging lib_layered_config with the
    application's runtime needs while keeping domain logic decoupled from
    configuration mechanics.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from lib_layered_config import Config, read_config

from . import __init__conf__
from .domain.errors import ConfigurationError
from .domain.models import FinanzOnlineCredentials
from .enums import EmailFormat


# =============================================================================
# Configuration Parsing Helpers
# =============================================================================


def _parse_float(raw: Any, default: float) -> float:
    """Parse a float value with fallback to default."""
    return float(raw) if isinstance(raw, (int, float)) else default


def _parse_int(raw: Any, default: int) -> int:
    """Parse an integer value with fallback to default."""
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        return int(raw)
    return default


def _parse_string_list(raw: object) -> list[str]:
    """Parse a string list from config, handling JSON strings from .env files."""
    import json

    if isinstance(raw, list):
        return [str(item) for item in cast(list[object], raw) if item]

    if isinstance(raw, str) and raw.startswith("["):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(item) for item in cast(list[object], parsed) if item]
        except json.JSONDecodeError:
            pass

    return []


def _parse_email_format(raw: Any, default: EmailFormat) -> EmailFormat:
    """Parse email format from config value.

    Args:
        raw: Raw config value (string or EmailFormat).
        default: Default value if parsing fails.

    Returns:
        EmailFormat enum value.
    """
    if isinstance(raw, EmailFormat):
        return raw

    if isinstance(raw, str):
        normalized = raw.lower().strip()
        try:
            return EmailFormat(normalized)
        except ValueError:
            pass

    return default


def _get_cache_dir() -> Path:
    """Get platform-specific cache directory.

    Returns:
        Path to cache directory:
        - Linux: ~/.cache/finanzonline-uid/
        - macOS: ~/Library/Caches/finanzonline-uid/
        - Windows: %LOCALAPPDATA%/finanzonline-uid/
    """
    import sys

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


def _parse_cache_file_path(raw: Any) -> Path:
    """Parse cache file path from config value.

    Args:
        raw: Raw config value (string path or None).

    Returns:
        Path object, using platform default if not specified.
    """
    if isinstance(raw, str) and raw.strip():
        return Path(raw.strip()).expanduser()
    if isinstance(raw, Path):
        return raw
    return _get_default_cache_path()


def _parse_ratelimit_file_path(raw: Any) -> Path:
    """Parse rate limit file path from config value.

    Args:
        raw: Raw config value (string path or None).

    Returns:
        Path object, using platform default if not specified.
    """
    if isinstance(raw, str) and raw.strip():
        return Path(raw.strip()).expanduser()
    if isinstance(raw, Path):
        return raw
    return _get_default_ratelimit_path()


@lru_cache(maxsize=1)
def get_default_config_path() -> Path:
    """Return the path to the bundled default configuration file.

    The default configuration ships with the package and needs to be
    locatable at runtime regardless of how the package is installed.
    Uses __file__ to locate the defaultconfig.toml file relative to this
    module.

    Returns:
        Absolute path to defaultconfig.toml.

    Note:
        This function is cached since the path never changes during runtime.

    Example:
        >>> path = get_default_config_path()
        >>> path.name
        'defaultconfig.toml'
        >>> path.exists()
        True
    """
    return Path(__file__).parent / "defaultconfig.toml"


# Cache configuration to avoid redundant file I/O and parsing.
# Trade-offs:
#   ✅ Future-proof if config is read from multiple places
#   ✅ Near-zero overhead (single cache entry)
#   ❌ Prevents dynamic config reloading (if ever needed)
#   ❌ start_dir/profile parameter variations would bypass cache
@lru_cache(maxsize=4)
def get_config(*, profile: str | None = None, start_dir: str | None = None) -> Config:
    """Load layered configuration with application defaults.

    Centralizes configuration loading so all entry points use the same
    precedence rules and default values without duplicating the discovery
    logic. Uses lru_cache to avoid redundant file reads when called from
    multiple modules.

    Loads configuration from multiple sources in precedence order:
    defaults → app → host → user → dotenv → env

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
        This function is cached (maxsize=4). The first call loads and parses all
        configuration files; subsequent calls with the same parameters return the
        cached Config instance immediately.

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


@dataclass(frozen=True, slots=True)
class AppConfig:
    """General application configuration.

    Attributes:
        language: Language code for user-facing messages (en, de, es, fr, ru).
    """

    language: str = "en"


def load_app_config(config: Config) -> AppConfig:
    """Load application configuration from layered config.

    Args:
        config: Loaded layered configuration object.

    Returns:
        AppConfig with language setting.

    Example:
        >>> config = get_config()  # doctest: +SKIP
        >>> app_config = load_app_config(config)  # doctest: +SKIP
        >>> app_config.language  # doctest: +SKIP
        'en'
    """
    from .i18n import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES

    config_dict = config.as_dict()
    app_section_raw = config_dict.get("app", {})
    app_section: Mapping[str, Any] = cast(Mapping[str, Any], app_section_raw if isinstance(app_section_raw, dict) else {})

    # Parse language with validation
    raw_language = app_section.get("language", DEFAULT_LANGUAGE)
    language = str(raw_language).lower().strip() if raw_language else DEFAULT_LANGUAGE

    if language not in SUPPORTED_LANGUAGES:
        language = DEFAULT_LANGUAGE

    return AppConfig(language=language)


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
    """

    credentials: FinanzOnlineCredentials
    uid_tn: str
    session_timeout: float = 30.0
    query_timeout: float = 30.0
    default_recipients: list[str] | None = None
    email_format: EmailFormat = EmailFormat.BOTH
    cache_results_hours: float = 48.0
    cache_file: Path | None = None
    ratelimit_queries: int = 50
    ratelimit_hours: float = 24.0
    ratelimit_file: Path | None = None


def load_finanzonline_config(config: Config) -> FinanzOnlineConfig:
    """Load FinanzOnline configuration from layered config.

    Args:
        config: Loaded layered configuration object.

    Returns:
        FinanzOnlineConfig with validated credentials and settings.

    Raises:
        ConfigurationError: If required configuration values are missing.

    Example:
        >>> config = get_config()  # doctest: +SKIP
        >>> fo_config = load_finanzonline_config(config)  # doctest: +SKIP
    """
    config_dict = config.as_dict()
    fo_section_raw = config_dict.get("finanzonline", {})
    fo_section: Mapping[str, Any] = cast(Mapping[str, Any], fo_section_raw if isinstance(fo_section_raw, dict) else {})

    # Required credentials
    tid = fo_section.get("tid", "")
    benid = fo_section.get("benid", "")
    pin = fo_section.get("pin", "")
    uid_tn = fo_section.get("uid_tn", "")
    herstellerid = fo_section.get("herstellerid", "")

    # Validate required fields
    missing: list[str] = []
    if not tid:
        missing.append("finanzonline.tid")
    if not benid:
        missing.append("finanzonline.benid")
    if not pin:
        missing.append("finanzonline.pin")
    if not uid_tn:
        missing.append("finanzonline.uid_tn")
    if not herstellerid:
        missing.append("finanzonline.herstellerid")

    if missing:
        raise ConfigurationError(f"Missing required FinanzOnline configuration: {', '.join(missing)}. Configure via config file or environment variables.")

    # Create credentials (validation happens in __post_init__)
    try:
        credentials = FinanzOnlineCredentials(
            tid=str(tid),
            benid=str(benid),
            pin=str(pin),
            herstellerid=str(herstellerid),
        )
    except ValueError as e:
        raise ConfigurationError(f"Invalid credentials: {e}") from e

    # Validate uid_tn format
    uid_tn_str = str(uid_tn)
    if not uid_tn_str.upper().startswith("ATU"):
        raise ConfigurationError(f"finanzonline.uid_tn must start with 'ATU', got: {uid_tn_str}")

    # Optional settings with defaults
    session_timeout = _parse_float(fo_section.get("session_timeout", 30.0), 30.0)
    query_timeout = _parse_float(fo_section.get("query_timeout", 30.0), 30.0)

    # Parse default_recipients - handle JSON string from .env files
    default_recipients = _parse_string_list(fo_section.get("default_recipients", []))

    # Parse email_format - defaults to "both" (HTML and plain text)
    email_format = _parse_email_format(fo_section.get("email_format", "both"), EmailFormat.BOTH)

    # Parse cache settings - defaults to 48 hours with platform-specific path
    cache_results_hours = _parse_float(fo_section.get("cache_results_hours", 48.0), 48.0)
    cache_file = _parse_cache_file_path(fo_section.get("cache_file"))

    # Parse rate limit settings - defaults to 50 queries per 24 hours
    ratelimit_queries = _parse_int(fo_section.get("ratelimit_queries", 50), 50)
    ratelimit_hours = _parse_float(fo_section.get("ratelimit_hours", 24.0), 24.0)
    ratelimit_file = _parse_ratelimit_file_path(fo_section.get("ratelimit_file"))

    return FinanzOnlineConfig(
        credentials=credentials,
        uid_tn=uid_tn_str,
        session_timeout=session_timeout,
        query_timeout=query_timeout,
        default_recipients=default_recipients if default_recipients else None,
        email_format=email_format,
        cache_results_hours=cache_results_hours,
        cache_file=cache_file,
        ratelimit_queries=ratelimit_queries,
        ratelimit_hours=ratelimit_hours,
        ratelimit_file=ratelimit_file,
    )


__all__ = [
    "AppConfig",
    "FinanzOnlineConfig",
    "get_config",
    "get_default_config_path",
    "load_app_config",
    "load_finanzonline_config",
]
