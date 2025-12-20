# Konfiguration

Dieses Dokument beschreibt alle Konfigurationsoptionen für `finanzonline_uid`.

## Konfigurationsmethoden

Die Konfiguration kann über mehrere Quellen bereitgestellt werden. Spätere Quellen überschreiben frühere:

| Priorität | Quelle   | Beschreibung                                           |
|-----------|----------|--------------------------------------------------------|
| 1         | defaults | Mitgelieferte `defaultconfig.toml`                     |
| 2         | app      | Systemweite Anwendungskonfiguration                    |
| 3         | host     | Host-spezifische Konfiguration                         |
| 4         | user     | Benutzerspezifische Konfiguration                      |
| 5         | .env     | Umgebungsdatei im aktuellen/übergeordneten Verzeichnis |
| 6         | env vars | Umgebungsvariablen (höchste Priorität)                 |

**Benennung von Umgebungsvariablen:**

```bash
# .env-Dateiformat (kein Präfix erforderlich)
SECTION__KEY=value

# Shell-Umgebungsvariablenformat (erfordert Präfix)
FINANZONLINE_UID___SECTION__KEY=value
```

**Speicherorte der Konfigurationsdateien:**

| Ziel   | Linux                                          | macOS                                                       | Windows                                     |
|--------|------------------------------------------------|-------------------------------------------------------------|---------------------------------------------|
| `user` | `~/.config/finanzonline-uid/`                 | `~/Library/Application Support/bitranox/FinanzOnline UID/` | `%APPDATA%\bitranox\FinanzOnline UID\`     |
| `app`  | `/etc/xdg/finanzonline-uid/`                  | `/Library/Application Support/bitranox/FinanzOnline UID/`  | `%PROGRAMDATA%\bitranox\FinanzOnline UID\` |
| `host` | `/etc/finanzonline-uid/hosts/{hostname}.toml` | Wie app                                                     | Wie app                                     |

**Konfigurationsverzeichnisstruktur:**

Jedes Konfigurationsverzeichnis unterstützt ein `config.d/`-Unterverzeichnis für modulare Konfigurationsfragmente:

```
~/.config/finanzonline-uid/           # Benutzerkonfigurationsverzeichnis (Linux)
├── config.toml                        # Hauptkonfigurationsdatei
└── config.d/                          # Fragment-Verzeichnis (in Sortierreihenfolge geladen)
    ├── 20-email.toml                  # E-Mail-Einstellungen
    └── 30-logging.toml                # Logging-Einstellungen
```

Fragment-Dateien werden in alphabetischer/numerischer Reihenfolge geladen und **tief zusammengeführt** mit der Hauptkonfiguration. Verwenden Sie numerische Präfixe (z.B. `20-`, `30-`), um die Ladereihenfolge zu steuern. Spätere Dateien überschreiben frühere.

**Vorteil der tiefen Zusammenführung:**

Einstellungen werden tief zusammengeführt, sodass Sie spezifische Werte überschreiben können, ohne ganze Abschnitte zu duplizieren. Erstellen Sie eine hochnummerierte Datei wie `99-myconfig.toml` für Ihre Anpassungen:

```toml
# config.d/99-myconfig.toml - Ihre persönlichen Überschreibungen
[finanzonline]
tid = "123456789"
benid = "MEINUSER"
pin = "geheimespasswort"
uid_tn = "ATU12345678"
herstellerid = "ATU12345678"
default_recipients = ["ich@beispiel.at"]

[email]
smtp_hosts = ["smtp.meinefirma.at:587"]
```

Dieses Muster gewährleistet problemlose Updates - wenn Standardkonfigurationen (`20-email.toml`, `30-logging.toml`) mit neuen Funktionen aktualisiert werden, bleiben Ihre Anpassungen in `99-myconfig.toml` intakt und überschreiben nur die spezifischen Werte, die Sie gesetzt haben.

**Standard-Fragmente (mit Paket geliefert):**

| Datei             | Inhalt                             |
|-------------------|------------------------------------|
| `20-email.toml`   | SMTP- und E-Mail-Einstellungen     |
| `30-logging.toml` | lib_log_rich Logging-Konfiguration |

---

## Spracheinstellungen

Alle benutzerorientierten Meldungen, CLI-Ausgaben und E-Mail-Benachrichtigungen können in mehreren Sprachen angezeigt werden.

| Schlüssel      | Typ   | Standard | Beschreibung                                     |
|----------------|-------|----------|--------------------------------------------------|
| `app.language` | `str` | `"en"`   | Sprachcode für Meldungen und E-Mail-Inhalte      |

**Unterstützte Sprachen:**

| Code | Sprache            |
|------|--------------------|
| `en` | Englisch (Standard)|
| `de` | Deutsch            |
| `es` | Spanisch (Español) |
| `fr` | Französisch        |
| `ru` | Russisch (Русский) |

**Was wird übersetzt:**
- CLI-Ausgabe (Statusmeldungen, Fehlermeldungen, Eingabeaufforderungen)
- E-Mail-Benachrichtigungen (Betreffzeilen, Textinhalt, Beschriftungen)
- BMF-Rückgabecode-Beschreibungen
- Alle benutzerorientierten Beschriftungen und Meldungen
- Weitere Sprachen auf Anfrage

**Konfigurationsbeispiele:**

```toml
# config.toml
[app]
language = "de"
```

```bash
# .env-Datei
APP__LANGUAGE=de
```

---

## FinanzOnline-Einstellungen

Authentifizierungsdaten für den FinanzOnline-Webservice.

| Schlüssel                         | Typ         | Standard     | Beschreibung                                              |
|-----------------------------------|-------------|--------------|-----------------------------------------------------------|
| `finanzonline.tid`                | `str`       | Erforderlich | Teilnehmer-ID (8-12 alphanumerisch)                       |
| `finanzonline.benid`              | `str`       | Erforderlich | Benutzer-ID (5-12 Zeichen, muss Webservice-Benutzer sein) |
| `finanzonline.pin`                | `str`       | Erforderlich | Passwort (5-128 Zeichen)                                  |
| `finanzonline.uid_tn`             | `str`       | Erforderlich | Eigene österreichische UID (muss mit ATU beginnen)        |
| `finanzonline.herstellerid`       | `str`       | Erforderlich | Software-Hersteller UID (10-24 alphanumerisch)            |
| `finanzonline.session_timeout`    | `float`     | `30.0`       | Session-Timeout in Sekunden                               |
| `finanzonline.query_timeout`      | `float`     | `30.0`       | Abfrage-Timeout in Sekunden                               |
| `finanzonline.default_recipients` | `list[str]` | `[]`         | Standard-E-Mail-Empfänger für Benachrichtigungen          |
| `finanzonline.email_format`       | `str`       | `"both"`     | E-Mail-Format: `html`, `plain` oder `both`                |

**.env-Beispiel:**
```bash
FINANZONLINE__TID=123456789
FINANZONLINE__BENID=WEBUSER
FINANZONLINE__PIN=geheimespasswort
FINANZONLINE__UID_TN=ATU12345678
FINANZONLINE__HERSTELLERID=ATU12345678
FINANZONLINE__SESSION_TIMEOUT=60.0
FINANZONLINE__DEFAULT_RECIPIENTS=["admin@beispiel.at"]
```

---

## Caching-Einstellungen

Ergebnis-Caching reduziert redundante API-Aufrufe, indem gültige UID-Verifizierungsergebnisse lokal gespeichert werden.

| Schlüssel                          | Typ     | Standard            | Beschreibung                                            |
|------------------------------------|---------|---------------------|---------------------------------------------------------|
| `finanzonline.cache_results_hours` | `float` | `48.0`              | Stunden für Cache gültiger Ergebnisse (0 = deaktiviert) |
| `finanzonline.cache_file`          | `str`   | Plattformspezifisch | Pfad zur Cache-JSON-Datei                               |

**Standard-Cache-Dateispeicherorte:**
- Linux: `~/.cache/finanzonline-uid/uid_cache.json`
- macOS: `~/Library/Caches/finanzonline-uid/uid_cache.json`
- Windows: `%LOCALAPPDATA%/finanzonline-uid/uid_cache.json`

**Hinweise:**
- Nur gültige Ergebnisse (return_code=0) werden gecacht
- Gecachte Ergebnisse enthalten den ursprünglichen Abfragezeitstempel in E-Mail-Benachrichtigungen
- Verwendet Dateisperren für sicheren gleichzeitigen Zugriff auf Netzlaufwerken
- Das Caching ermöglicht UID-Prüfungen bei verschiedenen Vorgängen wie Auftragserfassung, Fakturierung, Zahlungseingang - ohne Limits zu erreichen

**.env-Beispiel:**
```bash
FINANZONLINE__CACHE_RESULTS_HOURS=48
FINANZONLINE__CACHE_FILE=/shared/network/uid_cache.json
```

---

## Ratenlimit-Einstellungen

Integriertes Ratenlimit-Tracking warnt, wenn die API-Nutzung sich den Limits nähert. Dies ist eine lokale Schutzmaßnahme - die tatsächliche Ratenbegrenzung wird von den BMF-Servern durchgesetzt.

| Schlüssel                        | Typ     | Standard           | Beschreibung                                             |
|----------------------------------|---------|--------------------|----------------------------------------------------------|
| `finanzonline.ratelimit_queries` | `int`   | `50`               | Max. Abfragen im Zeitfenster (0 = Tracking deaktiviert)  |
| `finanzonline.ratelimit_hours`   | `float` | `24.0`             | Gleitendes Zeitfenster in Stunden                        |
| `finanzonline.ratelimit_file`    | `str`   | Plattformspezifisch| Pfad zur Ratenlimit-Tracking-JSON-Datei                  |

**Standard-Ratenlimit-Dateispeicherorte:**
- Linux: `~/.cache/finanzonline-uid/rate_limits.json`
- macOS: `~/Library/Caches/finanzonline-uid/rate_limits.json`
- Windows: `%LOCALAPPDATA%/finanzonline-uid/rate_limits.json`

**Verhalten bei Limit-Überschreitung:**
- Protokolliert eine Warnmeldung
- Sendet eine E-Mail-Benachrichtigung mit Fair-Use-Richtlinien-Hinweis
- **Abfrage wird trotzdem durchgeführt** - BMF führt die eigentliche Durchsetzung durch

**Hinweise:**
- Cache-Treffer zählen nicht zum Ratenlimit (nur tatsächliche API-Aufrufe)
- Sowohl erfolgreiche als auch fehlgeschlagene API-Aufrufe werden verfolgt
- Verwendet Dateisperren für sicheren gleichzeitigen Zugriff

**.env-Beispiel:**
```bash
FINANZONLINE__RATELIMIT_QUERIES=50
FINANZONLINE__RATELIMIT_HOURS=24.0
FINANZONLINE__RATELIMIT_FILE=/shared/network/rate_limits.json
```

---

## E-Mail-Einstellungen

SMTP-Konfiguration für das Senden von Benachrichtigungs-E-Mails.

| Schlüssel                  | Typ           | Standard              | Beschreibung                          |
|----------------------------|---------------|-----------------------|---------------------------------------|
| `email.smtp_hosts`         | `list[str]`   | `[]`                  | SMTP-Server (der Reihe nach versucht) |
| `email.from_address`       | `str`         | `"noreply@localhost"` | Absenderadresse                       |
| `email.smtp_username`      | `str \| None` | `None`                | SMTP-Benutzername                     |
| `email.smtp_password`      | `str \| None` | `None`                | SMTP-Passwort                         |
| `email.use_starttls`       | `bool`        | `True`                | STARTTLS aktivieren                   |
| `email.timeout`            | `float`       | `30.0`                | Verbindungs-Timeout                   |
| `email.default_recipients` | `list[str]`   | `[]`                  | Standard-Empfänger                    |

**.env-Beispiel:**
```bash
EMAIL__SMTP_HOSTS=["smtp.gmail.com:587"]
EMAIL__FROM_ADDRESS=alerts@beispiel.at
EMAIL__SMTP_USERNAME=benutzer@gmail.com
EMAIL__SMTP_PASSWORD=app-passwort
EMAIL__USE_STARTTLS=true
EMAIL__TIMEOUT=60.0
EMAIL__DEFAULT_RECIPIENTS=["admin@beispiel.at"]
```

---

## Logging-Einstellungen

Alle Logging-Einstellungen verwenden lib_layered_config-Benennung:

| Schlüssel                            | Typ   | Standard     | Beschreibung                                  |
|--------------------------------------|-------|--------------|-----------------------------------------------|
| `lib_log_rich.console_level`         | `str` | `"INFO"`     | Konsolen-Loglevel                             |
| `lib_log_rich.console_format_preset` | `str` | `"full"`     | Format: full, short, full_loc, short_loc      |
| `lib_log_rich.service`               | `str` | Paketname    | Dienstname in Logs                            |
| `lib_log_rich.environment`           | `str` | `"prod"`     | Umgebungskennzeichnung                        |

**.env-Beispiel:**
```bash
LIB_LOG_RICH__CONSOLE_LEVEL=DEBUG
LIB_LOG_RICH__CONSOLE_FORMAT_PRESET=short
```
