# BMF-Rückgabecodes

> 🇬🇧 **[English version available (RETURNCODES_en.md)](RETURNCODES_en.md)**

Dieses Dokument beschreibt alle Rückgabecodes des österreichischen BMF (Bundesministerium für Finanzen) FinanzOnline-Webservices.

---

## Session-/Authentifizierungscodes

Diese Codes werden bei der Anmeldung und Session-Verwaltung zurückgegeben.

| Code | Bedeutung                                         | Schweregrad | Wiederholbar |
|------|---------------------------------------------------|-------------|--------------|
| 0    | Erfolg                                            | success     | -            |
| -1   | Sitzung ungültig oder abgelaufen                  | error       | Nein         |
| -2   | Systemwartung                                     | warning     | Ja           |
| -3   | Technischer Fehler                                | error       | Ja           |
| -4   | Zugangscodes sind nicht gültig                    | critical    | Nein         |
| -5   | Benutzer wegen falscher Anmeldeversuche gesperrt  | critical    | Nein         |
| -6   | Benutzer ist gesperrt                             | critical    | Nein         |
| -7   | Benutzer ist kein Webservice-Benutzer             | critical    | Nein         |
| -8   | Teilnehmer gesperrt oder nicht autorisiert        | critical    | Nein         |

### Häufige Authentifizierungsprobleme

- **Code -4 (Ungültige Zugangscodes):** Überprüfen Sie TID, BENID und PIN in Ihrer Konfiguration.
- **Code -7 (Kein Webservice-Benutzer):** Der Benutzer muss in der FinanzOnline-Benutzerverwaltung als Webservice-Benutzer konfiguriert werden.
- **Code -8 (Teilnehmer nicht autorisiert):** Der Teilnehmer muss für die Webservice-Nutzung freigeschaltet sein.

---

## UID-Abfragecodes

Diese Codes werden bei der UID-Verifizierung (Stufe 2) zurückgegeben.

| Code | Bedeutung                                       | Schweregrad | Wiederholbar |
|------|-------------------------------------------------|-------------|--------------|
| 0    | UID ist gültig                                  | success     | -            |
| 1    | UID ist ungültig                                | warning     | Nein         |
| 4    | Falsches UID-Format                             | error       | Nein         |
| 5    | Ungültige Anfragesteller-UID                    | error       | Nein         |
| 10   | Mitgliedstaat verbietet Abfrage                 | warning     | Nein         |
| 11   | Nicht autorisiert für Anfragesteller-UID        | error       | Nein         |
| 12   | UID noch nicht abfragbar                        | warning     | Ja           |
| 101  | UID beginnt nicht mit ATU                       | error       | Nein         |
| 103  | Umsatzsteuergruppe (CZ) - Sonderbehandlung      | warning     | Nein         |
| 104  | Umsatzsteuergruppe (SK) - Sonderbehandlung      | warning     | Nein         |
| 105  | Muss über FinanzOnline-Portal abgefragt werden  | error       | Nein         |
| 1511 | Dienst nicht verfügbar                          | critical    | Ja           |
| 1512 | Zu viele Anfragen (Serverauslastung)            | warning     | Ja           |
| 1513 | Ratenlimit: 2 Abfragen/UID/Tag überschritten    | warning     | Ja           |
| 1514 | Ratenlimit: Anfragesteller-Limit überschritten  | warning     | Ja           |

---

## Schweregrade

| Schweregrad | Beschreibung |
|-------------|--------------|
| `success`   | Operation erfolgreich |
| `warning`   | Warnung - Aktion möglicherweise erforderlich |
| `error`     | Fehler - Anfrage konnte nicht verarbeitet werden |
| `critical`  | Kritisch - Konfiguration oder Berechtigung prüfen |

---

## Wiederholbare Fehler

Fehler mit "Wiederholbar: Ja" können nach einer Wartezeit erneut versucht werden:

- **Code -2 (Systemwartung):** Warten Sie einige Minuten und versuchen Sie es erneut.
- **Code -3 (Technischer Fehler):** Temporäres Problem, später erneut versuchen.
- **Code 12 (UID noch nicht abfragbar):** Die UID wurde kürzlich registriert, später erneut versuchen.
- **Code 1511 (Dienst nicht verfügbar):** Server überlastet oder in Wartung.
- **Code 1512-1514 (Ratenlimits):** Warten Sie bis zum nächsten Tag oder reduzieren Sie die Abfragehäufigkeit.

---

## Ratenlimits des BMF

Seit 6. April 2023 gelten folgende Einschränkungen:

- **Maximal 2 Abfragen pro UID pro Tag** pro Teilnehmer
- Überschreitung liefert Code `1513`

### Empfehlungen

1. Nutzen Sie das integrierte Caching (Standard: 48 Stunden)
2. Fragen Sie UIDs nur bei tatsächlichen Geschäftsvorfällen ab
3. Vermeiden Sie Massenabfragen zur Datenbankvalidierung
