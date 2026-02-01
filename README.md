# finanzonline_uid

<!-- Badges -->
[![CI](https://github.com/bitranox/finanzonline_uid/actions/workflows/default_cicd_public.yml/badge.svg)](https://github.com/bitranox/finanzonline_uid/actions/workflows/default_cicd_public.yml)
[![CodeQL](https://github.com/bitranox/finanzonline_uid/actions/workflows/codeql.yml/badge.svg)](https://github.com/bitranox/finanzonline_uid/actions/workflows/codeql.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Open in Codespaces](https://img.shields.io/badge/Codespaces-Open-blue?logo=github&logoColor=white&style=flat-square)](https://codespaces.new/bitranox/finanzonline_uid?quickstart=1)
[![PyPI](https://img.shields.io/pypi/v/finanzonline_uid.svg)](https://pypi.org/project/finanzonline_uid/)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/finanzonline_uid.svg)](https://pypi.org/project/finanzonline_uid/)
[![Code Style: Ruff](https://img.shields.io/badge/Code%20Style-Ruff-46A3FF?logo=ruff&labelColor=000)](https://docs.astral.sh/ruff/)
[![codecov](https://codecov.io/gh/bitranox/finanzonline_uid/graph/badge.svg?token=UFBaUDIgRk)](https://codecov.io/gh/bitranox/finanzonline_uid)
[![Maintainability](https://qlty.sh/badges/041ba2c1-37d6-40bb-85a0-ec5a8a0aca0c/maintainability.svg)](https://qlty.sh/gh/bitranox/projects/finanzonline_uid)
[![Known Vulnerabilities](https://snyk.io/test/github/bitranox/finanzonline_uid/badge.svg)](https://snyk.io/test/github/bitranox/finanzonline_uid)
[![security: bandit](https://img.shields.io/badge/security-bandit-yellow.svg)](https://github.com/PyCQA/bandit)

> 🇬🇧 **[English version available (README_en.md)](README_en.md)**

`finanzonline_uid` ist eine Python-Bibliothek und CLI zur Abfrage von **Stufe 2 UID-Prüfungen** (Umsatzsteuer-Identifikationsnummer-Verifizierung) über den österreichischen FinanzOnline-Webservice. Stufe-2-Abfragen liefern detaillierte Bestätigungen von EU-Umsatzsteuer-Identifikationsnummern einschließlich des registrierten Firmennamens und der Adresse.

## Warum finanzonline_uid?

Die Verifizierung von UID-Nummern über das FinanzOnline-Webportal erfordert Anmeldung, Navigation durch Menüs und manuelle Dateneingabe - mühsam und nicht automatisierbar. Mit `finanzonline_uid`:

- **Kein Browser erforderlich** - läuft vollständig über die Kommandozeile oder per Windows-Icon.
- **Vollständig skriptfähig** - Integration in Fakturierungssysteme, Batch-Prozesse oder CI-Pipelines.
- **E-Mail-Benachrichtigungen** - automatische Bestätigungs-E-Mails mit Prüfergebnissen.
- **Ergebnis-Caching** - Vermeidung redundanter API-Aufrufe durch konfigurierbare Zwischenspeicherung.
- **Ratenlimit-Schutz** - integriertes Tracking mit E-Mail-Warnungen bei Annäherung an Limits.
- **Einfache Bedienung** - einfach die zu prüfende UID übergeben und sofort Ergebnisse erhalten.
- **FREIE SOFTWARE** - diese Software ist und bleibt kostenlos. Bei Bedarf an Installation oder Support kann dieser beim Autor gebucht werden.

**Funktionen:**
- Abfrage von FinanzOnline für Stufe-2-UID-Verifizierung
- CLI-Einstiegspunkt mit rich-click (rich-Ausgabe + click-Ergonomie)
- Automatische E-Mail-Benachrichtigungen mit HTML-Formatierung (standardmäßig aktiviert)
- **Mehrsprachige Unterstützung** - Englisch, Deutsch, Spanisch, Französisch, Russisch
- Menschenlesbare und JSON-Ausgabeformate
- **Dateiausgabe** - gültige Ergebnisse als Textdateien speichern (`--outputdir`)
- Ergebnis-Caching mit konfigurierbarer TTL (Standard: 48 Stunden)
- Ratenlimit-Tracking mit Warn-E-Mails
- **UID-Eingabe-Bereinigung** - automatische Entfernung von Copy-Paste-Artefakten (Leerzeichen, unsichtbare Zeichen)
- **Wiederholungsmodus** - automatische Wiederholung bei temporären Fehlern mit animiertem Countdown
- Mehrschichtiges Konfigurationssystem mit lib_layered_config
- Strukturiertes Logging mit lib_log_rich
- Exit-Code- und Meldungshelfer durch lib_cli_exit_tools

**Zukünftige Entwicklung:**
- in Kürze: Automatischer Download von Bestätigungsdokumenten aus Ihrer **FinanzOnline Databox**. Dies **MÜSSEN** Sie derzeit manuell erledigen - siehe **Aufbewahrungspflichten**
- benötigen Sie weitere Funktionalität, zögern Sie nicht uns zu kontaktieren.

**Beispiel:**
```bash
# Beispiel: eine UID verifizieren
finanzonline_uid check DE123456789
```

---

## Fair-Use-Richtlinie

> **Wie sollte der UID-Verifizierungsdienst richtig verwendet werden?**
>
> UID-Verifizierungen sollten nur zum Zeitpunkt der innergemeinschaftlichen steuerfreien Lieferungen oder sonstigen Leistungen an Kunden in anderen EU-Mitgliedstaaten angefordert werden - nicht im Voraus oder in großen Mengen. Das dauerhafte Abfragen aller UID-Nummern in Ihrer Datenbank stellt keine faire Nutzung dar.
>
> **Bitte unterlassen Sie unnötige UID-Verifizierungsanfragen.**

### BMF-Ratenlimits

Seit 6. April 2023 kann **jede UID-Nummer nur zweimal pro Tag pro Teilnehmer** über den Webservice abgefragt werden. Überschreitung dieses Limits liefert Code `1513`.

### Lokales Ratenlimit-Tracking

Dieses Tool enthält integriertes Ratenlimit-Tracking (Standard: 50 Abfragen pro 24 Stunden), das:
- Warnt, bevor Sie BMF-Limits erreichen
- E-Mail-Benachrichtigungen bei Überschreitung sendet
- Erfolgreiche Abfragen werden lokal zwischengespeichert, um versehentliche Limit-Überschreitungen zu vermeiden
- Abfragen werden NICHT blockiert - das BMF führt die eigentliche Durchsetzung durch

Konfiguration über `finanzonline.ratelimit_queries` und `finanzonline.ratelimit_hours`.

### FinanzOnline Webservice-Benutzer

> **WICHTIG:** Der Benutzer (BENID) muss in der FinanzOnline-Benutzerverwaltung als **Webservice-Benutzer** konfiguriert sein.
>
> Häufige Fehler:
> - `-4` = Ungültige Zugangsdaten
> - `-7` = Benutzer ist kein Webservice-Benutzer
> - `-8` = Teilnehmer gesperrt oder nicht für Webservice autorisiert

### Bestätigungsdokumente (Aufbewahrungspflichten)

> **WICHTIG:** Das offizielle Bestätigungsdokument wird am **folgenden Tag in Ihre FinanzOnline Databox** zugestellt.
>
> Dieses Dokument muss gemäß § 132 BAO (Bundesabgabenordnung) **ausgedruckt und als Nachweis** der UID-Verifizierung aufbewahrt werden.

Der ausgedruckte Beleg dient als offizielle Dokumentation für Steuerprüfungen und muss gemäß den österreichischen Aufbewahrungsvorschriften aufbewahrt werden (üblicherweise 7 Jahre).

**Automatischer Download:** Die Bestätigungsdokumente können automatisch aus der FinanzOnline Databox heruntergeladen werden mit [finanzonline_databox](https://github.com/bitranox/finanzonline_databox) (auch auf [PyPI](https://pypi.org/project/finanzonline_databox/) verfügbar).

---

## Inhaltsverzeichnis

- [Fair-Use-Richtlinie](#fair-use-richtlinie)
- [Schnellstart](#schnellstart)
- [Verwendung](#verwendung)
- [BMF-Rückgabecodes](#bmf-rückgabecodes)
- [Weitere Dokumentation](#weitere-dokumentation)

---

## Schnellstart

Ihr IT-Personal sollte diese Anwendung problemlos installieren können. Bei Bedarf an Support können Sie den Autor für bezahlten Support kontaktieren.


### Empfohlen: Ausführung via uvx für automatisch die neueste Version

UV - der ultraschnelle Installer - geschrieben in Rust (10-20x schneller als pip/poetry)

```bash
# Python installieren (erfordert >= **Python 3.10+**)
# UV installieren
pip install --upgrade uv
# Konfigurationsdateien erstellen
uvx finanzonline_uid@latest config-deploy --target user
```

Erstellen Sie Ihre persönliche Konfigurationsdatei im `config.d/`-Verzeichnis (Einstellungen werden tief zusammengeführt, sodass Updates der Standardkonfigurationen Ihre Einstellungen nicht beeinflussen):

```bash
# Linux:   ~/.config/finanzonline-uid/config.d/99-myconfig.toml
# macOS:   ~/Library/Application Support/bitranox/FinanzOnline UID/config.d/99-myconfig.toml
# Windows: %APPDATA%\bitranox\FinanzOnline UID\config.d\99-myconfig.toml
```

```toml
# 99-myconfig.toml - Ihre persönlichen Einstellungen
[finanzonline]
tid = "123456789"           # Teilnehmer-ID
benid = "WEBUSER"           # Benutzer-ID - muss Webservice-Benutzer sein!
pin = "yourpassword"        # Passwort/PIN
uid_tn = "ATU12345678"      # Ihre österreichische UID (muss mit "ATU" beginnen)
herstellerid = "ATU12345678" # Software-Hersteller UID (Ihre österreichische UID eintragen)
default_recipients = ["buchhaltung@ihre-firma.at"]

[email]
smtp_hosts = ["smtp.beispiel.at:587"]
from_address = "uidcheck@ihre-firma.at"
```

```bash
# Neueste Version ohne weitere Installation starten
uvx finanzonline_uid@latest check DE123456789
```

Für alternative Installationswege (pip, pipx, uvx, Source-Builds) siehe [INSTALL_de.md](INSTALL_de.md).

---

## Verwendung

```bash
# Prüfung per Kommandozeile
uvx finanzonline_uid@latest check NL123456789

# Interaktive Prüfung (fragt nach der zu prüfenden UID):
uvx finanzonline_uid@latest check --interactive

# Wiederholungsmodus: bei temporären Fehlern alle 5 Minuten wiederholen
uvx finanzonline_uid@latest check --interactive --retryminutes 5
```

Die Ergebnisse werden angezeigt und eine E-Mail mit den Ergebnissen wird an die konfigurierten E-Mail-Adressen gesendet.

### UID-Eingabe-Bereinigung

UID-Nummern werden automatisch von Copy-Paste-Artefakten bereinigt:
- Leerzeichen, Tabs und Zeilenumbrüche werden entfernt
- Unsichtbare Zeichen (Zero-Width-Spaces, BOM) werden entfernt
- Automatische Umwandlung in Großbuchstaben

Beispiel: `"  de 123 456 789  "` wird zu `"DE123456789"`

### Wiederholungsmodus

Mit `--retryminutes` können Sie bei temporären Fehlern (Netzwerk, Rate-Limit) automatisch wiederholen lassen:

```bash
# Alle 5 Minuten wiederholen bis Erfolg oder Abbruch mit Ctrl+C
finanzonline-uid check --interactive --retryminutes 5
```

- Animierter Countdown zeigt Zeit bis zum nächsten Versuch
- E-Mail wird nur bei Erfolg oder endgültigem Fehler gesendet
- Bei dauerhaften Fehlern (ungültige UID, Authentifizierung) wird sofort abgebrochen

---

## BMF-Rückgabecodes

Eine vollständige Liste aller BMF-Rückgabecodes finden Sie in der **[Rückgabecode-Referenz (RETURNCODES_de.md)](RETURNCODES_de.md)**.

---

## Weitere Dokumentation

- [Installationsanleitung (DE)](INSTALL_de.md) | [Installation Guide (EN)](INSTALL_en.md)
- [Konfigurationsreferenz (DE)](CONFIGURATION_de.md) | [Configuration Reference (EN)](CONFIGURATION_en.md)
- [CLI-Referenz (DE)](CLI_REFERENCE_de.md) | [CLI Reference (EN)](CLI_REFERENCE_en.md)
- [Python-API-Referenz (DE)](API_REFERENCE_de.md) | [Python API Reference (EN)](API_REFERENCE_en.md)
- [BMF-Rückgabecodes (DE)](RETURNCODES_de.md) | [BMF Return Codes (EN)](RETURNCODES_en.md)
- [Entwicklungshandbuch](DEVELOPMENT.md)
- [Contributor-Leitfaden](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)
- [Modulreferenz](docs/systemdesign/module_reference.md)
- [Lizenz](LICENSE)
