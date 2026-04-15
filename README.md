![Python](https://img.shields.io/badge/Python-3.10--3.14-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-3.x-06B6D4?logo=tailwindcss&logoColor=white)
![HTMX](https://img.shields.io/badge/HTMX-2.0-3366CC?logo=htmx&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-3-003B57?logo=sqlite&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20WSL%20%7C%20Linux%20%7C%20macOS-lightgrey?logo=windows&logoColor=white)

# AM4 Ops Center ✈️

**Releases:** **0.1.1** (2026-04-04), **0.1.0** (2026-03-28) — [CHANGELOG.md](CHANGELOG.md). **Git tags:** **`v0.1.0`**, **`v0.1.1`**.

> Bulk route profitability mining for Airline Manager 4 — extract, analyze, and optimize across all aircraft × hub combinations in a single offline tool.

AM4 Ops Center is a Python CLI and web dashboard that uses the [am4](https://github.com/abc8747/am4) package to compute route economics for every valid aircraft × airport combination. It completely eliminates the need for per-hub Discord bot queries. Results are stored in an SQLite database, allowing for offline querying through a lightning-fast FastAPI + Tailwind CSS + HTMX dashboard.

## Install (Windows 11)

For a **prebuilt app** (no compiler, no `pip install am4`):

1. Open the [**Releases**](https://github.com/saqibj/am4-ops-center/releases) page and download **`AM4OpsCenter-Setup-vX.Y.Z.exe`** for the version you want.
2. Run the installer. If **Windows SmartScreen** warns that the app is unrecognized (typical for unsigned builds), choose **More info** → **Run anyway**.
3. Complete the wizard. **Python 3.14** is installed per-user under `%LOCALAPPDATA%\Programs\Python\Python314` only if no suitable **Python 3.14** is already found (registry / `py -3.14`).
4. Start **AM4 Ops Center** from the Start menu or desktop shortcut (optional task during setup).
5. A browser opens to the app; on first run, the **setup wizard** asks for AM4 credentials, hubs, and **initial extraction** (often **10–30+ minutes** depending on hubs).

**Upgrading:** Run a newer `AM4OpsCenter-Setup-*.exe` over the existing install. Your database and config stay under **`%APPDATA%\AM4OpsCenter`** (see `app/paths.py` / `AM4OPS_DATA_DIR`).

**Uninstalling:** **Settings → Apps → AM4 Ops Center → Uninstall**. You will be asked whether to **remove user data**; choose **No** to keep the DB and credentials for a future reinstall.

**Troubleshooting**

| Issue | What to try |
|--------|-------------|
| App won’t start | From the install folder (e.g. `%LOCALAPPDATA%\Programs\AM4OpsCenter`), run **`AM4OpsCenter.exe --debug`** to show a console and errors. Check **`%APPDATA%\AM4OpsCenter\logs\launcher.log`**. |
| Port already in use | **`AM4OpsCenter.exe --port 9000`** (or another free port). |
| Extraction seems stuck | Prefer a small hub first; see logs. If it persists, open an issue with **launcher.log** and steps. |

**FAQ**

- **Are my AM4 credentials safe?** They are **encrypted on disk** with a **machine-derived** key, stored under **`%APPDATA%\AM4OpsCenter\credentials.json`**, and used only to talk to **AM4’s own services** — not sent to this project’s servers.
- **Mac or Linux?** There is **no installer** for those yet; developers can run from source — see **[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)**.
- **Why does SmartScreen warn?** Public **code-signing certificates** are costly. Builds run on **GitHub Actions**; verify the **SHA-256** of the downloaded `.exe` against the value published on the release when provided.

---

## 📸 Screenshots

> Screenshots coming soon. The dashboard has **17** main pages: Overview, Hub Explorer, Aircraft, Route Analyzer, Scenarios, Fleet Planner, Buy Next, My Fleet, My Routes, Fleet Health, Demand utilization, Extraction deltas, Hub ROI, Hub Manager, Contributions, Heatmap, and **Settings**.

---

## ✨ Features

- **Bulk extraction** — compute route profitability for every aircraft × hub combo using the am4 C++ engine
- **6+ hub support** — KHI, DXB, LHR, JFK, HKG, MJD (or any IATA code)
- **336 aircraft** — all AM4 aircraft types with full specs
- **3,900+ airports** — complete airport database with runway, market tier, hub costs
- **SQLite storage** — 3.8M+ route rows queryable offline
- **FastAPI dashboard** — web UI with **light / dark / system** themes, semantic styling (`theme.css`, `am4-*` utilities), Tailwind CSS (CDN) + HTMX (no page reloads)
- **17 dashboard pages** — Overview, Hub Explorer, Aircraft, Route Analyzer, **Scenarios** (fuel/CO₂ vs extraction baselines), Fleet Planner, **Buy Next** (budget-ranked purchase candidates; same data as Fleet Planner / `recommend`), My Fleet, My Routes, **Fleet Health**, **Demand utilization**, **Extraction deltas** (compare route snapshots between two extractions), **Hub ROI**, **Hub Manager** (managed hubs, per-hub / stale refresh), Contributions, Heatmap, and **Settings** (`/settings`: themes, airline branding, default landing page, UI density, notification toggles; stored in browser **`localStorage`**)
- **Fleet & routes** — `my_fleet` / `my_routes` in SQLite; CSV import defaults to **merge**; **`--replace`** overwrites counts; dashboard forms match the same semantics
- **CLI `recommend`** / **Buy Next** (`/buy-next`) — budget-ranked aircraft from extracted `route_aircraft` (shared logic with **Fleet Planner**)
- **CSV/Excel export** — dump tables for spreadsheet analysis
- **Fully offline** — after initial setup, no internet needed

---

## 📑 Table of Contents

- [Install (Windows 11)](#install-windows-11)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
  - [Quick Start](#quick-start-5-commands)
  - [Detailed Installation](#detailed-installation)
  - [Windows (native with MSVC)](#windows-native-with-msvc)
  - [WSL (optional)](#wsl-optional)
  - [Opening in Cursor/VS Code](#opening-in-cursorvs-code)
- [Usage](#usage)
  - [Extract Route Data](#extract-route-data)
  - [Query Routes](#query-routes)
  - [Export Data](#export-data)
  - [Launch Dashboard](#launch-dashboard)
  - [Fleet Management](#fleet-management)
  - [Docker](#docker)
  - [Direct SQLite Queries](#direct-sqlite-queries)
- [Dashboard](#dashboard)
  - [Pages](#pages)
  - [Tech Stack](#tech-stack)
  - [Tests](#tests)
- [Changelog](CHANGELOG.md)
- [Upgrading](#upgrading)
- [Project Structure](#project-structure)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [Credits](#credits)
- [License](#license)

---

## 🔧 Prerequisites

- **OS:** Windows 10/11 (native), WSL Ubuntu, native Linux, or macOS
- **Python:** 3.10–3.12 (3.12.x recommended; 3.13+ not supported)
- **Build tools (compile am4 C++ / pybind11):**
  - **Linux / WSL:** `build-essential`, `cmake`, `python3-dev`
  - **Windows (native):** [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) with the **Desktop development with C++** workload (MSVC, Windows SDK). **CMake** is included in that workload; **Git for Windows** for cloning.
  - **macOS:** Xcode Command Line Tools (`xcode-select --install`); **CMake** via Homebrew if needed
- **Git**

> **Windows:** Native installs are supported. This project pins **[saqibj/am4](https://github.com/saqibj/am4)** (fork with MSVC fixes) at a **commit hash** in `requirements.in`. Install the C++ build tools above, then follow [Windows (native with MSVC)](#windows-native-with-msvc). [WSL](#wsl-optional) remains optional if you prefer a Linux environment.

---

## 🚀 Installation

Developer / from-source setup (all platforms): **[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)**.

### Quick Start (5 commands)

**Linux / macOS / WSL:**

```bash
git clone https://github.com/saqibj/am4-ops-center.git && cd am4-ops-center
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
python3 -c "from am4.utils.db import init; init(); print('✅ am4 OK')"
```

**Windows (PowerShell, after [MSVC build tools](#windows-native-with-msvc) are installed):**

```powershell
git clone https://github.com/saqibj/am4-ops-center.git; cd am4-ops-center
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python -c "from am4.utils.db import init; init(); print('am4 OK')"
```

### Detailed Installation

1. **Install system dependencies (Ubuntu/Debian)**
   ```bash
   sudo apt update && sudo apt install -y python3-full python3-dev python3-venv build-essential cmake git
   ```

2. **Clone the repository**
   ```bash
   git clone https://github.com/saqibj/am4-ops-center.git
   cd am4-ops-center
   ```

3. **Create virtual environment**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   ```

4. **Install Python dependencies** (includes **`am4`** from Git — compiles C++ via pybind11, typically 1–3 minutes)
   ```bash
   pip install -r requirements.txt
   ```

5. **Verify installation**
   ```bash
   python3 -c "from am4.utils.db import init; init(); from am4.utils.aircraft import Aircraft; print(Aircraft.search('b738').ac.name)"
   # Expected: B737-800
   ```

### Windows (native with MSVC)

1. **Install build prerequisites**
   - [Python 3.12](https://www.python.org/downloads/) (64-bit). During setup, enable **Add python.exe to PATH** (or use `py -3.12` from the [Python launcher](https://docs.python.org/3/using/windows.html#python-launcher-for-windows)).
   - [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) → **Desktop development with C++** (includes MSVC, Windows SDK, and CMake).
   - [Git for Windows](https://git-scm.com/download/win).

2. **Open a shell where MSVC is on PATH** (needed so `pip` can compile extensions):
   - **Recommended:** Start **“x64 Native Tools Command Prompt for VS 2022”** or **“Developer PowerShell for VS 2022”** from the Start menu, then `cd` to your project folder; *or*
   - From a normal PowerShell, builds often still succeed if Build Tools are installed—if `pip install` fails with “cannot find cl.exe” or similar, use the Native Tools prompt above.

3. **Create a venv and install**

   ```powershell
   cd C:\path\to\am4-ops-center
   py -3.12 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. **Verify**

   ```powershell
   python -c "from am4.utils.db import init; init(); from am4.utils.aircraft import Aircraft; print(Aircraft.search('b738').ac.name)"
   ```

   You should see `B737-800`. Use the same venv for `python main.py extract …`, `python main.py dashboard …`, etc.

### WSL (optional)

If you prefer Ubuntu on Windows (same GCC-based flow as Linux):

```powershell
# From PowerShell (admin)
wsl --install -d Ubuntu
```

Then open the Ubuntu terminal and follow [Detailed Installation](#detailed-installation) (Linux steps). Older upstream **am4** builds failed MSVC with error **C2446**; this repo’s pinned fork includes fixes, so **native Windows and WSL are both valid**—choose whichever you prefer.

### Opening in Cursor/VS Code

**Windows (native):** Open the project folder in Cursor/VS Code as usual; select the interpreter **`.venv\Scripts\python.exe`**.

**WSL:** From the Ubuntu terminal: `cursor .` or `code .`, or use **WSL: Connect to WSL** (`Ctrl`+`Shift`+`P`).

For **Taskmaster MCP** (optional), copy `.mcp.json.example` to `.mcp.json` and add your API keys. The real `.mcp.json` is gitignored so secrets are not committed.

### Dependency files (`requirements.in`, locks, `pyproject.toml`)

- **`requirements.in`** — edit this for **direct** dependencies (version ranges). The **`am4`** line is a Git URL **pinned to a commit hash** (integrity for that package is the hash, not a pip wheel hash).
- **`requirements.txt`** — generated (**no** hashes): `pip install -r requirements.txt` for local/dev installs.
- **`requirements.lock`** — generated **with** `--hash=sha256:…` for every PyPI package; used by **Docker** after stripping the VCS line (see **`scripts/strip_vcs_from_lock.py`**). **`am4`** is installed separately in the image from the same line as in **`requirements.in`**.
- Regenerate both files after changing **`requirements.in`**: `bash scripts/update_deps.sh` (needs **`pip-tools`**; use **Python 3.12** to match the **`Dockerfile`** base image).
- **`pyproject.toml`** mirrors the same direct deps so `pip install -e .` stays consistent. If you upgrade **`am4`**, update **`requirements.in`**, **`pyproject.toml`**, and rerun **`scripts/update_deps.sh`**.

---

## 💻 Usage

### Extract Route Data

**Full rebuild** (default `extract` without `--refresh-hubs`): runs a bulk extraction for `--hubs …` or `--all-hubs`. Use this when building the database from scratch or refreshing masters + routes at scale.

**Hub-only refresh** (`--refresh-hubs` + `--hubs`): recomputes **`route_aircraft`** / **`route_demands`** only for the listed origins. Faster and scoped; requires **aircraft** (and normal prerequisites) from a **prior full extract**. Cannot be combined with `--all-hubs`.

```bash
# Full rebuild — specific hubs (typical first run)
python3 main.py extract --hubs KHI,DXB --mode easy --workers 4

# Full rebuild — your hub list
python3 main.py extract --hubs KHI,DXB,LHR,JFK,HKG,MJD --mode easy --workers 4

# Full rebuild — ALL airports as hubs (very long-running)
python3 main.py extract --all-hubs --mode easy --workers 4

# Hub-only refresh (after data already exists)
python3 main.py extract --refresh-hubs --hubs KHI,DXB --mode easy --workers 4
```

**Extract options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--hubs` | — | Comma-separated IATA codes (required with `--refresh-hubs`; for full extract, provide `--hubs` or `--all-hubs`) |
| `--all-hubs` | `false` | Process all airports as hubs (**full rebuild only**; not with `--refresh-hubs`) |
| `--refresh-hubs` | `false` | **Hub-only** route recompute for `--hubs` only |
| `--mode` | `easy` | Game mode: `easy` or `realism` |
| `--ci` | `200` | Cost Index (0–200) |
| `--reputation` | `87.0` | Player reputation (0–100) |
| `--aircraft` | all | Filter by aircraft: `b738,a388` |
| `--db` | `app.paths.db_path()` (`…/am4ops.db`) | SQLite path; override with `--db` or **`AM4_OPS_CENTER_DB`** (legacy **`AM4_ROUTEMINE_DB`**) |
| `--workers` | `4` | Parallel worker count (lower if you see instability) |
| `--aircraft-id-max` | `1000` | Exclusive end of am4 aircraft ID scan (`range(0, N)`) |
| `--airport-id-max` | `8000` | Exclusive end of am4 airport ID scan (`range(0, N)`) |

Bulk extraction writes **every** valid am4 airport to SQLite (all runway lengths). **`min_runway`** in `UserConfig` only affects **adding a hub** through the dashboard (short strips are rejected there if below the threshold).

### Query Routes

```bash
python3 main.py query --hub KHI --top 20
python3 main.py query --hub KHI --aircraft b738
python3 main.py query --hub DXB --type cargo --top 10
python3 main.py query --hub KHI --sort contribution --top 20
```

### Export Data

```bash
python3 main.py export --format csv --output ./exports/
python3 main.py export --format excel --output ./exports/
```

### Launch Dashboard

By default the dashboard binds to **127.0.0.1** only (localhost). To open it from another device on your LAN, run `python3 main.py dashboard --host 0.0.0.0` — use that only on trusted networks; set a strong **`AM4_OPS_CENTER_TOKEN`** (legacy **`AM4_ROUTEMINE_TOKEN`** still works; see below) before exposing the app. Add `--reload` for development auto-reload.

```bash
python3 main.py dashboard
# Opens at http://localhost:8000

python3 main.py dashboard --port 3000  # custom port
python3 main.py dashboard --db custom.db  # custom database
python3 main.py dashboard --host 0.0.0.0  # LAN access
python3 main.py dashboard --reload  # dev: auto-reload on file changes
```

On **Windows** with an activated venv, `python` is usually correct if `python3` is not on your PATH.

**Mutating API authentication:** Every **`POST /api/*`** action (fleet, routes, hubs) requires header **`Authorization: Bearer <token>`**. The HTML shell sets **`hx-headers`** on `<body>` so HTMX picks up the token automatically. If neither **`AM4_OPS_CENTER_TOKEN`** nor legacy **`AM4_ROUTEMINE_TOKEN`** is set, a random token is generated once at startup and printed to the console; set **`AM4_OPS_CENTER_TOKEN`** in your environment to keep the same token across restarts. For scripts or `curl`, pass the header explicitly, for example: `curl -X POST -H "Authorization: Bearer YOUR_TOKEN" -d 'fleet_id=1' http://127.0.0.1:8000/api/fleet/delete`.

### Fleet Management

**Import semantics:** **`fleet import`** and **`routes import`** default to **`--merge`**: duplicate rows **add** to stored `quantity` / `num_assigned` (capped at 999). Use **`--replace`** to **overwrite** counts from the CSV for matching keys.

```bash
# Import fleet (merge is default)
python3 main.py fleet import --file fleet.csv

# Replace fleet counts from file for duplicates
python3 main.py fleet import --replace --file fleet.csv

# Import routes (merge is default)
python3 main.py routes import --file my_routes.csv

# Overwrite route assignment counts from file
python3 main.py routes import --replace --file my_routes.csv

# Export fleet
python3 main.py fleet export --output fleet_backup.csv

# List fleet
python3 main.py fleet list
```

**CLI recommendations** (extracted routes + budget):

```bash
python3 main.py recommend --hub KHI --budget 500000000 --top 25
```

Tab-separated output includes **`days_be_avg`** (break-even days using average daily profit across routes) and **`days_be_best`** (using the single best route). **`days_be_best`** is never greater than **`days_be_avg`** when both are present.

**Fleet CSV format:** `shortname,count,notes`
```csv
a342,58,Main long-haul fleet
a319neo,19,Short-haul workhorse
erj172,11,Regional routes
```

**Routes CSV format:** `hub,destination,aircraft,num_assigned,notes`
```csv
KHI,BCN,a342,2,Premium route
DXB,CAI,a319neo,1,High frequency
HKG,IAD,a342,2,Trans-Pacific
```

**Fleet quantity is global:** `my_fleet` stores **one row per aircraft type** with a total **`quantity`** (there is no per-hub column). The dashboard treats **available** aircraft as owned quantity minus **`num_assigned` summed across all route origins**, so a type fully assigned from another hub does not appear as spare when adding a route from a different hub.

**OCR export → import files (`scripts/convert_csv.py`):** The game API does not expose your fleet; some workflows OCR screenshots into a CSV with columns **`Hub`**, **`Destination`**, **`Aircraft_Type`**, **`Aircraft_Reg`**, **`Route_Type`**. Run:

```bash
python scripts/convert_csv.py path/to/am4_routes.csv
python scripts/convert_csv.py path/to/am4_routes.csv --on-undercount warn
```

This writes **`fleet.csv`**, **`my_routes.csv`**, and **`mapping_report.txt`** in the current directory. Fleet counts come from **unique registrations per aircraft type**; bad OCR can reuse the same reg for several rows and **under-count** fleet size while routes stay correct. The script compares those counts to a **minimum implied by route rows** (each active route assigns one aircraft of that type) and either **raises** fleet tallies to match (**`--on-undercount bump`**, the default), **warns without changing** (**`warn`**), or **exits with an error** (**`fail`**). It also warns when there are **more rows than unique regs** for a type. Review **`mapping_report.txt`** → **DATA QUALITY WARNINGS** after each run.

### Docker

Multi-stage **`Dockerfile`**: build tools and **`pip install`** run in a builder stage; the runtime image copies only the virtualenv and runs as **`appuser`** (uid **1000**), without **`gcc`/`cmake`/`git`**. The dashboard defaults to **`--db /app/data/am4ops.db`**. If you still have **`am4_data.db`** in the data volume, rename it once to **`am4ops.db`** (or point **`AM4_OPS_CENTER_DB`** / legacy **`AM4_ROUTEMINE_DB`** at the old path).

```bash
docker build -t am4-ops-center .
docker compose up --build
```

The compose service and container are named **`am4-ops-center`**; the named volume is **`am4-ops-center-data`**. If you still have an older setup using **`routemine`** / **`routemine-data`**, copy data out of the old volume or recreate the stack and set **`AM4_OPS_CENTER_DB`** (or legacy **`AM4_ROUTEMINE_DB`**) to your database path.

**`docker-compose.yml`** publishes **`127.0.0.1:8000:8000`** so the dashboard is not bound on your LAN interface by default. Set **`AM4_OPS_CENTER_TOKEN`** under **`environment`** if you change the publish address or need a fixed API secret (legacy **`AM4_ROUTEMINE_TOKEN`** still works).

### Direct SQLite Queries

Default file is **`am4ops.db`** at **`app.paths.db_path()`** (platform user data dir unless **`AM4OPS_DATA_DIR`** / **`AM4_OPS_CENTER_DB`** / legacy **`AM4_ROUTEMINE_DB`** overrides). Run from the **repo root** so Python can import **`app`**. **`sqlite3`** is the SQLite CLI (install separately on Windows if needed).

**Bash / Git Bash / WSL / macOS / Linux:**

```bash
sqlite3 "$(python -c "from app.paths import db_path; print(db_path())")"
```

**Windows PowerShell:**

```powershell
$db = python -c "from app.paths import db_path; print(db_path())"
sqlite3 $db
```

**Windows `cmd.exe`:** run `python -c "from app.paths import db_path; print(db_path())"`, then `sqlite3 "that\path\am4ops.db"`. One-liner: `for /f "delims=" %p in ('python -c "from app.paths import db_path; print(db_path())"') do sqlite3 "%p"` (use `%%p` in a `.bat` file).

**Docker** (path from compose): `sqlite3 /app/data/am4ops.db`

More detail: **`.taskmaster/docs/prd/am4-ops-center-SETUP-GUIDE.md`** (Direct SQLite Queries).

**Example Queries:**

*Best 5 Routes for B737-800 from KHI:*
```sql
SELECT destination, profit_per_ac_day, distance_km 
FROM v_best_routes 
WHERE hub = 'KHI' AND aircraft = 'b738' 
ORDER BY profit_per_ac_day DESC LIMIT 5;
```

*Most profitable Aircraft for JFK to LHR:*
```sql
SELECT aircraft, profit_per_ac_day, config_y, config_j, config_f 
FROM v_best_routes 
WHERE hub = 'JFK' AND destination = 'LHR' 
ORDER BY profit_per_ac_day DESC LIMIT 5;
```

*Top 5 Hubs by Average Profitability:*
```sql
SELECT origin_id, AVG(profit_per_ac_day) as avg_profit 
FROM route_aircraft 
WHERE is_valid = 1 
GROUP BY origin_id ORDER BY avg_profit DESC LIMIT 5;
```

---

## 📊 Dashboard

### Pages

| Page | URL | Description |
|------|-----|-------------|
| Overview | `/` | Stats, top routes, quick links, freshness card |
| Hub Explorer | `/hub-explorer` | Routes from a hub, filterable by aircraft/type/profit |
| Aircraft | `/aircraft` | Aircraft list plus cost-breakdown stacked chart |
| Route Analyzer | `/route-analyzer` | All aircraft ranked for a specific origin → destination |
| Scenarios | `/scenarios` | Fuel/CO2 what-if slider vs extracted baseline costs |
| Fleet Planner | `/fleet-planner` | Budget-based aircraft / route suggestions |
| Buy Next | `/buy-next` | Payback-ranked purchases, top routes, optional multi-hub allocator |
| My Fleet | `/my-fleet` | `my_fleet` table: quantities, assigned vs free, buy/sell, CSV |
| My Routes | `/my-routes` | `my_routes` assignments, merge on add, duplicate hints |
| Fleet Health | `/fleet-health` | Profit gap vs best aircraft/config on each assigned route |
| Demand utilization | `/demand-utilization` | Offered Y/J/F seats vs route demand with underserved/wasted flags |
| Extraction deltas | `/extraction-deltas` | Compare two extraction snapshots: new/removed/movers/flip counts |
| Hub ROI | `/hub-roi` | Per-hub capital deployed, daily profit, payback, worst-hub highlight |
| Hub Manager | `/my-hubs` | Managed hubs (`my_hubs`): add IATA, per-hub refresh, **stale** refresh (OK extract older than 7 days), remove |
| Contributions | `/contributions` | Routes sorted by alliance contribution |
| Heatmap | `/heatmap` | Map visualization of profitable destinations |
| Settings | `/settings` | Light/dark/system theme, density, landing page, notifications, branding; stored in **`localStorage`** |

### Tech Stack

- **Backend:** FastAPI + Jinja2 templates; bearer token on **`POST /api/*`** (see [Launch Dashboard](#launch-dashboard))
- **Frontend:** Tailwind CSS (CDN) + HTMX (no page reloads); **`theme.css`** semantic tokens and **`am4-*`** components; client-side theme boot (`data-theme` on `<html>`)
- **Settings:** `dashboard/static/js/settings-store.js` (persistence) and `dashboard/ui_settings.py` (shared schema / allowlists for server use)
- **Charts:** Chart.js
- **Maps:** Leaflet.js
- **Database:** SQLite
- **Core Engine:** am4 (C++ with pybind11 Python bindings)

### Tests

```bash
pip install -e ".[dev]"
pytest tests/
```

Covers UI settings parsing/sanitization, HTTP smoke checks for static assets, **`/`** and **`/settings`**, HTMX **`after-request`** elt guards on **`/my-routes`**, **`/my-hubs`**, and **`/my-fleet`**, **`POST /api/*`** bearer-token auth, schema/migrations, fleet recommend breakeven, and related regressions (see **`tests/`**).

---

## 🔼 Upgrading

```bash
# Update the am4 package (match requirements.in / pyproject.toml commit or branch)
pip install --upgrade "am4 @ git+https://github.com/saqibj/am4.git@af2ddf7cd433b0e61c1732fbdd4780136d46aa29"
# Or move to a newer commit after updating requirements.in and pyproject.toml

# Re-extract routes with updated data
python3 main.py extract --hubs KHI,DXB,LHR,JFK,HKG,MJD --mode easy --workers 4

# Pull the latest code
git pull origin main
pip install -r requirements.txt
```

---

## 📁 Project Structure

```text
am4-ops-center/
├── main.py                  # CLI entry point
├── config.py                # GameMode, UserConfig
├── commands/
│   └── airline.py           # Fleet/routes CLI commands
├── extractors/
│   ├── aircraft.py          # Aircraft data extraction
│   ├── airports.py          # Airport data extraction
│   └── routes.py            # Bulk route computation (RoutesSearch)
├── database/
│   ├── schema.py            # SQLite tables, indexes, views
│   └── queries.py           # Predefined SQL queries
├── exporters/
│   ├── csv_export.py        # CSV export
│   └── excel_export.py      # Excel export
├── dashboard/
│   ├── server.py            # FastAPI app
│   ├── auth.py              # Bearer token for POST /api/*
│   ├── db.py                # SQLite helpers
│   ├── ui_settings.py       # UI settings schema / allowlists (mirrors client store)
│   ├── hub_freshness.py     # Hub extract stale threshold / display status
│   ├── routes/
│   │   ├── pages.py         # Page routes
│   │   ├── api_routes.py    # re-exports /api router (compat)
│   │   └── api/             # HTMX + JSON under /api (meta, analytics, fleet, …)
│   ├── templates/           # Jinja2 HTML templates
│   └── static/              # favicon; css/ (theme, settings); js/ (theme, settings store, branding, shell)
├── docs/                    # Design notes (e.g. UIPRO brief / visual spec)
├── tests/                   # pytest (dashboard, fleet, convert_csv, …)
├── PRD/                     # Product specs (SQLite naming matches app: am4ops.db / db_path())
├── .taskmaster/docs/prd/    # Archived PRD copies (same DB naming conventions)
├── exports/                 # CSV/Excel output
├── fleet.csv                # Fleet import data
├── my_routes.csv            # Routes import data
├── scripts/convert_csv.py   # AM4 CSV → import format converter
├── requirements.in          # direct deps (edit)
├── requirements.txt         # pinned, no hashes (generated)
├── requirements.lock        # pinned + hashes for Docker (generated)
├── scripts/
│   ├── strip_vcs_from_lock.py  # strip VCS lines before pip --require-hashes
│   └── update_deps.sh          # pip-compile requirements.txt + requirements.lock
├── pyproject.toml
└── README.md
```

---

## Database migrations

Canonical SQLite DDL (tables, indexes, views) lives in [`database/schema.py`](database/schema.py) (`SCHEMA_SQL`, `DASHBOARD_VIEWS_SQL`). Dashboard startup and helpers call `migrate_add_unique_constraints` and related routines so existing databases pick up new columns and recreated views.

Human-readable notes and optional one-off snippets are under [`app/db/migrations/`](app/db/migrations/) (for example `001_my_routes_needs_extraction_refresh.sql`, `002_v_fleet_availability.sql`). Prefer running the Python migration path so the database stays consistent; use the `.sql` files when fixing an older copy manually.

---

## 🚑 Troubleshooting

| Issue | Fix |
|-------|-----|
| `am4` build fails on Windows (MSVC / `cl.exe` not found) | Install **Visual Studio Build Tools** with **Desktop development with C++**, then run `pip install` from **x64 Native Tools Command Prompt for VS** (see [Windows (native with MSVC)](#windows-native-with-msvc)). If it still fails, try WSL or compare your pinned **am4** commit with `requirements.in`. |
| `am4` build fails on Python 3.13+ | Use Python 3.10–3.12 |
| `ModuleNotFoundError: am4` or Hub Manager flash **“The am4 package is not available…”** | Use **Python 3.10–3.12**, create/activate a venv (`python3 -m venv .venv` then `source .venv/bin/activate`, or on Windows `py -3.12 -m venv .venv` then `.\.venv\Scripts\Activate.ps1`), run `pip install -r requirements.txt`, and start the dashboard with **that** interpreter (`python main.py dashboard …`). The UI loads without `am4`, but **add hub** and **refresh** need it. |
| Segfault on import | Must call `init()` before any am4 module usage |
| `init()` downloads data files | Normal on first run — needs internet connection once |
| Extraction is slow | Default is `--workers 4`; try `--workers 1` if you see instability or on very large extracts |
| SQLite locked | Close other DB connections, enable WAL mode |
| Dashboard blank page | Check **`AM4_OPS_CENTER_DB`** (or legacy **`AM4_ROUTEMINE_DB`**) points to an existing `.db` file |
| **`401`** on **`POST /api/*`** (curl, custom clients, or broken HTMX) | Send **`Authorization: Bearer <token>`** matching **`AM4_OPS_CENTER_TOKEN`**, legacy **`AM4_ROUTEMINE_TOKEN`**, or the token printed at server startup; the HTML UI sets **`hx-headers`** on **`<body>`** automatically |
| Can’t reach the dashboard from another device | Expected with the default bind address — use `--host 0.0.0.0` only on trusted networks; set **`AM4_OPS_CENTER_TOKEN`** (or legacy **`AM4_ROUTEMINE_TOKEN`**) and use HTTPS or a reverse proxy if exposing beyond localhost (see [Launch Dashboard](#launch-dashboard)) |
| Settings / theme seem “stuck” | Preferences live in **`localStorage`** for this origin; try a hard refresh or clear site data for localhost if corrupted |
| Aircraft shortname not found | Use am4 shortnames (e.g., `a342` not `A340-200`) |
| WSL venv broken after move | Delete `.venv` and recreate — pip paths are hardcoded |

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request, report issues, or suggest new features. Use **`PRD/`** and **`.taskmaster/docs/prd/`** for product context; both follow the same SQLite conventions as the code (**`am4ops.db`**, default **`app.paths.db_path()`**).

---

## 🙌 Credits

- [abc8747/am4](https://github.com/abc8747/am4) — Core game calculations engine (C++ with pybind11)
- [AM4 Formulae](https://abc8747.github.io/am4/formulae/) — Reverse-engineered game formulae documentation

---

## 📄 License

MIT License
