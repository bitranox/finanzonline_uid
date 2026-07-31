# Changelog

All notable changes to this project will be documented in this file following
the [Keep a Changelog](https://keepachangelog.com/) format.



## [Unreleased]

## [2.7.9] 2026-08-01 00:40:33
### Fixed
- **Console output no longer crashes on a legacy codepage.** A Windows console at codepage 1252
  hands Python an `errors="strict"` stream, so writing a non-ASCII character such as a check mark
  raised `UnicodeEncodeError: 'charmap' codec can't encode character` and the command exited
  non-zero *after* its work had already succeeded. Click does not protect against this, and Rich
  raises the same way through its own writer. The new `safe_console` module degrades at the sink:
  a UTF-8 terminal still receives the character, and only a stream that cannot encode it sees
  `[OK]` / `[X]` / `[!]`. Every `click.echo` call site routes through it, and a test fails if a
  module reaches for `click.echo` or builds an unwrapped `Console(file=sys.stdout)` again.


## [2.7.8] 2026-07-24

### Fixed
- Restored a clean gate against a latest-ruff regression (94 findings across
  `EXE002`, `I001`, `UP037`, `BLE001`, `RUF022`, `UP035`, `PLE0704`, `G201`,
  `PLC0206`, `PLR1711`, `RET501`, `RUF100`, `SIM117`). Every rule was fixed at
  the root; none were silenced via `[tool.ruff.lint].ignore`.
- 62 `src`/`tests` files carried a stray executable bit with no shebang
  (`EXE002`), an artifact of the softdev SMB/fuse mount; cleared with
  `chmod -x` plus `git update-index --chmod=-x`.
- Two `_handle_*_exception` helpers used a bare `raise` outside of any
  enclosing `except` block (`PLE0704`); it only worked because the caller was
  still inside its own `except` when it called the helper. Replaced with an
  explicit `raise exc` so the re-raise no longer depends on the caller's
  exception context.
- `EmailConfig.default_recipients` used `field(default_factory=list)` after
  ruff's `PIE807` autofix replaced `lambda: []`; the unparameterized `list`
  lost pyright's type information (`list[Unknown]`, `reportUnknownVariableType`).
  Replaced with a small typed factory function, mirroring the existing
  `_default_smtp_hosts` pattern.

### Changed
- Eleven blind `except Exception`/`except BaseException` blocks (`BLE001`) at
  genuine resilience boundaries (CLI top-level entry point, non-fatal email
  and rate-limit notifications, SOAP logout, diagnostics-only XML capture)
  now carry an explicit `# noqa: BLE001` with the reason instead of being
  silently accepted; the broad catch is intentional there.
- `mail.py`'s `logger.error(..., exc_info=True)` is now `logger.exception(...)`
  (`G201`).

## [2.7.7] 2026-07-20

### Fixed
- Restored a green test suite against `btx_lib_mail` 1.5.0, which replaced its
  `send_message` call with a streaming transport that drives raw SMTP verbs
  (`MAIL FROM` / `RCPT TO` / `BDAT`) and unpacks `(code, resp)` replies. Seven
  tests and one doctest stubbed delivery with `patch("smtplib.SMTP")`, and a
  `MagicMock` cannot satisfy that protocol, so every send failed with
  `ValueError: not enough values to unpack`.

### Changed
- `send_email` and `send_notification` accept an optional `transport`, forwarded
  to btx_lib_mail's delivery seam. Passing one substitutes the entire SMTP wire
  protocol, which is how delivery is now exercised without a live server or a
  patched `smtplib`.
- Bump the `btx_lib_mail` floor to `>=1.5.0`, the first release exposing that
  `transport` parameter, and the `filelock` floor to `>=3.31.1`.

## [2.7.6] 2026-07-19

### Changed
- Bump `btx_lib_mail` floor to `>=1.4.0` and wrap the SMTP password in
  `pydantic.SecretStr` when building the `ConfMail` transport config, matching
  btx_lib_mail 1.4.0 which now stores `smtp_password` as a `SecretStr`.
- Declare the `pydantic` dependency that the mail adapter now imports directly.

## [2.7.5] 2026-06-14

### Changed
- Added a `typed_click.py` facade wrapping rich-click's `option` / `version_option` / `argument` decorators behind explicit, fully-known signatures, keeping the CLI strict-clean under pyright 1.1.410 (`reportUnknownMemberType`) without disabling the rule (ignore isolated to the facade).
- Bumped internal dependency floors: `lib_cli_exit_tools>=2.3.2`, `lib_log_rich>=6.3.5`, `lib_layered_config>=5.5.2`, `btx_lib_mail>=1.3.2`.

## [2.7.4] - 2026-05-04

### Fixed

- **Raw response section was missing from failure emails**: When zeep's `last_received` buffer is empty or its envelope cannot be serialized, the diagnostics section was previously skipped silently. The capture now always returns a non-empty marker so the email/CLI output always shows useful context:
  - Captured XML when the response was received
  - `[Request was sent but no SOAP response was captured/parseable]` when only the request envelope is available (the request body is intentionally not dumped  -  it contains credentials)
  - `[No SOAP envelope captured - error occurred before HTTP exchange]` when the failure happened before any HTTP call
- **Capture errors no longer crash diagnostics**: Any exception during XML serialization (lxml internals, oversized envelopes, etc.) is now caught and logged at DEBUG level instead of bubbling up.

### Added

- Four unit tests covering all `_capture_raw_response` paths (response present, sent-only fallback, empty buffer, oversized truncation).

## [2.7.3] - 2026-05-04

### Added

- **Raw SOAP response in error diagnostics**: When the UID query fails (especially the transient zeep `name cannot be None` parsing error), the actual XML response from FinanzOnline is now captured via zeep's `HistoryPlugin` and included in:
  - The error notification email (plain text section + scrollable monospace `<pre>` block in HTML)
  - The CLI human/JSON output
  - The `Diagnostics.raw_response` field
- This makes flaky cross-border (HR/IT/etc.) failures investigable without re-running with debug logging. Captured XML is truncated at 8 KB.

### Changed

- **`Diagnostics` dataclass**: New optional field `raw_response: str = ""` (backward-compatible  -  default empty string).

## [2.7.2] - 2026-05-04

### Fixed

- **Transient zeep parsing errors now retryable**: Cryptic `Unexpected error: ('name cannot be None', <class 'zeep.xsd.elements.element.Element'>)` is now detected and reported as a clear, **retryable** `Query Error` ("Malformed response from FinanzOnline (transient, likely cross-border VIES issue)"). With `--retryminutes N` set, these flaky cross-border (HR/IT/etc.) lookups  -  which usually clear within 2-3 attempts when BMF's upstream VIES forwarding hiccups  -  now retry automatically instead of failing hard.

### Added

- **`is_zeep_parsing_error()` utility** in `domain/soap_utils.py`  -  pure detection helper for the zeep `name cannot be None` TypeError pattern, with full doctest and unit-test coverage.

## [2.7.1] - 2026-04-26

### Fixed

- **CI test failure on macOS**: Made `test_when_check_uses_json_format_it_outputs_json` tolerant of log lines mixed into stdout  -  the test now extracts the JSON portion from `result.output` instead of parsing the whole capture, fixing a regression where the macOS Python 3.12 CI job failed with `JSONDecodeError`.

### Changed

- **PowerShell linter configuration**: Added `[tool.psscriptanalyzer]` section to exclude `PSAvoidUsingInvokeExpression` and `PSAvoidUsingCmdletAliases` rules  -  required for the standard upstream `uv` install snippet (`irm ... | iex`) used in `installer_rotek/finanzonline_uid/install.ps1`.
- **CVE exclusion list cleaned up**: Removed pip 24.3.1 CVE exclusions (CVE-2025-8869, CVE-2026-1703  -  pip is now 26.0.1) and pillow CVE-2026-25990 (pillow now 12.2.0). Added CVE-2026-3219 (pip 26.0.1 concatenated tar/ZIP confusion, no fix available yet).

## [2.7.0] - 2026-04-01

### Added

- **Service maintenance detection**: When FinanzOnline returns an HTML maintenance page instead of a SOAP XML response, the error is now detected and reported as "Service Maintenance" with a clear message instead of a cryptic XML parsing error. The error is marked retryable, so `--retryminutes` automatically retries after maintenance windows.
- **`ServiceMaintenanceError` exception**: New domain exception for maintenance scenarios, inherits from `SessionError` with `retryable=True`.

### Changed

- **CVE exclusion list cleaned up**: Removed 3 resolved setuptools CVE exclusions (PYSEC-2022-43012, PYSEC-2025-49, CVE-2024-6345).

## [2.6.1] - 2026-03-30

### Fixed

- **Rate limit not counting failed retries**: Retryable errors (service unavailable, rate limit exceeded, system maintenance, etc.) no longer count against the local rate limit tracker. Rate limit is now recorded only after a successfully processed query, preventing retry loops from exhausting the local quota with failed attempts.

### Changed

- **CVE exclusion list cleaned up**: Removed resolved CVEs (CVE-2026-25645 requests, CVE-2026-26007 cryptography, CVE-2026-4539 pygments).

## [2.6.0] - 2026-03-27

### Added

- **Clear retry mode messaging**: Retry countdown panel now shows "Retry Mode (unlimited)" title, a persistent "Retries indefinitely" warning, and "Ctrl+C to stop" hint. On the first retryable error, a one-time message explains the retry interval and that retries have no limit.
- **Translations for new retry messages**: Added German, Spanish, French, and Russian translations for all new retry-related strings.

### Changed

- **CVE exclusion list updated**: Removed resolved entries (GHSA-4xh5-x5gv-qwph, CVE-2025-68146), added newly flagged CVE-2025-8869 (pip) and CVE-2026-25990 (pillow). Retained setuptools exclusions needed for Python 3.10/3.11 on Windows CI. Improved inline documentation for each exclusion.
- **CI/CD workflow updates**: Updated GitHub Actions runner, upload/download artifact actions, and workflow configuration.

## [2.5.7] - 2026-02-13

### Removed

- **Deleted legacy `scripts/` module**: Removed the entire `scripts/` directory and its test file `tests/test_scripts.py`. Build automation is now handled by `bmk` via the Makefile.

### Fixed

- **Shell lint compliance in `reset_git_history.sh`**: Fixed indentation (2 → 4 spaces) to satisfy `shfmt` and suppressed shellcheck SC1083 false positive on `HEAD^{tree}` git syntax.

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
