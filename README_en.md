# uid_check_austria

<!-- Badges -->
[![CI](https://github.com/bitranox/uid_check_austria/actions/workflows/ci.yml/badge.svg)](https://github.com/bitranox/uid_check_austria/actions/workflows/ci.yml)
[![CodeQL](https://github.com/bitranox/uid_check_austria/actions/workflows/codeql.yml/badge.svg)](https://github.com/bitranox/uid_check_austria/actions/workflows/codeql.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Open in Codespaces](https://img.shields.io/badge/Codespaces-Open-blue?logo=github&logoColor=white&style=flat-square)](https://codespaces.new/bitranox/uid_check_austria?quickstart=1)
[![PyPI](https://img.shields.io/pypi/v/uid_check_austria.svg)](https://pypi.org/project/uid_check_austria/)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/uid_check_austria.svg)](https://pypi.org/project/uid_check_austria/)
[![Code Style: Ruff](https://img.shields.io/badge/Code%20Style-Ruff-46A3FF?logo=ruff&labelColor=000)](https://docs.astral.sh/ruff/)
[![codecov](https://codecov.io/gh/bitranox/uid_check_austria/graph/badge.svg?token=UFBaUDIgRk)](https://codecov.io/gh/bitranox/uid_check_austria)
[![Maintainability](https://qlty.sh/badges/041ba2c1-37d6-40bb-85a0-ec5a8a0aca0c/maintainability.svg)](https://qlty.sh/gh/bitranox/projects/uid_check_austria)
[![Known Vulnerabilities](https://snyk.io/test/github/bitranox/uid_check_austria/badge.svg)](https://snyk.io/test/github/bitranox/uid_check_austria)
[![security: bandit](https://img.shields.io/badge/security-bandit-yellow.svg)](https://github.com/PyCQA/bandit)

> 🇩🇪 **[Deutsche Version verfügbar (README.md)](README.md)**

`uid_check_austria` is a Python library and CLI for querying **Level 2 UID checks** (VAT number verification) via the Austrian FinanzOnline web service. Level 2 checks provide detailed confirmation of EU VAT identification numbers including the registered company name and address.

## Why uid_check_austria?

Verifying VAT IDs through the FinanzOnline web portal requires logging in, navigating menus, and manually entering data - tedious and impossible to automate. With `uid_check_austria`:

- **No browser required** - runs entirely from the command line or from a Windows Icon.
- **Fully scriptable** - integrate into invoicing systems, batch processes, or CI pipelines.
- **Email notifications** - automatic confirmation emails with verification results.
- **Result caching** - avoid redundant API calls with configurable result caching.
- **Rate limit protection** - built-in tracking with email warnings when limits approached.
- **Simple operation** - just pass the UID to query and get results instantly.
- **FREE SOFTWARE** - this software is, and always will be free of charge. If You need installation or other support, that can be booked with the author.

**Features:**
- Query Austrian FinanzOnline for Level 2 UID (VAT ID) verification
- CLI entry point styled with rich-click (rich output + click ergonomics)
- Automatic email notifications with HTML formatting (enabled by default)
- **Multi-language support** - English, German, Spanish, French, Russian
- Human-readable and JSON output formats
- Result caching with configurable TTL (default: 48 hours)
- Rate limit tracking with warning emails
- Layered configuration system with lib_layered_config
- Rich structured logging with lib_log_rich
- Exit-code and messaging helpers powered by lib_cli_exit_tools

**Future Development:**
- coming soon: Automatic download of confirmation documents from your **FinanzOnline Databox**. This you **MUST** do manually at the moment - see **Aufbewahrungspflichten**
- Need additional functionality? Don't hesitate to contact us.

```bash
# Example: verify a VAT ID
uid_check_austria check DE123456789
```

---

## Fair Use Policy

> **How should the UID verification service be used correctly?**
>
> UID verifications should only be requested at the time when intra-Community tax-exempt supplies or other services are provided to customers in other EU member states - not in advance or in bulk. Permanently querying all VAT numbers in your database does not constitute fair usage.
>
> **Please refrain from unnecessary UID verification requests.**

### BMF Rate Limits

Since April 6, 2023, **each VAT number can only be queried twice per day per participant** via the web service. Exceeding this limit returns code `1513`.

### Local Rate Limit Tracking

This tool includes built-in rate limit tracking (default: 50 queries per 24 hours) that:
- Warns you before you approach BMF limits
- Sends email notifications when exceeded
- Successful queries are cached locally to avoid hitting limits by accident
- Does NOT block queries - BMF handles actual enforcement

Configure via `finanzonline.ratelimit_queries` and `finanzonline.ratelimit_hours`.

### FinanzOnline Webservice User

> **IMPORTANT:** The user (BENID) must be configured as a **webservice user** in FinanzOnline user administration.
>
> Common errors:
> - `-4` = Invalid credentials
> - `-7` = User is not a web service user
> - `-8` = Participant locked or not authorized for web service

### Confirmation Documents (Aufbewahrungspflichten)

> **IMPORTANT:** The official confirmation document will be delivered to your **FinanzOnline Databox on the following day**.
>
> This document must be **printed and kept as proof** of the UID verification per § 132 BAO (Bundesabgabenordnung - Austrian Federal Tax Code).

The printed confirmation serves as official documentation for tax audits and must be retained according to Austrian retention requirements (typically 7 years).

---

## Table of Contents

- [Fair Use Policy](#fair-use-policy)
- [Quick Start](#quick-start)
- [Usage](#usage)
- [BMF Return Codes](#bmf-return-codes)
- [Further Documentation](#further-documentation)

---

## Quick Start

Your IT stuff should be perfectly able to install that application easily. If You need support, You might contact the author for paid support.


### Recommended: run via uvx to get automatically the last version

UV - the ultrafast installer - written in Rust (10-20x faster than pip/poetry)

```bash
# install python (Requires >= **Python 3.10+**)
# Install UV
pip install --upgrade uv
# create configuration files
uvx uid_check_austria@latest config-deploy --target user
```

Create your personal config file in the `config.d/` directory (settings are deeply merged, so updates to default configs won't affect your settings):

```bash
# Linux:   ~/.config/uid-check-austria/config.d/99-myconfig.toml
# macOS:   ~/Library/Application Support/bitranox/Uid Check Austria/config.d/99-myconfig.toml
# Windows: %APPDATA%\bitranox\Uid Check Austria\config.d\99-myconfig.toml
```

```toml
# 99-myconfig.toml - Your personal settings
[finanzonline]
tid = "123456789"           # Participant ID (Teilnehmer-ID)
benid = "WEBUSER"           # User ID (Benutzer-ID) - must be webservice user!
pin = "yourpassword"        # Password/PIN
uid_tn = "ATU12345678"      # Your Austrian UID (must start with "ATU")
herstellerid = "ATU12345678" # Software producer VAT-ID (put your Austrian UID)
default_recipients = ["accounting@yourcompany.com"]

[email]
smtp_hosts = ["smtp.example.com:587"]
from_address = "alerts@yourcompany.com"
```

```bash
# Launch the latest version without any further installation
uvx uid_check_austria@latest check DE123456789
```

For alternative install paths (pip, pipx, uvx, source builds), see [INSTALL_en.md](INSTALL_en.md).

---

## Usage

```bash
# check per commandline
uvx uid_check_austria@latest check NL123456789

# check interactive (will ask for the UID to check) : 
uvx uid_check_austria@latest check --interactive
```

the results will be displayed and a email with the results will be sent to the configured email adresses. 

---

## BMF Return Codes

For a complete list of all BMF return codes, see the **[Return Code Reference (RETURNCODES_en.md)](RETURNCODES_en.md)**.

---

## Further Documentation

- [Installation Guide (EN)](INSTALL_en.md) | [Installationsanleitung (DE)](INSTALL_de.md)
- [Configuration Reference (EN)](CONFIGURATION_en.md) | [Konfigurationsreferenz (DE)](CONFIGURATION_de.md)
- [CLI Reference (EN)](CLI_REFERENCE_en.md) | [CLI-Referenz (DE)](CLI_REFERENCE_de.md)
- [Python API Reference (EN)](API_REFERENCE_en.md) | [Python-API-Referenz (DE)](API_REFERENCE_de.md)
- [BMF Return Codes (EN)](RETURNCODES_en.md) | [BMF-Rückgabecodes (DE)](RETURNCODES_de.md)
- [Development Handbook](DEVELOPMENT.md)
- [Contributor Guide](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)
- [Module Reference](docs/systemdesign/module_reference.md)
- [License](LICENSE)
- **[Deutsche Dokumentation (README.md)](README.md)**
