# Installationsanleitung

> Der CLI-Stack verwendet `rich-click`, das `rich`-Styling auf click-Ergonomie aufbaut.

Diese Anleitung beschreibt alle unterstützten Methoden zur Installation von `finanzonline_uid`,
einschließlich isolierter Umgebungen und System-Paketmanager. Wählen Sie die Option, die zu Ihrem Workflow passt.


## Wir empfehlen `uv` zur Installation des Pakets

### 🔹 `uv` = Ultraschneller Python-Paketmanager

→ Blitzschneller Ersatz für `pip`, `venv`, `pip-tools` und `poetry`,
geschrieben in Rust, kompatibel mit PEP 621 (`pyproject.toml`)

### 🔹 `uvx` = On-Demand-Tool-Runner

→ Führt Tools temporär in isolierten Umgebungen aus, ohne sie global zu installieren


## ⚙️ Installation

```bash
# empfohlen unter Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
# alternativ
pip install uv
# alternativ
python -m pip install uv
```

---

## 🧠 Grundprinzip

`uv` vereint die Fähigkeiten von:

* **pip** (Paketinstallation)
* **venv** (virtuelle Umgebungen)
* **pip-tools** (Lockfiles)
* **poetry** (Projektverwaltung)
* **pipx** (Tool-Ausführung)

Alles über eine einzige Befehlssuite.

---

## 🧭 Vergleich mit Alternativen

| Tool         | Geschwindigkeit | Lockfile | Tool-Ausführung | pyproject-Unterstützung |
|--------------|-----------------|----------|-----------------|-------------------------|
| pip          | mittel          | ❌        | ❌               | teilweise               |
| poetry       | langsam         | ✅        | ❌               | ✅                       |
| pipx         | mittel          | ❌        | ✅               | ❌                       |
| **uv + uvx** | ⚡ sehr schnell  | ✅        | ✅               | ✅                       |

---

## 🪶 Hauptfunktionen

| Funktion                      | Beschreibung                                              |
|-------------------------------|-----------------------------------------------------------|
| **Sehr schnell**              | Geschrieben in Rust (10–20× schneller als pip/poetry)     |
| **Deterministische Builds**   | via `uv.lock`                                             |
| **Isolierte Tools (`uvx`)**   | Keine globalen Installationen erforderlich                |
| **PEP-kompatibel**            | Unterstützt `pyproject.toml`, PEP 621                     |
| **Cache-Sharing**             | Wiederverwendung von Paketen aus dem globalen Cache       |
| **Kompatibel**                | Funktioniert mit bestehenden virtuellen Umgebungen        |


---

## 📚 Weitere Ressourcen

* 🔗 [https://docs.astral.sh/uv](https://docs.astral.sh/uv)
* 🔗 [https://astral.sh/blog/uv](https://astral.sh/blog/uv)
* 🔗 [https://github.com/astral-sh/uv](https://github.com/astral-sh/uv)

---


## 1. Installation via uv

```bash
# Virtuelle Umgebung erstellen und aktivieren (optional, aber empfohlen)
uv venv
# macOS/Linux
source .venv/bin/activate
# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# Installation via uv von PyPI
uv pip install finanzonline_uid
# optionale Installation von GitHub
uv pip install "git+https://github.com/bitranox/finanzonline_uid"
# Upgrade
uv tool upgrade --all
```

## 2. Einmalige Ausführung via uvx

Einmalige/Ad-hoc-Nutzung ermöglicht die Ausführung des Tools, ohne es dem Projekt hinzuzufügen.
Mehrere Projekte mit unterschiedlichen Tool-Versionen bleiben isoliert, sodass jedes "seine" uvx-Version ohne Konflikte verwenden kann.

```bash
# Ausführung von PyPI
uvx finanzonline_uid
# Ausführung von GitHub
uvx --from git+https://github.com/bitranox/finanzonline_uid.git finanzonline_uid

```

---

## 3. Installation via pip

```bash
# optional, Installation in einer venv (empfohlen)
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
# Installation von PyPI
pip install finanzonline_uid
# optionale Installation von GitHub
pip install "git+https://github.com/bitranox/finanzonline_uid"
# optionale Entwicklungsinstallation von lokal
pip install -e .[dev]
# optionale Installation von lokal (nur Runtime):
pip install .
```

## 4. Benutzer-Installation (ohne Virtualenv) - von lokal

```bash
# Installation von PyPI
pip install --user finanzonline_uid
# optionale Installation von GitHub
pip install --user "git+https://github.com/bitranox/finanzonline_uid"
# optionale Installation von lokal
pip install --user .
```

> Hinweis: Dies respektiert PEP 668. Vermeiden Sie die Verwendung bei System-Python-Builds,
> die als "externally managed" gekennzeichnet sind. Stellen Sie sicher, dass `~/.local/bin` (POSIX)
> in Ihrem PATH ist, damit die CLI verfügbar ist.

## 5. pipx (Isolierte CLI-freundliche Umgebung)

```bash
# pipx via pip installieren
python -m pip install pipx
# optional pipx via apt installieren
sudo apt install python-pipx
# Installation via pipx von PyPI
pipx install finanzonline_uid
# optionale Installation via pipx von GitHub
pipx install "git+https://github.com/bitranox/finanzonline_uid"
# optionale Installation von lokal
pipx install .
pipx upgrade finanzonline_uid
```

## 6. Aus Build-Artefakten

```bash
python -m build
pip install dist/finanzonline_uid-*.whl
pip install dist/finanzonline_uid-*.tar.gz   # sdist
```

## 7. Poetry oder PDM verwaltete Umgebungen

```bash
# Poetry
poetry add finanzonline_uid     # als Abhängigkeit
poetry install                   # für lokale Entwicklung

# PDM
pdm add finanzonline_uid
pdm install
```

## 8. Direkte Installation von Git

```bash
pip install "git+https://github.com/bitranox/finanzonline_uid#egg=finanzonline_uid"
```

## 9. System-Paketmanager (optionale Vertriebskanäle)

- Deb/RPM: Paketierung mit `fpm` für OS-native Bereitstellung

Alle Methoden registrieren sowohl den Befehl `finanzonline_uid` als auch
`finanzonline-uid` in Ihrem PATH.

---

## Zugangsdaten-Konfiguration

Nach der Installation müssen Sie Ihre FinanzOnline-Zugangsdaten konfigurieren.

### Option A: Konfigurationsdateien bereitstellen (Empfohlen)

Stellen Sie eine benutzerspezifische Konfigurationsdatei mit allen dokumentierten Einstellungen bereit:

```bash
# Benutzerkonfigurationsvorlage bereitstellen
finanzonline-uid config-deploy --target user

# Die generierte Konfigurationsdatei bearbeiten
# Linux:   ~/.config/finanzonline-uid/config.toml
# macOS:   ~/Library/Application Support/bitranox/FinanzOnline UID/config.toml
# Windows: %APPDATA%\bitranox\FinanzOnline UID\config.toml
```

Für systemweite Konfiguration (erfordert Berechtigungen):

```bash
# Systemweite Konfigurationsvorlage bereitstellen
sudo finanzonline-uid config-deploy --target app

# Die generierte Konfigurationsdatei bearbeiten
# Linux:   /etc/xdg/finanzonline-uid/config.toml
# macOS:   /Library/Application Support/bitranox/FinanzOnline UID/config.toml
# Windows: %PROGRAMDATA%\bitranox\FinanzOnline UID\config.toml
```

### Option B: Eine .env-Datei verwenden (Optional)

Alternativ erstellen Sie eine `.env`-Datei in Ihrem Arbeitsverzeichnis (siehe [.env.example](.env.example) für eine vollständige Vorlage):

```bash
# FinanzOnline-Zugangsdaten (ERFORDERLICH)
FINANZONLINE__TID=123456789           # Teilnehmer-ID (8-12 alphanumerisch)
FINANZONLINE__BENID=WEBUSER           # Benutzer-ID (5-12 Zeichen, muss als Webservice-Benutzer in FinanzOnline angelegt sein!)
FINANZONLINE__PIN=yourpassword        # Passwort (5-128 Zeichen)
FINANZONLINE__UID_TN=ATU12345678      # Ihre österreichische UID
FINANZONLINE__HERSTELLERID=ATU12345678  # Software-Hersteller UID (Ihre österreichische UID)
FINANZONLINE__DEFAULT_RECIPIENTS=["admin@ihrfirma.at","buchhaltung@ihrfirma.at"]

# E-Mail-Konfiguration (für Benachrichtigungen)
EMAIL__SMTP_HOSTS=["smtp.beispiel.at:587"]
EMAIL__FROM_ADDRESS=alerts@beispiel.at
```

### Option C: Umgebungsvariablen verwenden

Umgebungsvariablen direkt setzen (mit App-Präfix):

```bash
export FINANZONLINE_UID___FINANZONLINE__TID=123456789
export FINANZONLINE_UID___FINANZONLINE__BENID=WEBUSER
export FINANZONLINE_UID___FINANZONLINE__PIN=yourpassword
export FINANZONLINE_UID___FINANZONLINE__UID_TN=ATU12345678
export FINANZONLINE_UID___FINANZONLINE__HERSTELLERID=ATU12345678
```

### Installation überprüfen

```bash
# wenn installiert
finanzonline-uid check DE123456789
# mit uvx, neueste Version ohne Installation ausführen
uvx finanzonline-uid@latest check DE123456789
```

Für detaillierte Konfigurationsoptionen siehe [CONFIGURATION_de.md](CONFIGURATION_de.md).
