# CLI Reference

This document describes all CLI commands and options for `uid_check_austria`.

## Global Options

These options apply to all commands:

| Option                         | Default          | Description                                                          |
|--------------------------------|------------------|----------------------------------------------------------------------|
| `--traceback / --no-traceback` | `--no-traceback` | Show full Python traceback on errors                                 |
| `--profile NAME`               | `None`           | Load configuration from a named profile (e.g., 'production', 'test') |
| `--version`                    | -                | Show version and exit                                                |
| `-h, --help`                   | -                | Show help and exit                                                   |

## Commands

The CLI command is registered under `uid-check-austria` and `uid_check_austria` - so you can use both.

---

### `check` - Verify a VAT ID

```bash
uid-check-austria check [OPTIONS] [UID]
```

**Arguments:**

| Argument | Required | Description                                                                 |
|----------|----------|-----------------------------------------------------------------------------|
| `UID`    | Yes*     | EU VAT ID to verify (e.g., DE123456789). *Not required with `--interactive` |

**Options:**

| Option          | Short | Default        | Description                                           |
|-----------------|-------|----------------|-------------------------------------------------------|
| `--interactive` | `-i`  | `False`        | Interactive mode: prompt for UID                      |
| `--no-email`    | -     | `False`        | Disable email notification (email enabled by default) |
| `--format`      | -     | `human`        | Output format: `human` or `json`                      |
| `--recipient`   | -     | Config default | Email recipient (can specify multiple times)          |

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
uid-check-austria check DE123456789

# JSON output
uid-check-austria check DE123456789 --format json

# Without email notification
uid-check-austria check DE123456789 --no-email

# Custom recipients
uid-check-austria check DE123456789 --recipient admin@example.com --recipient finance@example.com

# Interactive mode
uid-check-austria check --interactive

# With profile
uid-check-austria --profile production check DE123456789
```

---

### `config` - Display Configuration

```bash
uid-check-austria config [OPTIONS]
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
uid-check-austria config

# JSON output for scripting
uid-check-austria config --format json

# Show only email section
uid-check-austria config --section email

# Show production profile
uid-check-austria config --profile production
```

---

### `config-deploy` - Deploy Configuration Files

```bash
uid-check-austria config-deploy [OPTIONS]
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
uid-check-austria config-deploy --target user

# Deploy system-wide (requires privileges)
sudo uid-check-austria config-deploy --target app

# Deploy multiple targets
uid-check-austria config-deploy --target user --target host

# Overwrite existing
uid-check-austria config-deploy --target user --force

# Deploy to production profile
uid-check-austria config-deploy --target user --profile production
```

---

### `info` - Display Package Information

```bash
uid-check-austria info
```

Shows package name, version, homepage, author, and other metadata.

---

### `hello` - Test Success Path

```bash
uid-check-austria hello
```

Emits a greeting message to verify the CLI is working.

---

### `fail` - Test Error Handling

```bash
uid-check-austria fail
uid-check-austria --traceback fail  # With full traceback
```

Triggers an intentional error to test error handling.
