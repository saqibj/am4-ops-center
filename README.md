![Python](https://img.shields.io/badge/Python-3.10--3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-3.x-06B6D4?logo=tailwindcss&logoColor=white)
![HTMX](https://img.shields.io/badge/HTMX-2.0-3366CC?logo=htmx&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-3-003B57?logo=sqlite&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)
![Platform](https://img.shields.io/badge/Platform-WSL%20%7C%20Linux%20%7C%20macOS-lightgrey)

# AM4 RouteMine ✈️

> Bulk route profitability mining for Airline Manager 4 — extract, analyze, and optimize across all aircraft × hub combinations in a single offline tool.

AM4 RouteMine is a Python CLI and web dashboard that uses the [am4](https://github.com/abc8747/am4) package to compute route economics for every valid aircraft × airport combination. It completely eliminates the need for per-hub Discord bot queries. Results are stored in an SQLite database, allowing for offline querying through a lightning-fast FastAPI + Tailwind CSS + HTMX dashboard.

---

## 📸 Screenshots

> Screenshots coming soon. The dashboard features 9 pages including Hub Explorer, Aircraft Comparison, Route Analyzer, Fleet Management, and a Global Heatmap.

---

## ✨ Features

- **Bulk extraction** — compute route profitability for every aircraft × hub combo using the am4 C++ engine
- **6+ hub support** — KHI, DXB, LHR, JFK, HKG, MJD (or any IATA code)
- **336 aircraft** — all AM4 aircraft types with full specs
- **3,900+ airports** — complete airport database with runway, market tier, hub costs
- **SQLite storage** — 3.8M+ route rows queryable offline
- **FastAPI dashboard** — dark-mode web UI with Tailwind CSS + HTMX (no page reloads)
- **9 dashboard pages** — Overview, Hub Explorer, Aircraft Comparison, Route Analyzer, Fleet Planner, My Fleet, My Routes, Contribution Optimizer, Global Heatmap
- **Fleet management** — track owned aircraft, active routes, CSV import/export
- **"Buy Next" engine** — ROI-ranked aircraft purchase recommendations
- **CSV/Excel export** — dump any table for spreadsheet analysis
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
  - [Direct SQLite Queries](#direct-sqlite-queries)
- [Dashboard](#dashboard)
  - [Pages](#pages)
  - [Tech Stack](#tech-stack)
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
pip install "am4 @ git+https://github.com/abc8747/am4.git@master" && pip install -r requirements.txt
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

4. **Install the am4 package** (compiles C++ core with GCC, ~2 minutes)
   ```bash
   pip install "am4 @ git+https://github.com/abc8747/am4.git@master"
   ```

5. **Install remaining dependencies**
   ```bash
   pip install -r requirements.txt
   ```

6. **Verify installation**
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

---

## 💻 Usage

### Extract Route Data

```bash
# Extract specific hubs (recommended start)
python3 main.py extract --hubs KHI,DXB --mode easy --workers 1

# Extract all your hubs
python3 main.py extract --hubs KHI,DXB,LHR,JFK,HKG,MJD --mode easy --workers 1

# Extract ALL airports as hubs (takes hours)
python3 main.py extract --all-hubs --mode easy --workers 1
```

**Extract options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--hubs` | — | Comma-separated IATA codes |
| `--all-hubs` | `false` | Process all 3,900+ airports as hubs |
| `--mode` | `easy` | Game mode: `easy` or `realism` |
| `--ci` | `200` | Cost Index (0–200) |
| `--reputation` | `87.0` | Player reputation (0–100) |
| `--aircraft` | all | Filter by aircraft: `b738,a388` |
| `--db` | `am4_data.db` | SQLite output path |
| `--workers` | `1` | Parallel threads (1 recommended) |

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

```bash
python3 main.py dashboard
# Opens at http://localhost:8000

python3 main.py dashboard --port 3000  # custom port
python3 main.py dashboard --db custom.db  # custom database
```

### Fleet Management

```bash
# Import fleet from CSV
python3 main.py fleet import --file fleet.csv

# Import routes from CSV
python3 main.py routes import --file my_routes.csv

# Export fleet
python3 main.py fleet export --output fleet_backup.csv

# List fleet
python3 main.py fleet list
```

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
| Aircraft Comparison | `/aircraft` | Best routes for a specific aircraft across all hubs |
| Route Analyzer | `/route-analyzer` | All aircraft ranked for a specific route |
| Fleet Planner | `/fleet-planner` | Budget-based aircraft/route recommendations |
| My Fleet | `/my-fleet` | Owned aircraft with inline editing, CSV import/export |
| My Routes | `/my-routes` | Active route assignments with profit calculations |
| Buy Next | `/buy-next` | ROI-ranked purchase recommendations |
| Contributions | `/contributions` | Routes sorted by alliance contribution |
| Heatmap | `/heatmap` | Map visualization of profitable destinations |

### Tech Stack

- **Backend:** FastAPI + Jinja2 templates
- **Frontend:** Tailwind CSS (dark mode) + HTMX (no page reloads)
- **Charts:** Chart.js
- **Maps:** Leaflet.js
- **Database:** SQLite
- **Core Engine:** am4 (C++ with pybind11 Python bindings)

---

## 🔼 Upgrading

```bash
# Update the am4 game data package
pip install --upgrade "am4 @ git+https://github.com/abc8747/am4.git@master"

# Re-extract routes with updated data
python3 main.py extract --hubs KHI,DXB,LHR,JFK,HKG,MJD --mode easy --workers 1

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
│   ├── db.py                # SQLite helpers
│   ├── routes/
│   │   ├── pages.py         # Page routes
│   │   └── api_routes.py    # HTMX + JSON API routes
│   ├── templates/           # Jinja2 HTML templates
│   └── static/              # JS, CSS, favicon
├── PRD/                     # Product specs
├── exports/                 # CSV/Excel output
├── fleet.csv                # Fleet import data
├── my_routes.csv            # Routes import data
├── convert_csv.py           # AM4 CSV → import format converter
├── requirements.txt
├── pyproject.toml
└── README.md
```

---

## 🚑 Troubleshooting

| Issue | Fix |
|-------|-----|
| `am4` build fails on Windows/MSVC | Use WSL Ubuntu — GCC compiles it cleanly |
| `am4` build fails on Python 3.13+ | Use Python 3.10–3.12 |
| `ModuleNotFoundError: am4` | Activate venv: `source .venv/bin/activate` |
| Segfault on import | Must call `init()` before any am4 module usage |
| `init()` downloads data files | Normal on first run — needs internet connection once |
| Extraction is slow | Use `--workers 1` (parallel hands on large datasets) |
| SQLite locked | Close other DB connections, enable WAL mode |
| Dashboard blank page | Check `AM4_ROUTEMINE_DB` path points to an existing `.db` file |
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
