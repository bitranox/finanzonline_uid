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
finanzonline-uid check DE123456789

# JSON output
finanzonline-uid check DE123456789 --format json

# Without email notification
finanzonline-uid check DE123456789 --no-email

# Custom recipients
finanzonline-uid check DE123456789 --recipient admin@example.com --recipient finance@example.com

# Interactive mode
finanzonline-uid check --interactive

# With profile
finanzonline-uid --profile production check DE123456789
```

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
