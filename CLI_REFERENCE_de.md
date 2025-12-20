# CLI-Referenz

Dieses Dokument beschreibt alle CLI-Befehle und Optionen für `finanzonline_uid`.

## Globale Optionen

Diese Optionen gelten für alle Befehle:

| Option                         | Standard         | Beschreibung                                                           |
|--------------------------------|------------------|------------------------------------------------------------------------|
| `--traceback / --no-traceback` | `--no-traceback` | Vollständigen Python-Traceback bei Fehlern anzeigen                    |
| `--profile NAME`               | `None`           | Konfiguration aus benanntem Profil laden (z.B. 'production', 'test')   |
| `--version`                    | -                | Version anzeigen und beenden                                           |
| `-h, --help`                   | -                | Hilfe anzeigen und beenden                                             |

## Befehle

Der CLI-Befehl ist unter `finanzonline-uid` und `finanzonline_uid` registriert - Sie können beide verwenden.

---

### `check` - Eine UID verifizieren

```bash
finanzonline-uid check [OPTIONEN] [UID]
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
finanzonline-uid check DE123456789

# JSON-Ausgabe
finanzonline-uid check DE123456789 --format json

# Ohne E-Mail-Benachrichtigung
finanzonline-uid check DE123456789 --no-email

# Benutzerdefinierte Empfänger
finanzonline-uid check DE123456789 --recipient admin@beispiel.at --recipient finanzen@beispiel.at

# Interaktiver Modus
finanzonline-uid check --interactive

# Mit Profil
finanzonline-uid --profile production check DE123456789
```

---

### `config` - Konfiguration anzeigen

```bash
finanzonline-uid config [OPTIONEN]
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
finanzonline-uid config

# JSON-Ausgabe für Skripte
finanzonline-uid config --format json

# Nur E-Mail-Abschnitt anzeigen
finanzonline-uid config --section email

# Produktionsprofil anzeigen
finanzonline-uid config --profile production
```

---

### `config-deploy` - Konfigurationsdateien bereitstellen

```bash
finanzonline-uid config-deploy [OPTIONEN]
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
finanzonline-uid config-deploy --target user

# Systemweit bereitstellen (erfordert Berechtigungen)
sudo finanzonline-uid config-deploy --target app

# Mehrere Ziele bereitstellen
finanzonline-uid config-deploy --target user --target host

# Bestehende überschreiben
finanzonline-uid config-deploy --target user --force

# In Produktionsprofil bereitstellen
finanzonline-uid config-deploy --target user --profile production
```

---

### `info` - Paketinformationen anzeigen

```bash
finanzonline-uid info
```

Zeigt Paketname, Version, Homepage, Autor und andere Metadaten an.

---

### `hello` - Erfolgspfad testen

```bash
finanzonline-uid hello
```

Gibt eine Begrüßungsmeldung aus, um zu verifizieren, dass die CLI funktioniert.

---

### `fail` - Fehlerbehandlung testen

```bash
finanzonline-uid fail
finanzonline-uid --traceback fail  # Mit vollständigem Traceback
```

Löst absichtlich einen Fehler aus, um die Fehlerbehandlung zu testen.
