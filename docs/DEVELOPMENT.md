# Development setup

For contributors and advanced users running **am4-ops-center** from source (all platforms). The **Windows installer** path is described in the root [README.md](../README.md#install-windows-11).

## Clone and virtualenv

```bash
git clone https://github.com/saqibj/am4-ops-center.git
cd am4-ops-center
python3 -m venv .venv
source .venv/bin/activate   # Windows: .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

`requirements.txt` includes **`am4`** from Git (C++ extension). On **Windows**, use **MSVC** build tools if `pip` cannot compile — see README **Windows (native with MSVC)**.

## Environment

- **`AM4OPS_DATA_DIR`** — optional override for the SQLite DB and writable dirs (default: platformdirs user data).
- **`AM4_ROUTEMINE_TOKEN`** — bearer token for dashboard mutating APIs (see README security notes).

## Run the dashboard (dev)

From the repo root with `PYTHONPATH` including the project root:

```bash
export PYTHONPATH=.
python -m uvicorn dashboard.server:app --host 127.0.0.1 --port 8765 --reload
```

Or use **`python main.py dashboard`** if your tree wires that entrypoint (see README **Launch Dashboard**).

## CLI extraction

See README **Extract Route Data** — typically:

```bash
PYTHONPATH=. python main.py extract --help
```

## Tests

```bash
PYTHONPATH=. python -m pytest tests/ -q
```

## Packaging (maintainers)

- **Launcher EXE:** `pyinstaller --clean --noconfirm packaging/launcher/launcher.spec`
- **Offline wheels:** `packaging/installer/build_wheels.ps1` (see [packaging/README.md](../packaging/README.md))
- **Installer:** Inno Setup `packaging/installer/am4opscenter.iss` after staging `dist/app` and `dist/launcher` (see `.github/workflows/build-installer.yml`)

## Dependency bumps

- Edit **`requirements.in`**, then regenerate lockfiles per README (**`scripts/update_deps.sh`**).
