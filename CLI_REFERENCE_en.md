# CLI Reference

This document describes all CLI commands and options for `finanzonline_uid`.

## Global Options

These options apply to all commands:

| Option                         | Default          | Description                                                          |
|--------------------------------|------------------|----------------------------------------------------------------------|
| `--traceback / --no-traceback` | `--no-traceback` | Show full Python traceback on errors                                 |
| `--profile NAME`               | `None`           | Load configuration from a named profile (e.g., 'production', 'test') |
| `--version`                    | -                | Show version and exit                                                |
| `-h, --help`                   | -                | Show help and exit                                                   |

## Commands

The CLI command is registered under `finanzonline-uid` and `finanzonline_uid` - so you can use both.

---

### `check` - Verify a VAT ID

```bash
finanzonline-uid check [OPTIONS] [UID]
```

**Arguments:**

| Argument | Required | Description                                                                 |
|----------|----------|-----------------------------------------------------------------------------|
| `UID`    | Yes*     | EU VAT ID to verify (e.g., DE123456789). *Not required with `--interactive` |

**Options:**

| Option           | Short | Default        | Description                                             |
|------------------|-------|----------------|---------------------------------------------------------|
| `--interactive`  | `-i`  | `False`        | Interactive mode: prompt for UID                        |
| `--no-email`     | -     | `False`        | Disable email notification (email enabled by default)   |
| `--format`       | -     | `human`        | Output format: `human` or `json`                        |
| `--recipient`    | -     | Config default | Email recipient (can specify multiple times)            |
| `--retryminutes` | -     | `None`         | Retry interval in minutes (requires `--interactive`)    |
| `--outputdir`    | `-o`  | Config default | Directory to save valid results as files                |
| `--outputformat` | -     | `html`         | Output file format: `json`, `txt`, or `html`            |

> **Note:** UID inputs are automatically sanitized: whitespace and invisible characters are removed, and converted to uppercase.

**Exit Codes:**

| Code | Meaning              |
|------|----------------------|
| 0    | UID is valid         |
| 1    | UID is invalid       |
| 2    | Configuration error  |
| 3    | Authentication error |
| 4    | Query error          |

**Examples:**

```bash
# Basic usage
finanzonline-uid check DE123456789

# JSON output
finanzonline-uid check DE123456789 --format json

# Without email notification
finanzonline-uid check DE123456789 --no-email

# Custom recipients
finanzonline-uid check DE123456789 --recipient admin@example.com --recipient finance@example.com

# Interactive mode
finanzonline-uid check --interactive

# Retry mode: retry every 5 minutes until success
finanzonline-uid check --interactive --retryminutes 5

# Save valid result to file (default: HTML format)
finanzonline-uid check DE123456789 --outputdir /var/log/uid-checks/

# Save as JSON
finanzonline-uid check DE123456789 --outputdir /var/log/uid-checks/ --outputformat json

# Save as plain text
finanzonline-uid check DE123456789 --outputdir /var/log/uid-checks/ --outputformat txt

# With profile
finanzonline-uid --profile production check DE123456789
```

**File Output (`--outputdir` and `--outputformat`):**

When `--outputdir` is specified and the UID check is valid (return_code=0), the result is saved to a file:

- Filename format: `<UID>_<YYYY-MM-DD>.<ext>` (e.g., `DE123456789_2025-12-28.html`)
- Extension matches the format: `.json`, `.txt`, or `.html`
- Overwrites existing file if present (one file per UID per day per format)
- Directory is created automatically if it doesn't exist
- Can also be configured via `finanzonline.output_dir` and `finanzonline.output_format` in config file

**Output formats:**

| Format | Extension | Description                                        |
|--------|-----------|---------------------------------------------------|
| `html` | `.html`   | Styled HTML document (default, best for archiving) |
| `json` | `.json`   | Structured JSON data (for programmatic use)        |
| `txt`  | `.txt`    | Plain text, human-readable                         |

**Retry Mode (`--retryminutes`):**

The retry mode automatically retries the check on transient errors:

- Shows animated countdown with time until next attempt
- Only retries on transient errors (network, session, rate-limit)
- Aborts immediately on permanent errors (invalid UID, authentication)
- Email is only sent on success or final error
- Can be cancelled anytime with Ctrl+C

---

### `config` - Display Configuration

```bash
finanzonline-uid config [OPTIONS]
```

**Options:**

| Option      | Default | Description                                                                  |
|-------------|---------|------------------------------------------------------------------------------|
| `--format`  | `human` | Output format: `human` or `json`                                             |
| `--section` | `None`  | Show only a specific section (e.g., 'finanzonline', 'email', 'lib_log_rich') |
| `--profile` | `None`  | Override profile from root command                                           |

**Examples:**

```bash
# Show all configuration
finanzonline-uid config

# JSON output for scripting
finanzonline-uid config --format json

# Show only email section
finanzonline-uid config --section email

# Show production profile
finanzonline-uid config --profile production
```

---

### `config-deploy` - Deploy Configuration Files

```bash
finanzonline-uid config-deploy [OPTIONS]
```

**Options:**

| Option      | Required | Default | Description                                                   |
|-------------|----------|---------|---------------------------------------------------------------|
| `--target`  | Yes      | -       | Target layer: `user`, `app`, or `host` (can specify multiple) |
| `--force`   | No       | `False` | Overwrite existing configuration files                        |
| `--profile` | No       | `None`  | Deploy to a specific profile directory                        |

**Examples:**

```bash
# Deploy user configuration
finanzonline-uid config-deploy --target user

# Deploy system-wide (requires privileges)
sudo finanzonline-uid config-deploy --target app

# Deploy multiple targets
finanzonline-uid config-deploy --target user --target host

# Overwrite existing
finanzonline-uid config-deploy --target user --force

# Deploy to production profile
finanzonline-uid config-deploy --target user --profile production
```

---

### `info` - Display Package Information

```bash
finanzonline-uid info
```

Shows package name, version, homepage, author, and other metadata.

---

### `hello` - Test Success Path

```bash
finanzonline-uid hello
```

Emits a greeting message to verify the CLI is working.

---

### `fail` - Test Error Handling

```bash
finanzonline-uid fail
finanzonline-uid --traceback fail  # With full traceback
```

Triggers an intentional error to test error handling.
