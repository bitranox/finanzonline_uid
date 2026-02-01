# Changelog

All notable changes to this project will be documented in this file following
the [Keep a Changelog](https://keepachangelog.com/) format.



## [2.5.6] - 2026-02-01

### Fixed

- **macOS test compatibility**: Fixed test failures on macOS caused by `btx_lib_mail`'s security restrictions blocking `/var` directory (where macOS temp files reside under `/private/var/folders/`):
  - Added pre-validation of attachment existence in `send_email()` before calling `btx_send`, ensuring `FileNotFoundError` is raised predictably regardless of OS-specific temp directory locations
  - Updated `test_attachments_are_included` to mock `btx_send` directly, bypassing library security checks while still verifying attachments are correctly passed

## [2.5.5] - 2026-01-29

### Fixed

- **Test fixture type compatibility**: Fixed `MockConfig` class in test fixtures to match the base `Config` class method signatures. Added missing `redact` parameter to `as_dict()` and `to_json()` methods, resolving Pyright type-check errors.

## [2.5.4] - 2026-01-01

### Fixed

- **Test brittleness**: Fixed `test_oldest_entries_trimmed_when_limit_exceeded` to use dynamically calculated timestamps instead of hardcoded dates. Previously used expiration dates in the past (`2025-12-31`) which caused entries to be cleaned up as expired before the trimming logic could run.

## [2.5.3] - 2025-12-29

### Changed

- **Dependencies updated**:
  - `lib_log_rich` minimum version bumped from 6.0.0 to 6.1.0
  - `lib_layered_config` minimum version bumped from 5.1.0 to 5.2.0

## [2.5.2] - 2025-12-28

### Changed

- **Cross-platform path support**: All file path configuration options (`cache_file`, `ratelimit_file`, `output_dir`) now accept forward slashes on Windows. Linux-style UNC paths like `//server/share/path` are automatically converted to Windows-style `\\server\share\path`. This allows using the same config file across platforms without escaping backslashes in TOML.

## [2.5.1] - 2025-12-28

### Changed

- **Default email format changed from "both" to "html"**: Email notifications now send HTML-only content by default instead of multipart/alternative (both HTML and plain text). This reduces email size and improves rendering consistency. The `email_format` configuration option can still be set to `"plain"` or `"both"` if needed.

## [2.5.0] - 2025-12-28

### Added

- **Per-UID rate limiting**: New `per_uid_limit` parameter (default: 2) to track per-UID query counts matching BMF service limits:
  - New `PerUidRateLimitStatus` dataclass with `uid`, `uid_count`, `per_uid_limit`, `is_uid_exceeded` fields
  - New `get_uid_status(uid)` method on `RateLimitTracker` to check per-UID limits
  - Exported from `adapters.ratelimit` module

- **Max entries limits**: Cache and rate-limit files now enforce maximum entry limits to prevent unbounded growth:
  - `UidResultCache`: `max_entries=1000` parameter with auto-cleanup of oldest entries
  - `RateLimitTracker`: `max_entries=10000` parameter with auto-cleanup of oldest entries

- **CLI error formatters**: New functions in `adapters.output.formatters`:
  - `format_error_human()` - Colored console output for errors with ANSI codes
  - `format_error_json()` - Structured JSON error output for programmatic use

### Changed

- **Code architecture improvements** (internal, no API changes):
  - Added `CliContext` dataclass to replace untyped `ctx.obj` dict in CLI
  - Added `_extract_config_section()` helper in `config.py` to eliminate duplicated dict extraction logic
  - Enhanced `CacheEntry` dataclass with `to_dict()`, `from_dict()`, `to_result()`, `from_result()`, and `is_expired()` methods
  - Created `RateLimitEntry` dataclass with `to_dict()`/`from_dict()` methods for typed rate limit tracking
  - Added `EmailConfig.from_dict()` classmethod to consolidate parsing logic
  - Created `SoapLoginResponse` and `SoapUidQueryResponse` dataclasses with `from_zeep()` classmethods for typed SOAP response handling
  - Replaced magic return code numbers with `ReturnCode` enum in `session_client.py` and `uid_query_client.py`
  - Fixed enum docstring examples to show direct comparison instead of `.value` access

- **Module reorganization** (internal, no API changes):
  - Extracted shared HTML formatting to new `adapters/formatting/` module:
    - `html_templates.py` - HTML constants, colors, styles, and helper functions
    - `result_html.py` - `format_result_html()` function
  - Split email adapter into focused modules:
    - `plain_formatter.py` - Plain text formatters for results and errors
    - `error_html_formatter.py` - HTML error notification formatter
    - `rate_limit_formatter.py` - Rate limit warning formatters (plain and HTML)
  - Centralized SOAP response extraction to `domain/soap_utils.py` with `extract_string_attr()` function

### Fixed

- **Security: Credential masking consistency**: Applied `_mask_credential()` to TID and BENID in session client debug logs, matching the masking already applied to PIN and session ID

### Documentation

- Added reference to [finanzonline_databox](https://github.com/bitranox/finanzonline_databox) for automatic download of confirmation documents from FinanzOnline Databox

## [2.4.0] - 2025-12-28

### Added

- **File output option** (`--outputdir`): New option to save valid UID verification results to text files:
  - Filename format: `<UID>_<YYYY-MM-DD>.txt` (e.g., `DE123456789_2025-12-28.txt`)
  - Only valid results (return_code=0) are saved
  - One file per UID per day (overwrites if exists)
  - Directory is auto-created if it doesn't exist
  - Can be set via CLI (`--outputdir`) or config (`finanzonline.output_dir`)
  - Graceful error handling: filesystem errors (permissions, disk full) show a warning but don't fail the UID check
  - Example: `finanzonline-uid check DE123456789 --outputdir /var/log/uid-checks/`

## [2.3.0] - 2025-12-28

### Fixed

- **Security: HTML injection in email notifications**: Added `html.escape()` to all external data (company names, addresses, error messages) inserted into HTML email bodies. Prevents potential XSS in email clients from malicious company names in BMF responses.

- **Security: Credentials exposed in debug logs**: Masked TID and BENID in debug log output using the same masking function already applied to PIN and session ID.

- **SOAP timeout not applied**: Fixed Zeep client initialization to actually use the configured timeout. Previously, the timeout parameter was stored but never passed to the Transport, allowing SOAP requests to hang indefinitely.

- **Austrian UID validation incomplete**: Strengthened `uid_tn` validation from simple prefix check to full regex pattern `^ATU\d{8}$`. Previously accepted malformed values like "ATU" (just prefix), "ATUXYZ" (letters after prefix), or "ATU1" (wrong length).

- **Cache timestamp semantics**: Cached results now return the original query timestamp instead of the retrieval time. This ensures consistent behavior where `timestamp` always reflects when the UID was verified, not when the cache was read.

- **Duplicate CliExitCode enum value**: Removed `UID_VALID = 0` alias which was identical to `SUCCESS = 0`. Python IntEnum treats same-value members as aliases, causing iteration issues.

- **Email notification failures not visible**: Added `click.echo()` output for email notification failures so CLI users see the warning even without log configuration.

- **from_cache/cached_at invariant not enforced**: Added `__post_init__` validation to `UidCheckResult` ensuring `cached_at` is set when `from_cache=True`.

- **Type hint style**: Removed unnecessary string quotes from type annotations where `from __future__ import annotations` makes them redundant.

### Added

- Translations for email notification warning messages (de, es, fr, ru)

## [2.2.0] - 2025-12-28

### Added

- **UID input sanitization**: UID numbers are now automatically cleaned from copy-paste artifacts in both interactive and script modes:
  - Removes all whitespace (spaces, tabs, newlines, non-breaking spaces, Unicode spaces)
  - Removes zero-width and invisible characters (BOM, zero-width space, joiner, etc.)
  - Removes control characters
  - Normalizes to uppercase
  - Example: `"  de 123 456 789  "` becomes `"DE123456789"`

- **Retry mode with countdown** (`--retryminutes`): New option for interactive mode that retries the check at specified intervals until success or cancellation:
  - Requires `--interactive` mode
  - Shows animated countdown display with time until next attempt and total attempts
  - Only retries on transient errors (network, session, rate limit)
  - Stops immediately on permanent errors (invalid UID, auth, config)
  - Email notification sent only on final result (success or final error), not during retries
  - Handles Ctrl+C gracefully via `lib_cli_exit_tools` signal handling
  - Example: `finanzonline-uid check --interactive --retryminutes 5`

### Changed

- **Code simplifications** (internal, no API changes):
  - Consolidated duplicate parsing functions (`parse_float`, `parse_int`, `parse_string_list`) from `mail.py` into `config.py`
  - Simplified `sanitize_uid()` to use single-pass filtering with combined character set
  - Inlined tiny helper functions in `behaviors.py` into `emit_greeting()`
  - Modernized type hints: replaced `Tuple` with `tuple`, `Optional[X]` with `X | None`

### Fixed

- **Retry mode not retrying on retryable return codes**: The `--retryminutes` option now correctly retries when the FinanzOnline service returns transient errors (return codes -2, -3, 12, 1511, 1512, 1513, 1514). Previously, retryable return codes like 1511 (Service Unavailable) would exit immediately instead of waiting and retrying.
- **Countdown display now shows UID**: The retry countdown animation now displays which UID is being checked, improving visibility during long retry sessions.
- **Retry mode countdown fully localized**: All text in the countdown display is now properly translated (de, es, fr, ru). Removed emoji icon from display for cleaner output.

## [2.1.0] - 2025-12-23

### Fixed

- **Email notification status for service errors**: Return code 1511 (service unavailable) and similar codes no longer incorrectly show status as "INVALID". Email notifications now properly distinguish between:
  - `VALID` / `Valid` - UID is valid (return code 0)
  - `INVALID` / `Invalid` - UID is invalid (return code 1)
  - `UNAVAILABLE` / `Service Unavailable` - Service temporarily unavailable (return codes 1511, 1512, -2)
  - `RATE LIMITED` / `Rate Limited` - Rate limit exceeded (return codes 1513, 1514)
  - `ERROR` / (return code meaning) - Other error codes

### Added

- **Translations for new status labels**: Added translations for UNAVAILABLE, RATE LIMITED, Valid, Invalid, Service Unavailable, and Rate Limited in German, Spanish, French, and Russian locales

## [2.0.1] - 2025-12-23

### Fixed

- **Address not showing in output**: BMF returns address fields as `adrz1`-`adrz6`, not `adr_1`-`adr_6` as documented. Fixed SOAP response extraction to use correct attribute names.
- **Address hidden when name empty**: JSON and console formatters now show company address even when company name is empty (uses `has_company_info` property instead of gating on `name`).

## [2.0.0] - 2025-12-20

### Changed (BREAKING)

- **Package renamed** from `uid_check_austria` to `finanzonline_uid`
- **CLI commands renamed** from `uid-check-austria` / `uid_check_austria` to `finanzonline-uid` / `finanzonline_uid`
- **Environment variable prefix** changed from `UID_CHECK_AUSTRIA___` to `FINANZONLINE_UID___`
- **Configuration paths** changed from `uid-check-austria` to `finanzonline-uid`:
  - Linux: `~/.config/finanzonline-uid/`
  - macOS: `~/Library/Application Support/bitranox/FinanzOnline UID/`
- **Import statements** changed: `from uid_check_austria import ...` → `from finanzonline_uid import ...`

### Migration

To migrate from 1.x:
1. Update imports: replace `uid_check_austria` with `finanzonline_uid`
2. Update CLI calls: replace `uid-check-austria` with `finanzonline-uid`
3. Rename config directories if customized
4. Update environment variables: replace `UID_CHECK_AUSTRIA___` prefix with `FINANZONLINE_UID___`

## [1.0.0] - 2025-12-18

- initial release
