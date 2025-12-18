# CLI-Referenz

Dieses Dokument beschreibt alle CLI-Befehle und Optionen für `uid_check_austria`.

## Globale Optionen

Diese Optionen gelten für alle Befehle:

| Option                         | Standard         | Beschreibung                                                           |
|--------------------------------|------------------|------------------------------------------------------------------------|
| `--traceback / --no-traceback` | `--no-traceback` | Vollständigen Python-Traceback bei Fehlern anzeigen                    |
| `--profile NAME`               | `None`           | Konfiguration aus benanntem Profil laden (z.B. 'production', 'test')   |
| `--version`                    | -                | Version anzeigen und beenden                                           |
| `-h, --help`                   | -                | Hilfe anzeigen und beenden                                             |

## Befehle

Der CLI-Befehl ist unter `uid-check-austria` und `uid_check_austria` registriert - Sie können beide verwenden.

---

### `check` - Eine UID verifizieren

```bash
uid-check-austria check [OPTIONEN] [UID]
```

**Argumente:**

| Argument | Erforderlich | Beschreibung                                                                  |
|----------|--------------|-------------------------------------------------------------------------------|
| `UID`    | Ja*          | EU-UID zur Verifizierung (z.B. DE123456789). *Nicht erforderlich mit `--interactive` |

**Optionen:**

| Option          | Kurz  | Standard        | Beschreibung                                             |
|-----------------|-------|-----------------|----------------------------------------------------------|
| `--interactive` | `-i`  | `False`         | Interaktiver Modus: UID eingeben                         |
| `--no-email`    | -     | `False`         | E-Mail-Benachrichtigung deaktivieren (Standard: aktiviert)|
| `--format`      | -     | `human`         | Ausgabeformat: `human` oder `json`                       |
| `--recipient`   | -     | Konfig-Standard | E-Mail-Empfänger (kann mehrfach angegeben werden)        |

**Exit-Codes:**

| Code | Bedeutung                 |
|------|---------------------------|
| 0    | UID ist gültig            |
| 1    | UID ist ungültig          |
| 2    | Konfigurationsfehler      |
| 3    | Authentifizierungsfehler  |
| 4    | Abfragefehler             |

**Beispiele:**

```bash
# Grundlegende Verwendung
uid-check-austria check DE123456789

# JSON-Ausgabe
uid-check-austria check DE123456789 --format json

# Ohne E-Mail-Benachrichtigung
uid-check-austria check DE123456789 --no-email

# Benutzerdefinierte Empfänger
uid-check-austria check DE123456789 --recipient admin@beispiel.at --recipient finanzen@beispiel.at

# Interaktiver Modus
uid-check-austria check --interactive

# Mit Profil
uid-check-austria --profile production check DE123456789
```

---

### `config` - Konfiguration anzeigen

```bash
uid-check-austria config [OPTIONEN]
```

**Optionen:**

| Option      | Standard | Beschreibung                                                                    |
|-------------|----------|---------------------------------------------------------------------------------|
| `--format`  | `human`  | Ausgabeformat: `human` oder `json`                                              |
| `--section` | `None`   | Nur bestimmten Abschnitt anzeigen (z.B. 'finanzonline', 'email', 'lib_log_rich')|
| `--profile` | `None`   | Profil vom Root-Befehl überschreiben                                            |

**Beispiele:**

```bash
# Alle Konfigurationen anzeigen
uid-check-austria config

# JSON-Ausgabe für Skripte
uid-check-austria config --format json

# Nur E-Mail-Abschnitt anzeigen
uid-check-austria config --section email

# Produktionsprofil anzeigen
uid-check-austria config --profile production
```

---

### `config-deploy` - Konfigurationsdateien bereitstellen

```bash
uid-check-austria config-deploy [OPTIONEN]
```

**Optionen:**

| Option      | Erforderlich | Standard | Beschreibung                                                    |
|-------------|--------------|----------|-----------------------------------------------------------------|
| `--target`  | Ja           | -        | Zielebene: `user`, `app` oder `host` (kann mehrfach angegeben werden) |
| `--force`   | Nein         | `False`  | Bestehende Konfigurationsdateien überschreiben                  |
| `--profile` | Nein         | `None`   | In bestimmtes Profilverzeichnis bereitstellen                   |

**Beispiele:**

```bash
# Benutzerkonfiguration bereitstellen
uid-check-austria config-deploy --target user

# Systemweit bereitstellen (erfordert Berechtigungen)
sudo uid-check-austria config-deploy --target app

# Mehrere Ziele bereitstellen
uid-check-austria config-deploy --target user --target host

# Bestehende überschreiben
uid-check-austria config-deploy --target user --force

# In Produktionsprofil bereitstellen
uid-check-austria config-deploy --target user --profile production
```

---

### `info` - Paketinformationen anzeigen

```bash
uid-check-austria info
```

Zeigt Paketname, Version, Homepage, Autor und andere Metadaten an.

---

### `hello` - Erfolgspfad testen

```bash
uid-check-austria hello
```

Gibt eine Begrüßungsmeldung aus, um zu verifizieren, dass die CLI funktioniert.

---

### `fail` - Fehlerbehandlung testen

```bash
uid-check-austria fail
uid-check-austria --traceback fail  # Mit vollständigem Traceback
```

Löst absichtlich einen Fehler aus, um die Fehlerbehandlung zu testen.
