# Python-API-Referenz

Dieses Dokument beschreibt die Python-API für `finanzonline_uid`.

## Öffentliche Exporte

```python
import finanzonline_uid

# Paket-Metadaten
finanzonline_uid.__version__    # "0.0.1"
finanzonline_uid.__title__      # "Python library and CLI..."
finanzonline_uid.__author__     # "bitranox"
finanzonline_uid.__url__        # "https://github.com/bitranox/finanzonline_uid"
```

---

## Konfiguration

### `get_config()`

Lädt die mehrschichtige Konfiguration aus allen Quellen.

```python
from finanzonline_uid.config import get_config

config = get_config()
# oder mit Profil
config = get_config(profile="production")
# oder mit benutzerdefiniertem Startverzeichnis für .env-Erkennung
config = get_config(start_dir="/path/to/project")
```

**Parameter:**

| Parameter   | Typ           | Standard | Beschreibung                              |
|-------------|---------------|----------|-------------------------------------------|
| `profile`   | `str \| None` | `None`   | Profilname für Umgebungsisolierung        |
| `start_dir` | `str \| None` | `None`   | Verzeichnis für .env-Dateierkennung       |

**Rückgabe:** `Config` - Unveränderliches Konfigurationsobjekt

---

### `FinanzOnlineConfig`

Konfiguration für die FinanzOnline-Verbindung.

```python
from finanzonline_uid.config import FinanzOnlineConfig, load_finanzonline_config

# Aus mehrschichtiger Konfiguration laden
config = get_config()
fo_config = load_finanzonline_config(config)
```

**Attribute:**

| Attribut              | Typ                       | Standard     | Beschreibung                                |
|-----------------------|---------------------------|--------------|---------------------------------------------|
| `credentials`         | `FinanzOnlineCredentials` | Erforderlich | Authentifizierungsdaten                     |
| `uid_tn`              | `str`                     | Erforderlich | Eigene österreichische UID (muss mit ATU beginnen) |
| `session_timeout`     | `float`                   | `30.0`       | Timeout für Session-Operationen (Sekunden)  |
| `query_timeout`       | `float`                   | `30.0`       | Timeout für Abfrage-Operationen (Sekunden)  |
| `default_recipients`  | `list[str] \| None`       | `None`       | Standard-E-Mail-Empfänger                   |
| `email_format`        | `EmailFormat`             | `BOTH`       | E-Mail-Body-Format                          |
| `cache_results_hours` | `float`                   | `48.0`       | Stunden für Cache gültiger Ergebnisse       |
| `cache_file`          | `Path \| None`            | `None`       | Pfad zur Cache-JSON-Datei                   |
| `ratelimit_queries`   | `int`                     | `50`         | Max. Abfragen im Zeitfenster                |
| `ratelimit_hours`     | `float`                   | `24.0`       | Gleitendes Zeitfenster in Stunden           |
| `ratelimit_file`      | `Path \| None`            | `None`       | Pfad zur Ratenlimit-Tracking-Datei          |

---

## Domain-Modelle

### `FinanzOnlineCredentials`

Authentifizierungsdaten für FinanzOnline-Webservices.

```python
from finanzonline_uid.domain.models import FinanzOnlineCredentials

credentials = FinanzOnlineCredentials(
    tid="123456789",      # Teilnehmer-ID (8-12 alphanumerisch)
    benid="WEBUSER",      # Benutzer-ID (5-12 Zeichen)
    pin="password123",    # Passwort (5-128 Zeichen)
    herstellerid="ATU12345678"  # Software-Hersteller UID (10-24 alphanumerisch)
)
```

**Validierungsregeln (gemäß login.xsd):**

| Feld           | Muster              | Beschreibung                   |
|----------------|---------------------|--------------------------------|
| `tid`          | 8-12 alphanumerisch | Teilnehmer-ID                  |
| `benid`        | 5-12 Zeichen        | Benutzer-ID                    |
| `pin`          | 5-128 Zeichen       | Passwort/PIN                   |
| `herstellerid` | 10-24 alphanumerisch| UID des Software-Herstellers   |

---

### `UidCheckRequest`

Anfrageparameter für Stufe-2-UID-Verifizierung.

```python
from finanzonline_uid.domain.models import UidCheckRequest

request = UidCheckRequest(
    uid_tn="ATU12345678",    # Eigene österreichische UID
    uid="DE987654321",       # Ziel-UID zur Verifizierung
    stufe=2                  # Abfragestufe (immer 2)
)
```

**Attribute:**

| Attribut  | Typ   | Standard     | Beschreibung                                   |
|-----------|-------|--------------|------------------------------------------------|
| `uid_tn`  | `str` | Erforderlich | Eigene österreichische UID (muss mit ATU beginnen) |
| `uid`     | `str` | Erforderlich | Ziel-EU-UID zur Verifizierung                  |
| `stufe`   | `int` | `2`          | Abfragestufe (nur 2 unterstützt)               |

---

### `UidCheckResult`

Vollständiges Ergebnis der Stufe-2-UID-Verifizierung.

```python
from finanzonline_uid.domain.models import UidCheckResult

# Beispiel-Ergebnis
result.uid           # "DE987654321"
result.return_code   # 0
result.message       # "gueltige UID"
result.name          # "Beispiel GmbH"
result.address       # Address-Objekt
result.timestamp     # datetime (UTC)
result.from_cache    # False (True wenn aus Cache)
result.cached_at     # None (oder ursprünglicher Abfragezeitpunkt wenn aus Cache)

# Properties
result.is_valid      # True wenn return_code == 0
result.is_invalid    # True wenn return_code == 1
result.has_company_info  # True wenn Name oder Adresse vorhanden
```

**Attribute:**

| Attribut      | Typ                | Standard    | Beschreibung                                    |
|---------------|--------------------|--------------|-------------------------------------------------|
| `uid`         | `str`              | Erforderlich | Die verifizierte UID                            |
| `return_code` | `int`              | Erforderlich | FinanzOnline-Rückgabecode                       |
| `message`     | `str`              | Erforderlich | Menschenlesbare Statusmeldung                   |
| `name`        | `str`              | `""`         | Firmenname (wenn UID gültig)                    |
| `address`     | `Address \| None`  | `None`       | Firmenadresse (wenn UID gültig)                 |
| `timestamp`   | `datetime`         | Jetzt (UTC)  | Wann die Verifizierung durchgeführt wurde       |
| `from_cache`  | `bool`             | `False`      | Ob das Ergebnis aus dem Cache stammt            |
| `cached_at`   | `datetime \| None` | `None`       | Ursprünglicher Abfragezeitstempel wenn aus Cache|

---

### `Address`

Firmenadresse aus der Stufe-2-UID-Verifizierung.

```python
from finanzonline_uid.domain.models import Address

address = Address(
    line1="Beispiel GmbH",
    line2="Hauptstraße 1",
    line3="1010 Wien",
    line4="",
    line5="",
    line6=""
)

# Methoden
address.as_lines()  # ["Beispiel GmbH", "Hauptstraße 1", "1010 Wien"]
address.as_text()   # "Beispiel GmbH\nHauptstraße 1\n1010 Wien"
address.as_text(", ")  # "Beispiel GmbH, Hauptstraße 1, 1010 Wien"
address.is_empty    # False
```

**Attribute:**

| Attribut          | Typ   | Standard | Beschreibung       |
|-------------------|-------|----------|--------------------|
| `line1` - `line6` | `str` | `""`     | Adresszeilen 1-6   |

---

## Use Cases

### `CheckUidUseCase`

Haupt-Use-Case für die Ausführung der Stufe-2-UID-Verifizierung.

```python
from finanzonline_uid.application.use_cases import CheckUidUseCase
from finanzonline_uid.adapters.finanzonline import (
    FinanzOnlineSessionClient,
    FinanzOnlineQueryClient
)
from finanzonline_uid.domain.models import FinanzOnlineCredentials

# Clients erstellen
session_client = FinanzOnlineSessionClient(timeout=30.0)
query_client = FinanzOnlineQueryClient(timeout=30.0)

# Use Case erstellen
use_case = CheckUidUseCase(session_client, query_client)

# Verifizierung ausführen
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

print(f"Gültig: {result.is_valid}")
print(f"Firma: {result.name}")
```

**Parameter für `execute()`:**

| Parameter     | Typ                       | Beschreibung                 |
|---------------|---------------------------|------------------------------|
| `credentials` | `FinanzOnlineCredentials` | Authentifizierungsdaten      |
| `uid_tn`      | `str`                     | Eigene österreichische UID   |
| `target_uid`  | `str`                     | Ziel-UID zur Verifizierung   |

**Rückgabe:** `UidCheckResult`

**Wirft:**
- `SessionError` - Login oder Session-Verwaltung fehlgeschlagen
- `QueryError` - UID-Abfrageausführung fehlgeschlagen
- `ValueError` - Ungültige Anfrageparameter

---

## E-Mail-Funktionen

### `EmailConfig`

E-Mail-Konfigurationscontainer.

```python
from finanzonline_uid.mail import EmailConfig

config = EmailConfig(
    smtp_hosts=["smtp.beispiel.at:587"],
    from_address="alerts@beispiel.at",
    smtp_username="benutzer@beispiel.at",  # Optional
    smtp_password="passwort",               # Optional
    use_starttls=True,
    timeout=30.0,
    raise_on_missing_attachments=True,
    raise_on_invalid_recipient=True,
    default_recipients=["admin@beispiel.at"]
)
```

**Attribute:**

| Attribut                       | Typ           | Standard              | Beschreibung                         |
|--------------------------------|---------------|-----------------------|--------------------------------------|
| `smtp_hosts`                   | `list[str]`   | `[]`                  | SMTP-Server im 'host:port'-Format    |
| `from_address`                 | `str`         | `"noreply@localhost"` | Standard-Absenderadresse             |
| `smtp_username`                | `str \| None` | `None`                | SMTP-Authentifizierungsbenutzername  |
| `smtp_password`                | `str \| None` | `None`                | SMTP-Authentifizierungspasswort      |
| `use_starttls`                 | `bool`        | `True`                | STARTTLS aktivieren                  |
| `timeout`                      | `float`       | `30.0`                | Socket-Timeout (Sekunden)            |
| `raise_on_missing_attachments` | `bool`        | `True`                | Exception bei fehlenden Dateien      |
| `raise_on_invalid_recipient`   | `bool`        | `True`                | Exception bei ungültigen Adressen    |
| `default_recipients`           | `list[str]`   | `[]`                  | Standard-Empfänger                   |

---

### `send_email()`

Sendet eine E-Mail mit konfigurierten SMTP-Einstellungen.

```python
from finanzonline_uid.mail import EmailConfig, send_email
from pathlib import Path

config = EmailConfig(
    smtp_hosts=["smtp.beispiel.at:587"],
    from_address="alerts@beispiel.at"
)

send_email(
    config=config,
    recipients=["benutzer@beispiel.at"],
    subject="Test-E-Mail",
    body="Klartext-Inhalt",
    body_html="<h1>HTML-Inhalt</h1>",  # Optional
    from_address="override@beispiel.at",  # Optional
    attachments=[Path("bericht.pdf")]  # Optional
)
```

**Parameter:**

| Parameter      | Typ                      | Standard     | Beschreibung           |
|----------------|--------------------------|--------------|------------------------|
| `config`       | `EmailConfig`            | Erforderlich | E-Mail-Konfiguration   |
| `recipients`   | `str \| Sequence[str]`   | Erforderlich | Empfängeradresse(n)    |
| `subject`      | `str`                    | Erforderlich | E-Mail-Betreff         |
| `body`         | `str`                    | `""`         | Klartext-Body          |
| `body_html`    | `str`                    | `""`         | HTML-Body              |
| `from_address` | `str \| None`            | `None`       | Absender überschreiben |
| `attachments`  | `Sequence[Path] \| None` | `None`       | Dateipfade für Anhänge |

**Rückgabe:** `bool` - True bei Erfolg

**Wirft:**
- `ValueError` - Keine gültigen Empfänger
- `FileNotFoundError` - Fehlender Anhang
- `RuntimeError` - Alle SMTP-Hosts fehlgeschlagen

---

### `send_notification()`

Sendet eine einfache Klartext-Benachrichtigungs-E-Mail.

```python
from finanzonline_uid.mail import EmailConfig, send_notification

config = EmailConfig(
    smtp_hosts=["smtp.beispiel.at:587"],
    from_address="alerts@beispiel.at"
)

send_notification(
    config=config,
    recipients="admin@beispiel.at",
    subject="Systemwarnung",
    message="Backup erfolgreich abgeschlossen"
)
```

**Parameter:**

| Parameter    | Typ                    | Standard     | Beschreibung           |
|--------------|------------------------|--------------|------------------------|
| `config`     | `EmailConfig`          | Erforderlich | E-Mail-Konfiguration   |
| `recipients` | `str \| Sequence[str]` | Erforderlich | Empfängeradresse(n)    |
| `subject`    | `str`                  | Erforderlich | Betreffzeile           |
| `message`    | `str`                  | Erforderlich | Benachrichtigungstext  |

**Rückgabe:** `bool` - True bei Erfolg

---

### `load_email_config_from_dict()`

Lädt EmailConfig aus einem Konfigurations-Dictionary.

```python
from finanzonline_uid.mail import load_email_config_from_dict
from finanzonline_uid.config import get_config

config = get_config()
email_config = load_email_config_from_dict(config.as_dict())
```

---

## Exceptions

Alle Domain-Exceptions erben von `UidCheckError`:

```python
from finanzonline_uid.domain.errors import (
    UidCheckError,           # Basis-Exception
    ConfigurationError,      # Fehlende oder ungültige Konfiguration
    AuthenticationError,     # Login/Zugangsdaten-Fehler
    SessionError,            # Session-Verwaltungsfehler
    QueryError,              # UID-Abfrageausführungsfehler
)
```

| Exception             | Attribute                                            | Beschreibung                                  |
|-----------------------|------------------------------------------------------|-----------------------------------------------|
| `UidCheckError`       | `message`                                            | Basis-Exception für alle UID-Prüfungsfehler   |
| `ConfigurationError`  | `message`                                            | Fehlende oder ungültige Konfiguration         |
| `AuthenticationError` | `message`, `return_code`, `diagnostics`              | Login fehlgeschlagen                          |
| `SessionError`        | `message`, `return_code`, `diagnostics`              | Session-Verwaltung fehlgeschlagen             |
| `QueryError`          | `message`, `return_code`, `retryable`, `diagnostics` | Abfrageausführung fehlgeschlagen              |

---

## Rückgabecode-Hilfsfunktionen

```python
from finanzonline_uid.domain.return_codes import (
    get_return_code_info,
    is_success,
    is_retryable,
    Severity,
    ReturnCodeInfo
)

# Informationen über einen Rückgabecode abrufen
info = get_return_code_info(0)
print(info.code)       # 0
print(info.meaning)    # "UID ist gültig"
print(info.severity)   # Severity.SUCCESS
print(info.retryable)  # False

# Schnellprüfungen
is_success(0)      # True
is_retryable(1513) # True (Ratenlimit)
```
