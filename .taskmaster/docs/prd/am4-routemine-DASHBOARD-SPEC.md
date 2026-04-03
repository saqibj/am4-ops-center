# AM4 RouteMine — Dashboard Specification

> **Stack:** FastAPI + Tailwind CSS + HTMX
> **Replaces:** Streamlit dashboard (dashboard/app.py)
> **Data source:** SQLite database (`am4_data.db`) produced by the extractor

---

## 1. Architecture

```
┌─────────────────────────────────────────────────┐
│                   Browser                        │
│  Tailwind CSS (styling) + HTMX (interactivity)  │
│  Chart.js (charts, loaded via CDN/local)         │
└──────────────────┬──────────────────────────────┘
                   │  HTTP (localhost)
┌──────────────────▼──────────────────────────────┐
│              FastAPI Backend                      │
│  Jinja2 templates    SQLite queries              │
│  JSON endpoints      Static file serving         │
└──────────────────┬──────────────────────────────┘
                   │
            ┌──────▼──────┐
            │  am4_data.db │
            │   (SQLite)   │
            └─────────────┘
```

### Key design decisions

- **Server-rendered HTML** — FastAPI renders pages via Jinja2; HTMX swaps fragments on interaction (no full page reloads)
- **No JS framework** — HTMX handles all interactivity via HTML attributes (`hx-get`, `hx-target`, `hx-trigger`)
- **Tailwind via CDN** — `<script src="https://cdn.tailwindcss.com">` for dev; for offline use, download the standalone CSS or use the Tailwind CLI to build a local file
- **Chart.js via CDN** — for bar/line/pie charts; for offline use, download `chart.min.js` locally
- **Fully offline capable** — bundle Tailwind CSS and Chart.js locally in `dashboard/static/`

---

## 2. Project Structure

```
dashboard/
├── __init__.py
├── server.py              # FastAPI app, routes, startup
├── db.py                  # SQLite connection, query helpers
├── templates/
│   ├── base.html          # Layout: nav, head, Tailwind, HTMX, Chart.js
│   ├── index.html         # Landing / overview page
│   ├── hub_explorer.html  # Hub Explorer page
│   ├── aircraft.html      # Aircraft Comparison page
│   ├── route_analyzer.html # Route Analyzer page
│   ├── fleet_planner.html # Fleet Planner page
│   ├── contributions.html # Contribution Optimizer page
│   ├── heatmap.html       # Global Heatmap page
│   └── partials/          # HTMX fragment templates
│       ├── route_table.html
│       ├── aircraft_table.html
│       ├── chart_data.html
│       └── stats_cards.html
├── static/
│   ├── css/
│   │   └── tailwind.min.css   # (optional offline Tailwind build)
│   ├── js/
│   │   ├── chart.min.js       # Chart.js (local copy for offline)
│   │   └── app.js             # Minimal custom JS (chart init helpers)
│   └── favicon.ico
```

---

## 3. FastAPI Backend (server.py)

### 3.1 App setup

```python
from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import sqlite3
import os

app = FastAPI(title="AM4 RouteMine Dashboard")
app.mount("/static", StaticFiles(directory="dashboard/static"), name="static")
templates = Jinja2Templates(directory="dashboard/templates")

DB_PATH = os.environ.get("AM4_ROUTEMINE_DB", "am4_data.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
```

### 3.2 Page routes (return full HTML)

```
GET /                        → index.html (overview stats)
GET /hub-explorer            → hub_explorer.html
GET /aircraft                → aircraft.html
GET /route-analyzer          → route_analyzer.html
GET /fleet-planner           → fleet_planner.html
GET /contributions           → contributions.html
GET /heatmap                 → heatmap.html
```

### 3.3 HTMX partial routes (return HTML fragments)

```
GET /api/hub-routes?hub=KHI&sort=profit&limit=50      → partials/route_table.html
GET /api/aircraft-routes?aircraft=b738&limit=50        → partials/aircraft_table.html
GET /api/route-compare?origin=KHI&dest=LHR             → partials/aircraft_table.html
GET /api/fleet-plan?hub=KHI&budget=500000000            → partials/route_table.html
GET /api/contributions?limit=50                         → partials/route_table.html
GET /api/heatmap-data?hub=KHI                           → JSON (for Chart.js/map)
GET /api/stats                                          → partials/stats_cards.html
GET /api/hubs                                           → JSON list of hubs in DB
GET /api/aircraft-list                                  → JSON list of aircraft in DB
```

### 3.4 JSON endpoints (for Chart.js and dropdowns)

```
GET /api/chart/profit-by-aircraft?hub=KHI&limit=20     → JSON {labels, data}
GET /api/chart/profit-by-distance?hub=KHI              → JSON {labels, data}
GET /api/chart/haul-breakdown?hub=KHI                   → JSON {short, medium, long}
```

---

## 4. Pages

### 4.1 Overview / Index (`/`)

- **Stats cards:** Total hubs extracted, total routes, total aircraft, DB size, last extraction timestamp
- **Quick links** to each page
- **Top 10 routes** across all hubs (profit/day)

### 4.2 Hub Explorer (`/hub-explorer`)

- **Hub dropdown** (searchable, populated from DB)
- **Filters:** aircraft type (PAX/CARGO/VIP), min profit, max flight time, show/hide stopovers
- **Sort:** profit/trip, profit/day, contribution, income
- **Results table** (HTMX-loaded):
  - Destination, Aircraft, Config (Y/J/F), Profit/Trip, Trips/Day, Profit/Day, Contribution, Flight Time, Stopover
- **Bar chart:** Top 20 routes by profit/day (Chart.js)
- **Summary stats:** Total viable routes, avg profit, best route

### 4.3 Aircraft Comparison (`/aircraft`)

- **Aircraft dropdown** (searchable)
- **Results table:** Best routes for selected aircraft across all hubs
- **Bar chart:** Top hubs for this aircraft by avg daily profit

### 4.4 Route Analyzer (`/route-analyzer`)

- **Origin + Destination dropdowns**
- **Results table:** All aircraft ranked for that route
- **Comparison chart:** profit/day by aircraft

### 4.5 Fleet Planner (`/fleet-planner`)

- **Hub dropdown + Budget input**
- **Algorithm:** Given budget, recommend aircraft purchases and routes to maximize daily profit
- **Output table:** Aircraft to buy, routes to assign, estimated daily revenue

### 4.6 Contribution Optimizer (`/contributions`)

- **Table:** All routes sorted by alliance contribution, with profit alongside
- **Filter by hub**
- **Contribution/profit ratio column** for identifying high-contribution-per-dollar routes

### 4.7 Global Heatmap (`/heatmap`)

- **Hub dropdown**
- **Map visualization** using Leaflet.js (lightweight, offline-capable with tile caching)
- **Markers** for each destination, colored by profit tier
- **Click marker** → popup with route details

---

## 5. HTMX Patterns

### 5.1 Dropdown triggers table reload

```html
<select name="hub" hx-get="/api/hub-routes" hx-target="#route-table"
        hx-include="[name='sort'],[name='type']" hx-trigger="change">
  {% for hub in hubs %}
  <option value="{{ hub.iata }}">{{ hub.iata }} — {{ hub.name }}</option>
  {% endfor %}
</select>

<div id="route-table">
  {% include "partials/route_table.html" %}
</div>
```

### 5.2 Sort column headers

```html
<th>
  <a hx-get="/api/hub-routes?hub={{ hub }}&sort=profit_per_ac_day"
     hx-target="#route-table" class="cursor-pointer hover:text-blue-400">
    Profit/Day ↕
  </a>
</th>
```

### 5.3 Loading indicator

```html
<div id="route-table" hx-indicator="#spinner">
  <!-- content swapped by HTMX -->
</div>
<div id="spinner" class="htmx-indicator">
  <svg class="animate-spin h-5 w-5 ...">...</svg> Loading...
</div>
```

---

## 6. Tailwind Styling Guidelines

### Color scheme

- **Background:** `bg-gray-900` (dark mode default)
- **Cards:** `bg-gray-800 rounded-lg shadow-lg p-6`
- **Text:** `text-gray-100` (primary), `text-gray-400` (secondary)
- **Accent:** `text-emerald-400` (profit positive), `text-red-400` (negative)
- **Table headers:** `bg-gray-700 text-gray-300 text-xs uppercase tracking-wider`
- **Table rows:** `hover:bg-gray-700 transition-colors`
- **Buttons/dropdowns:** `bg-gray-700 border-gray-600 text-white rounded-md`

### Typography

- Font: `font-mono` for numbers/codes (IATA, shortnames, prices)
- Font: default sans for everything else
- Profit numbers: formatted with `$` and commas, green if positive, red if negative

### Responsive

- Sidebar nav on desktop (w-64), hamburger menu on mobile
- Tables horizontally scroll on small screens (`overflow-x-auto`)

---

## 7. base.html Template Structure

```html
<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AM4 RouteMine — {% block title %}Dashboard{% endblock %}</title>

  <!-- Tailwind (use local file for offline) -->
  <script src="https://cdn.tailwindcss.com"></script>
  <!-- Or: <link rel="stylesheet" href="/static/css/tailwind.min.css"> -->

  <!-- HTMX -->
  <script src="https://unpkg.com/htmx.org@2.0.4"></script>

  <!-- Chart.js -->
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>

  <!-- Leaflet (for heatmap) -->
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9/dist/leaflet.css" />
  <script src="https://unpkg.com/leaflet@1.9/dist/leaflet.js"></script>
</head>
<body class="bg-gray-900 text-gray-100 min-h-screen flex">

  <!-- Sidebar -->
  <nav class="w-64 bg-gray-800 border-r border-gray-700 p-4 space-y-2 hidden lg:block">
    <h1 class="text-xl font-bold text-emerald-400 mb-6">AM4 RouteMine</h1>
    <a href="/" class="block px-3 py-2 rounded hover:bg-gray-700">Overview</a>
    <a href="/hub-explorer" class="block px-3 py-2 rounded hover:bg-gray-700">Hub Explorer</a>
    <a href="/aircraft" class="block px-3 py-2 rounded hover:bg-gray-700">Aircraft</a>
    <a href="/route-analyzer" class="block px-3 py-2 rounded hover:bg-gray-700">Route Analyzer</a>
    <a href="/fleet-planner" class="block px-3 py-2 rounded hover:bg-gray-700">Fleet Planner</a>
    <a href="/contributions" class="block px-3 py-2 rounded hover:bg-gray-700">Contributions</a>
    <a href="/heatmap" class="block px-3 py-2 rounded hover:bg-gray-700">Heatmap</a>
  </nav>

  <!-- Main content -->
  <main class="flex-1 p-6 overflow-auto">
    {% block content %}{% endblock %}
  </main>

</body>
</html>
```

---

## 8. CLI Integration

Update `main.py` dashboard command:

```python
# dashboard command
dash = subparsers.add_parser("dashboard", help="Launch web dashboard")
dash.add_argument("--db", type=str, default="am4_data.db")
dash.add_argument("--port", type=int, default=8000)
dash.add_argument("--host", type=str, default="0.0.0.0")
```

Launch:

```python
def cmd_dashboard(args):
    import uvicorn
    os.environ["AM4_ROUTEMINE_DB"] = args.db
    uvicorn.run("dashboard.server:app", host=args.host, port=args.port, reload=True)
```

Usage:

```bash
python main.py dashboard                    # http://localhost:8000
python main.py dashboard --port 3000        # http://localhost:3000
python main.py dashboard --db custom.db     # use different database
```

---

## 9. Dependencies (add to requirements.txt)

```
fastapi>=0.115.0
uvicorn>=0.30.0
jinja2>=3.1.0
python-multipart>=0.0.9
```

**Remove:** `streamlit>=1.30.0` (no longer needed)

---

## 10. Offline Bundling

For fully offline use, download these files into `dashboard/static/`:

```bash
# From project root
mkdir -p dashboard/static/js dashboard/static/css

# HTMX
curl -o dashboard/static/js/htmx.min.js https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js

# Chart.js
curl -o dashboard/static/js/chart.min.js https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js

# Leaflet
curl -o dashboard/static/js/leaflet.js https://unpkg.com/leaflet@1.9/dist/leaflet.js
curl -o dashboard/static/css/leaflet.css https://unpkg.com/leaflet@1.9/dist/leaflet.css

# Tailwind (standalone CSS build)
npx tailwindcss -o dashboard/static/css/tailwind.min.css --minify
```

Then update `base.html` to reference `/static/` paths instead of CDN URLs.

> **Note:** Leaflet map tiles still require internet unless you cache tiles locally. The dashboard will work offline for all pages except the map background imagery.
