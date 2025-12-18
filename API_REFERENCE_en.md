# Python API Reference

This document describes the Python API for `uid_check_austria`.

## Public Exports

```python
import uid_check_austria

# Package metadata
uid_check_austria.__version__    # "0.0.1"
uid_check_austria.__title__      # "Python library and CLI..."
uid_check_austria.__author__     # "bitranox"
uid_check_austria.__url__        # "https://github.com/bitranox/uid_check_austria"
```

---

## Configuration

### `get_config()`

Load layered configuration from all sources.

```python
from uid_check_austria.config import get_config

config = get_config()
# or with profile
config = get_config(profile="production")
# or with custom start directory for .env discovery
config = get_config(start_dir="/path/to/project")
```

**Parameters:**

| Parameter   | Type          | Default | Description                            |
|-------------|---------------|---------|----------------------------------------|
| `profile`   | `str \| None` | `None`  | Profile name for environment isolation |
| `start_dir` | `str \| None` | `None`  | Directory for .env file discovery      |

**Returns:** `Config` - Immutable configuration object

---

### `FinanzOnlineConfig`

Configuration for FinanzOnline connection.

```python
from uid_check_austria.config import FinanzOnlineConfig, load_finanzonline_config

# Load from layered config
config = get_config()
fo_config = load_finanzonline_config(config)
```

**Attributes:**

| Attribute             | Type                      | Default  | Description                              |
|-----------------------|---------------------------|----------|------------------------------------------|
| `credentials`         | `FinanzOnlineCredentials` | Required | Authentication credentials               |
| `uid_tn`              | `str`                     | Required | Own Austrian UID (must start with ATU)   |
| `session_timeout`     | `float`                   | `30.0`   | Timeout for session operations (seconds) |
| `query_timeout`       | `float`                   | `30.0`   | Timeout for query operations (seconds)   |
| `default_recipients`  | `list[str] \| None`       | `None`   | Default email recipients                 |
| `email_format`        | `EmailFormat`             | `BOTH`   | Email body format                        |
| `cache_results_hours` | `float`                   | `48.0`   | Hours to cache valid results             |
| `cache_file`          | `Path \| None`            | `None`   | Path to cache JSON file                  |
| `ratelimit_queries`   | `int`                     | `50`     | Max queries in time window               |
| `ratelimit_hours`     | `float`                   | `24.0`   | Sliding window duration in hours         |
| `ratelimit_file`      | `Path \| None`            | `None`   | Path to rate limit tracking file         |

---

## Domain Models

### `FinanzOnlineCredentials`

Authentication credentials for FinanzOnline web services.

```python
from uid_check_austria.domain.models import FinanzOnlineCredentials

credentials = FinanzOnlineCredentials(
    tid="123456789",      # Participant ID (8-12 alphanumeric)
    benid="WEBUSER",      # User ID (5-12 chars)
    pin="password123",    # Password (5-128 chars)
    herstellerid="ATU12345678"  # Software producer VAT-ID (10-24 alphanumeric)
)
```

**Validation Rules (per login.xsd):**

| Field          | Pattern            | Description                    |
|----------------|--------------------|--------------------------------|
| `tid`          | 8-12 alphanumeric  | Participant ID (Teilnehmer-ID) |
| `benid`        | 5-12 characters    | User ID (Benutzer-ID)          |
| `pin`          | 5-128 characters   | Password/PIN                   |
| `herstellerid` | 10-24 alphanumeric | VAT-ID of software producer    |

---

### `UidCheckRequest`

Request parameters for Level 2 UID verification.

```python
from uid_check_austria.domain.models import UidCheckRequest

request = UidCheckRequest(
    uid_tn="ATU12345678",    # Own Austrian UID
    uid="DE987654321",       # Target VAT ID to verify
    stufe=2                  # Query level (always 2)
)
```

**Attributes:**

| Attribute | Type  | Default  | Description                            |
|-----------|-------|----------|----------------------------------------|
| `uid_tn`  | `str` | Required | Own Austrian UID (must start with ATU) |
| `uid`     | `str` | Required | Target EU VAT ID to verify             |
| `stufe`   | `int` | `2`      | Query level (only 2 supported)         |

---

### `UidCheckResult`

Complete result from Level 2 UID verification.

```python
from uid_check_austria.domain.models import UidCheckResult

# Example result
result.uid           # "DE987654321"
result.return_code   # 0
result.message       # "gueltige UID"
result.name          # "Example GmbH"
result.address       # Address object
result.timestamp     # datetime (UTC)
result.from_cache    # False (True if result was cached)
result.cached_at     # None (or original query datetime if from cache)

# Properties
result.is_valid      # True if return_code == 0
result.is_invalid    # True if return_code == 1
result.has_company_info  # True if name or address present
```

**Attributes:**

| Attribute     | Type               | Default   | Description                              |
|---------------|--------------------|-----------|------------------------------------------|
| `uid`         | `str`              | Required  | The VAT ID that was verified             |
| `return_code` | `int`              | Required  | FinanzOnline return code                 |
| `message`     | `str`              | Required  | Human-readable status message            |
| `name`        | `str`              | `""`      | Company name (if UID valid)              |
| `address`     | `Address \| None`  | `None`    | Company address (if UID valid)           |
| `timestamp`   | `datetime`         | Now (UTC) | When verification was performed          |
| `from_cache`  | `bool`             | `False`   | Whether result was retrieved from cache  |
| `cached_at`   | `datetime \| None` | `None`    | Original query timestamp if from cache   |

---

### `Address`

Company address from Level 2 UID verification.

```python
from uid_check_austria.domain.models import Address

address = Address(
    line1="Example GmbH",
    line2="Hauptstrasse 1",
    line3="1010 Wien",
    line4="",
    line5="",
    line6=""
)

# Methods
address.as_lines()  # ["Example GmbH", "Hauptstrasse 1", "1010 Wien"]
address.as_text()   # "Example GmbH\nHauptstrasse 1\n1010 Wien"
address.as_text(", ")  # "Example GmbH, Hauptstrasse 1, 1010 Wien"
address.is_empty    # False
```

**Attributes:**

| Attribute         | Type  | Default | Description       |
|-------------------|-------|---------|-------------------|
| `line1` - `line6` | `str` | `""`    | Address lines 1-6 |

---

## Use Cases

### `CheckUidUseCase`

Main use case for executing Level 2 UID verification.

```python
from uid_check_austria.application.use_cases import CheckUidUseCase
from uid_check_austria.adapters.finanzonline import (
    FinanzOnlineSessionClient,
    FinanzOnlineQueryClient
)
from uid_check_austria.domain.models import FinanzOnlineCredentials

# Create clients
session_client = FinanzOnlineSessionClient(timeout=30.0)
query_client = FinanzOnlineQueryClient(timeout=30.0)

# Create use case
use_case = CheckUidUseCase(session_client, query_client)

# Execute verification
credentials = FinanzOnlineCredentials(
    tid="123456789",
    benid="WEBUSER",
    pin="password",
    herstellerid="ATU12345678"
)

result = use_case.execute(
    credentials=credentials,
    uid_tn="ATU12345678",
    target_uid="DE987654321"
)

print(f"Valid: {result.is_valid}")
print(f"Company: {result.name}")
```

**Parameters for `execute()`:**

| Parameter     | Type                      | Description                |
|---------------|---------------------------|----------------------------|
| `credentials` | `FinanzOnlineCredentials` | Authentication credentials |
| `uid_tn`      | `str`                     | Own Austrian UID           |
| `target_uid`  | `str`                     | Target VAT ID to verify    |

**Returns:** `UidCheckResult`

**Raises:**
- `SessionError` - Login or session management failed
- `QueryError` - UID query execution failed
- `ValueError` - Invalid request parameters

---

## Email Functions

### `EmailConfig`

Email configuration container.

```python
from uid_check_austria.mail import EmailConfig

config = EmailConfig(
    smtp_hosts=["smtp.example.com:587"],
    from_address="alerts@example.com",
    smtp_username="user@example.com",  # Optional
    smtp_password="password",           # Optional
    use_starttls=True,
    timeout=30.0,
    raise_on_missing_attachments=True,
    raise_on_invalid_recipient=True,
    default_recipients=["admin@example.com"]
)
```

**Attributes:**

| Attribute                      | Type          | Default               | Description                        |
|--------------------------------|---------------|-----------------------|------------------------------------|
| `smtp_hosts`                   | `list[str]`   | `[]`                  | SMTP servers in 'host:port' format |
| `from_address`                 | `str`         | `"noreply@localhost"` | Default sender address             |
| `smtp_username`                | `str \| None` | `None`                | SMTP authentication username       |
| `smtp_password`                | `str \| None` | `None`                | SMTP authentication password       |
| `use_starttls`                 | `bool`        | `True`                | Enable STARTTLS                    |
| `timeout`                      | `float`       | `30.0`                | Socket timeout (seconds)           |
| `raise_on_missing_attachments` | `bool`        | `True`                | Raise on missing files             |
| `raise_on_invalid_recipient`   | `bool`        | `True`                | Raise on invalid addresses         |
| `default_recipients`           | `list[str]`   | `[]`                  | Default recipients                 |

---

### `send_email()`

Send an email using configured SMTP settings.

```python
from uid_check_austria.mail import EmailConfig, send_email
from pathlib import Path

config = EmailConfig(
    smtp_hosts=["smtp.example.com:587"],
    from_address="alerts@example.com"
)

send_email(
    config=config,
    recipients=["user@example.com"],
    subject="Test Email",
    body="Plain text body",
    body_html="<h1>HTML body</h1>",  # Optional
    from_address="override@example.com",  # Optional
    attachments=[Path("report.pdf")]  # Optional
)
```

**Parameters:**

| Parameter      | Type                     | Default  | Description           |
|----------------|--------------------------|----------|-----------------------|
| `config`       | `EmailConfig`            | Required | Email configuration   |
| `recipients`   | `str \| Sequence[str]`   | Required | Recipient address(es) |
| `subject`      | `str`                    | Required | Email subject         |
| `body`         | `str`                    | `""`     | Plain-text body       |
| `body_html`    | `str`                    | `""`     | HTML body             |
| `from_address` | `str \| None`            | `None`   | Override sender       |
| `attachments`  | `Sequence[Path] \| None` | `None`   | File paths to attach  |

**Returns:** `bool` - True on success

**Raises:**
- `ValueError` - No valid recipients
- `FileNotFoundError` - Missing attachment
- `RuntimeError` - All SMTP hosts failed

---

### `send_notification()`

Send a simple plain-text notification email.

```python
from uid_check_austria.mail import EmailConfig, send_notification

config = EmailConfig(
    smtp_hosts=["smtp.example.com:587"],
    from_address="alerts@example.com"
)

send_notification(
    config=config,
    recipients="admin@example.com",
    subject="System Alert",
    message="Backup completed successfully"
)
```

**Parameters:**

| Parameter    | Type                   | Default  | Description           |
|--------------|------------------------|----------|-----------------------|
| `config`     | `EmailConfig`          | Required | Email configuration   |
| `recipients` | `str \| Sequence[str]` | Required | Recipient address(es) |
| `subject`    | `str`                  | Required | Subject line          |
| `message`    | `str`                  | Required | Notification message  |

**Returns:** `bool` - True on success

---

### `load_email_config_from_dict()`

Load EmailConfig from a configuration dictionary.

```python
from uid_check_austria.mail import load_email_config_from_dict
from uid_check_austria.config import get_config

config = get_config()
email_config = load_email_config_from_dict(config.as_dict())
```

---

## Exceptions

All domain exceptions inherit from `UidCheckError`:

```python
from uid_check_austria.domain.errors import (
    UidCheckError,           # Base exception
    ConfigurationError,      # Missing or invalid configuration
    AuthenticationError,     # Login/credentials failure
    SessionError,            # Session management errors
    QueryError,              # UID query execution errors
)
```

| Exception             | Attributes                                           | Description                             |
|-----------------------|------------------------------------------------------|-----------------------------------------|
| `UidCheckError`       | `message`                                            | Base exception for all UID check errors |
| `ConfigurationError`  | `message`                                            | Missing or invalid configuration        |
| `AuthenticationError` | `message`, `return_code`, `diagnostics`              | Login failed                            |
| `SessionError`        | `message`, `return_code`, `diagnostics`              | Session management failed               |
| `QueryError`          | `message`, `return_code`, `retryable`, `diagnostics` | Query execution failed                  |

---

## Return Code Utilities

```python
from uid_check_austria.domain.return_codes import (
    get_return_code_info,
    is_success,
    is_retryable,
    Severity,
    ReturnCodeInfo
)

# Get info about a return code
info = get_return_code_info(0)
print(info.code)       # 0
print(info.meaning)    # "UID is valid"
print(info.severity)   # Severity.SUCCESS
print(info.retryable)  # False

# Quick checks
is_success(0)      # True
is_retryable(1513) # True (rate limit)
```
