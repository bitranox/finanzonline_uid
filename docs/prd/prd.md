# PRD: uid_check_austria - FinanzOnline Level 2 UID Verification

## 1. Overview

**Product**: Python library and CLI for querying Level 2 UID checks via FinanzOnline Austria
**Version**: 0.1.0
**Date**: 2025-12-17

### Purpose
Enable Austrian businesses to programmatically verify EU VAT identification numbers through the BMF FinanzOnline web service, with automatic email confirmation of results.

### Key Features
- Level 2 UID verification (returns company name + address)
- Email notification of results (default enabled, `--no-email` to disable)
- Human-readable and JSON output formats
- Integration with existing lib_layered_config and btx_lib_mail infrastructure

---

## 2. BMF FinanzOnline API Specification

### 2.1 Authentication Flow
```
1. Login  → Session Webservice → SessionID
2. Query  → UID-Abfrage Webservice (with SessionID)
3. Logout → Session Webservice
```

### 2.2 Session Webservice
- **WSDL**: `https://finanzonline.bmf.gv.at/fon/ws/sessionService.wsdl`
- **Login Parameters**:
  - `tid`: Participant ID (Teilnehmer-ID)
  - `benid`: User ID (Benutzer-ID)
  - `pin`: Password/PIN
- **Returns**: `session_id`, `rc` (return code), `msg`

### 2.3 UID Query Webservice
- **WSDL**: `https://finanzonline.bmf.gv.at/fonuid/ws/uidAbfrageService.wsdl`
- **Endpoint**: `https://finanzonline.bmf.gv.at:443/fonuid/ws/uidAbfrage/`
- **Parameters**:
  - `tid`, `benid`: Credentials
  - `id`: SessionID from login
  - `uid_tn`: Own Austrian UID (must start with `ATU`)
  - `uid`: Target EU VAT ID to verify
  - `stufe`: Level (`2` for Level 2 with name/address)
- **Level 2 Response**: `rc`, `msg`, `name`, `adr_1` through `adr_6`

### 2.4 Return Codes
| Code | Meaning | Severity |
|------|---------|----------|
| 0 | UID is valid | success |
| 1 | UID is invalid | warning |
| -1 | Session invalid/expired | error |
| -2 | System maintenance | warning |
| -3 | Technical error | error |
| -4 | Not authorized | critical |
| 4 | Wrong UID format | error |
| 5 | Invalid requester UID | error |
| 10 | Member state forbids query | warning |
| 11 | Not authorized for requester | error |
| 12 | UID not yet queryable | warning |
| 101 | UID doesn't start with ATU | error |
| 103 | VAT group (CZ) - special handling | warning |
| 104 | VAT group (SK) - special handling | warning |
| 105 | Must query via FinanzOnline directly | error |
| 1511 | Service unavailable | critical |
| 1512 | Too many queries (server load) | warning |
| 1513 | Rate limit: 2 queries/UID/day exceeded | warning |
| 1514 | Rate limit: requester limit exceeded | warning |

### 2.5 Rate Limiting
- Max **2 queries per UID per participant per day** via webservice
- Exceeding returns code `1513`
- Direct FinanzOnline portal queries exempt

---

## 3. Functional Requirements

### 3.1 CLI Command: `uid-check-austria check`
```bash
uid-check-austria check <uid> [OPTIONS]

Arguments:
  uid                    EU VAT ID to verify (e.g., DE123456789)

Options:
  --no-email            Disable email notification (default: email enabled)
  --format [human|json] Output format (default: human)
  --recipient EMAIL     Email recipient (multiple allowed, uses config default)
  --profile NAME        Configuration profile
```

### 3.2 Exit Codes
| Code | Meaning |
|------|---------|
| 0 | UID is valid |
| 1 | UID is invalid |
| 2 | Configuration error |
| 3 | Authentication error |
| 4 | Query error |

### 3.3 Email Notification (Default Enabled)
**Content**:
- UID queried
- Status (VALID/INVALID)
- Return code and message
- Timestamp (UTC)
- Company name (if valid)
- Company address (if valid, 6 lines)
- Severity and retryable status

**Formats**: Plain text + HTML

---

## 4. Technical Architecture

### 4.1 Module Structure
```
src/uid_check_austria/
├── domain/                      # Pure domain layer (no I/O)
│   ├── __init__.py
│   ├── models.py               # Immutable dataclasses
│   ├── errors.py               # Domain exceptions
│   └── return_codes.py         # Return code enum + info
├── application/                 # Use cases + ports
│   ├── __init__.py
│   ├── ports.py                # Protocol definitions
│   └── use_cases.py            # CheckUidUseCase
├── adapters/                    # External integrations
│   ├── __init__.py
│   ├── finanzonline/
│   │   ├── __init__.py
│   │   ├── session_client.py   # SOAP session adapter
│   │   └── uid_query_client.py # SOAP query adapter
│   ├── notification/
│   │   ├── __init__.py
│   │   └── email_adapter.py    # Email notification
│   └── output/
│       ├── __init__.py
│       └── formatters.py       # Human/JSON formatters
├── cli.py                       # Add check command
├── config.py                    # Add FO config loader
└── defaultconfig.toml           # Add [finanzonline] section
```

### 4.2 Domain Models
```python
@dataclass(frozen=True, slots=True)
class FinanzOnlineCredentials:
    tid: str      # Participant ID
    benid: str    # User ID
    pin: str      # Password

@dataclass(frozen=True, slots=True)
class UidCheckRequest:
    uid_tn: str   # Own Austrian UID (ATU...)
    uid: str      # Target UID to verify
    stufe: int = 2

@dataclass(frozen=True, slots=True)
class Address:
    line1: str = ""
    line2: str = ""
    line3: str = ""
    line4: str = ""
    line5: str = ""
    line6: str = ""

@dataclass(frozen=True, slots=True)
class UidCheckResult:
    uid: str
    return_code: int
    message: str
    name: str = ""
    address: Address | None = None
    timestamp: datetime

    @property
    def is_valid(self) -> bool:
        return self.return_code == 0
```

### 4.3 Port Protocols
```python
class SessionPort(Protocol):
    def login(self, credentials: FinanzOnlineCredentials) -> SessionInfo: ...
    def logout(self, session_id: str, credentials: FinanzOnlineCredentials) -> bool: ...

class UidQueryPort(Protocol):
    def query(self, session_id: str, credentials: FinanzOnlineCredentials,
              request: UidCheckRequest) -> UidCheckResult: ...

class NotificationPort(Protocol):
    def send_result(self, result: UidCheckResult, recipients: list[str]) -> bool: ...
```

### 4.4 Use Case Flow
```python
class CheckUidUseCase:
    def execute(self, credentials, uid_tn, target_uid) -> UidCheckResult:
        # 1. Login to FinanzOnline
        session = self._session_client.login(credentials)
        try:
            # 2. Execute Level 2 query
            request = UidCheckRequest(uid_tn=uid_tn, uid=target_uid, stufe=2)
            result = self._query_client.query(session.session_id, credentials, request)
            return result
        finally:
            # 3. Always logout
            self._session_client.logout(session.session_id, credentials)
```

---

## 5. Configuration Schema

### 5.1 New Section: `[finanzonline]`
```toml
[finanzonline]
# Participant ID (Teilnehmer-ID) - REQUIRED
# tid = ""

# User ID (Benutzer-ID) - REQUIRED
# benid = ""

# Password/PIN - REQUIRED (use environment variable!)
# pin = ""

# Own Austrian UID (must start with ATU) - REQUIRED
# uid_tn = ""

# Timeouts in seconds
session_timeout = 30.0
query_timeout = 30.0

# Default email recipients for results
default_recipients = []
```

### 5.2 Environment Variable Format
```bash
UID_CHECK_AUSTRIA___FINANZONLINE__TID=123456789
UID_CHECK_AUSTRIA___FINANZONLINE__BENID=MYUSER
UID_CHECK_AUSTRIA___FINANZONLINE__PIN=secret
UID_CHECK_AUSTRIA___FINANZONLINE__UID_TN=ATU12345678
```

---

## 6. Dependencies

**Add to pyproject.toml**:
```toml
"zeep>=4.2.1",  # SOAP client for FinanzOnline webservices
```

---

## 7. Files to Create/Modify

### New Files
| File | Purpose |
|------|---------|
| `src/uid_check_austria/domain/__init__.py` | Domain package |
| `src/uid_check_austria/domain/models.py` | Immutable dataclasses |
| `src/uid_check_austria/domain/errors.py` | Domain exceptions |
| `src/uid_check_austria/domain/return_codes.py` | Return code enum |
| `src/uid_check_austria/application/__init__.py` | Application package |
| `src/uid_check_austria/application/ports.py` | Protocol definitions |
| `src/uid_check_austria/application/use_cases.py` | CheckUidUseCase |
| `src/uid_check_austria/adapters/__init__.py` | Adapters package |
| `src/uid_check_austria/adapters/finanzonline/__init__.py` | FO package |
| `src/uid_check_austria/adapters/finanzonline/session_client.py` | Session SOAP |
| `src/uid_check_austria/adapters/finanzonline/uid_query_client.py` | Query SOAP |
| `src/uid_check_austria/adapters/notification/__init__.py` | Notification pkg |
| `src/uid_check_austria/adapters/notification/email_adapter.py` | Email adapter |
| `src/uid_check_austria/adapters/output/__init__.py` | Output package |
| `src/uid_check_austria/adapters/output/formatters.py` | Output formatters |
| `tests/domain/test_models.py` | Domain model tests |
| `tests/domain/test_return_codes.py` | Return code tests |
| `tests/application/test_use_cases.py` | Use case tests |
| `tests/adapters/test_session_client.py` | Session adapter tests |
| `tests/adapters/test_uid_query_client.py` | Query adapter tests |
| `tests/adapters/test_email_adapter.py` | Email adapter tests |
| `tests/adapters/test_formatters.py` | Formatter tests |
| `docs/prd/prd.md` | This PRD document |

### Modified Files
| File | Changes |
|------|---------|
| `src/uid_check_austria/cli.py` | Add `check` command |
| `src/uid_check_austria/config.py` | Add `load_finanzonline_config()` |
| `src/uid_check_austria/defaultconfig.toml` | Add `[finanzonline]` section |
| `src/uid_check_austria/__init__.py` | Export new public API |
| `pyproject.toml` | Add zeep dependency, update import-linter |
| `tests/conftest.py` | Add FinanzOnline fixtures |

---

## 8. Test Strategy

### Unit Tests
- Domain models: immutability, property behavior
- Return codes: all mappings, unknown code handling
- Use cases: happy path, error paths (mock ports)
- Formatters: human/JSON output

### Adapter Tests
- Session client: login/logout with mocked zeep
- Query client: all return code scenarios with mocked zeep
- Email adapter: subject/body generation

### Integration Tests (Optional)
- Real FinanzOnline API (requires credentials via env vars)
- Skip in CI unless `TEST_FINANZONLINE_*` vars set

### CLI Tests
- `check` command with mocked use case
- `--no-email` flag behavior
- `--format json` output
- Exit code verification

---

## 9. Implementation Order

1. **Domain Layer** - models.py, errors.py, return_codes.py + tests
2. **Application Layer** - ports.py, use_cases.py + tests
3. **Adapters** - session_client.py, uid_query_client.py, email_adapter.py, formatters.py + tests
4. **CLI Integration** - Add `check` command, config loading
5. **Configuration** - Update defaultconfig.toml
6. **Final** - Integration tests, documentation, README examples

---

## 10. Sources

- [BMF UID-Abfrage Webservice PDF](https://www.bmf.gv.at/dam/jcr:e6acfe5b-f4a5-44f6-8a57-28256efdb850/BMF_UID_Abfrage_Webservice_2.pdf)
- [BMF Session Webservice PDF (German)](https://www.bmf.gv.at/dam/jcr:570753b2-d511-4194-a03e-33f0ac7371ec/BMF_Session_Webservice_2.pdf)
- [BMF Session Webservice PDF (English)](https://www.bmf.gv.at/dam/jcr:95d0e370-4efb-4ac9-9132-165189ac30ba/BMF_Session_Webservice_Englisch.pdf)
- Local: `docs/prd/BMF_UID_Abfrage_Webservice_2.pdf`
- Local: `docs/prd/uidAbfrageService.wsdl`
