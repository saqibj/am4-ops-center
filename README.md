![Python](https://img.shields.io/badge/Python-3.10--3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-3.x-06B6D4?logo=tailwindcss&logoColor=white)
![HTMX](https://img.shields.io/badge/HTMX-2.0-3366CC?logo=htmx&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-3-003B57?logo=sqlite&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20WSL%20%7C%20Linux%20%7C%20macOS-lightgrey?logo=windows&logoColor=white)

# AM4 Ops Center ✈️

**Releases:** **0.1.1** (2026-04-04), **0.1.0** (2026-03-28) — [CHANGELOG.md](CHANGELOG.md). **Git tags:** **`v0.1.0`** (annotated); add **`v0.1.1`** after you commit the Settings/theme release (command in CHANGELOG).

> Bulk route profitability mining for Airline Manager 4 — extract, analyze, and optimize across all aircraft × hub combinations in a single offline tool.

AM4 RouteMine is a Python CLI and web dashboard that uses the [am4](https://github.com/abc8747/am4) package to compute route economics for every valid aircraft × airport combination. It completely eliminates the need for per-hub Discord bot queries. Results are stored in an SQLite database, allowing for offline querying through a lightning-fast FastAPI + Tailwind CSS + HTMX dashboard.

---

## 📸 Screenshots

> Screenshots coming soon. The dashboard has **12** pages: Overview, Hub Explorer, Aircraft, Route Analyzer, Fleet Planner, Buy Next, My Fleet, My Routes, Hub Manager, Contributions, Heatmap, and **Settings**.

---

## ✨ Features

- **Bulk extraction** — compute route profitability for every aircraft × hub combo using the am4 C++ engine
- **6+ hub support** — KHI, DXB, LHR, JFK, HKG, MJD (or any IATA code)
- **336 aircraft** — all AM4 aircraft types with full specs
- **3,900+ airports** — complete airport database with runway, market tier, hub costs
- **SQLite storage** — 3.8M+ route rows queryable offline
- **FastAPI dashboard** — web UI with **light / dark / system** themes, semantic styling (`theme.css`, `am4-*` utilities), Tailwind CSS (CDN) + HTMX (no page reloads)
- **12 dashboard pages** — Overview, Hub Explorer, Aircraft, Route Analyzer, Fleet Planner, **Buy Next** (budget-ranked purchase candidates; same data as Fleet Planner / `recommend`), My Fleet, My Routes, **Hub Manager** (managed hubs, per-hub / stale refresh), Contributions, Heatmap, and **Settings** (`/settings`: themes, airline branding, default landing page, UI density, notification toggles; stored in browser **`localStorage`**)
- **Fleet & routes** — `my_fleet` / `my_routes` in SQLite; CSV import defaults to **merge**; **`--replace`** overwrites counts; dashboard forms match the same semantics
- **CLI `recommend`** / **Buy Next** (`/buy-next`) — budget-ranked aircraft from extracted `route_aircraft` (shared logic with **Fleet Planner**)
- **CSV/Excel export** — dump tables for spreadsheet analysis
- **Fully offline** — after initial setup, no internet needed

---

## 📑 Table of Contents

- [Prerequisites](#prerequisites)
- [Installation](#installation)
  - [Quick Start](#quick-start-5-commands)
  - [Detailed Installation](#detailed-installation)
  - [WSL Setup (Windows Users)](#wsl-setup-windows-users)
  - [Why WSL?](#why-wsl)
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

- **OS:** WSL Ubuntu 24.04 (recommended for Windows), native Linux, or macOS
- **Python:** 3.10–3.12 (3.12.x recommended; 3.13+ not supported)
- **Build tools:** `build-essential`, `cmake`, `python3-dev` (for compiling the am4 C++ core)
- **Git**

> ⚠️ **Windows users:** The am4 package contains C++ code that does not compile under MSVC.
> Use WSL (Windows Subsystem for Linux) with Ubuntu. See [Why WSL?](#why-wsl) below for details.

---

## 🚀 Installation

### Quick Start (5 commands)

```bash
git clone https://github.com/saqibj/am4-routemine.git && cd am4-routemine
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
python3 -c "from am4.utils.db import init; init(); print('✅ am4 OK')"
```

### Detailed Installation

1. **Install system dependencies (Ubuntu/Debian)**
   ```bash
   sudo apt update && sudo apt install -y python3-full python3-dev python3-venv build-essential cmake git
   ```

2. **Clone the repository**
   ```bash
   git clone https://github.com/saqibj/am4-routemine.git
   cd am4-routemine
   ```

3. **Create virtual environment**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   ```

4. **Install Python dependencies** (includes **`am4`** from Git — compiles C++ core with GCC, ~2 minutes)
   ```bash
   pip install -r requirements.txt
   ```

5. **Verify installation**
   ```bash
   python3 -c "from am4.utils.db import init; init(); from am4.utils.aircraft import Aircraft; print(Aircraft.search('b738').ac.name)"
   # Expected: B737-800
   ```

### WSL Setup (Windows Users)

```powershell
# From PowerShell (admin)
wsl --install -d Ubuntu
```

Then open the Ubuntu terminal and follow the Linux installation steps above.

### Why WSL?

The am4 pip package compiles C++ source via `pybind11` on every install. The code uses a lambda ternary pattern (`route.cpp`) that GCC handles appropriately, but MSVC rejects with compilation error C2446. WSL provides a native Linux environment where GCC compiles it cleanly.

### Opening in Cursor/VS Code

From the WSL terminal:
```bash
cursor .   # or: code .
```

Alternatively, you can use Cursor's "WSL: Connect to WSL" command (`Ctrl`+`Shift`+`P`).

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
| `--db` | `am4_data.db` | SQLite output path |
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

By default the dashboard binds to **127.0.0.1** only (localhost). To open it from another device on your LAN, run `python3 main.py dashboard --host 0.0.0.0` — use that only on trusted networks; set a strong **`AM4_ROUTEMINE_TOKEN`** (see below) before exposing the app. Add `--reload` for development auto-reload.

```bash
python3 main.py dashboard
# Opens at http://localhost:8000

python3 main.py dashboard --port 3000  # custom port
python3 main.py dashboard --db custom.db  # custom database
python3 main.py dashboard --host 0.0.0.0  # LAN access
python3 main.py dashboard --reload  # dev: auto-reload on file changes
```

**Mutating API authentication:** Every **`POST /api/*`** action (fleet, routes, hubs) requires header **`Authorization: Bearer <token>`**. The HTML shell sets **`hx-headers`** on `<body>` so HTMX picks up the token automatically. If **`AM4_ROUTEMINE_TOKEN`** is not set, a random token is generated once at startup and printed to the console; set that variable in your environment to keep the same token across restarts. For scripts or `curl`, pass the header explicitly, for example: `curl -X POST -H "Authorization: Bearer YOUR_TOKEN" -d 'fleet_id=1' http://127.0.0.1:8000/api/fleet/delete`.

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

### Docker

Multi-stage **`Dockerfile`**: build tools and **`pip install`** run in a builder stage; the runtime image copies only the virtualenv and runs as **`appuser`** (uid **1000**), without **`gcc`/`cmake`/`git`**. The dashboard defaults to **`--db /app/data/am4_data.db`**.

```bash
docker build -t am4-ops-center .
docker compose up --build
```

**`docker-compose.yml`** publishes **`127.0.0.1:8000:8000`** so the dashboard is not bound on your LAN interface by default. Set **`AM4_ROUTEMINE_TOKEN`** under **`environment`** if you change the publish address or need a fixed API secret.

### Direct SQLite Queries

```bash
sqlite3 am4_data.db
```

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
| Overview | `/` | Stats, top routes, quick links |
| Hub Explorer | `/hub-explorer` | Routes from a hub, filterable by aircraft/type/profit |
| Aircraft | `/aircraft` | Aircraft list and comparison against extracted routes |
| Route Analyzer | `/route-analyzer` | All aircraft ranked for a specific origin → destination |
| Fleet Planner | `/fleet-planner` | Budget-based aircraft / route suggestions |
| Buy Next | `/buy-next` | Same ranking as Fleet Planner / `recommend`; **Owned** from `my_fleet` and optional **hide types I already own** (also `recommend --hide-owned`) |
| My Fleet | `/my-fleet` | `my_fleet` table: quantities, assigned vs free, buy/sell, CSV |
| My Routes | `/my-routes` | `my_routes` assignments, merge on add, duplicate hints |
| Hub Manager | `/my-hubs` | Managed hubs (`my_hubs`): add IATA, per-hub refresh, **stale** refresh (OK extract older than 7 days), remove |
| Contributions | `/contributions` | Routes sorted by alliance contribution |
| Heatmap | `/heatmap` | Map visualization of profitable destinations |
| Settings | `/settings` | Light / dark / system theme, comfortable or compact density, default landing page (first `/` visit per tab session), notification toggles, airline name + logo; saved in **`localStorage`** (per browser) |

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
# Update the am4 package (same URL as requirements.txt / pyproject.toml)
pip install --upgrade "am4 @ git+https://github.com/saqibj/am4.git@msvc-fix"

# Re-extract routes with updated data
python3 main.py extract --hubs KHI,DXB,LHR,JFK,HKG,MJD --mode easy --workers 4

# Pull the latest code
git pull origin main
pip install -r requirements.txt
```

---

## 📁 Project Structure

```text
am4-routemine/
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
├── tests/                   # pytest (UI settings + dashboard HTTP smoke)
├── PRD/                     # Product specs
├── exports/                 # CSV/Excel output
├── fleet.csv                # Fleet import data
├── my_routes.csv            # Routes import data
├── convert_csv.py           # AM4 CSV → import format converter
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

## 🚑 Troubleshooting

| Issue | Fix |
|-------|-----|
| `am4` build fails on Windows/MSVC | Use WSL Ubuntu — GCC compiles it cleanly |
| `am4` build fails on Python 3.13+ | Use Python 3.10–3.12 |
| `ModuleNotFoundError: am4` or Hub Manager flash **“The am4 package is not available…”** | Use **Python 3.10–3.12**, create/activate a venv (`python3 -m venv .venv` then `source .venv/bin/activate`, or on Windows `py -3.12 -m venv .venv` then `.\.venv\Scripts\Activate.ps1`), run `pip install -r requirements.txt`, and start the dashboard with **that** interpreter (`python main.py dashboard …`). The UI loads without `am4`, but **add hub** and **refresh** need it. |
| Segfault on import | Must call `init()` before any am4 module usage |
| `init()` downloads data files | Normal on first run — needs internet connection once |
| Extraction is slow | Default is `--workers 4`; try `--workers 1` if you see instability or on very large extracts |
| SQLite locked | Close other DB connections, enable WAL mode |
| Dashboard blank page | Check `AM4_ROUTEMINE_DB` path points to an existing `.db` file |
| **`401`** on **`POST /api/*`** (curl, custom clients, or broken HTMX) | Send **`Authorization: Bearer <token>`** matching **`AM4_ROUTEMINE_TOKEN`** or the token printed at server startup; the HTML UI sets **`hx-headers`** on **`<body>`** automatically |
| Can’t reach the dashboard from another device | Expected with the default bind address — use `--host 0.0.0.0` only on trusted networks; set **`AM4_ROUTEMINE_TOKEN`** and use HTTPS or a reverse proxy if exposing beyond localhost (see [Launch Dashboard](#launch-dashboard)) |
| Settings / theme seem “stuck” | Preferences live in **`localStorage`** for this origin; try a hard refresh or clear site data for localhost if corrupted |
| Aircraft shortname not found | Use am4 shortnames (e.g., `a342` not `A340-200`) |
| WSL venv broken after move | Delete `.venv` and recreate — pip paths are hardcoded |

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request, report issues, or suggest new features. You can reference the product specs in the `/PRD` folder for guidance.

---

## 🙌 Credits

- [abc8747/am4](https://github.com/abc8747/am4) — Core game calculations engine (C++ with pybind11)
- [AM4 Formulae](https://abc8747.github.io/am4/formulae/) — Reverse-engineered game formulae documentation

---

## 📄 License

MIT License
