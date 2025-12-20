# BMF Return Codes

> 🇩🇪 **[Deutsche Version verfügbar (RETURNCODES_de.md)](RETURNCODES_de.md)**

This document describes all return codes from the Austrian BMF (Federal Ministry of Finance) FinanzOnline web service.

---

## Session/Authentication Codes

These codes are returned during login and session management.

| Code | Meaning                                     | Severity | Retryable |
|------|---------------------------------------------|----------|-----------|
| 0    | Success                                     | success  | -         |
| -1   | Session invalid or expired                  | error    | No        |
| -2   | System maintenance                          | warning  | Yes       |
| -3   | Technical error                             | error    | Yes       |
| -4   | Access codes are not valid                  | critical | No        |
| -5   | User locked due to incorrect login attempts | critical | No        |
| -6   | User is locked                              | critical | No        |
| -7   | User is not a web service user              | critical | No        |
| -8   | Participant locked or not authorized        | critical | No        |

### Common Authentication Issues

- **Code -4 (Invalid access codes):** Check your TID, BENID, and PIN in the configuration.
- **Code -7 (Not a web service user):** The user must be configured as a web service user in FinanzOnline user administration.
- **Code -8 (Participant not authorized):** The participant must be enabled for web service usage.

---

## UID Query Codes

These codes are returned during UID verification (Level 2).

| Code | Meaning                                | Severity | Retryable |
|------|----------------------------------------|----------|-----------|
| 0    | UID is valid                           | success  | -         |
| 1    | UID is invalid                         | warning  | No        |
| 4    | Wrong UID format                       | error    | No        |
| 5    | Invalid requester UID                  | error    | No        |
| 10   | Member state forbids query             | warning  | No        |
| 11   | Not authorized for requester UID       | error    | No        |
| 12   | UID not yet queryable                  | warning  | Yes       |
| 101  | UID doesn't start with ATU             | error    | No        |
| 103  | VAT group (CZ) - special handling      | warning  | No        |
| 104  | VAT group (SK) - special handling      | warning  | No        |
| 105  | Must query via FinanzOnline portal     | error    | No        |
| 1511 | Service unavailable                    | critical | Yes       |
| 1512 | Too many queries (server load)         | warning  | Yes       |
| 1513 | Rate limit: 2 queries/UID/day exceeded | warning  | Yes       |
| 1514 | Rate limit: requester limit exceeded   | warning  | Yes       |

---

## Severity Levels

| Severity   | Description |
|------------|-------------|
| `success`  | Operation completed successfully |
| `warning`  | Warning - action may be required |
| `error`    | Error - request could not be processed |
| `critical` | Critical - check configuration or permissions |

---

## Retryable Errors

Errors with "Retryable: Yes" can be retried after a waiting period:

- **Code -2 (System maintenance):** Wait a few minutes and try again.
- **Code -3 (Technical error):** Temporary issue, retry later.
- **Code 12 (UID not yet queryable):** The UID was recently registered, retry later.
- **Code 1511 (Service unavailable):** Server overloaded or in maintenance.
- **Code 1512-1514 (Rate limits):** Wait until the next day or reduce query frequency.

---

## BMF Rate Limits

Since April 6, 2023, the following restrictions apply:

- **Maximum 2 queries per UID per day** per participant
- Exceeding this limit returns code `1513`

### Recommendations

1. Use the built-in caching (default: 48 hours)
2. Only query UIDs during actual business transactions
3. Avoid bulk queries for database validation
