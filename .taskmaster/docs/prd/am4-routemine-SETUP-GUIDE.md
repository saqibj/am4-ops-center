# AM4 RouteMine — Setup & Run Guide

> **Repository:** https://github.com/saqibj/am4-routemine
> **PRD:** am4-routemine-PRD.md

---

## Prerequisites

- **WSL (Windows Subsystem for Linux)** with Ubuntu 24.04 — recommended for Windows users
- **Python 3.10–3.12** (the `am4` package must be compiled from C++ source; GCC on Linux handles this cleanly)
- **Build tools:** `build-essential`, `cmake`, `python3-dev`
- **Git**

### Why WSL?

The `am4` pip package has no prebuilt wheels — it compiles C++ code via pybind11 on every install. The source code uses a C++ lambda pattern that fails under MSVC (Visual Studio) but compiles cleanly under GCC (Linux). WSL gives you a native Linux environment on Windows that avoids this issue entirely.

### Why not native Windows?

- Python 3.14/3.13 are too new (no compatible build dependencies)
- Python 3.12 compiles the `am4` source but hits MSVC error C2446 in `route.cpp` (lambda ternary incompatibility)
- Even with VS Build Tools installed, the C++ code doesn't compile on MSVC

---

## Step 1: Set Up WSL (Windows users)

If you don't already have WSL, open PowerShell as Administrator:

```powershell
wsl --install -d Ubuntu
```

Then open the Ubuntu terminal from your Start Menu, or type `wsl` in any terminal.

If you already have Ubuntu in WSL, just open it.

---

## Step 2: Install System Dependencies

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y build-essential cmake python3-dev python3-venv python3-pip git
```

Verify Python:

```bash
python3 --version
# Should output Python 3.10.x through 3.12.x
# Ubuntu 24.04 ships with Python 3.12.3 — perfect
```

---

## Step 3: Clone the Repository

```bash
cd ~
git clone https://github.com/saqibj/am4-routemine.git
cd am4-routemine
```

---

## Step 4: Create Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
```

You should see `(.venv)` in your prompt.

---

## Step 5: Install the `am4` Package

The `am4` package must be installed from the GitHub master branch (the PyPI version is outdated and has build issues):

```bash
pip install "am4 @ git+https://github.com/abc8747/am4.git@master"
```

This will:
1. Clone the `am4` repo
2. Compile the C++ core with GCC
3. Install the Python bindings

On first run, `am4` will automatically download its data files (aircrafts.parquet, airports.parquet, routes.parquet) from GitHub releases.

---

## Step 6: Install Remaining Dependencies

```bash
pip install pandas tqdm rich streamlit openpyxl
```

### Option: Use requirements.txt

Create or verify `requirements.txt`:

```
am4 @ git+https://github.com/abc8747/am4.git@master
streamlit>=1.30.0
pandas>=2.0.0
openpyxl>=3.1.0
tqdm>=4.65.0
rich>=13.0.0
```

Then: `pip install -r requirements.txt`

---

## Step 7: Verify Everything Works

```bash
python -c "
from am4.utils.db import init
init()

from am4.utils.aircraft import Aircraft
result = Aircraft.search('b738')
print(f'Aircraft: {result.ac.name}')
print(f'Speed: {result.ac.speed} km/h')
print(f'Range: {result.ac.range} km')
print(f'Cost: \${result.ac.cost:,}')
"
```

**Expected output:**

```
Aircraft: B737-800
Speed: 842.0 km/h
Range: 5765 km
Cost: $72,800,000
```

Also verify airports:

```bash
python -c "
from am4.utils.db import init
init()

from am4.utils.airport import Airport
result = Airport.search('KHI')
ap = result.ap
print(f'Airport: {ap.fullname}')
print(f'IATA: {ap.iata} | ICAO: {ap.icao}')
print(f'Country: {ap.country}')
print(f'Runway: {ap.rwy} ft')
print(f'Hub cost: \${ap.hub_cost:,}')
"
```

> **Note:** You must call `init()` from `am4.utils.db` before using any other `am4` module. This loads the internal databases into memory.

---

## Step 8: Set Up the Project Structure

If the repo doesn't already have the folder structure, create it:

```bash
mkdir -p extractors database exporters dashboard exports
touch extractors/__init__.py database/__init__.py exporters/__init__.py dashboard/__init__.py
```

Target structure:

```
am4-routemine/
├── main.py                  # CLI entry point
├── config.py                # User settings (game mode, training, CI, etc.)
├── extractors/
│   ├── __init__.py
│   ├── aircraft.py          # Dump all aircraft to DB
│   ├── airports.py          # Dump all airports to DB
│   └── routes.py            # Bulk route calculations
├── database/
│   ├── __init__.py
│   ├── schema.py            # SQLite schema definitions
│   └── queries.py           # Predefined useful queries
├── exporters/
│   ├── __init__.py
│   ├── csv_export.py        # Export tables to CSV
│   └── excel_export.py      # Optional Excel export
├── dashboard/
│   ├── __init__.py
│   └── app.py               # Streamlit dashboard
├── exports/                 # CSV/Excel output directory
├── requirements.txt
├── pyproject.toml
└── README.md
```

---

## Running the Tool

### Extract data for specific hubs

```bash
python main.py extract --hubs KHI,DXB --mode easy --ci 200
```

**Common extract options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--hubs` | (none) | Comma-separated IATA codes, e.g., `KHI,DXB,LHR` |
| `--all-hubs` | false | Process ALL airports as hubs (takes hours) |
| `--mode` | `easy` | Game mode: `easy` or `realism` |
| `--ci` | `200` | Cost Index (0–200) |
| `--reputation` | `87.0` | Player reputation (0–100) |
| `--aircraft` | (all) | Filter to specific aircraft, e.g., `b738,a388` |
| `--db` | `am4_data.db` | Path to SQLite output file |
| `--workers` | `4` | Number of parallel worker threads |

### Extract ALL hubs (full database)

```bash
python main.py extract --all-hubs --mode easy --ci 200 --workers 8
```

> **Warning:** ~3,900 airports × ~450 aircraft = hours of processing. Start with `--hubs` first.

### Quick queries

```bash
python main.py query --hub KHI --top 20
python main.py query --hub KHI --aircraft b738
python main.py query --hub KHI --type cargo --top 10
python main.py query --hub DXB --sort contribution --top 20
```

### Export to CSV / Excel

```bash
python main.py export --format csv --output ./exports/
python main.py export --format excel --output ./exports/
```

### Launch the Streamlit dashboard

```bash
python main.py dashboard
```

Opens at `http://localhost:8501`. Access from Windows browser at the same URL.

Dashboard pages:

1. **Hub Explorer** — select a hub, see all routes sorted by profit
2. **Aircraft Comparison** — select an aircraft, see its best routes across hubs
3. **Route Analyzer** — pick origin + destination, see all aircraft ranked
4. **Fleet Planner** — given a hub + budget, get aircraft/route recommendations
5. **Contribution Optimizer** — routes sorted by alliance contribution
6. **Global Heatmap** — map of most profitable destinations from a hub

---

## Direct SQLite Queries (Power Users)

```bash
sqlite3 am4_data.db
```

```sql
-- Best routes from a hub
SELECT * FROM v_best_routes WHERE hub = 'KHI'
ORDER BY profit_per_ac_day DESC LIMIT 20;

-- Best aircraft for a specific route
SELECT ac.shortname, ac.name, ra.profit_per_ac_day, ra.trips_per_day,
       ra.config_y, ra.config_j, ra.config_f, ra.flight_time_hrs
FROM route_aircraft ra
JOIN aircraft ac ON ra.aircraft_id = ac.id
WHERE ra.origin_id = (SELECT id FROM airports WHERE iata = 'KHI')
  AND ra.dest_id   = (SELECT id FROM airports WHERE iata = 'LHR')
  AND ra.is_valid = 1
ORDER BY ra.profit_per_ac_day DESC;

-- Top 10 most profitable hubs overall
SELECT a.iata, a.name, a.country,
       COUNT(*) AS total_routes,
       AVG(ra.profit_per_ac_day) AS avg_profit,
       MAX(ra.profit_per_ac_day) AS max_profit
FROM route_aircraft ra
JOIN airports a ON ra.origin_id = a.id
WHERE ra.is_valid = 1
GROUP BY ra.origin_id
ORDER BY avg_profit DESC
LIMIT 10;
```

---

## Incremental Updates

When the AM4 game updates aircraft or airports:

```bash
pip install --upgrade "am4 @ git+https://github.com/abc8747/am4.git@master"
python main.py extract --hubs KHI,DXB --mode easy --ci 200
```

---

## Returning to Work

Each time you open WSL:

```bash
cd ~/am4-routemine
source .venv/bin/activate
```

---

## Common Issues & Fixes

| Issue | Fix |
|-------|-----|
| `ModuleNotFoundError: No module named 'am4'` | Activate the venv: `source .venv/bin/activate` |
| `am4` build fails on Windows/MSVC | Use WSL Ubuntu instead — GCC compiles it cleanly |
| `am4` build fails on Python 3.13+ | Use Python 3.10–3.12 |
| `init()` not called error | Add `from am4.utils.db import init; init()` at the start of every script |
| Extraction is slow | Reduce hubs or increase `--workers`. Start with 2-3 hubs |
| SQLite locked error | Close other DB connections. Consider enabling WAL mode |
| Dashboard won't start | Check port isn't in use: `lsof -i :8501` or use `--port 8080` |
| `Aircraft.search()` returns no result | Use shortname codes like `b738`, `a388`, not full names |
| Data files missing on first run | `am4` auto-downloads them from GitHub; ensure internet connectivity |

---

## Development Workflow Summary

```bash
# One-time setup
wsl
sudo apt install -y build-essential cmake python3-dev python3-venv git
cd ~ && git clone https://github.com/saqibj/am4-routemine.git && cd am4-routemine
python3 -m venv .venv && source .venv/bin/activate && pip install --upgrade pip
pip install "am4 @ git+https://github.com/abc8747/am4.git@master"
pip install pandas tqdm rich streamlit openpyxl
python -c "from am4.utils.db import init; init(); print('am4 OK')"

# Daily use
cd ~/am4-routemine && source .venv/bin/activate
python main.py extract --hubs KHI,DXB --mode easy --ci 200
python main.py query --hub KHI --top 20
python main.py dashboard
```

That's it — you're mining routes!
