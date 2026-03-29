# AM4 RouteMine

Python CLI that uses the [`am4`](https://github.com/abc8747/am4) package to extract aircraft, airports, and route economics into SQLite, with CSV/Excel export and a Streamlit dashboard.

See **am4-routemine-PRD.md** and **am4-routemine-SETUP-GUIDE.md** for full specification and WSL setup.

## Quick start (WSL Ubuntu)

```bash
cd am4-routemine
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python main.py extract --hubs KHI,DXB --mode easy --ci 200
python main.py query --hub KHI --top 20
python main.py dashboard
```

Always call `from am4.utils.db import init; init()` before am4 lookups; `extract` does this internally.

## Commands

- `python main.py extract --hubs IATA1,IATA2` or `--all-hubs`
- `python main.py export --format csv --output ./exports/`
- `python main.py query --hub KHI --top 20`
- `python main.py dashboard --port 8501`
