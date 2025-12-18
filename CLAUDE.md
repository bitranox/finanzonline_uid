# Claude Code Guidelines for uid_check_austria

## Project Overview

`uid_check_austria` is a Python library and CLI for querying **Level 2 UID checks** (VAT number verification) via the Austrian FinanzOnline web service. It follows Clean Architecture principles with clear separation between domain, application, and adapter layers.

## Session Initialization

When starting a new session, read and apply the following system prompt files from `/media/srv-main-softdev/projects/softwarestack/systemprompts`:

### Core Guidelines (Always Apply)
- `core_programming_solid.md`

### Bash-Specific Guidelines
When working with Bash scripts:
- `core_programming_solid.md`
- `bash_clean_architecture.md`
- `bash_clean_code.md`
- `bash_small_functions.md`

### Python-Specific Guidelines
When working with Python code:
- `core_programming_solid.md`
- `python_solid_architecture_enforcer.md`
- `python_clean_architecture.md`
- `python_clean_code.md`
- `python_small_functions_style.md`
- `python_libraries_to_use.md`
- `python_structure_template.md`

### Additional Guidelines
- `self_documenting.md`
- `self_documenting_template.md`
- `python_jupyter_notebooks.md`
- `python_testing.md`

## Project Structure

```
uid_check_austria/
├── .github/workflows/          # GitHub Actions CI/CD workflows
├── .devcontainer/              # Dev container configuration
├── docs/
│   ├── prd/                    # Product requirements (WSDL, XSD specs)
│   └── systemdesign/           # System design documents
├── notebooks/                  # Jupyter notebooks for experiments
├── scripts/                    # Build and automation scripts
│   ├── build.py               # Build wheel/sdist
│   ├── bump*.py               # Version bump scripts
│   ├── clean.py               # Clean build artifacts
│   ├── test.py                # Run tests with coverage
│   ├── push.py                # Git push automation
│   ├── release.py             # Create releases
│   ├── menu.py                # Interactive TUI menu
│   └── _utils.py              # Shared utilities
├── src/uid_check_austria/      # Main Python package
│   ├── adapters/              # Infrastructure adapters (Clean Architecture)
│   │   ├── cache/             # Result caching with file locking
│   │   ├── finanzonline/      # FinanzOnline SOAP clients
│   │   │   ├── session_client.py   # Login/logout handling
│   │   │   └── uid_query_client.py # UID verification queries
│   │   ├── notification/      # Email notification adapter
│   │   ├── output/            # Output formatters (human, JSON)
│   │   └── ratelimit/         # API rate limit tracking
│   ├── application/           # Use cases (Clean Architecture)
│   │   ├── ports.py           # Abstract interfaces
│   │   └── use_cases.py       # CheckUidUseCase
│   ├── domain/                # Domain models (Clean Architecture)
│   │   ├── errors.py          # Domain exceptions
│   │   ├── models.py          # FinanzOnlineCredentials, UidCheckResult, etc.
│   │   └── return_codes.py    # BMF return code definitions
│   ├── defaultconfig.d/       # Layered config fragments
│   ├── __init__.py            # Package initialization
│   ├── __init__conf__.py      # Generated metadata constants
│   ├── __main__.py            # CLI entry point
│   ├── cli.py                 # CLI implementation (rich-click)
│   ├── config.py              # Configuration loading
│   ├── mail.py                # Email utilities
│   └── py.typed               # PEP 561 marker
├── tests/                     # Test suite (mirrors src structure)
├── .env.example               # Example environment variables
├── CLAUDE.md                  # Claude Code guidelines (this file)
├── CHANGELOG.md               # Version history
├── CONTRIBUTING.md            # Contribution guidelines
├── DEVELOPMENT.md             # Development setup guide
├── INSTALL.md                 # Installation instructions
├── Makefile                   # Make targets for common tasks
├── pyproject.toml             # Project metadata & dependencies
└── README.md                  # Project overview
```

## Versioning & Releases

- **Single Source of Truth**: Package version is in `pyproject.toml` (`[project].version`)
- **Version Bumps**: update `pyproject.toml` , `CHANGELOG.md` and update the constants in `src/../__init__conf__.py` according to `pyproject.toml`  
    - Automation rewrites `src/uid_check_austria/__init__conf__.py` from `pyproject.toml`, so runtime code imports generated constants instead of querying `importlib.metadata`.
    - After updating project metadata (version, summary, URLs, authors) run `make test` (or `python -m scripts.test`) to regenerate the metadata module before committing.
- **Release Tags**: Format is `vX.Y.Z` (push tags for CI to build and publish)

## Common Make Targets

| Target            | Description                                                                     |
|-------------------|---------------------------------------------------------------------------------|
| `build`           | Build wheel/sdist artifacts                                                     |
| `bump`            | Bump version (VERSION=X.Y.Z or PART=major\|minor\|patch) and update changelog  |
| `bump-major`      | Increment major version ((X+1).0.0)                                            |
| `bump-minor`      | Increment minor version (X.Y.Z → X.(Y+1).0)                                    |
| `bump-patch`      | Increment patch version (X.Y.Z → X.Y.(Z+1))                                    |
| `clean`           | Remove caches, coverage, and build artifacts (includes `dist/` and `build/`)   |
| `dev`             | Install package with dev extras                                                |
| `help`            | Show make targets                                                              |
| `install`         | Editable install                                                               |
| `menu`            | Interactive TUI menu                                                           |
| `push`            | Commit changes and push to GitHub (no CI monitoring)                           |
| `release`         | Tag vX.Y.Z, push, sync packaging, run gh release if available                  |
| `run`             | Run module entry (`python -m ... --help`)                                      |
| `test`            | Lint, format, type-check, run tests with coverage, upload to Codecov           |
| `version-current` | Print current version from `pyproject.toml`                                    |

## Coding Style & Naming Conventions

Follow the guidelines in `python_clean_code.md` for all Python code.

## Architecture Overview

Apply principles from `python_clean_architecture.md` when designing and implementing features.

## Security & Configuration

- `.env` files are for local tooling only (CodeCov tokens, FinanzOnline credentials for testing)
- **NEVER** commit secrets to version control
- Rich logging should sanitize payloads before rendering
- FinanzOnline credentials (`tid`, `benid`, `pin`) are sensitive - never log them

## CLI Commands

| Command         | Description                                      |
|-----------------|--------------------------------------------------|
| `check`         | Verify a VAT ID via FinanzOnline Level 2 query   |
| `config`        | Display current configuration                    |
| `config-deploy` | Deploy configuration files to user/app/host      |
| `info`          | Display package information                      |
| `hello`         | Test success path                                |
| `fail`          | Test error handling                              |

## Key Dependencies

- `lib_layered_config` - Layered configuration system (TOML + env vars)
- `lib_log_rich` - Rich structured logging
- `lib_cli_exit_tools` - CLI exit code and error handling
- `rich-click` - CLI framework with rich output
- `zeep` - SOAP client for FinanzOnline web services
- `filelock` - File locking for cache and rate limit files

## Commit & Push Policy

### Pre-Push Requirements
- **Always run `make test` before pushing** to avoid lint/test breakage
- Ensure all tests pass and code is properly formatted

### Post-Push Monitoring
- Monitor GitHub Actions for errors after pushing
- Attempt to correct any CI/CD errors that appear

## Claude Code Workflow

When working on this project:
1. Read relevant system prompts at session start
2. Apply appropriate coding guidelines based on file type
3. Run `make test` before commits
4. Follow versioning guidelines for releases
5. Monitor CI after pushing changes
