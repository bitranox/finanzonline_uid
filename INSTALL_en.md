# Installation Guide

> The CLI stack uses `rich-click`, which bundles `rich` styling on top of click-style ergonomics.

This guide collects every supported method to install `uid_check_austria`, including
isolated environments and system package managers. Pick the option that matches your workflow.


## We recommend `uv` to install the package 

### 🔹 `uv` = Ultra-fast Python package manager

→ lightning-fast replacement for `pip`, `venv`, `pip-tools`, and `poetry`
written in Rust, compatible with PEP 621 (`pyproject.toml`)

### 🔹 `uvx` = On-demand tool runner

→ runs tools temporarily in isolated environments without installing them globally


## ⚙️ Installation

```bash
# recommended on linux
curl -LsSf https://astral.sh/uv/install.sh | sh
# alternative
pip install uv
# alternative
python -m pip install uv
```

---

## 🧠 Core Principle

`uv` combines the capabilities of:

* **pip** (package installation)
* **venv** (virtual environments)
* **pip-tools** (Lockfiles)
* **poetry** (project management)
* **pipx** (tool execution)

All via a single command suite.

---

## 🧭 Comparison with Alternatives

| Tool         | Speed       | Lockfile | Tool execution | pyproject support |
|--------------|-------------|----------|----------------|-------------------|
| pip          | medium      | ❌        | ❌              | partial           |
| poetry       | slow        | ✅        | ❌              | ✅                 |
| pipx         | medium      | ❌        | ✅              | ❌                 |
| **uv + uvx** | ⚡ very fast | ✅        | ✅              | ✅                 |

---

## 🪶 Key Features

| Feature                     | Description                                                |
| --------------------------- | ---------------------------------------------------------- |
| **Very fast**               | written in Rust (10–20× faster than pip/poetry)            |
| **Deterministic builds**    | via `uv.lock`                                              |
| **Isolated tools (`uvx`)**  | no global installations required                           |
| **PEP-compatible**          | supports `pyproject.toml`, PEP 621                         |
| **Cache sharing**           | reuses packages from the global cache                      |
| **Compatible**              | works with existing virtual environments and Pipfiles      |


---

## 📚 Further Resources

* 🔗 [https://docs.astral.sh/uv](https://docs.astral.sh/uv)
* 🔗 [https://astral.sh/blog/uv](https://astral.sh/blog/uv)
* 🔗 [https://github.com/astral-sh/uv](https://github.com/astral-sh/uv)

---


## 1. Installation via uv

```bash
# Create and activate a virtual environment (optional but recommended)
uv venv
# macOS/Linux
source .venv/bin/activate
# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# install via uv from PyPI
uv pip install uid_check_austria
# optional install from GitHub
uv pip install "git+https://github.com/bitranox/uid_check_austria"
# upgrade
uv tool upgrade --all
```

## 2.  One Time run via uvx

One-off/ad-hoc usage lets you run the tool without adding it to the project.
Multiple projects with different tool versions stay isolated so each can use "its" uvx version without conflicts.

```bash
# run from PyPI
uvx uid_check_austria
# run from GitHub
uvx --from git+https://github.com/bitranox/uid_check_austria.git uid_check_austria

```

---

## 3. Installation via pip

```bash
# optional, install in a venv (recommended)
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
# install from PyPI
pip install uid_check_austria 
# optional install from GitHub
pip install "git+https://github.com/bitranox/uid_check_austria"
# optional development install from local
pip install -e .[dev]
# optional install from local runtime only:
pip install .
```

## 4. Per-User Installation (No Virtualenv) - from local

```bash
# install from PyPI
pip install --user uid_check_austria 
# optional install from GitHub
pip install --user "git+https://github.com/bitranox/uid_check_austria"
# optional install from local
pip install --user .
```

> Note: This respects PEP 668. Avoid using it on system Python builds marked as
> "externally managed". Ensure `~/.local/bin` (POSIX) is on your PATH so the CLI is available.

## 5. pipx (Isolated CLI-Friendly Environment)

```bash
# install pipx via pip
python -m pip install pipx
# optional install pipx via apt
sudo apt install python-pipx
# install via pipx from PyPI
pipx install uid_check_austria
# optional install via pipx from GitHub
pipx install "git+https://github.com/bitranox/uid_check_austria"
# optional install from local
pipx install .
pipx upgrade uid_check_austria
# From Git tag/commit:
```

## 6. From Build Artifacts

```bash
python -m build
pip install dist/uid_check_austria-*.whl
pip install dist/uid_check_austria-*.tar.gz   # sdist
```

## 7. Poetry or PDM Managed Environments

```bash
# Poetry
poetry add uid_check_austria     # as dependency
poetry install                          # for local dev

# PDM
pdm add uid_check_austria
pdm install
```

## 8. Install Directly from Git

```bash
pip install "git+https://github.com/bitranox/uid_check_austria#egg=uid_check_austria"
```

## 9. System Package Managers (Optional Distribution Channels)

- Deb/RPM: Package with `fpm` for OS-native delivery

All methods register both the `uid_check_austria` and
`uid-check-austria` commands on your PATH.

---

## Credential Configuration

After installation, you need to configure your FinanzOnline credentials.

### Option A: Deploy configuration files (Recommended)

Deploy a user-specific configuration file with all settings documented:

```bash
# Deploy user configuration template
uid-check-austria config-deploy --target user

# Edit the generated config file
# Linux:   ~/.config/uid-check-austria/config.toml
# macOS:   ~/Library/Application Support/bitranox/Uid Check Austria/config.toml
# Windows: %APPDATA%\bitranox\Uid Check Austria\config.toml
```

For system-wide configuration (requires privileges):

```bash
# Deploy system-wide configuration template
sudo uid-check-austria config-deploy --target app

# Edit the generated config file
# Linux:   /etc/xdg/uid-check-austria/config.toml
# macOS:   /Library/Application Support/bitranox/Uid Check Austria/config.toml
# Windows: %PROGRAMDATA%\bitranox\Uid Check Austria\config.toml
```

### Option B: Use a .env file (Optional)

Alternatively, create a `.env` file in your working directory (see [.env.example](.env.example) for a complete template):

```bash
# FinanzOnline credentials (REQUIRED)
FINANZONLINE__TID=123456789           # Participant ID (8-12 alphanumeric)
FINANZONLINE__BENID=WEBUSER           # User ID (5-12 chars, must be created as webservice user in Finanz Online!)
FINANZONLINE__PIN=yourpassword        # Password (5-128 chars)
FINANZONLINE__UID_TN=ATU12345678      # Your Austrian UID
FINANZONLINE__HERSTELLERID=ATU12345678  # Software producer VAT-ID (put Your Austrian UID)
FINANZONLINE__DEFAULT_RECIPIENTS=["admin@yourcompany.com","accounting@yourcompany.com"]

# Email configuration (for notifications)
EMAIL__SMTP_HOSTS=["smtp.example.com:587"]
EMAIL__FROM_ADDRESS=alerts@example.com
```

### Option C: Use environment variables

Set environment variables directly (with app prefix):

```bash
export UID_CHECK_AUSTRIA___FINANZONLINE__TID=123456789
export UID_CHECK_AUSTRIA___FINANZONLINE__BENID=WEBUSER
export UID_CHECK_AUSTRIA___FINANZONLINE__PIN=yourpassword
export UID_CHECK_AUSTRIA___FINANZONLINE__UID_TN=ATU12345678
export UID_CHECK_AUSTRIA___FINANZONLINE__HERSTELLERID=ATU12345678
```

### Verify Installation

```bash
# when installed
uid-check-austria check DE123456789
# using uvx, run the latest version without installing
uvx uid-check-austria@latest check DE123456789
```

For detailed configuration options, see [CONFIGURATION_en.md](CONFIGURATION_en.md).
